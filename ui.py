import pygame
import config as c
import math
import collections
from entities import Unit, MapFeature, Arrow, MapText
import actions

try:
    import pyperclip
except ImportError:
    pyperclip = None

class UIElement:
    def __init__(self, rect, parent=None):
        self.rect = pygame.Rect(rect)
        self.children, self.parent = [], parent
        if parent: parent.add_child(self)
        self.visible, self.target_pos, self.lerp_speed = True, self.rect.topleft, 0.2
        self.alpha = 255.0
        self.target_alpha = 255.0

    def get_absolute_rect(self):
        if self.parent:
            parent_abs_rect = self.parent.get_absolute_rect()
            abs_rect = self.rect.move(parent_abs_rect.topleft)
            if isinstance(self.parent, ScrollablePanel):
                abs_rect.y -= self.parent.scroll_y
            return abs_rect
        return self.rect
    
    def add_child(self, child):
        self.children.append(child)
        child.parent = self

    def handle_event(self, event, ui_manager):
        if not self.visible: return False
        
        for child in reversed(self.children):
            if child.handle_event(event, ui_manager):
                return True
            
        return False

    def update(self):
        dx, dy = self.target_pos[0] - self.rect.x, self.target_pos[1] - self.rect.y
        if abs(dx) > 0.5 or abs(dy) > 0.5:
            self.rect.x += dx * self.lerp_speed
            self.rect.y += dy * self.lerp_speed
        else:
            self.rect.topleft = self.target_pos

        if abs(self.target_alpha - self.alpha) > 1:
            self.alpha += (self.target_alpha - self.alpha) * self.lerp_speed
        else:
            self.alpha = self.target_alpha

        for child in self.children: child.update()

    def draw(self, surface):
        if not self.visible and self.alpha < 1: return
        for child in self.children:
            if child.visible or child.alpha > 1:
                child_surf = pygame.Surface(child.rect.size, pygame.SRCALPHA)
                child.draw(child_surf)
                child_surf.set_alpha(child.alpha)
                surface.blit(child_surf, child.rect.topleft)

    def is_mouse_over(self, pos):
        if not self.visible: return False
        return self.get_absolute_rect().collidepoint(pos)
    
class ImageElement(UIElement):
    def __init__(self, rect, image_surf, parent=None):
        super().__init__(rect, parent)
        self.image_surf = image_surf
    def draw(self, surface):
        if self.image_surf: surface.blit(self.image_surf, (0, 0))

class Panel(UIElement):
    def __init__(self, rect, color=c.UI_PANEL_COLOR, border_color=c.UI_BORDER_COLOR, border_width=2, parent=None):
        super().__init__(rect, parent)
        self.color, self.border_color, self.border_width = color, border_color, border_width
        self.content_height = 0
        
    def rebuild_content(self, elements):
        self.children.clear()
        y_offset = 10
        for element_data in elements:
            elem = element_data['element']
            elem.rect.top = y_offset
            elem.target_pos = elem.rect.topleft
            self.add_child(elem)
            y_offset += element_data['height']
        self.content_height = y_offset
    
    def draw(self, surface):
        if not self.visible: return
        
        if self.color:
            pygame.draw.rect(surface, self.color, (0,0,self.rect.width, self.rect.height), border_radius=5)
        
        super().draw(surface)
        
        if self.border_width > 0:
            # Subtle angled line for style
            pygame.draw.line(surface, c.UI_HIGHLIGHT_COLOR, (self.border_width, self.border_width), (self.border_width + 20, self.border_width), 2)
            pygame.draw.rect(surface, self.border_color, (0,0,self.rect.width, self.rect.height), self.border_width, border_radius=5)
        
    def handle_event(self, event, ui_manager):
        if not self.visible:
            return False

        # Let children handle the event first. If they do, we're done.
        if super().handle_event(event, ui_manager):
            return True

        # If no child handled it, we only consume the event if it's a click
        # on this panel's background. This prevents clicks from "leaking" to the map.
        if hasattr(event, 'pos') and self.get_absolute_rect().collidepoint(event.pos):
            if event.type == pygame.MOUSEBUTTONDOWN:
                return True  # Consume the click
        
        return False

class ScrollablePanel(Panel):
    def __init__(self, rect, max_height=None, **kwargs):
        super().__init__(rect, **kwargs)
        self.scroll_y = 0
        self.content_height = 0
        self.max_height = max_height if max_height is not None else c.SCREEN_HEIGHT
        self.dragging_scrollbar = False
        self.scrollbar_drag_offset = 0

    def rebuild_content(self, elements):
        self.children.clear()
        self.scroll_y = 0
        y_offset = 10
        for element_data in elements:
            elem = element_data['element']
            elem.rect.top = y_offset
            elem.target_pos = elem.rect.topleft
            self.add_child(elem)
            y_offset += element_data['height']
        self.content_height = y_offset + 10

    def get_scrollbar_rects(self):
        if self.content_height <= self.rect.height:
            return None, None

        scrollbar_width = 8
        track_rect = pygame.Rect(self.rect.width - scrollbar_width - 2, 2, scrollbar_width, self.rect.height - 4)

        handle_height = max(20, self.rect.height * (self.rect.height / self.content_height))
        
        max_scroll = self.content_height - self.rect.height
        scroll_ratio = self.scroll_y / max_scroll if max_scroll > 0 else 0
        
        handle_y = track_rect.y + scroll_ratio * (track_rect.height - handle_height)
        handle_rect = pygame.Rect(track_rect.left, handle_y, scrollbar_width, handle_height)

        return track_rect, handle_rect

    def draw(self, surface):
        if not self.visible: return
        
        original_clip = surface.get_clip()
        surface.set_clip(pygame.Rect(0, 0, self.rect.width, self.rect.height))
        
        if self.color:
            pygame.draw.rect(surface, self.color, (0,0,self.rect.width, self.rect.height), border_radius=5)

        for child in self.children:
            if child.visible:
                child_surf = pygame.Surface(child.rect.size, pygame.SRCALPHA)
                child.draw(child_surf)
                surface.blit(child_surf, child.rect.move(0, -self.scroll_y).topleft)
        
        surface.set_clip(original_clip)
        
        track_rect, handle_rect = self.get_scrollbar_rects()
        if track_rect:
            pygame.draw.rect(surface, c.darken_color(self.color if self.color else c.UI_PANEL_COLOR, 0.8), track_rect, border_radius=4)
            pygame.draw.rect(surface, c.UI_BORDER_COLOR, handle_rect, border_radius=4)
        
        if self.border_width > 0:
            pygame.draw.rect(surface, self.border_color, (0,0,self.rect.width, self.rect.height), self.border_width, border_radius=5)

    def handle_event(self, event, ui_manager, force_scroll=False):
        if not self.visible: return False
        
        abs_rect = self.get_absolute_rect()
        is_mouse_over = hasattr(event, 'pos') and abs_rect.collidepoint(event.pos)
        
        if event.type == pygame.MOUSEWHEEL and (is_mouse_over or force_scroll):
            self.scroll_y -= event.y * 30
            max_scroll = self.content_height - self.rect.height
            self.scroll_y = max(0, min(self.scroll_y, max_scroll if max_scroll > 0 else 0))
            return True

        track_rect, handle_rect = self.get_scrollbar_rects()
        is_over_scrollbar = False
        if handle_rect and hasattr(event, 'pos'):
            abs_handle_rect = handle_rect.move(abs_rect.topleft)
            is_over_scrollbar = abs_handle_rect.collidepoint(event.pos)

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if is_over_scrollbar:
                self.dragging_scrollbar = True
                self.scrollbar_drag_offset = event.pos[1] - abs_handle_rect.y
                return True

        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self.dragging_scrollbar:
                self.dragging_scrollbar = False
                return True

        if event.type == pygame.MOUSEMOTION:
            if self.dragging_scrollbar:
                local_mouse_y = event.pos[1] - abs_rect.y
                new_handle_y = local_mouse_y - self.scrollbar_drag_offset
                max_handle_y = track_rect.height - handle_rect.height if track_rect else 0
                scroll_ratio = (new_handle_y - track_rect.y) / max_handle_y if max_handle_y > 0 else 0
                scroll_ratio = max(0, min(1, scroll_ratio))
                max_scroll = self.content_height - self.rect.height
                self.scroll_y = scroll_ratio * max_scroll if max_scroll > 0 else 0
                return True

        for child in reversed(self.children):
            if child.handle_event(event, ui_manager):
                return True
        
        if is_mouse_over and event.type == pygame.MOUSEBUTTONDOWN:
            return True

        return False

class Button(UIElement):
    def __init__(self, rect, text="", on_click=None, parent=None, icon=None, tooltip="", key=None, draw_background=True, icon_path=None):
        super().__init__(rect, parent)
        self.text, self.on_click, self.tooltip, self.key = text, on_click, tooltip, key
        self.is_hovered, self.is_active, self.is_pressed = False, False, False
        self.font = c.get_font(c.FONT_PATH, 16)
        self.draw_background = draw_background
        
        self.icon = icon
        if icon_path:
            icon_size = int(min(self.rect.width, self.rect.height) * 0.8)
            if icon_size > 0:
                self.icon, _ = c.get_scaled_asset(icon_path, icon_size)
        
    def handle_event(self, event, ui_manager):
        if not self.visible: return False
        
        abs_rect = self.get_absolute_rect()
        self.is_hovered = abs_rect.collidepoint(pygame.mouse.get_pos())

        if self.is_hovered and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.is_pressed = True
            return True

        if self.is_pressed and event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.is_pressed = False
            if self.is_hovered and self.on_click:
                self.on_click()
            return True # Consume the mouse up event regardless of hover

        return False

    def draw(self, surface):
        if not self.visible: return

        if self.draw_background:
            color = c.UI_BUTTON_COLOR
            if self.is_active:
                color = c.UI_HIGHLIGHT_COLOR
            elif self.is_pressed:
                color = c.darken_color(c.UI_BUTTON_HOVER_COLOR, 0.6)
            elif self.is_hovered:
                color = c.UI_BUTTON_HOVER_COLOR

            btn_rect = pygame.Rect(0, 0, self.rect.width, self.rect.height)
            pygame.draw.rect(surface, color, btn_rect, border_radius=5)
            if self.is_active or self.is_hovered:
                pygame.draw.line(surface, c.UI_HIGHLIGHT_COLOR, (1, 1), (1, 15), 2)
            
            pygame.draw.rect(surface, c.UI_BORDER_COLOR, btn_rect, 1, border_radius=5)
        
        btn_rect = surface.get_rect()
        if self.icon and self.text:
            icon_rect = self.icon.get_rect(centery=btn_rect.centery, left=8)
            surface.blit(self.icon, icon_rect)
            text_surf = self.font.render(self.text, True, c.UI_FONT_COLOR)
            surface.blit(text_surf, text_surf.get_rect(midleft=(icon_rect.right + 8, btn_rect.centery)))
        elif self.icon:
            surface.blit(self.icon, self.icon.get_rect(center=btn_rect.center))
        elif self.text:
            text_surf = self.font.render(self.text, True, c.UI_FONT_COLOR)
            surface.blit(text_surf, text_surf.get_rect(center=btn_rect.center))

class NationListButton(Button):
    def __init__(self, rect, nation_data, on_click, parent=None):
        super().__init__(rect, text="", on_click=on_click, parent=parent)
        self.nation_color, self.nation_name = nation_data['color'], nation_data['name']
    
    def draw(self, surface):
        if not self.visible: return
        
        color = c.UI_BUTTON_COLOR
        if self.is_active:
            color = c.UI_HIGHLIGHT_COLOR
        elif self.is_pressed:
            color = c.darken_color(c.UI_BUTTON_HOVER_COLOR, 0.6)
        elif self.is_hovered:
            color = c.UI_BUTTON_HOVER_COLOR

        button_rect = pygame.Rect(0, 0, self.rect.width, self.rect.height)
        pygame.draw.rect(surface, color, button_rect, border_radius=5)
        pygame.draw.rect(surface, c.UI_BORDER_COLOR, button_rect, 1, border_radius=5)
        pygame.draw.rect(surface, self.nation_color, pygame.Rect(5,5,30,30), border_radius=3)
        text_surf = self.font.render(self.nation_name,True,c.UI_FONT_COLOR)
        surface.blit(text_surf, text_surf.get_rect(midleft=(45, button_rect.height/2)))

class ColorPicker(UIElement):
    def __init__(self, rect, on_color_change, parent=None):
        super().__init__(rect, parent)
        self.on_color_change = on_color_change
        self.hue, self.saturation, self.value = 0, 1.0, 1.0
        self.picker_size = self.rect.height
        self.hue_slider_width = self.rect.width - self.picker_size - 10
        self.sv_surface = pygame.Surface((self.picker_size, self.picker_size))
        self.hue_surface = pygame.Surface((self.hue_slider_width, 15))
        self.create_hue_slider()
        self.dragging_sv, self.dragging_hue = False, False
        self.update_sv_surface()

    def create_hue_slider(self):
        for x in range(self.hue_slider_width):
            hue = x / self.hue_slider_width * 360
            color = pygame.Color(0,0,0)
            color.hsva = (hue,100,100,100)
            pygame.draw.line(self.hue_surface, color, (x,0), (x,self.hue_surface.get_height()))

    def update_sv_surface(self):
        base_color = pygame.Color(0,0,0)
        base_color.hsva = (self.hue, 100, 100, 100)
        white_to_color = pygame.Surface((self.picker_size, self.picker_size))
        white_to_color.fill((255, 255, 255))
        white_to_color.fill(base_color, special_flags=pygame.BLEND_RGB_MULT)
        black_gradient = pygame.Surface((self.picker_size, self.picker_size), pygame.SRCALPHA)
        for y in range(self.picker_size):
            pygame.draw.line(black_gradient, (0,0,0,int((y/self.picker_size)*255)),(0,y),(self.picker_size,y))
        self.sv_surface.blit(white_to_color, (0,0))
        self.sv_surface.blit(black_gradient, (0,0))

    def set_color(self, rgb_color):
        h,s,v,_=pygame.Color(rgb_color).hsva
        self.hue,self.saturation,self.value = h,s/100,v/100
        self.update_sv_surface()
    
    def handle_event(self, event, ui_manager):
        if not self.visible or not hasattr(event, 'pos'): return False
        
        abs_rect = self.get_absolute_rect()
        sv_abs_rect = pygame.Rect(abs_rect.left, abs_rect.top, self.picker_size, self.picker_size)
        hue_abs_rect = pygame.Rect(sv_abs_rect.right + 10, sv_abs_rect.top, self.hue_slider_width, 15)
        
        is_over_sv = sv_abs_rect.collidepoint(event.pos)
        is_over_hue = hue_abs_rect.collidepoint(event.pos)

        if event.type == pygame.MOUSEBUTTONDOWN and event.button==1:
            if is_over_sv: self.dragging_sv = True
            elif is_over_hue: self.dragging_hue = True
            if self.dragging_sv or self.dragging_hue:
                 self.handle_mouse_move(event.pos, sv_abs_rect, hue_abs_rect)
                 return True
                 
        if event.type == pygame.MOUSEBUTTONUP and event.button==1:
            if self.dragging_sv or self.dragging_hue:
                self.dragging_sv, self.dragging_hue = False, False
                return True

        if event.type == pygame.MOUSEMOTION:
            if self.dragging_sv or self.dragging_hue:
                self.handle_mouse_move(event.pos, sv_abs_rect, hue_abs_rect)
                return True
        
        return is_over_sv or is_over_hue

    def handle_mouse_move(self,pos,sv_abs_rect,hue_abs_rect):
        if self.dragging_sv:
            self.saturation = max(0, min(1, (pos[0] - sv_abs_rect.left) / self.picker_size))
            self.value = 1 - max(0, min(1, (pos[1] - sv_abs_rect.top) / self.picker_size))
            self.notify_color_change()
        elif self.dragging_hue:
            self.hue=max(0,min(359,(pos[0]-hue_abs_rect.left)/self.hue_slider_width*360))
            self.update_sv_surface()
            self.notify_color_change()

    def notify_color_change(self):
        color=pygame.Color(0,0,0)
        color.hsva=(self.hue,self.saturation*100,self.value*100,100)
        if self.on_color_change:
            self.on_color_change(tuple(color)[:3])
    
    def draw(self, surface):
        if not self.visible: return
        sv_rect,hue_rect = pygame.Rect(0,0,self.picker_size,self.picker_size), pygame.Rect(self.picker_size+10,0,self.hue_slider_width,15)
        surface.blit(self.sv_surface, sv_rect.topleft)
        pygame.draw.rect(surface, c.UI_BORDER_COLOR, sv_rect, 1)
        surface.blit(self.hue_surface, hue_rect.topleft)
        pygame.draw.rect(surface, c.UI_BORDER_COLOR, hue_rect, 1)
        sv_x,sv_y = sv_rect.left+self.saturation*self.picker_size, sv_rect.top+(1-self.value)*self.picker_size
        pygame.draw.circle(surface, c.COLOR_BLACK, (sv_x,sv_y), 6, 2)
        pygame.draw.circle(surface, c.COLOR_WHITE, (sv_x,sv_y), 5, 1)
        hue_x = hue_rect.left+(self.hue/360)*self.hue_slider_width
        pygame.draw.rect(surface, c.COLOR_WHITE, (hue_x-2,hue_rect.top-2,4,hue_rect.height+4),1)

class InputField(UIElement):
    def __init__(self, rect, initial_text="", on_change=None, parent=None, multiline=False, on_submit=None):
        super().__init__(rect, parent)
        self.text = initial_text
        self.on_change = on_change
        self.on_submit = on_submit
        self.multiline = multiline
        self.is_active = False
        self.font = c.get_font(c.FONT_PATH, 18)
        self.cursor_pos = len(initial_text)
        self.initial_text_on_focus = None
        self.tooltip = ""

    def handle_event(self, event, ui_manager):
        if not self.visible: return False
        
        abs_rect = self.get_absolute_rect()
        is_over = hasattr(event, 'pos') and abs_rect.collidepoint(event.pos)

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if is_over:
                if not self.is_active:
                    self.is_active = True
                    self.initial_text_on_focus = self.text
                    if ui_manager: ui_manager.set_active_input(self)
                # Recalculate cursor position based on click
                local_x = event.pos[0] - abs_rect.left - 5 # 5 is padding
                
                # For multiline, this logic is more complex and not implemented here
                # For single line:
                if not self.multiline:
                    best_dist = float('inf')
                    best_pos = len(self.text)
                    for i in range(len(self.text) + 1):
                        sub_width = self.font.size(self.text[:i])[0]
                        dist = abs(local_x - sub_width)
                        if dist < best_dist:
                            best_dist = dist
                            best_pos = i
                    self.cursor_pos = best_pos

                return True
            else:
                if self.is_active:
                    if self.on_submit and self.text != self.initial_text_on_focus:
                        self.on_submit(self.initial_text_on_focus, self.text)
                    self.is_active = False
                    if ui_manager: ui_manager.set_active_input(None)
                return False

        if event.type == pygame.MOUSEBUTTONUP and event.button == 1 and is_over:
            return True

        if self.is_active and event.type == pygame.KEYDOWN:
            mods = pygame.key.get_mods()
            
            if event.key == pygame.K_RETURN:
                # For multiline, Ctrl+Enter adds a newline
                if self.multiline and (mods & pygame.KMOD_CTRL):
                    self.text = self.text[:self.cursor_pos] + '\n' + self.text[self.cursor_pos:]
                    self.cursor_pos += 1
                # For both single and multiline, a simple Enter submits and deactivates
                else:
                    if self.on_submit and self.text != self.initial_text_on_focus:
                        self.on_submit(self.initial_text_on_focus, self.text)
                    self.is_active = False
                    if ui_manager: ui_manager.set_active_input(None)

            elif mods & pygame.KMOD_CTRL and pyperclip:
                if event.key == pygame.K_c:
                    pyperclip.copy(self.text)
                elif event.key == pygame.K_v:
                    paste_text = pyperclip.paste()
                    self.text = self.text[:self.cursor_pos] + paste_text + self.text[self.cursor_pos:]
                    self.cursor_pos += len(paste_text)
            elif event.key == pygame.K_BACKSPACE:
                if self.cursor_pos > 0:
                    self.text = self.text[:self.cursor_pos-1] + self.text[self.cursor_pos:]
                    self.cursor_pos -= 1
            elif event.key == pygame.K_DELETE:
                self.text = self.text[:self.cursor_pos] + self.text[self.cursor_pos+1:]
            elif event.key == pygame.K_LEFT:
                self.cursor_pos = max(0, self.cursor_pos - 1)
            elif event.key == pygame.K_RIGHT:
                self.cursor_pos = min(len(self.text), self.cursor_pos + 1)
            else:
                self.text = self.text[:self.cursor_pos] + event.unicode + self.text[self.cursor_pos:]
                self.cursor_pos += len(event.unicode)
            
            if self.on_change: self.on_change(self.text)
            return True
            
        return False

    def set_text(self, text): 
        if self.text != text:
            self.text = text
            self.cursor_pos = len(text)

    def draw(self, surface):
        if not self.visible: return
        bg_color = c.UI_BUTTON_HOVER_COLOR if self.is_active else c.UI_BUTTON_COLOR
        pygame.draw.rect(surface, bg_color, (0,0,self.rect.width, self.rect.height), border_radius=5)
        pygame.draw.rect(surface, c.UI_BORDER_COLOR, (0,0,self.rect.width, self.rect.height), 1, border_radius=5)
        
        text_surf = self.font.render(self.text, True, c.UI_FONT_COLOR)
        surface.blit(text_surf, (5, 5))
        
        if self.is_active and pygame.time.get_ticks() % 1000 < 500:
            cursor_x = 5 + self.font.size(self.text[:self.cursor_pos])[0]
            pygame.draw.line(surface, c.UI_FONT_COLOR, (cursor_x, 5), (cursor_x, self.rect.height - 5))

class MultilineInputField(InputField):
    def __init__(self, rect, initial_text="", on_change=None, parent=None, on_submit=None):
        super().__init__(rect, initial_text, on_change, parent, multiline=True, on_submit=on_submit)
        self.padding = 5
        self.on_resize = None
        self._reflow_text(initial_reflow=True)

    def set_text(self, text):
        if self.text != text:
            super().set_text(text)
            self._reflow_text()

    def _reflow_text(self, initial_reflow=False):
        self.lines = []
        raw_lines = self.text.split('\n')
        wrap_width = self.rect.width - 2 * self.padding
        
        for raw_line in raw_lines:
            words = raw_line.split(' ')
            current_line = ""
            if not words or (len(words) == 1 and words[0] == ''):
                self.lines.append("")
                continue

            for word in words:
                if self.font.size(current_line + word)[0] < wrap_width:
                    current_line += word + " "
                else:
                    self.lines.append(current_line.strip())
                    current_line = word + " "
            self.lines.append(current_line.strip())
        
        new_height = max(30, len(self.lines) * self.font.get_linesize() + 2 * self.padding)
        if new_height != self.rect.height:
            self.rect.height = new_height
            if self.on_resize and not initial_reflow:
                self.on_resize()

    def handle_event(self, event, ui_manager):
        if super().handle_event(event, ui_manager):
            self._reflow_text()
            return True
        return False

    def draw(self, surface):
        if not self.visible: return
        bg_color = c.UI_BUTTON_HOVER_COLOR if self.is_active else c.UI_BUTTON_COLOR
        pygame.draw.rect(surface, bg_color, (0,0,self.rect.width, self.rect.height), border_radius=5)
        pygame.draw.rect(surface, c.UI_BORDER_COLOR, (0,0,self.rect.width, self.rect.height), 1, border_radius=5)

        y = self.padding
        total_chars_drawn = 0
        cursor_drawn = False

        for i, line in enumerate(self.lines):
            text_surf = self.font.render(line, True, c.UI_FONT_COLOR)
            surface.blit(text_surf, (self.padding, y))
            
            line_len = len(line) + 1

            if self.is_active and not cursor_drawn:
                if total_chars_drawn <= self.cursor_pos < total_chars_drawn + line_len:
                    cursor_char_pos = self.cursor_pos - total_chars_drawn
                    cursor_x = self.padding + self.font.size(line[:cursor_char_pos])[0]
                    if pygame.time.get_ticks() % 1000 < 500:
                         pygame.draw.line(surface, c.UI_FONT_COLOR, (cursor_x, y), (cursor_x, y + self.font.get_linesize()))
                    cursor_drawn = True

            total_chars_drawn += line_len
            y += self.font.get_linesize()

class TextLabel(UIElement):
    def __init__(self, rect, text, font, color, parent=None, center_align=False, wrap_width=None):
        super().__init__(rect, parent)
        self.text, self.font, self.color = text, font, color
        self.center_align, self.wrap_width = center_align, wrap_width
        self.rendered_surfaces = []
        self.render_text()

    def set_text(self, text):
        if self.text == text: return
        self.text = text
        self.render_text()

    def render_text(self):
        self.rendered_surfaces.clear()
        if not self.wrap_width:
            self.rendered_surfaces.append(self.font.render(self.text, True, self.color))
        else:
            words = self.text.split(' ')
            lines = []
            current_line = ""
            for word in words:
                if self.font.size(current_line + word)[0] < self.wrap_width:
                    current_line += word + " "
                else:
                    lines.append(current_line.strip())
                    current_line = word + " "
            lines.append(current_line.strip())
            for line in lines:
                self.rendered_surfaces.append(self.font.render(line, True, self.color))
        
        if self.rendered_surfaces:
            line_height = self.rendered_surfaces[0].get_height()
            self.rect.height = len(self.rendered_surfaces) * line_height

    def draw(self, surface):
        if not self.visible: return
        y = 0
        for text_surf in self.rendered_surfaces:
            if self.center_align:
                dest_rect = text_surf.get_rect(centerx=self.rect.width/2, top=y)
            else:
                dest_rect = text_surf.get_rect(left=0, top=y)
            surface.blit(text_surf, dest_rect)
            y += text_surf.get_height()

class CategoryHeader(Button):
    def __init__(self, rect, text, on_toggle, expanded, parent=None):
        super().__init__(rect, text=text, on_click=on_toggle, parent=parent)
        self.expanded, self.font = expanded, c.get_font(c.FONT_PATH, 18)
    def draw(self, surface):
        if not self.visible: return
        bg_color = c.UI_BUTTON_HOVER_COLOR if self.is_hovered else c.UI_BUTTON_COLOR
        pygame.draw.rect(surface, bg_color, (0,0,self.rect.width, self.rect.height), border_top_left_radius=5, border_top_right_radius=5)
        arrow_surf = self.font.render("V" if self.expanded else ">", True, c.UI_FONT_COLOR)
        surface.blit(arrow_surf, (10, self.rect.height/2 - arrow_surf.get_height() // 2))
        text_surf = self.font.render(self.text, True, c.UI_FONT_COLOR)
        surface.blit(text_surf, (30, self.rect.height/2 - text_surf.get_height() // 2))

class Checkbox(UIElement):
    def __init__(self, rect, text="", initial_state=False, on_toggle=None, parent=None):
        super().__init__(rect, parent)
        self.text = text
        self.checked = initial_state
        self.on_toggle = on_toggle
        self.font = c.get_font(c.FONT_PATH, 16)
        self.box_size = self.rect.height - 4
        self.is_hovered = False

    def handle_event(self, event, ui_manager):
        if not self.visible or not hasattr(event, 'pos'): return False
        abs_rect = self.get_absolute_rect()
        is_over = abs_rect.collidepoint(event.pos)
        self.is_hovered = is_over

        if is_over and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.checked = not self.checked
            if self.on_toggle:
                self.on_toggle(self.checked)
            return True
        return False

    def draw(self, surface):
        box_rect = pygame.Rect(2, 2, self.box_size, self.box_size)
        
        text_surf = self.font.render(self.text, True, c.UI_FONT_COLOR)
        text_pos = (box_rect.right + 8, self.rect.height / 2 - text_surf.get_height() / 2)
        surface.blit(text_surf, text_pos)
        
        border_color = c.UI_HIGHLIGHT_COLOR if self.is_hovered else c.UI_BORDER_COLOR
        pygame.draw.rect(surface, border_color, box_rect, 2, border_radius=3)
        
        if self.checked:
            check_margin = 5
            points = [
                (box_rect.left + check_margin, box_rect.centery),
                (box_rect.centerx - 2, box_rect.bottom - check_margin),
                (box_rect.right - check_margin, box_rect.top + check_margin)
            ]
            pygame.draw.lines(surface, c.UI_HIGHLIGHT_COLOR, False, points, 3)

class PopUpMenu(Panel):
    def __init__(self, pos, options, parent=None):
        self.options = options
        width = 200
        height = len(options) * 45 + 10
        super().__init__(rect=(pos[0], pos[1], width, height), parent=parent)
        
        elements = []
        for text, callback in options:
            btn = Button(rect=(10, 0, width - 20, 40), text=text, on_click=callback)
            elements.append({'element': btn, 'height': 45})
        self.rebuild_content(elements)

class LeaderboardRow(UIElement):
    def __init__(self, rect, nation_id, nation_color, nation_name, manpower_text, used, total, is_special, strength, techs, font, parent=None):
        super().__init__(rect, parent)
        self.nation_id = nation_id
        self.nation_color = nation_color
        self.nation_name = nation_name
        self.manpower_text = manpower_text
        self.used = used
        self.total = total
        self.is_special = is_special
        self.strength = strength
        self.techs = techs
        self.font = font

    def draw(self, surface):
        name_surf = self.font.render(self.nation_name, True, self.nation_color)
        surface.blit(name_surf, (2, 2))
        
        manpower_color = c.UI_FONT_COLOR
        if not self.is_special:
            if self.used > self.total:
                pulse = (math.sin(pygame.time.get_ticks() * 0.005) + 1) / 2
                base_color = pygame.Color(c.COLOR_RED)
                flash_color = pygame.Color(255, 150, 150)
                manpower_color = base_color.lerp(flash_color, pulse)
            elif self.used == self.total and self.total > 0:
                manpower_color = c.COLOR_GREEN
            elif self.used == 0 and self.total > 0:
                manpower_color = c.COLOR_ORANGE

        manpower_surf = self.font.render(self.manpower_text, True, manpower_color)
        manpower_rect = manpower_surf.get_rect(topright=(self.rect.width, 2))
        surface.blit(manpower_surf, manpower_rect)

        stats_text = f"Strength: {self.strength} | Techs: {self.techs}"
        stats_surf = self.font.render(stats_text, True, (200, 200, 200))
        stats_rect = stats_surf.get_rect(topleft=(2, 22))
        surface.blit(stats_surf, stats_rect)

class TurnOrderPanel(UIElement):
    def __init__(self, rect, game_app, parent=None):
        super().__init__(rect, parent)
        self.game_app = game_app
        self.dragging_nation_id = None
        self.drag_offset_x = 0
        self.font = c.get_font(c.FONT_PATH, 16)
        self.is_admin = self.game_app.main_app.user_mode == 'editor'
        self.build_elements()

    def build_elements(self):
        self.children.clear()
        
        # Center the panel content
        total_width = (len(self.game_app.turn_order) * 130) + (100 if self.is_admin else 0)
        start_x = (self.rect.width - total_width) / 2

        for i, nation_id in enumerate(self.game_app.turn_order):
            nation = self.game_app.nations.get(nation_id)
            if not nation: continue
            
            is_current_turn = (i == self.game_app.current_turn_index)
            
            nation_rect = pygame.Rect(start_x + i * 130, 5, 120, self.rect.height - 10)
            
            class NationBox(UIElement):
                def __init__(self, rect, nation_data, font, is_current_flag, parent=None): # Renamed to avoid confusion
                    super().__init__(rect, parent)
                    self.nation_data = nation_data
                    self.font = font
                    self.is_current = is_current_flag # Assigned the flag
                
                def draw(self, surface):
                    pygame.draw.rect(surface, c.UI_PANEL_COLOR, surface.get_rect(), border_radius=5)
                    pygame.draw.rect(surface, self.nation_data['color'], pygame.Rect(5,5,10,self.rect.height-10), border_radius=3)
                    
                    text_surf = self.font.render(self.nation_data['name'], True, c.UI_FONT_COLOR)
                    surface.blit(text_surf, (20, self.rect.height / 2 - text_surf.get_height() / 2))

                    if self.is_current:
                        pygame.draw.rect(surface, c.COLOR_YELLOW, surface.get_rect(), 2, border_radius=5)
                    else:
                        pygame.draw.rect(surface, c.UI_BORDER_COLOR, surface.get_rect(), 1, border_radius=5)
            
            self.add_child(NationBox(nation_rect, nation, self.font, is_current_turn))

        if self.is_admin:
            next_btn_rect = pygame.Rect(start_x + len(self.game_app.turn_order) * 130, 5, 90, self.rect.height - 10)
            self.add_child(Button(next_btn_rect, text="Next Turn", on_click=self.game_app.next_turn))

    def handle_event(self, event, ui_manager):
        if not self.is_admin or not self.visible: return False
        
        abs_rect = self.get_absolute_rect()
        
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if abs_rect.collidepoint(event.pos):
                for i, nation_id in enumerate(self.game_app.turn_order):
                    child_rect = self.children[i].get_absolute_rect()
                    if child_rect.collidepoint(event.pos):
                        self.dragging_nation_id = nation_id
                        self.drag_offset_x = event.pos[0] - child_rect.x
                        return True

        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self.dragging_nation_id:
                self.dragging_nation_id = None
                self.build_elements() # Redraw to snap back
                return True

        if event.type == pygame.MOUSEMOTION and self.dragging_nation_id:
            current_index = self.game_app.turn_order.index(self.dragging_nation_id)
            
            total_width = (len(self.game_app.turn_order) * 130)
            start_x = (self.rect.width - total_width) / 2 + abs_rect.x
            relative_mouse_x = event.pos[0] - start_x
            new_index = max(0, min(len(self.game_app.turn_order) - 1, int(relative_mouse_x // 130)))

            if new_index != current_index:
                self.game_app.turn_order.pop(current_index)
                self.game_app.turn_order.insert(new_index, self.dragging_nation_id)
                self.build_elements()
            return True

        return super().handle_event(event, ui_manager)
    
    def draw(self, surface):
        pygame.draw.rect(surface, c.darken_color(c.UI_BACKGROUND_COLOR, 1.2), surface.get_rect(), border_radius=5)
        super().draw(surface)
        
        
class MiniMap(UIElement):
    def __init__(self, app, rect, parent=None):
        super().__init__(rect, parent)
        self.app = app
        self.map_surface = None
        self.is_dirty = True
        self.surf_w = 0
        self.surf_h = 0
        self.scaled_surface = None

    def set_dirty(self):
        self.is_dirty = True

    def build_surface(self):
        map_w, map_h = self.app.map.width, self.app.map.height
        if map_w == 0 or map_h == 0: return

        aspect_ratio = map_w / map_h
        if self.rect.width / aspect_ratio <= self.rect.height:
            self.surf_w = self.rect.width
            self.surf_h = int(self.rect.width / aspect_ratio)
        else:
            self.surf_h = self.rect.height
            self.surf_w = int(self.rect.height * aspect_ratio)
        
        self.surf_w = max(1, self.surf_w)
        self.surf_h = max(1, self.surf_h)

        self.map_surface = pygame.Surface((map_w, map_h))
        for x in range(map_w):
            for y in range(map_h):
                tile = self.app.map.grid[x][y]
                
                is_fogged = tile.visibility_state != 0 and self.app.main_app.user_mode != 'editor'
                
                if is_fogged:
                    color = (20,20,25)
                else:
                    color = c.LAND_COLORS.get(tile.land_type, c.COLOR_BLACK)
                    if tile.nation_owner_id and tile.nation_owner_id in self.app.nations:
                        nation_color = pygame.Color(self.app.nations[tile.nation_owner_id]['color'])
                        color = pygame.Color(color).lerp(nation_color, 0.6)

                self.map_surface.set_at((x,y), color)
        
        if self.map_surface.get_width() > self.surf_w or self.map_surface.get_height() > self.surf_h:
            self.scaled_surface = pygame.transform.smoothscale(self.map_surface, (self.surf_w, self.surf_h))
        else:
            self.scaled_surface = pygame.transform.scale(self.map_surface, (self.surf_w, self.surf_h))
            
        self.is_dirty = False
    
    def update(self):
        if self.is_dirty:
            self.build_surface()

    def handle_event(self, event, ui_manager):
        abs_rect = self.get_absolute_rect()
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if abs_rect.collidepoint(event.pos):
                local_x, local_y = event.pos[0] - abs_rect.x, event.pos[1] - abs_rect.y
                map_x = (local_x / self.surf_w) * self.app.map.width
                map_y = (local_y / self.surf_h) * self.app.map.height
                
                target_wx, target_wy = map_x * c.TILE_SIZE, map_y * c.TILE_SIZE
                self.app.map.camera.center_on(target_wx, target_wy)
                return True
        return False

    def draw(self, surface):
        if not self.scaled_surface: return
        
        surface.blit(self.scaled_surface, (0, 0))
        
        cam = self.app.map.camera
        world_start_x, world_start_y = cam.screen_to_world(0,0)
        world_end_x, world_end_y = cam.screen_to_world(c.SCREEN_WIDTH, c.SCREEN_HEIGHT)
        
        view_x = (world_start_x / (self.app.map.width * c.TILE_SIZE)) * self.surf_w
        view_y = (world_start_y / (self.app.map.height * c.TILE_SIZE)) * self.surf_h
        view_w = ((world_end_x - world_start_x) / (self.app.map.width * c.TILE_SIZE)) * self.surf_w
        view_h = ((world_end_y - world_start_y) / (self.app.map.height * c.TILE_SIZE)) * self.surf_h
        
        view_rect = pygame.Rect(view_x, view_y, view_w, view_h)
        pygame.draw.rect(surface, c.UI_FONT_COLOR, view_rect, 1)

        pygame.draw.rect(surface, c.UI_BORDER_COLOR, surface.get_rect(), 2, border_radius=5)           

class UIManager:
    def __init__(self, game_app):
        self.game_app = game_app
        self.root = UIElement(pygame.Rect(0,0,c.SCREEN_WIDTH,c.SCREEN_HEIGHT))
        self.active_input = None
        self.active_popup = None
        self.tooltip_text, self.tooltip_surf, self.tooltip_timer, self.tooltip_owner, self.tooltip_pos = "", None, 0, None, (0,0)
        self.tooltip_font = c.get_font(c.FONT_PATH, 14)
        self.category_states = {}
        self.dialog_open = False
        self.admin_selected_nation_id = None
        self.admin_selected_alliance_nations = set()
        self.placement_filter_text = ""
        self.idle_unit_button = None
        self.search_panel = None
        self.search_panel_visible = False
        self.leaderboard_panel = None
        self.selection_info_panel = None
        self.sub_panels = {}
        self.tool_buttons = {}
        self.build_ui()

    def setup_sub_panels(self):
        self.sub_panels = {
            'manage_nations': self.create_nation_panel(),
            'paint_land': self.create_brush_panel(c.LAND_COLORS, 'paint_land'),
            'paint_nation': self.create_brush_panel(None, 'paint_nation'),
            'paint_fog': self.create_brush_panel(None, 'paint_fog'),
            'add_unit': self.create_category_panel(c.UNIT_TYPES, 'unit_type'),
            'add_feature': self.create_category_panel(c.FEATURE_TYPES, 'feature_type'),
            'add_arrow': self.create_sub_panel(c.ARROW_ORDERS, 'arrow_order'),
            'add_strait': self.create_brush_panel({}, 'strait_type')
        }
        for panel in self.sub_panels.values():
            panel.visible = False
            panel.target_alpha = 0
            panel.alpha = 0
        
        self.selection_info_panel = ScrollablePanel(rect=pygame.Rect(c.SCREEN_WIDTH - 210, c.SCREEN_HEIGHT, 200, 350), parent=self.root, max_height=400)
        self.rebuild_selection_info_panel()

    def close_popup_and_run(self, callback):
        if self.active_popup:
            self.root.children.remove(self.active_popup)
            self.active_popup = None
        callback()

    def create_popup(self, pos, options):
        if self.active_popup:
            self.root.children.remove(self.active_popup)
        
        wrapped_options = []
        for text, callback in options:
            wrapped_options.append((text, lambda cb=callback: self.close_popup_and_run(cb)))

        self.active_popup = PopUpMenu(pos, wrapped_options, parent=self.root)

    def create_sub_panel(self, item_dict, sub_tool_key):
        panel = ScrollablePanel(rect=(0,0,220, c.SCREEN_HEIGHT-150), parent=self.root)
        elements = []
        for key, data in item_dict.items():
            text = data.get('name', key) if isinstance(data, dict) else key
            icon = c.get_asset(data['asset']) if isinstance(data, dict) and 'asset' in data else None
            btn = Button(rect=(10,0,200,40), text=text, on_click=lambda k=key: self.game_app.set_sub_tool(sub_tool_key, k), icon=icon)
            if self.game_app.current_selection.get(sub_tool_key) == key:
                btn.is_active = True
            elements.append({'element': btn, 'height': 45})
        panel.rebuild_content(elements)
        return panel

    def create_category_panel(self, item_dict, sub_tool_key):
        panel = ScrollablePanel(rect=(0,0,220, c.SCREEN_HEIGHT-150), parent=self.root)
        elements = []
        
        search_input = InputField(rect=(10, 0, 200, 30), initial_text=self.placement_filter_text, on_change=self.on_placement_filter_change)
        elements.append({'element': search_input, 'height': 40})

        query = self.placement_filter_text.lower().strip()

        for category, items in item_dict.items():
            filtered_items = {
                key: data for key, data in items.items()
                if query in data.get('name', '').lower()
            }
            if not filtered_items:
                continue

            is_expanded = self.category_states.get(category, True)
            header = CategoryHeader(rect=(10,0,200,30), text=category, on_toggle=lambda c=category: self.toggle_category(c), expanded=is_expanded)
            elements.append({'element': header, 'height': 35})
            if is_expanded:
                for key, data in filtered_items.items():
                    text = data.get('name', key)
                    icon_path = data.get('asset')
                    icon = c.get_scaled_asset(icon_path, 30)[0] if icon_path else None
                    btn = Button(rect=(20,0,180,40), text=text, on_click=lambda k=key: self.game_app.set_sub_tool(sub_tool_key, k), icon=icon)
                    if self.game_app.current_selection.get(sub_tool_key) == key:
                        btn.is_active = True
                    elements.append({'element': btn, 'height': 45})
        panel.rebuild_content(elements)
        return panel

    def create_brush_panel(self, item_dict, sub_tool_key):
        panel = ScrollablePanel(rect=(0,0,220, c.SCREEN_HEIGHT-150), parent=self.root)
        elements = []
        
        size_row = UIElement(pygame.Rect(10, 0, 200, 30))
        TextLabel(pygame.Rect(0,5,80,20), "Brush Size:", c.get_font(c.FONT_PATH, 16), c.UI_FONT_COLOR, size_row)
        for i in range(1, 6):
            btn = Button(rect=(90 + (i-1)*22, 5, 20, 20), text=str(i), on_click=lambda s=i: self.game_app.set_sub_tool('paint_brush_size', s))
            if self.game_app.current_selection.get('paint_brush_size') == i: btn.is_active = True
            size_row.add_child(btn)
        elements.append({'element': size_row, 'height': 40})
        
        def toggle_fill_mode():
            self.game_app.paint_is_fill_mode = not self.game_app.paint_is_fill_mode
            self.rebuild_active_tool_panel()
        
        if sub_tool_key in ['paint_land', 'paint_nation']:
            fill_mode_btn = Button(rect=(10, 0, 200, 30), text="Fill Mode (Bucket)", on_click=toggle_fill_mode)
            fill_mode_btn.is_active = self.game_app.paint_is_fill_mode
            elements.append({'element': fill_mode_btn, 'height': 40})

        if item_dict:
            for key, color in item_dict.items():
                btn = Button(rect=(10,0,200,40), text=key, on_click=lambda k=key: self.game_app.set_sub_tool(sub_tool_key, k))
                if self.game_app.current_selection.get(sub_tool_key) == key:
                    btn.is_active = True
                elements.append({'element': btn, 'height': 45})
        
        if sub_tool_key == 'strait_type': 
             for strait_type in ['strait', 'blockade']:
                 btn = Button(rect=(10,0,200,40), text=strait_type.title(), on_click=lambda k=strait_type: self.game_app.set_sub_tool('strait_type', k))
                 if self.game_app.current_selection.get('strait_type') == strait_type:
                     btn.is_active = True
                 elements.append({'element': btn, 'height': 45})

        panel.rebuild_content(elements)
        return panel

    def create_nation_panel(self):
        panel = ScrollablePanel(rect=(0,0,300, c.SCREEN_HEIGHT-150), parent=self.root)
        self.rebuild_nation_panel_content(panel)
        return panel

    def rebuild_nation_panel_content(self, panel=None):
        if panel is None:
            panel = self.sub_panels.get('manage_nations')
        if panel is None: return

        elements = []
        active_id = self.game_app.active_nation_id
        is_editing = active_id and active_id in self.game_app.nations
        
        user_mode = self.game_app.main_app.user_mode
        player_nation_id = self.game_app.main_app.player_nation_id
        is_admin = (user_mode == 'editor')
        can_edit_basic = is_admin or (user_mode == 'player' and active_id == player_nation_id)
        
        if not is_admin and player_nation_id:
             if active_id != player_nation_id:
                 active_id = player_nation_id
                 self.game_app.active_nation_id = player_nation_id
                 is_editing = True

        add_edit_panel = Panel(rect=(10, 0, 280, 260), color=(50, 55, 65))
        
        header_text = "Edit Nation" if is_editing else "Add New Nation"
        TextLabel(rect=(10, 10, 260, 20), text=header_text, font=c.get_font(c.FONT_PATH, 18), color=c.UI_FONT_COLOR, parent=add_edit_panel)
        
        initial_name = self.game_app.nations[active_id]['name'] if is_editing else self.game_app.new_nation_name
        
        name_cb = None
        if is_editing:
            if can_edit_basic: name_cb = self.game_app.update_nation_name
        else:
            if is_admin: name_cb = self.game_app.set_new_nation_name

        name_input = InputField(rect=(10, 40, 260, 30), initial_text=initial_name, on_change=name_cb, parent=add_edit_panel)
        
        color_cb = None
        if is_editing:
            if can_edit_basic: color_cb = self.game_app.update_nation_color
        else:
            if is_admin: color_cb = self.game_app.set_new_nation_color

        color_picker = ColorPicker(rect=(10, 80, 260, 100), on_color_change=color_cb, parent=add_edit_panel)
        initial_color = self.game_app.nations[active_id]['color'] if is_editing else self.game_app.new_nation_color
        color_picker.set_color(initial_color)
        
        final_height = 270

        if is_editing:
            if is_admin:
                slot_row = UIElement(pygame.Rect(10, 190, 260, 30), parent=add_edit_panel)
                TextLabel(rect=(0, 5, 120, 20), text="Research Slots:", font=c.get_font(c.FONT_PATH, 16), color=c.UI_FONT_COLOR, parent=slot_row)
                current_slots = self.game_app.nations[active_id].get('research_slots', 1)
                def on_slots_change(old, new, nid=active_id):
                    try: self.game_app.nations[nid]['research_slots'] = max(1, int(new))
                    except ValueError: pass
                InputField(rect=(130, 0, 50, 30), initial_text=str(current_slots), on_submit=on_slots_change, parent=slot_row)
                
                Checkbox(rect=(10, 230, 260, 25), text="Is Special (No MP Limit)", initial_state=self.game_app.nations[active_id].get('is_special', False), on_toggle=lambda state: self.game_app.toggle_special_nation(active_id), parent=add_edit_panel)
                Button(rect=(10, 260, 125, 30), text="Delete", on_click=self.game_app.delete_active_nation, parent=add_edit_panel)
                Button(rect=(145, 260, 125, 30), text="Deselect", on_click=self.game_app.deselect_nation, parent=add_edit_panel)
                final_height = 300
            else:
                final_height = 190 # Just Name/Color controls for player
        else:
            if is_admin:
                Button(rect=(10, 190, 260, 30), text="Add Nation", on_click=self.game_app.add_nation, parent=add_edit_panel)
            else:
                TextLabel(rect=(10, 190, 260, 30), text="Select a nation to view.", font=c.get_font(c.FONT_PATH, 16), color=c.UI_FONT_COLOR, parent=add_edit_panel, center_align=True)
            final_height = 230

        add_edit_panel.rect.height = final_height
        elements.append({'element': add_edit_panel, 'height': final_height + 10})

        # Nation List Filtering
        nations_to_list = []
        if is_admin:
            nations_to_list = sorted(self.game_app.nations.items(), key=lambda item: item[1]['name'])
        elif player_nation_id and player_nation_id in self.game_app.nations:
            nations_to_list = [(player_nation_id, self.game_app.nations[player_nation_id])]

        for nid, ndata in nations_to_list:
            btn = NationListButton(rect=(10,0,280,40), nation_data=ndata, on_click=lambda i=nid: self.game_app.set_active_nation(i))
            btn.is_active = (self.game_app.active_nation_id == nid)
            elements.append({'element': btn, 'height': 45})

        panel.rebuild_content(elements)

    def toggle_category(self, cat_name):
        self.category_states[cat_name] = not self.category_states.get(cat_name, True)
        self.rebuild_active_tool_panel()

    def rebuild_active_tool_panel(self):
        tool = self.game_app.current_tool
        
        if tool not in ['add_unit', 'add_feature']:
            self.placement_filter_text = ""

        if not tool or tool not in self.sub_panels:
            return
            
        old_panel = self.sub_panels.get(tool)
        if old_panel and old_panel in self.root.children:
            self.root.children.remove(old_panel)
            
        new_panel = None
        if tool == 'add_unit':
            new_panel = self.create_category_panel(c.UNIT_TYPES, 'unit_type')
        elif tool == 'add_feature':
            new_panel = self.create_category_panel(c.FEATURE_TYPES, 'feature_type')
        elif tool == 'paint_land':
            new_panel = self.create_brush_panel(c.LAND_COLORS, 'paint_land')
        elif tool == 'paint_nation':
            new_panel = self.create_brush_panel(None, 'paint_nation')
        elif tool == 'paint_fog':
            new_panel = self.create_brush_panel(None, 'paint_fog')
        elif tool == 'add_strait':
            new_panel = self.create_brush_panel({}, 'strait_type')
        elif tool == 'add_arrow':
            new_panel = self.create_sub_panel(c.ARROW_ORDERS, 'arrow_order')
            
        if new_panel:
            self.sub_panels[tool] = new_panel

    def build_ui(self):
        self.root.children.clear()
        self.tool_buttons = {}

        # --- TOP BAR ---
        top_bar_height = 50
        top_bar = Panel(rect=(0, 0, c.SCREEN_WIDTH, top_bar_height), parent=self.root)

        is_admin = (self.game_app.main_app.user_mode == 'editor')

        # Top-Left: Game Menu
        game_menu_buttons = [
            ('menu', 'logout_icon.png', "Main Menu", lambda: self.game_app.main_app.change_state('TITLE')),
            ('save', 'save_icon.png', "Save Map Local", self.game_app.save_map),
            ('load', 'load_icon.png', "Load Map Local", self.game_app.load_map),
            ('export', 'export_icon.png', "Export as PNG", self.game_app.export_map_to_image),
            ('logout', 'logout_icon.png', "Logout", self.game_app.main_app.logout)
        ]
        
        # Admin / Player Cloud Buttons
        if is_admin:
            game_menu_buttons.insert(1, ('push', 'save_icon.png', "Push Map to Cloud", self.game_app.admin_push_map))
        else:
            game_menu_buttons.insert(1, ('submit', 'save_icon.png', "Submit Turn", self.game_app.player_submit_turn))

        for i, (name, icon, tip, action) in enumerate(game_menu_buttons):
            # Use red color for special cloud buttons to distinguish them
            btn = Button(rect=(10 + i * 45, 5, 40, 40), on_click=action, icon_path=f'assets/icons/{icon}', tooltip=tip, parent=top_bar)
            if name in ['push', 'submit']:
                # HACK: Manually tint the button rect in draw later or just accept standard look. 
                # Let's rely on tooltip for now.
                pass

        # ... [Turn Panel (Center Top) - SAME AS BEFORE] ...
        turn_panel_width = 400 
        turn_panel = Panel(rect=(0, 5, turn_panel_width, 40), parent=top_bar, color=None, border_width=0)
        turn_panel.rect.centerx = top_bar.rect.centerx
        turn_panel.target_pos = turn_panel.rect.topleft

        turn_text = f"Turn: {self.game_app.turn_counter}"
        turn_label_font = c.get_font(c.FONT_PATH, 24)
        turn_label_surf = turn_label_font.render(turn_text, True, c.UI_FONT_COLOR)
        
        if self.game_app.main_app.user_mode == 'editor':
            end_turn_button = Button(rect=(0, 0, 140, 40), text="End Turn", on_click=self.game_app.next_turn)
            total_width = end_turn_button.rect.width + turn_label_surf.get_width() + 20
            group_start_x = (turn_panel_width - total_width) / 2
            end_turn_button.rect.topleft = (group_start_x, 0)
            turn_panel.add_child(end_turn_button)
            label_x = end_turn_button.rect.right + 20
            TextLabel(rect=(label_x, 0, turn_label_surf.get_width(), 40), text=turn_text, font=turn_label_font, color=c.UI_FONT_COLOR, parent=turn_panel)
        else:
            label_x = (turn_panel_width - turn_label_surf.get_width()) / 2
            TextLabel(rect=(label_x, 0, turn_label_surf.get_width(), 40), text=turn_text, font=turn_label_font, color=c.UI_FONT_COLOR, parent=turn_panel)

        # ... [Top-Right: Core Menus - SAME AS BEFORE] ...
        self.tech_tree_button = None
        self.nation_button = None
        def open_tech_tree(): self.game_app.main_app.change_state('TECH_TREE')
        core_menu_buttons = [
            ('manage_nations', 'nation_icon.png', "Manage Nations", self.game_app.toggle_nations_panel),
            ('tech_tree', 'tech_tree_icon.png', "Tech Tree", open_tech_tree),
            ('encyclopedia', 'encyclopedia_icon.png', "Encyclopedia", lambda: self.game_app.main_app.change_state('ENCYCLOPEDIA')),
            ('search', 'find_icon.png', "Search Entities", self.toggle_search_panel)
        ]
        for i, (name, icon, tip, action) in enumerate(core_menu_buttons):
            btn = Button(rect=(c.SCREEN_WIDTH - 50 - i * 45, 5, 40, 40), on_click=action, icon_path=f'assets/icons/{icon}', tooltip=tip, parent=top_bar)
            if name == 'manage_nations': self.tool_buttons['manage_nations'] = btn; self.nation_button = btn
            if name == 'tech_tree': self.tech_tree_button = btn

        # ... [Bottom Bar - SAME AS BEFORE] ...
        bottom_bar_y = c.SCREEN_HEIGHT - 80
        toolbar_panel = Panel(rect=(10, bottom_bar_y, 500, 70), parent=self.root)
        user_mode = self.game_app.main_app.user_mode
        tool_list = [('select', 'paint_icon.png', "Select Tool (Q)")]
        if user_mode == 'editor':
            tool_list.extend([('paint_nation', 'paint_icon.png', "Paint Territory"), ('paint_land', 'terrain_icon.png', "Paint Land"), ('paint_fog', 'fog_icon.png', "Paint Fog"), ('add_unit', 'unit_icon.png', "Add Unit"), ('add_feature', 'feature_icon.png', "Add Feature"), ('add_strait', 'arrow_icon.png', "Add Strait/Blockade")])
        tool_list.extend([('add_arrow', 'arrow_icon.png', "Draw Arrow"), ('add_text', 'add_note_icon.png', "Add Text/Note"), ('clear_arrows', 'clear_arrows_icon.png', "Clear Orders")])
        for i, (name, icon, tip) in enumerate(tool_list):
            action = self.game_app.clear_arrows if name == 'clear_arrows' else (lambda n=name: self.game_app.set_tool(n))
            btn = Button(rect=(10 + i * 55, 10, 50, 50), on_click=action, icon_path=f'assets/icons/{icon}', tooltip=tip, parent=toolbar_panel)
            self.tool_buttons[name] = btn
        toolbar_panel.rect.width = 20 + len(tool_list) * 55
        self.toolbar_panel = toolbar_panel

        # ... [Minimap Hub - SAME AS BEFORE] ...
        minimap_hub_width = 240
        minimap_hub = Panel(rect=(0, 0, minimap_hub_width, 230), parent=self.root, color=None, border_width=0)
        minimap_hub.rect.bottomright = (c.SCREEN_WIDTH - 10, c.SCREEN_HEIGHT - 35)
        minimap_hub.target_pos = minimap_hub.rect.topleft
        if not hasattr(self.game_app.minimap, 'parent') or self.game_app.minimap.parent != minimap_hub:
             self.game_app.minimap.rect = pygame.Rect(20, 70, 200, 200) 
             minimap_hub.add_child(self.game_app.minimap)
        view_options_panel = Panel(rect=(0, 0, minimap_hub_width, 60), parent=minimap_hub)
        self.text_display_button = Button(rect=(10, 5, 45, 50), on_click=lambda: setattr(self.game_app, 'show_territory_names', not self.game_app.show_territory_names), parent=view_options_panel, icon_path='assets/icons/text_display_icon.png', tooltip="Toggle Territory Names")
        self.layer_switch_button = Button(rect=(60, 5, 45, 50), on_click=self.game_app.switch_layer, parent=view_options_panel, icon_path='assets/icons/layers_icon.png', tooltip="Switch Layer")
        self.manpower_overlay_button = Button(rect=(110, 5, 45, 50), on_click=lambda: setattr(self.game_app, 'show_manpower_overlay', not self.game_app.show_manpower_overlay), parent=view_options_panel, icon_path='assets/icons/manpower_icon.png', tooltip="Toggle Manpower Overlay")
        self.alliance_mode_button = Button(rect=(160, 5, 45, 50), text="ALL", on_click=self.game_app.toggle_alliance_map_mode, parent=view_options_panel, tooltip="Toggle Alliance Map Mode")
        
        # --- UI Panels ---
        self.delete_selected_button = Button(rect=(c.SCREEN_WIDTH/2 - 120, -50, 240, 40), text="", on_click=lambda: self.game_app.delete_multi_selected(), parent=self.root)
        if self.game_app.main_app.user_mode == 'editor':
             self.admin_panel_button = Button(rect=(c.SCREEN_WIDTH - 200, top_bar_height + 10, 190, 30), text="Admin Panel", on_click=self.toggle_admin_panel, parent=self.root)
             self.admin_panel = ScrollablePanel(rect=(c.SCREEN_WIDTH / 2 - 250, c.SCREEN_HEIGHT, 500, 450), parent=self.root, max_height=c.SCREEN_HEIGHT-100)
             self.rebuild_admin_panel()
             self.admin_panel_visible = False
        
        self.leaderboard_panel = ScrollablePanel(rect=pygame.Rect(10, c.SCREEN_HEIGHT, 250, 250), parent=self.root, max_height=250)
        self.setup_sub_panels()
        self.rebuild_search_panel()

    def toggle_search_panel(self):
        self.search_panel_visible = not self.search_panel_visible
        if self.search_panel_visible:
            self.rebuild_search_panel()

    def rebuild_search_panel(self):
        if self.search_panel and self.search_panel in self.root.children:
            self.root.children.remove(self.search_panel)

        panel = Panel(rect=(c.SCREEN_WIDTH / 2 - 200, -410, 400, 400), parent=self.root)
        
        search_input = InputField(rect=(10, 10, 380, 30), initial_text="", on_change=self.perform_search)
        panel.add_child(search_input)

        results_panel = ScrollablePanel(rect=(10, 50, 380, 340), parent=panel, color=(40,45,50))
        panel.add_child(results_panel)
        
        self.search_panel = panel
        self.search_results_panel = results_panel
        self.perform_search("")

    def perform_search(self, query):
        query = query.lower().strip()
        results = []
        if query:
            # Only search through the game's features
            for feature in self.game_app.features:
                # The 'feature.name' attribute holds the custom name you've entered.
                feature_name = feature.name
                
                if query in feature_name.lower():
                    # Add the custom name to the results list
                    results.append({'name': feature_name, 'entity': feature})
        
        elements = []
        # Display the custom name in the result button
        for res in results:
            btn = Button(rect=(10, 0, 340, 30), text=res['name'], on_click=lambda e=res['entity']: self.pan_to_entity(e))
            elements.append({'element': btn, 'height': 35})
        
        self.search_results_panel.rebuild_content(elements)

    def pan_to_entity(self, entity):
        world_x, world_y = self.game_app.map.camera.grid_to_world(entity.grid_x, entity.grid_y)
        self.game_app.map.camera.center_on(world_x, world_y)
        
        self.game_app.clear_selection()
        self.game_app.multi_selected_entities.append(entity)
        self.game_app.ui_manager.rebuild_selection_info_panel()

        self.search_panel_visible = False

    def toggle_admin_panel(self):
        self.admin_panel_visible = not self.admin_panel_visible
        if self.admin_panel_visible:
            self.rebuild_admin_panel()

    def toggle_fog_and_rebuild(self):
        self.game_app.toggle_fog_of_war()
        self.rebuild_admin_panel()

    def toggle_fog_and_rebuild(self):
        self.game_app.toggle_fog_of_war()
        self.rebuild_admin_panel()

    def rebuild_leaderboard(self):
        panel = self.leaderboard_panel
        elements = []

        manpower_data = self.game_app.manpower_data
        nations = self.game_app.nations
        grand_total = self.game_app.grand_total_manpower
        
        sorted_nations = sorted(manpower_data.items(), key=lambda item: item[1]['total'], reverse=True)

        title_font = c.get_font(c.FONT_PATH, 18)
        body_font = c.get_font(c.FONT_PATH, 14)

        title = TextLabel(pygame.Rect(10, 0, 230, 20), "Leaderboard", title_font, c.UI_FONT_COLOR, center_align=True)
        elements.append({'element': title, 'height': 30})

        for nid, data in sorted_nations:
            nation_info = nations.get(nid)
            if not nation_info: continue

            nation_name = nation_info['name']
            total = data['total']
            used = data['used']
            strength = data['strength']
            techs = data['techs']
            is_special = nation_info.get('is_special', False)
            
            if is_special:
                manpower_text = f"MP: {used} / ∞"
            else:
                percentage = (total / grand_total * 100) if grand_total > 0 else 0
                manpower_text = f"MP: {used} / {total} ({percentage:.0f}%)"
            
            row = LeaderboardRow(
                rect=pygame.Rect(10, 0, 230, 40),
                nation_id=nid,
                nation_color=nation_info['color'],
                nation_name=nation_name,
                manpower_text=manpower_text,
                used=used,
                total=total,
                is_special=is_special,
                strength=strength,
                techs=techs,
                font=body_font
            )
            elements.append({'element': row, 'height': 45})
        
        panel.rebuild_content(elements)
        panel.rect.height = min(350, panel.content_height)

    def toggle_admin_category(self, cat_name):
        self.category_states[cat_name] = not self.category_states.get(cat_name, True)
        self.rebuild_admin_panel()

    def set_admin_nation(self, nid):
        self.admin_selected_nation_id = nid
        self.rebuild_admin_panel()
        self.toggle_admin_category("player_nations")

    def remove_player(self, name):
        if name in self.game_app.player_list:
            del self.game_app.player_list[name]
            self.rebuild_admin_panel()
    
    def remove_alliance(self, name):
        if name in self.game_app.alliances:
            del self.game_app.alliances[name]
            self.rebuild_admin_panel()
    
    def toggle_alliance_nation(self, nid, state):
        if state:
            self.admin_selected_alliance_nations.add(nid)
        elif nid in self.admin_selected_alliance_nations:
            self.admin_selected_alliance_nations.remove(nid)

    def create_alliance(self):
        name = self.new_alliance_name_input.text
        if name and name != "New Alliance Name" and self.admin_selected_alliance_nations:
            self.game_app.alliances[name] = list(self.admin_selected_alliance_nations)
            self.admin_selected_alliance_nations.clear()
            self.rebuild_admin_panel()
            
    def set_ai_difficulty(self, difficulty):
        self.game_app.selected_ai_difficulty = difficulty
        self.rebuild_admin_panel()

    def rebuild_admin_panel(self):
        panel = self.admin_panel
        elements = []
        
        # --- TURN REVIEW SECTION ---
        elements.append({'element': CategoryHeader(pygame.Rect(10,0,480,30), "Turn Reviews (Git)", lambda c="turn_review": self.toggle_admin_category(c), self.category_states.get("turn_review", True)), 'height': 35})
        if self.category_states.get("turn_review", True):
            if self.game_app.preview_mode:
                # Preview Mode Controls
                status_row = UIElement(pygame.Rect(10, 0, 480, 40))
                TextLabel(rect=(0,10,200,30), text=f"Previewing: {self.game_app.preview_filename}", font=c.get_font(c.FONT_PATH, 16), color=c.COLOR_YELLOW, parent=status_row)
                Button(rect=(210,0,120,40), text="INTEGRATE", on_click=self.game_app.integrate_preview, parent=status_row)
                Button(rect=(340,0,120,40), text="DISCARD", on_click=self.game_app.discard_preview, parent=status_row)
                elements.append({'element': status_row, 'height': 50})
                
                # Exit preview button
                elements.append({'element': Button(rect=(10,0,470,30), text="Cancel Preview (Back to Master)", on_click=self.game_app.revert_preview), 'height': 40})
            else:
                # List files
                from save_load_manager import get_player_turn_files
                files = get_player_turn_files()
                if not files:
                    elements.append({'element': TextLabel(pygame.Rect(10,0,470,30), "No pending turns.", c.get_font(c.FONT_PATH, 16), c.UI_FONT_COLOR, center_align=True), 'height': 40})
                else:
                    for f in files:
                        row = UIElement(pygame.Rect(10, 0, 480, 40))
                        TextLabel(rect=(0,10,350,30), text=f, font=c.get_font(c.FONT_PATH, 14), color=c.UI_FONT_COLOR, parent=row)
                        Button(rect=(360,0,110,35), text="Preview", on_click=lambda fname=f: self.game_app.load_preview_turn(fname), parent=row)
                        elements.append({'element': row, 'height': 45})

        # ... [AI Control Section - SAME AS BEFORE] ...
        elements.append({'element': CategoryHeader(pygame.Rect(10,0,480,30), "AI Control", lambda c="ai_control": self.toggle_admin_category(c), self.category_states.get("ai_control", True)), 'height': 35})
        if self.category_states.get("ai_control", True):
            diff_row = UIElement(pygame.Rect(10, 0, 480, 30))
            TextLabel(pygame.Rect(0,5,80,20), "Difficulty:", c.get_font(c.FONT_PATH, 16), c.UI_FONT_COLOR, diff_row)
            difficulties = ['Easy', 'Normal', 'Hard', 'Impossible']
            btn_width = (400 - 15) // len(difficulties)
            for i, diff in enumerate(difficulties):
                btn = Button(rect=(90 + i * (btn_width + 5), 0, btn_width, 30), text=diff, on_click=lambda d=diff: self.set_ai_difficulty(d))
                if self.game_app.selected_ai_difficulty == diff: btn.is_active = True
                diff_row.add_child(btn)
            elements.append({'element': diff_row, 'height': 40})
            if self.game_app.ai_is_thinking:
                status_label = TextLabel(pygame.Rect(10,0,480,20), "AI is thinking...", c.get_font(c.FONT_PATH, 16), c.COLOR_YELLOW, center_align=True)
                elements.append({'element': status_label, 'height': 30})
            else:
                for nid, ndata in self.game_app.nations.items():
                    ai_row = UIElement(pygame.Rect(10, 0, 480, 30))
                    TextLabel(pygame.Rect(0, 5, 200, 20), ndata['name'], c.get_font(c.FONT_PATH, 16), ndata['color'], ai_row)
                    Button(rect=(210, 0, 260, 30), text="Generate AI Orders", on_click=lambda n=nid: self.game_app.start_ai_for_nation(n), parent=ai_row)
                    elements.append({'element': ai_row, 'height': 40})

        # ... [Map Style Section - SAME AS BEFORE] ...
        elements.append({'element': CategoryHeader(pygame.Rect(10,0,480,30), "Map Style", lambda c="map_style": self.toggle_admin_category(c), self.category_states.get("map_style", True)), 'height': 35})
        if self.category_states.get("map_style", True):
            style_row = UIElement(pygame.Rect(10, 0, 480, 70))
            styles = self.game_app.main_app.style_manager.styles
            btn_width, btn_height = 110, 30
            x_offset, y_offset = 0, 0
            for style_name in styles.keys():
                if x_offset + btn_width > 470: x_offset = 0; y_offset += btn_height + 5
                btn = Button(rect=(x_offset, y_offset, btn_width, btn_height), text=style_name, on_click=lambda s=style_name: self.game_app.main_app.style_manager.set_style(s, self.game_app))
                if style_name == self.game_app.main_app.style_manager.active_style_name: btn.is_active = True
                style_row.add_child(btn)
                x_offset += btn_width + 5
            style_row.rect.height = y_offset + btn_height
            elements.append({'element': style_row, 'height': style_row.rect.height + 10})

        # ... [Map Tools Section - SAME AS BEFORE] ...
        elements.append({'element': CategoryHeader(pygame.Rect(10,0,480,30), "Map Tools", lambda c="map_tools": self.toggle_admin_category(c), self.category_states.get("map_tools", True)), 'height': 35})
        if self.category_states.get("map_tools", True):
            resize_row = UIElement(pygame.Rect(10, 0, 480, 30))
            TextLabel(pygame.Rect(0,5,180,20), f"Resize Map ({self.game_app.current_layer_key})", c.get_font(c.FONT_PATH, 16), c.UI_FONT_COLOR, resize_row)
            self.width_input = InputField(rect=(190, 0, 80, 30), initial_text=str(self.game_app.map.width), parent=resize_row)
            TextLabel(pygame.Rect(275,5,20,20), "x", c.get_font(c.FONT_PATH, 18), c.UI_FONT_COLOR, resize_row, center_align=True)
            self.height_input = InputField(rect=(300, 0, 80, 30), initial_text=str(self.game_app.map.height), parent=resize_row)
            Button(rect=(390, 0, 80, 30), text="Apply", on_click=self.apply_map_resize, parent=resize_row)
            elements.append({'element': resize_row, 'height': 40})
            
            turn_row = UIElement(pygame.Rect(10, 0, 480, 30))
            TextLabel(pygame.Rect(0,5,100,20), "Current Turn:", c.get_font(c.FONT_PATH, 16), c.UI_FONT_COLOR, turn_row)
            self.turn_input = InputField(rect=(110, 0, 80, 30), initial_text=str(self.game_app.turn_counter), parent=turn_row)
            Button(rect=(200, 0, 80, 30), text="Set", on_click=self.apply_turn_change, parent=turn_row)
            Button(rect=(290, 0, 180, 30), text="Next Turn", on_click=self.game_app.next_turn, parent=turn_row)
            elements.append({'element': turn_row, 'height': 40})
            
            elements.append({'element': Button(rect=(10, 0, 470, 30), text="Commence All Orders", on_click=self.game_app.commence_all_moves), 'height': 40})
            shift_row = UIElement(pygame.Rect(10, 0, 480, 30))
            TextLabel(pygame.Rect(0,5,80,20), "Rotate Map:", c.get_font(c.FONT_PATH, 16), c.UI_FONT_COLOR, shift_row)
            Button(rect=(90, 0, 80, 30), text="-90°", on_click=lambda: self.game_app.commence_map_rotation(-90), parent=shift_row)
            Button(rect=(180, 0, 80, 30), text="+90°", on_click=lambda: self.game_app.commence_map_rotation(90), parent=shift_row)
            elements.append({'element': shift_row, 'height': 40})
            elements.append({'element': Button(rect=(10, 0, 470, 30), text="Auto-Balance Territories", on_click=self.game_app.auto_balance_territories), 'height': 40})
            fog_button_text = "Disable Fog" if self.game_app.fog_of_war_enabled else "Enable Fog"
            elements.append({'element': Button(rect=(10, 0, 470, 30), text=fog_button_text, on_click=self.toggle_fog_and_rebuild), 'height': 40})

        # ... [Player/Alliance Management - SAME AS BEFORE] ...
        elements.append({'element': CategoryHeader(pygame.Rect(10,0,480,30), "Player Management", lambda c="players": self.toggle_admin_category(c), self.category_states.get("players", True)), 'height': 35})
        if self.category_states.get("players", True):
            add_player_row = UIElement(pygame.Rect(10, 0, 480, 65))
            self.new_player_name_input = InputField(rect=(0,0,140,30), initial_text="Login Name", parent=add_player_row)
            self.new_player_nick_input = InputField(rect=(150,0,140,30), initial_text="Nickname", parent=add_player_row)
            nation_name = self.game_app.nations[self.admin_selected_nation_id]['name'] if self.admin_selected_nation_id else "Select Nation"
            Button(rect=(0,35,140,30), text=nation_name, on_click=lambda: self.toggle_admin_category("player_nations"), parent=add_player_row)
            Button(rect=(150,35,140,30), text="Add Player", on_click=self.add_player, parent=add_player_row)
            elements.append({'element': add_player_row, 'height': 75})
            if self.category_states.get("player_nations", False):
                for nid, ndata in self.game_app.nations.items():
                    btn = NationListButton(rect=(10, 0, 200, 30), nation_data=ndata, on_click=lambda i=nid: self.set_admin_nation(i))
                    elements.append({'element': btn, 'height': 35})
            for name, p_data in self.game_app.player_list.items():
                player_row = UIElement(pygame.Rect(10, 0, 480, 30))
                nation_name = self.game_app.nations.get(p_data.get('nation_id'), {}).get('name', 'N/A')
                nickname_input = InputField(rect=(0,0,140,30), initial_text=p_data.get('nickname', name), on_submit=lambda old, new, n=name: self.game_app.update_player_nickname(n, new), parent=player_row)
                TextLabel(pygame.Rect(150,5,250,20), f"({name}) -> {nation_name}", c.get_font(c.FONT_PATH, 16), c.UI_FONT_COLOR, player_row)
                Button(rect=(410,0,60,30), text="Del", on_click=lambda n=name: self.remove_player(n), parent=player_row)
                elements.append({'element': player_row, 'height': 35})

        elements.append({'element': CategoryHeader(pygame.Rect(10,0,480,30), "Alliance Management", lambda c="alliances": self.toggle_admin_category(c), self.category_states.get("alliances", True)), 'height': 35})
        if self.category_states.get("alliances", True):
            add_alliance_row = UIElement(pygame.Rect(10, 0, 480, 30))
            self.new_alliance_name_input = InputField(rect=(0,0,200,30), initial_text="New Alliance Name", parent=add_alliance_row)
            Button(rect=(210,0,260,30), text="Create Alliance w/ Selected", on_click=self.create_alliance, parent=add_alliance_row)
            elements.append({'element': add_alliance_row, 'height': 40})
            for nid, ndata in self.game_app.nations.items():
                chk = Checkbox(rect=(15, 0, 460, 25), text=ndata['name'], initial_state=nid in self.admin_selected_alliance_nations, on_toggle=lambda state, i=nid: self.toggle_alliance_nation(i, state))
                elements.append({'element': chk, 'height': 30})
            for name, members in self.game_app.alliances.items():
                alliance_row = UIElement(pygame.Rect(10, 0, 480, 30))
                member_names = ", ".join([self.game_app.nations.get(nid, {}).get('name', 'N/A') for nid in members])
                label_wrap = TextLabel(pygame.Rect(0,5,400,20), f"{name}: {member_names}", c.get_font(c.FONT_PATH, 14), c.UI_FONT_COLOR, alliance_row, wrap_width=400)
                Button(rect=(410,0,60,30), text="Del", on_click=lambda n=name: self.remove_alliance(n), parent=alliance_row)
                elements.append({'element': alliance_row, 'height': label_wrap.rect.height + 10})

        panel.rebuild_content(elements)
        panel.rect.height = min(panel.max_height, panel.content_height)
        
    def apply_map_resize(self):
        try:
            new_width = int(self.width_input.text)
            new_height = int(self.height_input.text)
            
            if new_width > 0 and new_height > 0:
                self.game_app.resize_map(new_width, new_height)
            else:
                print("Error: Map dimensions must be positive.")
                # Reset to current values
                self.width_input.set_text(str(self.game_app.map.width))
                self.height_input.set_text(str(self.game_app.map.height))

        except ValueError:
            print("Error: Invalid input for map dimensions. Please enter numbers.")
            self.width_input.set_text(str(self.game_app.map.width))
            self.height_input.set_text(str(self.game_app.map.height))
        
    def on_placement_filter_change(self, text):
        self.placement_filter_text = text
        self.rebuild_active_tool_panel()

    def add_player(self):
        name = self.new_player_name_input.text
        nickname = self.new_player_nick_input.text
        if name and nickname and self.admin_selected_nation_id:
            self.game_app.player_list[name] = {'nation_id': self.admin_selected_nation_id, 'nickname': nickname}
            self.rebuild_admin_panel()
            
    def apply_turn_change(self):
        try:
            new_turn = int(self.turn_input.text)
            if new_turn >= 0:
                self.game_app.turn_counter = new_turn
                self.build_ui()
        except ValueError:
            print("Invalid turn number provided.")
            self.turn_input.set_text(str(self.game_app.turn_counter))

    def rebuild_selection_info_panel(self):
        panel = self.selection_info_panel
        game = self.game_app
        
        if not game.multi_selected_entities:
            panel.visible = False
            return

        panel.visible = True
        elements = []

        font_head = c.get_font(c.FONT_PATH, 18)
        font_body = c.get_font(c.FONT_PATH, 16)

        if len(game.multi_selected_entities) > 1:
            text = f"{len(game.multi_selected_entities)} entities selected"
            label = TextLabel(pygame.Rect(10,0,180,20), text, font_head, c.UI_FONT_COLOR)
            elements.append({'element': label, 'height': 30})
        else:
            entity = game.multi_selected_entities[0]
            name = entity.properties['name'] if isinstance(entity, Unit) else (entity.name if hasattr(entity, 'name') else "Arrow")
            
            title_text = "Note" if isinstance(entity, MapText) and entity.author_username else name
            title = TextLabel(pygame.Rect(10,0,180,20), title_text, font_head, c.UI_FONT_COLOR, wrap_width=180)
            elements.append({'element': title, 'height': title.rect.height + 10})

            if isinstance(entity, MapText):
                is_owner = game.main_app.username == entity.author_username
                is_admin = game.main_app.user_mode == 'editor'
                can_edit = is_owner or is_admin

                if entity.author_username:
                    author_user = entity.author_username
                    player_data = game.player_list.get(author_user, {})
                    author_nick = player_data.get('nickname', author_user)
                    nation_id = player_data.get('nation_id')
                    nation_name = game.nations.get(nation_id, {}).get('name', 'Unknown')
                    author_label = TextLabel(pygame.Rect(10,0,180,20), f"From: {nation_name}", font_body, c.UI_FONT_COLOR, wrap_width=180)
                    elements.append({'element': author_label, 'height': author_label.rect.height + 5})

                text_label = TextLabel(pygame.Rect(10,0,180,20), "Content:", font_body, c.UI_FONT_COLOR)
                elements.append({'element': text_label, 'height': 25})
                if can_edit:
                    on_submit_callback = lambda old, new, e=entity: game.do_action(actions.PropertyChangeAction(e, 'text', old, new))
                    text_input = MultilineInputField(rect=(10, 0, 180, 60), initial_text=entity.text, on_submit=on_submit_callback)
                    text_input.on_resize = self.rebuild_selection_info_panel
                    elements.append({'element': text_input, 'height': text_input.rect.height + 10})
                else:
                    content_label = TextLabel(pygame.Rect(10,0,180,20), entity.text, font_body, c.UI_FONT_COLOR, wrap_width=180)
                    elements.append({'element': content_label, 'height': content_label.rect.height + 10})
                
                if can_edit:
                    size_row = UIElement(pygame.Rect(10, 0, 180, 30))
                    TextLabel(pygame.Rect(0,5,80,20), "Size:", font_body, c.UI_FONT_COLOR, size_row)
                    Button(rect=(90, 5, 25, 25), text="-", on_click=lambda e=entity: game.do_action(actions.PropertyChangeAction(e, 'font_size', e.font_size, max(8, e.font_size-2))), parent=size_row)
                    TextLabel(pygame.Rect(120,5,30,20), str(entity.font_size), font_body, c.UI_FONT_COLOR, size_row, center_align=True)
                    Button(rect=(155, 5, 25, 25), text="+", on_click=lambda e=entity: game.do_action(actions.PropertyChangeAction(e, 'font_size', e.font_size, min(72, e.font_size+2))), parent=size_row)
                    elements.append({'element': size_row, 'height': 40})

                imp_row = UIElement(pygame.Rect(10, 0, 180, 30))
                TextLabel(pygame.Rect(0,5,80,20), "Importance:", font_body, c.UI_FONT_COLOR, imp_row)
                for i in range(6):
                    class ImpButton(Button):
                        def draw(self, surface):
                            color = c.COLOR_YELLOW if self.is_active else (c.UI_BUTTON_HOVER_COLOR if self.is_hovered else (50,50,55))
                            pygame.draw.circle(surface, color, self.rect.center, 7)
                    imp_btn = ImpButton(rect=(90 + i*16, 5, 15, 20), on_click=lambda v=i, e=entity: game.do_action(actions.PropertyChangeAction(e, 'importance', e.importance, v)) if can_edit else None, parent=imp_row)
                    if entity.importance >= i: imp_btn.is_active = True
                elements.append({'element': imp_row, 'height': 40})
                
                vis_row = UIElement(pygame.Rect(10, 0, 180, 30))
                TextLabel(pygame.Rect(0,5,80,20), "Visible to:", font_body, c.UI_FONT_COLOR, vis_row)
                if can_edit:
                    vis_types = [('private', 'S', 'Private (Self)'), ('alliance', 'A', 'Alliance'), ('public', 'E', 'Public (Everyone)')]
                    btn_width = 100 // len(vis_types)
                    for i, (v_type, label, tip) in enumerate(vis_types):
                        btn = Button(rect=(90 + i*(btn_width+2), 5, btn_width, 20), text=label, tooltip=tip, on_click=lambda v=v_type, e=entity: game.do_action(actions.PropertyChangeAction(e, 'visibility', e.visibility, v)), parent=vis_row)
                        if entity.visibility == v_type: btn.is_active = True
                else:
                    TextLabel(pygame.Rect(90,5,80,20), entity.visibility.title(), font_body, c.UI_FONT_COLOR, vis_row)
                elements.append({'element': vis_row, 'height': 40})

            elif isinstance(entity, MapFeature) and game.main_app.user_mode == 'editor':
                name_label = TextLabel(pygame.Rect(10,0,180,20), "Name:", font_body, c.UI_FONT_COLOR)
                elements.append({'element': name_label, 'height': 25})
                
                on_submit_callback = lambda old, new, e=entity: self.game_app.do_action(actions.PropertyChangeAction(e, 'name', old, new))
                name_input = InputField(rect=(10, 0, 180, 30), initial_text=entity.name, on_submit=on_submit_callback)
                elements.append({'element': name_input, 'height': 40})

                # Define the cycles for feature types that can be swapped
                FEATURE_CYCLES = [
                    ['city', 'a_city'],
                    ['village', 'a_village'],
                    ['quarry', 'quarry_empty'],
                    ['city', 'village', 'fort']
                ]

                current_type = entity.feature_type
                cycle_list = None
                for cycle in FEATURE_CYCLES:
                    if current_type in cycle:
                        cycle_list = cycle
                        break

                if cycle_list:
                    current_index = cycle_list.index(current_type)
                    next_index = (current_index + 1) % len(cycle_list)
                    next_type_key = cycle_list[next_index]

                    next_type_name = "Unknown"
                    for category in c.FEATURE_TYPES.values():
                        if next_type_key in category:
                            next_type_name = category[next_type_key]['name']
                            break
                    
                    def on_cycle_click(e=entity, n_type=next_type_key):
                        game.do_action(actions.ChangeFeatureTypeAction(e, n_type))

                    cycle_btn = Button(rect=(10, 0, 180, 30), text=f"Cycle to: {next_type_name}", on_click=on_cycle_click)
                    elements.append({'element': cycle_btn, 'height': 40})


            elif isinstance(entity, Unit):
                arrow_chain = game.get_arrow_chain_for_unit(entity)
                effective_stats, bonuses = entity.get_effective_stats(game)
                
                can_control_unit = game.main_app.user_mode == 'editor' or \
                                   (game.main_app.user_mode == 'player' and entity.nation_id == game.main_app.player_nation_id)
                
                if can_control_unit:
                    rotate_btn = Button(rect=(10, 0, 180, 30), text=f"Rotate ({entity.rotation}°)", on_click=game.rotate_selected_unit)
                    elements.append({'element': rotate_btn, 'height': 40})
                    
                    if entity.status == 'active' and not arrow_chain:
                        status_row = UIElement(pygame.Rect(10, 0, 180, 30))
                        Button(rect=(0,0,85,30), text="Skip Turn", on_click=lambda e=entity: game.set_unit_status(e, 'skipped'), parent=status_row)
                        Button(rect=(95,0,85,30), text="Sleep", on_click=lambda e=entity: game.set_unit_status(e, 'sleeping'), parent=status_row)
                        elements.append({'element': status_row, 'height': 40})
                    elif entity.status == 'sleeping':
                        wake_btn = Button(rect=(10, 0, 180, 30), text="Wake Unit", on_click=lambda e=entity: game.set_unit_status(e, 'active'))
                        elements.append({'element': wake_btn, 'height': 40})
                
                if self.game_app.main_app.user_mode == 'editor':
                    upgrade_btn = Button(rect=(10, 0, 180, 30), text="Toggle Upgrade", on_click=lambda e=entity: setattr(e, 'is_upgrading', not e.is_upgrading))
                    upgrade_btn.is_active = entity.is_upgrading
                    elements.append({'element': upgrade_btn, 'height': 40})
                
                stats_header = TextLabel(pygame.Rect(10,0,180,20), "Stats", font_body, c.UI_FONT_COLOR)
                elements.append({'element': stats_header, 'height': 30})

                stat_icons = {
                    'str': 'dmg_icon.png', 'arm': 'def_icon.png', 'sup': 'sup_icon.png',
                    'spe': 'spe_icon.png', 'cost': 'cost_icon.png'
                }

                for key, icon_name in stat_icons.items():
                    if key in effective_stats:
                        stat_row = UIElement(pygame.Rect(10, 0, 180, 25))
                        
                        icon_surf, _ = c.get_scaled_asset(f"assets/icons/{icon_name}", 20)
                        ImageElement(rect=(0, 2, 20, 20), image_surf=icon_surf, parent=stat_row)

                        val = effective_stats[key]
                        bonus_val = bonuses.get(key)
                        
                        display_text = f"{val}"
                        if bonus_val:
                            op = '+' if bonus_val > 0 else ''
                            display_text = f"{val} ({op}{int(bonus_val)})"

                        TextLabel(rect=(25, 0, 150, 25), text=display_text, font=font_body, color=c.UI_FONT_COLOR, parent=stat_row)
                        elements.append({'element': stat_row, 'height': 30})

                if arrow_chain:
                    try:
                        max_spe = int(entity.get_effective_stats(game)[0].get('spe', 0))
                        current_cost = game.calculate_chain_cost(entity, arrow_chain)
                        if current_cost > max_spe:
                            warning_text = f"Exceeds SPE! ({current_cost:.1f}/{max_spe})"
                            warning_label = TextLabel(pygame.Rect(10,0,180,20), warning_text, font_body, c.COLOR_RED, wrap_width=180)
                            elements.append({'element': warning_label, 'height': warning_label.rect.height + 10})
                    except (ValueError, TypeError):
                        warning_label = TextLabel(pygame.Rect(10,0,180,20), "Invalid SPE stat!", font_body, c.COLOR_RED)
                        elements.append({'element': warning_label, 'height': 25})
                
                if entity.weight_capacity:
                    cap_text = f"Cargo: {entity.get_current_weight()}/{entity.weight_capacity} W | {len(entity.carried_units)}/{entity.max_units} U"
                    cap_label = TextLabel(pygame.Rect(10,0,180,20), cap_text, font_body, c.COLOR_CYAN)
                    elements.append({'element': cap_label, 'height': 30})

                    if entity.carried_units:
                        cargo_header = CategoryHeader(pygame.Rect(10,0,180,30), "Carried Units", lambda:None, True)
                        cargo_header.is_hovered = False
                        elements.append({'element': cargo_header, 'height': 35})
                        for unit in entity.carried_units:
                            icon_surf, _ = c.get_scaled_asset(unit.asset_path, 24)
                            unload_btn = Button(rect=(15,0,170,30), text=unit.properties['name'], icon=icon_surf, on_click=lambda u=unit, transport=entity: game.start_unloading_unit(transport, u), tooltip="Click to unload this unit")
                            is_player_unit = game.main_app.user_mode == 'player' and entity.nation_id == game.main_app.player_nation_id
                            unload_btn.is_active = (game.main_app.user_mode == 'editor' or is_player_unit)
                            elements.append({'element': unload_btn, 'height': 35})

        panel.rebuild_content(elements)
        panel.rect.height = min(panel.max_height, panel.content_height)
        
    def update_delete_button_text(self):
        if not hasattr(self, 'delete_selected_button') or not self.delete_selected_button: return
        game = self.game_app
        if not game.is_multi_selecting():
            self.delete_selected_button.text = ""
            return
        
        user_mode = game.main_app.user_mode
        player_nation_id = game.main_app.player_nation_id
        
        something_is_deletable = False
        if user_mode == 'editor':
            something_is_deletable = bool(game.multi_selected_entities)
        elif user_mode == 'player':
            for e in game.multi_selected_entities:
                if isinstance(e, Arrow) and e.nation_id == player_nation_id:
                    something_is_deletable = True
                    break
        
        if something_is_deletable:
            self.delete_selected_button.text = "Delete Selected (Del)"
        else:
            self.delete_selected_button.text = ""

    def update(self):
        # --- Centralized Tooltip Logic ---
        hovered_element = self._find_hovered_element(self.root, pygame.mouse.get_pos())
        
        if hovered_element and hasattr(hovered_element, 'tooltip') and hovered_element.tooltip:
            if self.tooltip_owner != hovered_element:
                self.set_tooltip(hovered_element.tooltip, hovered_element, pygame.mouse.get_pos())
        elif self.tooltip_owner:
            self.clear_tooltip()
        
        if self.tooltip_owner: # Update position if tooltip is active
            self.tooltip_pos = pygame.mouse.get_pos()

        self.update_active_tool_buttons()
        self.update_delete_button_text()
        
        if self.idle_unit_button:
            idle_units = self.game_app.get_idle_units()
            num_idle = len(idle_units)
            if num_idle > 0:
                self.idle_unit_button.visible = True
                self.idle_unit_button.text = f"{num_idle} Idle Unit{'s' if num_idle > 1 else ''} (Tab)"
            else:
                self.idle_unit_button.visible = False
        
        hovered_nation_id = None
        if self.leaderboard_panel and self.leaderboard_panel.visible:
            mouse_pos = pygame.mouse.get_pos()
            if self.leaderboard_panel.is_mouse_over(mouse_pos):
                for child in self.leaderboard_panel.children:
                    if isinstance(child, LeaderboardRow) and child.is_mouse_over(mouse_pos):
                        hovered_nation_id = child.nation_id
                        break
        self.game_app.hovered_leaderboard_nation_id = hovered_nation_id

        if self.active_popup and not self.active_popup.is_mouse_over(pygame.mouse.get_pos()):
            pass

        for name, panel in self.sub_panels.items():
            is_active = (self.game_app.current_tool == name)
            
            if is_active:
                panel.target_alpha = 255
                panel.visible = True
                panel.target_pos = (10, c.SCREEN_HEIGHT - 80 - panel.rect.height - 10) # Pop up from bottom-left
            else:
                panel.target_alpha = 0

            if panel.alpha < 1: panel.visible = False

        # --- Nation Panel Positioning ---
        nations_panel = self.sub_panels.get('manage_nations')
        if nations_panel:
            is_nations_open = self.game_app.nations_panel_open
            nations_panel.target_alpha = 255 if is_nations_open else 0
            nations_panel.visible = is_nations_open or nations_panel.alpha > 1
            nations_panel.target_pos = (c.SCREEN_WIDTH - nations_panel.rect.width - 10, 60) if is_nations_open else (c.SCREEN_WIDTH + 20, 60)

        # --- Selection Panel Positioning ---
        if self.selection_info_panel:
            self.selection_info_panel.visible = bool(self.game_app.multi_selected_entities)
            self.selection_info_panel.target_alpha = 255 if self.selection_info_panel.visible else 0
            if self.selection_info_panel.alpha < 1: self.selection_info_panel.visible = False
            panel_width = self.selection_info_panel.rect.width
            self.selection_info_panel.target_pos = (c.SCREEN_WIDTH - panel_width - 10, c.SCREEN_HEIGHT - 80 - self.selection_info_panel.rect.height - 10) if self.selection_info_panel.visible else (c.SCREEN_WIDTH - panel_width - 10, c.SCREEN_HEIGHT + 20)

        if hasattr(self, 'delete_selected_button') and self.delete_selected_button:
            if not self.delete_selected_button.text:
                 self.delete_selected_button.target_pos = (c.SCREEN_WIDTH / 2 - 120, -50)
                 self.delete_selected_button.target_alpha = 0
            else:
                 self.delete_selected_button.target_pos = (c.SCREEN_WIDTH/2-120, 10)
                 self.delete_selected_button.target_alpha = 255
        
        if hasattr(self, 'admin_panel'):
            self.admin_panel.target_alpha = 255 if self.admin_panel_visible else 0
            target_y = c.SCREEN_HEIGHT - self.admin_panel.rect.height - 10 if self.admin_panel_visible else c.SCREEN_HEIGHT + 10
            self.admin_panel.target_pos = (c.SCREEN_WIDTH / 2 - 250, target_y)

        if hasattr(self, 'search_panel'):
            self.search_panel.target_alpha = 255 if self.search_panel_visible else 0
            target_y = 10 if self.search_panel_visible else -self.search_panel.rect.height - 10
            self.search_panel.target_pos = (c.SCREEN_WIDTH / 2 - 200, target_y)

        if hasattr(self, 'leaderboard_panel') and self.leaderboard_panel:
            bottom_y = c.SCREEN_HEIGHT - 80 - 10
            self.leaderboard_panel.target_pos = (10, bottom_y - self.leaderboard_panel.rect.height)
            self.leaderboard_panel.visible = True
            
        self.root.update()
        
    def _find_hovered_element(self, element, pos):
        if not element.visible or not element.get_absolute_rect().collidepoint(pos):
            return None
        
        # Check children in reverse draw order
        for child in reversed(element.children):
            hovered = self._find_hovered_element(child, pos)
            if hovered:
                return hovered
        
        # If no child is hovered, this element is the topmost one
        # We only care about elements that can have tooltips (like Buttons)
        if hasattr(element, 'tooltip'):
            return element
        return None

    def update_active_tool_buttons(self):
        for name, btn in self.tool_buttons.items():
            btn.is_active = (name == self.game_app.current_tool) or (name == 'manage_nations' and self.game_app.nations_panel_open)
        if hasattr(self, 'text_display_button'):
            self.text_display_button.is_active = self.game_app.show_territory_names
        if hasattr(self, 'manpower_overlay_button'):
            self.manpower_overlay_button.is_active = self.game_app.show_manpower_overlay
        if hasattr(self, 'alliance_mode_button'):
            self.alliance_mode_button.is_active = self.game_app.alliance_map_mode

    def set_active_input(self, input_field):
        if self.active_input and self.active_input != input_field: self.active_input.is_active = False
        self.active_input = input_field

    def handle_event(self, event):
        if self.active_popup:
            if self.active_popup.handle_event(event, self):
                return True
            if event.type == pygame.MOUSEBUTTONDOWN and not self.active_popup.is_mouse_over(event.pos):
                self.root.children.remove(self.active_popup)
                self.active_popup = None
                return True
        
        if event.type == pygame.MOUSEWHEEL:
            if self.selection_info_panel and self.selection_info_panel.is_mouse_over(pygame.mouse.get_pos()):
                return self.selection_info_panel.handle_event(event, self, force_scroll=True)

        if self.active_input and event.type == pygame.KEYDOWN:
            if self.active_input.handle_event(event, self):
                return True
        return self.root.handle_event(event, self)

    def is_mouse_over_ui(self, pos):
        if self.active_popup and self.active_popup.is_mouse_over(pos):
            return True
        for child in self.root.children:
            if child is not self.active_popup and child.visible and child.is_mouse_over(pos):
                return True
        return False

    def set_tooltip(self, text, owner, pos):
        if text:
            if self.tooltip_text != text: self.tooltip_surf = self.tooltip_font.render(text, True, c.UI_FONT_COLOR)
            self.tooltip_text, self.tooltip_timer, self.tooltip_owner, self.tooltip_pos = text, pygame.time.get_ticks(), owner, pos

    def clear_tooltip(self, owner=None):
        if owner is None or self.tooltip_owner == owner: self.tooltip_text, self.tooltip_surf, self.tooltip_owner = "", None, None

    def draw(self, screen):
        self.root.draw(screen)
        if self.game_app.battle_prediction and self.game_app.battle_prediction.get('suppressed'):
            font = c.get_font(c.FONT_PATH, 18)
            text_surf = c.create_text_with_border("SUPPRESSED!", font, c.COLOR_ORANGE, c.COLOR_BLACK)
            pos = self.game_app.battle_prediction['pos']
            bg_rect = pygame.Rect(pos[0] + 15, pos[1] + 15, 100, 60)
            text_rect = text_surf.get_rect(midbottom=(bg_rect.centerx, bg_rect.top - 5))
            screen.blit(text_surf, text_rect)
        self.draw_research_warning(screen)
        if self.game_app.is_tutorial:
            self.draw_tutorial_overlay(screen)
            
        self.draw_tooltip(screen)
        
    def draw_research_warning(self, screen):
        # Only for players with a valid nation
        if self.game_app.main_app.user_mode != 'player' or not self.game_app.main_app.player_nation_id:
            return
        
        nation = self.game_app.nations.get(self.game_app.main_app.player_nation_id)
        if not nation: return
        
        used_slots = len(nation.get('currently_researching', {}))
        total_slots = nation.get('research_slots', 1)
        
        if used_slots < total_slots and self.tech_tree_button:
            # Flashing effect
            alpha = int(abs(math.sin(pygame.time.get_ticks() * 0.005)) * 255)
            
            btn_rect = self.tech_tree_button.get_absolute_rect()
            
            # Draw Red '!' Circle
            circle_pos = btn_rect.topright
            pygame.draw.circle(screen, c.COLOR_RED, circle_pos, 10)
            pygame.draw.circle(screen, c.COLOR_WHITE, circle_pos, 10, 2)
            
            font = c.get_font(None, 18)
            text = font.render("!", True, c.COLOR_WHITE)
            text_rect = text.get_rect(center=circle_pos)
            screen.blit(text, text_rect)
            
            # Optional: Glow on button border
            glow_surf = pygame.Surface((btn_rect.width, btn_rect.height), pygame.SRCALPHA)
            pygame.draw.rect(glow_surf, (255, 0, 0, alpha // 2), glow_surf.get_rect(), 3, border_radius=5)
            screen.blit(glow_surf, btn_rect.topleft)

    def draw_tutorial_overlay(self, screen):
        steps = [
            {
                'text': "Welcome to DiploStrat! This is your main view.\nYou can see your units, territory, and map features here.\n\nUse WASD or MMB to Pan, Scroll to Zoom.",
                'target': None
            },
            {
                'text': "This is the Nation Panel.\nManage your nation's name, color, and alliances here.",
                'target': self.nation_button
            },
            {
                'text': "The Tech Tree.\nResearch new technologies to upgrade your units\nand unlock bonuses. Watch out for the flashing '!'\nindicating a free research slot!",
                'target': self.tech_tree_button
            },
            {
                'text': "Your Toolbar.\nSelect tools to move units (Arrows),\nadd notes, or manage your orders.",
                'target': self.toolbar_panel
            },
            {
                'text': "That's the basics!\nExplore the Encyclopedia for unit stats,\nand have fun conquering!",
                'target': None
            }
        ]
        
        if self.game_app.tutorial_step >= len(steps):
            self.game_app.is_tutorial = False
            return

        step_data = steps[self.game_app.tutorial_step]
        
        # Darken background
        overlay = pygame.Surface((c.SCREEN_WIDTH, c.SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        screen.blit(overlay, (0, 0))
        
        # Exit Button
        exit_btn_rect = pygame.Rect(c.SCREEN_WIDTH - 160, 20, 140, 40)
        pygame.draw.rect(screen, c.COLOR_RED, exit_btn_rect, border_radius=5)
        pygame.draw.rect(screen, c.UI_BORDER_COLOR, exit_btn_rect, 2, border_radius=5)
        exit_font = c.get_font(c.FONT_PATH, 18)
        exit_text = exit_font.render("Exit Tutorial", True, c.COLOR_WHITE)
        screen.blit(exit_text, exit_text.get_rect(center=exit_btn_rect.center))

        # Text Box
        font = c.get_font(c.FONT_PATH, 20)
        lines = step_data['text'].split('\n')
        
        box_width = 400
        box_height = len(lines) * 25 + 60
        box_rect = pygame.Rect(c.SCREEN_WIDTH/2 - box_width/2, c.SCREEN_HEIGHT/2 - box_height/2, box_width, box_height)
        
        pygame.draw.rect(screen, c.UI_PANEL_COLOR, box_rect, border_radius=10)
        pygame.draw.rect(screen, c.UI_BORDER_COLOR, box_rect, 2, border_radius=10)
        
        for i, line in enumerate(lines):
            text_surf = font.render(line, True, c.UI_FONT_COLOR)
            screen.blit(text_surf, (box_rect.x + 20, box_rect.y + 20 + i * 25))
            
        btn_font = c.get_font(c.FONT_PATH, 18)
        next_text = btn_font.render("Click anywhere to continue...", True, c.COLOR_YELLOW)
        screen.blit(next_text, (box_rect.centerx - next_text.get_width()/2, box_rect.bottom - 30))

        # Arrow logic
        if step_data['target']:
            target_rect = step_data['target'].get_absolute_rect()
            start_pos = box_rect.center
            end_pos = target_rect.center
            pygame.draw.line(screen, c.COLOR_YELLOW, start_pos, end_pos, 4)
            pygame.draw.circle(screen, c.COLOR_YELLOW, end_pos, 8)
            pygame.draw.rect(screen, c.COLOR_YELLOW, target_rect, 3, border_radius=5)

        # Input Handling
        if pygame.mouse.get_pressed()[0]:
            if not hasattr(self, 'tutorial_click_cooldown') or pygame.time.get_ticks() > self.tutorial_click_cooldown:
                mouse_pos = pygame.mouse.get_pos()
                
                # Check exit button
                if exit_btn_rect.collidepoint(mouse_pos):
                    self.game_app.is_tutorial = False
                    self.game_app.main_app.change_state('TITLE')
                else:
                    self.game_app.tutorial_step += 1
                
                self.tutorial_click_cooldown = pygame.time.get_ticks() + 300
        
        
    def draw_tooltip(self, screen):
        if self.game_app.main_app.active_screen is not self.game_app: self.clear_tooltip(); return
        if self.tooltip_text and self.tooltip_surf and pygame.time.get_ticks()-self.tooltip_timer > 500:
            mouse_pos = self.tooltip_pos
            rect = self.tooltip_surf.get_rect(topleft=(mouse_pos[0]+15, mouse_pos[1]+15))
            if rect.right > c.SCREEN_WIDTH: rect.right = c.SCREEN_WIDTH-5
            if rect.bottom > c.SCREEN_HEIGHT: rect.bottom = c.SCREEN_HEIGHT-5
            bg_rect = rect.inflate(10,6)
            pygame.draw.rect(screen, c.UI_PANEL_COLOR, bg_rect, border_radius=3)
            pygame.draw.rect(screen, c.UI_BORDER_COLOR, bg_rect, 1, border_radius=3)
            screen.blit(self.tooltip_surf, rect)