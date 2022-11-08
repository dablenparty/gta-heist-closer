import ctypes
import os
from pathlib import Path
import traceback
import psutil
import signal
import subprocess as sp
import time

import cv2
from python_imagesearch.imagesearch import imagesearch_region_loop

NETSH_COMMAND = 'netsh interface set interface "Ethernet"'


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


def get_main_monitor_resolution():
    user32 = ctypes.windll.user32
    screensize = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    return screensize


def disable_network():
    print(f"disabling ethernet")
    disable_result = sp.run(NETSH_COMMAND + " disable", shell=True)
    if disable_result.returncode != 0:
        print("failed to disable ethernet")
        return
    # wait 30 seconds
    timeout = 30
    for i in range(timeout):
        print(f"\33[2Kwaiting {timeout - i} seconds", end="\r", flush=True)
        time.sleep(1)
    print("re-enabling ethernet")
    enable_result = sp.run(NETSH_COMMAND + " enable", shell=True)
    if enable_result.returncode != 0:
        print("failed to enable ethernet")


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
    # disable_network()
    kill_process()
    input("press enter to exit...")

if __name__ == "__main__":
    main()
