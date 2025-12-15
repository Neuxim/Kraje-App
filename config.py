import pygame
import sys
import os
import json

ENCRYPTION_KEY = b'w3-G1Orqc9zYEN_xegp5Y2m2da2ytAP8kY5y0p2t2jE='
PLAYER_TURNS_DIR = "player_turns"

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

def darken_color(color, factor=0.7):
    return tuple(max(0, int(c_val * factor)) for c_val in color)

SCREEN_WIDTH = 1600
SCREEN_HEIGHT = 900
APP_TITLE = "DiploStrat"
FONT_PATH = resource_path('assets/fonts/Tectoyaki.ttf')

TILE_SIZE = 48
GRID_LINE_COLOR = (50, 50, 50)

COLOR_WHITE = (255, 255, 255); COLOR_BLACK = (0, 0, 0)
COLOR_RED = (200, 50, 50); COLOR_BLUE = (50, 100, 200)
COLOR_GREEN = (50, 150, 50); COLOR_YELLOW = (220, 200, 80)
COLOR_ORANGE = (220, 120, 40); COLOR_PURPLE = (150, 80, 200)
COLOR_CYAN = (80, 200, 200); COLOR_SAND = (210, 200, 150)

# --- NEW: Refined Nation Color Palette ---
NATION_COLORS = [
    (192, 57, 43),  # Alizarin Crimson
    (41, 128, 185), # Peter River Blue
    (39, 174, 96),  # Nephritis Green
    (241, 196, 15), # Sunflower Yellow
    (142, 68, 173), # Wisteria Purple
    (230, 126, 34), # Carrot Orange
    (26, 188, 156), # Turquoise
    (231, 76, 60),  # Pomegranate Red
    (52, 152, 219), # Belize Hole Blue
    (46, 204, 113), # Emerald Green
    (243, 156, 18), # Orange
    (155, 89, 182), # Amethyst Purple
    (211, 84, 0),   # Pumpkin Orange
    (22, 160, 133)  # Green Sea
]


LAND_COLORS = { 'Plains':(90, 175, 70), 'Water':(60, 80, 220), 'Mountains':(110, 110, 120), 'Desert':(240, 215, 150), 'Swamps':(80, 100, 50), 'Snowy':(230, 245, 255), 'Forest':(40, 120, 60), 'Border':(0, 0, 0), 'Objective':(255, 235, 50), 'Canal':(100, 130, 240), 'Territorial Water': (80, 110, 230) }
ARROW_ORDERS = {
    'Move': {'color': COLOR_BLUE, 'width': 3},
    'Attack': {'color': COLOR_RED, 'width': 4},
    'Support Attack': {'color': COLOR_GREEN, 'width': 2},
    'Support Defense': {'color': COLOR_CYAN, 'width': 2},
    'Suppressive Fire': {'color': COLOR_ORANGE, 'width': 3},
    'Plan': {'color': COLOR_PURPLE, 'width': 2},
    'Load/Unload': {'color': COLOR_YELLOW, 'width': 2}
}
NAVAL_TERRAIN = {'Water', 'Canal', 'Territorial Water'}

LOAD_COSTS = {
    'truck': 0.5,
    'ship': 1.0,
    'battleship': 0.0
}

FEATURE_BONUSES = {
    'fort': {'arm': 1},
    'quarry': {'arm': 1},
    'quarry_empty': {'arm': 1},
    'a_city': {'arm': 1},
    'a_village': {'arm': 1}
}

UNIT_TYPES = {
    "Humans": {
        'infantry': {'name':'Infantry', 'asset':'assets/units/Human/infantry.png', 'weight': 1, 'unit_class': 'land'},
        'gunner': {'name':'Gunner', 'asset':'assets/units/Human/gunner.png', 'weight': 1, 'unit_class': 'land'},
        'mech_light': {'name':'Light Mech', 'asset':'assets/units/Human/Mech_Light.png', 'weight': 2, 'unit_class': 'land'},
        'mech': {'name':'Mech', 'asset':'assets/units/Human/mech.png', 'weight': 4, 'unit_class': 'land'},
        'mech_artillery': {'name':'Artillery Mech', 'asset':'assets/units/Human/Mech_Artillery.png', 'unit_class': 'land'},
        'tank': {'name':'Tank', 'asset':'assets/units/Human/Tank.png', 'weight': 4, 'unit_class': 'land'},
        'artillery': {'name':'Artillery', 'asset':'assets/units/Human/artillery.png', 'weight': 1.5, 'unit_class': 'land'},
        'truck': {'name':'Truck', 'asset':'assets/units/Human/truck.png', 'weight_capacity': 4, 'max_units': 3, 'unit_class': 'land'},
        'battleship': {'name':'Battleship', 'asset':'assets/units/Human/battleship.png', 'weight_capacity': 12, 'max_units': 2, 'unit_class': 'naval'},
        'ship': {'name':'Ship', 'asset':'assets/units/Human/ship.png', 'weight_capacity': 8, 'max_units': 4, 'unit_class': 'naval'},
        'plane': {'name':'Plane', 'asset':'assets/units/Human/plane.png', 'unit_class': 'air'},
        'fryderyk': {'name':'Fryderyk', 'asset':'assets/units/Human/Fryderyk.png', 'unit_class': 'air'}
    },
    "G.O.C. (Ganzir)": {
        'GOC_MEKH': {'name':'Mekhane Followers', 'asset':'assets/units/GOC/GOC_MEKHANE.png', 'weight': 1, 'unit_class': 'land'},
        'GOC_INF': {'name':'G.O.C. Team', 'asset':'assets/units/GOC/GOC_Team.png', 'weight': 1, 'unit_class': 'land'}
    },
    "SCP": {
        'MTF': {'name':'MTF', 'asset':'assets/units/SCP/mtf.png', 'weight': 1, 'unit_class': 'land'},
        '049': {'name':'049', 'asset':'assets/units/SCP/SCP049.png', 'weight': 1, 'unit_class': 'land'},
        '096': {'name':'096', 'asset':'assets/units/SCP/SCP096.png', 'weight': 2, 'unit_class': 'land'},
        '173': {'name':'173', 'asset':'assets/units/SCP/SCP173.png', 'weight': 3, 'unit_class': 'land'},
        '682': {'name':'682', 'asset':'assets/units/SCP/SCP682.png', 'weight': 8, 'unit_class': 'land'},
        '939': {'name':'939', 'asset':'assets/units/SCP/SCP939.png', 'weight': 2, 'unit_class': 'land'},
        '1048_a': {'name':'1048-A', 'asset':'assets/units/SCP/SCP1048-1.png', 'weight': 0.5, 'unit_class': 'land'},
        '1048_b': {'name':'1048-B', 'asset':'assets/units/SCP/SCP1048-2.png', 'weight': 0.5, 'unit_class': 'land'},
        '1048_c': {'name':'1048-C', 'asset':'assets/units/SCP/SCP1048-3.png', 'weight': 1.5, 'unit_class': 'land'},
        '1048_d': {'name':'1048-D', 'asset':'assets/units/SCP/SCP1048-4.png', 'weight': 1, 'unit_class': 'land'}
    },
    "Flesh": {
        'Flesh_INF': {'name':'Hate', 'asset':'assets/units/Flesh/FleshINF.png', 'weight': 1, 'unit_class': 'land'},
        'Flesh_ART': {'name':'Despise', 'asset':'assets/units/Flesh/FleshART.png', 'weight': 1.5, 'unit_class': 'land'},
        'Flesh_MECH': {'name':'Loathe', 'asset':'assets/units/Flesh/FleshMECH.png', 'weight': 4, 'unit_class': 'land'},
        'Flesh_MASS': {'name':'Abominate', 'asset':'assets/units/Flesh/FleshMASS.png', 'weight': 6, 'unit_class': 'land'},
        'Flesh_TYRANID': {'name':'Execrate', 'asset':'assets/units/Flesh/FleshTYRANID.png', 'weight': 2, 'unit_class': 'land'},
        'Flesh_CITY': {'name':'Hell (c)', 'asset':'assets/units/Flesh/FleshCITY.png', 'unit_class': 'land'},
        'Flesh_VILLAGE': {'name':'Abyss (v)', 'asset':'assets/units/Flesh/FleshVILLAGE.png', 'unit_class': 'land'}
    },
    "Zombie": {
        'Zombie_INF': {'name':'Zombie', 'asset':'assets/units/Zombie/zombies.png', 'weight': 1, 'unit_class': 'land'},
        'Zombie_INFSMART': {'name':'Smarts', 'asset':'assets/units/Zombie/zombiesSmart.png', 'weight': 1, 'unit_class': 'land'},
        'Zombie_MECH': {'name':'Gigant', 'asset':'assets/units/Zombie/zombieGigant.png', 'weight': 5, 'unit_class': 'land'},
        'Zombie_FLYING': {'name':'Birds', 'asset':'assets/units/Zombie/zombieBirds.png', 'unit_class': 'air'},
        'Zombie_SHIP': {'name':'Whale', 'asset':'assets/units/Zombie/zombieWhale.png', 'weight_capacity': 6, 'max_units': 4, 'unit_class': 'naval'},
        'Zombie_BATTLESHIP': {'name':'Kraken', 'asset':'assets/units/Zombie/zombieKraken.png', 'weight_capacity': 12, 'max_units': 4, 'unit_class': 'naval'},
        'Zombie_Feature': {'name':'Zombie Base', 'asset':'assets/units/Zombie/zombieBase.png', 'unit_class': 'land'}
    },
    "Ancient": {
        'ancient_transporter': {'name':'Ox Baggage ', 'asset':'assets/units/Human/Ancient/transporter.png', 'weight_capacity': 4, 'max_units': 3, 'unit_class': 'land'},
        'ancient_warrior': {'name':'Hoplite', 'asset':'assets/units/Human/Ancient/warrior.png', 'weight': 1, 'unit_class': 'land'},
        'ancient_ranged': {'name':'Slinger', 'asset':'assets/units/Human/Ancient/ranged.png', 'weight': 1, 'unit_class': 'land'},
        'ancient_air': {'name':'Gigant Eagle', 'asset':'assets/units/Human/Ancient/air.png', 'unit_class': 'air'},
        'ancient_chariot': {'name':'Chariot', 'asset':'assets/units/Human/Ancient/chariot.png', 'weight': 5, 'unit_class': 'land'},
        'ancient_elephant': {'name':'War Elephant', 'asset':'assets/units/Human/Ancient/elephant.png', 'weight': 8, 'unit_class': 'land'},
        'ancient_catapult_v2': {'name':'Early Catapult', 'asset':'assets/units/Human/Ancient/catapult.png','weight': 3, 'unit_class': 'land'},
        'ancient_raft': {'name':'Papirus Raft', 'asset':'assets/units/Human/Ancient/raft.png', 'weight_capacity': 8, 'max_units': 1, 'unit_class': 'naval'},
        'ancient_ship': {'name':'Brimere', 'asset':'assets/units/Human/Ancient/brimere.png', 'weight_capacity': 12, 'max_units': 2, 'unit_class': 'naval'},
        'ancient_trade': {'name':'Ancient Trader', 'asset':'assets/units/Human/Ancient/transporter.png', 'unit_class': 'land'},
    },
}
default_grid = [[0]*5 for _ in range(5)]; default_grid[2][2] = 9
default_stats = {'str': '1', 'arm': '0', 'sup': '0', 'spe': '0', 'cost': '0'}

for category in UNIT_TYPES.values():
    for unit_data in category.values():
        if 'stats' not in unit_data: unit_data['stats'] = default_stats.copy()
        if 'cost' not in unit_data['stats']: unit_data['stats']['cost'] = '0'
        if 'desc' not in unit_data: unit_data['desc'] = "No description available."
        if 'grid' not in unit_data: unit_data['grid'] = [row[:] for row in default_grid]

FEATURE_TYPES = {
    "Civilian": { 'city': {'name':'City', 'asset':'assets/features/city.png'}, 'a_city': {'name':'A. City', 'asset':'assets/features/A_city.png'}, 'village': {'name':'Village', 'asset':'assets/features/village.png'}, 'a_village': {'name':'A. Village', 'asset':'assets/features/A_village.png'}},
    "Industrial": { 'oil_rig': {'name':'Oil Rig', 'asset':'assets/features/oil_rig.png', 'is_naval': True}, 'quarry': {'name':'Quarry', 'asset':'assets/features/quarry.png'}, 'quarry_empty': {'name':'Used Quarry', 'asset':'assets/features/quarry_empty.png'}},
    "Military": {'fort': {'name':'Fort', 'asset':'assets/features/fort.png'}}
}

# --- NEW: Revamped UI Color Scheme ---
UI_BACKGROUND_COLOR = (23, 32, 42)    # Dark Slate Blue
UI_PANEL_COLOR = (44, 62, 80, 235)      # Wet Asphalt (with transparency)
UI_BORDER_COLOR = (52, 73, 94)      # Wet Asphalt (darker)
UI_FONT_COLOR = (236, 240, 241)   # Clouds (off-white)
UI_HIGHLIGHT_COLOR = (26, 188, 156)   # Turquoise
UI_BUTTON_COLOR = (52, 73, 94)      # Wet Asphalt (darker)
UI_BUTTON_HOVER_COLOR = (72, 93, 114)     # A slightly lighter Wet Asphalt
UI_MULTI_SELECT_COLOR = (52, 152, 219) # Peter River Blue
UI_SHADOW_COLOR = (20, 20, 25, 100) # Removed for flatter design, kept for compatibility


LOGIN_DATA_FILE = "user_login.json"
_assets = {}; _scaled_assets_cache = {}; _fonts_cache = {}

def get_asset(path):
    final_path = resource_path(path)
    if final_path not in _assets:
        try: _assets[final_path] = pygame.image.load(final_path).convert_alpha()
        except (pygame.error, FileNotFoundError):
            placeholder = pygame.Surface((64, 64), pygame.SRCALPHA); placeholder.fill((255, 0, 255))
            if 'fog_icon.png' in path:
                font = pygame.font.Font(None, 50)
                text_surf = font.render("F", True, COLOR_WHITE)
                placeholder.blit(text_surf, text_surf.get_rect(center=placeholder.get_rect().center))
            _assets[final_path] = placeholder
    return _assets[final_path]

def get_scaled_asset(path, size):
    if size < 1: return None, None
    cache_key = (path, int(size));
    if cache_key in _scaled_assets_cache: return _scaled_assets_cache[cache_key]
    original_asset = get_asset(path)
    try:
        scaled_asset = pygame.transform.smoothscale(original_asset, (int(size), int(size)))
        shadow_surf = scaled_asset.copy()
        shadow_surf.fill((0, 0, 0, 100), special_flags=pygame.BLEND_RGBA_MULT)
    except (ValueError, pygame.error): return None, None
    _scaled_assets_cache[cache_key] = (scaled_asset, shadow_surf)
    return scaled_asset, shadow_surf

def get_font(path, size):
    size = int(size)
    if size <= 0: return pygame.font.Font(None, 10)

    if path is None:
        cache_key = (None, size)
        if cache_key not in _fonts_cache:
            try:
                _fonts_cache[cache_key] = pygame.font.Font(None, size)
            except pygame.error as e:
                print(f"Error loading default font: {e}")
                return pygame.font.Font(None, 10)
        return _fonts_cache[cache_key]

    absolute_path = resource_path(path)
    cache_key = (absolute_path, size)

    if cache_key not in _fonts_cache:
        try:
            _fonts_cache[cache_key] = pygame.font.Font(absolute_path, size)
        except (pygame.error, FileNotFoundError) as e:
            print(f"--- FONT ERROR ---")
            print(f"Failed to load font: '{absolute_path}'")
            print(f"Error: {e}")
            print(f"Falling back to default font.")
            print(f"--------------------")
            _fonts_cache[cache_key] = pygame.font.Font(None, size)
            
    return _fonts_cache[cache_key]

def create_text_with_border(text, font, text_color, border_color, border_size=2, angle=0):
    text_surf_orig = font.render(text, True, text_color)
    border_surf_orig = font.render(text, True, border_color)

    if angle != 0:
        text_surf = pygame.transform.rotate(text_surf_orig, angle)
        border_surf = pygame.transform.rotate(border_surf_orig, angle)
    else:
        text_surf = text_surf_orig
        border_surf = border_surf_orig

    w, h = text_surf.get_size()
    composite_surf = pygame.Surface((w + border_size * 2, h + border_size * 2), pygame.SRCALPHA)

    for dx in range(-border_size, border_size + 1):
        for dy in range(-border_size, border_size + 1):
            if dx != 0 or dy != 0:
                composite_surf.blit(border_surf, (border_size + dx, border_size + dy))

    composite_surf.blit(text_surf, (border_size, border_size))
    return composite_surf

def get_unit_data(unit_key):
    for category in UNIT_TYPES.values():
        if unit_key in category:
            return category[unit_key]
    return None

def preload_assets():
    for category in UNIT_TYPES.values():
        for unit_data in category.values(): get_asset(unit_data['asset'])
    for category in FEATURE_TYPES.values():
        for feature_data in category.values(): get_asset(feature_data['asset'])
    asset_names = ['paint_icon', 'terrain_icon', 'unit_icon', 'feature_icon', 'arrow_icon', 'nation_icon',
                   'save_icon', 'load_icon', 'clear_arrows_icon', 'text_display_icon', 'encyclopedia_icon', 
                   'export_icon', 'find_icon', 'layers_icon', 'tech_tree_icon', 'logout_icon', 'fog_icon',
                   'add_note_icon', 'manpower_icon', 'dmg_icon', 'def_icon', 'sup_icon',
                   'spe_icon', 'cost_icon', 'weight_icon']
    for name in asset_names: get_asset(f'assets/icons/{name}.png')

def save_encyclopedia_defaults(filepath):
    from save_load_manager import save_encyclopedia_data as save_data
    save_data(UNIT_TYPES)

def load_encyclopedia_data():
    global UNIT_TYPES
    user_data_filename = 'encyclopedia_data.json'
    
    user_data_path = user_data_filename
    if 'ANDROID_ARGUMENT' in os.environ:
        user_data_path = os.path.join(os.environ['ANDROID_PRIVATE'], user_data_filename)

    bundled_data_path = resource_path(user_data_filename)

    data_to_load_path = None
    if os.path.exists(user_data_path):
        data_to_load_path = user_data_path
        print(f"Loading user encyclopedia data from: {user_data_path}")
    elif os.path.exists(bundled_data_path):
        data_to_load_path = bundled_data_path
        print(f"Loading bundled encyclopedia data from: {bundled_data_path}")

    if data_to_load_path:
        try:
            with open(data_to_load_path, 'r') as f:
                loaded_data = json.load(f)
                
                flat_unit_types = {}
                for category, units in UNIT_TYPES.items():
                    for unit_key, unit_data in units.items():
                        flat_unit_types[unit_key] = unit_data

                for category, units in loaded_data.items():
                    if category not in UNIT_TYPES: UNIT_TYPES[category] = {}
                    for unit_key, unit_data in units.items():
                        if unit_key not in UNIT_TYPES[category]:
                             UNIT_TYPES[category][unit_key] = {}
                        if 'stats' in unit_data and unit_key in flat_unit_types and 'stats' in flat_unit_types[unit_key]:
                             flat_unit_types[unit_key]['stats'].update(unit_data['stats'])
                             del unit_data['stats']
                        
                        UNIT_TYPES[category][unit_key].update(unit_data)

        except Exception as e:
            print(f"Error loading '{data_to_load_path}': {e}. Using default data.")
    else:
        print("Encyclopedia data not found. Creating default data file.")
        save_encyclopedia_defaults(user_data_path)
        
        
def generate_cloud_texture(width, height):
    """Generates a procedural cloud/noise texture for Fog of War."""
    surface = pygame.Surface((width, height), pygame.SRCALPHA)
    import random
    
    # Fill with base dark fog
    surface.fill((20, 20, 25, 230))
    
    # Draw random "puffs" to simulate clouds (subtractive alpha to make holes, or additive color)
    # Here we draw slightly lighter blobs to create texture
    for _ in range(100):
        x = random.randint(0, width)
        y = random.randint(0, height)
        radius = random.randint(20, 60)
        alpha = random.randint(10, 30)
        # Draw a soft circle
        temp_surf = pygame.Surface((radius*2, radius*2), pygame.SRCALPHA)
        pygame.draw.circle(temp_surf, (40, 45, 55, alpha), (radius, radius), radius)
        surface.blit(temp_surf, (x - radius, y - radius))
        
    return surface

def get_fog_texture():
    # Try to load file, fallback to generator
    path = resource_path('assets/fog_texture.png')
    if os.path.exists(path):
        try:
            return pygame.image.load(path).convert_alpha()
        except: pass
    return generate_cloud_texture(512, 512)