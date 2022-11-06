import os
import psutil
import signal
import subprocess as sp
import time

from python_imagesearch.imagesearch import imagesearch_region_loop

NETSH_COMMAND = 'netsh interface set interface "Ethernet"'


def get_main_monitor_resolution():
    import ctypes

    user32 = ctypes.windll.user32
    screensize = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    return screensize


print(get_main_monitor_resolution())


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


def main():
    mon_width, mon_height = get_main_monitor_resolution()
    x1 = 0
    y1 = round(mon_height / 5.76)
    x2 = mon_width
    y2 = y1 + 1000
    print("Searching for image...")
    image_path = os.path.join(os.path.dirname(__file__), "heist_passed_cropped.jpg")
    #? TODO: custom impl to cap directly from window
    pos = imagesearch_region_loop(image_path, 0.2, x1, y1, x2, y2, 0.7)
    if pos[0] == -1:
        print("the image was somehow not found")
        return
    print(f"image located at {pos[0]}, {pos[1]}")
    time.sleep(1)
    # disable_network()
    kill_process()


if __name__ == "__main__":
    main()
