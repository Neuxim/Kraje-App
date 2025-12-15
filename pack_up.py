import os
import subprocess
import shutil
import sys

APP_NAME = "Kraje"
MAIN_SCRIPT = "main.py"
ASSETS_DIR = "assets"
ENCYCLOPEDIA_FILE = "encyclopedia_data.json"

def run_command(command):
    print(f"--- Running command: {' '.join(command)} ---")
    try:
        process = subprocess.Popen(
            command, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT, 
            text=True, 
            encoding='utf-8',
            errors='replace',
            bufsize=1
        )

        while True:
            output = process.stdout.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                print(output.strip())
        
        rc = process.poll()
        if rc != 0:
            print(f"--- Command failed with exit code {rc} ---")
            sys.exit(rc)
            
    except FileNotFoundError:
        print(f"Error: Command '{command[0]}' not found. Make sure it's in your system's PATH.")
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        sys.exit(1)
        
    print("--- Command finished successfully ---")

def main():
    print("Starting the packaging process...")

    try:
        subprocess.run(["pyinstaller", "--version"], check=True, capture_output=True)
        print("PyInstaller is found.")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Error: PyInstaller is not installed or not in the system's PATH.")
        print("Please install it by running: pip install pyinstaller")
        sys.exit(1)

    if not os.path.exists(MAIN_SCRIPT):
        print(f"Error: Main script '{MAIN_SCRIPT}' not found.")
        sys.exit(1)
    if not os.path.isdir(ASSETS_DIR):
        print(f"Error: Assets directory '{ASSETS_DIR}' not found.")
        sys.exit(1)
    if not os.path.exists(ENCYCLOPEDIA_FILE):
        print(f"Error: Encyclopedia data file '{ENCYCLOPEDIA_FILE}' not found.")
        sys.exit(1)

    command = [
        "pyinstaller",
        "--name", APP_NAME,
        "--onefile",
        "--windowed",
        "--add-data", f"{ASSETS_DIR}{os.pathsep}{ASSETS_DIR}",
        "--add-data", f"{ENCYCLOPEDIA_FILE}{os.pathsep}.",
        "--hidden-import=requests",
        "--hidden-import=cryptography",
    ]
    
    # --- FIX for missing DLL ---
    python_dir = sys.prefix
    dll_name = "python312.dll" 
    dll_path = os.path.join(python_dir, dll_name)
    
    if os.path.exists(dll_path):
        print(f"Found and adding {dll_name} from {dll_path}")
        command.extend(["--add-binary", f"{dll_path}{os.pathsep}."])
    else:
        print(f"WARNING: {dll_name} not found in {python_dir}. This may cause runtime errors.")
        print("Please ensure your Python installation is correct.")
    
    command.append(MAIN_SCRIPT)
    # --- END FIX ---

    run_command(command)

    print("Cleaning up temporary build files...")
    spec_file = f"{APP_NAME}.spec"
    build_dir = "build"
    
    if os.path.exists(spec_file):
        os.remove(spec_file)
        print(f"Removed {spec_file}")
    if os.path.isdir(build_dir):
        shutil.rmtree(build_dir)
        print(f"Removed '{build_dir}' directory.")
    
    print("\n----------------------------------------------------")
    print("Packaging complete!")
    print(f"The executable can be found in the '{os.path.abspath('dist')}' directory.")
    print("----------------------------------------------------")


if __name__ == "__main__":
    main()