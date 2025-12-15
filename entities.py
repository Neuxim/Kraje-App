import pygame
import math
import uuid
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

class BaseEntity:
    def __init__(self):
        self.delete_button_rect = None
        self.font = pygame.font.Font(None, 20)
        self.visible = True

    def draw_delete_button(self, screen, top_right_pos):
        self.delete_button_rect = pygame.Rect(top_right_pos[0], top_right_pos[1] - 16, 16, 16)
        pygame.draw.rect(screen, (200, 20, 20), self.delete_button_rect)
        pygame.draw.rect(screen, c.COLOR_WHITE, self.delete_button_rect, 1)
        text_surf = self.font.render("X", True, c.COLOR_WHITE)
        screen.blit(text_surf, text_surf.get_rect(center=self.delete_button_rect.center))

    def draw_shadow(self, screen, shadow_surf, rect):
        if shadow_surf:
            screen.blit(shadow_surf, rect.move(2, 3))


class Unit(BaseEntity):
    def __init__(self, unit_type, grid_x, grid_y, nation_id):
        super().__init__()
        self.id = str(uuid.uuid4())
        self.unit_type, self.grid_x, self.grid_y, self.nation_id = unit_type, grid_x, grid_y, nation_id
        self.rotation = 0
        self.is_upgrading = False
        self.status = 'active'
        self.properties = c.get_unit_data(unit_type)
        if not self.properties:
            raise ValueError(f"Unit type '{unit_type}' not found.")

        self.asset_path = self.properties['asset']
        self.weight = self.properties.get('weight')
        self.weight_capacity = self.properties.get('weight_capacity')
        self.max_units = self.properties.get('max_units')
        self.unit_class = self.properties.get('unit_class', 'land')
        self.carried_units = []
        self.display_x, self.display_y = grid_x * c.TILE_SIZE, grid_y * c.TILE_SIZE

    def get_effective_stats(self, app):
        # Start with base stats from config
        base_stats = {}
        for key, val in self.properties.get('stats', {}).items():
            try:
                # Handle potential string stats like '2x1'
                if isinstance(val, str) and 'x' in val:
                     base_stats[key] = val
                else:
                     base_stats[key] = float(val)
            except (ValueError, TypeError):
                base_stats[key] = val # Keep as string if not convertible
        
        bonuses = {}
        assignments = {} # For the '=' operator
        
        # Add bonuses from map features
        feature = app.find_entity_at(self.grid_x, self.grid_y, None, ignore_arrows=True, ignore_units=True)
        if isinstance(feature, MapFeature) and feature.feature_type in c.FEATURE_BONUSES:
            bonus_data = c.FEATURE_BONUSES[feature.feature_type]
            for stat, bonus in bonus_data.items():
                if stat in base_stats and isinstance(base_stats[stat], (int, float)):
                    bonuses[stat] = bonuses.get(stat, 0) + bonus

        # Add bonuses from technology
        nation = app.nations.get(self.nation_id)
        if nation:
            researched_techs = nation.get('researched_techs', [])
            for tech_id in researched_techs:
                tech_data = app.tech_tree.get(tech_id)
                if tech_data and 'bonuses' in tech_data and isinstance(tech_data['bonuses'], dict):
                    bonuses_data = tech_data['bonuses']
                    unit_keys = bonuses_data.get('unit_keys', [])
                    unit_class = bonuses_data.get('unit_class', '')
                    applies_to_unit = not unit_keys or self.unit_type in unit_keys
                    applies_to_class = not unit_class or self.unit_class == unit_class
                    
                    if applies_to_unit and applies_to_class:
                        modifiers_dict = bonuses_data.get('modifiers', {})
                        if isinstance(modifiers_dict, dict):
                            for stat, mod_val_str in modifiers_dict.items():
                                if stat in base_stats and isinstance(base_stats[stat], (int, float)):
                                    try:
                                        mod_val_str = str(mod_val_str).strip()
                                        if not mod_val_str: continue

                                        op = mod_val_str[0]
                                        val = float(mod_val_str[1:])
                                        
                                        if op == '=':
                                            assignments[stat] = val
                                        elif op == '+':
                                            bonuses[stat] = bonuses.get(stat, 0) + val
                                        elif op == '-':
                                            bonuses[stat] = bonuses.get(stat, 0) - val
                                    except (ValueError, TypeError, IndexError):
                                        continue
        
        # Apply bonuses first
        final_stats = base_stats.copy()
        for stat, bonus_val in bonuses.items():
            if stat in final_stats and isinstance(final_stats[stat], (int, float)):
                final_stats[stat] += bonus_val

        # Apply assignments last
        for stat, assign_val in assignments.items():
            final_stats[stat] = assign_val

        # Convert to int if possible
        for key, val in final_stats.items():
            if isinstance(val, float) and val.is_integer():
                final_stats[key] = int(val)

        return final_stats, bonuses


    def get_current_weight(self):
        return sum(u.weight for u in self.carried_units)

    def can_carry(self, unit_to_carry):
        if not self.weight_capacity or not unit_to_carry.weight: return False
        if unit_to_carry.weight_capacity: return False
        if len(self.carried_units) >= self.max_units: return False
        if self.get_current_weight() + unit_to_carry.weight > self.weight_capacity: return False
        return True

    def draw(self, screen, camera, nation_color, is_held=False, mouse_pos=(0, 0), selection_color=None, is_hovered=False, opacity=255, is_idle=False):
        self.delete_button_rect = None
        
        # Calculate draw position locally to avoid mutating state if held (ghost logic)
        draw_x, draw_y = self.display_x, self.display_y
        
        if is_held:
            draw_x, draw_y = camera.screen_to_world(*mouse_pos)
            draw_x -= c.TILE_SIZE / 2
            draw_y -= c.TILE_SIZE / 2
        else:
            # Only update internal state if not held (normal lerp)
            target_x, target_y = camera.grid_to_world(self.grid_x, self.grid_y)
            self.display_x += (target_x - self.display_x) * 0.2
            self.display_y += (target_y - self.display_y) * 0.2
            draw_x, draw_y = self.display_x, self.display_y

        discretized_zoom = round(camera.zoom * 20) / 20.0
        scaled_size = int(c.TILE_SIZE * discretized_zoom * 0.8)
        
        if scaled_size < 1: return

        scaled_asset, shadow_asset = c.get_scaled_asset(self.asset_path, scaled_size)
        if not scaled_asset: return
        
        if opacity < 255:
            scaled_asset = scaled_asset.copy()
            scaled_asset.set_alpha(opacity)

        # Use the local draw_x/draw_y for rendering
        sx, sy = camera.world_to_screen(draw_x, draw_y)
        offset = (c.TILE_SIZE * camera.zoom) / 2
        asset_rect = scaled_asset.get_rect(center=(sx + offset, sy + offset))
        
        # Draw Shadow (only if not ghost/held to prevent double shadows confusing depth)
        if not is_held:
            self.draw_shadow(screen, shadow_asset, asset_rect)
            
        screen.blit(scaled_asset, asset_rect.topleft)
        
        if is_idle:
            font = c.get_font(None, int(30 * camera.zoom))
            if font:
                text_surf = c.create_text_with_border("!", font, c.COLOR_RED, c.COLOR_BLACK)
                screen.blit(text_surf, (asset_rect.right - text_surf.get_width() / 2, asset_rect.top - text_surf.get_height() / 2))

        if self.is_upgrading:
            size = 12 * camera.zoom
            if size > 2:
                center_x = asset_rect.right - size * 0.8
                center_y = asset_rect.top + size * 0.8
                p1 = (center_x, center_y - size * 0.6)
                p2 = (center_x - size * 0.5, center_y + size * 0.4)
                p3 = (center_x + size * 0.5, center_y + size * 0.4)
                pygame.draw.polygon(screen, c.COLOR_YELLOW, [p1,p2,p3])
                pygame.draw.polygon(screen, c.COLOR_BLACK, [p1,p2,p3], int(max(1, 2 * camera.zoom)))

        if nation_color:
            dot_radius = max(2, int(4 * camera.zoom))
            dot_pos = (asset_rect.left + dot_radius, asset_rect.top + dot_radius)
            pygame.draw.circle(screen, nation_color, dot_pos, dot_radius)
            pygame.draw.circle(screen, c.COLOR_BLACK, dot_pos, dot_radius, 1)

        self.draw_rotation_indicator(screen, asset_rect.bottomleft, camera.zoom)

        if selection_color:
            pulse = (math.sin(pygame.time.get_ticks() * 0.005) + 1) / 2
            base_color = pygame.Color(selection_color)
            final_selection_color = base_color.lerp((255, 255, 0), pulse)
            pygame.draw.rect(screen, final_selection_color, asset_rect, 2)
            if selection_color == c.COLOR_YELLOW:
                self.draw_delete_button(screen, asset_rect.topright)
        
        if is_hovered and self.carried_units:
            self.draw_carried_units(screen, asset_rect, camera.zoom)

    def draw_carried_units(self, screen, asset_rect, zoom):
        icon_size = int(24 * zoom)
        if icon_size < 5: return
        
        panel_width = (icon_size + 4) * len(self.carried_units) + 4
        panel_height = icon_size + 8
        panel_rect = pygame.Rect(asset_rect.centerx - panel_width / 2, asset_rect.bottom + 5, panel_width, panel_height)
        
        pygame.draw.rect(screen, c.UI_PANEL_COLOR, panel_rect, border_radius=3)
        pygame.draw.rect(screen, c.UI_BORDER_COLOR, panel_rect, 1, border_radius=3)

        start_x = panel_rect.left + 4
        for unit in self.carried_units:
            icon, _ = c.get_scaled_asset(unit.asset_path, icon_size)
            if icon:
                screen.blit(icon, (start_x, panel_rect.top + 4))
                start_x += icon_size + 4

    def draw_rotation_indicator(self, screen, pos, zoom):
        size = max(2, 7 * zoom)
        angle_rad = math.radians(self.rotation)
        center_x, center_y = pos[0] + size / 2, pos[1] - size / 2
        points = [(center_x, center_y - size / 2), (center_x + size, center_y), (center_x, center_y + size / 2)]
        rotated_points = []
        for p in points:
            dx, dy = p[0] - center_x, p[1] - center_y
            rx = dx * math.cos(angle_rad) - dy * math.sin(angle_rad)
            ry = dx * math.sin(angle_rad) + dy * math.cos(angle_rad)
            rotated_points.append((center_x + rx, center_y + ry))

        pygame.draw.polygon(screen, c.COLOR_WHITE, rotated_points)
        pygame.draw.polygon(screen, c.COLOR_BLACK, rotated_points, 1)

    def to_dict(self, compact=False):
        if not compact:
            return {'id': self.id, 'unit_type': self.unit_type, 'grid_x': self.grid_x, 'grid_y': self.grid_y, 'nation_id': self.nation_id, 'rotation': self.rotation, 'is_upgrading': self.is_upgrading, 'status': self.status, 'carried_units': [u.to_dict(compact) for u in self.carried_units]}
        
        d = {
            'i': self.id,
            't': self.unit_type,
            'x': self.grid_x,
            'y': self.grid_y,
            'n': self.nation_id,
        }
        if self.rotation != 0: d['r'] = self.rotation
        if self.is_upgrading: d['upg'] = 1
        if self.status != 'active': d['s'] = self.status
        if self.carried_units: d['c'] = [u.to_dict(compact) for u in self.carried_units]
        return d

    @staticmethod
    def from_dict(data):
        is_compact = 't' in data
        if is_compact:
            unit = Unit(data['t'], data['x'], data['y'], data['n'])
            unit.id = data.get('i', str(uuid.uuid4()))
            unit.rotation = data.get('r', 0)
            unit.is_upgrading = data.get('upg', 0) == 1
            unit.status = data.get('s', 'active')
            unit.carried_units = [Unit.from_dict(u) for u in data.get('c', [])]
        else: 
            unit = Unit(data['unit_type'], data['grid_x'], data['grid_y'], data['nation_id'])
            unit.id = data.get('id', str(uuid.uuid4()))
            unit.rotation = data.get('rotation', 0)
            unit.is_upgrading = data.get('is_upgrading', False)
            unit.status = data.get('status', 'active')
            unit.carried_units = [Unit.from_dict(u) for u in data.get('carried_units', [])]
        return unit


class MapFeature(BaseEntity):
    def __init__(self, feature_type, grid_x, grid_y, name=None):
        super().__init__()
        self.id = str(uuid.uuid4())
        self.feature_type, self.grid_x, self.grid_y = feature_type, grid_x, grid_y
        self.properties = None
        for category in c.FEATURE_TYPES.values():
            if feature_type in category:
                self.properties = category[feature_type]
                break
        if not self.properties:
            raise ValueError(f"Feature type '{feature_type}' not found in any category.")
        self.asset_path = self.properties['asset']
        self.name = name if name else self.properties['name']
        self.is_naval = self.properties.get('is_naval', False)

    def draw(self, screen, camera, owner_color, font, selection_color=None):
        self.delete_button_rect = None
        
        discretized_zoom = round(camera.zoom * 20) / 20.0
        scaled_size = int(c.TILE_SIZE * discretized_zoom * 0.7)
        if scaled_size < 1:
            return

        scaled_asset, _ = c.get_scaled_asset(self.asset_path, scaled_size)
        if not scaled_asset:
            return

        wx, wy = camera.grid_to_world(self.grid_x, self.grid_y)
        sx, sy = camera.world_to_screen(wx, wy)
        offset = (c.TILE_SIZE * camera.zoom - scaled_size) / 2
        top_left_pos = (sx + offset, sy + offset)
        
        asset_rect = scaled_asset.get_rect(topleft=top_left_pos)
        
        # Special visual for Occupied Oil Rigs
        if self.feature_type == 'oil_rig' and owner_color:
            border_rect = asset_rect.inflate(6, 6)
            # Draw black OUTLINE (width=5) for contrast, not a filled rect
            pygame.draw.rect(screen, c.COLOR_BLACK, border_rect, 5, border_radius=3)
            # Draw colored OUTLINE (width=3) on top
            pygame.draw.rect(screen, owner_color, border_rect, 3, border_radius=3)

        screen.blit(scaled_asset, asset_rect.topleft)

        if camera.zoom > 0.8:
            text_color = pygame.Color(owner_color) if owner_color else c.COLOR_WHITE
            center_pos = (sx + c.TILE_SIZE * camera.zoom / 2, sy + c.TILE_SIZE * camera.zoom * 0.9)
            text_surf = c.create_text_with_border(self.name, font, text_color, c.COLOR_BLACK)
            text_rect = text_surf.get_rect(center=center_pos)
            screen.blit(text_surf, text_rect)

        if selection_color:
            selection_rect = pygame.Rect(top_left_pos, (scaled_size, scaled_size))
            pulse = (math.sin(pygame.time.get_ticks() * 0.005) + 1) / 2
            base_color = pygame.Color(selection_color)
            final_selection_color = base_color.lerp((255, 255, 0), pulse)
            pygame.draw.rect(screen, final_selection_color, selection_rect, 2)
            if selection_color == c.COLOR_YELLOW:
                self.draw_delete_button(screen, selection_rect.topright)

    def to_dict(self, compact=False):
        if not compact:
            return {'id': self.id, 'feature_type': self.feature_type, 'grid_x': self.grid_x, 'grid_y': self.grid_y, 'name': self.name}
        
        d = {
            'i': self.id,
            't': self.feature_type,
            'x': self.grid_x,
            'y': self.grid_y
        }
        if self.name != self.properties.get('name'):
            d['n'] = self.name
        return d

    @staticmethod
    def from_dict(data):
        is_compact = 't' in data
        if is_compact:
            name = data.get('n')
            if not name:
                for category in c.FEATURE_TYPES.values():
                    if data['t'] in category:
                        name = category[data['t']]['name']
                        break
            feature = MapFeature(data['t'], data['x'], data['y'], name)
            feature.id = data.get('i', str(uuid.uuid4()))
        else: 
            feature = MapFeature(data['feature_type'], data['grid_x'], data['grid_y'], data['name'])
            feature.id = data.get('id', str(uuid.uuid4()))
        return feature


class Arrow(BaseEntity):
    def __init__(self, start_gx, start_gy, end_gx, end_gy, order_type, nation_id=None, unit_id=None):
        super().__init__()
        self.id = str(uuid.uuid4())
        self.start_gx, self.start_gy, self.end_gx, self.end_gy = start_gx, start_gy, end_gx, end_gy
        self.order_type = order_type
        self.nation_id = nation_id
        self.unit_id = unit_id
        self.properties = c.ARROW_ORDERS[order_type]

    def is_clicked(self, world_pos):
        px, py = world_pos
        x1, y1 = self.start_gx * c.TILE_SIZE + c.TILE_SIZE / 2, self.start_gy * c.TILE_SIZE + c.TILE_SIZE / 2
        x2, y2 = self.end_gx * c.TILE_SIZE + c.TILE_SIZE / 2, self.end_gy * c.TILE_SIZE + c.TILE_SIZE / 2
        dx, dy = x2 - x1, y2 - y1
        if dx == 0 and dy == 0:
            return False
        
        len_sq = dx*dx + dy*dy
        if len_sq == 0:
            return False
            
        t = max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / len_sq))
        closest_x, closest_y = x1 + t * dx, y1 + t * dy
        return (px - closest_x) ** 2 + (py - closest_y) ** 2 < (10 * 10)

    def draw(self, screen, camera, selection_color=None, path_count=1, path_index=0, is_invalid=False):
        self.delete_button_rect = None
        offset = c.TILE_SIZE / 2
        start_wx, start_wy = self.start_gx * c.TILE_SIZE + offset, self.start_gy * c.TILE_SIZE + offset
        end_wx, end_wy = self.end_gx * c.TILE_SIZE + offset, self.end_gy * c.TILE_SIZE + offset
        start_sx, start_sy = camera.world_to_screen(start_wx, start_wy)
        end_sx, end_sy = camera.world_to_screen(end_wx, end_wy)

        if path_count > 1:
            dx, dy = end_sx - start_sx, end_sy - start_sy
            length = math.hypot(dx, dy)
            if length > 0:
                perp_x, perp_y = -dy / length, dx / length
                spacing = 8 * camera.zoom
                shift = (path_index - (path_count - 1) / 2.0) * spacing
                start_sx += perp_x * shift
                start_sy += perp_y * shift
                end_sx += perp_x * shift
                end_sy += perp_y * shift

        color = self.properties['color']
        if is_invalid:
            pulse = (math.sin(pygame.time.get_ticks() * 0.01) + 1) / 2
            base_color = pygame.Color(color)
            flash_color = pygame.Color(139, 0, 0) # Deep dark red
            color = base_color.lerp(flash_color, pulse)

        pulse = (math.sin(pygame.time.get_ticks() * 0.004) + 1) / 2 * 0.5
        line_width = max(1, int((self.properties['width'] + pulse) * camera.zoom))
        border_width = line_width + max(2, int(4 * camera.zoom))

        dx, dy = end_sx - start_sx, end_sy - start_sy
        length = math.hypot(dx, dy)
        if length < 1.0: return

        udx, udy = dx / length, dy / length
        arrowhead_len = max(6.0, 15.0 * camera.zoom)
        arrowhead_width = max(4.0, 10.0 * camera.zoom)
        if length < arrowhead_len:
            arrowhead_len = length
            arrowhead_width = length * (10.0 / 15.0)

        line_end_x = end_sx - udx * arrowhead_len
        line_end_y = end_sy - udy * arrowhead_len

        if length > arrowhead_len:
            pygame.draw.line(screen, c.COLOR_BLACK, (start_sx, start_sy), (line_end_x, line_end_y), border_width)
            pygame.draw.line(screen, color, (start_sx, start_sy), (line_end_x, line_end_y), line_width)

        tip_pos = (end_sx, end_sy)
        perp_dx, perp_dy = -udy, udx
        base_point_1 = (line_end_x + perp_dx * arrowhead_width, line_end_y + perp_dy * arrowhead_width)
        base_point_2 = (line_end_x - perp_dx * arrowhead_width, line_end_y - perp_dy * arrowhead_width)
        head_points = [tip_pos, base_point_1, base_point_2]
        pygame.draw.polygon(screen, c.COLOR_BLACK, head_points)
        pygame.draw.polygon(screen, color, head_points)

        if selection_color:
            mid_x, mid_y = (start_sx + end_sx) / 2, (start_sy + end_sy) / 2
            pulse = (math.sin(pygame.time.get_ticks() * 0.005) + 1) / 2
            base_color = pygame.Color(selection_color)
            final_selection_color = base_color.lerp((255, 255, 0), pulse)
            pygame.draw.circle(screen, final_selection_color, (mid_x, mid_y), 10, 2)
            if selection_color == c.COLOR_YELLOW:
                self.draw_delete_button(screen, (mid_x + 10, mid_y))

    def to_dict(self, compact=False):
        if not compact:
            return {'id': self.id, 'start_gx': self.start_gx, 'start_gy': self.start_gy, 'end_gx': self.end_gx, 'end_gy': self.end_gy, 'order_type': self.order_type, 'nation_id': self.nation_id, 'unit_id': self.unit_id}
        
        if not hasattr(c, 'ARROW_ORDER_TO_ID'):
            c.ARROW_ORDER_TO_ID = {name: i for i, name in enumerate(c.ARROW_ORDERS.keys())}
        
        d = {
            'i': self.id,
            'sx': self.start_gx,
            'sy': self.start_gy,
            'ex': self.end_gx,
            'ey': self.end_gy,
            'o': c.ARROW_ORDER_TO_ID.get(self.order_type, 0)
        }
        if self.nation_id:
            d['n'] = self.nation_id
        if self.unit_id:
            d['uid'] = self.unit_id
        return d

    @staticmethod
    def from_dict(data):
        is_compact = 'sx' in data
        if is_compact:
            if not hasattr(c, 'ID_TO_ARROW_ORDER'):
                c.ARROW_ORDER_TO_ID = {name: i for i, name in enumerate(c.ARROW_ORDERS.keys())}
                c.ID_TO_ARROW_ORDER = {i: name for name, i in c.ARROW_ORDER_TO_ID.items()}
            
            order_type = c.ID_TO_ARROW_ORDER.get(data['o'], 'Move')
            nation_id = data.get('n')
            unit_id = data.get('uid')
            arrow = Arrow(data['sx'], data['sy'], data['ex'], data['ey'], order_type, nation_id, unit_id)
            arrow.id = data.get('i', str(uuid.uuid4()))
        else: 
            nation_id = data.get('nation_id')
            unit_id = data.get('unit_id')
            arrow = Arrow(data['start_gx'], data['start_gy'], data['end_gx'], data['end_gy'], data['order_type'], nation_id, unit_id)
            arrow.id = data.get('id', str(uuid.uuid4()))
        return arrow

class Strait(BaseEntity):
    def __init__(self, start_gx, start_gy, end_gx, end_gy):
        super().__init__()
        self.id = str(uuid.uuid4())
        self.start_gx, self.start_gy = start_gx, start_gy
        self.end_gx, self.end_gy = end_gx, end_gy

    def is_clicked(self, world_pos):
        px, py = world_pos
        x1, y1 = self.start_gx * c.TILE_SIZE + c.TILE_SIZE / 2, self.start_gy * c.TILE_SIZE + c.TILE_SIZE / 2
        x2, y2 = self.end_gx * c.TILE_SIZE + c.TILE_SIZE / 2, self.end_gy * c.TILE_SIZE + c.TILE_SIZE / 2
        
        dx, dy = x2 - x1, y2 - y1
        len_sq = dx*dx + dy*dy
        if len_sq == 0: return False
            
        t = max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / len_sq))
        closest_x, closest_y = x1 + t * dx, y1 + t * dy
        return (px - closest_x)**2 + (py - closest_y)**2 < (15 * 15)

    def draw(self, screen, camera, is_editor_tool_active=False, selection_color=None):
        if not is_editor_tool_active:
            return

        offset = c.TILE_SIZE / 2
        start_wx, start_wy = self.start_gx * c.TILE_SIZE + offset, self.start_gy * c.TILE_SIZE + offset
        end_wx, end_wy = self.end_gx * c.TILE_SIZE + offset, self.end_gy * c.TILE_SIZE + offset
        
        start_sx, start_sy = camera.world_to_screen(start_wx, start_wy)
        end_sx, end_sy = camera.world_to_screen(end_wx, end_wy)

        color = c.COLOR_ORANGE
        width = max(2, int(4 * camera.zoom))
        
        pygame.draw.line(screen, color, (start_sx, start_sy), (end_sx, end_sy), width)
        pygame.draw.circle(screen, color, (start_sx, start_sy), width * 2)
        pygame.draw.circle(screen, color, (end_sx, end_sy), width * 2)

        if selection_color:
            mid_x, mid_y = (start_sx + end_sx) / 2, (start_sy + end_sy) / 2
            pulse = (math.sin(pygame.time.get_ticks() * 0.005) + 1) / 2
            base_color = pygame.Color(selection_color)
            final_selection_color = base_color.lerp((255, 255, 0), pulse)
            pygame.draw.circle(screen, final_selection_color, (mid_x, mid_y), 10, 2)
            if selection_color == c.COLOR_YELLOW:
                self.draw_delete_button(screen, (mid_x + 10, mid_y))

    def to_dict(self, compact=False):
        return {
            'i': self.id,
            'sx': self.start_gx,
            'sy': self.start_gy,
            'ex': self.end_gx,
            'ey': self.end_gy,
            'type': 'blockade' if isinstance(self, Blockade) else 'strait'
        }

    @staticmethod
    def from_dict(data):
        if data.get('type') == 'blockade':
            obj = Blockade(data['sx'], data['sy'], data['ex'], data['ey'])
        else:
            obj = Strait(data['sx'], data['sy'], data['ex'], data['ey'])
        obj.id = data.get('i', str(uuid.uuid4()))
        return obj

class Blockade(Strait):
    def draw(self, screen, camera, is_editor_tool_active=False, selection_color=None):
        if not is_editor_tool_active:
            return

        offset = c.TILE_SIZE / 2
        start_wx, start_wy = self.start_gx * c.TILE_SIZE + offset, self.start_gy * c.TILE_SIZE + offset
        end_wx, end_wy = self.end_gx * c.TILE_SIZE + offset, self.end_gy * c.TILE_SIZE + offset
        
        start_sx, start_sy = camera.world_to_screen(start_wx, start_wy)
        end_sx, end_sy = camera.world_to_screen(end_wx, end_wy)

        color = c.COLOR_RED
        width = max(3, int(6 * camera.zoom))
        
        draw_dashed_line(screen, color, (start_sx, start_sy), (end_sx, end_sy), width, 10 * camera.zoom)
        pygame.draw.circle(screen, color, (start_sx, start_sy), width * 1.5)
        pygame.draw.circle(screen, color, (end_sx, end_sy), width * 1.5)

        if selection_color:
            mid_x, mid_y = (start_sx + end_sx) / 2, (start_sy + end_sy) / 2
            pulse = (math.sin(pygame.time.get_ticks() * 0.005) + 1) / 2
            base_color = pygame.Color(selection_color)
            final_selection_color = base_color.lerp((255, 255, 0), pulse)
            pygame.draw.circle(screen, final_selection_color, (mid_x, mid_y), 10, 2)
            if selection_color == c.COLOR_YELLOW:
                self.draw_delete_button(screen, (mid_x + 10, mid_y))

class MapText(BaseEntity):
    def __init__(self, grid_x, grid_y, text="New Text", color=(255, 255, 255), font_size=24, author_username=None, visibility='public', importance=0):
        super().__init__()
        self.id = str(uuid.uuid4())
        self.grid_x, self.grid_y = grid_x, grid_y
        self.text = text
        self.color = color
        self.font_size = font_size
        self.author_username = author_username
        self.visibility = visibility # 'private', 'alliance', 'public'
        self.importance = importance # 0-5
        
        self.display_x, self.display_y = grid_x * c.TILE_SIZE, grid_y * c.TILE_SIZE
        self.font = None # Will be created on demand

    def draw(self, screen, camera, selection_color=None, is_hovered=False, is_held=False, mouse_pos=(0,0)):
        if not self.visible: return
        self.delete_button_rect = None

        if is_held:
            self.display_x, self.display_y = camera.screen_to_world(*mouse_pos)
            self.display_x -= c.TILE_SIZE / 2
            self.display_y -= c.TILE_SIZE / 2
        else:
            target_x, target_y = camera.grid_to_world(self.grid_x, self.grid_y)
            self.display_x += (target_x - self.display_x) * 0.2
            self.display_y += (target_y - self.display_y) * 0.2

        scaled_font_size = int(self.font_size * camera.zoom)
        if scaled_font_size < 5: return

        self.font = c.get_font(c.FONT_PATH, scaled_font_size)
        if not self.font: return
        
        border_color = c.COLOR_BLACK
        try:
            # Get the rect on the screen where the text will be drawn
            center_sx, center_sy = camera.world_to_screen(self.display_x + c.TILE_SIZE/2, self.display_y + c.TILE_SIZE/2)
            temp_surf = self.font.render(self.text, True, self.color)
            temp_rect = temp_surf.get_rect(center=(center_sx, center_sy))

            # Ensure the sample area is within screen bounds
            sample_rect = temp_rect.clamp(screen.get_rect())
            
            if sample_rect.width > 0 and sample_rect.height > 0:
                bg_subsurface = screen.subsurface(sample_rect)
                avg_color = pygame.transform.average_color(bg_subsurface)
                # Calculate luminance
                luminance = (0.2126 * avg_color[0] + 0.7152 * avg_color[1] + 0.0722 * avg_color[2])
                if luminance < 100: # If the background is dark
                    border_color = c.COLOR_WHITE
        except (pygame.error, ValueError):
             # Fallback if subsurface fails
            border_color = c.COLOR_BLACK
        
        text_surf_orig = c.create_text_with_border(self.text, self.font, self.color, border_color, border_size=max(1, int(2 * camera.zoom)))
        
        text_surf = text_surf_orig.copy()
        alpha = 255 if is_hovered or selection_color or is_held else 128
        text_surf.set_alpha(alpha)

        sx, sy = camera.world_to_screen(self.display_x, self.display_y)
        offset = (c.TILE_SIZE * camera.zoom) / 2
        text_rect = text_surf.get_rect(center=(sx + offset, sy + offset))
        
        # Draw importance indicators
        if self.importance > 0:
            indicator_radius = max(2, int(4 * camera.zoom))
            indicator_spacing = indicator_radius * 2.5
            start_x = text_rect.left - indicator_spacing
            
            for i in range(self.importance):
                imp_color = c.COLOR_YELLOW if i < 3 else c.COLOR_RED
                pygame.draw.circle(screen, imp_color, (start_x - i * indicator_spacing, text_rect.centery), indicator_radius)
                pygame.draw.circle(screen, c.COLOR_BLACK, (start_x - i * indicator_spacing, text_rect.centery), indicator_radius, 1)

        screen.blit(text_surf, text_rect)
        
        if selection_color:
            pulse = (math.sin(pygame.time.get_ticks() * 0.005) + 1) / 2
            base_color = pygame.Color(selection_color)
            final_selection_color = base_color.lerp((255, 255, 0), pulse)
            pygame.draw.rect(screen, final_selection_color, text_rect.inflate(4,4), 2)
            if selection_color == c.COLOR_YELLOW:
                self.draw_delete_button(screen, text_rect.topright)

    def to_dict(self, compact=False):
        return {
            'i': self.id,
            'x': self.grid_x, 'y': self.grid_y,
            'txt': self.text,
            'c': self.color,
            'fs': self.font_size,
            'auth': self.author_username,
            'vis': self.visibility,
            'imp': self.importance
        }
    
    @staticmethod
    def from_dict(data):
        text_obj = MapText(data['x'], data['y'], data.get('txt', "New Text"), tuple(data.get('c', (255,255,255))), data.get('fs', 24),
                           data.get('auth'), data.get('vis', 'public'), data.get('imp', 0))
        text_obj.id = data.get('i', str(uuid.uuid4()))
        return text_obj