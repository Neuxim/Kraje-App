import pygame
import math
import config as c

def draw_dashed_line(surface, color, start_pos, end_pos, width=1, dash_length=10):
    dx, dy = end_pos[0] - start_pos[0], end_pos[1] - start_pos[1]
    distance = math.hypot(dx, dy)
    if distance == 0: return
    
    scaled_dash = dash_length
    if scaled_dash == 0: return

    dashes = int(distance / scaled_dash)
    if dashes == 0:
        pygame.draw.line(surface, color, start_pos, end_pos, int(width))
        return

    for i in range(dashes):
        start = (start_pos[0] + (dx * i / dashes), start_pos[1] + (dy * i / dashes))
        end = (start_pos[0] + (dx * (i + 0.5) / dashes), start_pos[1] + (dy * (i + 0.5) / dashes))
        if (end[0]-start[0])**2 + (end[1]-start[1])**2 > 1.0:
             pygame.draw.line(surface, color, start, end, int(width))

class Tile:
    def __init__(self, grid_x, grid_y, land_type='Plains'):
        self.grid_x, self.grid_y = grid_x, grid_y
        self.land_type = land_type
        self.nation_owner_id = None
        self.visibility_state = 2
        self.rotation = 0

    def to_dict(self):
        land_type_to_save = 'Water' if self.land_type == 'Territorial Water' else self.land_type
        return {'grid_x': self.grid_x, 'grid_y': self.grid_y, 'land_type': land_type_to_save, 'nation_owner_id': self.nation_owner_id, 'visibility_state': self.visibility_state}

    @staticmethod
    def from_dict(data):
        tile = Tile(data['grid_x'], data['grid_y'], data['land_type'])
        tile.nation_owner_id = data['nation_owner_id']
        if 'visibility_state' in data:
            tile.visibility_state = data.get('visibility_state', 2)
        else: # Legacy support
            is_fogged = data.get('is_fogged', True)
            tile.visibility_state = 2 if is_fogged else 0
        tile.rotation = data.get('rotation', 0)
        return tile

class Camera:
    def __init__(self):
        self.x, self.y = 0, 0
        self.target_x, self.target_y = 0, 0
        self.zoom, self.target_zoom = 1.0, 1.0
        self.lerp_speed = 0.2

    def update(self):
        # Apply lerp for smooth panning and zooming
        self.x += (self.target_x - self.x) * self.lerp_speed
        self.y += (self.target_y - self.y) * self.lerp_speed
        self.zoom += (self.target_zoom - self.zoom) * self.lerp_speed

    def pan(self, dx, dy):
        self.target_x += dx
        self.target_y += dy
    
    def center_on(self, world_x, world_y):
        self.target_x = c.SCREEN_WIDTH / 2 - (world_x * self.target_zoom)
        self.target_y = c.SCREEN_HEIGHT / 2 - (world_y * self.target_zoom)

    def adjust_zoom(self, scale_factor, mouse_pos):
        # --- MODIFIED: Corrected zoom logic to prevent "jumping" ---
        mx, my = mouse_pos
        
        # 1. Figure out which point in the world is under the mouse BEFORE the zoom
        world_x_before, world_y_before = self.screen_to_world(mx, my)

        # 2. Immediately calculate the new target zoom
        self.target_zoom = max(0.2, min(self.target_zoom * scale_factor, 4.0))

        # 3. Figure out the new camera position (target_x, target_y) that will keep the
        #    point under the mouse stationary.
        #    The formula is: new_cam_x = mouse_screen_x - world_x * new_zoom
        self.target_x = mx - world_x_before * self.target_zoom
        self.target_y = my - world_y_before * self.target_zoom


    def screen_to_world(self, sx, sy):
        return (sx - self.x) / self.zoom, (sy - self.y) / self.zoom

    def world_to_screen(self, wx, wy):
        return wx * self.zoom + self.x, wy * self.zoom + self.y

    def grid_to_world(self, gx, gy):
        return gx * c.TILE_SIZE, gy * c.TILE_SIZE

    def world_to_grid(self, wx, wy):
        return math.floor(wx / c.TILE_SIZE), math.floor(wy / c.TILE_SIZE)
    
    def screen_to_grid(self, sx, sy):
        return self.world_to_grid(*self.screen_to_world(sx, sy))

class Map:
    def __init__(self, width, height):
        self.width, self.height = width, height
        self.grid = [[Tile(x, y) for y in range(height)] for x in range(width)]
        self.camera = Camera()
        self.map_cache_surface = None
        self.fog_surface = None
        self.is_dirty = True
        self.fog_is_dirty = True
        self.fog_surface = None
        self.fog_texture = c.get_fog_texture()
        self.is_dirty = True
        self.fog_is_dirty = True

    def get_tile(self, grid_x, grid_y):
        if 0 <= grid_x < self.width and 0 <= grid_y < self.height:
            return self.grid[grid_x][grid_y]
        return None
        
    def set_dirty(self):
        self.is_dirty = True

    def set_fog_dirty(self):
        self.fog_is_dirty = True

    def _build_map_cache(self, nations, features, alliance_mode=False, alliances=None):
        print(f"Rebuilding map cache (Alliance Mode: {alliance_mode})...")
        if self.width <= 0 or self.height <= 0:
            self.map_cache_surface = None
            return
        
        self.map_cache_surface = pygame.Surface((self.width * c.TILE_SIZE, self.height * c.TILE_SIZE))
        
        feature_locations = {(f.grid_x, f.grid_y) for f in features}

        def get_tile_color(tile):
            if not tile.nation_owner_id: return None
            if alliance_mode and alliances:
                for alliance_name, members in alliances.items():
                    if tile.nation_owner_id in members:
                        h = abs(hash(alliance_name))
                        return pygame.Color((h & 0xFF), ((h >> 8) & 0xFF), ((h >> 16) & 0xFF))
            if tile.nation_owner_id in nations:
                return pygame.Color(*nations[tile.nation_owner_id]['color'])
            return None

        for gx in range(self.width):
            for gy in range(self.height):
                tile = self.grid[gx][gy]
                rect = pygame.Rect(gx * c.TILE_SIZE, gy * c.TILE_SIZE, c.TILE_SIZE, c.TILE_SIZE)
                
                land_key = tile.land_type
                if land_key == 'Territorial Water' and land_key not in c.LAND_COLORS: land_key = 'Water'
                base_color = pygame.Color(c.LAND_COLORS.get(land_key, c.LAND_COLORS['Plains']))
                owner_color_obj = get_tile_color(tile)
                
                if tile.land_type in c.NAVAL_TERRAIN:
                    self.map_cache_surface.fill(base_color, rect)
                    if owner_color_obj:
                        overlay = pygame.Surface((c.TILE_SIZE, c.TILE_SIZE), pygame.SRCALPHA)
                        overlay.fill((owner_color_obj.r, owner_color_obj.g, owner_color_obj.b, 35))
                        self.map_cache_surface.blit(overlay, rect.topleft)
                else:
                    if owner_color_obj:
                        final_color = base_color.lerp(owner_color_obj, 0.675)
                        self.map_cache_surface.fill(final_color, rect)
                    else:
                        self.map_cache_surface.fill(base_color, rect)

                # Terrain Blending (Soft Edges)
                border_alpha = 50 
                blend_width = 4 

                neighbors = [((gx+1, gy), 'right'), ((gx, gy+1), 'down')]
                
                for (nx, ny), direction in neighbors:
                    if nx < self.width and ny < self.height:
                        n_tile = self.grid[nx][ny]
                        if n_tile.land_type != tile.land_type:
                            n_key = n_tile.land_type
                            if n_key == 'Territorial Water' and n_key not in c.LAND_COLORS: n_key = 'Water'
                            n_color = c.LAND_COLORS.get(n_key, c.COLOR_BLACK)
                            
                            current_alpha = 30 if owner_color_obj else border_alpha

                            blend_surf = pygame.Surface((c.TILE_SIZE, blend_width) if direction == 'down' else (blend_width, c.TILE_SIZE), pygame.SRCALPHA)
                            
                            if direction == 'down':
                                for i in range(blend_width):
                                    alpha = int(current_alpha * (i / blend_width))
                                    pygame.draw.line(blend_surf, (*n_color, alpha), (0, i), (c.TILE_SIZE, i))
                                self.map_cache_surface.blit(blend_surf, (rect.left, rect.bottom - blend_width))
                            else: # right
                                for i in range(blend_width):
                                    alpha = int(current_alpha * (i / blend_width))
                                    pygame.draw.line(blend_surf, (*n_color, alpha), (i, 0), (i, c.TILE_SIZE))
                                self.map_cache_surface.blit(blend_surf, (rect.right - blend_width, rect.top))

        # Step 2: Draw grid lines
        grid_line_color = c.GRID_LINE_COLOR
        for gx in range(self.width + 1):
            pygame.draw.line(self.map_cache_surface, grid_line_color, (gx * c.TILE_SIZE, 0), (gx * c.TILE_SIZE, self.height * c.TILE_SIZE))
        for gy in range(self.height + 1):
            pygame.draw.line(self.map_cache_surface, grid_line_color, (0, gy * c.TILE_SIZE), (self.width * c.TILE_SIZE, gy * c.TILE_SIZE))

        # Step 3: Draw nation borders
        border_width = 4
        dark_color_cache = {}
        for gx in range(self.width):
            for gy in range(self.height):
                tile = self.get_tile(gx, gy)
                if not tile or not tile.nation_owner_id or tile.nation_owner_id not in nations: continue
                owner_id = tile.nation_owner_id
                
                if alliance_mode and alliances:
                     visual_color_obj = get_tile_color(tile)
                     nation_color_tuple = (visual_color_obj.r, visual_color_obj.g, visual_color_obj.b) if visual_color_obj else nations[owner_id]['color']
                else:
                     nation_color_tuple = nations[owner_id]['color']

                if nation_color_tuple not in dark_color_cache: dark_color_cache[nation_color_tuple] = c.darken_color(nation_color_tuple)
                border_color = dark_color_cache[nation_color_tuple]

                neighbors_dict = {'up': self.get_tile(gx, gy-1), 'down': self.get_tile(gx, gy+1), 'left': self.get_tile(gx-1, gy), 'right': self.get_tile(gx+1, gy)}
                for neighbor_key, neighbor in neighbors_dict.items():
                    draw_border = False
                    if not neighbor: draw_border = True 
                    elif neighbor.nation_owner_id != owner_id:
                        if alliance_mode and alliances:
                            my_alliance = next((a for a, m in alliances.items() if owner_id in m), None)
                            their_alliance = next((a for a, m in alliances.items() if neighbor.nation_owner_id in m), None)
                            if my_alliance != their_alliance: draw_border = True
                        else: draw_border = True

                    if draw_border:
                        if neighbor_key == 'up': start, end = (gx*c.TILE_SIZE, gy*c.TILE_SIZE), ((gx+1)*c.TILE_SIZE, gy*c.TILE_SIZE)
                        elif neighbor_key == 'down': start, end = (gx*c.TILE_SIZE, (gy+1)*c.TILE_SIZE), ((gx+1)*c.TILE_SIZE, (gy+1)*c.TILE_SIZE)
                        elif neighbor_key == 'left': start, end = (gx*c.TILE_SIZE, gy*c.TILE_SIZE), (gx*c.TILE_SIZE, (gy+1)*c.TILE_SIZE)
                        else: start, end = ((gx+1)*c.TILE_SIZE, gy*c.TILE_SIZE), ((gx+1)*c.TILE_SIZE, (gy+1)*c.TILE_SIZE)

                        is_dashed = tile.land_type == 'Territorial Water' and (not neighbor or neighbor.land_type in c.NAVAL_TERRAIN)
                        if is_dashed: draw_dashed_line(self.map_cache_surface, border_color, start, end, border_width)
                        else: pygame.draw.line(self.map_cache_surface, border_color, start, end, border_width)

        self.is_dirty = False
        print("Map cache rebuild complete.")

    def draw_animated_coastlines(self, screen):
        # Calculate dynamic foam width/offset
        import math
        time = pygame.time.get_ticks()
        wave_offset = math.sin(time * 0.003) * 1.25 + 1 # 0.5 to 3.5 px
        
        # Only draw visible coastlines to save performance
        cam = self.camera
        view_start_gx, view_start_gy = cam.screen_to_grid(0,0)
        view_end_gx, view_end_gy = cam.screen_to_grid(c.SCREEN_WIDTH, c.SCREEN_HEIGHT)
        
        # Color of the "Smashing Water" (Foam) - Lighter sand/white
        foam_color = (230, 225, 200)
        
        base_size = 2 # "Super small" width
        
        for (gx, gy), direction in self.coastline_data:
            if not (view_start_gx-1 <= gx <= view_end_gx+1 and view_start_gy-1 <= gy <= view_end_gy+1):
                continue
            
            # Tile world coords
            wx, wy = gx * c.TILE_SIZE, gy * c.TILE_SIZE
            sx, sy = cam.world_to_screen(wx, wy)
            ts = c.TILE_SIZE * cam.zoom # Scaled tile size
            
            current_width = (base_size + wave_offset) * cam.zoom
            
            rect = None
            if direction == 'top':
                rect = pygame.Rect(sx, sy, ts, current_width)
            elif direction == 'bottom':
                rect = pygame.Rect(sx, sy + ts - current_width, ts, current_width)
            elif direction == 'left':
                rect = pygame.Rect(sx, sy, current_width, ts)
            elif direction == 'right':
                rect = pygame.Rect(sx + ts - current_width, sy, current_width, ts)
            elif direction == 'tl':
                # Corner triangle or small square
                rect = pygame.Rect(sx, sy, current_width, current_width)
            elif direction == 'tr':
                rect = pygame.Rect(sx + ts - current_width, sy, current_width, current_width)
            elif direction == 'bl':
                rect = pygame.Rect(sx, sy + ts - current_width, current_width, current_width)
            elif direction == 'br':
                rect = pygame.Rect(sx + ts - current_width, sy + ts - current_width, current_width, current_width)
                
            if rect:
                pygame.draw.rect(screen, foam_color, rect)

    def _build_fog_cache(self, user_mode):
        print("Rebuilding fog cache with texture...")
        if self.width <= 0 or self.height <= 0:
            self.fog_surface = None
            return
            
        self.fog_surface = pygame.Surface((self.width * c.TILE_SIZE, self.height * c.TILE_SIZE), pygame.SRCALPHA)
        
        # Tile the fog texture across the map
        if self.fog_texture:
            tex_w, tex_h = self.fog_texture.get_size()
            for x in range(0, self.fog_surface.get_width(), tex_w):
                for y in range(0, self.fog_surface.get_height(), tex_h):
                    self.fog_surface.blit(self.fog_texture, (x, y))
        else:
            self.fog_surface.fill((20, 20, 25, 230)) # Fallback

        # Cut holes for visible areas
        # We use a mask approach: Create a surface for the "holes", fill it with opaque (to keep fog), 
        # then clear rects (make transparent) where visible.
        # However, pygame compositing is tricky. Easier method:
        # 1. Create a mask surface (all white/opaque)
        # 2. Draw black/transparent rects on visible tiles
        # 3. Multiply fog_surface alpha by this mask
        
        mask_surface = pygame.Surface(self.fog_surface.get_size(), pygame.SRCALPHA)
        mask_surface.fill((255, 255, 255, 255)) # Fully opaque mask
        
        for gx in range(self.width):
            for gy in range(self.height):
                tile = self.get_tile(gx, gy)
                if not tile: continue
                
                rect = pygame.Rect(gx * c.TILE_SIZE, gy * c.TILE_SIZE, c.TILE_SIZE, c.TILE_SIZE)
                
                if tile.visibility_state == 0:
                    pygame.draw.rect(mask_surface, (0, 0, 0, 0), rect) 
                elif tile.visibility_state == 1:
                    if user_mode != 'editor':
                        pygame.draw.rect(mask_surface, (255, 255, 255, 100), rect)
        
        self.fog_surface.blit(mask_surface, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        
        if user_mode == 'editor':
            self.fog_surface.fill((0,0,0,0))

        self.fog_is_dirty = False
        print("Map cache rebuild complete.")


    def _build_fog_cache(self, user_mode):
        print("Rebuilding fog cache...")
        if self.width <= 0 or self.height <= 0:
            self.fog_surface = None
            return
            
        self.fog_surface = pygame.Surface((self.width * c.TILE_SIZE, self.height * c.TILE_SIZE), pygame.SRCALPHA)
        self.fog_surface.fill((0,0,0,0))

        FOG_COLOR = (20, 20, 25)
        MEMORY_FOG_ALPHA = int(255 * 0.25)
        ADMIN_FOG_ALPHA = int(255 * 0.25)
        
        for gx in range(self.width):
            for gy in range(self.height):
                tile = self.get_tile(gx, gy)
                if not tile or tile.visibility_state == 0: continue
                
                rect = pygame.Rect(gx * c.TILE_SIZE, gy * c.TILE_SIZE, c.TILE_SIZE, c.TILE_SIZE)
                
                if tile.visibility_state == 2: # Full Fog
                    if user_mode == 'editor':
                        self.fog_surface.fill((*FOG_COLOR, ADMIN_FOG_ALPHA), rect)
                    else:
                        self.fog_surface.fill(FOG_COLOR, rect)
                elif tile.visibility_state == 1: # Memory Fog
                    if user_mode != 'editor':
                        self.fog_surface.fill((*FOG_COLOR, MEMORY_FOG_ALPHA), rect)

        self.fog_is_dirty = False

    def draw(self, screen, nations, user_mode, features=[], is_export=False, alliance_mode=False, alliances=None):
        if not is_export:
            self.camera.update()
        
        if self.is_dirty or self.map_cache_surface is None:
            self._build_map_cache(nations, features, alliance_mode, alliances)
        
        if self.fog_is_dirty or self.fog_surface is None:
            self._build_fog_cache(user_mode)

        if self.map_cache_surface:
            if is_export:
                screen.blit(self.map_cache_surface, (0, 0))
            else:
                self.draw_scaled_portion(screen, self.map_cache_surface)
        
        if not is_export and self.fog_surface:
            self.draw_scaled_portion(screen, self.fog_surface)

    def draw_scaled_portion(self, screen, source_surface):
        """
        Calculates the visible portion of a source surface (like the map or fog cache)
        and blits only that part, scaled, to the screen. This is the core of the
        performance optimization.
        """
        cam = self.camera
        if cam.zoom <= 0: return

        # 1. Determine the rectangle of the world visible on screen
        view_rect_world = pygame.Rect(
            cam.screen_to_world(0, 0),
            (c.SCREEN_WIDTH / cam.zoom, c.SCREEN_HEIGHT / cam.zoom)
        )

        # 2. Find the intersection of the view and the actual map boundaries
        clipped_rect = view_rect_world.clip(source_surface.get_rect())

        if clipped_rect.width == 0 or clipped_rect.height == 0:
            return

        # 3. Create a temporary subsurface of only the visible part
        try:
            source_subsurface = source_surface.subsurface(clipped_rect)
        except ValueError: # Can happen if rect is somehow invalid
            return

        # 4. Calculate the size this subsurface should be on the screen
        dest_size = (
            int(clipped_rect.width * cam.zoom),
            int(clipped_rect.height * cam.zoom)
        )

        if dest_size[0] <= 0 or dest_size[1] <= 0:
            return

        # 5. Scale *only the small subsurface* up to the destination size
        scaled_subsurface = pygame.transform.scale(source_subsurface, dest_size)

        # 6. Determine where on the screen to draw this scaled piece
        dest_pos_on_screen = cam.world_to_screen(clipped_rect.left, clipped_rect.top)

        # 7. Blit the final, scaled piece to the screen
        screen.blit(scaled_subsurface, dest_pos_on_screen)


    def to_dict(self, compact=False):
        if not compact:
            return {'width': self.width, 'height': self.height, 'grid': [[t.to_dict() for t in r] for r in self.grid]}
        
        if not hasattr(c, 'LAND_TYPE_TO_ID'):
            c.LAND_TYPE_TO_ID = {name: i for i, name in enumerate(c.LAND_COLORS.keys())}
        
        compact_grid = []
        for x in range(self.width):
            col = []
            for y in range(self.height):
                tile = self.grid[x][y]

                land_type_to_save = 'Water' if tile.land_type == 'Territorial Water' else tile.land_type
                land_id = c.LAND_TYPE_TO_ID.get(land_type_to_save, 0)
                
                nation_id = tile.nation_owner_id or 0
                fog_state = tile.visibility_state
                
                if land_id == 0 and nation_id == 0 and fog_state == 2:
                    col.append(0)
                else:
                    col.append([land_id, nation_id, fog_state])
            compact_grid.append(col)
        return {'w': self.width, 'h': self.height, 'g': compact_grid}

    @staticmethod
    def from_dict(data):
        is_compact = 'w' in data 

        if not is_compact:
            new_map = Map(data['width'], data['height'])
            new_map.grid = [[Tile.from_dict(td) for td in row] for row in data['grid']]
            for row in new_map.grid:
                for tile in row:
                    if tile.land_type not in c.LAND_COLORS:
                        tile.land_type = 'Plains'
            return new_map
        
        if not hasattr(c, 'ID_TO_LAND_TYPE'):
             c.LAND_TYPE_TO_ID = {name: i for i, name in enumerate(c.LAND_COLORS.keys())}
             c.ID_TO_LAND_TYPE = {i: name for name, i in c.LAND_TYPE_TO_ID.items()}

        if not data or 'w' not in data or 'h' not in data or 'g' not in data:
            print("Warning: Map data is missing required keys (w, h, g). Creating default map.")
            return Map(50, 50)

        w, h = data['w'], data['h']
        grid_data = data['g']
        new_map = Map(w, h)

        if not isinstance(grid_data, list) or len(grid_data) != w:
            print(f"Warning: Map data grid width mismatch. Declared: {w}, Found: {len(grid_data)}. Map may be incomplete.")

        for x in range(w):
            if x >= len(grid_data) or not isinstance(grid_data[x], list):
                continue

            for y in range(h):
                if y >= len(grid_data[x]):
                    continue
                
                tile = new_map.grid[x][y]
                tile_data = grid_data[x][y]

                if isinstance(tile_data, int) and tile_data == 0:
                    continue 
                
                elif isinstance(tile_data, int): # Legacy single-int format
                    tile.land_type = c.ID_TO_LAND_TYPE.get(tile_data, 'Plains')
                
                elif isinstance(tile_data, list) and tile_data:
                    if len(tile_data) >= 3: # New format [land, nation, fog_state]
                        tile.land_type = c.ID_TO_LAND_TYPE.get(tile_data[0], 'Plains')
                        if tile_data[1] != 0: tile.nation_owner_id = tile_data[1]
                        tile.visibility_state = tile_data[2]
                    elif len(tile_data) >= 2: # Legacy format [land, nation]
                        tile.land_type = c.ID_TO_LAND_TYPE.get(tile_data[0], 'Plains')
                        if tile_data[1] != 0: tile.nation_owner_id = tile_data[1]
        return new_map