import pygame
import config as c
import uuid
import math
from ui import UIElement, Panel, Button, InputField, TextLabel, ScrollablePanel, MultilineInputField, Checkbox, CategoryHeader
from save_load_manager import save_encyclopedia_data, save_tech_tree_template, load_tech_tree_template, load_login_data


class ImageElement(UIElement):
    def __init__(self, rect, image_surf, parent=None):
        super().__init__(rect, parent)
        self.image_surf = image_surf
    def draw(self, surface):
        if self.image_surf: surface.blit(self.image_surf, (0, 0))

class LoginScreen:
    def __init__(self, main_app):
        self.main_app = main_app
        self.username = ""
        self.active_input = None
        self.root = UIElement(pygame.Rect(0, 0, c.SCREEN_WIDTH, c.SCREEN_HEIGHT))
        self.panel = Panel(rect=(0,0, 400, 300), parent=self.root)
        self.panel.rect.center = (c.SCREEN_WIDTH/2, c.SCREEN_HEIGHT/2)
        self.panel.target_pos = self.panel.rect.topleft
        
        title_font = c.get_font(c.FONT_PATH, 32)
        self.title = TextLabel(rect=(0, 20, 400, 40), text="Enter Your Name", font=title_font, color=c.UI_FONT_COLOR, parent=self.panel, center_align=True)

        self.input_field = InputField(rect=(50, 80, 300, 40), initial_text="", on_change=self.on_text_change, parent=self.panel)
        
        saved_username = load_login_data()
        remember_me_default = False
        if saved_username:
            self.username = saved_username
            self.input_field.set_text(saved_username)
            remember_me_default = True
            
        self.remember_me_checkbox = Checkbox(rect=(50, 130, 300, 30), text="Remember Me", parent=self.panel, initial_state=remember_me_default)
        self.continue_button = Button(rect=(125, 180, 150, 40), text="Continue", on_click=self.on_continue, parent=self.panel)
        self.error_label = TextLabel(rect=(0, 230, 400, 30), text="", font=c.get_font(c.FONT_PATH, 16), color=c.COLOR_RED, parent=self.panel, center_align=True)

    def on_text_change(self, text): self.username = text
    
    def on_continue(self):
        from save_load_manager import save_login_data, delete_login_data
        
        username = self.username.strip()
        if not username:
            self.error_label.set_text("Name cannot be empty.")
            return

        game = self.main_app.game_instance
        is_admin = username == "Nuxia14"
        is_in_player_list = game and username in game.player_list

        if not is_admin and not is_in_player_list:
            self.error_label.set_text("Invalid username for this map.")
            return

        self.on_login(username)

    def on_login(self, username):
        from save_load_manager import save_login_data, delete_login_data
        if self.remember_me_checkbox.checked:
            save_login_data(username)
        else:
            delete_login_data()
        self.main_app.on_login_success(username)

    def set_active_input(self, input_field):
        if self.active_input and self.active_input != input_field:
            self.active_input.is_active = False
        self.active_input = input_field

    def set_tooltip(self, text, owner, pos):
        pass

    def clear_tooltip(self, owner=None):
        pass

    def handle_events(self, event):
        if event.type == pygame.QUIT:
            self.main_app.change_state('QUIT')
        
        self.root.handle_event(event, self)

        if event.type == pygame.KEYDOWN and self.input_field.is_active and event.key == pygame.K_RETURN:
            self.on_continue()

    def update(self): self.root.update()
    def draw(self, screen): screen.fill(c.UI_BACKGROUND_COLOR); self.root.draw(screen)

class EncyclopediaScreen:
    GRID_COLORS = { 0: (60, 60, 60), 1: c.COLOR_BLUE, 2: c.COLOR_GREEN, 3: c.COLOR_RED, 4: c.COLOR_YELLOW, 9:c.COLOR_BLACK}
    GRID_TOOLTIPS = {
        0: "Block: No movement or actions.", 1: "Move: Can move to this tile.",
        2: "Support: Can move to and support from this tile.", 3: "Attack: Can move, support, and attack from this tile.",
        4: "Support Only: Can support from this tile.", 9: "Unit Center"
    }
    
    def __init__(self, main_app):
        self.main_app = main_app
        self.view_mode = 'LIST'
        self.selected_unit_key = None
        self.is_editor = self.main_app.user_mode == 'editor'
        self.has_unsaved_changes = False
        self.category_states = {}
        self.save_feedback_timer = 0
        self.active_input = None
        self.grid_buttons = {}
        self.search_query = ""

        self.root = UIElement(pygame.Rect(0, 0, c.SCREEN_WIDTH, c.SCREEN_HEIGHT))

        self.header_panel = Panel(rect=(0, 0, c.SCREEN_WIDTH, 60), parent=self.root, color=None, border_width=0)
        
        main_content_y = self.header_panel.rect.bottom
        main_content_height = c.SCREEN_HEIGHT - main_content_y

        self.left_panel = Panel(rect=(30, main_content_y, 400, main_content_height), parent=self.root)
        
        self.right_panel_width = 400
        self.right_panel = Panel(rect=(c.SCREEN_WIDTH - self.right_panel_width - 30, main_content_y, self.right_panel_width, main_content_height), parent=self.root, color=None, border_width=0)

        middle_x = self.left_panel.rect.right + 20
        middle_width = self.right_panel.rect.left - middle_x - 20
        self.middle_panel = ScrollablePanel(rect=(middle_x, main_content_y, middle_width, main_content_height), parent=self.root)

        self.font_title = c.get_font(c.FONT_PATH, 48)
        self.font_header = c.get_font(c.FONT_PATH, 24)
        self.font_text = c.get_font(c.FONT_PATH, 18)
        self.font_stats = c.get_font(c.FONT_PATH, 22)
        self.tooltip_font = c.get_font(c.FONT_PATH, 14)
        self.tooltip_text, self.tooltip_surf, self.tooltip_timer, self.tooltip_owner, self.tooltip_pos = "", None, 0, None, (0,0)
        self.cached_tooltip_text = ""
        
        self.save_button = None
        
        self.rebuild_ui()

    def set_active_input(self, input_field):
        if self.active_input and self.active_input != input_field:
            self.active_input.is_active = False
        self.active_input = input_field

    def set_tooltip(self, text, owner, pos):
        if text: self.tooltip_text, self.tooltip_timer, self.tooltip_owner, self.tooltip_pos = text, pygame.time.get_ticks(), owner, pos
    def clear_tooltip(self, owner=None):
        if owner is None or self.tooltip_owner == owner: self.tooltip_text, self.tooltip_surf, self.tooltip_owner = "", None, None

    def rebuild_ui(self):
        for panel in [self.header_panel, self.left_panel, self.middle_panel, self.right_panel]:
            panel.children.clear()
        self.grid_buttons.clear()

        Button(rect=(c.SCREEN_WIDTH - 50, 10, 40, 40), text="X", on_click=lambda: self.main_app.change_state('GAME'), parent=self.header_panel)
        
        if self.view_mode == 'LIST':
            self.rebuild_list_view()
        elif self.view_mode == 'DETAIL' and self.selected_unit_key:
            self.rebuild_detail_view()
        else:
            self.middle_panel.rebuild_content([])

    def rebuild_list_view(self):
        TextLabel(rect=(30, 10, 500, 50), text="Unit Encyclopedia", font=self.font_title, color=c.UI_FONT_COLOR, parent=self.header_panel)

        elements = []
        
        if not hasattr(self, 'search_input'):
            self.search_input = InputField(rect=(10, 0, self.middle_panel.rect.width - 20, 30), initial_text=self.search_query, on_change=self.on_search_change)
        else:
            self.search_input.rect.width = self.middle_panel.rect.width - 20
        elements.append({'element': self.search_input, 'height': 40})

        query = self.search_query.lower().strip()

        for category, units in c.UNIT_TYPES.items():
            filtered_units = {
                key: data for key, data in units.items()
                if query in data.get('name', '').lower()
            }
            if not filtered_units:
                continue

            is_expanded = self.category_states.get(category, True)
            header = CategoryHeader(rect=(0, 0, self.middle_panel.rect.width, 30), text=category, on_toggle=lambda c=category: self.toggle_category(c), expanded=is_expanded)
            elements.append({'element': header, 'height': 35})

            if is_expanded:
                for key, data in filtered_units.items():
                    icon_surf, _ = c.get_scaled_asset(data['asset'], 30)
                    btn = Button(rect=(20, 0, self.middle_panel.rect.width - 40, 40), text=data['name'], icon=icon_surf, on_click=lambda k=key: self.show_detail_view(k))
                    elements.append({'element': btn, 'height': 45})
            elements.append({'element': UIElement(pygame.Rect(0,0,0,20)), 'height': 20})
        self.middle_panel.rebuild_content(elements)

    def rebuild_detail_view(self):
        unit_data = c.get_unit_data(self.selected_unit_key)
        if not unit_data: return

        Button(rect=(30, 20, 100, 40), text="Back", on_click=self.show_list_view, parent=self.header_panel)
        TextLabel(rect=(150, 20, self.header_panel.rect.width - 350, 50), text=unit_data['name'], font=self.font_title, color=c.UI_FONT_COLOR, parent=self.header_panel)
        if self.is_editor:
            self.save_button = Button(rect=(c.SCREEN_WIDTH - 160, 20, 100, 40), text="Save", on_click=self.save_changes, parent=self.header_panel)
            self.save_button.is_active = self.has_unsaved_changes
        else:
            self.save_button = None
        
        class ImageElement(UIElement):
            def __init__(self, rect, image_surf, parent=None):
                super().__init__(rect, parent)
                self.image_surf = image_surf
            def draw(self, surface):
                if self.image_surf: surface.blit(self.image_surf, (0, 0))
        
        unit_img = c.get_asset(unit_data['asset'])
        ImageElement(rect=(0, 20, unit_img.get_width(), unit_img.get_height()), image_surf=unit_img, parent=self.left_panel)
        
        self.rebuild_action_grid(unit_data)

        elements = []
        desc_header = TextLabel(rect=(10, 0, 500, 40), text="Description", font=self.font_header, color=c.UI_FONT_COLOR)
        elements.append({'element': desc_header, 'height': 40})
        
        desc_text = TextLabel(rect=(10, 0, self.middle_panel.rect.width - 20, 0), text=unit_data.get('desc', ''), font=self.font_text, color=c.UI_FONT_COLOR, wrap_width=self.middle_panel.rect.width - 20)
        elements.append({'element': desc_text, 'height': desc_text.rect.height + 40})
        
        stats_header = TextLabel(rect=(10, 0, 500, 40), text="Statistics", font=self.font_header, color=c.UI_FONT_COLOR)
        elements.append({'element': stats_header, 'height': 40})
        
        stat_order = ['str', 'arm', 'sup', 'spe']
        stat_icons = {
            'str': 'dmg_icon.png', 'arm': 'def_icon.png', 'sup': 'sup_icon.png',
            'spe': 'spe_icon.png', 'cost': 'cost_icon.png', 'weight': 'weight_icon.png'
        }
        
        all_stats_keys = list(unit_data.get('stats', {}).keys())
        other_stats_keys = sorted([k for k in all_stats_keys if k not in stat_order])
        all_props = stat_order + other_stats_keys

        for prop in ['weight', 'weight_capacity', 'max_units']:
            if prop in unit_data:
                all_props.append(prop)
        
        for prop_name in all_props:
            prop_row = UIElement(pygame.Rect(30, 0, self.middle_panel.rect.width - 40, 30))
            
            icon_x_offset = 0
            if prop_name in stat_icons:
                icon_surf, _ = c.get_scaled_asset(f"assets/icons/{stat_icons[prop_name]}", 20)
                ImageElement(rect=(0, 5, 20, 20), image_surf=icon_surf, parent=prop_row)
                icon_x_offset = 25

            TextLabel(rect=(icon_x_offset, 0, 150, 30), text=f"{prop_name.replace('_', ' ').title()}:", font=self.font_stats, color=c.UI_FONT_COLOR, parent=prop_row)
            
            value = unit_data.get('stats', {}).get(prop_name, unit_data.get(prop_name))
            if value is None: continue

            if self.is_editor:
                on_submit_func = lambda old, new, ukey=self.selected_unit_key, skey=prop_name: self.on_prop_change(ukey, skey, new)
                InputField(rect=(190, 0, 150, 30), initial_text=str(value), on_submit=on_submit_func, parent=prop_row)
            else:
                TextLabel(rect=(190, 0, 150, 30), text=str(value), font=self.font_stats, color=c.UI_FONT_COLOR, parent=prop_row)
            elements.append({'element': prop_row, 'height': 40})
        self.middle_panel.rebuild_content(elements)
    


    def rebuild_action_grid(self, unit_data):
        self.right_panel.children.clear()
        self.grid_buttons.clear()

        TextLabel(rect=(0, 0, self.right_panel.rect.width, 30), text="Action Range", font=self.font_header, color=c.UI_FONT_COLOR, parent=self.right_panel)

        cell_size, padding = 60, 8
        grid_y_start = 50

        for r in range(5):
            for c_idx in range(5):
                rect_pos = (c_idx * (cell_size + padding), grid_y_start + r * (cell_size + padding))
                rect = pygame.Rect(*rect_pos, cell_size, cell_size)
                
                class GridCell(UIElement):
                    def __init__(self, rect, color, is_center, parent=None):
                        super().__init__(rect, parent)
                        self.color = color
                        self.is_center = is_center
                    def draw(self, surface):
                        pygame.draw.rect(surface, self.color, surface.get_rect(), border_radius=5)
                        if self.is_center:
                             pygame.draw.rect(surface, (255,255,255), surface.get_rect(), 2, border_radius=5)
                        else:
                             pygame.draw.rect(surface, c.UI_BORDER_COLOR, surface.get_rect(), 1, border_radius=5)

                grid_val = unit_data['grid'][r][c_idx]
                color = self.GRID_COLORS.get(grid_val, c.COLOR_BLACK)
                is_center = (r == 2 and c_idx == 2)
                
                GridCell(rect, color, is_center, parent=self.right_panel)

                if not is_center:
                    tooltip = self.GRID_TOOLTIPS.get(grid_val, "")
                    btn = Button(rect=rect, on_click=lambda r_idx=r, c_idx=c_idx: self.on_grid_click(r_idx, c_idx), tooltip=tooltip, draw_background=False, parent=self.right_panel)
                    self.grid_buttons[(r, c_idx)] = btn

    def on_prop_change(self, unit_key, prop_key, new_value):
        unit_data = c.get_unit_data(unit_key)
        if not unit_data: return
        try:
            num_val = float(new_value) if '.' in str(new_value) else int(new_value)
        except (ValueError, TypeError):
            num_val = new_value

        if prop_key in unit_data.get('stats', {}): unit_data['stats'][prop_key] = str(new_value)
        elif prop_key in unit_data: unit_data[prop_key] = num_val
        self.has_unsaved_changes = True

    def toggle_category(self, cat_name):
        self.category_states[cat_name] = not self.category_states.get(cat_name, True); self.rebuild_ui()

    def show_list_view(self):
        self.view_mode = 'LIST'; self.selected_unit_key = None; self.rebuild_ui()
    def show_detail_view(self, unit_key):
        self.view_mode = 'DETAIL'; self.selected_unit_key = unit_key; self.rebuild_ui()
        
    def on_search_change(self, text):
        self.search_query = text
        self.rebuild_list_view()

    def on_grid_click(self, r, c_idx):
        if not self.is_editor or not self.selected_unit_key: return
        unit_data = c.get_unit_data(self.selected_unit_key)
        current_val = unit_data['grid'][r][c_idx]
        new_val = (current_val + 1) % 5
        unit_data['grid'][r][c_idx] = new_val
        self.has_unsaved_changes = True
        self.rebuild_action_grid(unit_data)

    def save_changes(self):
        if not self.is_editor or not self.has_unsaved_changes: return
        save_encyclopedia_data(c.UNIT_TYPES); self.has_unsaved_changes = False
        self.save_feedback_timer = pygame.time.get_ticks()

    def handle_events(self, event):
        if event.type == pygame.QUIT:
            self.main_app.change_state('QUIT')
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            if self.active_input:
                self.active_input.is_active = False
                self.set_active_input(None)
            elif self.view_mode == 'DETAIL':
                self.show_list_view()
            else:
                self.main_app.change_state('GAME')

        if event.type == pygame.MOUSEWHEEL:
            if self.middle_panel.is_mouse_over(pygame.mouse.get_pos()):
                self.middle_panel.handle_event(event, self, force_scroll=True)
                return

        if self.root.handle_event(event, self):
            return

    def update(self):
        self.root.update()
        if self.tooltip_owner and not self.tooltip_owner.is_mouse_over(self.tooltip_pos):
            self.clear_tooltip(self.tooltip_owner)
        
        if self.view_mode == 'DETAIL' and self.is_editor and self.save_button:
            if self.save_feedback_timer and pygame.time.get_ticks() - self.save_feedback_timer < 1000:
                self.save_button.text = "Saved!"
            else:
                if self.save_feedback_timer != 0: self.save_feedback_timer = 0
                self.save_button.text = "Save"
            
            self.save_button.is_active = self.has_unsaved_changes

    def draw(self, screen):
        screen.fill(c.UI_BACKGROUND_COLOR)
        self.root.draw(screen)
        self.draw_tooltip(screen)

    def draw_tooltip(self, screen):
        if self.tooltip_owner and not self.tooltip_owner.is_mouse_over(self.tooltip_pos):
            self.clear_tooltip(self.tooltip_owner)
        
        if self.tooltip_text and pygame.time.get_ticks() - self.tooltip_timer > 500:
            if not self.tooltip_surf or self.tooltip_text != self.cached_tooltip_text:
                self.tooltip_surf = self.tooltip_font.render(self.tooltip_text, True, c.UI_FONT_COLOR)
                self.cached_tooltip_text = self.tooltip_text
                
            rect = self.tooltip_surf.get_rect(topleft=(self.tooltip_pos[0]+15, self.tooltip_pos[1]+15))
            if rect.right > c.SCREEN_WIDTH: rect.right = c.SCREEN_WIDTH-5
            if rect.bottom > c.SCREEN_HEIGHT: rect.bottom = c.SCREEN_HEIGHT-5
            bg_rect = rect.inflate(10,6)
            pygame.draw.rect(screen, c.UI_PANEL_COLOR, bg_rect, border_radius=3)
            pygame.draw.rect(screen, c.UI_BORDER_COLOR, bg_rect, 1, border_radius=3)
            screen.blit(self.tooltip_surf, rect)

class TechTreeScreen:
    def __init__(self, main_app, game_app):
        self.main_app = main_app
        self.game_app = game_app
        self.is_editor = main_app.user_mode == 'editor'
        
        self.tech_tree = game_app.tech_tree
        self.nations = game_app.nations
        if self.is_editor:
            self.viewing_nation_id = game_app.active_nation_id if game_app.active_nation_id in self.nations else next(iter(self.nations), None)
        else:
            self.viewing_nation_id = main_app.player_nation_id

        self.camera = self.Camera()
        self.panning = False
        self.active_input = None
        self.selected_node_id = None
        self.multi_selected_node_ids = []
        self.linking_from_node_id = None
        self.linking_type = 'and'
        self.dragging_node_id = None
        self.drag_offset = (0,0)
        self.was_dragged = False
        self.is_rebuilding_panel = False
        self.side_panel_fields = {}
        self.modifier_editor_popup = None
        self.category_states = {}

        self.root = UIElement(pygame.Rect(0, 0, c.SCREEN_WIDTH, c.SCREEN_HEIGHT))
        self.font_title = c.get_font(c.FONT_PATH, 32)
        self.font_node = c.get_font(c.FONT_PATH, 16)
        self.font_node_small = c.get_font(c.FONT_PATH, 14)
        
        self.build_ui()
    
    class Camera:
        def __init__(self): self.x, self.y, self.zoom = c.SCREEN_WIDTH/2, c.SCREEN_HEIGHT/2, 1.0
        def screen_to_world(self, sx, sy): return (sx - self.x) / self.zoom, (sy - self.y) / self.zoom
        def world_to_screen(self, wx, wy): return wx * self.zoom + self.x, wy * self.zoom + self.y

    def build_ui(self):
        self.root.children.clear()
        
        Button(rect=(c.SCREEN_WIDTH - 60, 10, 50, 40), text="X", on_click=lambda: self.main_app.change_state('GAME'), parent=self.root)
        
        if self.is_editor:
            Button(rect=(10, 10, 150, 40), text="Add New Tech", on_click=self.add_new_tech, parent=self.root)
            Button(rect=(170, 10, 150, 40), text="Save Template", on_click=self.save_tech_template, parent=self.root)
            Button(rect=(330, 10, 150, 40), text="Load Template", on_click=self.load_tech_template, parent=self.root)
        
        self.rebuild_nation_selector()
        self.rebuild_side_panel()

    def rebuild_nation_selector(self):
        if not self.is_editor: return
        if hasattr(self, 'nation_panel'):
             if self.nation_panel in self.root.children: self.root.children.remove(self.nation_panel)
        
        self.nation_panel = ScrollablePanel(rect=(c.SCREEN_WIDTH - 220, 60, 210, c.SCREEN_HEIGHT - 70), parent=self.root)
        elements = []
        for nid, nation in self.nations.items():
            btn = Button(rect=(10,0,190,30), text=nation['name'], on_click=lambda n=nid: self.set_viewing_nation(n))
            btn.is_active = self.viewing_nation_id == nid
            elements.append({'element': btn, 'height': 35})
        self.nation_panel.rebuild_content(elements)

    def set_viewing_nation(self, nid):
        self.viewing_nation_id = nid
        self.rebuild_nation_selector()

    def save_tech_template(self):
        save_tech_tree_template(self.tech_tree)
    
    def load_tech_template(self):
        loaded_data = load_tech_tree_template()
        if loaded_data:
            for tech_id, tech_data in loaded_data.items():
                if 'prerequisites' in tech_data and isinstance(tech_data['prerequisites'], list):
                    tech_data['prerequisites'] = {'and': tech_data['prerequisites'],'or': [],'xor': []}
                elif 'prerequisites' not in tech_data:
                     tech_data['prerequisites'] = {'and': [], 'or': [], 'xor': []}
                if 'bonuses' not in tech_data or not isinstance(tech_data['bonuses'], dict):
                     tech_data['bonuses'] = {'description': str(tech_data.get('bonuses', '...')), 'modifiers': {}}
            
            self.tech_tree = loaded_data
            self.game_app.tech_tree = loaded_data
            self.selected_node_id = None
            self.multi_selected_node_ids.clear()
            self.rebuild_side_panel()

    def add_new_tech(self):
        new_id = str(uuid.uuid4())
        wx, wy = self.camera.screen_to_world(c.SCREEN_WIDTH/2, c.SCREEN_HEIGHT/2)
        self.tech_tree[new_id] = {
            'title': 'New Technology', 'time': 10,
            'bonuses': { 'description': '...', 'modifiers': {}, 'unit_keys': [], 'unit_class': '' },
            'prerequisites': {'and': [], 'or': [], 'xor': []}, 'pos': (wx, wy)
        }
        self.multi_selected_node_ids = [new_id]
        self.selected_node_id = new_id
        self.rebuild_side_panel()

    def delete_selected_tech(self):
        if not self.selected_node_id or self.selected_node_id not in self.tech_tree: return
        
        id_to_delete = self.selected_node_id
        del self.tech_tree[id_to_delete]
        
        for tech_id, data in self.tech_tree.items():
            if 'prerequisites' in data and isinstance(data['prerequisites'], dict):
                for prereq_type in data['prerequisites']:
                    if id_to_delete in data['prerequisites'][prereq_type]:
                        data['prerequisites'][prereq_type].remove(id_to_delete)
        
        if id_to_delete in self.multi_selected_node_ids:
            self.multi_selected_node_ids.remove(id_to_delete)
        
        self.selected_node_id = self.multi_selected_node_ids[-1] if self.multi_selected_node_ids else None
        self.rebuild_side_panel()

    def rebuild_side_panel(self):
        if self.is_rebuilding_panel: return
        self.is_rebuilding_panel = True
        
        current_scroll = 0
        if hasattr(self, 'side_panel') and self.side_panel:
            current_scroll = self.side_panel.scroll_y
            if self.side_panel in self.root.children: self.root.children.remove(self.side_panel)
            self.side_panel = None

        if not self.multi_selected_node_ids: 
            self.side_panel_fields.clear()
            self.is_rebuilding_panel = False
            return
        
        self.side_panel = ScrollablePanel(rect=(10, 60, 300, c.SCREEN_HEIGHT - 70), parent=self.root)
        
        if len(self.multi_selected_node_ids) > 1:
            self.side_panel_fields.clear()
            if self.is_editor: self.rebuild_multi_edit_ui()
            else: self.rebuild_multi_view_ui()
        elif len(self.multi_selected_node_ids) == 1:
            if self.selected_node_id != self.multi_selected_node_ids[0]:
                self.side_panel_fields.clear()
            self.selected_node_id = self.multi_selected_node_ids[0]
            if self.is_editor: self.rebuild_single_edit_ui()
            else: self.rebuild_single_view_ui()
        
        self.side_panel.scroll_y = current_scroll
        max_scroll = self.side_panel.content_height - self.side_panel.rect.height
        self.side_panel.scroll_y = max(0, min(self.side_panel.scroll_y, max_scroll if max_scroll > 0 else 0))

        self.is_rebuilding_panel = False
    
    def get_nation_status_elements(self):
        elements = []
        if self.viewing_nation_id:
            nation_data = self.nations[self.viewing_nation_id]
            used_slots = len(nation_data.get('currently_researching', {}))
            max_slots = nation_data.get('research_slots', 1)

            elements.append({'element': UIElement(pygame.Rect(0,0,0,10)), 'height': 20})
            nation_label = TextLabel(pygame.Rect(10,0,280,20), f"For: {nation_data['name']} ({used_slots}/{max_slots} slots)", self.font_node, c.COLOR_YELLOW)
            elements.append({'element': nation_label, 'height': 30})
            
            if self.is_editor:
                elements.append({'element': Button(rect=(10,0,280,30), text="Mark as Researched", on_click=lambda: self.set_nation_tech_status('researched')), 'height': 40})
            
            # Start Research Logic
            tech_status = self.get_tech_status(self.multi_selected_node_ids[0]) if self.multi_selected_node_ids else 'none'
            
            start_btn_text = "Start Researching"
            btn_active = False
            
            if tech_status == 'researched':
                start_btn_text = "Already Researched"
            elif tech_status == 'researching':
                start_btn_text = "Researching..."
            elif used_slots >= max_slots:
                 start_btn_text = "Slots Full!"
                 btn_active = True
            
            # Only enable click if it's a valid action
            action = None
            if tech_status == 'none' and used_slots < max_slots:
                action = lambda: self.set_nation_tech_status('researching')
            
            btn = Button(rect=(10,0,280,30), text=start_btn_text, on_click=action)
            btn.is_active = btn_active
            elements.append({'element': btn, 'height': 40})
            
            # Progress Bar (if researching)
            tech_id = self.multi_selected_node_ids[0] if len(self.multi_selected_node_ids) == 1 else None
            if tech_id and tech_id in nation_data.get('currently_researching', {}):
                progress = nation_data['currently_researching'][tech_id].get('progress', 0)
                time_cost = self.tech_tree[tech_id].get('time', 1)
                
                progress_row = UIElement(pygame.Rect(10, 0, 280, 30))
                # Only editor can manually edit progress number, players just see it
                if self.is_editor:
                    InputField(rect=(0,0,60,30), initial_text=str(progress), on_change=lambda val, t_id=tech_id: self.set_research_progress(t_id, val), parent=progress_row)
                else:
                    TextLabel(pygame.Rect(0,5,60,20), str(progress), self.font_node, c.UI_FONT_COLOR, parent=progress_row)
                    
                TextLabel(pygame.Rect(70,5,20,20), "/", self.font_node, c.UI_FONT_COLOR, parent=progress_row)
                TextLabel(pygame.Rect(90,5,40,20), str(time_cost), self.font_node, c.UI_FONT_COLOR, parent=progress_row)
                elements.append({'element': progress_row, 'height': 40})

            elements.append({'element': Button(rect=(10,0,280,30), text="Stop Research", on_click=lambda: self.set_nation_tech_status('none')), 'height': 40})
        return elements
    
    def get_tech_status(self, tech_id):
        if not self.viewing_nation_id: return 'none'
        ndata = self.nations[self.viewing_nation_id]
        if tech_id in ndata.get('researched_techs', []): return 'researched'
        if tech_id in ndata.get('currently_researching', {}): return 'researching'
        return 'none'

    def set_nation_tech_status(self, status):
        if not self.viewing_nation_id or not self.multi_selected_node_ids: return
        
        nation_data = self.nations[self.viewing_nation_id]
        
        for tech_id in self.multi_selected_node_ids:
            if tech_id in nation_data.get('researched_techs', []):
                nation_data['researched_techs'].remove(tech_id)
            if tech_id in nation_data.get('currently_researching', {}):
                del nation_data['currently_researching'][tech_id]
        
        if status == 'researched':
            for tech_id in self.multi_selected_node_ids:
                if tech_id not in nation_data.get('researched_techs', []):
                    nation_data.setdefault('researched_techs', []).append(tech_id)
        elif status == 'researching':
            max_slots = nation_data.get('research_slots', 1)
            current_slots = len(nation_data.get('currently_researching', {}))
            
            for tech_id in self.multi_selected_node_ids:
                if current_slots < max_slots:
                    nation_data.setdefault('currently_researching', {})[tech_id] = {'progress': 0}
                    current_slots += 1
                else:
                    print(f"Cannot research {self.tech_tree[tech_id].get('title')}: No free slots.")
        
        self.rebuild_side_panel()

    def set_research_progress(self, tech_id, value):
        if self.viewing_nation_id and tech_id in self.nations[self.viewing_nation_id].get('currently_researching', {}):
            try:
                self.nations[self.viewing_nation_id]['currently_researching'][tech_id]['progress'] = int(value)
            except ValueError:
                pass
        
    def set_linking_type(self, link_type):
        self.linking_type = link_type
        self.rebuild_side_panel()

    def rebuild_multi_edit_ui(self):
        elements = []
        
        label = TextLabel(pygame.Rect(10,0,280,20), f"{len(self.multi_selected_node_ids)} techs selected", self.font_node, c.UI_FONT_COLOR)
        elements.append({'element': label, 'height': 30})

        nation_elements = self.get_nation_status_elements()
        elements.extend(nation_elements)
        
        self.side_panel.rebuild_content(elements)

    def rebuild_single_edit_ui(self):
        node_data = self.tech_tree[self.selected_node_id]
        elements = []
        
        if 'bonuses' not in node_data or not isinstance(node_data['bonuses'], dict):
            node_data['bonuses'] = {'description': '...', 'modifiers': {}, 'unit_keys': [], 'unit_class': ''}
        if 'modifiers' not in node_data['bonuses'] or isinstance(node_data['bonuses']['modifiers'], list):
            node_data['bonuses']['modifiers'] = {}

        def create_on_change(key): 
            def on_change(text):
                self.tech_tree[self.selected_node_id][key] = text
            return on_change
        
        for key, name in [('title', "Title"), ('time', "Time/Cost")]:
            elements.append({'element': TextLabel(pygame.Rect(10,0,280,20), name, self.font_node, c.UI_FONT_COLOR), 'height': 25})
            if key not in self.side_panel_fields:
                self.side_panel_fields[key] = InputField(pygame.Rect(10,0,280,30), on_change=create_on_change(key))
            field = self.side_panel_fields[key]; field.set_text(str(node_data.get(key, ''))); elements.append({'element': field, 'height': 40})
        
        elements.append({'element': TextLabel(pygame.Rect(10,0,280,20), "Bonus Description", self.font_node, c.UI_FONT_COLOR), 'height': 25})
        if 'bonus_desc' not in self.side_panel_fields:
            self.side_panel_fields['bonus_desc'] = MultilineInputField(pygame.Rect(10,0,280,30), on_change=lambda txt: self.tech_tree[self.selected_node_id]['bonuses'].__setitem__('description', txt))
        desc_input = self.side_panel_fields['bonus_desc']; desc_input.set_text(node_data['bonuses'].get('description', '')); desc_input.on_resize = self.rebuild_side_panel
        elements.append({'element': desc_input, 'height': desc_input.rect.height + 10})

        elements.append({'element': TextLabel(pygame.Rect(10,0,280,20), "Stat Modifiers", self.font_node, c.UI_FONT_COLOR), 'height': 25})
        
        unit_keys = node_data['bonuses'].get('unit_keys', [])
        btn_text = ", ".join(unit_keys) if unit_keys else "Affects: All Units"
        if self.font_node.size(btn_text)[0] > 270: btn_text = f"Affects: {len(unit_keys)} units"
        elements.append({'element': Button(rect=(10,0,270,30), text=btn_text, on_click=lambda: self.open_unit_selector_popup()), 'height': 40})

        class_input = InputField(pygame.Rect(10,0,270,30), initial_text=node_data['bonuses'].get('unit_class',''), on_change=lambda txt: self.update_bonus_prop('unit_class', txt))
        class_input.tooltip = "Optional: land, naval, air"
        elements.append({'element': class_input, 'height': 40})

        mod_panel = Panel(pygame.Rect(10,0,280, 70), color=(50,55,65)); y=5
        stat_keys = ['str', 'arm', 'sup', 'spe']
        input_width = (270 - 15) // 4

        for i, key in enumerate(stat_keys):
            label = TextLabel(pygame.Rect(5 + i * (input_width + 5), y, input_width, 15), key.upper(), self.font_node_small, c.UI_FONT_COLOR, center_align=True)
            mod_panel.add_child(label)
        y += 20
        
        for i, key in enumerate(stat_keys):
            field = InputField(pygame.Rect(5 + i * (input_width + 5), y, input_width, 30),
                               initial_text=str(node_data['bonuses']['modifiers'].get(key, '')),
                               on_submit=lambda old, new, k=key: self.update_modifier_stat(k, new),
                               parent=mod_panel)
            field.tooltip = "e.g., +1, -2, =5"
        
        elements.append({'element': mod_panel, 'height': mod_panel.rect.height + 10})

        prereq_button_row = UIElement(pygame.Rect(10, 0, 280, 30))
        prereq_types = [('and', "AND"), ('or', "OR"), ('xor', "XOR")]; btn_width = 280 // len(prereq_types)
        for i, (key, text) in enumerate(prereq_types):
            btn = Button(rect=(i*btn_width,0,btn_width-5,30), text=text, on_click=(lambda k=key: self.set_linking_type(k)), parent=prereq_button_row)
            btn.is_active = self.linking_type == key
        elements.append({'element': prereq_button_row, 'height': 40})

        elements.append({'element': Button(rect=(10,0,280,30), text="Set Prerequisite Link", on_click=lambda: setattr(self, 'linking_from_node_id', self.selected_node_id)), 'height': 40})
        elements.append({'element': Button(rect=(10,0,280,30), text="Delete Tech", on_click=self.delete_selected_tech), 'height': 40})
        elements.extend(self.get_nation_status_elements())
        self.side_panel.rebuild_content(elements)

    def rebuild_single_view_ui(self):
        node_data = self.tech_tree[self.selected_node_id]
        elements = []
        
        bonuses = node_data.get('bonuses', {})
        if isinstance(bonuses, str): bonuses = {'description': bonuses, 'modifiers': {}}

        for key, name in [('title', "Title"), ('time', "Time/Cost")]:
            label_name = TextLabel(pygame.Rect(10,0,280,20), f"{name}:", self.font_node, c.COLOR_YELLOW)
            elements.append({'element': label_name, 'height': 25})
            value_text = TextLabel(pygame.Rect(20,0,260,30), str(node_data.get(key, '')), self.font_node, c.UI_FONT_COLOR, wrap_width=260)
            elements.append({'element': value_text, 'height': value_text.rect.height + 15})
        
        desc_label = TextLabel(pygame.Rect(10,0,280,20), "Bonus Description:", self.font_node, c.COLOR_YELLOW)
        elements.append({'element': desc_label, 'height': 25})
        desc_text = TextLabel(pygame.Rect(20,0,260,30), bonuses.get('description', ''), self.font_node, c.UI_FONT_COLOR, wrap_width=260)
        elements.append({'element': desc_text, 'height': desc_text.rect.height + 15})
        
        modifiers = bonuses.get('modifiers', {})
        if modifiers:
            mod_header = TextLabel(pygame.Rect(10,0,280,20), "Stat Modifiers:", self.font_node, c.COLOR_YELLOW)
            elements.append({'element': mod_header, 'height': 30})
            for stat, mod_val_str in modifiers.items():
                if mod_val_str:
                    mod_text = f"{stat.upper()}: {mod_val_str}"
                    mod_label = TextLabel(pygame.Rect(20,0,260,20), mod_text, self.font_node, c.UI_FONT_COLOR, wrap_width=260)
                    elements.append({'element': mod_label, 'height': mod_label.rect.height + 5})

        # Add Research Buttons for Players
        elements.extend(self.get_nation_status_elements())

        self.side_panel.rebuild_content(elements)

    def rebuild_multi_view_ui(self):
        elements = []
        label = TextLabel(pygame.Rect(10,0,280,20), f"{len(self.multi_selected_node_ids)} techs selected", self.font_node, c.UI_FONT_COLOR)
        elements.append({'element': label, 'height': 30})
        # Add Research Buttons for Players
        elements.extend(self.get_nation_status_elements())
        self.side_panel.rebuild_content(elements)
    
    def rebuild_multi_view_ui(self):
        elements = []
        label = TextLabel(pygame.Rect(10,0,280,20), f"{len(self.multi_selected_node_ids)} techs selected", self.font_node, c.UI_FONT_COLOR)
        elements.append({'element': label, 'height': 30})
        self.side_panel.rebuild_content(elements)

    def update_modifier_stat(self, key, value):
        self.tech_tree[self.selected_node_id]['bonuses']['modifiers'][key] = value

    def update_bonus_prop(self, key, value):
        self.tech_tree[self.selected_node_id]['bonuses'][key] = value
        self.rebuild_side_panel()

    def open_unit_selector_popup(self):
        if self.modifier_editor_popup:
            return

        bonuses = self.tech_tree[self.selected_node_id]['bonuses']
        if 'unit_keys' not in bonuses or not isinstance(bonuses['unit_keys'], list):
            bonuses['unit_keys'] = []

        popup_panel = ScrollablePanel(rect=(0,0, 400, 500), parent=self.root)
        popup_panel.rect.center = (c.SCREEN_WIDTH / 2, c.SCREEN_HEIGHT / 2)
        
        elements = []
        title = TextLabel(pygame.Rect(10,0,380,25), "Select Units", self.font_node, c.UI_FONT_COLOR, center_align=True)
        elements.append({'element': title, 'height': 30})
        
        structured_units = {}
        for faction, units in c.UNIT_TYPES.items():
            structured_units[faction] = {}
            for key, data in units.items():
                unit_class = data.get('unit_class', 'land').title()
                if unit_class not in structured_units[faction]: structured_units[faction][unit_class] = []
                structured_units[faction][unit_class].append((key, data))

        for faction, classes in sorted(structured_units.items()):
            cat_key = f"mod_{faction}"
            cat_header = CategoryHeader(pygame.Rect(5,0,390,30), faction, lambda c=cat_key: self.toggle_unit_cat(c), self.category_states.get(cat_key, True))
            elements.append({'element': cat_header, 'height': 35})
            if self.category_states.get(cat_key, True):
                for unit_class, units_in_class in sorted(classes.items()):
                    sub_cat_key = f"mod_{faction}_{unit_class}"
                    sub_cat_header = CategoryHeader(pygame.Rect(15,0,370,25), unit_class, lambda c=sub_cat_key: self.toggle_unit_cat(c), self.category_states.get(sub_cat_key, True))
                    elements.append({'element': sub_cat_header, 'height': 30})
                    if self.category_states.get(sub_cat_key, True):
                        for key, data in sorted(units_in_class, key=lambda item: item[1]['name']):
                            checkbox = Checkbox(rect=(25,0,350,25), text=data['name'], 
                                                initial_state=(key in bonuses['unit_keys']), 
                                                on_toggle=lambda state, k=key: self.toggle_modifier_unit(k, state))
                            elements.append({'element': checkbox, 'height': 30})

        done_button = Button(rect=(10,0,380,40), text="Done", on_click=self.close_modifier_editor)
        elements.append({'element': UIElement(rect=(0,0,0,10)), 'height': 10})
        elements.append({'element': done_button, 'height': 50})

        popup_panel.rebuild_content(elements)
        self.modifier_editor_popup = popup_panel

    def toggle_unit_cat(self, cat_key):
        self.category_states[cat_key] = not self.category_states.get(cat_key, True)
        if self.modifier_editor_popup:
            self.root.children.remove(self.modifier_editor_popup)
            self.modifier_editor_popup = None
            self.open_unit_selector_popup()

    def close_modifier_editor(self):
        if self.modifier_editor_popup:
            if self.modifier_editor_popup in self.root.children: self.root.children.remove(self.modifier_editor_popup)
            self.modifier_editor_popup = None
            self.rebuild_side_panel()

    def toggle_modifier_unit(self, unit_key, state):
        bonuses = self.tech_tree[self.selected_node_id]['bonuses']
        unit_keys = bonuses.setdefault('unit_keys', [])
        if state and unit_key not in unit_keys:
            unit_keys.append(unit_key)
        elif not state and unit_key in unit_keys:
            unit_keys.remove(unit_key)
        self.rebuild_side_panel()

    def get_node_at_pos(self, pos):
        for tech_id, data in reversed(list(self.tech_tree.items())):
            sx, sy = self.camera.world_to_screen(*data.get('pos', (0,0)))
            node_rect = pygame.Rect(0,0, 120 * self.camera.zoom, 60 * self.camera.zoom)
            node_rect.center = (sx, sy)
            if node_rect.collidepoint(pos):
                return tech_id
        return None
        
    def get_connection_at_pos(self, pos):
        world_pos = self.camera.screen_to_world(*pos)
        px, py = world_pos

        for tech_id, tech_data in self.tech_tree.items():
            prereqs = tech_data.get('prerequisites', {})
            if not isinstance(prereqs, dict): continue

            for prereq_type, prereq_list in prereqs.items():
                for prereq_id in prereq_list:
                    if prereq_id in self.tech_tree:
                        start_node = self.tech_tree[prereq_id]
                        end_node = tech_data
                        
                        x1, y1 = start_node.get('pos', (0,0))
                        x2, y2 = end_node.get('pos', (0,0))

                        dx, dy = x2 - x1, y2 - y1
                        len_sq = dx*dx + dy*dy
                        if len_sq == 0: continue

                        t = max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / len_sq))
                        closest_x = x1 + t * dx
                        closest_y = y1 + t * dy

                        dist_sq = (px - closest_x)**2 + (py - closest_y)**2
                        click_radius = (10 / self.camera.zoom)**2

                        if dist_sq < click_radius:
                            return (tech_id, prereq_id, prereq_type)
        return None

    def handle_mouse_down(self, pos):
        self.was_dragged = False
        clicked_node_id = self.get_node_at_pos(pos)
        
        if self.is_editor and clicked_node_id:
            self.dragging_node_id = clicked_node_id
            data = self.tech_tree[clicked_node_id]
            wx, wy = data['pos']
            mx, my = self.camera.screen_to_world(*pos)
            self.drag_offset = (wx - mx, wy - my)

    def handle_mouse_up(self, pos):
        clicked_node_id = self.get_node_at_pos(pos)

        if self.is_editor and self.was_dragged:
            self.dragging_node_id = None
            return

        if clicked_node_id:
            if self.is_editor and self.linking_from_node_id and self.linking_from_node_id != clicked_node_id:
                target_node = self.tech_tree[self.linking_from_node_id]
                
                if 'prerequisites' not in target_node or not isinstance(target_node['prerequisites'], dict):
                    target_node['prerequisites'] = {'and': [], 'or': [], 'xor': []}

                prereq_list = target_node['prerequisites'][self.linking_type]
                if clicked_node_id not in prereq_list:
                    prereq_list.append(clicked_node_id)
                
                self.linking_from_node_id = None
                self.rebuild_side_panel()
            else:
                mods = pygame.key.get_mods()
                if mods & pygame.KMOD_SHIFT:
                    if clicked_node_id in self.multi_selected_node_ids:
                        self.multi_selected_node_ids.remove(clicked_node_id)
                    else:
                        self.multi_selected_node_ids.append(clicked_node_id)
                else:
                     self.multi_selected_node_ids = [clicked_node_id]
        else:
            mods = pygame.key.get_mods()
            if not (mods & pygame.KMOD_SHIFT):
                self.multi_selected_node_ids.clear()
            self.linking_from_node_id = None
        
        self.dragging_node_id = None
        self.rebuild_side_panel()

    def handle_events(self, event):
        if event.type == pygame.QUIT:
            self.main_app.change_state('QUIT')
            return

        if self.modifier_editor_popup:
            if self.modifier_editor_popup.handle_event(event, self):
                return
            if event.type == pygame.MOUSEBUTTONDOWN and not self.modifier_editor_popup.is_mouse_over(event.pos):
                self.close_modifier_editor()
                return

        if self.root.handle_event(event, self):
            return

        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.main_app.change_state('GAME')
            return

        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 2: self.panning = True
            elif event.button == 1: self.handle_mouse_down(event.pos)
            elif event.button == 3:
                self.linking_from_node_id = None
                if self.is_editor:
                    connection = self.get_connection_at_pos(event.pos)
                    if connection:
                        tech_id, prereq_id, prereq_type = connection
                        self.tech_tree[tech_id]['prerequisites'][prereq_type].remove(prereq_id)
                        self.rebuild_side_panel()

        if event.type == pygame.MOUSEBUTTONUP:
            if event.button == 2: self.panning = False
            elif event.button == 1: self.handle_mouse_up(event.pos)

        if event.type == pygame.MOUSEMOTION:
            if self.panning:
                self.camera.x += event.rel[0]
                self.camera.y += event.rel[1]
            elif self.is_editor and self.dragging_node_id:
                self.was_dragged = True
                mx, my = self.camera.screen_to_world(*event.pos)
                self.tech_tree[self.dragging_node_id]['pos'] = (mx + self.drag_offset[0], my + self.drag_offset[1])

        if event.type == pygame.MOUSEWHEEL:
            mx, my = pygame.mouse.get_pos()
            world_x_before, world_y_before = self.camera.screen_to_world(mx, my)
            self.camera.zoom *= (1.1 if event.y > 0 else 0.9)
            self.camera.zoom = max(0.2, min(self.camera.zoom, 3.0))
            world_x_after, world_y_after = self.camera.screen_to_world(mx, my)
            self.camera.x += (world_x_after - world_x_before) * self.camera.zoom
            self.camera.y += (world_y_after - world_y_before) * self.camera.zoom

    def update(self):
        self.root.update()

    def draw(self, screen):
        screen.fill(c.UI_BACKGROUND_COLOR)
        grid_color = (60, 65, 75)
        grid_spacing = int(50 * self.camera.zoom)
        offset_x = int(self.camera.x % grid_spacing)
        offset_y = int(self.camera.y % grid_spacing)
        
        for x in range(offset_x, c.SCREEN_WIDTH, grid_spacing):
            pygame.draw.line(screen, grid_color, (x, 0), (x, c.SCREEN_HEIGHT))
        for y in range(offset_y, c.SCREEN_HEIGHT, grid_spacing):
            pygame.draw.line(screen, grid_color, (0, y), (c.SCREEN_WIDTH, y))

        self.draw_connections(screen)
        self.draw_nodes(screen)
        if self.is_editor and self.linking_from_node_id and self.linking_from_node_id in self.tech_tree:
            start_pos = self.camera.world_to_screen(*self.tech_tree[self.linking_from_node_id]['pos'])
            pygame.draw.line(screen, c.COLOR_YELLOW, start_pos, pygame.mouse.get_pos(), 2)
        
        if self.viewing_nation_id:
            ndata = self.nations[self.viewing_nation_id]
            used = len(ndata.get('currently_researching', {}))
            total = ndata.get('research_slots', 1)
            if used < total:
                warning_rect = pygame.Rect(c.SCREEN_WIDTH/2 - 150, 10, 300, 40)
                pygame.draw.rect(screen, (220, 160, 40), warning_rect, border_radius=5)
                pygame.draw.rect(screen, c.COLOR_WHITE, warning_rect, 2, border_radius=5)
                
                font = c.get_font(c.FONT_PATH, 20)
                text_surf = font.render(f"Free Research Slot! ({used}/{total})", True, c.COLOR_BLACK)
                screen.blit(text_surf, text_surf.get_rect(center=warning_rect.center))

        self.root.draw(screen)
        self.draw_minimap(screen)
        
        if self.modifier_editor_popup:
            self.modifier_editor_popup.draw(screen)
            
    def draw_minimap(self, screen):
        if not self.tech_tree: return
        
        # Calculate bounds
        all_positions = [data['pos'] for data in self.tech_tree.values()]
        min_x = min(p[0] for p in all_positions) - 200
        max_x = max(p[0] for p in all_positions) + 200
        min_y = min(p[1] for p in all_positions) - 200
        max_y = max(p[1] for p in all_positions) + 200
        
        tree_w = max(1, max_x - min_x)
        tree_h = max(1, max_y - min_y)
        
        map_size = 150
        rect = pygame.Rect(10, c.SCREEN_HEIGHT - map_size - 10, map_size, map_size)
        
        # Aspect ratio fitting
        scale = min(map_size / tree_w, map_size / tree_h)
        
        pygame.draw.rect(screen, (30, 30, 35), rect)
        pygame.draw.rect(screen, c.UI_BORDER_COLOR, rect, 1)
        
        # Draw nodes on minimap
        for data in self.tech_tree.values():
            wx, wy = data['pos']
            mx = rect.x + (wx - min_x) * scale
            my = rect.y + (wy - min_y) * scale
            pygame.draw.rect(screen, (100, 100, 100), (mx-2, my-1, 4, 2))
            
        # Draw Viewport
        # Calculate world corners of screen
        screen_w_world = c.SCREEN_WIDTH / self.camera.zoom
        screen_h_world = c.SCREEN_HEIGHT / self.camera.zoom
        top_left_world_x = (0 - self.camera.x) / self.camera.zoom
        top_left_world_y = (0 - self.camera.y) / self.camera.zoom
        
        vx = rect.x + (top_left_world_x - min_x) * scale
        vy = rect.y + (top_left_world_y - min_y) * scale
        vw = screen_w_world * scale
        vh = screen_h_world * scale
        
        view_rect = pygame.Rect(vx, vy, vw, vh)
        view_rect.clamp_ip(rect) # Keep inside
        pygame.draw.rect(screen, c.COLOR_YELLOW, view_rect, 1)
        
        # Basic Interaction check
        if pygame.mouse.get_pressed()[0]:
            mpos = pygame.mouse.get_pos()
            if rect.collidepoint(mpos):
                rel_x = (mpos[0] - rect.x) / scale + min_x
                rel_y = (mpos[1] - rect.y) / scale + min_y
                
                # Center camera on this world point
                self.camera.x = c.SCREEN_WIDTH/2 - rel_x * self.camera.zoom
                self.camera.y = c.SCREEN_HEIGHT/2 - rel_y * self.camera.zoom

    def draw_dashed_line(self, surface, color, start_pos, end_pos, width=1, dash_length=10):
        x1, y1 = start_pos
        x2, y2 = end_pos
        dx, dy = x2 - x1, y2 - y1
        distance = math.hypot(dx, dy)
        if distance == 0: return
        
        scaled_dash = dash_length * self.camera.zoom
        if scaled_dash == 0: return

        dashes = int(distance / scaled_dash)
        if dashes == 0:
            pygame.draw.line(surface, color, start_pos, end_pos, int(width))
            return

        for i in range(dashes):
            start = (x1 + dx * i / dashes, y1 + dy * i / dashes)
            end = (x1 + dx * (i + 0.5) / dashes, y1 + dy * (i + 0.5) / dashes)
            if (end[0]-start[0])**2 + (end[1]-start[1])**2 > 1.0:
                 pygame.draw.line(surface, color, start, end, int(width))

    def draw_connections(self, screen):
        for tech_id, tech_data in self.tech_tree.items():
            prereqs = tech_data.get('prerequisites', {})
            if not isinstance(prereqs, dict): continue

            end_pos = self.camera.world_to_screen(*tech_data.get('pos', (0,0)))

            for prereq_type, prereq_list in prereqs.items():
                for prereq_id in prereq_list:
                    if prereq_id in self.tech_tree:
                        start_pos = self.camera.world_to_screen(*self.tech_tree[prereq_id].get('pos', (0,0)))
                        
                        color = (100, 100, 100)
                        width = max(1, int(2 * self.camera.zoom))
                        
                        if prereq_type == 'or':
                            color = (100, 100, 200)
                            self.draw_dashed_line(screen, color, start_pos, end_pos, width)
                            continue
                        elif prereq_type == 'xor':
                            color = (200, 50, 50)
                            width = max(2, int(3 * self.camera.zoom))

                        pygame.draw.line(screen, color, start_pos, end_pos, width)

    def draw_nodes(self, screen):
        nation_data = self.nations.get(self.viewing_nation_id)
        
        for tech_id, data in self.tech_tree.items():
            sx, sy = self.camera.world_to_screen(*data.get('pos', (0,0)))
            node_rect = pygame.Rect(0,0, 120 * self.camera.zoom, 60 * self.camera.zoom)
            node_rect.center = (sx, sy)
            
            if not screen.get_rect().colliderect(node_rect): continue

            color = (80,80,90) 
            progress_ratio = 0.0

            if nation_data:
                researched = nation_data.get('researched_techs', [])
                prereqs = data.get('prerequisites', {})
                if not isinstance(prereqs, dict):
                    prereqs = {'and': prereqs if isinstance(prereqs, list) else [], 'or': [], 'xor': []}
                
                and_met = all(p in researched for p in prereqs.get('and', []))
                or_met = not prereqs.get('or') or any(p in researched for p in prereqs.get('or', []))
                
                xor_met = not any(p in researched for p in prereqs.get('xor', []))
                
                is_blocked_by_other_xor = False
                for other_tech_id in researched:
                    other_tech_data = self.tech_tree.get(other_tech_id, {})
                    other_prereqs = other_tech_data.get('prerequisites', {})
                    if isinstance(other_prereqs, dict) and tech_id in other_prereqs.get('xor', []):
                        is_blocked_by_other_xor = True
                        break

                prereqs_met = and_met and or_met and xor_met and not is_blocked_by_other_xor

                currently_researching = nation_data.get('currently_researching', {})

                if tech_id in researched: 
                    color = c.COLOR_GREEN
                elif tech_id in currently_researching: 
                    color = c.COLOR_YELLOW
                    try:
                        progress = float(currently_researching[tech_id].get('progress', 0))
                        time_cost = float(data.get('time', 1))
                        if time_cost > 0:
                            progress_ratio = min(1.0, progress / time_cost)
                    except (ValueError, TypeError, ZeroDivisionError):
                        progress_ratio = 0.0

                elif prereqs_met: 
                    color = c.COLOR_BLUE
            
            border_color, border_width = c.UI_BORDER_COLOR, 1
            if tech_id in self.multi_selected_node_ids:
                border_color, border_width = c.COLOR_ORANGE, 3

            pygame.draw.rect(screen, color, node_rect, border_radius=5)
            
            if progress_ratio > 0:
                progress_width = node_rect.width * progress_ratio
                progress_rect = pygame.Rect(node_rect.left, node_rect.top, progress_width, node_rect.height)
                screen.fill(c.COLOR_GREEN, progress_rect, special_flags=pygame.BLEND_RGBA_MULT)

            pygame.draw.rect(screen, border_color, node_rect, max(1,int(border_width*self.camera.zoom)), border_radius=5)
            
            font_size = int(16 * self.camera.zoom)
            if font_size > 5:
                font = c.get_font(c.FONT_PATH, font_size)
                text_surf = font.render(data.get('title', ''), True, c.UI_FONT_COLOR)
                screen.blit(text_surf, text_surf.get_rect(center=node_rect.center))

                time_font_size = int(14 * self.camera.zoom)
                if time_font_size > 4:
                    time_font = c.get_font(c.FONT_PATH, time_font_size)
                    time_surf = time_font.render(f"{data.get('time', 0)}t", True, c.UI_FONT_COLOR)
                    time_rect = time_surf.get_rect(bottomright=node_rect.bottomright - pygame.Vector2(5 * self.camera.zoom, 2 * self.camera.zoom))
                    screen.blit(time_surf, time_rect)

    def set_active_input(self, input_field): 
        if self.active_input and self.active_input != input_field: self.active_input.is_active = False
        self.active_input = input_field
    def set_tooltip(self, text, owner, pos): pass
    def clear_tooltip(self, owner=None): pass
    
    
    
class TitleScreen:
    def __init__(self, main_app):
        self.main_app = main_app
        self.root = UIElement(pygame.Rect(0, 0, c.SCREEN_WIDTH, c.SCREEN_HEIGHT))
        self.font_title = c.get_font(c.FONT_PATH, 72)
        self.font_button = c.get_font(c.FONT_PATH, 24)
        
        # Background (Dark with a subtle grid pattern or just color)
        self.bg_color = (20, 25, 30)
        
        center_x = c.SCREEN_WIDTH / 2
        center_y = c.SCREEN_HEIGHT / 2
        
        # Title
        TextLabel(rect=(0, center_y - 150, c.SCREEN_WIDTH, 80), text=c.APP_TITLE, font=self.font_title, color=c.UI_HIGHLIGHT_COLOR, parent=self.root, center_align=True)
        
        # Buttons
        btn_width = 250
        btn_height = 50
        spacing = 20
        start_y = center_y
        
        # Play
        Button(rect=(center_x - btn_width/2, start_y, btn_width, btn_height), text="Play", on_click=self.on_play, parent=self.root)
        
        # Create Map (WIP)
        self.create_btn = Button(rect=(center_x - btn_width/2, start_y + btn_height + spacing, btn_width, btn_height), text="Create Your Map", on_click=self.on_create, parent=self.root)
        
        # Tutorial
        Button(rect=(center_x - btn_width/2, start_y + (btn_height + spacing)*2, btn_width, btn_height), text="Tutorial", on_click=self.on_tutorial, parent=self.root)

        # Exit
        Button(rect=(center_x - btn_width/2, start_y + (btn_height + spacing)*3, btn_width, btn_height), text="Exit", on_click=self.on_exit, parent=self.root)

        self.wip_timer = 0

    def on_play(self):
        self.main_app.change_state('ONLINE_MAPS')

    def on_create(self):
        self.wip_timer = pygame.time.get_ticks()

    def on_tutorial(self):
        self.main_app.change_state('TUTORIAL')

    def on_exit(self):
        self.main_app.change_state('QUIT')

    def handle_events(self, event):
        if event.type == pygame.QUIT:
            self.main_app.change_state('QUIT')
        self.root.handle_event(event, self)

    def update(self):
        self.root.update()

    def draw(self, screen):
        screen.fill(self.bg_color)
        
        # Subtle grid background
        grid_color = (30, 35, 40)
        for x in range(0, c.SCREEN_WIDTH, 40):
            pygame.draw.line(screen, grid_color, (x, 0), (x, c.SCREEN_HEIGHT))
        for y in range(0, c.SCREEN_HEIGHT, 40):
            pygame.draw.line(screen, grid_color, (0, y), (c.SCREEN_WIDTH, y))
            
        self.root.draw(screen)
        
        # WIP Toast
        if pygame.time.get_ticks() - self.wip_timer < 2000:
            font = c.get_font(c.FONT_PATH, 20)
            text_surf = c.create_text_with_border("Work in Progress!", font, c.COLOR_ORANGE, c.COLOR_BLACK)
            rect = text_surf.get_rect(midbottom=(self.create_btn.rect.centerx, self.create_btn.rect.top - 10))
            screen.blit(text_surf, rect)

    # Dummy methods to satisfy interface if needed by main loop
    def set_active_input(self, i): pass
    def set_tooltip(self, t, o, p): pass
    def clear_tooltip(self, o=None): pass