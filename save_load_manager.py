import json
import os
import sys
import subprocess
import shutil
import config as c
from cryptography.fernet import Fernet

IS_ANDROID = 'ANDROID_ARGUMENT' in os.environ
cipher_suite = Fernet(c.ENCRYPTION_KEY)




def ensure_turns_directory():
    if not os.path.exists(c.PLAYER_TURNS_DIR):
        os.makedirs(c.PLAYER_TURNS_DIR)

def run_git_command(commands):
    """Runs a git command list and prints output."""
    try:
        # result = subprocess.run(commands, check=True, capture_output=True, text=True) # captured output is cleaner but harder to debug
        result = subprocess.run(commands, check=True, text=True)
        print(f"Git command success: {' '.join(commands)}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Git command failed: {' '.join(commands)}\nError: {e}")
        return False
    except FileNotFoundError:
        print("Git not found. Is it installed and in PATH?")
        return False

def push_master_map_to_cloud(game_state, map_name="Global Map"):
    """Admin function: Auto-saves saved_map.json to ROOT and pushes to Git."""
    
    # 1. Force save to the specific file git expects in the root directory
    filename = "saved_map.json"
    
    print(f"Preparing to push. Saving {filename}...")
    if not _write_data_to_disk(game_state, filename):
        print("Failed to create master save file.")
        return False
    
    # 2. Add
    if not run_git_command(["git", "add", filename]): return False
    
    # 3. Commit
    message = f"Update: {map_name} - Turn {game_state.get('turn_counter', '?')}"
    # We ignore the result of commit because if nothing changed, it returns exit code 1, which is fine
    run_git_command(["git", "commit", "-m", message])
    
    # 4. Push
    if not run_git_command(["git", "push"]): 
        print("Push failed. Trying to set upstream...")
        # Fallback: Try to push setting upstream if it fails
        if run_git_command(["git", "push", "--set-upstream", "origin", "master"]):
            return True
        elif run_git_command(["git", "push", "--set-upstream", "origin", "main"]):
            return True
        return False
    
    return True

def submit_player_turn_to_cloud(game_state, nation_name, turn_number):
    """Player function: Saves specific turn file and pushes."""
    ensure_turns_directory()
    
    safe_name = "".join([c for c in nation_name if c.isalnum() or c in (' ', '_')]).strip().replace(' ', '_')
    filename = os.path.join(c.PLAYER_TURNS_DIR, f"Turn{turn_number}_{safe_name}.json")
    
    # Save the file (Encrypt if needed, here using standard logic)
    try:
        json_data = json.dumps(game_state, separators=(',', ':'))
        encrypted_data = cipher_suite.encrypt(json_data.encode('utf-8'))
        with open(filename, 'wb') as f:
            f.write(encrypted_data)
    except Exception as e:
        print(f"Error saving turn file: {e}")
        return False

    # Git Operations
    if not run_git_command(["git", "add", filename]): return False
    if not run_git_command(["git", "commit", "-m", f"Turn Submit: {nation_name}"]): return False
    if not run_git_command(["git", "push"]): return False
    
    return True

def get_player_turn_files():
    """Returns a list of available turn files."""
    ensure_turns_directory()
    run_git_command(["git", "pull"]) # Sync first to see new turns
    files = [f for f in os.listdir(c.PLAYER_TURNS_DIR) if f.endswith('.json')]
    return sorted(files)

def load_turn_file(filename):
    """Loads a specific player turn file."""
    filepath = os.path.join(c.PLAYER_TURNS_DIR, filename)
    if not os.path.exists(filepath): return None
    
    try:
        with open(filepath, 'rb') as f:
            raw_data = f.read()
        try:
            decrypted_data = cipher_suite.decrypt(raw_data)
            return json.loads(decrypted_data.decode('utf-8'))
        except:
            return json.loads(raw_data.decode('utf-8')) # Try plain json
    except Exception as e:
        print(f"Error loading turn file: {e}")
        return None

def delete_turn_file_from_cloud(filename):
    """Deletes a turn file locally and pushes the deletion."""
    filepath = os.path.join(c.PLAYER_TURNS_DIR, filename)
    
    if os.path.exists(filepath):
        os.remove(filepath)
        
    run_git_command(["git", "add", filepath]) # Add the deletion
    run_git_command(["git", "commit", "-m", f"Processed/Discarded: {filename}"])
    run_git_command(["git", "push"])
    
    
def _write_data_to_disk(game_state, filepath):
    """Internal helper to encrypt and write data."""
    try:
        json_data = json.dumps(game_state, separators=(',', ':'))
        encrypted_data = cipher_suite.encrypt(json_data.encode('utf-8'))
        with open(filepath, 'wb') as f:
            f.write(encrypted_data)
        return True
    except Exception as e:
        print(f"Error writing to disk: {e}")
        return False
    


def get_persistent_data_path(filename):
    """Gets the full path to a file in the user's persistent app data directory."""
    base_path = os.environ.get('LOCALAPPDATA', os.path.expanduser("~"))
    app_data_dir = os.path.join(base_path, "Kraje")
    
    if not os.path.exists(app_data_dir):
        os.makedirs(app_data_dir)
        
    return os.path.join(app_data_dir, filename)

def get_android_storage_path():
    if IS_ANDROID:
        return os.environ['ANDROID_PRIVATE']
    return None

def save_map_to_file(game_state):
    if IS_ANDROID:
        path = get_android_storage_path()
        if not path:
            print("Error: Could not determine Android storage path.")
            return
        filepath = os.path.join(path, "saved_map.json")
    else:
        from tkinter import filedialog
        import tkinter as tk
        if tk._default_root is None: 
            root = tk.Tk(); root.withdraw()
        
        # Allow user to pick location for PERSONAL backup
        filepath = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON Map Files", "*.json"), ("All Files", "*.*")], title="Save Map As...")

    if not filepath:
        print("Save operation cancelled.")
        return

    if _write_data_to_disk(game_state, filepath):
        print(f"Map saved successfully to {filepath}")
        
    try:
        json_data = json.dumps(game_state, separators=(',', ':'))
        encrypted_data = cipher_suite.encrypt(json_data.encode('utf-8'))
        with open(filepath, 'wb') as f:
            f.write(encrypted_data)
        print(f"Map saved successfully to {filepath}")
    except Exception as e:
        print(f"Error saving map: {e}")

def load_map_from_file():
    if IS_ANDROID:
        path = get_android_storage_path()
        if not path:
            print("Error: Could not determine Android storage path.")
            return None
        filepath = os.path.join(path, "saved_map.json")
        if not os.path.exists(filepath):
            print(f"No saved map found at {filepath}")
            return None
    else:
        from tkinter import filedialog
        import tkinter as tk
        tk.Tk().withdraw()
        filepath = filedialog.askopenfilename(filetypes=[("JSON Map Files", "*.json"), ("All Files", "*.*")], title="Load Map")

    if not filepath:
        print("Load operation cancelled.")
        return None
        
    try:
        with open(filepath, 'rb') as f: # Read in binary mode
            raw_data = f.read()

        try:
            # First, try to load as plain text (for old saves)
            data = json.loads(raw_data.decode('utf-8'))
            print("Loaded unencrypted (old) save file.")
        except (json.JSONDecodeError, UnicodeDecodeError):
            # If that fails, it's likely encrypted
            decrypted_data = cipher_suite.decrypt(raw_data)
            data = json.loads(decrypted_data.decode('utf-8'))
            print("Loaded encrypted save file.")

        print(f"Map loaded successfully from {filepath}")
        return data
    except Exception as e:
        print(f"Error loading map: {e}. File may be corrupt or not a valid save file.")
        return None

def save_encyclopedia_data(unit_types_data):
    filename = 'encyclopedia_data.json'
    filepath = filename
    if IS_ANDROID:
        path = get_android_storage_path()
        if path:
            filepath = os.path.join(path, filename)

    try:
        with open(filepath, 'w') as f:
            json.dump(unit_types_data, f, indent=4)
        print(f"Encyclopedia data saved to {filepath}")
    except Exception as e:
        print(f"Error saving encyclopedia data: {e}")

def save_tech_tree_template(tech_tree_data):
    from tkinter import filedialog
    import tkinter as tk
    tk.Tk().withdraw()
    filepath = filedialog.asksaveasfilename(
        defaultextension=".json",
        filetypes=[("Tech Tree Template", "*.json"), ("All Files", "*.*")],
        title="Save Tech Tree Template As..."
    )
    if not filepath:
        print("Save operation cancelled.")
        return
    try:
        with open(filepath, 'w') as f:
            json.dump(tech_tree_data, f, indent=4)
        print(f"Tech tree template saved successfully to {filepath}")
    except Exception as e:
        print(f"Error saving tech tree template: {e}")

def load_tech_tree_template():
    from tkinter import filedialog
    import tkinter as tk
    tk.Tk().withdraw()
    filepath = filedialog.askopenfilename(
        filetypes=[("Tech Tree Template", "*.json"), ("All Files", "*.*")],
        title="Load Tech Tree Template"
    )
    if not filepath:
        print("Load operation cancelled.")
        return None
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
        print(f"Tech tree template loaded successfully from {filepath}")
        return data
    except Exception as e:
        print(f"Error loading tech tree template: {e}")
        return None

def save_login_data(username):
    login_file_path = get_persistent_data_path(c.LOGIN_DATA_FILE)
    try:
        with open(login_file_path, 'w') as f:
            json.dump({'username': username}, f)
        print(f"Login data saved to {login_file_path}")
    except Exception as e:
        print(f"Error saving login data: {e}")

def load_login_data():
    login_file_path = get_persistent_data_path(c.LOGIN_DATA_FILE)
    if os.path.exists(login_file_path):
        try:
            with open(login_file_path, 'r') as f:
                data = json.load(f)
                return data.get('username')
        except Exception as e:
            print(f"Error loading login data: {e}")
            return None
    return None

def delete_login_data():
    login_file_path = get_persistent_data_path(c.LOGIN_DATA_FILE)
    if os.path.exists(login_file_path):
        try:
            os.remove(login_file_path)
            print(f"Login data deleted from {login_file_path}")
        except Exception as e:
            print(f"Error deleting login data: {e}")