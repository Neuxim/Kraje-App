import pygame
import requests
import json
import config as c
from ui import UIElement, Panel, Button, TextLabel, ScrollablePanel
from save_load_manager import cipher_suite

MAPS_INDEX_URL = "https://raw.githubusercontent.com/Neuxim/Kraje-App/refs/heads/main/maps_index.json"

class OnlineMapsScreen:
    def __init__(self, main_app):
        self.main_app = main_app
        self.root = UIElement(pygame.Rect(0, 0, c.SCREEN_WIDTH, c.SCREEN_HEIGHT))
        self.status_text = "Fetching map list..."
        self.maps = []

        self.panel = Panel(rect=(0,0, 600, 400), parent=self.root)
        self.panel.rect.center = (c.SCREEN_WIDTH/2, c.SCREEN_HEIGHT/2)
        
        self.font_title = c.get_font(c.FONT_PATH, 32)
        self.font_text = c.get_font(c.FONT_PATH, 16)

        TextLabel(rect=(0, 20, 600, 40), text="Online Maps", font=self.font_title, color=c.UI_FONT_COLOR, parent=self.panel, center_align=True)
        Button(rect=(self.panel.rect.width - 50, 10, 40, 40), text="X", on_click=self.close_screen, parent=self.panel)
        
        self.scroll_panel = ScrollablePanel(rect=(20, 80, 560, 300), parent=self.panel, color=(50,55,60))
        self.status_label = TextLabel(rect=(0, 10, 560, 30), text=self.status_text, font=self.font_text, color=c.UI_FONT_COLOR, center_align=True)
        
        self.fetch_maps()
        self.rebuild_map_list()

    def fetch_maps(self):
        try:
            response = requests.get(MAPS_INDEX_URL, timeout=10)
            response.raise_for_status()
            self.maps = response.json()
            self.status_text = ""
        except requests.exceptions.RequestException as e:
            self.status_text = f"Error: Could not fetch map list. {e}"
        except json.JSONDecodeError:
            self.status_text = "Error: Invalid map index file format."

    def rebuild_map_list(self):
        elements = []
        if self.status_text:
            self.status_label.set_text(self.status_text)
            elements.append({'element': self.status_label, 'height': 40})
        else:
            for map_info in self.maps:
                map_container = Panel(rect=(0, 0, self.scroll_panel.rect.width - 40, 60), color=(60,65,75))
                TextLabel(rect=(10, 10, 400, 20), text=map_info.get('name', 'Unnamed Map'), font=self.font_text, color=c.UI_FONT_COLOR, parent=map_container)
                TextLabel(rect=(10, 35, 400, 20), text=map_info.get('description', ''), font=self.font_text, color=(180,180,180), parent=map_container)
                Button(rect=(map_container.rect.width - 110, 15, 100, 30), text="Load", on_click=lambda url=map_info.get('url'): self.load_map(url), parent=map_container)
                elements.append({'element': map_container, 'height': 70})

        self.scroll_panel.rebuild_content(elements)

    def load_map(self, url):
        if not url:
            self.status_text = "Error: Map URL is missing."
            self.rebuild_map_list()
            return

        self.status_text = f"Downloading map..."
        self.rebuild_map_list()
        pygame.display.flip()

        try:
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            
            raw_data = response.content
            map_data = None

            try:
                map_data = json.loads(raw_data.decode('utf-8'))
                print("Loaded unencrypted online map.")
            except (json.JSONDecodeError, UnicodeDecodeError):
                try:
                    decrypted_data = cipher_suite.decrypt(raw_data)
                    map_data = json.loads(decrypted_data.decode('utf-8'))
                    print("Loaded and decrypted online map.")
                except Exception as decrypt_error:
                    raise ValueError(f"File is not valid JSON and failed to decrypt: {decrypt_error}")

            if map_data is None:
                raise ValueError("Could not decode map data.")

            game_instance = self.main_app.game_instance
            if game_instance:
                game_instance.load_game_state(map_data)
                self.main_app.change_state('LOGIN')
            else:
                self.status_text = "Error: Game instance not found."
                self.rebuild_map_list()

        except Exception as e:
            self.status_text = f"Failed to load map: {e}"
            self.rebuild_map_list()

    def close_screen(self):
        self.main_app.change_state('QUIT')

    def handle_events(self, event):
        if event.type == pygame.QUIT:
            self.main_app.change_state('QUIT')
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.close_screen()
        self.root.handle_event(event, self)

    def update(self):
        self.root.update()

    def draw(self, screen):
        overlay = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        screen.blit(overlay, (0, 0))
        self.root.draw(screen)
        
    def set_active_input(self, input_field): pass
    def set_tooltip(self, text, owner, pos): pass
    def clear_tooltip(self, owner=None): pass