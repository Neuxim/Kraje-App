import sys
import subprocess
import os

print("--- Python Interpreter Information ---")
# Get the full path of the Python executable running this script
python_executable = sys.executable
print(f"This script is running with Python at: {python_executable}\n")

# Check if the path is inside a virtual environment
if "venv" in python_executable or ".venv" in python_executable:
    print("This appears to be a virtual environment. That's good!\n")
else:
    print("WARNING: You are using a global Python installation.")
    print("It is highly recommended to use a virtual environment to avoid conflicts.\n")

print("--- Checking for 'cryptography' package ---")
try:
    # Use the *same Python executable* to run pip and check for the package
    result = subprocess.run(
        [python_executable, "-m", "pip", "show", "cryptography"],
        capture_output=True,
        text=True,
        check=True
    )
    print("Found it! Details below:")
    print(result.stdout)
    
    location_line = [line for line in result.stdout.split('\n') if line.startswith('Location:')][0]
    location_path = location_line.split(': ')[1].strip()

    print("\n--- DIAGNOSIS ---")
    if os.path.dirname(python_executable).lower() in location_path.lower():
        print("\033[92mSUCCESS: 'cryptography' is installed in the correct location for this Python interpreter.\033[0m")
    else:
        print("\033[91mERROR: Mismatch detected!\033[0m")
        print(f"Your Python is at: {os.path.dirname(python_executable)}")
        print(f"But the package is installed at: {location_path}")
        print("They are not in the same environment. This is the source of your error.")

except subprocess.CalledProcessError:
    print("\033[91mERROR: 'cryptography' is NOT installed for this Python interpreter.\033[0m")
    print(f"Please run this exact command to install it:")
    print(f'"{python_executable}" -m pip install cryptography')