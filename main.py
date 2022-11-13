import argparse as ap
import ctypes
import os
from pathlib import Path
import traceback
import psutil
import signal
import subprocess as sp
import sys
import time
import types

import cv2
from python_imagesearch.imagesearch import imagesearch_region_loop


def parse_args():
    parser = ap.ArgumentParser()
    parser.add_argument(
        "--network",
        "-n",
        action="store_true",
        help="disables network instead of killing GTA process",
    )
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

    if os.name != "nt":
        raise RuntimeError("This function is only implemented on Windows.")

    # these imports may not be able to be resolved by vscode. this is fine.
    import win32api, win32con, win32event, win32process
    from win32com.shell.shell import ShellExecuteEx
    from win32com.shell import shellcon

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


def disable_network():
    interfaces = psutil.net_if_addrs()

    def interface_filter(interface_name: str):
        lower_name = interface_name.lower()
        return not (
            lower_name.startswith("local area connection")
            or lower_name.startswith("loopback")
        )

    interface_names = tuple(filter(interface_filter, interfaces.keys()))
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
    proc_iter = psutil.process_iter(attrs=None, ad_value=None)
    gta_process = next((p for p in proc_iter if p.name().startswith("GTA5")), None)
    if gta_process is None:
        print("failed to find GTA5 process")
        return
    pid = gta_process.pid
    print(f"found gta process with pid {pid}")
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

    print("Searching for image...")
    # ? TODO: custom impl to cap directly from window
    pos = imagesearch_region_loop(str(image_path), 0.2, x1, y1, x2, y2, 0.7)
    if pos[0] == -1:
        print("the image was somehow not found")
        return
    print(f"image located at {pos[0]}, {pos[1]}")
    time.sleep(1)
    if args.network:
        disable_network()
    else:
        kill_process()


if __name__ == "__main__":
    main()
