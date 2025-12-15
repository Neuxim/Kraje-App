import os
import warnings
import math
import datetime
warnings.filterwarnings("ignore", category=DeprecationWarning, module='pkg_resources')
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"
import pygame, sys, math, random
import subprocess
import urllib.request
import json
import traceback
import tkinter as tk
from tkinter import messagebox
import config as c
from screens import LoginScreen, EncyclopediaScreen, TechTreeScreen, TitleScreen
from game_app import GameApp
from online_maps import OnlineMapsScreen
from save_load_manager import load_login_data, delete_login_data
from style_manager import StyleManager

VERSION_URL = "https://raw.githubusercontent.com/Neuxim/Kraje-App/refs/heads/main/version.json"
CURRENT_VERSION = "1.19.0"
APP_NAME = "DiploStrat.exe"

def show_crash_report(error_log):
    """
    Displays a crash report window using tkinter.
    This is self-contained and will be bundled by PyInstaller.
    """
    root = tk.Tk()
    root.withdraw()
    report_window = tk.Toplevel(root)
    report_window.title("Crash Report")
    report_window.geometry("800x600")

    def on_closing():
        root.destroy()
        sys.exit(1)
    report_window.protocol("WM_DELETE_WINDOW", on_closing)

    instructions = ("An unexpected error occurred. Please copy the text below and send it to @Neuxim on Discord.\n\n"
                  "You can press CTRL+C to copy the entire report.")
    label = tk.Label(report_window, text=instructions, justify=tk.LEFT, padx=10, pady=10)
    label.pack(side=tk.TOP, fill=tk.X)

    text_box = tk.Text(report_window, wrap="word", font=("Courier New", 10))
    text_box.insert(tk.END, error_log)
    text_box.config(state=tk.DISABLED)

    scrollbar = tk.Scrollbar(report_window, command=text_box.yview)
    text_box.config(yscrollcommand=scrollbar.set)

    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    text_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    report_window.attributes("-topmost", True)
    report_window.focus_force()
    root.mainloop()

def compare_versions(v1, v2):
    parts1 = [int(p) for p in v1.split('.')]
    parts2 = [int(p) for p in v2.split('.')]
    
    max_len = max(len(parts1), len(parts2))
    parts1.extend([0] * (max_len - len(parts1)))
    parts2.extend([0] * (max_len - len(parts2)))

    return parts1 > parts2

def check_and_apply_update():
    try:
        print("Checking for updates...")
        with urllib.request.urlopen(VERSION_URL, timeout=5) as url:
            data = json.loads(url.read().decode())
            latest_version = data['latest_version']
            download_url = data['download_url']

        if compare_versions(latest_version, CURRENT_VERSION):
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True) # Ensure the popup is on top
            
            if messagebox.askyesno(
                "Update Available",
                f"A new version ({latest_version}) is available.\nYour version is {CURRENT_VERSION}.\n\nWould you like to download and install it?"
            ):
                root.destroy()
                download_and_launch_updater(download_url)
                return True
            
            root.destroy()
    except Exception as e:
        print(f"Update check failed: {e}")
    return False

def download_and_launch_updater(url):
    temp_exe_path = f"{APP_NAME}.new"
    try:
        print(f"Downloading update from {url}...")
        urllib.request.urlretrieve(url, temp_exe_path)
        print("Download complete.")
        current_exe = os.path.basename(sys.executable)

        if not getattr(sys, 'frozen', False):
            print("Running from script, update simulation only.")
            return

        updater_script_path = "update_and_run.bat"
        with open(updater_script_path, "w") as f:
            f.write(f"@echo off\n")
            f.write(f"echo Updating to {APP_NAME}, please wait...\n")
            f.write(f"timeout /t 3 /nobreak > nul\n")
            f.write(f"del \"{current_exe}\"\n")
            f.write(f"rename \"{temp_exe_path}\" \"{APP_NAME}\"\n")
            f.write(f"echo Update complete!\n")
            f.write(f"start \"\" \"{APP_NAME}\" --updated\n")
            f.write(f"(goto) 2>nul & del \"%~f0\"\n")

        subprocess.Popen([updater_script_path], shell=True)
        print("Updater script launched. Exiting main application.")
        sys.exit(0)

    except Exception as e:
        print(f"Update process failed: {e}")
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Update Failed", f"An error occurred during the update process:\n{e}")

    except Exception as e:
        print(f"Update process failed: {e}")
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Update Failed", f"An error occurred during the update process:\n{e}")

IS_ANDROID = 'ANDROID_ARGUMENT' in os.environ

class MainApp:
    def __init__(self):
        pygame.init()
        pygame.font.init()

        # Instantiate the style manager early, so it applies the default style
        self.style_manager = StyleManager()

        if IS_ANDROID:
            info = pygame.display.Info()
            c.SCREEN_WIDTH, c.SCREEN_HEIGHT = info.current_w, info.current_h
        else:
            display_info = pygame.display.Info()
            c.SCREEN_WIDTH, c.SCREEN_HEIGHT = display_info.current_w, display_info.current_h

        self.screen = pygame.display.set_mode((c.SCREEN_WIDTH, c.SCREEN_HEIGHT))
        pygame.display.set_caption(c.APP_TITLE)
        self.clock = pygame.time.Clock()
        c.preload_assets()
        c.load_encyclopedia_data()

        self.user_mode = None
        self.username = ""
        self.player_nation_id = None
        self.running = True

        self.active_screen = None
        self.game_instance = None
        self.encyclopedia_instance = None
        self.tech_tree_instance = None
        self.online_maps_instance = None

        self.game_instance = GameApp(self)
        self.change_state('TITLE')

    def change_state(self, new_state, **kwargs):
        print(f"Changing state to: {new_state}")
        
        if self.active_screen is self.game_instance and new_state not in ['QUIT', 'LOGIN', 'ONLINE_MAPS']:
            pass
        
        if new_state == 'LOGIN':
            saved_username = load_login_data()
            if saved_username:
                is_admin = saved_username == "Nuxia14"
                is_in_player_list = self.game_instance and saved_username in self.game_instance.player_list
                
                if is_admin or is_in_player_list:
                    print(f"Auto-logging in as '{saved_username}'.")
                    self.on_login_success(saved_username)
                    return
            self.active_screen = LoginScreen(self)
        elif new_state == 'TITLE':
            self.active_screen = TitleScreen(self)
        elif new_state == 'GAME':
            if self.game_instance is None:
                self.game_instance = GameApp(self)
            self.active_screen = self.game_instance
        elif new_state == 'ENCYCLOPEDIA':
            if self.encyclopedia_instance is None:
                self.encyclopedia_instance = EncyclopediaScreen(self)
            self.active_screen = self.encyclopedia_instance
            if 'unit_key' in kwargs:
                self.encyclopedia_instance.show_detail_view(kwargs['unit_key'])
        elif new_state == 'TECH_TREE':
            # Ensure game instance exists before creating tech tree screen
            if self.game_instance is None:
                self.change_state('GAME')
                return
            # Always recreate or update the tech tree instance to ensure it gets fresh data
            self.tech_tree_instance = TechTreeScreen(self, self.game_instance)
            self.active_screen = self.tech_tree_instance
        elif new_state == 'ONLINE_MAPS':
            self.online_maps_instance = OnlineMapsScreen(self)
            self.active_screen = self.online_maps_instance
        elif new_state == 'TUTORIAL':
            if self.game_instance is None:
                self.game_instance = GameApp(self)
            self.game_instance.start_tutorial()
            self.active_screen = self.game_instance
        elif new_state == 'QUIT':
            self.running = False
            
        elif new_state == 'ENCYCLOPEDIA':
            if self.encyclopedia_instance is None:
                self.encyclopedia_instance = EncyclopediaScreen(self)
            self.active_screen = self.encyclopedia_instance
            if 'unit_key' in kwargs:
                self.encyclopedia_instance.show_detail_view(kwargs['unit_key'])

    def on_login_success(self, username):
        self.username = username
        if username == "Nuxia14":
            self.user_mode = 'editor'
            self.player_nation_id = None
            print(f"Admin user logged in. User mode: {self.user_mode}")
        elif self.game_instance and username in self.game_instance.player_list:
            self.user_mode = 'player'
            player_data = self.game_instance.player_list[username]
            self.player_nation_id = player_data.get('nation_id') if isinstance(player_data, dict) else player_data
            print(f"Player '{username}' logged in. User mode: {self.user_mode}, Nation: {self.player_nation_id}")
            self.game_instance.fow_dirty = True
        
        if self.game_instance and hasattr(self.game_instance, 'ui_manager'):
            self.game_instance.ui_manager.build_ui()

        self.change_state('GAME')
        return True

    def logout(self):
        delete_login_data()
        self.username = ""
        self.user_mode = None
        self.player_nation_id = None
        self.change_state('TITLE')

    def run(self):
        while self.running:
            self.clock.tick(60)
            
            # Centralized event loop
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                
                # Pass the event to the active screen
                if self.active_screen:
                    self.active_screen.handle_events(event)

            if not self.running:
                break

            # Drawing logic
            if self.active_screen is not self.game_instance and self.game_instance:
                self.game_instance.draw(self.screen)

            if self.active_screen:
                self.active_screen.update()
                self.active_screen.draw(self.screen)
            
            pygame.display.flip()

        pygame.quit()
        sys.exit()

if __name__ == '__main__':
    if not IS_ANDROID:
        if "--updated" in sys.argv:
            root = tk.Tk()
            root.withdraw()
            messagebox.showinfo("Update Successful", "The application has been updated successfully!")

        if check_and_apply_update():
            sys.exit(0) 

    app = MainApp()
    try:
        app.run()
    except Exception as e:
        error_info = (
            f"--- DiploStrat Crash Report ---\n"
            f"Version: {CURRENT_VERSION}\n"
            f"Error Type: {type(e).__name__}\n"
            f"Error Message: {e}\n\n"
            f"--- Traceback ---\n"
            f"{traceback.format_exc()}"
        )
        print("--- CRITICAL ERROR ---")
        print(error_info)
        print("--- Displaying crash report window. ---")
        show_crash_report(error_info)
        sys.exit(1) # Exit after displaying the report