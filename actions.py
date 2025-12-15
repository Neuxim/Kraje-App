import config as c

class Action:
    """Base class for an action that can be undone."""
    def execute(self, app):
        raise NotImplementedError
    
    def undo(self, app):
        raise NotImplementedError

class CompositeAction(Action):
    """An action that groups multiple other actions together."""
    def __init__(self, actions):
        self.actions = actions
        
    def execute(self, app):
        for action in self.actions:
            action.execute(app)
            
    def undo(self, app):
        for action in reversed(self.actions):
            action.undo(app)

class PaintAction(Action):
    """Action for painting terrain, nation ownership, or fog on one or more tiles."""
    def __init__(self, tiles_data, paint_type):
        self.tiles_data = tiles_data
        self.paint_type = paint_type

    def execute(self, app):
        for tile, _, new_value in self.tiles_data:
            setattr(tile, self.paint_type, new_value)
        
        if self.paint_type == 'land_type' or self.paint_type == 'nation_owner_id':
            app.map.set_dirty()

        if self.paint_type == 'nation_owner_id':
            app.territory_data_dirty = True
        elif self.paint_type == 'visibility_state':
            app.fow_dirty = True
            
    def undo(self, app):
        for tile, old_value, _ in self.tiles_data:
            setattr(tile, self.paint_type, old_value)

        if self.paint_type == 'land_type' or self.paint_type == 'nation_owner_id':
            app.map.set_dirty()

        if self.paint_type == 'nation_owner_id':
            app.territory_data_dirty = True
        elif self.paint_type == 'visibility_state':
            app.fow_dirty = True

class EntityAction(Action):
    """Action for creating or deleting entities (Units, Features, Arrows, Straits, MapText)."""
    def __init__(self, entity, is_creation):
        self.entity = entity
        self.is_creation = is_creation
        self.list_map = {
            'Unit': 'units',
            'MapFeature': 'features',
            'Arrow': 'arrows',
            'Strait': 'straits',
            'Blockade': 'blockades',
            'MapText': 'map_texts'
        }
        self.entity_type_name = type(entity).__name__
        self.list_name = self.list_map.get(self.entity_type_name)

    def get_list(self, app):
        return getattr(app, self.list_name, None)

    def execute(self, app):
        entity_list = self.get_list(app)
        if self.is_creation:
            if self.entity not in entity_list: entity_list.append(self.entity)
        else:
            if self.entity in entity_list: entity_list.remove(self.entity)
            # Special case for units being carried
            if self.entity_type_name == 'Unit':
                for u in app.units:
                    if hasattr(u, 'carried_units') and self.entity in u.carried_units:
                        u.carried_units.remove(self.entity)

    def undo(self, app):
        entity_list = self.get_list(app)
        if self.is_creation:
            if self.entity in entity_list: entity_list.remove(self.entity)
        else:
            if self.entity not in entity_list: entity_list.append(self.entity)

class MoveOrCarryAction(Action):
    """Action for moving an entity, or loading/unloading a unit."""
    def __init__(self, entity, old_pos, new_pos, old_container, new_container):
        self.entity = entity
        self.old_gx, self.old_gy = old_pos
        self.new_gx, self.new_gy = new_pos
        self.old_container = old_container
        self.new_container = new_container

    def _move(self, app, gx, gy, from_container, to_container):
        self.entity.grid_x, self.entity.grid_y = gx, gy
        
        # Only handle container logic for units
        if type(self.entity).__name__ != 'Unit':
            return

        if from_container:
            if self.entity in from_container.carried_units: from_container.carried_units.remove(self.entity)
        else:
            if self.entity in app.units: app.units.remove(self.entity)

        if to_container:
            if self.entity not in to_container.carried_units: to_container.carried_units.append(self.entity)
        else:
            if self.entity not in app.units: app.units.append(self.entity)
        
    def execute(self, app):
        self._move(app, self.new_gx, self.new_gy, self.old_container, self.new_container)

    def undo(self, app):
        self._move(app, self.old_gx, self.old_gy, self.new_container, self.old_container)

class RotateUnitAction(Action):
    """Action for rotating a unit by a specified step."""
    def __init__(self, unit, rotation_step=90):
        self.unit = unit
        self.rotation_step = rotation_step

    def execute(self, app):
        self.unit.rotation = (self.unit.rotation + self.rotation_step) % 360

    def undo(self, app):
        self.unit.rotation = (self.unit.rotation - self.rotation_step) % 360

class ShiftMapAction(Action):
    """Action for shifting the entire map's contents."""
    def __init__(self, dx, dy, layer_key):
        self.dx = dx
        self.dy = dy
        self.layer_key = layer_key
    
    def execute(self, app):
        app.shift_map_contents(self.dx, self.dy, self.layer_key)

    def undo(self, app):
        app.shift_map_contents(-self.dx, -self.dy, self.layer_key)

class PropertyChangeAction(Action):
    """Action for changing a single property on any object."""
    def __init__(self, obj, prop_name, old_value, new_value):
        self.obj = obj
        self.prop_name = prop_name
        self.old_value = old_value
        self.new_value = new_value

    def execute(self, app):
        setattr(self.obj, self.prop_name, self.new_value)
        # A bit of a catch-all, but ensures UI updates for any property change
        if hasattr(app, 'ui_manager'):
            app.ui_manager.rebuild_selection_info_panel()

    def undo(self, app):
        setattr(self.obj, self.prop_name, self.old_value)
        if hasattr(app, 'ui_manager'):
            app.ui_manager.rebuild_selection_info_panel()
            
class RotateMapAction(Action):
    def __init__(self, degrees, layer_key):
        self.degrees = degrees
        self.layer_key = layer_key

    def execute(self, app):
        app.rotate_map_contents(self.degrees, self.layer_key)

    def undo(self, app):
        app.rotate_map_contents(-self.degrees, self.layer_key)
        
        
class ChangeFeatureTypeAction(Action):
    """Action for changing the type of a MapFeature."""
    def __init__(self, feature, new_type):
        self.feature = feature
        self.old_type = feature.feature_type
        self.new_type = new_type

    def _set_type(self, feature_type):
        self.feature.feature_type = feature_type
        self.feature.properties = None
        for category in c.FEATURE_TYPES.values():
            if feature_type in category:
                self.feature.properties = category[feature_type]
                break

        if self.feature.properties:
            self.feature.asset_path = self.feature.properties['asset']
            self.feature.is_naval = self.feature.properties.get('is_naval', False)
        else:
            print(f"ERROR: Could not find properties for feature type '{feature_type}' during action")

    def execute(self, app):
        self._set_type(self.new_type)
        if hasattr(app, 'ui_manager'):
            app.ui_manager.rebuild_selection_info_panel()
        app.map.set_dirty()


    def undo(self, app):
        self._set_type(self.old_type)
        if hasattr(app, 'ui_manager'):
            app.ui_manager.rebuild_selection_info_panel()
        app.map.set_dirty()