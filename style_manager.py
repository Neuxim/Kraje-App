import config as c

class StyleManager:
    """
    Manages and applies visual themes for the map and UI.
    The active style is saved with the game state.
    """

    def __init__(self):
        self.styles = {
            'Primordial': {
                'GRID_LINE_COLOR': (87, 83, 78),
                'LAND_COLORS': {'Plains':(90, 175, 70), 'Water':(60, 80, 220), 'Mountains':(110, 110, 120), 'Desert':(240, 215, 150), 'Swamps':(80, 100, 50), 'Snowy':(230, 245, 255), 'Forest':(40, 120, 60), 'Border':(0, 0, 0), 'Objective':(255, 235, 50), 'Canal':(100, 130, 240)},
                'UI_BACKGROUND_COLOR': (46, 41, 37),
                'UI_PANEL_COLOR': (64, 57, 51, 235),
                'UI_BORDER_COLOR': (87, 83, 78),
                'FONT_PATH': 'assets/fonts/Tectoyaki.ttf'
            },
            'Ancient': {
                'GRID_LINE_COLOR': (140, 125, 105),
                'LAND_COLORS': {'Plains':(220, 205, 175), 'Water':(110, 135, 175), 'Mountains':(160, 150, 130), 'Desert':(235, 220, 180), 'Swamps':(170, 165, 135), 'Snowy':(210, 225, 235), 'Forest':(180, 175, 140), 'Border':(40, 30, 20), 'Objective':(255, 215, 0), 'Canal':(130, 155, 190)},
                'UI_BACKGROUND_COLOR': (50, 40, 30),
                'UI_PANEL_COLOR': (90, 70, 50, 240),
                'UI_BORDER_COLOR': (140, 125, 105),
                'FONT_PATH': 'assets/fonts/Tectoyaki.ttf'
            },
            'Medieval': {
                'GRID_LINE_COLOR': (100, 80, 60),
                'LAND_COLORS': {'Plains':(120, 160, 90), 'Water':(100, 130, 180), 'Mountains':(140, 130, 120), 'Desert':(220, 200, 160), 'Swamps':(100, 120, 80), 'Snowy':(220, 230, 240), 'Forest':(80, 130, 70), 'Border':(40, 30, 20), 'Objective':(240, 200, 80), 'Canal':(130, 160, 200)},
                'UI_BACKGROUND_COLOR': (30, 25, 20),
                'UI_PANEL_COLOR': (80, 65, 50, 245),
                'UI_BORDER_COLOR': (110, 90, 70),
                'FONT_PATH': 'assets/fonts/Tectoyaki.ttf'
            },
            'Colonial': {
                'GRID_LINE_COLOR': (160, 150, 130),
                'LAND_COLORS': {'Plains':(235, 225, 200), 'Water':(120, 160, 190), 'Mountains':(190, 180, 165), 'Desert':(245, 235, 210), 'Swamps':(180, 190, 160), 'Snowy':(215, 225, 230), 'Forest':(160, 180, 110), 'Border':(50, 40, 30), 'Objective':(250, 220, 100), 'Canal':(140, 175, 200)},
                'UI_BACKGROUND_COLOR': (60, 50, 40),
                'UI_PANEL_COLOR': (110, 95, 80, 240),
                'UI_BORDER_COLOR': (160, 150, 130),
                'FONT_PATH': 'assets/fonts/Tectoyaki.ttf'
            },
            'Industrial': {
                'GRID_LINE_COLOR': (90, 90, 90),
                'LAND_COLORS': {'Plains':(130, 150, 100), 'Water':(90, 110, 140), 'Mountains':(110, 110, 110), 'Desert':(190, 180, 150), 'Swamps':(90, 100, 80), 'Snowy':(190, 200, 205), 'Forest':(70, 100, 70), 'Border':(30, 30, 30), 'Objective':(200, 180, 60), 'Canal':(110, 130, 160)},
                'UI_BACKGROUND_COLOR': (40, 40, 45),
                'UI_PANEL_COLOR': (60, 60, 65, 245),
                'UI_BORDER_COLOR': (90, 90, 90),
                'FONT_PATH': 'assets/fonts/Tectoyaki.ttf'
            },
            'Great War': {
                'GRID_LINE_COLOR': (80, 75, 70),
                'LAND_COLORS': {'Plains':(155, 145, 110), 'Water':(100, 110, 120), 'Mountains':(115, 110, 105), 'Desert':(180, 165, 140), 'Swamps':(100, 95, 80), 'Snowy':(180, 185, 190), 'Forest':(100, 110, 80), 'Border':(20, 20, 20), 'Objective':(190, 170, 80), 'Canal':(120, 130, 140)},
                'UI_BACKGROUND_COLOR': (55, 50, 45),
                'UI_PANEL_COLOR': (75, 70, 65, 240),
                'UI_BORDER_COLOR': (80, 75, 70),
                'FONT_PATH': 'assets/fonts/Tectoyaki.ttf'
            },
            'WWII': {
                'GRID_LINE_COLOR': (90, 90, 90),
                'LAND_COLORS': {'Plains':(118, 134, 98), 'Water':(90, 105, 128), 'Mountains':(100, 100, 100), 'Desert':(193, 178, 145), 'Swamps':(82, 88, 70), 'Snowy':(195, 200, 202), 'Forest':(72, 90, 62), 'Border':(25, 25, 25), 'Objective':(210, 185, 70), 'Canal':(110, 125, 148)},
                'UI_BACKGROUND_COLOR': (48, 52, 48),
                'UI_PANEL_COLOR': (68, 72, 68, 240),
                'UI_BORDER_COLOR': (90, 90, 90),
                'FONT_PATH': 'assets/fonts/Tectoyaki.ttf'
            },
            'Atomic': {
                'GRID_LINE_COLOR': (100, 110, 100),
                'LAND_COLORS': {'Plains':(160, 170, 130), 'Water':(100, 115, 130), 'Mountains':(150, 150, 150), 'Desert':(190, 180, 160), 'Swamps':(120, 125, 110), 'Snowy':(200, 205, 210), 'Forest':(110, 130, 95), 'Border':(40, 40, 40), 'Objective':(230, 210, 90), 'Canal':(120, 135, 150)},
                'UI_BACKGROUND_COLOR': (55, 60, 55),
                'UI_PANEL_COLOR': (80, 85, 80, 240),
                'UI_BORDER_COLOR': (100, 110, 100),
                'FONT_PATH': 'assets/fonts/Tectoyaki.ttf'
            },
            'Information': {
                'GRID_LINE_COLOR': (60, 70, 80),
                'LAND_COLORS': {'Plains':(100, 140, 120), 'Water':(70, 90, 130), 'Mountains':(110, 115, 120), 'Desert':(180, 170, 150), 'Swamps':(80, 100, 90), 'Snowy':(190, 200, 210), 'Forest':(70, 110, 90), 'Border':(20, 25, 30), 'Objective':(100, 220, 220), 'Canal':(90, 110, 150)},
                'UI_BACKGROUND_COLOR': (23, 32, 42),
                'UI_PANEL_COLOR': (44, 62, 80, 235),
                'UI_BORDER_COLOR': (52, 73, 94),
                'FONT_PATH': 'assets/fonts/Tectoyaki.ttf'
            },
            'Future': {
                'GRID_LINE_COLOR': (0, 100, 100),
                'LAND_COLORS': {'Plains':(15, 35, 25), 'Water':(10, 20, 40), 'Mountains':(50, 60, 55), 'Desert':(70, 60, 40), 'Swamps':(20, 40, 30), 'Snowy':(180, 190, 195), 'Forest':(20, 50, 35), 'Border':(0, 0, 0), 'Objective':(200, 50, 200), 'Canal':(20, 50, 90)},
                'UI_BACKGROUND_COLOR': (5, 10, 15),
                'UI_PANEL_COLOR': (10, 25, 35, 240),
                'UI_BORDER_COLOR': (0, 180, 180),
                'FONT_PATH': 'assets/fonts/Tectoyaki.ttf'
            },
        }
        self.active_style_name = 'Primordial'
        self.active_style = self.styles[self.active_style_name]
        self.apply_style()

    def set_style(self, style_name, game_app_ref):
        if style_name in self.styles:
            self.active_style_name = style_name
            self.active_style = self.styles[style_name]
            self.apply_style()

            if game_app_ref:
                if hasattr(game_app_ref, 'map'):
                    game_app_ref.map.set_dirty()
                if hasattr(game_app_ref, 'ui_manager'):
                    game_app_ref.ui_manager.build_ui()
            print(f"Switched to style: {style_name}")
            return True
        return False

    def apply_style(self):
        for key, value in self.active_style.items():
            setattr(c, key, value)
        c._fonts_cache.clear()

    def to_dict(self):
        return {'active_style_name': self.active_style_name}

    def from_dict(self, data, game_app_ref):
        style_name = data.get('active_style_name', 'Primordial')
        self.set_style(style_name, game_app_ref)