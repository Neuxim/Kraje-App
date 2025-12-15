
import pygame
import sys
import uuid
import collections
import math
import heapq
import config as c
from map_core import Map, Tile, Camera
from entities import Unit, MapFeature, Arrow, Strait, Blockade, MapText
from ui import UIManager, MiniMap
from save_load_manager import push_master_map_to_cloud, submit_player_turn_to_cloud, get_player_turn_files, load_turn_file, delete_turn_file_from_cloud
from config import create_text_with_border, darken_color
from actions import PaintAction, EntityAction, MoveOrCarryAction, CompositeAction, ShiftMapAction, RotateUnitAction, PropertyChangeAction, RotateMapAction
from screens import EncyclopediaScreen
import random
import actions

class DeathAnimation:
    def __init__(self, surface, rect, duration=200):
        self.surface, self.rect, self.duration = surface, rect, duration
        self.start_time = pygame.time.get_ticks()

    def update(self):
        return pygame.time.get_ticks() - self.start_time < self.duration

    def draw(self, screen):
        progress = (pygame.time.get_ticks() - self.start_time) / self.duration
        scale, alpha = 1.0 - progress, 255 * (1.0 - progress)
        if self.rect.width * scale < 1 or self.rect.height * scale < 1: return
        scaled_surface = pygame.transform.smoothscale(self.surface, (int(self.rect.width * scale), int(self.rect.height * scale)))
        scaled_surface.set_alpha(alpha)
        new_rect = scaled_surface.get_rect(center=self.rect.center)
        screen.blit(scaled_surface, new_rect)

def get_excel_column(n):
    name = ""
    chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    num_chars = len(chars)
    while n >= 0:
        name = chars[n % num_chars] + name
        n = n // num_chars - 1
    return name

def rotate_grid(grid, angle):
    if angle == 0 or not grid:
        return grid
    
    rotated = [row[:] for row in grid]
    
    if angle == 90:
        rotated = list(zip(*rotated[::-1]))
    elif angle == 180:
        rotated = [row[::-1] for row in rotated[::-1]]
    elif angle == 270:
        rotated = list(zip(*rotated))[::-1]
    
    return [list(row) for row in rotated]


class GameApp:
    def __init__(self, main_app):
        self.main_app = main_app
        pygame.key.set_repeat(500, 30)
        self.panning = False
        
        self.layers = {
            'overworld': {'map': Map(100, 100), 'units': [], 'features': [], 'arrows': [], 'straits': [], 'blockades': [], 'map_texts': []},
            'underworld': {'map': Map(50, 50), 'units': [], 'features': [], 'arrows': [], 'straits': [], 'blockades': [], 'map_texts': []}
        }
        self.current_layer_key = 'overworld'
        self.nations = {}
        self.tech_tree = {}
        self.player_list = {}
        self.alliances = {}
        self.turn_counter = 1
        
        self.death_animations = []
        self.current_tool, self.active_nation_id, self.held_entity = 'select', None, None
        self.held_entity_source_container = None
        self.held_entity_start_pos = (0, 0)
        self.nations_panel_open = False
        self.multi_selected_entities = []
        self.action_range_display = None
        self.hovered_tile_for_range = None
        self.current_selection = {'unit_type': 'infantry', 'feature_type': 'city', 'arrow_order': 'Move', 'paint_land': 'Plains', 'paint_brush_size': 1, 'strait_type': 'strait'}
        self.arrow_start_pos = None
        self.strait_start_pos = None
        self.new_nation_name, self.new_nation_color = "New Nation", c.COLOR_RED
        self.show_territory_names = False
        self.paint_mode = 'land'
        self.paint_is_fill_mode = False
        
        self.minimap = MiniMap(self, pygame.Rect(c.SCREEN_WIDTH - 210, c.SCREEN_HEIGHT - 210, 200, 200))
        self.ui_manager = UIManager(self)
        self.territory_data_dirty = True
        self.cached_territory_data = {}
        self.territory_name_cache = {}
        self.manpower_data = {}
        self.manpower_dirty = True
        self.fow_dirty = True
        self.fog_of_war_enabled = True
        self.grand_total_manpower = 0
        self.move_warning_text = None
        self.fps_font = c.get_font(None, 24)
        self.coord_font = c.get_font(c.FONT_PATH, 20)
        self.feature_font = c.get_font(c.FONT_PATH, 16)
        self.last_click_time = 0
        self.hovered_entity = None
        self.hovered_leaderboard_nation_id = None
        self.show_manpower_overlay = False
        self.idle_unit_index = 0
        self.idle_units_list = []
        
        self.undo_stack = []
        self.redo_stack = []
        
        self.entity_clipboard = None
        
        self.battle_prediction = None
        self.invalid_arrow_ids = set()

        self.ai_is_thinking = False
        self.ai_pending_actions = []
        self.AI_EVENT = pygame.USEREVENT + 1
        self.selected_ai_difficulty = 'Normal'
        self.alliance_map_mode = False
        self.is_tutorial = False
        self.tutorial_step = 0
        
        
        self.preview_mode = False
        self.preview_data = None
        self.preview_filename = None
        self.master_state_backup = None

    @property
    def map(self):
        return self.layers[self.current_layer_key]['map']

    @property
    def units(self):
        return self.layers[self.current_layer_key]['units']

    @units.setter
    def units(self, value):
        self.layers[self.current_layer_key]['units'] = value

    @property
    def features(self):
        return self.layers[self.current_layer_key]['features']

    @features.setter
    def features(self, value):
        self.layers[self.current_layer_key]['features'] = value

    @property
    def arrows(self):
        return self.layers[self.current_layer_key]['arrows']

    @arrows.setter
    def arrows(self, value):
        self.layers[self.current_layer_key]['arrows'] = value
        
    @property
    def straits(self):
        return self.layers[self.current_layer_key]['straits']

    @straits.setter
    def straits(self, value):
        self.layers[self.current_layer_key]['straits'] = value

    @property
    def blockades(self):
        return self.layers[self.current_layer_key]['blockades']

    @blockades.setter
    def blockades(self, value):
        self.layers[self.current_layer_key]['blockades'] = value
        
    @property
    def map_texts(self):
        return self.layers[self.current_layer_key]['map_texts']

    @map_texts.setter
    def map_texts(self, value):
        self.layers[self.current_layer_key]['map_texts'] = value
        
        
        
    def admin_push_map(self):
        if self.ui_manager.dialog_open: return
        
        def on_confirm():
            success = push_master_map_to_cloud(self.get_game_state())
            self.ui_manager.active_popup = None
            if success:
                print("Map successfully pushed to cloud.")
            else:
                print("Failed to push map.")

        self.ui_manager.create_popup(pygame.mouse.get_pos(), [
            ("CONFIRM PUSH TO CLOUD", on_confirm),
            ("Cancel", lambda: setattr(self.ui_manager, 'active_popup', None))
        ])

    def player_submit_turn(self):
        if self.ui_manager.dialog_open: return
        
        if not self.main_app.player_nation_id:
            print("Error: You must be logged in as a nation to submit.")
            return

        nation_name = self.nations[self.main_app.player_nation_id]['name']
        
        def on_confirm():
            success = submit_player_turn_to_cloud(self.get_game_state(), nation_name, self.turn_counter)
            self.ui_manager.active_popup = None
            if success:
                print("Turn submitted successfully.")
            else:
                print("Failed to submit turn.")

        # Warning Popup
        options = [
            ("WARNING: Griefing = Ban/Skip", lambda: None), # Just text
            ("CONFIRM SUBMIT", on_confirm),
            ("Cancel", lambda: setattr(self.ui_manager, 'active_popup', None))
        ]
        self.ui_manager.create_popup((c.SCREEN_WIDTH/2 - 100, c.SCREEN_HEIGHT/2), options)

    def load_preview_turn(self, filename):
        """Loads a player turn file VISUALLY without overwriting master data permanently yet."""
        data = load_turn_file(filename)
        if not data: return

        # Backup current master state
        self.master_state_backup = self.get_game_state()
        self.preview_filename = filename
        self.preview_mode = True
        
        # Load the player data completely to see what they saw/did
        self.load_game_state(data)
        self.ui_manager.rebuild_admin_panel() # Rebuild to show Integrate/Discard buttons

    def discard_preview(self):
        """Deletes the previewed file and reverts to master."""
        if not self.preview_filename: return
        
        def on_confirm():
            delete_turn_file_from_cloud(self.preview_filename)
            self.revert_preview()
            self.ui_manager.active_popup = None

        self.ui_manager.create_popup(pygame.mouse.get_pos(), [
            ("CONFIRM DISCARD (Delete File)", on_confirm),
            ("Cancel", lambda: setattr(self.ui_manager, 'active_popup', None))
        ])

    def integrate_preview(self):
        """Merges new arrows/text from preview into master and deletes file."""
        if not self.preview_filename or not self.master_state_backup: return

        def on_confirm():
            # 1. Identify what to merge. Usually Arrows and Text.
            # We are currently IN the preview state.
            player_arrows = self.arrows
            player_texts = self.map_texts
            player_layer = self.current_layer_key # Assuming simple single layer for now or matching logic
            
            # 2. Revert to Master State first
            self.load_game_state(self.master_state_backup)
            
            # 3. Append the player's objects
            # Note: A robust system would check for duplicates (ID check)
            current_arrow_ids = {a.id for a in self.arrows}
            current_text_ids = {t.id for t in self.map_texts}
            
            count = 0
            for arrow in player_arrows:
                if arrow.id not in current_arrow_ids:
                    self.arrows.append(arrow)
                    count += 1
            
            for text in player_texts:
                if text.id not in current_text_ids:
                    self.map_texts.append(text)
            
            print(f"Integrated {count} new arrows.")
            
            # 4. Delete the file
            delete_turn_file_from_cloud(self.preview_filename)
            
            # 5. Clean up
            self.preview_mode = False
            self.preview_filename = None
            self.master_state_backup = None
            self.ui_manager.active_popup = None
            self.ui_manager.rebuild_admin_panel()

        self.ui_manager.create_popup(pygame.mouse.get_pos(), [
            ("CONFIRM INTEGRATE", on_confirm),
            ("Cancel", lambda: setattr(self.ui_manager, 'active_popup', None))
        ])

    def revert_preview(self):
        """Just closes preview without doing anything."""
        if self.master_state_backup:
            self.load_game_state(self.master_state_backup)
        self.preview_mode = False
        self.preview_filename = None
        self.master_state_backup = None
        self.ui_manager.rebuild_admin_panel()
    
    
        
    def start_tutorial(self):
        print("Starting Tutorial Mode")
        self.is_tutorial = True
        self.tutorial_step = 0
        
        # Initialize a basic map for tutorial
        self.layers['overworld']['map'] = Map(20, 15)
        self.nations = {}
        self.units = []
        self.features = []
        self.arrows = []
        
        # Create a dummy player nation
        pid = str(uuid.uuid4())
        self.nations[pid] = {'name': "Player Nation", 'color': (50, 100, 200), 'researched_techs': [], 'research_slots': 1}
        
        # Setup player
        self.main_app.username = "NewPlayer"
        self.main_app.user_mode = 'player'
        self.main_app.player_list = {"NewPlayer": {'nation_id': pid, 'nickname': "Recruit"}}
        self.main_app.player_nation_id = pid
        
        # Add a unit and feature for context
        self.do_action(EntityAction(MapFeature('city', 5, 5), is_creation=True))
        tile = self.map.get_tile(5, 5)
        tile.nation_owner_id = pid
        self.do_action(EntityAction(Unit('infantry', 6, 5, pid), is_creation=True))
        
        self.ui_manager.build_ui()
        self.map.camera.center_on(5 * c.TILE_SIZE, 5 * c.TILE_SIZE)
        self.fow_dirty = True

    def switch_layer(self):
        self.clear_selection()
        self.current_layer_key = 'underworld' if self.current_layer_key == 'overworld' else 'overworld'
        self.minimap.set_dirty()
        self.fow_dirty = True
        
        if hasattr(self.ui_manager, 'width_input'):
            self.ui_manager.width_input.set_text(str(self.map.width))
            self.ui_manager.height_input.set_text(str(self.map.height))
        print(f"Switched to {self.current_layer_key}")

    def do_action(self, action):
        action.execute(self)
        self.undo_stack.append(action)
        self.redo_stack.clear()
        self.minimap.set_dirty()
        self.manpower_dirty = True
        self.fow_dirty = True
        self.update_arrow_validity()

    def undo_action(self):
        if not self.undo_stack: return
        action = self.undo_stack.pop()
        action.undo(self)
        self.redo_stack.append(action)
        self.minimap.set_dirty()
        self.manpower_dirty = True
        self.fow_dirty = True
        self.update_arrow_validity()

    def redo_action(self):
        if not self.redo_stack: return
        action = self.redo_stack.pop()
        action.execute(self)
        self.undo_stack.append(action)
        self.minimap.set_dirty()
        self.manpower_dirty = True
        self.fow_dirty = True
        self.update_arrow_validity()
        

    def update_arrow_validity(self):
        self.invalid_arrow_ids.clear()
        nation_arrows = collections.defaultdict(list)
        for arrow in self.arrows:
            if arrow.nation_id:
                nation_arrows[arrow.nation_id].append(arrow)

        units_at_pos = {(u.grid_x, u.grid_y): u for u in self.units}
        
        suppressed_unit_ids = set()
        targeted_units = collections.defaultdict(list)
        for arrow in self.arrows:
            if arrow.order_type in ['Attack', 'Suppressive Fire']:
                defender = self.find_entity_at(arrow.end_gx, arrow.end_gy, None, ignore_arrows=True)
                if isinstance(defender, Unit):
                    attacker = self.find_entity_at(arrow.start_gx, arrow.start_gy, None, ignore_arrows=True)
                    if isinstance(attacker, Unit):
                        targeted_units[defender.id].append(attacker)
        
        for defender_id, attackers in targeted_units.items():
            defender = next((u for u in self.units if u.id == defender_id), None)
            if not defender: continue

            attack_power, _ = self.get_suppressive_fire_power(attackers)
            defense_power, _ = self.get_defense_power(defender)

            if attack_power >= defense_power:
                suppressed_unit_ids.add(defender_id)

        for nation_id, arrows in nation_arrows.items():
            starts = { (a.start_gx, a.start_gy): a for a in arrows }
            ends = { (a.end_gx, a.end_gy) for a in arrows }
            
            chain_heads = [a for s, a in starts.items() if s not in ends]
            
            for head_arrow in chain_heads:
                unit = units_at_pos.get((head_arrow.start_gx, head_arrow.start_gy))
                
                if unit and unit.nation_id == nation_id:
                    if unit.id in suppressed_unit_ids and any(a.order_type == 'Move' for a in self.get_arrow_chain_for_unit(unit)):
                        for arrow in self.get_arrow_chain_for_unit(unit):
                            if arrow.order_type == 'Move':
                                self.invalid_arrow_ids.add(arrow.id)
                        continue
                    
                    full_chain = self.get_arrow_chain_for_unit(unit)
                    try:
                        stats, _ = unit.get_effective_stats(self)
                        max_spe = int(stats.get('spe', 0))
                        cost = self.calculate_chain_cost(unit, full_chain)
                        
                        if cost > max_spe:
                            for arrow in full_chain:
                                self.invalid_arrow_ids.add(arrow.id)
                    except (ValueError, TypeError):
                        continue

    def set_tool(self, tool_name):
        user_mode = self.main_app.user_mode
        if user_mode == 'player' and tool_name not in ['select', 'add_arrow', 'add_text']:
            return
            
        if tool_name == 'paint_land':
            self.paint_mode = 'land'
        elif tool_name == 'paint_nation':
            self.paint_mode = 'nation'

        self.current_tool = 'select' if self.current_tool == tool_name else tool_name
        self.ui_manager.rebuild_active_tool_panel()
        self.arrow_start_pos = None

    def set_sub_tool(self, key, value):
        self.current_selection[key] = value
        if self.current_tool == 'paint_canal':
            self.current_selection['paint_land'] = 'Canal'
        self.ui_manager.rebuild_active_tool_panel()

    def toggle_nations_panel(self):
        self.nations_panel_open = not self.nations_panel_open
        if self.nations_panel_open: self.ui_manager.rebuild_nation_panel_content()
    
    def toggle_special_nation(self, nation_id):
        if nation_id in self.nations:
            self.nations[nation_id]['is_special'] = not self.nations[nation_id].get('is_special', False)
            self.manpower_dirty = True
            self.ui_manager.rebuild_nation_panel_content()

    def set_active_nation(self, nid): 
        if self.active_nation_id != nid:
            self.active_nation_id = nid
        else:
            self.active_nation_id = None
        self.ui_manager.rebuild_nation_panel_content()
        self.ui_manager.rebuild_selection_info_panel()


    def deselect_nation(self):
        if self.active_nation_id is not None:
            self.active_nation_id = None
            self.ui_manager.rebuild_nation_panel_content()
            self.ui_manager.rebuild_selection_info_panel()

    def set_new_nation_color(self, color): self.new_nation_color = color
    
    def set_new_nation_name(self, name):
        self.new_nation_name = name

    def update_nation_name(self, name):
        if self.active_nation_id and self.active_nation_id in self.nations:
            self.nations[self.active_nation_id]['name'] = name; self.territory_data_dirty = True; self.manpower_dirty = True

    def update_nation_color(self, color):
        if self.active_nation_id and self.active_nation_id in self.nations:
            self.nations[self.active_nation_id]['color'] = color
            self.territory_data_dirty = True
            self.manpower_dirty = True
            self.map.set_dirty()
    
    def delete_active_nation(self):
        if not self.active_nation_id: return
        nation_id = self.active_nation_id

        for layer in self.layers.values():
            all_nation_units = []
            units_to_check = [u for u in layer['units'] if u.nation_id == nation_id]
            while units_to_check:
                unit = units_to_check.pop()
                all_nation_units.append(unit)
                if hasattr(unit, 'carried_units'):
                    units_to_check.extend(u for u in unit.carried_units if u.nation_id == nation_id)

            for unit in all_nation_units:
                if unit in layer['units']:
                    layer['units'].remove(unit)
                for u_transport in layer['units']:
                    if hasattr(u_transport, 'carried_units') and unit in u_transport.carried_units:
                        u_transport.carried_units.remove(unit)

            for row in layer['map'].grid:
                for tile in row:
                    if tile.nation_owner_id == nation_id: tile.nation_owner_id = None
            
            layer['arrows'] = [a for a in layer['arrows'] if a.nation_id != nation_id]

        if nation_id in self.nations: del self.nations[nation_id]
        
        for user, nid in list(self.player_list.items()):
            if nid == nation_id:
                del self.player_list[user]
        
        empty_alliances = []
        for alliance, members in self.alliances.items():
            if nation_id in members:
                members.remove(nation_id)
            if not members:
                empty_alliances.append(alliance)
        for alliance in empty_alliances:
            del self.alliances[alliance]

        self.active_nation_id = None
        self.territory_data_dirty = True
        self.manpower_dirty = True
        self.ui_manager.rebuild_nation_panel_content()
    
    def add_nation(self):
        name = self.new_nation_name.strip()
        if not name or name == "New Nation" or name in [n['name'] for n in self.nations.values()]: return
        nid = str(uuid.uuid4())
        self.nations[nid] = {
            'name': name,
            'color': self.new_nation_color,
            'is_special': False,
            'researched_techs': [],
            'currently_researching': {},
            'research_slots': 1
        }
        self.active_nation_id, self.new_nation_name = nid, "New Nation"
        self.territory_data_dirty = True; self.manpower_dirty = True
        self.ui_manager.rebuild_nation_panel_content()

    def get_game_state(self, compact=True):
        layered_data = {}
        for key, layer_data in self.layers.items():
            layered_data[key] = {
                'map_data': layer_data['map'].to_dict(compact=compact),
                'units': [u.to_dict(compact=compact) for u in layer_data['units']],
                'features': [mf.to_dict(compact=compact) for mf in layer_data['features']],
                'arrows': [a.to_dict(compact=compact) for a in layer_data['arrows']],
                'straits': [s.to_dict(compact=compact) for s in layer_data.get('straits', [])],
                'blockades': [b.to_dict(compact=compact) for b in layer_data.get('blockades', [])],
                'map_texts': [t.to_dict(compact=compact) for t in layer_data.get('map_texts', [])]
            }
        
        return {
            'version': 9,
            'layers': layered_data,
            'nations': self.nations,
            'tech_tree': self.tech_tree,
            'player_list': self.player_list,
            'alliances': self.alliances,
            'turn_counter': self.turn_counter,
            'show_territory_names': self.show_territory_names,
            'fog_enabled': self.fog_of_war_enabled,
            'style_manager': self.main_app.style_manager.to_dict()
        }

    # In file: game_app.py

    def load_game_state(self, raw_data):
        if not raw_data: return
            
        self.clear_selection()
        self.active_nation_id = None

        if 'style_manager' in raw_data:
            self.main_app.style_manager.from_dict(raw_data['style_manager'], self)
        
        if 'layers' in raw_data:
            for key, layer_data in raw_data['layers'].items():
                if key not in self.layers:
                    self.layers[key] = {}
                
                self.layers[key]['map'] = Map.from_dict(layer_data.get('map_data', {}))
                self.layers[key]['units'] = [Unit.from_dict(u) for u in layer_data.get('units', [])]
                
                loaded_features = [MapFeature.from_dict(mf) for mf in layer_data.get('features', [])]
                
                valid_features = []
                current_map = self.layers[key]['map']
                for feature in loaded_features:
                    is_naval_feature = feature.properties.get('is_naval', False)
                    tile = current_map.get_tile(feature.grid_x, feature.grid_y)
                    if tile:
                        is_water_tile = tile.land_type in c.NAVAL_TERRAIN
                        if (is_naval_feature and is_water_tile) or (not is_naval_feature and not is_water_tile):
                            valid_features.append(feature)
                self.layers[key]['features'] = valid_features

                self.layers[key]['arrows'] = [Arrow.from_dict(a) for a in layer_data.get('arrows', [])]
                self.layers[key]['straits'] = [Strait.from_dict(s) for s in layer_data.get('straits', [])]
                self.layers[key]['blockades'] = [Strait.from_dict(b) for b in layer_data.get('blockades', [])]
                self.layers[key]['map_texts'] = [MapText.from_dict(t) for t in layer_data.get('map_texts', [])]

        else:
            self.current_layer_key = 'overworld'
            self.layers['overworld']['map'] = Map.from_dict(raw_data['map_data'])
            self.layers['overworld']['units'] = [Unit.from_dict(u) for u in raw_data.get('units', [])]
            self.layers['overworld']['features'] = [MapFeature.from_dict(mf) for mf in raw_data.get('features', [])]
            self.layers['overworld']['arrows'] = [Arrow.from_dict(a) for a in raw_data.get('arrows', [])]
            self.layers['overworld']['straits'] = []
            self.layers['overworld']['blockades'] = []
            self.layers['overworld']['map_texts'] = []
            self.layers['underworld'] = {'map': Map(50, 50), 'units': [], 'features': [], 'arrows': [], 'straits': [], 'blockades': [], 'map_texts': []}

        self.nations = raw_data.get('nations', {})
        self.tech_tree = raw_data.get('tech_tree', {})
        self.player_list = raw_data.get('player_list', {})
        self.alliances = raw_data.get('alliances', {})
        if 'turn_counter' in raw_data:
            self.turn_counter = raw_data.get('turn_counter', 1)
        else: # Legacy support
            self.turn_counter = raw_data.get('current_turn_index', 0) + 1
        
        for username, data in self.player_list.items():
            if isinstance(data, str): 
                self.player_list[username] = {'nation_id': data, 'nickname': username}

        for tech_id, tech_data in self.tech_tree.items():
            if 'prerequisites' in tech_data and isinstance(tech_data['prerequisites'], list):
                tech_data['prerequisites'] = {'and': tech_data['prerequisites'],'or': [],'xor': []}
            elif 'prerequisites' not in tech_data:
                 tech_data['prerequisites'] = {'and': [], 'or': [], 'xor': []}
            if 'bonuses' not in tech_data or not isinstance(tech_data['bonuses'], dict):
                 tech_data['bonuses'] = {'description': str(tech_data.get('bonuses', '...')), 'modifiers': {}}
            if 'modifiers' in tech_data.get('bonuses', {}) and isinstance(tech_data['bonuses']['modifiers'], list):
                tech_data['bonuses']['modifiers'] = {}

        for nid, nation_data in self.nations.items():
            if 'color' in nation_data and isinstance(nation_data['color'], list):
                nation_data['color'] = tuple(nation_data['color'])
            nation_data.setdefault('researched_techs', [])
            nation_data.setdefault('currently_researching', {})
            nation_data.setdefault('research_slots', 1)

            if 'current_research' in nation_data and nation_data['current_research']:
                tech_id = nation_data['current_research']
                progress = nation_data.get('research_progress', 0)
                if tech_id not in nation_data['currently_researching']:
                    nation_data['currently_researching'][tech_id] = {'progress': progress}
            
            if 'current_research' in nation_data: del nation_data['current_research']
            if 'research_progress' in nation_data: del nation_data['research_progress']
        
        self.show_territory_names = raw_data.get('show_territory_names', False)
        self.fog_of_war_enabled = raw_data.get('fog_enabled', True)
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.ui_manager.build_ui()
        self.territory_data_dirty = True
        self.cached_territory_data.clear()
        self.territory_name_cache.clear()
        self.minimap.set_dirty()
        self.manpower_dirty = True
        self.fow_dirty = True
    
    def update_player_nickname(self, login_name, new_nickname):
        if login_name in self.player_list and isinstance(self.player_list[login_name], dict):
            self.player_list[login_name]['nickname'] = new_nickname
            print(f"Updated nickname for '{login_name}' to '{new_nickname}'")
            
    def save_map(self):
        if self.ui_manager.dialog_open: return
        self.ui_manager.dialog_open = True
        save_map_to_file(self.get_game_state())
        self.ui_manager.dialog_open = False

    def load_map(self):
        if self.ui_manager.dialog_open: return
        self.ui_manager.dialog_open = True
        loaded_data = load_map_from_file()
        if loaded_data:
            self.load_game_state(loaded_data)
            self.main_app.username = ""
            self.main_app.user_mode = None
            self.main_app.player_nation_id = None
            self.main_app.change_state('LOGIN')
        self.ui_manager.dialog_open = False

    def export_map_to_image(self):
        if self.ui_manager.dialog_open: return
        self.ui_manager.dialog_open = True
        
        from tkinter import filedialog, Tk
        root = Tk(); root.withdraw()
        filepath = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG Image", "*.png")], title="Export Map to Image...")
        
        if not filepath:
            self.ui_manager.dialog_open = False
            return
            
        w, h = self.map.width * c.TILE_SIZE, self.map.height * c.TILE_SIZE
        export_surface = pygame.Surface((w,h))
        
        export_cam = Camera()
        
        self.map.draw(export_surface, self.nations, "editor", self.features, is_export=True) 
        
        for feature in self.features:
            owner_tile = self.map.get_tile(feature.grid_x, feature.grid_y)
            owner_color = self.nations.get(owner_tile.nation_owner_id, {}).get('color') if owner_tile else None
            feature.draw(export_surface, export_cam, owner_color, self.feature_font)
        
        for unit in self.units:
            nation_color = self.nations.get(unit.nation_id,{}).get('color')
            unit.draw(export_surface, export_cam, nation_color)
        
        for text_obj in self.map_texts:
            text_obj.draw(export_surface, export_cam)

        try:
            pygame.image.save(export_surface, filepath)
        except pygame.error as e:
            print(f"Error saving image: {e}")
            
        self.ui_manager.dialog_open = False

    def clear_arrows(self):
        if not self.arrows: return
        actions = []
        if self.main_app.user_mode == 'player':
            player_nation = self.main_app.player_nation_id
            arrows_to_delete = [arrow for arrow in self.arrows if arrow.nation_id == player_nation]
            if arrows_to_delete:
                actions = [EntityAction(arrow, is_creation=False) for arrow in arrows_to_delete]
        else:
            actions = [EntityAction(arrow, is_creation=False) for arrow in list(self.arrows)]

        if actions:
            self.do_action(CompositeAction(actions))

    def clear_selection(self): 
        self.multi_selected_entities.clear()
        self.action_range_display = None
        self.hovered_tile_for_range = None
        if hasattr(self, 'ui_manager'):
            self.ui_manager.rebuild_selection_info_panel()

    def is_multi_selecting(self): return len(self.multi_selected_entities) > 0
    
    def get_selection_color(self, entity):
        if entity in self.multi_selected_entities:
            return c.UI_MULTI_SELECT_COLOR if len(self.multi_selected_entities) > 1 else c.COLOR_YELLOW
        return None

    def delete_multi_selected(self):
        actions = []
        user_mode = self.main_app.user_mode
        player_nation = self.main_app.player_nation_id

        for entity in list(self.multi_selected_entities):
            can_delete = False
            if user_mode == 'editor':
                can_delete = True
            elif isinstance(entity, Arrow):
                if user_mode == 'player' and entity.nation_id == player_nation:
                    can_delete = True
            elif isinstance(entity, MapText):
                if user_mode == 'player' and entity.author_username == self.main_app.username:
                    can_delete = True
            
            if not can_delete: continue

            if hasattr(entity, 'asset_path') and hasattr(entity, 'grid_x'):
                rect = pygame.Rect(0,0, c.TILE_SIZE*self.map.camera.zoom, c.TILE_SIZE*self.map.camera.zoom)
                wx, wy = self.map.camera.grid_to_world(entity.grid_x, entity.grid_y)
                rect.center = self.map.camera.world_to_screen(wx + c.TILE_SIZE/2, wy + c.TILE_SIZE/2)
                self.death_animations.append(DeathAnimation(c.get_asset(entity.asset_path), rect))
            
            actions.append(EntityAction(entity, is_creation=False))

        if actions:
            self.do_action(CompositeAction(actions))
            self.clear_selection()

    def find_entity_at(self, gx, gy, world_pos, ignore_arrows=False, ignore_units=False, ignore_text=False):
        tile = self.map.get_tile(gx, gy)
        if tile and tile.visibility_state == 2 and self.main_app.user_mode != 'editor':
            return None

        if not ignore_arrows and world_pos:
            for arrow in reversed(self.arrows):
                if arrow.is_clicked(world_pos): return arrow
        if not ignore_text:
            for text_obj in reversed(self.map_texts):
                if text_obj.grid_x == gx and text_obj.grid_y == gy: return text_obj
        
        if not ignore_units:
            for unit in reversed(self.units):
                if unit.unit_class == 'air' and unit.grid_x == gx and unit.grid_y == gy:
                    return unit
            for unit in reversed(self.units):
                if unit.unit_class != 'air' and unit.grid_x == gx and unit.grid_y == gy:
                    return unit

        for feature in reversed(self.features):
            if feature.grid_x == gx and feature.grid_y == gy: return feature
        return None

    def start_unloading_unit(self, transport_unit, unit_to_unload):
        user_mode = self.main_app.user_mode
        player_nation_id = self.main_app.player_nation_id
        
        can_interact = False
        if user_mode == 'editor':
            can_interact = True
        elif user_mode == 'player' and transport_unit.nation_id == player_nation_id:
            can_interact = True
            
        if self.held_entity or not can_interact:
            return
            
        if user_mode == 'editor':
            self.held_entity = unit_to_unload
            self.held_entity_source_container = transport_unit
            self.held_entity_start_pos = (transport_unit.grid_x, transport_unit.grid_y)
        else:
            self.clear_selection()
            self.multi_selected_entities.append(unit_to_unload)
            self.action_range_display, _ = self.calculate_reachable_tiles(unit_to_unload)

        self.ui_manager.rebuild_selection_info_panel()

    def handle_map_interaction(self, event):
        mouse_pos = pygame.mouse.get_pos()
        if self.ui_manager.is_mouse_over_ui(mouse_pos):
            if event.type == pygame.MOUSEBUTTONUP and self.held_entity:
                action = MoveOrCarryAction(self.held_entity, self.held_entity_start_pos, self.held_entity_start_pos, self.held_entity_source_container, self.held_entity_source_container)
                action.execute(self)
                self.held_entity = None; self.held_entity_source_container = None
            return

        world_pos = self.map.camera.screen_to_world(*mouse_pos)
        gx, gy = self.map.camera.world_to_grid(*world_pos)
        
        if event.type == pygame.MOUSEMOTION:
            # ... [Existing hover logic] ...
            self.hovered_entity = self.find_entity_at(gx, gy, world_pos)
            if self.action_range_display and (gx, gy) in self.action_range_display:
                self.hovered_tile_for_range = (gx, gy)
            else:
                self.hovered_tile_for_range = None

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            # ... [Existing Left Click Logic] ...
            if self.ui_manager.active_popup:
                self.ui_manager.root.children.remove(self.ui_manager.active_popup)
                self.ui_manager.active_popup = None
                return

            if len(self.multi_selected_entities) == 1:
                entity = self.multi_selected_entities[0]
                if hasattr(entity, 'delete_button_rect') and entity.delete_button_rect and entity.delete_button_rect.collidepoint(mouse_pos):
                    self.delete_multi_selected()
                    return

            if self.current_tool != 'select': self.perform_tool_action(gx, gy, event=event); return
            
            # ... [Rest of selection logic] ...
            entity = self.find_entity_at(gx, gy, world_pos)
            if entity and isinstance(entity, Unit) and entity in self.multi_selected_entities and pygame.time.get_ticks() - self.last_click_time < 300:
                self.main_app.change_state('ENCYCLOPEDIA', unit_key=entity.unit_type); return
            self.last_click_time = pygame.time.get_ticks()
            
            if pygame.key.get_mods() & pygame.KMOD_SHIFT:
                if entity and entity not in self.multi_selected_entities: self.multi_selected_entities.append(entity)
            else:
                self.clear_selection()
                if entity: self.multi_selected_entities.append(entity)
            
            if len(self.multi_selected_entities) == 1 and isinstance(self.multi_selected_entities[0], Unit):
                unit = self.multi_selected_entities[0]
                self.action_range_display, _ = self.calculate_reachable_tiles(unit)
            else:
                self.action_range_display = None
            
            self.ui_manager.rebuild_selection_info_panel()

            if len(self.multi_selected_entities) == 1 and isinstance(self.multi_selected_entities[0], (Unit, MapText)):
                entity_to_hold = self.multi_selected_entities[0]
                user_mode = self.main_app.user_mode
                can_hold = (user_mode == 'editor')
                if can_hold:
                    self.held_entity = entity_to_hold
                    self.held_entity_source_container = None
                    self.held_entity_start_pos = (self.held_entity.grid_x, self.held_entity.grid_y)
        
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
            # FIX: If using a tool that utilizes right-click (like Paint Fog), do NOT cancel.
            if self.current_tool == 'paint_fog':
                self.perform_tool_action(gx, gy, event=event)
                return

            # --- Cancellation Logic ---
            cancelled = False
            if self.held_entity:
                if isinstance(self.held_entity, Unit):
                    action = MoveOrCarryAction(self.held_entity, self.held_entity_start_pos, self.held_entity_start_pos, self.held_entity_source_container, self.held_entity_source_container)
                    action.execute(self)
                self.held_entity = None; self.held_entity_source_container = None
                cancelled = True
            
            if self.current_tool != 'select':
                self.set_tool('select')
                self.arrow_start_pos = None; self.strait_start_pos = None
                cancelled = True
            
            if not cancelled and self.multi_selected_entities:
                self.clear_selection()
                cancelled = True
            
            if cancelled:
                self.ui_manager.rebuild_active_tool_panel()
                self.ui_manager.rebuild_selection_info_panel()
                return

            self.handle_right_click(gx, gy, mouse_pos)

        # ... [Rest of mouse motion logic] ...
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self.held_entity:
             # ... [Existing drop logic] ...
             if isinstance(self.held_entity, Unit):
                target_entity = self.find_entity_at(gx, gy, world_pos, ignore_arrows=True)
                if isinstance(target_entity, Unit) and target_entity != self.held_entity and target_entity.can_carry(self.held_entity):
                    self.do_action(MoveOrCarryAction(self.held_entity, self.held_entity_start_pos, (gx,gy), self.held_entity_source_container, target_entity))
                    self.clear_selection(); self.multi_selected_entities.append(target_entity)
                else:
                    tile = self.map.get_tile(gx, gy)
                    if tile:
                        actions = []
                        actions.append(MoveOrCarryAction(self.held_entity, self.held_entity_start_pos, (gx,gy), self.held_entity_source_container, None))
                        if self.held_entity_source_container:
                            transport = self.held_entity_source_container
                            actions.append(EntityAction(Arrow(transport.grid_x, transport.grid_y, gx, gy, 'Load/Unload', transport.nation_id, transport.id), is_creation=True))
                        self.do_action(CompositeAction(actions))
                        self.action_range_display, _ = self.calculate_reachable_tiles(self.held_entity)
                    else:
                        action = MoveOrCarryAction(self.held_entity, self.held_entity_start_pos, self.held_entity_start_pos, self.held_entity_source_container, self.held_entity_source_container)
                        action.execute(self)
            
             elif isinstance(self.held_entity, MapText):
                self.do_action(MoveOrCarryAction(self.held_entity, self.held_entity_start_pos, (gx, gy), None, None))

             self.held_entity = None; self.held_entity_source_container = None
             self.ui_manager.rebuild_selection_info_panel()

        if event.type == pygame.MOUSEMOTION and (event.buttons[0] or event.buttons[2]) and self.current_tool != 'select':
            self.perform_tool_action(gx, gy, is_drag=True)

    def handle_unload_order(self, transporter, dest_gx, dest_gy):
        if not transporter or not transporter.carried_units:
            print("Unload failed: No transporter or no units to unload.")
            return

        reachable_tiles, cost_so_far = self.calculate_reachable_tiles(transporter)
        
        chain = self.get_arrow_chain_for_unit(transporter)
        start_pos = (transporter.grid_x, transporter.grid_y)
        if chain:
            start_pos = (chain[-1].end_gx, chain[-1].end_gy)
        
        reachable_tiles.add(start_pos)
        cost_so_far[start_pos] = 0

        best_spot = None
        min_cost = float('inf')

        for tile_pos in reachable_tiles:
            if abs(tile_pos[0] - dest_gx) <= 1 and abs(tile_pos[1] - dest_gy) <= 1:
                cost = cost_so_far.get(tile_pos, float('inf'))
                if cost < min_cost:
                    min_cost = cost
                    best_spot = tile_pos

        if best_spot:
            actions = []
            is_shift_held = pygame.key.get_mods() & pygame.KMOD_SHIFT
            if not is_shift_held:
                actions.extend([EntityAction(arrow, is_creation=False) for arrow in chain])

            if best_spot != start_pos:
                actions.append(EntityAction(Arrow(start_pos[0], start_pos[1], best_spot[0], best_spot[1], 'Move', transporter.nation_id, transporter.id), is_creation=True))
            
            actions.append(EntityAction(Arrow(best_spot[0], best_spot[1], dest_gx, dest_gy, 'Load/Unload', transporter.nation_id, transporter.id), is_creation=True))
            
            if actions:
                self.do_action(CompositeAction(actions))
        else:
            print("Unload failed: Destination is not reachable.")


    def handle_right_click(self, gx, gy, mouse_pos):
        if self.main_app.user_mode not in ['player', 'editor']:
            return

        if self.current_tool == 'add_strait' and self.main_app.user_mode == 'editor':
            world_pos = self.map.camera.screen_to_world(*mouse_pos)
            for link in reversed(self.straits + self.blockades):
                if link.is_clicked(world_pos):
                    self.do_action(EntityAction(link, is_creation=False))
                    return

        if len(self.multi_selected_entities) != 1 or not isinstance(self.multi_selected_entities[0], Unit):
            if self.held_entity:
                action = MoveOrCarryAction(self.held_entity, self.held_entity_start_pos, self.held_entity_start_pos, self.held_entity_source_container, self.held_entity_source_container)
                action.execute(self)
                self.held_entity = None
                self.held_entity_source_container = None
            self.clear_selection()
            return

        unit = self.multi_selected_entities[0]
        
        if self.main_app.user_mode == 'player' and unit.nation_id != self.main_app.player_nation_id:
            return
            
        target_entity = self.find_entity_at(gx, gy, None, ignore_arrows=True)
        is_shift_held = pygame.key.get_mods() & pygame.KMOD_SHIFT

        def create_arrow_action(order_type, start_pos=None, end_pos=(gx, gy)):
            chain = self.get_arrow_chain_for_unit(unit)
            
            last_pos = (unit.grid_x, unit.grid_y)
            if chain and is_shift_held:
                last_pos = (chain[-1].end_gx, chain[-1].end_gy)

            if start_pos is None: start_pos = last_pos

            try:
                stats, _ = unit.get_effective_stats(self)
                max_spe = int(stats.get('spe', 0))
                current_cost = self.calculate_chain_cost(unit, chain)
                
                additional_cost = 0
                if order_type == 'Move':
                    path = self._find_shortest_path(unit, start_pos, end_pos)
                    if not path: return
                    additional_cost = len(path) - 1 if path else float('inf')
                elif order_type == 'Load/Unload':
                    additional_cost = c.LOAD_COSTS.get(unit.unit_type, 1.0)

                if current_cost + additional_cost > max_spe:
                    print("Move exceeds unit's speed.")
                    return
            except (ValueError, TypeError):
                print("Error calculating move cost due to invalid unit stats.")
                return

            actions = []
            if not is_shift_held:
                actions.extend([EntityAction(arrow, is_creation=False) for arrow in chain])
            
            actions.append(EntityAction(Arrow(start_pos[0], start_pos[1], end_pos[0], end_pos[1], order_type, unit.nation_id, unit.id), is_creation=True))
            if actions: self.do_action(CompositeAction(actions))

        if target_entity is None or isinstance(target_entity, (MapFeature, MapText)):
            if unit.weight_capacity and unit.carried_units:
                options = [("Move Transporter", lambda: create_arrow_action('Move'))]
                
                can_unload = False
                tile = self.map.get_tile(gx, gy)
                if tile:
                    for carried_unit in unit.carried_units:
                        if carried_unit.unit_class == 'land' and tile.land_type not in c.NAVAL_TERRAIN:
                            can_unload = True
                            break
                        if carried_unit.unit_class == 'naval' and tile.land_type in c.NAVAL_TERRAIN:
                            can_unload = True
                            break
                
                if can_unload:
                    options.append(("Unload Here", lambda: self.handle_unload_order(unit, gx, gy)))
                
                if len(options) > 1:
                    self.ui_manager.create_popup(mouse_pos, options)
                elif options:
                    options[0][1]()

            elif self.action_range_display and (gx, gy) in self.action_range_display:
                create_arrow_action('Move')
        
        elif isinstance(target_entity, Unit) and target_entity is not unit:
            allies = self.get_allied_nations(unit.nation_id)
            if target_entity.nation_id in allies:
                options = []
                try: 
                    stats, _ = unit.get_effective_stats(self)
                    sup_stat_str = stats.get('sup', '0')
                    sup_stat = int(str(sup_stat_str).split('x')[0])
                except (ValueError, TypeError): sup_stat = 0

                if sup_stat > 0:
                    options.extend([
                        ("Support Attack", lambda: self.handle_support_order(unit, target_entity, 'Support Attack')),
                        ("Support Defense", lambda: self.handle_support_order(unit, target_entity, 'Support Defense'))
                    ])
                if target_entity.can_carry(unit):
                    options.append(("Load", lambda: create_arrow_action('Load/Unload', end_pos=(target_entity.grid_x, target_entity.grid_y))))

                if options: self.ui_manager.create_popup(mouse_pos, options)

            else:
                reachable_tiles, _ = self.calculate_reachable_tiles(unit)
                reachable_tiles.add((unit.grid_x, unit.grid_y))

                can_attack = any(self.is_valid_action_target(unit, gx, gy, 'Attack', from_pos=pos) for pos in reachable_tiles)
                can_support = any(self.is_valid_action_target(unit, gx, gy, 'Support Attack', from_pos=pos) for pos in reachable_tiles)
                
                options = []
                try: 
                    stats, _ = unit.get_effective_stats(self)
                    str_stat = int(stats.get('str', 0))
                    sup_stat = int(str(stats.get('sup', '0')).split('x')[0])
                    spe_stat = int(stats.get('spe', 0))
                except (ValueError, TypeError): 
                    str_stat = 0
                    sup_stat = 0
                    spe_stat = 0

                is_already_attacked = self.is_target_already_attacked(target_entity, unit.nation_id)

                if can_attack and str_stat > 0 and not is_already_attacked and spe_stat > 0:
                    options.append(("Attack", lambda: self.handle_support_order(unit, target_entity, 'Attack')))
                if can_support and sup_stat > 0:
                    if is_already_attacked:
                        options.append(("Support Attack", lambda: self.handle_support_order(unit, target_entity, 'Support Attack')))
                    options.append(("Suppressive Fire", lambda: self.handle_support_order(unit, target_entity, 'Suppressive Fire')))

                if options:
                    self.ui_manager.create_popup(mouse_pos, options)
                    
                    
    def toggle_alliance_map_mode(self):
        self.alliance_map_mode = not self.alliance_map_mode
        self.map.set_dirty()
        self.minimap.set_dirty()


    def draw(self, screen):
        screen.fill(c.UI_BACKGROUND_COLOR)
        
        # 1. Map Tiles (Base Terrain, Borders, Blending)
        self.map.draw(screen, self.nations, self.main_app.user_mode, self.features, alliance_mode=self.alliance_map_mode, alliances=self.alliances)
        
        # Coastline animation removed
        
        # 2. Features (Cities, Oil Rigs, etc.)
        for feature in self.features:
            tile = self.map.get_tile(feature.grid_x, feature.grid_y)
            if tile and tile.visibility_state != 0 and self.main_app.user_mode != 'editor': continue

            owner_tile = self.map.get_tile(feature.grid_x, feature.grid_y)
            owner_color = self.nations.get(owner_tile.nation_owner_id, {}).get('color') if owner_tile else None
            feature.draw(screen, self.map.camera, owner_color, self.feature_font, self.get_selection_color(feature))

        # 3. Action Range Overlay
        self.draw_action_range(screen)

        self.idle_units_list = self.get_idle_units()
        
        # 4. Land/Naval Units (Layer 1)
        for unit in self.units:
            if unit.unit_class != 'air':
                tile = self.map.get_tile(unit.grid_x, unit.grid_y)
                if tile and tile.visibility_state != 0 and self.main_app.user_mode != 'editor': continue

                nation_color = self.nations.get(unit.nation_id, {}).get('color')
                is_hovered = (unit is self.hovered_entity or unit in self.multi_selected_entities) and not self.held_entity
                is_idle = unit in self.idle_units_list
                unit.draw(screen, self.map.camera, nation_color, False, pygame.mouse.get_pos(), self.get_selection_color(unit), is_hovered, is_idle=is_idle)

        # 5. Air Units (Layer 2)
        for unit in self.units:
            if unit.unit_class == 'air':
                tile = self.map.get_tile(unit.grid_x, unit.grid_y)
                if tile and tile.visibility_state != 0 and self.main_app.user_mode != 'editor': continue

                opacity = 255
                if self.find_entity_at(unit.grid_x, unit.grid_y, None, ignore_arrows=True, ignore_units=True, ignore_text=True) or \
                   any(u for u in self.units if u is not unit and u.unit_class != 'air' and u.grid_x == unit.grid_x and u.grid_y == unit.grid_y):
                    opacity = 128
                
                nation_color = self.nations.get(unit.nation_id, {}).get('color')
                is_hovered = (unit is self.hovered_entity or unit in self.multi_selected_entities) and not self.held_entity
                is_idle = unit in self.idle_units_list
                unit.draw(screen, self.map.camera, nation_color, False, pygame.mouse.get_pos(), self.get_selection_color(unit), is_hovered, opacity, is_idle=is_idle)
                
        # 6. Map Text
        for text_obj in self.map_texts:
            if text_obj is not self.held_entity:
                can_see = False
                user = self.main_app.username
                mode = self.main_app.user_mode
                
                if mode == 'editor' or not text_obj.author_username or text_obj.visibility == 'public':
                    can_see = True
                elif text_obj.author_username == user:
                    can_see = True
                elif text_obj.visibility == 'alliance':
                    author_nation_id = self.player_list.get(text_obj.author_username, {}).get('nation_id')
                    player_nation_id = self.main_app.player_nation_id
                    if author_nation_id and player_nation_id and author_nation_id in self.get_allied_nations(player_nation_id):
                        can_see = True

                if can_see:
                    is_hovered = (text_obj is self.hovered_entity or text_obj in self.multi_selected_entities) and not self.held_entity
                    text_obj.draw(screen, self.map.camera, self.get_selection_color(text_obj), is_hovered=is_hovered)

        # 7. Drag Ghost (Semi-transparent copy at mouse cursor)
        if self.held_entity:
            if isinstance(self.held_entity, Unit):
                nation_color = self.nations.get(self.held_entity.nation_id,{}).get('color')
                self.held_entity.draw(screen, self.map.camera, nation_color, True, pygame.mouse.get_pos(), c.COLOR_YELLOW, opacity=128)
            elif isinstance(self.held_entity, MapText):
                self.held_entity.draw(screen, self.map.camera, c.COLOR_YELLOW, is_hovered=True, is_held=True, mouse_pos=pygame.mouse.get_pos())

        # 8. Arrows
        paths = collections.defaultdict(list)
        for arrow in self.arrows:
            paths[tuple(sorted(((arrow.start_gx, arrow.start_gy), (arrow.end_gx, arrow.end_gy))))].append(arrow)

        for path_key, arrows_on_path in paths.items():
            for i, arr in enumerate(arrows_on_path):
                start_tile = self.map.get_tile(arr.start_gx, arr.start_gy)
                
                is_visible = False
                if self.main_app.user_mode == 'editor':
                    is_visible = True
                elif self.main_app.user_mode == 'player':
                    player_nation_id = self.main_app.player_nation_id
                    allies = self.get_allied_nations(player_nation_id)
                    
                    owner_nation = arr.nation_id
                    if not owner_nation:
                        unit_at_start = self.find_entity_at(arr.start_gx, arr.start_gy, None, ignore_arrows=True, ignore_text=True)
                        if isinstance(unit_at_start, Unit):
                            owner_nation = unit_at_start.nation_id

                    if owner_nation in allies:
                        is_own_arrow = (owner_nation == player_nation_id)
                        start_tile_is_visible = start_tile and start_tile.visibility_state == 0
                        
                        if is_own_arrow or start_tile_is_visible:
                            is_visible = True
                
                if not is_visible:
                    continue

                is_invalid = arr.id in self.invalid_arrow_ids
                arr.draw(screen, self.map.camera, self.get_selection_color(arr), len(arrows_on_path), i, is_invalid=is_invalid)
        
        # 9. Straits and Blockades
        is_strait_tool_active = self.current_tool == 'add_strait'
        for strait in self.straits:
            strait.draw(screen, self.map.camera, is_editor_tool_active=is_strait_tool_active)
        for blockade in self.blockades:
            blockade.draw(screen, self.map.camera, is_editor_tool_active=is_strait_tool_active)

        if self.strait_start_pos and is_strait_tool_active:
            start_gx, start_gy = self.strait_start_pos
            world_pos = self.map.camera.screen_to_world(*pygame.mouse.get_pos())
            end_gx, end_gy = self.map.camera.world_to_grid(*world_pos)
            
            strait_type = self.current_selection.get('strait_type', 'strait')
            if strait_type == 'blockade':
                temp_link = Blockade(start_gx, start_gy, end_gx, end_gy)
            else:
                temp_link = Strait(start_gx, start_gy, end_gx, end_gy)
            temp_link.draw(screen, self.map.camera, is_editor_tool_active=True)

        # 10. Overlays and Animations
        self.draw_territory_highlight(screen)
        if self.show_territory_names: self.draw_territory_names(screen)
        if self.show_manpower_overlay: self.draw_manpower_overlay(screen)
        for anim in self.death_animations: anim.draw(screen)
        
        # 11. Ghost Building (Feature Preview)
        if self.current_tool == 'add_feature' and self.current_selection['feature_type']:
            mouse_pos = pygame.mouse.get_pos()
            if not self.ui_manager.is_mouse_over_ui(mouse_pos):
                world_pos = self.map.camera.screen_to_world(*mouse_pos)
                gx, gy = self.map.camera.world_to_grid(*world_pos)
                feature_props = next((cat[self.current_selection['feature_type']] for cat in c.FEATURE_TYPES.values() if self.current_selection['feature_type'] in cat), None)
                tile = self.map.get_tile(gx, gy)
                if tile and feature_props:
                    is_naval = feature_props.get('is_naval', False)
                    is_water = tile.land_type in c.NAVAL_TERRAIN
                    if (is_naval and is_water) or (not is_naval and not is_water):
                        asset = c.get_asset(feature_props['asset'])
                        ghost = asset.copy()
                        ghost.set_alpha(128)
                        dz = round(self.map.camera.zoom * 20) / 20.0
                        sz = int(c.TILE_SIZE * dz * 0.7)
                        if sz > 0:
                            ghost = pygame.transform.smoothscale(ghost, (sz, sz))
                            wx, wy = self.map.camera.grid_to_world(gx, gy)
                            sx, sy = self.map.camera.world_to_screen(wx, wy)
                            off = (c.TILE_SIZE * self.map.camera.zoom - sz) / 2
                            screen.blit(ghost, (sx+off, sy+off))

        # 12. Arrow Preview & Battle Prediction
        preview_arrow_order = self.current_selection['arrow_order']
        is_combat_preview = preview_arrow_order in ['Attack', 'Support Attack', 'Support Defense', 'Suppressive Fire']
        
        self.move_warning_text = None
        self.hovered_arrow = None

        if self.hovered_entity and isinstance(self.hovered_entity, Arrow):
            self.hovered_arrow = self.hovered_entity
            if self.hovered_arrow.order_type in ['Attack', 'Support Attack', 'Suppressive Fire']:
                attacker = self.find_entity_at(self.hovered_arrow.start_gx, self.hovered_arrow.start_gy, None, ignore_arrows=True)
                defender = self.find_entity_at(self.hovered_arrow.end_gx, self.hovered_arrow.end_gy, None, ignore_arrows=True)
                if isinstance(attacker, Unit) and isinstance(defender, Unit):
                    self.update_battle_prediction(attacker, defender, self.hovered_arrow.order_type, pygame.mouse.get_pos())
                else:
                    self.battle_prediction = None
        elif self.arrow_start_pos and self.current_tool == 'add_arrow':
            start_gx, start_gy = self.arrow_start_pos
            world_pos = self.map.camera.screen_to_world(*pygame.mouse.get_pos())
            end_gx, end_gy = self.map.camera.world_to_grid(*world_pos)
            
            temp_arrow = Arrow(start_gx, start_gy, end_gx, end_gy, preview_arrow_order)
            is_invalid_preview = False
            
            unit = self.find_entity_at(start_gx, start_gy, None, ignore_arrows=True)
            if isinstance(unit, Unit) and preview_arrow_order == 'Move':
                try:
                    stats, _ = unit.get_effective_stats(self)
                    max_spe = int(stats.get('spe', 0))
                    chain = self.get_arrow_chain_for_unit(unit)
                    current_cost = self.calculate_chain_cost(unit, chain)
                    path = self._find_shortest_path(unit, (start_gx, start_gy), (end_gx, end_gy))
                    preview_cost = (len(path) - 1) if path else float('inf')
                    total_cost = current_cost + preview_cost
                    if total_cost > max_spe:
                        is_invalid_preview = True
                        self.move_warning_text = f"Exceeds SPE! ({total_cost:.1f}/{max_spe})"
                except (ValueError, TypeError):
                    is_invalid_preview = True
                    self.move_warning_text = "Invalid SPE stat!"
            
            temp_arrow.draw(screen, self.map.camera, is_invalid=is_invalid_preview)

            if is_combat_preview:
                attacker = None
                defender = None
                
                unit1 = self.find_entity_at(start_gx, start_gy, None, ignore_arrows=True)
                unit2 = self.find_entity_at(end_gx, end_gy, None, ignore_arrows=True)

                if isinstance(unit1, Unit) and isinstance(unit2, Unit) and unit1 != unit2:
                    if preview_arrow_order == 'Attack':
                        attacker = unit1
                        defender = unit2
                    else:
                        battle_focus_unit = unit2
                        if not isinstance(battle_focus_unit, Unit):
                            battle_focus_unit = None
                        if battle_focus_unit:
                            for arrow in self.arrows:
                                if arrow.order_type == 'Attack' and (arrow.end_gx, arrow.end_gy) == (battle_focus_unit.grid_x, battle_focus_unit.grid_y):
                                    defender = battle_focus_unit
                                    attacker = self.find_entity_at(arrow.start_gx, arrow.start_gy, None, True)
                                    if isinstance(attacker, Unit): break
                                    else: defender = None
                            if not defender:
                                for arrow in self.arrows:
                                    if arrow.order_type == 'Attack' and (arrow.start_gx, start_gy) == (battle_focus_unit.grid_x, battle_focus_unit.grid_y):
                                        attacker = battle_focus_unit
                                        defender = self.find_entity_at(arrow.end_gx, arrow.end_gy, None, True)
                                        if isinstance(defender, Unit): break
                                        else: attacker = None
                    
                    if isinstance(attacker, Unit) and isinstance(defender, Unit):
                        self.update_battle_prediction(attacker, defender, preview_arrow_order, pygame.mouse.get_pos())
                    else:
                        self.battle_prediction = None
                else:
                    self.battle_prediction = None
            else:
                self.battle_prediction = None
        else:
            self.battle_prediction = None

        if self.battle_prediction:
            attack_text = f"ATK: {self.battle_prediction['attack']}"
            def_text = f"DEF: {self.battle_prediction['defense']}"
            font = c.get_font(c.FONT_PATH, 20)
            attack_surf = font.render(attack_text, True, c.COLOR_RED)
            def_surf = font.render(def_text, True, c.COLOR_BLUE)
            pos = self.battle_prediction['pos']
            bg_rect = pygame.Rect(pos[0] + 15, pos[1] + 15, 100, 60)
            pygame.draw.rect(screen, c.UI_PANEL_COLOR, bg_rect, border_radius=5)
            pygame.draw.rect(screen, c.UI_BORDER_COLOR, bg_rect, 1, border_radius=5)
            screen.blit(attack_surf, (bg_rect.x + 5, bg_rect.y + 5))
            screen.blit(def_surf, (bg_rect.x + 5, bg_rect.y + 30))
        
        if self.move_warning_text:
            font = c.get_font(c.FONT_PATH, 16)
            text_surf = c.create_text_with_border(self.move_warning_text, font, c.COLOR_RED, c.COLOR_BLACK)
            pos = pygame.mouse.get_pos()
            text_rect = text_surf.get_rect(bottomleft=(pos[0] + 15, pos[1] - 15))
            screen.blit(text_surf, text_rect)
            
        self.draw_coordinate_display(screen)
        self.ui_manager.draw(screen)
        self.draw_fps_counter(screen)

    def handle_support_order(self, unit, target_entity, order_type):
        _, cost_so_far = self.calculate_reachable_tiles(unit)
        best_move_pos = None
        is_shift_held = pygame.key.get_mods() & pygame.KMOD_SHIFT
        
        chain = self.get_arrow_chain_for_unit(unit)
        start_node = (unit.grid_x, unit.grid_y)
        if chain:
            start_node = (chain[-1].end_gx, chain[-1].end_gy)

        action_to_check = order_type

        if self.is_valid_action_target(unit, target_entity.grid_x, target_entity.grid_y, action_to_check, from_pos=start_node):
            best_move_pos = start_node
        else:
            min_cost = float('inf')
            
            occupied_or_pending = set((u.grid_x, u.grid_y) for u in self.units if u.unit_class != 'air')
            for arr in self.arrows:
                if arr.order_type == 'Move':
                    occupied_or_pending.add((arr.end_gx, arr.end_gy))
            
            all_possible_moves = set(cost_so_far.keys())
            cost_so_far[start_node] = 0

            for move_pos in all_possible_moves:
                if move_pos in occupied_or_pending and move_pos != start_node:
                    continue

                if self.is_valid_action_target(unit, target_entity.grid_x, target_entity.grid_y, action_to_check, from_pos=move_pos):
                    move_cost = cost_so_far.get(move_pos, float('inf'))
                    if move_cost < min_cost:
                        min_cost = move_cost
                        best_move_pos = move_pos
        
        if best_move_pos:
            actions = []
            
            if not is_shift_held:
                for arrow in chain:
                    actions.append(EntityAction(arrow, is_creation=False))
            
            last_pos = (unit.grid_x, unit.grid_y)
            if chain and is_shift_held:
                last_pos = (chain[-1].end_gx, chain[-1].end_gy)
            
            if best_move_pos != last_pos:
                actions.append(EntityAction(Arrow(last_pos[0], last_pos[1], best_move_pos[0], best_move_pos[1], 'Move', unit.nation_id, unit.id), is_creation=True))

            final_order_type = order_type
            if order_type == 'Attack':
                try:
                    sup_stat = int(str(unit.get_effective_stats(self)[0].get('sup', '0')).split('x')[0])
                except (ValueError, TypeError):
                    sup_stat = 0
                if self.is_target_already_attacked(target_entity, unit.nation_id) and sup_stat > 0:
                    final_order_type = 'Support Attack'

            actions.append(EntityAction(Arrow(best_move_pos[0], best_move_pos[1], target_entity.grid_x, target_entity.grid_y, final_order_type, unit.nation_id, unit.id), is_creation=True))
            
            if actions:
                self.do_action(CompositeAction(actions))

    def is_valid_action_target(self, unit, target_gx, target_gy, order_type, from_pos=None):
        start_pos = from_pos if from_pos else (unit.grid_x, unit.grid_y)
        grid_data = unit.properties['grid']
        rotated_grid = rotate_grid(grid_data, unit.rotation)
        
        rel_x = target_gx - start_pos[0]
        rel_y = target_gy - start_pos[1]
        
        if abs(rel_x) > 2 or abs(rel_y) > 2:
            return False
            
        grid_val = rotated_grid[rel_y + 2][rel_x + 2]
        
        if order_type == 'Attack':
            return grid_val == 3
        elif order_type in ['Support Attack', 'Support Defense', 'Suppressive Fire']:
            return grid_val in [2, 3, 4]
        return False

    def is_target_already_attacked(self, target_unit, friendly_nation_id):
        allies = self.get_allied_nations(friendly_nation_id)
        for arrow in self.arrows:
            if arrow.order_type == 'Attack' and (arrow.end_gx, arrow.end_gy) == (target_unit.grid_x, target_unit.grid_y):
                attacker = self.find_entity_at(arrow.start_gx, arrow.start_gy, None, ignore_arrows=True)
                if attacker and isinstance(attacker, Unit) and attacker.nation_id in allies:
                    return True
        return False

    def get_brush_tiles(self, gx, gy):
        size = self.current_selection.get('paint_brush_size', 1)
        if size == 1: return [(gx, gy)]
        
        tiles = []
        radius = (size - 1) / 2
        for x in range(gx - int(math.floor(radius)), gx + int(math.ceil(radius)) + 1):
            for y in range(gy - int(math.floor(radius)), gy + int(math.ceil(radius)) + 1):
                if size % 2 == 0:
                    tiles.append((x,y))
                else:
                    if (x - gx)**2 + (y - gy)**2 <= radius**2 + 0.5:
                        tiles.append((x,y))
        return tiles

    def perform_tool_action(self, gx, gy, is_drag=False, event=None):
        user_mode = self.main_app.user_mode
        if user_mode == 'player' and self.current_tool not in ['add_arrow', 'select', 'add_text']:
            return
        
        if self.current_tool == 'paint_fog':
            buttons = pygame.mouse.get_pressed()
            if not buttons[0] and not buttons[2]: return
            
            new_value = 2 if buttons[0] else 0
            
            brush_tiles = self.get_brush_tiles(gx, gy)
            tiles_data = []
            for tile_x, tile_y in brush_tiles:
                tile = self.map.get_tile(tile_x, tile_y)
                if tile and tile.visibility_state != new_value:
                    tiles_data.append((tile, tile.visibility_state, new_value))
            
            if tiles_data: self.do_action(PaintAction(tiles_data, 'visibility_state'))
            return

        if self.current_tool in ['paint_land', 'paint_nation']:
            if self.paint_is_fill_mode:
                if is_drag: return # Fill does not support dragging
                tile = self.map.get_tile(gx, gy)
                if not tile: return
                
                paint_type = 'land_type' if self.paint_mode == 'land' else 'nation_owner_id'
                new_value = self.current_selection['paint_land'] if self.paint_mode == 'land' else self.active_nation_id
                old_value = getattr(tile, paint_type)

                if new_value == old_value: return

                tiles_to_paint = []
                q = collections.deque([(gx, gy)])
                visited = set([(gx, gy)])

                while q:
                    cx, cy = q.popleft()
                    
                    current_tile = self.map.get_tile(cx, cy)
                    if current_tile and getattr(current_tile, paint_type) == old_value:
                        tiles_to_paint.append((current_tile, old_value, new_value))
                        
                        for dx, dy in [(0,1), (0,-1), (1,0), (-1,0)]:
                            nx, ny = cx + dx, cy + dy
                            if (nx, ny) not in visited and 0 <= nx < self.map.width and 0 <= ny < self.map.height:
                                visited.add((nx, ny))
                                q.append((nx, ny))
                
                if tiles_to_paint:
                    self.do_action(PaintAction(tiles_to_paint, paint_type))
                return
            else: # Brush mode
                brush_tiles = self.get_brush_tiles(gx, gy)
                tiles_data = []
                paint_type = 'land_type' if self.current_tool == 'paint_land' else 'nation_owner_id'
                new_value = self.current_selection['paint_land'] if self.current_tool == 'paint_land' else self.active_nation_id
                
                for tile_x, tile_y in brush_tiles:
                    tile = self.map.get_tile(tile_x, tile_y)
                    if not tile: continue
                    
                    old_value = getattr(tile, paint_type)
                    if old_value != new_value:
                        tiles_data.append((tile, old_value, new_value))

                if tiles_data: self.do_action(PaintAction(tiles_data, paint_type))
                return

        if is_drag: return
        
        nation_to_add = self.active_nation_id
        if user_mode == 'player':
            nation_to_add = self.main_app.player_nation_id

        if self.current_tool == 'add_unit':
            if not nation_to_add: return
            unit_key = self.current_selection['unit_type']
            if unit_key: self.do_action(EntityAction(Unit(unit_key, gx, gy, nation_to_add), is_creation=True))
        elif self.current_tool == 'add_feature':
            feature_key = self.current_selection['feature_type']
            if feature_key:
                feature_props = next((cat[feature_key] for cat in c.FEATURE_TYPES.values() if feature_key in cat), None)
                
                tile = self.map.get_tile(gx, gy)
                if tile and feature_props:
                    is_naval_feature = feature_props.get('is_naval', False)
                    is_water_tile = tile.land_type in c.NAVAL_TERRAIN
                    
                    if (is_naval_feature and is_water_tile) or (not is_naval_feature and not is_water_tile):
                        self.do_action(EntityAction(MapFeature(feature_key, gx, gy), is_creation=True))
                    else:
                        print(f"Cannot place '{feature_props['name']}' on '{tile.land_type}'.")
        elif self.current_tool == 'add_text':
            author_name = self.main_app.username if user_mode != 'editor' else None
            text_obj = MapText(gx, gy, author_username=author_name, visibility='public' if user_mode == 'editor' else 'private', importance=0)
            self.do_action(EntityAction(text_obj, is_creation=True))
        elif self.current_tool == 'add_arrow':
            player_nation_id = self.main_app.player_nation_id if self.main_app.user_mode == 'player' else None
            if not self.arrow_start_pos: 
                self.arrow_start_pos = (gx, gy)
            else:
                if self.arrow_start_pos != (gx, gy):
                    unit_at_start = self.find_entity_at(self.arrow_start_pos[0], self.arrow_start_pos[1], None, ignore_arrows=True)
                    unit_id = unit_at_start.id if isinstance(unit_at_start, Unit) else None
                    arrow = Arrow(self.arrow_start_pos[0], self.arrow_start_pos[1], gx, gy, self.current_selection['arrow_order'], nation_id=player_nation_id, unit_id=unit_id)
                    self.do_action(EntityAction(arrow, is_creation=True))
                self.arrow_start_pos = None
        elif self.current_tool == 'add_strait':
            if not self.strait_start_pos:
                self.strait_start_pos = (gx, gy)
            else:
                if self.strait_start_pos != (gx, gy):
                    strait_type = self.current_selection.get('strait_type', 'strait')
                    if strait_type == 'blockade':
                        entity = Blockade(self.strait_start_pos[0], self.strait_start_pos[1], gx, gy)
                    else:
                        entity = Strait(self.strait_start_pos[0], self.strait_start_pos[1], gx, gy)
                    self.do_action(EntityAction(entity, is_creation=True))
                self.strait_start_pos = None
    
    def handle_events(self, event):
        if event.type == pygame.QUIT:
            self.main_app.change_state('QUIT')

        if event.type == self.AI_EVENT:
            self._finalize_ai_moves()

        if event.type == pygame.MOUSEWHEEL:
            if hasattr(self.ui_manager, 'leaderboard_panel') and self.ui_manager.leaderboard_panel.is_mouse_over(pygame.mouse.get_pos()):
                if self.ui_manager.leaderboard_panel.handle_event(event, self.ui_manager, force_scroll=True):
                    return

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_AC_BACK:
                self.main_app.change_state('QUIT')
                return
            if event.key == pygame.K_TAB:
                self.cycle_idle_unit()
                return
            mods = pygame.key.get_mods()
            if mods & pygame.KMOD_CTRL:
                if event.key == pygame.K_z: self.undo_action()
                elif event.key == pygame.K_y: self.redo_action()
                elif event.key == pygame.K_c and self.main_app.user_mode == 'editor':
                    if len(self.multi_selected_entities) == 1:
                        entity = self.multi_selected_entities[0]
                        if isinstance(entity, (Unit, MapFeature, MapText)):
                            self.entity_clipboard = {
                                'type': type(entity).__name__,
                                'data': entity.to_dict(compact=False)
                            }
                            print(f"Copied {self.entity_clipboard['type']} to clipboard.")
                elif event.key == pygame.K_v and self.main_app.user_mode == 'editor':
                    if self.entity_clipboard:
                        world_pos = self.map.camera.screen_to_world(*pygame.mouse.get_pos())
                        gx, gy = self.map.camera.world_to_grid(*world_pos)
                        
                        data = self.entity_clipboard['data'].copy()
                        data['grid_x'], data['grid_y'] = gx, gy
                        data['id'] = str(uuid.uuid4())

                        new_entity = None
                        e_type = self.entity_clipboard['type']
                        
                        if e_type == 'Unit': new_entity = Unit.from_dict(data)
                        elif e_type == 'MapFeature': new_entity = MapFeature.from_dict(data)
                        elif e_type == 'MapText': new_entity = MapText.from_dict(data)
                        
                        if new_entity:
                            self.do_action(EntityAction(new_entity, is_creation=True))

            
            is_input_active = self.ui_manager.active_input and self.ui_manager.active_input.is_active
            if event.key == pygame.K_DELETE and not is_input_active and self.is_multi_selecting():
                self.delete_multi_selected()

        if self.ui_manager.handle_event(event):
            return 
        if self.minimap.handle_event(event, self.ui_manager):
            return 

        self.handle_map_interaction(event)
        
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 2:
            self.panning = True
        if event.type == pygame.MOUSEBUTTONUP and event.button == 2:
            self.panning = False
        if event.type == pygame.MOUSEMOTION and self.panning:
            if not self.ui_manager.is_mouse_over_ui(event.pos):
                self.map.camera.pan(event.rel[0], event.rel[1])
        
        if event.type == pygame.MOUSEWHEEL:
            if not self.ui_manager.is_mouse_over_ui(pygame.mouse.get_pos()):
                self.map.camera.adjust_zoom(1 + event.y * 0.1, pygame.mouse.get_pos())

    def toggle_fog_of_war(self):
        self.fog_of_war_enabled = not self.fog_of_war_enabled
        if not self.fog_of_war_enabled:
            for layer in self.layers.values():
                for row in layer['map'].grid:
                    for tile in row:
                        tile.visibility_state = 0
        self.fow_dirty = True

    def update(self):
        self.ui_manager.update()
        self.minimap.update()
        if self.territory_data_dirty:
            self.calculate_territory_data()
            self.update_territorial_waters()
            self.territory_data_dirty = False
            self.minimap.set_dirty()
        if self.fow_dirty:
            if self.main_app.user_mode != 'editor' and self.fog_of_war_enabled:
                self.update_fog_of_war()
            self.map.set_fog_dirty()
            self.fow_dirty = False
        if self.manpower_dirty:
            self.calculate_leaderboard_stats()
            self.ui_manager.rebuild_leaderboard()
        self.death_animations = [anim for anim in self.death_animations if anim.update()]

    def update_territorial_waters(self):
        for layer_key, layer in self.layers.items():
            current_map = layer['map']
            
            for x in range(current_map.width):
                for y in range(current_map.height):
                    tile = current_map.get_tile(x, y)
                    if tile and tile.land_type == 'Territorial Water':
                        tile.land_type = 'Water'

            coastal_tiles_by_nation = collections.defaultdict(list)
            all_water_tiles = []
            feature_locations = {(f.grid_x, f.grid_y) for f in layer['features']}

            for x in range(current_map.width):
                for y in range(current_map.height):
                    tile = current_map.grid[x][y]
                    if tile.land_type in c.NAVAL_TERRAIN:
                        all_water_tiles.append(tile)
                    
                    elif tile.nation_owner_id:
                        is_coastal = False
                        for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                            nx, ny = x + dx, y + dy
                            neighbor = current_map.get_tile(nx, ny)
                            if neighbor and neighbor.land_type in c.NAVAL_TERRAIN:
                                is_coastal = True
                                break
                        if is_coastal:
                            coastal_tiles_by_nation[tile.nation_owner_id].append((x, y))

            for feature in layer['features']:
                if feature.feature_type == 'oil_rig':
                    tile = current_map.get_tile(feature.grid_x, feature.grid_y)
                    if tile and tile.nation_owner_id:
                        if (feature.grid_x, feature.grid_y) not in coastal_tiles_by_nation[tile.nation_owner_id]:
                            coastal_tiles_by_nation[tile.nation_owner_id].append((feature.grid_x, feature.grid_y))

            changes_to_apply = []
            for water_tile in all_water_tiles:
                if (water_tile.grid_x, water_tile.grid_y) in feature_locations:
                    continue
                
                wx, wy = water_tile.grid_x, water_tile.grid_y
                
                distances = {}
                for nation_id, coastal_tiles in coastal_tiles_by_nation.items():
                    if not coastal_tiles: continue
                    
                    min_dist = min(abs(wx - cx) + abs(wy - cy) for cx, cy in coastal_tiles)
                    if min_dist <= 2:
                        distances[nation_id] = min_dist
                
                owner_id = None
                if distances:
                    min_dist_val = min(distances.values())
                    closest_nations = [nid for nid, dist in distances.items() if dist == min_dist_val]
                    if len(closest_nations) == 1:
                        owner_id = closest_nations[0]

                current_owner = water_tile.nation_owner_id
                current_type = water_tile.land_type

                if current_type == 'Canal':
                    if current_owner != owner_id:
                        changes_to_apply.append((water_tile, owner_id, 'Canal'))
                else:
                    new_type = 'Territorial Water' if owner_id else 'Water'
                    if current_owner != owner_id or current_type != new_type:
                        changes_to_apply.append((water_tile, owner_id, new_type))

            if changes_to_apply:
                for tile, new_owner, new_type in changes_to_apply:
                    tile.nation_owner_id = new_owner
                    tile.land_type = new_type
                current_map.set_dirty()
    
    def get_allied_nations(self, nation_id):
        if not nation_id: return []
        for alliance_name, members in self.alliances.items():
            if nation_id in members:
                return members
        return [nation_id]

    def update_fog_of_war(self):
        player_nation_id = self.main_app.player_nation_id
        if not player_nation_id:
            for layer in self.layers.values():
                for row in layer['map'].grid:
                    for tile in row:
                        tile.visibility_state = 0
            return
        
        for layer in self.layers.values():
            for row in layer['map'].grid:
                for tile in row:
                    if tile.visibility_state < 2:
                        tile.visibility_state = 1

        visible_tiles = set()
        allied_nations = self.get_allied_nations(player_nation_id)

        for layer_key, layer in self.layers.items():
            current_map = layer['map']
            
            for x in range(current_map.width):
                for y in range(current_map.height):
                    if current_map.grid[x][y].nation_owner_id in allied_nations:
                        for dx in range(-1, 2):
                            for dy in range(-1, 2):
                                visible_tiles.add((layer_key, x + dx, y + dy))

            for unit in layer['units']:
                if unit.nation_id in allied_nations:
                    grid_data = unit.properties['grid']
                    rotated_grid = rotate_grid(grid_data, unit.rotation)
                    for r in range(5):
                        for col in range(5):
                            if rotated_grid[r][col] in [1, 2, 3, 4]:
                                dx, dy = col - 2, r - 2
                                action_gx, action_gy = unit.grid_x + dx, unit.grid_y + dy
                                
                                visible_tiles.add((layer_key, action_gx, action_gy))
                                visible_tiles.add((layer_key, action_gx + 1, action_gy))
                                visible_tiles.add((layer_key, action_gx - 1, action_gy))
                                visible_tiles.add((layer_key, action_gx, action_gy + 1))
                                visible_tiles.add((layer_key, action_gx, action_gy - 1))

            vision_features = {'fort', 'city', 'village', 'a_city', 'a_village'}
            for feature in layer['features']:
                if feature.feature_type in vision_features:
                    tile = current_map.get_tile(feature.grid_x, feature.grid_y)
                    if tile and tile.nation_owner_id in allied_nations:
                        for dx in range(-2, 3):
                            for dy in range(-2, 3):
                                visible_tiles.add((layer_key, feature.grid_x + dx, feature.grid_y + dy))
        
        for layer_key, x, y in visible_tiles:
            if layer_key in self.layers:
                tile = self.layers[layer_key]['map'].get_tile(x, y)
                if tile:
                    tile.visibility_state = 0

        self.minimap.set_dirty()

    def calculate_manpower(self):
        self.manpower_data.clear()
        self.grand_total_manpower = 0
        
        all_units = []
        for layer in self.layers.values():
            for u in layer['units']:
                all_units.append(u)
                if hasattr(u, 'carried_units') and u.carried_units:
                    all_units.extend(u.carried_units)
        
        all_features = []
        for layer in self.layers.values():
            all_features.extend(layer['features'])
            
        for nid, nation in self.nations.items():
            self.manpower_data[nid] = {'used': 0, 'total': 0}
        
        for unit in all_units:
            if unit.nation_id in self.manpower_data:
                try: self.manpower_data[unit.nation_id]['used'] += int(unit.get_effective_stats(self)[0].get('cost', 0))
                except (ValueError, TypeError): pass
        
        for feature in all_features:
            f_type = feature.feature_type
            manpower_yield = 0
            if f_type in ['city', 'a_city']:
                manpower_yield = 2
            elif f_type in ['village', 'a_village', 'oil_rig']:
                manpower_yield = 1
            
            if manpower_yield > 0:
                self.grand_total_manpower += manpower_yield
                tile = self.map.get_tile(feature.grid_x, feature.grid_y)
                if tile and tile.nation_owner_id in self.manpower_data:
                    self.manpower_data[tile.nation_owner_id]['total'] += manpower_yield

        self.manpower_dirty = False

    def find_contiguous_territories(self):
        visited, territories = set(), collections.defaultdict(list)
        for y in range(self.map.height):
            for x in range(self.map.width):
                if (x,y) in visited or self.map.grid[x][y].nation_owner_id is None: continue
                component, q, owner_id = [], collections.deque([(x,y)]), self.map.grid[x][y].nation_owner_id
                visited.add((x,y)); component.append((x,y))
                while q:
                    cx,cy = q.popleft()
                    for dx,dy in [(0,1),(0,-1),(1,0),(-1,0)]:
                        nx,ny = cx+dx, cy+dy
                        if 0<=nx<self.map.width and 0<=ny<self.map.height and (nx,ny) not in visited and self.map.grid[nx][ny].nation_owner_id==owner_id:
                            visited.add((nx,ny)); q.append((nx,ny)); component.append((nx,ny))
                territories[owner_id].append(component)
        return territories

    def calculate_territory_data(self):
        self.cached_territory_data.clear()
        self.territory_name_cache.clear()
        territories = self.find_contiguous_territories()
        for nid, components in territories.items():
            ndata = self.nations.get(nid)
            if not ndata: continue
            self.cached_territory_data[nid] = []
            for comp in components:
                if len(comp) < 3: continue
                avg_x = sum(t[0] for t in comp) / len(comp); avg_y = sum(t[1] for t in comp) / len(comp)
                mean_x, mean_y = avg_x, avg_y
                cov_xx = sum((t[0] - mean_x)**2 for t in comp); cov_yy = sum((t[1] - mean_y)**2 for t in comp)
                cov_xy = sum((t[0] - mean_x)*(t[1] - mean_y) for t in comp)
                trace = cov_xx + cov_yy; det = cov_xx*cov_yy - cov_xy*cov_xy
                if trace**2/4 - det < 0: continue
                lambda1 = trace/2 + math.sqrt(max(0, trace**2/4 - det))
                angle_rad = math.atan2(lambda1 - cov_xx, cov_xy); angle_deg = -math.degrees(angle_rad)
                if 90 < abs(angle_deg) < 270: angle_deg += 180
                self.cached_territory_data[nid].append({'name': ndata['name'], 'color': ndata['color'], 'avg_gx': avg_x, 'avg_gy': avg_y, 'angle': angle_deg, 'comp': comp})

    
    def calculate_reachable_tiles(self, unit):
        try:
            stats, _ = unit.get_effective_stats(self)
            base_spe = int(stats.get('spe', 0))
        except (ValueError, TypeError):
            base_spe = 0
            
        chain = self.get_arrow_chain_for_unit(unit)
        chain_cost = self.calculate_chain_cost(unit, chain)
        
        start_pos = (unit.grid_x, unit.grid_y)
        if chain:
            start_pos = (chain[-1].end_gx, chain[-1].end_gy)

        max_dist = math.floor(base_spe - chain_cost)

        if max_dist <= 0:
            return set(), {}

        open_set = [(0, start_pos)]
        cost_so_far = {start_pos: 0}
        
        grid_data = unit.properties['grid']
        rotated_grid = rotate_grid(grid_data, unit.rotation)
        possible_grid_moves = []
        for r in range(5):
            for col in range(5):
                if rotated_grid[r][col] in [1, 2, 3]:
                    dx, dy = col - 2, r - 2
                    if dx == 0 and dy == 0:
                        continue
                    possible_grid_moves.append((dx, dy))
        
        while open_set:
            current_cost, current_pos = heapq.heappop(open_set)

            if current_cost >= max_dist:
                continue

            potential_steps = []
            for dx, dy in possible_grid_moves:
                neighbor_pos = (current_pos[0] + dx, current_pos[1] + dy)
                potential_steps.append((neighbor_pos, 1))

            if unit.unit_class != 'air':
                for strait in self.straits:
                    if (strait.start_gx, strait.start_gy) == current_pos:
                        potential_steps.append(((strait.end_gx, strait.end_gy), 1))
                    elif (strait.end_gx, strait.end_gy) == current_pos:
                        potential_steps.append(((strait.start_gx, strait.start_gy), 1))

            for neighbor, move_cost in potential_steps:
                new_cost = current_cost + move_cost
                
                if new_cost > max_dist:
                    continue

                if neighbor not in cost_so_far or new_cost < cost_so_far[neighbor]:
                    tile = self.map.get_tile(neighbor[0], neighbor[1])
                    if self.main_app.user_mode == 'player' and tile and tile.visibility_state == 2:
                        continue
                    if not tile or tile.land_type == 'Border':
                        continue

                    is_blocked = any(b for b in self.blockades if {current_pos, neighbor} == {(b.start_gx, b.start_gy), (b.end_gx, b.end_gy)})
                    if is_blocked:
                        continue

                    is_strait_move = any(s for s in self.straits if {current_pos, neighbor} == {(s.start_gx, s.start_gy), (s.end_gx, s.end_gy)})
                    
                    is_passable = True
                    if unit.unit_class != 'air':
                        if tile.land_type == 'Canal':
                            is_passable = True
                        elif unit.unit_class == 'naval':
                            is_passable = tile.land_type in c.NAVAL_TERRAIN or is_strait_move
                        elif unit.unit_class == 'land':
                            is_passable = tile.land_type not in c.NAVAL_TERRAIN or is_strait_move
                    
                    if not is_passable:
                        continue

                    entity_on_tile = self.find_entity_at(neighbor[0], neighbor[1], None, ignore_arrows=True)
                    is_blocked_by_unit = isinstance(entity_on_tile, Unit) and unit.unit_class != 'air' and entity_on_tile.unit_class != 'air'
                    
                    if not is_blocked_by_unit:
                        cost_so_far[neighbor] = new_cost
                        heapq.heappush(open_set, (new_cost, neighbor))
        
        reachable = set(cost_so_far.keys())
        reachable.discard(start_pos)
        return reachable, cost_so_far
    
    def calculate_leaderboard_stats(self):
        self.manpower_data.clear()
        self.grand_total_manpower = 0
        
        for nid, nation in self.nations.items():
            self.manpower_data[nid] = {'used': 0, 'total': 0, 'strength': 0, 'techs': 0}
        
        for nid, nation_data in self.nations.items():
            self.manpower_data[nid]['techs'] = len(nation_data.get('researched_techs', []))

        all_units = []
        for layer in self.layers.values():
            for u in layer['units']:
                all_units.append(u)
                if hasattr(u, 'carried_units') and u.carried_units:
                    all_units.extend(u.carried_units)
        
        for unit in all_units:
            if unit.nation_id in self.manpower_data:
                try:
                    stats, _ = unit.get_effective_stats(self)
                    cost = int(stats.get('cost', 0))
                    
                    str_val = int(stats.get('str', 0))
                    sup_str = str(stats.get('sup', '0'))
                    if 'x' in sup_str:
                        parts = sup_str.split('x')
                        sup = int(parts[0]) * int(parts[1])
                    else:
                        sup = int(sup_str)
                    arm = int(stats.get('arm', 0))
                    spe = int(stats.get('spe', 0))

                    strength_bonus = (0.5 * str_val) + (0.25 * arm) + (0.5 * sup) + (0.25 * spe)
                    
                    self.manpower_data[unit.nation_id]['used'] += cost
                    self.manpower_data[unit.nation_id]['strength'] += (cost + strength_bonus)

                except (ValueError, TypeError): pass

        for nid in self.manpower_data:
            self.manpower_data[nid]['strength'] = int(round(self.manpower_data[nid]['strength']))
        
        for layer in self.layers.values():
            for feature in layer['features']:
                f_type = feature.feature_type
                manpower_yield = 0
                if f_type in ['city', 'a_city']: manpower_yield = 2
                elif f_type in ['village', 'a_village', 'oil_rig']: manpower_yield = 1
                
                if manpower_yield > 0:
                    self.grand_total_manpower += manpower_yield
                    tile = self.map.get_tile(feature.grid_x, feature.grid_y)
                    if tile and tile.nation_owner_id in self.manpower_data:
                        self.manpower_data[tile.nation_owner_id]['total'] += manpower_yield

        self.manpower_dirty = False

    def draw_manpower_overlay(self, screen):
        font = c.get_font(c.FONT_PATH, int(18 * self.map.camera.zoom))
        if not font: return

        for layer in self.layers.values():
            for feature in layer['features']:
                manpower_yield = 0
                if feature.feature_type in ['city', 'a_city']: manpower_yield = 2
                elif feature.feature_type in ['village', 'a_village', 'oil_rig']: manpower_yield = 1

                if manpower_yield > 0:
                    wx, wy = self.map.camera.grid_to_world(feature.grid_x, feature.grid_y)
                    sx, sy = self.map.camera.world_to_screen(wx, wy)
                    offset = c.TILE_SIZE * self.map.camera.zoom / 2
                    
                    text_surf = create_text_with_border(f"+{manpower_yield}", font, c.COLOR_YELLOW, c.COLOR_BLACK)
                    text_rect = text_surf.get_rect(center=(sx + offset, sy + offset))
                    screen.blit(text_surf, text_rect)

    def commence_all_moves(self):
        all_actions = []
        paint_actions_data = collections.defaultdict(list)
        arrows_to_delete = []

        # Get all initial unit positions and what units they might be carrying
        all_units_map = {u.id: u for layer in self.layers.values() for u in layer['units']}
        
        # Projected final positions to resolve conflicts.
        # Initialize with units that have NO move orders. They are static obstacles.
        units_with_chains = {u for u in self.units if self.get_arrow_chain_for_unit(u)}
        projected_final_positions = {
            (u.grid_x, u.grid_y): u for u in self.units 
            if u not in units_with_chains and u.unit_class != 'air'
        }

        # First, process load/unload as they take priority and can change unit locations before moves
        load_unload_actions, processed_arrow_ids = self._get_load_unload_actions(set())
        all_actions.extend(load_unload_actions)
        
        # Temporarily apply these actions to predict the state before movement
        for action in load_unload_actions:
            action.execute(self)
        
        # Now process movement chains for units that haven't been loaded
        units_to_move = [u for u in self.units if self.get_arrow_chain_for_unit(u) and not any(a for a in load_unload_actions if isinstance(a, MoveOrCarryAction) and a.entity.id == u.id)]
        
        for unit in units_to_move:
            chain = self.get_arrow_chain_for_unit(unit)
            if not chain: continue

            current_pos = (unit.grid_x, unit.grid_y)
            path_taken = [current_pos]
            processed_arrows_in_chain = []

            for arrow in chain:
                if arrow.id in processed_arrow_ids: continue
                if arrow.order_type != 'Move':
                    break # Stop move chain on non-move orders

                next_pos = (arrow.end_gx, arrow.end_gy)

                # Validate the step
                is_valid = self._is_move_valid(unit, current_pos, next_pos)
                
                # Check for conflicts with other units' final positions
                if is_valid and next_pos in projected_final_positions:
                    is_valid = False
                
                if is_valid:
                    current_pos = next_pos
                    path_taken.append(current_pos)
                    processed_arrows_in_chain.append(arrow)
                else:
                    break # Stop chain at first invalid move

            # If the unit actually moved
            if current_pos != (unit.grid_x, unit.grid_y):
                projected_final_positions[current_pos] = unit
                
                # Create a single move action from start to the final valid position
                move_action = MoveOrCarryAction(unit, (unit.grid_x, unit.grid_y), current_pos, None, None)
                all_actions.append(move_action)
                
                # Handle carried units' positions as well
                if hasattr(unit, 'carried_units'):
                    for carried_unit in unit.carried_units:
                         all_actions.append(MoveOrCarryAction(carried_unit, (carried_unit.grid_x, carried_unit.grid_y), current_pos, unit, unit))
                
                # Handle territory capture along the path
                if unit.unit_class == 'land':
                    allies = self.get_allied_nations(unit.nation_id)
                    for step_pos in path_taken:
                        tile = self.map.get_tile(step_pos[0], step_pos[1])
                        unit_on_tile = self.find_entity_at(step_pos[0], step_pos[1], None, ignore_arrows=True)
                        is_occupied_by_non_ally = isinstance(unit_on_tile, Unit) and unit_on_tile.nation_id not in allies and unit_on_tile.id != unit.id
                        
                        if tile and tile.nation_owner_id not in allies and not is_occupied_by_non_ally:
                            paint_actions_data[(tile.grid_x, tile.grid_y)].append((tile.nation_owner_id, unit.nation_id))

            arrows_to_delete.extend(processed_arrows_in_chain)
            processed_arrow_ids.update(a.id for a in processed_arrows_in_chain)

        # Undo the temporary load/unload actions before applying the composite action
        for action in reversed(load_unload_actions):
            action.undo(self)
            
        # Add paint actions for territory capture
        paint_data = []
        for (gx, gy), changes in paint_actions_data.items():
            if changes:
                tile = self.map.get_tile(gx, gy)
                old_value = changes[0][0]
                new_value = changes[-1][1]
                if tile and old_value != new_value:
                    paint_data.append((tile, old_value, new_value))
        
        if paint_data:
            all_actions.append(PaintAction(paint_data, 'nation_owner_id'))

        # Add actions to delete all processed arrows
        unique_arrows_to_delete = {a.id: a for a in arrows_to_delete}.values()
        for arrow in unique_arrows_to_delete:
            all_actions.append(EntityAction(arrow, is_creation=False))

        if all_actions:
            self.do_action(CompositeAction(all_actions))
        else:
            print("No valid moves to commence.")
            
    def rotate_selected_unit(self):
        if len(self.multi_selected_entities) != 1: return
        
        entity = self.multi_selected_entities[0]
        if not isinstance(entity, Unit): return

        user_mode = self.main_app.user_mode
        if user_mode == 'editor' or (user_mode == 'player' and entity.nation_id == self.main_app.player_nation_id):
            self.do_action(RotateUnitAction(entity))

    def draw_action_range(self, screen):
        if not self.multi_selected_entities or len(self.multi_selected_entities) != 1:
            return

        unit = self.multi_selected_entities[0]
        if not isinstance(unit, Unit) or self.map.camera.zoom < 0.3:
            return
 
        scaled_tile_size = c.TILE_SIZE * self.map.camera.zoom
        if scaled_tile_size < 1: return
        
        if self.action_range_display:
            for gx, gy in self.action_range_display:
                wx, wy = self.map.camera.grid_to_world(gx, gy)
                sx, sy = self.map.camera.world_to_screen(wx, wy)
                
                range_surface = pygame.Surface((scaled_tile_size, scaled_tile_size), pygame.SRCALPHA)
                range_surface.fill((*c.COLOR_BLUE, 96))
                screen.blit(range_surface, (sx, sy))
                pygame.draw.rect(screen, c.darken_color(c.COLOR_BLUE, 0.5), (sx, sy, scaled_tile_size, scaled_tile_size), 2)

        origin = self.hovered_tile_for_range
        if not origin:
            chain = self.get_arrow_chain_for_unit(unit)
            if chain:
                origin = (chain[-1].end_gx, chain[-1].end_gy)
            else:
                origin = (unit.grid_x, unit.grid_y)
        
        if origin:
            grid_data = unit.properties['grid']
            rotated_grid = rotate_grid(grid_data, unit.rotation)
            
            for r in range(5):
                for col in range(5):
                    grid_value = rotated_grid[r][col]
                    if grid_value in [0, 1, 9]: continue

                    action_gx = origin[0] + (col - 2)
                    action_gy = origin[1] + (r - 2)

                    if self.map.get_tile(action_gx, action_gy):
                        wx, wy = self.map.camera.grid_to_world(action_gx, action_gy)
                        sx, sy = self.map.camera.world_to_screen(wx, wy)
                        
                        color_key = EncyclopediaScreen.GRID_COLORS.get(grid_value)
                        if color_key:
                            color = pygame.Color(color_key)
                            action_surface = pygame.Surface((scaled_tile_size, scaled_tile_size), pygame.SRCALPHA)
                            action_surface.fill((color.r, color.g, color.b, 96))
                            screen.blit(action_surface, (sx, sy))
                            pygame.draw.rect(screen, c.darken_color(color, 0.5), (sx, sy, scaled_tile_size, scaled_tile_size), 2)
                            
    def _finalize_ai_moves(self):
        print("AI finished thinking. Executing moves.")
        if self.ai_pending_actions:
            self.do_action(CompositeAction(self.ai_pending_actions))
        
        self.ai_is_thinking = False
        self.ai_pending_actions = []
        pygame.time.set_timer(self.AI_EVENT, 0)
        self.ui_manager.rebuild_admin_panel()
                            
    def run_ai_for_nation(self, nation_id):
        individual_strengths = self._calculate_strength_ranking()
        alliance_strengths = self._calculate_alliance_strengths(individual_strengths)
        ai_strength = alliance_strengths.get(nation_id, 0)
        
        threats = self._assess_threats(nation_id)
        
        primary_threat_id = None
        if threats['by_nation']:
            primary_threat_id = max(threats['by_nation'], key=threats['by_nation'].get)
        
        strategy = 'DEFENSIVE'
        expansion_ratio = 0.0
        
        if self.nations.get(nation_id, {}).get('is_special', False):
            strategy = 'AGGRESSIVE'
            expansion_ratio = 0.8
        elif len(self.arrows) < len(self.units) // 2:
            strategy = 'AGGRESSIVE'
            expansion_ratio = 0.8
        elif primary_threat_id:
            threat_strength = alliance_strengths.get(primary_threat_id, 0)
            if ai_strength > threat_strength * 1.5:
                strategy = 'AGGRESSIVE'
                expansion_ratio = 0.5
            elif ai_strength * 1.5 > threat_strength:
                strategy = 'TACTICAL'
                expansion_ratio = 0.2
            else:
                expansion_ratio = 0.0
        else: 
            strategy = 'AGGRESSIVE'
            expansion_ratio = 1.0

        print(f"AI: Nation '{self.nations.get(nation_id,{}).get('name')}'. Strategy: {strategy}. Expansion Ratio: {expansion_ratio}")

        all_units = [u for u in self.units if u.nation_id == nation_id and not self.get_arrow_chain_for_unit(u)]
        land_units = sorted([u for u in all_units if u.unit_class == 'land'], key=lambda u: u.get_effective_stats(self)[0].get('cost', 0))
        naval_units = [u for u in all_units if u.unit_class == 'naval']
        
        num_to_expand = 1 if strategy == 'DEFENSIVE' and land_units else int(len(land_units) * expansion_ratio)
        
        expansion_units = land_units[:num_to_expand]
        combat_units = land_units[num_to_expand:]
        available_transports = [u for u in naval_units if u.weight_capacity]
        
        projected_positions = {(u.grid_x, u.grid_y) for u in self.units}

        if expansion_units:
            yield from self._execute_expansion_strategy(nation_id, expansion_units, available_transports, projected_positions)
        if combat_units:
            yield from self._execute_combat_strategy(nation_id, combat_units, strategy, threats, available_transports, projected_positions)
        if naval_units:
            yield from self._execute_naval_strategy(nation_id, naval_units, projected_positions)

    def _calculate_strength_ranking(self):
        ranking = {}
        for nid, data in self.manpower_data.items():
            score = data.get('total', 0) * 1.5 + data.get('used', 0)
            ranking[nid] = score
        return ranking
    
    def _calculate_alliance_strengths(self, individual_strengths):
        alliance_strengths = {}
        for nid in self.nations.keys():
            allies = self.get_allied_nations(nid)
            total_strength = individual_strengths.get(nid, 0)
            for ally_id in allies:
                if ally_id != nid:
                    total_strength += individual_strengths.get(ally_id, 0) * 0.75
            alliance_strengths[nid] = total_strength
        return alliance_strengths

    def _assess_threats(self, ai_nation_id):
        threats = {'by_nation': collections.defaultdict(int), 'locations': collections.defaultdict(int)}
        allies = self.get_allied_nations(ai_nation_id)
        
        strategic_points = []
        for feature in self.features:
            tile = self.map.get_tile(feature.grid_x, feature.grid_y)
            if tile and tile.nation_owner_id in allies:
                manpower_yield = 0
                if feature.feature_type in ['city', 'a_city']: manpower_yield = 2
                elif feature.feature_type in ['village', 'a_village', 'oil_rig']: manpower_yield = 1
                if manpower_yield > 0:
                    strategic_points.append({'pos': (feature.grid_x, feature.grid_y), 'value': manpower_yield + 1})

        for unit in self.units:
            if unit.nation_id not in allies:
                is_special_threat = self.nations.get(unit.nation_id, {}).get('is_special', False)
                
                for point in strategic_points:
                    dist = abs(unit.grid_x - point['pos'][0]) + abs(unit.grid_y - point['pos'][1])
                    
                    threat_score = 0
                    if dist < 15:
                        threat_score = (15 - dist) * point['value']
                    elif dist < 45:
                        threat_score = (45 - dist) * point['value'] * 0.25
                    
                    if is_special_threat:
                        threat_score *= 2.0

                    if threat_score > 0:
                        threats['by_nation'][unit.nation_id] += threat_score
                        threats['locations'][point['pos']] += threat_score
        return threats
    
    def _execute_combat_strategy(self, ai_nation_id, combat_units, strategy, threats, available_transports, projected_positions):
        if strategy == 'AGGRESSIVE':
            yield from self._execute_expansion_strategy(ai_nation_id, combat_units, available_transports, projected_positions, target_enemy=True)
        elif strategy == 'TACTICAL':
            yield from self._execute_tactical_strategy(ai_nation_id, combat_units, threats, available_transports, projected_positions)
        else:
            yield from self._execute_defensive_strategy(ai_nation_id, combat_units, threats, available_transports, projected_positions)
    
    def _execute_aggressive_strategy(self, ai_nation_id, combat_units, strength_ranking, available_transports, projected_positions):
        allies = self.get_allied_nations(ai_nation_id)
        
        weakest_target_id = None
        min_strength = float('inf')
        for nid, strength in strength_ranking.items():
            if nid not in allies:
                if strength < min_strength:
                    min_strength = strength
                    weakest_target_id = nid
        
        if not weakest_target_id: return
        
        enemy_features = []
        for feature in self.features:
            tile = self.map.get_tile(feature.grid_x, feature.grid_y)
            if tile and tile.nation_owner_id == weakest_target_id:
                if feature.feature_type in ['city', 'a_city', 'village', 'a_village']:
                    enemy_features.append(feature)

        if not enemy_features: return

        for unit in combat_units:
            enemy_features.sort(key=lambda f: abs(unit.grid_x - f.grid_x) + abs(unit.grid_y - f.grid_y))
            if enemy_features:
                target = enemy_features[0]
                target_pos = (target.grid_x, target.grid_y)
                path = self._find_shortest_path(unit, (unit.grid_x, unit.grid_y), target_pos, occupied_tiles=projected_positions)
                if path:
                    reachable_tiles, _ = self.calculate_reachable_tiles(unit)
                    land_path_exists = all(self.map.get_tile(x, y) and self.map.get_tile(x, y).land_type not in c.NAVAL_TERRAIN for x, y in path)

                    if land_path_exists:
                        final_dest = path[-1]
                        for pos in reversed(path):
                            if pos in reachable_tiles and pos not in projected_positions:
                                final_dest = pos
                                break
                        if (unit.grid_x, unit.grid_y) != final_dest:
                            projected_positions.add(final_dest)
                            yield EntityAction(Arrow(unit.grid_x, unit.grid_y, final_dest[0], final_dest[1], 'Move', unit.nation_id), is_creation=True)
                    else:
                        transport_plan = self._plan_naval_transport(unit, target_pos, available_transports, projected_positions)
                        if transport_plan:
                            for action, new_pos in transport_plan:
                                projected_positions.add(new_pos)
                                yield action

    def _execute_tactical_strategy(self, ai_nation_id, combat_units, threats, available_transports, projected_positions):
        allies = self.get_allied_nations(ai_nation_id)
        enemy_units = [u for u in self.units if u.nation_id not in allies]

        for unit in combat_units:
            if not enemy_units: break
            enemy_units.sort(key=lambda e: abs(unit.grid_x - e.grid_x) + abs(unit.grid_y - e.grid_y))
            target = enemy_units[0]
            
            reachable, _ = self.calculate_reachable_tiles(unit)
            best_attack_pos = None
            if self.is_valid_action_target(unit, target.grid_x, target.grid_y, 'Attack'):
                 best_attack_pos = (unit.grid_x, unit.grid_y)
            else:
                for pos in sorted(list(reachable), key=lambda p: abs(p[0]-target.grid_x) + abs(p[1]-target.grid_y)):
                    if pos in projected_positions: continue
                    if self.is_valid_action_target(unit, target.grid_x, target.grid_y, 'Attack', from_pos=pos):
                        best_attack_pos = pos
                        break
            
            if best_attack_pos:
                actions = []
                if best_attack_pos != (unit.grid_x, unit.grid_y):
                     actions.append(EntityAction(Arrow(unit.grid_x, unit.grid_y, best_attack_pos[0], best_attack_pos[1], 'Move', unit.nation_id), is_creation=True))
                actions.append(EntityAction(Arrow(best_attack_pos[0], best_attack_pos[1], target.grid_x, target.grid_y, 'Attack', unit.nation_id), is_creation=True))
                
                projected_positions.add(best_attack_pos)
                yield CompositeAction(actions)

    def _execute_defensive_strategy(self, ai_nation_id, combat_units, threats, available_transports, projected_positions):
        if not threats['locations']: return
        
        sorted_threats = sorted(threats['locations'].items(), key=lambda item: item[1], reverse=True)

        for unit in combat_units:
            if not sorted_threats: break
            
            target_pos = min(sorted_threats, key=lambda t: abs(unit.grid_x - t[0][0]) + abs(unit.grid_y - t[0][1]))[0]
            
            path = self._find_shortest_path(unit, (unit.grid_x, unit.grid_y), target_pos, occupied_tiles=projected_positions)
            if path:
                reachable_tiles, _ = self.calculate_reachable_tiles(unit)
                final_dest = path[0]
                for pos in reversed(path):
                    if pos in reachable_tiles and pos not in projected_positions:
                        final_dest = pos
                        break
                if (unit.grid_x, unit.grid_y) != final_dest:
                    projected_positions.add(final_dest)
                    yield EntityAction(Arrow(unit.grid_x, unit.grid_y, final_dest[0], final_dest[1], 'Move', unit.nation_id), is_creation=True)
                    
    def _execute_naval_strategy(self, ai_nation_id, naval_units, projected_positions):
        allies = self.get_allied_nations(ai_nation_id)
        combat_ships = [u for u in naval_units if not u.weight_capacity]
        if not combat_ships: return

        enemy_ships = [u for u in self.units if u.unit_class == 'naval' and u.nation_id not in allies]
        
        coastal_combat_zones = []
        for arrow in self.arrows:
            if arrow.order_type in ['Attack', 'Support Attack']:
                attacker = self.find_entity_at(arrow.start_gx, arrow.start_gy, None, ignore_arrows=True)
                defender = self.find_entity_at(arrow.end_gx, arrow.end_gy, None, ignore_arrows=True)
                if attacker and defender and (attacker.nation_id in allies or defender.nation_id in allies):
                    for combatant in [attacker, defender]:
                        for dx, dy in [(0,1),(0,-1),(1,0),(-1,0)]:
                            tile = self.map.get_tile(combatant.grid_x + dx, combatant.grid_y + dy)
                            if tile and tile.land_type in c.NAVAL_TERRAIN:
                                coastal_combat_zones.append((combatant.grid_x, combatant.grid_y))
                                break

        for ship in combat_ships:
            target_pos = None
            order_type = 'Move'

            if enemy_ships:
                enemy_ships.sort(key=lambda e: abs(ship.grid_x - e.grid_x) + abs(ship.grid_y - e.grid_y))
                target = enemy_ships[0]
                reachable, _ = self.calculate_reachable_tiles(ship)
                attack_pos = self._find_best_attack_pos(ship, target, reachable, projected_positions)
                if attack_pos:
                    if attack_pos != (ship.grid_x, ship.grid_y):
                        yield EntityAction(Arrow(ship.grid_x, ship.grid_y, attack_pos[0], attack_pos[1], 'Move', ship.nation_id), is_creation=True)
                    yield EntityAction(Arrow(attack_pos[0], attack_pos[1], target.grid_x, target.grid_y, 'Attack', ship.nation_id), is_creation=True)
                    projected_positions.add(attack_pos)
                    continue

            if coastal_combat_zones:
                 coastal_combat_zones.sort(key=lambda z: abs(ship.grid_x - z[0]) + abs(ship.grid_y - z[1]))
                 target_pos = coastal_combat_zones[0]

            if target_pos:
                path = self._find_shortest_path(ship, (ship.grid_x, ship.grid_y), target_pos, occupied_tiles=projected_positions)
                if path:
                    reachable_tiles, _ = self.calculate_reachable_tiles(ship)
                    final_dest = path[0]
                    for pos in reversed(path):
                        if pos in reachable_tiles and pos not in projected_positions:
                            final_dest = pos
                            break
                    if (ship.grid_x, ship.grid_y) != final_dest:
                        projected_positions.add(final_dest)
                        yield EntityAction(Arrow(ship.grid_x, ship.grid_y, final_dest[0], final_dest[1], order_type, ship.nation_id), is_creation=True)

        
    def _execute_expansion_strategy(self, ai_nation_id, expansion_units, available_transports, projected_positions, target_enemy=False):
        allies = self.get_allied_nations(ai_nation_id)
        
        target_features = []
        feature_priority = {'city': 3, 'a_city': 3, 'village': 2, 'a_village': 2, 'quarry': 1}

        for feature in self.features:
            tile = self.map.get_tile(feature.grid_x, feature.grid_y)
            if not tile: continue
            
            is_unclaimed = tile.nation_owner_id is None or tile.nation_owner_id not in allies
            is_enemy_owned = tile.nation_owner_id not in allies and tile.nation_owner_id is not None
            
            if (target_enemy and is_enemy_owned) or (not target_enemy and is_unclaimed):
                priority = feature_priority.get(feature.feature_type, 0)
                if priority > 0:
                    target_features.append({'feature': feature, 'priority': priority})
        
        target_features.sort(key=lambda x: x['priority'], reverse=True)
        assigned_features = set()

        for unit in expansion_units:
            if not target_features: break
            
            target_features.sort(key=lambda x: abs(unit.grid_x - x['feature'].grid_x) + abs(unit.grid_y - x['feature'].grid_y))

            target_data = next((f for f in target_features if f['feature'].id not in assigned_features), None)
            if not target_data: continue

            target_pos = (target_data['feature'].grid_x, target_data['feature'].grid_y)
            assigned_features.add(target_data['feature'].id)

            path = self._find_shortest_path(unit, (unit.grid_x, unit.grid_y), target_pos, occupied_tiles=projected_positions)
            if not path: continue

            reachable, _ = self.calculate_reachable_tiles(unit)
            land_path_exists = all(self.map.get_tile(x, y) and self.map.get_tile(x, y).land_type not in c.NAVAL_TERRAIN for x, y in path)

            if land_path_exists:
                final_dest = path[0]
                for pos in reversed(path):
                    if pos in reachable and pos not in projected_positions:
                        final_dest = pos
                        break
                if (unit.grid_x, unit.grid_y) != final_dest:
                    projected_positions.add(final_dest)
                    yield EntityAction(Arrow(unit.grid_x, unit.grid_y, final_dest[0], final_dest[1], 'Move', unit.nation_id), is_creation=True)
            else:
                transport_plan = self._plan_naval_transport(unit, target_pos, available_transports, projected_positions)
                if transport_plan:
                    for action, new_pos in transport_plan:
                        projected_positions.add(new_pos)
                        yield action
                        
    def draw_territory_highlight(self, screen):
        if not self.hovered_leaderboard_nation_id or self.map.camera.zoom < 0.25:
            return

        nation_data = self.nations.get(self.hovered_leaderboard_nation_id)
        if not nation_data:
            return

        highlight_color = (*nation_data['color'], 80)

        view_start_gx, view_start_gy = self.map.camera.screen_to_grid(0, 0)
        view_end_gx, view_end_gy = self.map.camera.screen_to_grid(c.SCREEN_WIDTH, c.SCREEN_HEIGHT)

        scaled_tile_size = c.TILE_SIZE * self.map.camera.zoom
        if scaled_tile_size < 1: return

        highlight_surface = pygame.Surface((scaled_tile_size, scaled_tile_size), pygame.SRCALPHA)
        highlight_surface.fill(highlight_color)

        for x in range(max(0, view_start_gx), min(self.map.width, view_end_gx + 2)):
            for y in range(max(0, view_start_gy), min(self.map.height, view_end_gy + 2)):
                tile = self.map.get_tile(x, y)
                if tile and tile.nation_owner_id == self.hovered_leaderboard_nation_id:
                    screen_x, screen_y = self.map.camera.world_to_screen(x * c.TILE_SIZE, y * c.TILE_SIZE)
                    screen.blit(highlight_surface, (screen_x, screen_y))


    def _plan_naval_transport(self, land_unit, destination_pos, transports, projected_positions):
        if not transports: return []
        
        transports.sort(key=lambda t: abs(land_unit.grid_x - t.grid_x) + abs(land_unit.grid_y - t.grid_y))
        
        best_transport = next((t for t in transports if t.can_carry(land_unit) and (t.grid_x, t.grid_y) not in projected_positions), None)
        if not best_transport: return []

        embark_pos = self._find_closest_passable_tile(land_unit, land_unit.grid_x, land_unit.grid_y, naval_ok=False)
        disembark_pos = self._find_closest_passable_tile(land_unit, destination_pos[0], destination_pos[1], naval_ok=False)
        
        if not embark_pos or not disembark_pos: return []

        plan = []
        
        reachable_land, _ = self.calculate_reachable_tiles(land_unit)
        path_to_coast = self._find_shortest_path(land_unit, (land_unit.grid_x, land_unit.grid_y), embark_pos, occupied_tiles=projected_positions)
        if path_to_coast:
            dest = path_to_coast[0]
            for pos in reversed(path_to_coast):
                if pos in reachable_land and pos not in projected_positions:
                    dest = pos
                    break
            if (land_unit.grid_x, land_unit.grid_y) != dest:
                plan.append((EntityAction(Arrow(land_unit.grid_x, land_unit.grid_y, dest[0], dest[1], 'Move', land_unit.nation_id, land_unit.id), is_creation=True), dest))

        reachable_naval, _ = self.calculate_reachable_tiles(best_transport)
        path_to_embark = self._find_shortest_path(best_transport, (best_transport.grid_x, best_transport.grid_y), embark_pos, occupied_tiles=projected_positions)
        if path_to_embark:
            dest = path_to_embark[0]
            for pos in reversed(path_to_embark):
                if pos in reachable_naval and pos not in projected_positions:
                    dest = pos
                    break
            if (best_transport.grid_x, best_transport.grid_y) != dest:
                 plan.append((EntityAction(Arrow(best_transport.grid_x, best_transport.grid_y, dest[0], dest[1], 'Move', best_transport.nation_id, best_transport.id), is_creation=True), dest))
        
        return plan
    

    def _find_best_attack_pos(self, unit, target, reachable_tiles, projected_positions):
        best_pos = None
        if self.is_valid_action_target(unit, target.grid_x, target.grid_y, 'Attack'):
             best_pos = (unit.grid_x, unit.grid_y)
        else:
            for pos in sorted(list(reachable_tiles), key=lambda p: abs(p[0]-target.grid_x) + abs(p[1]-target.grid_y)):
                if pos in projected_positions: continue
                if self.is_valid_action_target(unit, target.grid_x, target.grid_y, 'Attack', from_pos=pos):
                    best_pos = pos
                    break
        return best_pos

    def _find_closest_passable_tile(self, unit, start_x, start_y, naval_ok):
        q = collections.deque([(start_x, start_y, 0)])
        visited = {(start_x, start_y)}
        max_dist = 50 

        while q:
            x, y, dist = q.popleft()
            if dist > max_dist: continue

            tile = self.map.get_tile(x, y)
            if tile:
                is_land = tile.land_type not in c.NAVAL_TERRAIN
                if (naval_ok and not is_land) or (not naval_ok and is_land):
                    return (x, y)

            for dx, dy in [(0,1), (0,-1), (1,0), (-1,0)]:
                nx, ny = x + dx, y + dy
                if (nx, ny) not in visited:
                    visited.add((nx, ny))
                    q.append((nx, ny, dist + 1))
        return None

    def draw_territory_names(self, screen):
        if self.map.camera.zoom < 0.4: return
        
        view_start_gx, view_start_gy = self.map.camera.screen_to_grid(0,0)
        view_end_gx, view_end_gy = self.map.camera.screen_to_grid(c.SCREEN_WIDTH, c.SCREEN_HEIGHT)

        for nid, cached_comps in self.cached_territory_data.items():
            for comp_data in cached_comps:
                if not (view_start_gx <= comp_data['avg_gx'] <= view_end_gx + 1 and view_start_gy <= comp_data['avg_gy'] <= view_end_gy + 1): continue
                
                tile = self.map.get_tile(int(comp_data['avg_gx']), int(comp_data['avg_gy']))
                if tile and tile.visibility_state == 2 and self.main_app.user_mode != 'editor': continue

                min_x = min(t[0] for t in comp_data['comp']); max_x = max(t[0] for t in comp_data['comp'])
                min_y = min(t[1] for t in comp_data['comp']); max_y = max(t[1] for t in comp_data['comp'])
                longest_dim = math.hypot((max_x - min_x) * c.TILE_SIZE, (max_y - min_y) * c.TILE_SIZE) * self.map.camera.zoom
                font_size = max(8, min(128, int(longest_dim / (len(comp_data['name']) * 0.7 + 1))))
                if font_size < 12: continue

                cache_key = (comp_data['name'], font_size, int(comp_data['angle']), tuple(comp_data['color']))
                if cache_key in self.territory_name_cache:
                    text_surf = self.territory_name_cache[cache_key]
                else:
                    dynamic_font = c.get_font(c.FONT_PATH, font_size)
                    if not dynamic_font: continue
                    text_surf = create_text_with_border(comp_data['name'].upper(), dynamic_font, c.COLOR_WHITE, comp_data['color'], angle=comp_data['angle'])
                    self.territory_name_cache[cache_key] = text_surf

                center_wx = comp_data['avg_gx'] * c.TILE_SIZE + c.TILE_SIZE/2; center_wy = comp_data['avg_gy'] * c.TILE_SIZE + c.TILE_SIZE/2
                sx, sy = self.map.camera.world_to_screen(center_wx, center_wy)
                screen.blit(text_surf, text_surf.get_rect(center=(sx, sy)))

    def draw_coordinate_display(self, screen):
        mouse_pos = pygame.mouse.get_pos()
        if not self.ui_manager.is_mouse_over_ui(mouse_pos):
            world_x, world_y = self.map.camera.screen_to_world(*mouse_pos)
            gx, gy = self.map.camera.world_to_grid(world_x, world_y)
            if 0 <= gx < self.map.width and 0 <= gy < self.map.height:
                coord_text = f"{get_excel_column(gx)}{gy + 1}"
                text_surf = self.coord_font.render(coord_text, True, c.UI_FONT_COLOR)
                
                minimap_hub_rect = self.ui_manager.game_app.minimap.parent.get_absolute_rect()
                text_rect = text_surf.get_rect(midbottom=(minimap_hub_rect.centerx, minimap_hub_rect.top - 5))
                screen.blit(text_surf, text_rect)

    def draw_fps_counter(self, screen):
        fps = f"FPS: {self.main_app.clock.get_fps():.1f}"
        fps_surf = self.fps_font.render(fps, True, c.COLOR_YELLOW)
        fps_rect = fps_surf.get_rect(bottomright=(c.SCREEN_WIDTH - 10, c.SCREEN_HEIGHT - 5))
        screen.blit(fps_surf, fps_rect)

    def get_arrow_chain_for_unit(self, unit):
        if not unit: return []
        
        unit_specific_arrows = [a for a in self.arrows if a.unit_id == unit.id]
        
        if unit_specific_arrows:
            chain = []
            visited_arrow_ids = set()
            
            arrow_starts = {(a.start_gx, a.start_gy): a for a in unit_specific_arrows}
            
            current_arrow = arrow_starts.get((unit.grid_x, unit.grid_y))

            while current_arrow:
                if current_arrow.id in visited_arrow_ids:
                    print(f"ERROR: Cycle detected in unit-specific arrow chain for unit {unit.id}.")
                    return chain

                visited_arrow_ids.add(current_arrow.id)
                chain.append(current_arrow)
                
                next_pos = (current_arrow.end_gx, current_arrow.end_gy)
                current_arrow = arrow_starts.get(next_pos)
            
            return chain

        chain = []
        visited_arrow_ids = set()
        
        legacy_arrows = [a for a in self.arrows if a.nation_id == unit.nation_id and a.unit_id is None]
        arrow_starts = {(a.start_gx, a.start_gy): a for a in legacy_arrows}
        
        current_arrow = arrow_starts.get((unit.grid_x, unit.grid_y))
        
        while current_arrow:
            if current_arrow.id in visited_arrow_ids:
                print(f"ERROR: Cycle detected in legacy arrow chain for unit {unit.id}.")
                return chain

            visited_arrow_ids.add(current_arrow.id)
            chain.append(current_arrow)
            
            next_pos = (current_arrow.end_gx, current_arrow.end_gy)
            current_arrow = arrow_starts.get(next_pos)
        
        return chain


    def calculate_chain_cost(self, unit, chain):
        if not unit: return 0
        total_cost = 0
        for arrow in chain:
            if arrow.order_type == 'Move':
                path = self._find_shortest_path(unit, (arrow.start_gx, arrow.start_gy), (arrow.end_gx, arrow.end_gy))
                if path:
                    total_cost += len(path) - 1
            elif arrow.order_type == 'Load/Unload':
                transporter = self.find_entity_at(arrow.end_gx, arrow.end_gy, None, ignore_arrows=True)
                if isinstance(transporter, Unit) and transporter.weight_capacity:
                    total_cost += c.LOAD_COSTS.get(transporter.unit_type, 1.0)
        return total_cost

    def resize_map(self, new_width, new_height):
        current_map = self.map
        old_grid = current_map.grid
        old_width = current_map.width
        old_height = current_map.height

        new_grid = [[Tile(x, y) for y in range(new_height)] for x in range(new_width)]

        for x in range(min(old_width, new_width)):
            for y in range(min(old_height, new_height)):
                new_grid[x][y] = old_grid[x][y]

        current_map.grid = new_grid
        current_map.width = new_width
        current_map.height = new_height

        self.units = [u for u in self.units if u.grid_x < new_width and u.grid_y < new_height]
        self.features = [f for f in self.features if f.grid_x < new_width and f.grid_y < new_height]
        self.map_texts = [t for t in self.map_texts if t.grid_x < new_width and t.grid_y < new_height]
        self.arrows = [a for a in self.arrows if
                       a.start_gx < new_width and a.start_gy < new_height and
                       a.end_gx < new_width and a.end_gy < new_height]
        
        self.map.set_dirty()
        self.minimap.set_dirty()
        self.fow_dirty = True
        print(f"Resized layer '{self.current_layer_key}' to {new_width}x{new_height}")
    
    def commence_map_shift(self, dx, dy):
        self.do_action(ShiftMapAction(dx, dy, self.current_layer_key))
    
    def shift_map_contents(self, dx, dy, layer_key):
        layer = self.layers[layer_key]
        current_map = layer['map']
        old_grid = current_map.grid
        new_grid = [[Tile(x, y) for y in range(current_map.height)] for x in range(current_map.width)]
        
        for x in range(current_map.width):
            for y in range(current_map.height):
                old_x, old_y = x - dx, y - dy
                if 0 <= old_x < current_map.width and 0 <= old_y < current_map.height:
                    tile = old_grid[old_x][old_y]
                    tile.grid_x, tile.grid_y = x, y
                    new_grid[x][y] = tile
        
        current_map.grid = new_grid

        for entity_list in [layer['units'], layer['features'], layer['straits'], layer['blockades'], layer['map_texts']]:
            for entity in entity_list:
                if isinstance(entity, (Strait, Blockade)):
                    entity.start_gx += dx
                    entity.start_gy += dy
                    entity.end_gx += dx
                    entity.end_gy += dy
                else:
                    entity.grid_x += dx
                    entity.grid_y += dy
        
        for arrow in layer['arrows']:
            arrow.start_gx += dx
            arrow.start_gy += dy
            arrow.end_gx += dx
            arrow.end_gy += dy

        self.minimap.set_dirty()
        self.territory_data_dirty = True
        self.fow_dirty = True
        
    def auto_balance_territories(self):
        """
        Automatically distributes land among non-special nations to give each
        a starting manpower of up to 6, ensuring territories are contiguous.
        """
        MANPOWER_TARGET = 6
        layer = self.layers[self.current_layer_key]
        current_map = layer['map']

        nations_to_balance = [nid for nid, data in self.nations.items() if not data.get('is_special', False)]
        if not nations_to_balance:
            print("Auto-Balance: No non-special nations to balance.")
            return

        valuable_tiles = []
        feature_manpower = {'city': 2, 'a_city': 2, 'village': 1, 'a_village': 1, 'oil_rig': 1}
        for feature in layer['features']:
            if feature.feature_type in feature_manpower:
                tile = current_map.get_tile(feature.grid_x, feature.grid_y)
                if tile:
                    valuable_tiles.append({'tile': tile, 'manpower': feature_manpower[feature.feature_type]})
        
        random.shuffle(valuable_tiles)

        final_ownership = {}
        q = collections.deque()
        nation_manpower = collections.defaultdict(int)
        
        available_tiles = list(valuable_tiles)

        for nation_id in nations_to_balance:
            while nation_manpower[nation_id] < MANPOWER_TARGET:
                best_tile_to_add = None
                # Find the best fitting tile from the remaining pool
                for tile_data in available_tiles:
                    # Check if adding this tile would NOT exceed the target
                    if (nation_manpower[nation_id] + tile_data['manpower']) <= MANPOWER_TARGET:
                        best_tile_to_add = tile_data
                        break  # Found a suitable tile
                
                if best_tile_to_add:
                    tile = best_tile_to_add['tile']
                    pos = (tile.grid_x, tile.grid_y)
                    
                    final_ownership[pos] = nation_id
                    q.append((pos, nation_id))
                    nation_manpower[nation_id] += best_tile_to_add['manpower']
                    available_tiles.remove(best_tile_to_add)
                else:
                    # No suitable tile found for this nation, move to the next one
                    break
        
        for nid, mp in nation_manpower.items():
            print(f"Auto-Balance: Nation '{self.nations[nid]['name']}' assigned {mp} manpower.")

        # Expand territories via BFS only on land tiles
        while q:
            (cx, cy), owner_id = q.popleft()
            for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                nx, ny = cx + dx, cy + dy
                pos = (nx, ny)
                if not (0 <= nx < current_map.width and 0 <= ny < current_map.height) or pos in final_ownership:
                    continue

                neighbor_tile = current_map.get_tile(nx, ny)
                if neighbor_tile and neighbor_tile.land_type not in c.NAVAL_TERRAIN and neighbor_tile.land_type != 'Border':
                    final_ownership[pos] = owner_id
                    q.append((pos, owner_id))
        
        # Create a single PaintAction with all territory changes
        all_paint_data = []
        for x in range(current_map.width):
            for y in range(current_map.height):
                tile = current_map.get_tile(x, y)
                if not tile: continue
                
                old_owner = tile.nation_owner_id
                new_owner = final_ownership.get((x, y))
                
                if old_owner != new_owner:
                    all_paint_data.append((tile, old_owner, new_owner))
        
        if all_paint_data:
            self.do_action(actions.PaintAction(all_paint_data, 'nation_owner_id'))
            print("Auto-Balance: Territory distribution complete.")
        else:
            print("Auto-Balance: No changes were necessary.")
    
    def commence_map_rotation(self, degrees):
        self.do_action(RotateMapAction(degrees, self.current_layer_key))

    def rotate_map_contents(self, degrees, layer_key):
        layer = self.layers[layer_key]
        current_map = layer['map']
        w, h = current_map.width, current_map.height

        angle = (degrees % 360 + 360) % 360

        if angle == 0: return
        if angle not in [90, 180, 270]: return

        if angle == 90: # Clockwise 90
            new_w, new_h = h, w
            coord_transform = lambda x, y: (h - 1 - y, x)
        elif angle == 180:
            new_w, new_h = w, h
            coord_transform = lambda x, y: (w - 1 - x, h - 1 - y)
        elif angle == 270: # Clockwise 270 / Counter-clockwise 90
            new_w, new_h = h, w
            coord_transform = lambda x, y: (y, w - 1 - x)

        new_grid = [[Tile(x, y) for y in range(new_h)] for x in range(new_w)]
        for x in range(w):
            for y in range(h):
                nx, ny = coord_transform(x, y)
                new_grid[nx][ny] = current_map.grid[x][y]

        current_map.grid = new_grid
        current_map.width = new_w
        current_map.height = new_h

        all_entities = layer['units'] + layer['features'] + layer['map_texts']
        for entity in all_entities:
            entity.grid_x, entity.grid_y = coord_transform(entity.grid_x, entity.grid_y)
            if isinstance(entity, Unit):
                entity.rotation = (entity.rotation + degrees) % 360

        for link in layer['arrows'] + layer['straits'] + layer['blockades']:
            link.start_gx, link.start_gy = coord_transform(link.start_gx, link.start_gy)
            link.end_gx, link.end_gy = coord_transform(link.end_gx, link.end_gy)

        self.minimap.set_dirty()
        self.territory_data_dirty = True
        self.fow_dirty = True

    def _get_load_unload_actions(self, processed_arrow_ids):
        load_unload_arrows = [a for a in self.arrows if a.order_type == 'Load/Unload' and a.id not in processed_arrow_ids]
        actions = []
        arrows_to_delete = []
        
        transporters_with_unloads = collections.defaultdict(list)
        for arrow in load_unload_arrows:
            transporter = self.find_entity_at(arrow.start_gx, arrow.start_gy, None, ignore_arrows=True)
            if isinstance(transporter, Unit) and transporter.carried_units:
                transporters_with_unloads[transporter.id].append(arrow)

        for transporter_id, arrows in transporters_with_unloads.items():
            transporter = next((u for u in self.units if u.id == transporter_id), None)
            if not transporter or not transporter.carried_units: continue
            
            units_available_to_unload = list(transporter.carried_units)
            for arrow in arrows:
                if not units_available_to_unload: break
                end_pos = (arrow.end_gx, arrow.end_gy)
                entity_at_end = self.find_entity_at(end_pos[0], end_pos[1], None, ignore_arrows=True)
                
                if not isinstance(entity_at_end, Unit):
                    tile = self.map.get_tile(end_pos[0], end_pos[1])
                    if tile:
                        unit_to_unload = units_available_to_unload.pop(0)
                        
                        is_passable = True
                        if unit_to_unload.unit_class == 'naval' and tile.land_type not in c.NAVAL_TERRAIN: is_passable = False
                        if unit_to_unload.unit_class == 'land' and tile.land_type in c.NAVAL_TERRAIN: is_passable = False
                        
                        if is_passable:
                            actions.append(MoveOrCarryAction(unit_to_unload, (transporter.grid_x, transporter.grid_y), end_pos, transporter, None))
                            arrows_to_delete.append(arrow)
                            
                            has_feature = any(isinstance(f, MapFeature) for f in self.features if f.grid_x == end_pos[0] and f.grid_y == end_pos[1])
                            if not has_feature:
                                actions.append(PaintAction([(tile, tile.nation_owner_id, unit_to_unload.nation_id)], 'nation_owner_id'))

        currently_processed_ids = {a.id for a in arrows_to_delete}
        
        for arrow in load_unload_arrows:
            if arrow.id in currently_processed_ids: continue
            
            unit_to_load = self.find_entity_at(arrow.start_gx, arrow.start_gy, None, ignore_arrows=True)
            transporter = self.find_entity_at(arrow.end_gx, arrow.end_gy, None, ignore_arrows=True)
            if isinstance(unit_to_load, Unit) and isinstance(transporter, Unit) and transporter.can_carry(unit_to_load):
                actions.append(MoveOrCarryAction(unit_to_load, (arrow.start_gx, arrow.start_gy), (arrow.end_gx, arrow.end_gy), None, transporter))
                arrows_to_delete.append(arrow)

        if actions:
            for arrow in arrows_to_delete:
                actions.append(EntityAction(arrow, is_creation=False))
        
        return actions, {a.id for a in arrows_to_delete}

    def _find_shortest_path(self, unit, start, end, occupied_tiles=None):
        if occupied_tiles is None:
            occupied_tiles = set()
        def heuristic(a, b):
            return abs(a[0] - b[0]) + abs(a[1] - b[1])

        open_set = [(0, start)]
        came_from = {}
        g_score = {start: 0}

        grid_data = unit.properties['grid']
        rotated_grid = rotate_grid(grid_data, unit.rotation)
        possible_grid_moves = []
        for r in range(5):
            for col in range(5):
                if rotated_grid[r][col] in [1, 2, 3]:
                    dx, dy = col - 2, r - 2
                    if dx == 0 and dy == 0: continue
                    possible_grid_moves.append((dx, dy))

        while open_set:
            _, current = heapq.heappop(open_set)

            if current == end:
                path = []
                while current in came_from:
                    path.append(current)
                    current = came_from[current]
                path.append(start)
                return path[::-1]

            potential_steps = []
            for dx, dy in possible_grid_moves:
                neighbor_pos = (current[0] + dx, current[1] + dy)
                potential_steps.append((neighbor_pos, 1))

            if unit.unit_class != 'air':
                for strait in self.straits:
                    if (strait.start_gx, strait.start_gy) == current:
                        potential_steps.append(((strait.end_gx, strait.end_gy), 1))
                    elif (strait.end_gx, strait.end_gy) == current:
                        potential_steps.append(((strait.start_gx, strait.start_gy), 1))

            for neighbor, move_cost in potential_steps:
                if not self.map.get_tile(neighbor[0], neighbor[1]):
                    continue
                
                if neighbor in occupied_tiles and neighbor != end:
                    continue
                
                tentative_g_score = g_score.get(current, float('inf')) + move_cost

                if tentative_g_score < g_score.get(neighbor, float('inf')):
                    tile = self.map.get_tile(neighbor[0], neighbor[1])
                    if self.main_app.user_mode == 'player' and tile and tile.visibility_state == 2:
                        continue
                    if not tile or tile.land_type == 'Border':
                        continue
                    
                    is_strait_move = any(s for s in self.straits if {current, neighbor} == {(s.start_gx, s.start_gy), (s.end_gx, s.end_gy)})
                    
                    is_passable = True
                    if unit.unit_class != 'air':
                        if tile.land_type == 'Canal':
                            is_passable = True
                        elif unit.unit_class == 'naval':
                            is_passable = tile.land_type in c.NAVAL_TERRAIN or is_strait_move
                        elif unit.unit_class == 'land':
                            is_passable = tile.land_type not in c.NAVAL_TERRAIN or is_strait_move
                    
                    if not is_passable:
                        continue

                    is_blocked = any(b for b in self.blockades if {current, neighbor} == {(b.start_gx, b.start_gy), (b.end_gx, b.end_gy)})
                    if is_blocked:
                        continue

                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g_score
                    f_score = tentative_g_score + heuristic(neighbor, end)
                    heapq.heappush(open_set, (f_score, neighbor))
        return None
    
    def get_idle_units(self):
        if self.main_app.user_mode != 'player':
            return []
        
        player_nation_id = self.main_app.player_nation_id
        if not player_nation_id:
            return []
            
        idle = []
        for unit in self.units:
            if unit.nation_id == player_nation_id and unit.status == 'active':
                if not self.get_arrow_chain_for_unit(unit):
                    idle.append(unit)
        return idle

    def cycle_idle_unit(self):
        self.idle_units_list = self.get_idle_units()
        if not self.idle_units_list:
            return

        self.idle_unit_index = (self.idle_unit_index + 1) % len(self.idle_units_list)
        unit = self.idle_units_list[self.idle_unit_index]
        
        self.clear_selection()
        self.multi_selected_entities.append(unit)
        self.ui_manager.rebuild_selection_info_panel()
        
        world_x, world_y = self.map.camera.grid_to_world(unit.grid_x, unit.grid_y)
        self.map.camera.center_on(world_x, world_y)

    def set_unit_status(self, unit, status):
        if unit:
            self.do_action(PropertyChangeAction(unit, 'status', unit.status, status))
            self.clear_selection()

    def start_ai_for_nation(self, nation_id):
        if self.ai_is_thinking:
            print("AI is already thinking.")
            return

        difficulty_map = {'Easy': 5, 'Normal': 10, 'Hard': 20, 'Impossible': 30}
        
        ai_units = [u for u in self.units if u.nation_id == nation_id and not self.get_arrow_chain_for_unit(u)]
        if not ai_units:
            print(f"AI: No units to command for nation {nation_id}")
            return
            
        total_time_seconds = difficulty_map.get(self.selected_ai_difficulty, 10)
        self.ai_is_thinking = True
        self.ui_manager.rebuild_admin_panel()

        self.ai_pending_actions = self.run_ai_for_nation(nation_id)
        
        pygame.time.set_timer(self.AI_EVENT, int(total_time_seconds * 1000), loops=1)
        print(f"AI started for {nation_id} with {self.selected_ai_difficulty} difficulty. Thinking for {total_time_seconds}s.")

    def update_ai(self):
        if self.ai_generator is None:
            return

        if pygame.time.get_ticks() >= self.ai_next_action_time:
            try:
                action = next(self.ai_generator)
                if action:
                    self.do_action(action)
                self.ai_next_action_time = pygame.time.get_ticks() + self.ai_time_per_action
            except StopIteration:
                print("AI has finished generating orders.")
                self.ai_is_thinking = False
                self.ai_generator = None
                self.ui_manager.rebuild_admin_panel()
                
    
    def get_contributed_support(self, supporter_unit, order_type_filter):
        """Calculates the support value a single unit contributes to one arrow, considering splits."""
        if not isinstance(supporter_unit, Unit):
            return 0
        
        try:
            stats, _ = supporter_unit.get_effective_stats(self)
            sup_stat_str = str(stats.get('sup', '0'))

            num_outgoing_arrows_of_type = 0
            for arrow in self.arrows:
                if (arrow.start_gx, arrow.start_gy) == (supporter_unit.grid_x, supporter_unit.grid_y) and arrow.order_type == order_type_filter:
                    num_outgoing_arrows_of_type += 1
            
            if num_outgoing_arrows_of_type == 0: return 0

            total_sup_potential = 0
            max_targets = 1

            if 'x' in sup_stat_str:
                parts = sup_stat_str.split('x')
                max_targets = int(parts[0])
                total_sup_potential = int(parts[0]) * int(parts[1])
            else:
                total_sup_potential = int(sup_stat_str)

            if num_outgoing_arrows_of_type > max_targets:
                return 0

            return total_sup_potential / num_outgoing_arrows_of_type

        except (ValueError, TypeError, IndexError):
            return 0
        
    def get_defense_power(self, defender_unit):
        try:
            defense_power = int(defender_unit.get_effective_stats(self)[0].get('str', 0))
        except (ValueError, TypeError):
            defense_power = 0
        
        support_power = 0
        for arrow in self.arrows:
            if arrow.order_type == 'Support Defense' and (arrow.end_gx, arrow.end_gy) == (defender_unit.grid_x, defender_unit.grid_y):
                supporter = self.find_entity_at(arrow.start_gx, arrow.start_gy, None, ignore_arrows=True)
                allies = self.get_allied_nations(defender_unit.nation_id)
                if isinstance(supporter, Unit) and supporter.nation_id in allies:
                    support_power += self.get_contributed_support(supporter, 'Support Defense')
        return defense_power, int(round(support_power))
    
    def get_attack_power(self, involved_attackers, target_pos):
        if not involved_attackers:
            return 0, 0

        # Find the single unit with the highest strength output from all involved attackers
        primary_attacker = max(
            involved_attackers, 
            key=lambda u: int(u.get_effective_stats(self)[0].get('str', 0)), 
            default=None
        )
        
        attack_power = 0
        if primary_attacker:
            try:
                attack_power = int(primary_attacker.get_effective_stats(self)[0].get('str', 0))
            except (ValueError, TypeError):
                pass
        
        support_power = 0
        for unit in involved_attackers:
            # The primary attacker does not contribute its SUP to its own attack
            if unit.id == (primary_attacker.id if primary_attacker else None):
                continue

            # Find the arrow from this specific unit to the target to determine its order type
            order_type = None
            for arrow in self.arrows:
                unit_pos = self.get_unit_projected_pos(unit)
                if (arrow.start_gx, arrow.start_gy) == unit_pos and (arrow.end_gx, arrow.end_gy) == target_pos:
                    if arrow.order_type in ['Attack', 'Support Attack', 'Suppressive Fire']:
                        order_type = arrow.order_type
                        break
            
            if order_type:
                support_power += self.get_contributed_support(unit, order_type)

        return attack_power, int(round(support_power))

    def get_suppressive_fire_power(self, attackers):
        if not attackers:
            return 0, 0
        
        main_attacker = max(attackers, key=lambda u: int(u.get_effective_stats(self)[0].get('str', 0)))
        
        try:
            attack_power = int(main_attacker.get_effective_stats(self)[0].get('str', 0))
        except (ValueError, TypeError):
            attack_power = 0
        
        support_power = 0
        for supporter in attackers:
            if supporter.id != main_attacker.id:
                try:
                    sup_stat = supporter.get_effective_stats(self)[0].get('sup', '0')
                    support_power += int(str(sup_stat).split('x')[0])
                except (ValueError, TypeError):
                    pass
        
        return attack_power, support_power

    def get_suppressive_fire_power(self, attackers):
        if not attackers:
            return 0, 0
        
        main_attacker = max(attackers, key=lambda u: int(u.get_effective_stats(self)[0].get('dmg', 0)))
        
        try:
            attack_power = int(main_attacker.get_effective_stats(self)[0].get('dmg', 0))
        except (ValueError, TypeError):
            attack_power = 0
        
        support_power = 0
        for supporter in attackers:
            if supporter.id != main_attacker.id:
                try:
                    sup_stat = supporter.get_effective_stats(self)[0].get('sup', '0')
                    support_power += int(str(sup_stat).split('x')[0])
                except (ValueError, TypeError):
                    pass
        
        return attack_power, support_power
    
    def _get_projected_positions_for_prediction(self):
        projected_pos = {u.id: (u.grid_x, u.grid_y) for u in self.units}
        for unit in self.units:
            chain = self.get_arrow_chain_for_unit(unit)
            if chain:
                final_arrow = chain[-1]
                if final_arrow.order_type == 'Move' or final_arrow.order_type == 'Load/Unload':
                    projected_pos[unit.id] = (final_arrow.end_gx, final_arrow.end_gy)
        return projected_pos
    
    def get_unit_projected_pos(self, unit):
        """Calculates the final position of a unit after its move chain."""
        if not unit: return None
        chain = self.get_arrow_chain_for_unit(unit)
        if not chain or chain[-1].order_type not in ['Move', 'Load/Unload']:
            return (unit.grid_x, unit.grid_y)
        return (chain[-1].end_gx, chain[-1].end_gy)
    
    def is_unit_making_primary_attack(self, unit, target, preview_order_type):
        """Helper to determine if a unit is performing a primary attack."""
        if self.multi_selected_entities and unit.id == self.multi_selected_entities[0].id:
            return preview_order_type in ['Attack', 'Suppressive Fire']
        
        for arrow in self.arrows:
            if (arrow.start_gx, arrow.start_gy) == self.get_unit_projected_pos(unit) and \
               (arrow.end_gx, arrow.end_gy) == (target.grid_x, target.grid_y):
                if arrow.order_type in ['Attack', 'Suppressive Fire']:
                    return True
        return False
    
    def _is_move_valid(self, unit, start_pos, end_pos):
        tile = self.map.get_tile(end_pos[0], end_pos[1])
        if not tile or tile.land_type == 'Border':
            return False

        is_blocked = any(b for b in self.blockades if {start_pos, end_pos} == {(b.start_gx, b.start_gy), (b.end_gx, b.end_gy)})
        if is_blocked:
            return False

        is_strait_move = any(s for s in self.straits if {start_pos, end_pos} == {(s.start_gx, s.start_gy), (s.end_gx, s.end_gy)})
        
        is_passable = True
        if unit.unit_class != 'air':
            if tile.land_type == 'Canal':
                is_passable = True
            elif unit.unit_class == 'naval':
                is_passable = tile.land_type in c.NAVAL_TERRAIN or is_strait_move
            elif unit.unit_class == 'land':
                is_passable = tile.land_type not in c.NAVAL_TERRAIN or is_strait_move
        
        return is_passable

    def update_battle_prediction(self, attacker_unit, defender_unit, order_type, pos):
        if not attacker_unit or not defender_unit:
            self.battle_prediction = None
            return

        allies = self.get_allied_nations(attacker_unit.nation_id)
        
        # Gather all attackers and supporters
        involved_attackers = {attacker_unit}
        for arrow in self.arrows:
            if (arrow.end_gx, arrow.end_gy) == (defender_unit.grid_x, defender_unit.grid_y):
                if arrow.order_type in ['Attack', 'Support Attack', 'Suppressive Fire']:
                    supporter = self.find_entity_at(arrow.start_gx, arrow.start_gy, None, ignore_arrows=True)
                    if isinstance(supporter, Unit) and supporter.nation_id in allies:
                        involved_attackers.add(supporter)
        
        # Calculate attacker's total power
        attack_str, attack_support = self.get_attack_power(involved_attackers, (defender_unit.grid_x, defender_unit.grid_y))
        total_attack_str = attack_str + attack_support
        
        # Calculate defender's total power
        defense_str, defense_support = self.get_defense_power(defender_unit)
        total_defense_str = defense_str + defense_support

        # Get armor values
        try:
            attacker_arm = int(attacker_unit.get_effective_stats(self)[0].get('arm', 0))
            defender_arm = int(defender_unit.get_effective_stats(self)[0].get('arm', 0))
        except (ValueError, TypeError):
            attacker_arm, defender_arm = 0, 0

        # Apply new combat formula
        attacker_final_power = max(0, total_attack_str - defender_arm)
        defender_final_power = max(0, total_defense_str - attacker_arm)

        self.battle_prediction = {
            'attack': f"{total_attack_str} - {defender_arm} = {attacker_final_power}",
            'defense': f"{total_defense_str} - {attacker_arm} = {defender_final_power}",
            'pos': pos,
            'suppressed': False 
        }

    def next_turn(self):
        self.turn_counter += 1
        for layer in self.layers.values():
            for unit in layer['units']:
                if unit.status == 'skipped':
                    unit.status = 'active'
        self.ui_manager.build_ui()