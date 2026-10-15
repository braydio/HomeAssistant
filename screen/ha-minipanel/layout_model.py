"""Panel-only room layout: an ordered list of rooms, each an ordered list of individual light entity IDs.

This never touches Home Assistant areas, groups, scenes or registries. Persisted to a small
0600 JSON file on the panel; edits are staged in memory until commit_atomic().
"""
import copy
import json
import os
import re
import tempfile
from pathlib import Path

VERSION = 1
_LIGHT = re.compile(r'^light\.[a-z0-9_]+$')
_ROOM_ID = re.compile(r'^[a-z0-9_]{1,40}$')


class LayoutError(ValueError):
    pass


def validate_data(data, allowed_ids=None):
    """Raise LayoutError if `data` is not a well-formed v1 layout. Returns data."""
    if not isinstance(data, dict) or data.get('version') != VERSION:
        raise LayoutError('unsupported layout version')
    rooms = data.get('rooms')
    if not isinstance(rooms, list) or not rooms:
        raise LayoutError('rooms must be a non-empty list')
    seen_rooms, seen_lights = set(), set()
    for i, room in enumerate(rooms):
        if not isinstance(room, dict):
            raise LayoutError('room must be an object')
        rid, label, lights = room.get('id'), room.get('label'), room.get('lights')
        if not isinstance(rid, str) or not _ROOM_ID.match(rid):
            raise LayoutError('bad room id')
        if rid in seen_rooms:
            raise LayoutError('duplicate room id')
        seen_rooms.add(rid)
        if not isinstance(label, str) or not label.strip() or len(label) > 40:
            raise LayoutError('bad room label')
        if not isinstance(lights, list):
            raise LayoutError('lights must be a list')
        for eid in lights:
            if not isinstance(eid, str) or not _LIGHT.match(eid):
                raise LayoutError('bad light id')
            if eid in seen_lights:
                raise LayoutError('light in more than one room')
            if allowed_ids is not None and eid not in allowed_ids:
                raise LayoutError('light not allowlisted')
            seen_lights.add(eid)
    return data


def _normalise(data):
    out = {'version': VERSION, 'rooms': []}
    for i, room in enumerate(data['rooms']):
        out['rooms'].append({'id': room['id'], 'label': room['label'], 'order': i, 'lights': list(room['lights'])})
    return out


def _write_atomic(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix='.layout-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=1)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o600)
        if path.exists():
            bak = path.with_name(path.name + '.bak')
            try:
                bak.write_bytes(path.read_bytes())
                os.chmod(bak, 0o600)
            except OSError:
                pass
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class PanelLayout:
    def __init__(self, path, defaults, allowed_ids=None):
        self.path = Path(path)
        self.allowed = set(allowed_ids) if allowed_ids is not None else None
        self.defaults = _normalise(validate_data(copy.deepcopy(defaults)))
        self.data = copy.deepcopy(self.defaults)
        self.saved = copy.deepcopy(self.defaults)
        self.loaded_from_file = False

    @classmethod
    def load(cls, path, defaults, allowed_ids=None):
        lay = cls(path, defaults, allowed_ids)
        for candidate in (lay.path, lay.path.with_name(lay.path.name + '.bak')):
            try:
                data = json.loads(candidate.read_text(encoding='utf-8'))
                validate_data(data)
            except (OSError, ValueError, LayoutError):
                continue
            lay.data = _normalise(data)
            lay.prune()
            lay.saved = copy.deepcopy(lay.data)
            lay.loaded_from_file = True
            break
        return lay

    # --- queries ---------------------------------------------------------
    def rooms(self):
        return self.data['rooms']

    def room(self, room_id):
        for r in self.data['rooms']:
            if r['id'] == room_id:
                return r
        raise LayoutError('unknown room')

    def room_of(self, entity_id):
        for r in self.data['rooms']:
            if entity_id in r['lights']:
                return r['id']
        return None

    def all_lights(self):
        seen, out = set(), []
        for r in self.data['rooms']:
            for e in r['lights']:
                if e not in seen:
                    seen.add(e); out.append(e)
        return out

    @property
    def dirty(self):
        return self.data != self.saved

    # --- staged edits ----------------------------------------------------
    def move_light(self, entity_id, target_room_id, before_id=None):
        src = self.room_of(entity_id)
        if src is None:
            raise LayoutError('light is not in the layout')
        target = self.room(target_room_id)
        self.room(src)['lights'].remove(entity_id)
        if before_id and before_id in target['lights']:
            target['lights'].insert(target['lights'].index(before_id), entity_id)
        else:
            target['lights'].append(entity_id)

    def reorder_light(self, room_id, entity_id, new_index):
        lights = self.room(room_id)['lights']
        if entity_id not in lights:
            raise LayoutError('light is not in that room')
        lights.remove(entity_id)
        lights.insert(max(0, min(new_index, len(lights))), entity_id)

    def reorder_room(self, room_id, new_index):
        rooms = self.data['rooms']
        room = self.room(room_id)
        rooms.remove(room)
        rooms.insert(max(0, min(new_index, len(rooms))), room)
        for i, r in enumerate(rooms):
            r['order'] = i

    def validate(self):
        validate_data(self.data, self.allowed)

    def commit_atomic(self):
        self.validate()
        self.data = _normalise(self.data)
        _write_atomic(self.path, self.data)
        self.saved = copy.deepcopy(self.data)
        self.loaded_from_file = True

    def cancel(self):
        self.data = copy.deepcopy(self.saved)

    def reset_to_defaults(self):
        self.data = copy.deepcopy(self.defaults)

    def prune(self):
        """Drop IDs HA no longer knows about. Unavailable lights are still known, so they stay."""
        if self.allowed is None:
            return
        for r in self.data['rooms']:
            r['lights'] = [e for e in r['lights'] if e in self.allowed]
