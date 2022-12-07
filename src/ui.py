import ctypes
import enum
import multiprocessing as mp
import os
import subprocess as sp
import sys
import time
import tkinter as tk
import traceback
import types
from pathlib import Path

import customtkinter as ctk
import cv2
import psutil
from PIL import Image

# these imports may not be able to be resolved by the IDE. this is fine.
import win32api, win32con, win32event, win32gui, win32process, win32ui
from python_imagesearch.imagesearch import imagesearcharea
from win32com.shell.shell import ShellExecuteEx
from win32com.shell import shellcon


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


def kill_process():
    proc_iter = psutil.process_iter()
    gta_proc = next((p for p in proc_iter if p.name().startswith("GTA5")), None)
    if gta_proc is None:
        # TODO: logging
        raise RuntimeError("failed to find GTA5 process")
    gta_proc.kill()


def disable_network():
    interfaces = psutil.net_if_addrs()
    interface_names = tuple(
        filter(lambda x: not (x.lower().startswith("loopback") or x.lower().startswith("local")), interfaces))
    netsh_command = "netsh interface set interface"
    for name in interface_names:
        disable_result = sp.run(f'{netsh_command} "{name}" disable', shell=True)
        if disable_result.returncode != 0:
            print(f"failed to disable {name}")

    time.sleep(20)
    for name in interface_names:
        disable_result = sp.run(f'{netsh_command} "{name}" enabled', shell=True)
        if disable_result.returncode != 0:
            print(f"failed to re-enable {name}")


def resize_image(image_path: Path, monitor_width: int):
    img = cv2.imread(str(image_path), cv2.IMREAD_UNCHANGED)
    scale_factor = monitor_width / 2560
    width = int(img.shape[1] * scale_factor)
    height = int(img.shape[0] * scale_factor)
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
        except Exception as e:
            print("error capturing window image", e)
            traceback.print_exc()
        else:
            pos = imagesearcharea(image_path, x1, y1, x2, y2, 0.7, im=im)
        time.sleep(timeout)
    return pos


def resource_path(relative_path):
    """https://stackoverflow.com/questions/31836104/pyinstaller-and-onefile-how-to-include-an-image-in-the-exe-file"""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


def image_search_worker(kill_func: callable):
    print("starting image search worker")
    gta_hwnd = win32gui.FindWindow(None, "Grand Theft Auto V")
    if gta_hwnd == 0:
        width, height = get_main_monitor_resolution()
    else:
        x, y, w, h = win32gui.GetWindowRect(gta_hwnd)
        width = w - x
        height = h - y
    x1 = 0
    y1 = round(height / 5.76)
    x2 = width
    y2 = y1 + 1000
    resized_image_path = Path(resource_path("heist_passed_resized.jpg"))
    cropped_image_path = Path(resource_path("heist_passed_cropped.jpg"))
    resized_image_path.unlink(missing_ok=True)
    resize_image(cropped_image_path, width)

    while True:
        pos = image_search_loop(width, height, x1, y1, x2, y2, str(resized_image_path))
        print(f"found heist passed at {pos}")
        # wait a tiny bit to make sure the heist is over
        # the number is completely arbitrary, but it seems to work
        time.sleep(0.6)
        kill_func()


class RunOptions(enum.Enum):
    KILL_PROCESS = 0,
    DISABLE_NETWORK = 1,


class App(ctk.CTk):
    def __init__(self, fg_color=None, **kwargs):
        super().__init__(fg_color, **kwargs)

        self.title("GTA Cayo Perico Heist Closer")
        self.geometry("400x400")

        self.grid_rowconfigure(4, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # main monitor resolution
        self._monitor_resolution = get_main_monitor_resolution()

        # main monitor resolution label
        res_str = f"{self._monitor_resolution[0]} x{self._monitor_resolution[1]}"
        self._monitor_resolution_label = ctk.CTkLabel(self, text=f"Main monitor resolution: {res_str}")
        self._monitor_resolution_label.grid(row=0, column=0, padx=10, pady=10, columnspan=1, sticky="nsew")

        self._is_running_var = tk.BooleanVar(value=False)

        self._start_button = ctk.CTkButton(self, text="Start", command=self._handle_start_clicked, width=10)
        self._start_button.grid(row=1, column=0, padx=10, pady=10, columnspan=1, sticky="nsew")

        self._radio_label = ctk.CTkLabel(self, text="Close type:", anchor=tk.W)
        self._radio_label.grid(row=2, column=0, padx=10, pady=10, columnspan=1, sticky="nsew")

        self._run_var = tk.IntVar(value=RunOptions.KILL_PROCESS.value[0])

        self._kill_process_radio = ctk.CTkRadioButton(self, text="Kill process", variable=self._run_var,
                                                      value=RunOptions.KILL_PROCESS.value[0])
        self._kill_process_radio.grid(row=3, column=0, padx=10, pady=10, columnspan=1, sticky="nsew")

        self._disable_network_radio = ctk.CTkRadioButton(self, text="Disable network", variable=self._run_var,
                                                         value=RunOptions.DISABLE_NETWORK.value[0])
        self._disable_network_radio.grid(row=4, column=0, padx=10, pady=10, columnspan=1, sticky="nsew")

        self._is_running_var.trace_add("write", self._handle_is_running_var_changed)

    def _handle_is_running_var_changed(self, *_):
        if self._is_running_var.get():
            self._start_button.configure(text="Stop", command=self._handle_stop_clicked)
            self._kill_process_radio.configure(state=tk.DISABLED)
            self._disable_network_radio.configure(state=tk.DISABLED)
            kill_func = None
            run_var_val = self._run_var.get()
            if run_var_val == 0:
                kill_func = kill_process
            elif run_var_val == 1:
                kill_func = disable_network
            self._worker_proc = mp.Process(target=image_search_worker, args=(kill_func,),
                                           daemon=True)
            self._worker_proc.start()
        else:
            self._start_button.configure(text="Start", command=self._handle_start_clicked)
            self._kill_process_radio.configure(state=tk.NORMAL)
            self._disable_network_radio.configure(state=tk.NORMAL)

    def _handle_start_clicked(self):
        self._is_running_var.set(True)
        # can't put this in the var handler, it just doesn't work for some reason
        while self._worker_proc.is_alive():
            self.update()
        self._is_running_var.set(False)

    def _handle_stop_clicked(self):
        self._worker_proc.terminate()


if __name__ == '__main__':
    # check for _MEIPASS
    if getattr(sys, 'frozen', False):
        mp.freeze_support()
    if not is_user_admin():
        run_as_admin()
    else:
        app = App()
        app.mainloop()
