import os
import json
import tkinter as tk
from tkinter import filedialog
from PIL import Image
import config as c

tk.Tk().withdraw()

COLOR_TO_LAND_TYPE = {v: k for k, v in c.LAND_COLORS.items()}

def create_map_from_image(image_path):
    print(f"Processing image: {image_path}...")
    try:
        image = Image.open(image_path)
        image = image.convert('RGB') 
    except FileNotFoundError:
        print(f"Error: Image file not found at '{image_path}'")
        return None
    except Exception as e:
        print(f"Error: Could not open or read image file. Reason: {e}")
        return None

    width, height = image.size
    print(f"Image dimensions detected: {width}x{height}. This will be the map size.")

    pixel_data = image.load()

    grid_data = []
    for x in range(width):
        column = []
        for y in range(height):
            rgb_tuple = pixel_data[x, y]
            land_type = COLOR_TO_LAND_TYPE.get(rgb_tuple, 'Plains')
            tile_dict = {
                'grid_x': x,
                'grid_y': y,
                'land_type': land_type,
                'nation_owner_id': None
            }
            column.append(tile_dict)
        grid_data.append(column)
    
    print("Pixel data converted to map grid successfully.")

    game_state = {
        'map_data': {
            'width': width,
            'height': height,
            'grid': grid_data
        },
        'nations': {},
        'units': [],
        'features': [],
        'arrows': [],
        'show_territory_names': False
    }

    return game_state

def main():
    print("--- Image to Map Converter for Strategic Map Creator ---")
    
    build_dir = 'assets/build'
    if not os.path.exists(build_dir):
        print(f"Creating source directory: '{build_dir}'")
        os.makedirs(build_dir)
        print("Please place the PNG map images you want to convert into this folder.")
        with open(os.path.join(build_dir, 'readme.txt'), 'w') as f:
            f.write("Place your map template images (PNG format) in this folder.\n")
            f.write("Then, run the image_to_map.py script to convert them to .json map files.\n\n")
            f.write("Each pixel's color in the image should correspond to a terrain type color in config.py.")
        return
    
    print(f"Please select a map image from the '{build_dir}' folder.")

    input_path = filedialog.askopenfilename(
        title="Select Map Image (PNG)",
        initialdir=os.path.abspath(build_dir),
        filetypes=[("PNG Images", "*.png"), ("All Files", "*.*")]
    )

    if not input_path:
        print("No file selected. Aborting.")
        return

    map_data = create_map_from_image(input_path)

    if not map_data:
        print("Map generation failed.")
        return

    output_path = filedialog.asksaveasfilename(
        title="Save Generated Map As...",
        defaultextension=".json",
        filetypes=[("JSON Map Files", "*.json"), ("All Files", "*.*")],
        initialfile=os.path.splitext(os.path.basename(input_path))[0] + '.json'
    )

    if not output_path:
        print("Save cancelled. Aborting.")
        return

    try:
        with open(output_path, 'w') as f:
            json.dump(map_data, f, indent=4)
        print(f"\n--- SUCCESS! ---")
        print(f"Map successfully saved to: {output_path}")
        print("You can now load this file in the main application.")
    except Exception as e:
        print(f"Error: Could not save the file. Reason: {e}")

if __name__ == "__main__":
    main()