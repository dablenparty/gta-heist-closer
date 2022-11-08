from pathlib import Path
import subprocess as sp
import sys


def main():
    this_interpreter = sys.executable
    this_file = Path(__file__).resolve()
    virtual_env_dir = this_file.parent / ".venv"
    virtual_interpreter = virtual_env_dir / "Scripts" / "python.exe"
    print("checking if virtual environment exists")
    if not virtual_env_dir.exists():
        print("virtual environment does not exist, creating...")
        output = sp.check_output([this_interpreter, "-m", "pip", "list"])
        decoded = output.decode("utf-8")
        lines = decoded.splitlines()
        has_virtualenv = False
        for line in lines:
            if line.startswith("virtualenv"):
                has_virtualenv = True
                break
        if not has_virtualenv:
            raise RuntimeError("virtualenv not installed but required")
        sp.run([this_interpreter, "-m", "virtualenv", virtual_env_dir])
        requirements_file = this_file.parent / "requirements.txt"
        sp.run([virtual_interpreter, "-m", "pip", "install", "-r", requirements_file])
    print(f"virtual environment found at {virtual_env_dir}")
    print("running main.py")
    sp.run([virtual_interpreter, this_file.parent / "main.py"])


if __name__ == "__main__":
    main()
