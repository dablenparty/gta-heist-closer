import os

if os.name != "nt":
    raise RuntimeError("This script is only implemented on Windows.")

import argparse as ap
import ctypes
from pathlib import Path
import traceback
import signal
import subprocess as sp
import sys
import time
import types

import cv2
from python_imagesearch.imagesearch import imagesearch_region_loop, imagesearcharea
from PIL import Image

# these imports may not be able to be resolved by vscode. this is fine.
import win32api, win32con, win32event, win32gui, win32process, win32ui
from win32com.shell.shell import ShellExecuteEx
from win32com.shell import shellcon


def parse_args():
    parser = ap.ArgumentParser()
    parser.add_argument(
        "--network",
        "-n",
        action="store_true",
        help="disables network instead of killing GTA process",
    )
    parser.add_argument("--loop", "-l", action="store_true", help="loops the script")
    return parser.parse_args()


def is_user_admin():
    """
    Checks if the current user has admin privileges.

    Taken from: https://gist.github.com/sylvainpelissier/ff072a6759082590a4fe8f7e070a4952

    :return: True if the user has admin privileges, False otherwise.
    :rtype: bool
    """
    if os.name == "nt":
        try:
            return ctypes.windll.shell32.IsUserAnAdmin()
        except Exception:
            traceback.print_exc()
            print("Admin check failed, assuming not an admin.")
            return False
    else:
        # check for root on posix
        return os.getuid() == 0


def run_as_admin(cmdLine=None, wait=True):
    """
    Taken from: https://gist.github.com/sylvainpelissier/ff072a6759082590a4fe8f7e070a4952

    Attempt to relaunch the current script as an admin using the same
    command line parameters.  Pass cmdLine in to override and set a new
    command.  It must be a list of [command, arg1, arg2...] format.
    Set wait to False to avoid waiting for the sub-process to finish. You
    will not be able to fetch the exit code of the process if wait is
    False.
    Returns the sub-process return code, unless wait is False in which
    case it returns None.
    @WARNING: this function only works on Windows.
    """

    python_exe = sys.executable

    if cmdLine is None:
        cmdLine = [python_exe] + sys.argv
    elif type(cmdLine) not in (types.TupleType, types.ListType):
        raise ValueError("cmdLine is not a sequence.")
    cmd = '"%s"' % (cmdLine[0],)
    # XXX TODO: isn't there a function or something we can call to massage command line params?
    params = " ".join(['"%s"' % (x,) for x in cmdLine[1:]])
    cmdDir = ""
    showCmd = win32con.SW_SHOWNORMAL
    lpVerb = "runas"  # causes UAC elevation prompt.

    # print "Running", cmd, params

    # ShellExecute() doesn't seem to allow us to fetch the PID or handle
    # of the process, so we can't get anything useful from it. Therefore
    # the more complex ShellExecuteEx() must be used.

    # procHandle = win32api.ShellExecute(0, lpVerb, cmd, params, cmdDir, showCmd)

    procInfo = ShellExecuteEx(
        nShow=showCmd,
        fMask=shellcon.SEE_MASK_NOCLOSEPROCESS,
        lpVerb=lpVerb,
        lpFile=cmd,
        lpParameters=params,
    )

    if wait:
        procHandle = procInfo["hProcess"]
        obj = win32event.WaitForSingleObject(procHandle, win32event.INFINITE)
        rc = win32process.GetExitCodeProcess(procHandle)
    else:
        rc = None

    return rc


def get_main_monitor_resolution():
    user32 = ctypes.windll.user32
    screensize = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    return screensize


def get_net_interfaces():
    output = sp.run("netsh interface show interface", shell=True, capture_output=True)
    if output.returncode != 0:
        raise RuntimeError("failed to get network interfaces")
    decoded_output = output.stdout.decode("utf-8")
    lines = decoded_output.splitlines()
    # windows output has a blank line, column names, then a separator, with a blank at the end
    lines = lines[3:-1]
    splits = [line.split() for line in lines]
    return tuple(
        map(lambda x: (x[0] == "Enabled", x[1] == "Connected", x[2], x[3]), splits)
    )


def find_process_by_name(name: str):
    command = f'tasklist /fi "imagename eq {name}"'
    output = sp.run(command, shell=True, capture_output=True)
    if output.returncode != 0:
        raise RuntimeError(f"failed to find process {name}")
    decoded_output = output.stdout.decode("utf-8")
    lines = decoded_output.splitlines()
    if len(lines) <= 3:
        raise RuntimeError(f"failed to find process {name}: {decoded_output}")
    lines = lines[3:]
    splits = [line.split() for line in lines]
    return tuple(map(lambda x: (x[0], int(x[1]), x[2], int(x[3]), x[4]), splits))


def disable_network():
    interfaces = get_net_interfaces()
    interface_names = tuple(map(lambda x: x[3], filter(lambda x: x[0], interfaces)))
    netsh_command = "netsh interface set interface"
    for name in interface_names:
        print(f"disabling {name}")
        disable_result = sp.run(f'{netsh_command} "{name}" disable', shell=True)
        if disable_result.returncode != 0:
            print(f"failed to disable {name}")

    # TODO: make this a command line arg
    timeout = 20
    for i in range(timeout):
        print(f"\33[2Kwaiting {timeout - i} seconds", end="\r", flush=True)
        time.sleep(1)
    print()
    for name in interface_names:
        print(f"re-enabling {name}")
        disable_result = sp.run(f'{netsh_command} "{name}" enabled', shell=True)
        if disable_result.returncode != 0:
            print(f"failed to re-enable {name}")


def kill_process():
    print("finding GTA5 process")
    proc_iter = find_process_by_name("GTA5.exe")
    gta_process = next((p for p in proc_iter if p[0].startswith("GTA5")), None)
    if gta_process is None:
        print("failed to find GTA5 process")
        return
    pid = gta_process[1]
    print(f"found gta process with pid {pid}")
    timeout = 0.2
    print(f"waiting {timeout} second")
    time.sleep(timeout)
    # kill gta process
    print("killing gta process")
    os.kill(int(pid), signal.SIGTERM)


def resize_image(image_path: Path, monitor_width: int):
    img = cv2.imread(str(image_path), cv2.IMREAD_UNCHANGED)
    scale_percent = monitor_width / 2560
    width = int(img.shape[1] * scale_percent)
    height = int(img.shape[0] * scale_percent)
    new_dim = (width, height)
    resized_img = cv2.resize(img, new_dim, interpolation=cv2.INTER_AREA)
    cv2.imwrite(str(image_path.parent / "heist_passed_resized.jpg"), resized_img)


def capture_window_image(window_name: str, monitor_width: int, monitor_height: int):
    """
    Captures the window with the given name and returns it as a PIL image.

    Taken from: https://stackoverflow.com/questions/6951557/pil-and-bitmap-from-winapi

    :param window_name: name of the window to capture
    :type window_name: str
    :param monitor_width: width of the monitor
    :type monitor_width: int
    :param monitor_height: height of the monitor
    :type monitor_height: int
    :raises ValueError: if the window is not found
    :return: the captured window as a PIL image
    :rtype: Image
    """
    # there are ways to make this faster; however, at 0.02 seconds on a bad day (aka 60 fps), it's
    # fast enough
    window_handle = win32gui.FindWindow(None, window_name)
    if window_handle == 0:
        raise ValueError(f"failed to find window {window_name}")
    window_DC = win32gui.GetWindowDC(window_handle)
    dc_obj = win32ui.CreateDCFromHandle(window_DC)
    compatible_cd = dc_obj.CreateCompatibleDC()

    data_bit_map = win32ui.CreateBitmap()
    data_bit_map.CreateCompatibleBitmap(dc_obj, monitor_width, monitor_height)
    compatible_cd.SelectObject(data_bit_map)
    compatible_cd.BitBlt(
        (0, 0), (monitor_width, monitor_height), dc_obj, (0, 0), win32con.SRCCOPY
    )

    bitmap_info = data_bit_map.GetInfo()
    bitmap_bits = data_bit_map.GetBitmapBits(True)
    im = Image.frombuffer(
        "RGB",
        (bitmap_info["bmWidth"], bitmap_info["bmHeight"]),
        bitmap_bits,
        "raw",
        "BGRX",
        0,
        1,
    )

    # free resources
    dc_obj.DeleteDC()
    compatible_cd.DeleteDC()
    win32gui.ReleaseDC(window_handle, window_DC)
    win32gui.DeleteObject(data_bit_map.GetHandle())

    return im


def image_search_loop(
    mon_width: int,
    mon_height: int,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    image_path: str,
    timeout=0.2,
):
    pos = (-1, -1)
    while pos[0] == -1:
        try:
            im = capture_window_image("Grand Theft Auto V", mon_width, mon_height)
        except ValueError:
            pass
        else:
            pos = imagesearcharea(image_path, x1, y1, x2, y2, 0.7, im=im)
        time.sleep(timeout)
    return pos


def main():
    args = parse_args()
    if args.network:
        print('using "disable network"')
        if not is_user_admin():
            print("not running as admin, relaunching as admin")
            ret = run_as_admin()
            sys.exit(ret)
    else:
        print('using "kill process"')
    mon_width, mon_height = get_main_monitor_resolution()
    x1 = 0
    y1 = round(mon_height / 5.76)
    x2 = mon_width
    y2 = y1 + 1000
    this_file = Path(__file__).resolve()
    image_path = this_file.parent / "heist_passed_resized.jpg"
    if not image_path.exists():
        print("resizing image")
        resize_image(this_file.parent / "heist_passed_cropped.jpg", mon_width)

    ran_once = False
    while not ran_once or args.loop:
        print("Searching for image...")
        pos = image_search_loop(mon_width, mon_height, x1, y1, x2, y2, str(image_path))
        print(f"image located at {pos[0]}, {pos[1]}")
        time.sleep(1)
        if args.network:
            disable_network()
        else:
            kill_process()
        ran_once = True


if __name__ == "__main__":
    main()
