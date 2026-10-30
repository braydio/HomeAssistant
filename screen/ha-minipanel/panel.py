#!/usr/bin/env python3
"""7-inch Home Assistant touchscreen panel using native Qt Widgets, not Chromium.

Run: python3 panel.py --demo --windowed
For actual devices: configure config.json and use python3 panel.py --fullscreen

Touch model: some digitizers (QDtech MPI7002 here) only report touches in a middle band. With `touch_band`
set, the top and bottom strips are display-only and EVERY control (including nav, Back, Done, Move to...) lives
inside the band. With touch_band=null the same layout simply uses a natural header/footer.
"""
import argparse
import json
import os
import random
import sys
import time
from datetime import datetime
from pathlib import Path

from PyQt5.QtCore import Qt, QTimer, QObject, QRunnable, QThreadPool, pyqtSignal
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (QScroller, QApplication, QFrame, QWidget, QMainWindow, QVBoxLayout, QHBoxLayout,
                             QStackedWidget, QScrollArea, QSizePolicy, QGridLayout)

import camera
import colors as C
import health
import settings
import telemetry
from ha_client import HAClient, HomeAssistantError
from layout_model import PanelLayout, LayoutError
from state_store import StateStore, age_text
from views import (LightRow, RoomRow, RoomTile, ColorEditor, ColorsView, label, card, layout_v, button,
                   friendly, available, set_kind, repolish, HIT)

VERSION = '2.1.0'
ROOT = Path(__file__).resolve().parent
CONF_DIR = Path.home() / '.config' / 'ha-minipanel'
WEATHER = {  # HA weather condition -> (glyph, label)
    'clear-night': ('☾', 'Clear night'), 'sunny': ('☀', 'Sunny'), 'cloudy': ('☁', 'Cloudy'),
    'partlycloudy': ('⛅', 'Partly cloudy'), 'rainy': ('☂', 'Rain'), 'pouring': ('☂', 'Heavy rain'),
    'lightning': ('⚡', 'Thunderstorm'), 'lightning-rainy': ('⚡', 'Thunderstorms'), 'snowy': ('❄', 'Snow'),
    'snowy-rainy': ('❄', 'Sleet'), 'hail': ('❄', 'Hail'), 'fog': ('≋', 'Fog'), 'windy': ('≈', 'Windy'),
    'windy-variant': ('≈', 'Windy'), 'exceptional': ('!', 'Alert'),
}
SAFE = 8  # every control stays at least this far inside the touch band
PALETTES = {
    'dark': {'bg': '#0A1720', 'card': '#152733', 'card2': '#213844', 'text': '#F0F7F4', 'muted': '#9EB8BB', 'accent': '#85DCC2', 'border': '#304852', 'danger': '#C8676B'},
    'light': {'bg': '#EFF3EF', 'card': '#FFFFFF', 'card2': '#E1ECE8', 'text': '#19342F', 'muted': '#5D7774', 'accent': '#2B9179', 'border': '#CCDBD5', 'danger': '#BD4F5C'},
}
# Lights page sub-views (QStackedWidget indexes)
V_ROOMS, V_ROOM, V_COLOR, V_COLORS, V_EDIT, V_EDITROOM, V_MOVE = range(7)
PAGE_HOME, PAGE_LIGHTS, PAGE_CAMERAS, PAGE_SETTINGS = range(4)


def geometry(height, band):
    """(top, bottom) of the interactive band. A configured band is clamped to the screen; otherwise a natural
    header/footer is used so the layout still works on a fully touch-capable panel."""
    if band and 0 <= band[0] < band[1] <= height:
        return int(band[0]), int(band[1])
    return 84, max(200, height - 70)


class JobSignals(QObject):
    done = pyqtSignal(object)
    error = pyqtSignal(str)


class Job(QRunnable):
    def __init__(self, fn):
        super().__init__(); self.fn = fn; self.signals = JobSignals()

    def run(self):
        try: self.signals.done.emit(self.fn())
        except Exception as e: self.signals.error.emit(str(e))


class Panel(QMainWindow):
    def __init__(self, config, demo=False, fullscreen=True, size=(1024, 600)):
        super().__init__()
        self.config = settings.normalize(config)
        self.client = HAClient(self.config, demo)
        self.demo = demo
        self.store = StateStore()
        self.inflight = set(); self.pending = 0; self.last_action = {}
        self.pool = QThreadPool.globalInstance(); self.pool.setMaxThreadCount(2)
        self.prefs_path = Path(os.path.expanduser(self.config.get('prefs_file', str(CONF_DIR / 'preferences.json'))))
        self.layout_path = Path(os.path.expanduser(self.config.get('layout_file', str(CONF_DIR / 'layout.json'))))
        self.prefs = self.load_preferences()
        self.override = self.prefs.get('theme', 'auto')
        self.camera_auto = bool(self.prefs.get('camera_auto', self.config['camera_auto_refresh']))
        self.current_theme = 'dark'; self.page_index = PAGE_HOME
        self.layout = None; self.room_meta = {}; self.editing = False
        self.current_room = None; self.edit_room_id = None; self.move_eid = None; self.color_return = V_ROOMS
        self.reset_pending = False; self.fail_count = 0; self.notice_token = 0
        self.active_camera = None; self.cam_gen = 0; self.cam_paused = False
        self.preview_image = None; self.camera_source = None; self.camera_controls_expanded = False
        self.forecast_next = None; self.forecast_at = -1e9; self.last_weather = ''
        self.setWindowTitle('Home Panel | Native Qt')
        self.W, self.H = size
        self.top, self.bot = geometry(self.H, self.config.get('touch_band'))
        self.resize(self.W, self.H)
        self.build_ui()
        self.set_theme('dark')
        self.clock_update()
        self.poll()
        self.poll_timer = QTimer(self); self.poll_timer.timeout.connect(self.poll)
        self.poll_timer.start(self.config['poll_seconds'] * 1000)
        self.camera_timer = QTimer(self); self.camera_timer.timeout.connect(self.poll_camera)
        self.diag_timer = QTimer(self); self.diag_timer.timeout.connect(self.update_diagnostics)
        self.clock_timer = QTimer(self); self.clock_timer.timeout.connect(self.clock_update)
        self.clock_timer.start(20000)
        if fullscreen: self.showFullScreen()
        else: self.show()

    # --- state access ------------------------------------------------------------------------------
    @property
    def states(self):
        return self.store.states

    @property
    def online(self):
        return self.store.online is True

    # --- preferences ---------------------------------------------------------------------------------
    def load_preferences(self):
        try:
            d = json.loads(self.prefs_path.read_text())
            return d if isinstance(d, dict) else {}
        except (FileNotFoundError, ValueError, OSError):
            return {}

    def save_preferences(self):
        self.prefs.update({'theme': self.override, 'camera_auto': self.camera_auto})
        self.prefs_path.parent.mkdir(parents=True, exist_ok=True)
        self.prefs_path.write_text(json.dumps(self.prefs))
        self.prefs_path.chmod(0o600)

    # --- UI construction -----------------------------------------------------------------------------
    def build_ui(self):
        root = QWidget(); root.setObjectName('Root'); self.setCentralWidget(root)
        # A full-screen, display-only image behind the three layout bands. Only
        # the middle band's controls receive touch events.
        self.camera_view = label('No camera available', 'cameraPlaceholder', wrap=True)
        self.camera_view.setParent(root); self.camera_view.setObjectName('CameraCanvas')
        self.camera_view.setAlignment(Qt.AlignCenter)
        self.camera_view.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.camera_view.setGeometry(6, 6, max(1, self.W - 12), max(1, self.H - 12))
        self.camera_view.hide()
        top, bot = self.top, self.bot
        page = layout_v(root, (0, 0, 0, 0), 0)
        # display-only header
        topw = QWidget(); topw.setFixedHeight(top); tl = QHBoxLayout(topw); tl.setContentsMargins(24, 6, 24, 6)
        left = QVBoxLayout(); left.setSpacing(0)
        self.clock = label('0:00 AM', 'infoClock'); self.date_label = label('', 'small')
        left.addStretch(1); left.addWidget(self.clock); left.addWidget(self.date_label); left.addStretch(1)
        centre = QVBoxLayout(); centre.setSpacing(2)
        self.top_greeting = label('', 'heading'); self.top_summary = label('Checking lights…', 'rowTitle')
        centre.addStretch(1); centre.addWidget(self.top_greeting); centre.addWidget(self.top_summary); centre.addStretch(1)
        right = QVBoxLayout(); right.setSpacing(2)
        self.theme_status = label('AUTO', 'small'); self.health_status = label('', 'small')
        self.brand_label = label('HOME PANEL', 'overline')
        right.addStretch(1); right.addWidget(self.brand_label); right.addWidget(self.theme_status)
        right.addWidget(self.health_status); right.addStretch(1)
        self.header_labels = (self.clock, self.date_label, self.top_greeting, self.top_summary,
                              self.brand_label, self.theme_status, self.health_status)
        tl.addLayout(left, 2); tl.addLayout(centre, 3); tl.addLayout(right, 1)
        # interactive band
        mid = QWidget(); mid.setFixedHeight(bot - top)
        outer = layout_v(mid, (16, SAFE, 16, SAFE), 6)
        # display-only footer
        botw = QWidget(); botw.setFixedHeight(self.H - bot); bl = QVBoxLayout(botw); bl.setContentsMargins(24, 8, 24, 8); bl.setSpacing(3)
        self.bottom_status = label('Loading weather…', 'heading'); self.bottom_detail = label('', 'small')
        self.camera_stamp = label('Snapshot · not live video', 'cameraCaption', wrap=True)
        self.camera_stamp.setAlignment(Qt.AlignCenter); self.camera_stamp.hide()
        bl.addStretch(1); bl.addWidget(self.bottom_status); bl.addWidget(self.bottom_detail)
        bl.addWidget(self.camera_stamp); bl.addStretch(1)
        page.addWidget(topw); page.addWidget(mid); page.addWidget(botw)
        self.stack = QStackedWidget(); outer.addWidget(self.stack, 1)
        self.make_home(); self.make_lights(); self.make_cameras(); self.make_settings()
        self.navbar = QFrame(); self.navbar.setObjectName('Nav'); nav = QHBoxLayout(self.navbar)
        nav.setContentsMargins(5, 3, 5, 3); nav.setSpacing(6)
        self.nav_buttons = []
        for idx, name in enumerate(('Home', 'Lights', 'Cameras')):
            b = button(name, lambda checked=False, n=idx: self.switch_page(n), 'nav')
            nav.addWidget(b, 1); self.nav_buttons.append(b)
        navdock = QHBoxLayout(); navdock.setContentsMargins(0, 0, 0, 0)
        navdock.addStretch(0); navdock.addWidget(self.navbar, 100); navdock.addStretch(0)
        outer.addLayout(navdock)
        self.update_nav()

    def make_scroll(self):
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame); scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        QScroller.grabGesture(scroll.viewport(), QScroller.LeftMouseButtonGesture)  # drag-to-scroll with a finger
        holder = QWidget(); holder.setObjectName('holder'); holder.setStyleSheet('#holder { background: transparent; }')
        scroll.viewport().setObjectName('vp'); scroll.viewport().setStyleSheet('#vp { background: transparent; }')
        lay = layout_v(holder, (0, 0, 0, 0), 6); lay.addStretch(1); scroll.setWidget(holder)
        return scroll, lay

    # Home ----------------------------------------------------------------------------------------------
    def make_home(self):
        page = QWidget(); body = QHBoxLayout(page); body.setContentsMargins(0, 0, 0, 0); body.setSpacing(12)
        self.tile_grid = QGridLayout(); self.tile_grid.setSpacing(10)
        gw = QWidget(); gw.setLayout(self.tile_grid)
        body.addWidget(gw, 3)
        self.tiles = {}
        self.home_empty = label('Loading rooms…', 'small')
        self.tile_grid.addWidget(self.home_empty, 0, 0)
        side = QVBoxLayout(); side.setSpacing(6)
        self.scene_holder = QVBoxLayout(); self.scene_holder.setSpacing(6)
        side.addLayout(self.scene_holder)
        side.addStretch(1)
        row = QHBoxLayout(); row.setSpacing(6)
        row.addWidget(button('All Off', self.all_lights_off, 'danger'), 1)
        row.addWidget(button('Settings', lambda: self.switch_page(PAGE_SETTINGS), 'secondary'), 1)
        side.addLayout(row)
        sw = QWidget(); sw.setLayout(side); body.addWidget(sw, 2)
        self.stack.addWidget(page)

    def populate_home(self):
        if not self.layout:
            return
        fav = [r['id'] for r in self.layout.rooms() if self.room_meta.get(r['id'], {}).get('favorite', True)][:4]
        if tuple(fav) != tuple(self.tiles):
            while self.tile_grid.count():
                it = self.tile_grid.takeAt(0)
                if it.widget(): it.widget().deleteLater()
            self.tiles = {}
            for i, rid in enumerate(fav):
                t = RoomTile(self, rid); self.tiles[rid] = t; self.tile_grid.addWidget(t, i // 2, i % 2)
            if not fav:
                self.tile_grid.addWidget(label('No favourite rooms. Add rooms in config.json.', 'small'), 0, 0)
            for r in range(2): self.tile_grid.setRowStretch(r, 1)
            for c in range(2): self.tile_grid.setColumnStretch(c, 1)
        for t in self.tiles.values():
            t.refresh()

    def populate_scenes(self):
        sigs = tuple(s['entity_id'] for s in self.config['scenes'] if s['entity_id'] in self.states)[:3]
        if getattr(self, 'scene_signature', None) == sigs:
            return
        self.scene_signature = sigs
        while self.scene_holder.count():
            it = self.scene_holder.takeAt(0)
            if it.widget(): it.widget().deleteLater()
        if not sigs:
            self.scene_holder.addWidget(label('No scenes yet.', 'small'))
        labels = {s['entity_id']: s.get('label') for s in self.config['scenes']}
        for eid in sigs:
            name = labels.get(eid) or friendly(self.states[eid]).replace('Panel ', '').replace(' Lights', '')
            b = button(name, None, 'secondary')
            b.clicked.connect(lambda checked=False, e=eid, bb=b: self.send_action('scene', 'turn_on', [e], button=bb))
            self.scene_holder.addWidget(b)

    # Lights --------------------------------------------------------------------------------------------
    def make_lights(self):
        page = QWidget(); pv = layout_v(page, (0, 0, 0, 0), 6)
        self.lights_head = QWidget(); hh = QHBoxLayout(self.lights_head); hh.setContentsMargins(0, 0, 0, 0); hh.setSpacing(8)
        self.seg_rooms = button('Rooms', lambda: self.show_view(V_ROOMS), 'primary'); self.seg_colors = button('Colors', lambda: self.show_view(V_COLORS), 'secondary')
        self.edit_btn = button('Edit layout', self.start_edit, 'secondary')
        hh.addWidget(self.seg_rooms, 2); hh.addWidget(self.seg_colors, 2); hh.addStretch(1); hh.addWidget(self.edit_btn, 2)
        pv.addWidget(self.lights_head)
        self.lights_views = QStackedWidget(); pv.addWidget(self.lights_views, 1)
        # V_ROOMS
        w = QWidget(); v = layout_v(w, (0, 0, 0, 0), 0)
        scroll, self.room_list = self.make_scroll(); v.addWidget(scroll); self.room_rows = {}
        self.lights_views.addWidget(w)
        # V_ROOM
        w = QWidget(); rv = layout_v(w, (0, 0, 0, 0), 6)
        head = QHBoxLayout(); head.setSpacing(8)
        self.room_back = button('‹  Rooms', self.close_room, 'secondary'); self.room_back.setFixedWidth(112)
        self.room_title = label('', 'heading', wrap=False)
        self.room_color = button('Color', self.open_room_color, 'secondary'); self.room_color.setFixedWidth(84)
        self.room_toggle = button('OFF', lambda: self.toggle_room(self.current_room, self.room_toggle), 'secondary'); self.room_toggle.setFixedWidth(84)
        head.addWidget(self.room_back); head.addWidget(self.room_title, 1); head.addWidget(self.room_color); head.addWidget(self.room_toggle)
        rv.addLayout(head)
        rscroll, self.room_layout = self.make_scroll(); rv.addWidget(rscroll, 1); self.room_light_rows = {}
        self.lights_views.addWidget(w)
        # V_COLOR (one reusable editor) and V_COLORS (global target + presets)
        self.editor = ColorEditor(self); self.lights_views.addWidget(self.editor)
        self.colors_view = ColorsView(self); self.lights_views.addWidget(self.colors_view)
        # V_EDIT
        w = QWidget(); ev = layout_v(w, (0, 0, 0, 0), 6)
        self.edit_head = QHBoxLayout(); self.edit_head.setSpacing(8); ev.addLayout(self.edit_head)
        ev.addWidget(label('Organize this panel (does not change Home Assistant rooms). Room buttons and All Off use these lights only.', 'small'))
        escroll, self.edit_list = self.make_scroll(); ev.addWidget(escroll, 1)
        self.lights_views.addWidget(w)
        # V_EDITROOM
        w = QWidget(); er = layout_v(w, (0, 0, 0, 0), 6)
        head = QHBoxLayout(); head.setSpacing(8)
        head.addWidget(button('‹  Layout', self.edit_back, 'secondary'))
        self.edit_room_title = label('', 'heading', wrap=False); head.addWidget(self.edit_room_title, 1)
        er.addLayout(head)
        erscroll, self.edit_room_list = self.make_scroll(); er.addWidget(erscroll, 1)
        self.lights_views.addWidget(w)
        # V_MOVE
        w = QWidget(); mv = layout_v(w, (0, 0, 0, 0), 6)
        head = QHBoxLayout(); head.setSpacing(8)
        head.addWidget(button('Cancel', self.cancel_move, 'secondary'))
        self.move_title = label('', 'heading', wrap=False); head.addWidget(self.move_title, 1)
        mv.addLayout(head)
        mscroll, self.move_list = self.make_scroll(); mv.addWidget(mscroll, 1)
        self.lights_views.addWidget(w)
        self.stack.addWidget(page)
        self.show_view(V_ROOMS)

    def show_view(self, idx):
        self.lights_views.setCurrentIndex(idx)
        self.lights_head.setVisible(idx in (V_ROOMS, V_COLORS))
        if idx in (V_ROOMS, V_COLORS):
            set_kind(self.seg_rooms, 'primary' if idx == V_ROOMS else 'secondary')
            set_kind(self.seg_colors, 'primary' if idx == V_COLORS else 'secondary')
            self.edit_btn.setVisible(idx == V_ROOMS)
        if idx == V_COLORS:
            self.colors_view.refresh()

    def room_summary(self, room_id):
        if not self.layout:
            return ('', 0, 0, 0)
        try: room = self.layout.room(room_id)
        except LayoutError: return ('', 0, 0, 0)
        sts = [self.states.get(e) for e in room['lights']]
        avail = sum(1 for s in sts if available(s)); on = sum(1 for s in sts if s and s.get('state') == 'on')
        return (room['label'], on, avail, len(sts))

    def toggle_room(self, room_id, btn=None):
        if not self.layout or not room_id: return
        # Act only on this panel room's individual lights, never on an HA group that may differ after edits.
        sts = {e: self.states.get(e) for e in self.layout.room(room_id)['lights']}
        ids = [e for e, s in sts.items() if available(s)]
        if not ids: return
        any_on = any(sts[e].get('state') == 'on' for e in ids)
        self.send_action('light', 'turn_off' if any_on else 'turn_on', ids, button=btn)

    def populate_rooms(self):
        if not self.layout: return
        ids = [r['id'] for r in self.layout.rooms()]
        if list(self.room_rows) != ids:
            while self.room_list.count():
                it = self.room_list.takeAt(0)
                if it.widget(): it.widget().deleteLater()
            self.room_rows = {}
            for rid in ids:
                row = RoomRow(self, rid); self.room_rows[rid] = row; self.room_list.addWidget(row)
            self.room_list.addStretch(1)
        else:
            for row in self.room_rows.values(): row.refresh()

    def open_room(self, room_id):
        if self.editing: return
        self.current_room = room_id; self.show_view(V_ROOM); self.refresh_room()

    def close_room(self):
        self.current_room = None; self.show_view(V_ROOMS)

    def refresh_room(self):
        if not self.current_room or not self.layout: return
        try: room = self.layout.room(self.current_room)
        except LayoutError: self.close_room(); return
        label_, on, avail, total = self.room_summary(self.current_room)
        self.room_title.setText(label_)
        self.room_toggle.setText('—' if not avail else ('ON' if on else 'OFF'))
        set_kind(self.room_toggle, 'primary' if on and avail else 'secondary')
        self.room_toggle.setEnabled(avail > 0 and self.online)
        self.room_color.setEnabled(avail > 0 and self.online)
        ids = list(room['lights'])
        if list(self.room_light_rows) != ids:
            while self.room_layout.count():
                it = self.room_layout.takeAt(0)
                if it.widget(): it.widget().deleteLater()
            self.room_light_rows = {}
            for e in ids:
                r = LightRow(self, e); self.room_light_rows[e] = r; self.room_layout.addWidget(r)
            if not ids: self.room_layout.addWidget(label('No lights in this room.', 'small'))
            self.room_layout.addStretch(1)
        else:
            for r in self.room_light_rows.values(): r.refresh()

    # colour editors
    def open_color(self, ids):
        self.color_return = V_ROOM if self.current_room else V_ROOMS
        title = friendly(self.states[ids[0]]) if len(ids) == 1 and ids[0] in self.states else 'Room colour'
        self.editor.open(ids, title); self.show_view(V_COLOR)

    def open_room_color(self):
        if self.current_room and self.layout:
            self.open_color(list(self.layout.room(self.current_room)['lights']))
            self.editor.title.setText(self.layout.room(self.current_room)['label'] + ' · all lights')
            self.editor._title = self.layout.room(self.current_room)['label'] + ' · all lights'

    def close_color(self):
        self.show_view(self.color_return if self.color_return != V_ROOM or self.current_room else V_ROOMS)

    def apply_colors(self, ids, choice, brightness, name, btn=None):
        groups = {}
        for e in ids:
            data = C.build_payload(self.states.get(e), choice, brightness)
            if data is None: continue
            groups.setdefault(json.dumps(data, sort_keys=True), []).append(e)
        n = sum(len(v) for v in groups.values())
        if not n:
            self.notice('No selected light supports that colour'); return
        for key, members in groups.items():
            self.send_action('light', 'turn_on', members, button=btn if members is next(iter(groups.values())) else None, **json.loads(key))
        skipped = len(ids) - n
        self.notice(f'{name}: sent to {n} light{"s" if n != 1 else ""}' + (f' ({skipped} skipped)' if skipped else ''))
        QTimer.singleShot(1500, self.poll)

    # global colour helper (existing HA scripts and helpers)
    def color_options(self):
        t = (self.config.get('colors') or {}).get('target_entity')
        return list((self.states.get(t, {}).get('attributes') or {}).get('options') or [])

    def color_target(self):
        t = (self.config.get('colors') or {}).get('target_entity')
        s = self.states.get(t)
        return s.get('state') if s and s.get('state') not in ('unknown', 'unavailable') else ''

    def cycle_target(self, d):
        opts = self.color_options(); cur = self.color_target()
        if not opts: return
        nxt = opts[(opts.index(cur) + d) % len(opts)] if cur in opts else opts[0]
        self.send_action('input_select', 'select_option', [self.config['colors']['target_entity']], option=nxt)

    def preset_value(self, slot):
        s = self.states.get(f'input_text.home_panel_preset_{slot}')
        v = (s or {}).get('state')
        return v if v and v not in ('unknown', 'unavailable') else ''

    def _script(self, key, **variables):
        sid = (self.config.get('colors') or {}).get(key)
        if sid: self.send_action('script', 'turn_on', [sid], variables=variables)
        else: self.notice('Colour scripts are not configured')

    def apply_global_color(self, choice, btn=None):
        kind, value, name = choice
        if kind == 'rgb': self._script('apply_script', rgb=list(value))
        else: self._script('apply_script', kelvin=int(value))
        self.notice(f'{name} sent to {self.color_target() or "target"}')

    def apply_preset(self, slot):
        self._script('preset_script', slot=slot); self.notice(f'Preset {slot} applied')

    def save_preset(self, slot):
        self._script('save_script', slot=slot); self.notice(f'Saved to preset {slot}')
        QTimer.singleShot(1500, self.poll)

    # edit layout ------------------------------------------------------------------------------------------
    def start_edit(self):
        if not self.layout: return
        self.editing = True; self.reset_pending = False
        self.layout.cancel()
        self.render_edit(); self.show_view(V_EDIT)

    def clear_layout(self, lay, keep_stretch=True):
        while lay.count():
            it = lay.takeAt(0)
            if it.widget(): it.widget().deleteLater()

    def render_edit(self):
        self.clear_layout(self.edit_head)
        if self.reset_pending:
            self.edit_head.addWidget(label('Reset every room to its default?', 'rowTitle', wrap=False), 2)
            self.edit_head.addWidget(button('Yes, reset', self.do_reset, 'danger'), 1)
            self.edit_head.addWidget(button('No', self.cancel_reset, 'secondary'), 1)
        else:
            self.edit_head.addWidget(button('Done', self.finish_edit, 'primary'), 1)
            self.edit_head.addWidget(button('Cancel', self.cancel_edit, 'secondary'), 1)
            self.edit_head.addWidget(button('Reset', self.ask_reset, 'secondary'), 1)
        self.clear_layout(self.edit_list)
        rooms = self.layout.rooms()
        for i, r in enumerate(rooms):
            row = QFrame(); row.setObjectName('LightRow'); row.setMinimumHeight(56)
            h = QHBoxLayout(row); h.setContentsMargins(14, 4, 10, 4); h.setSpacing(8)
            names = QVBoxLayout(); names.setSpacing(1)
            names.addWidget(label(r['label'], 'rowTitle', wrap=False)); names.addWidget(label(f'{len(r["lights"])} lights', 'small', wrap=False))
            h.addLayout(names, 1)
            up = button('▲', lambda checked=False, rid=r['id'], k=i: self.move_room(rid, k - 1), 'secondary'); up.setFixedWidth(56); up.setEnabled(i > 0)
            dn = button('▼', lambda checked=False, rid=r['id'], k=i: self.move_room(rid, k + 1), 'secondary'); dn.setFixedWidth(56); dn.setEnabled(i < len(rooms) - 1)
            h.addWidget(up); h.addWidget(dn)
            h.addWidget(button('Lights ›', lambda checked=False, rid=r['id']: self.edit_room(rid), 'secondary'))
            self.edit_list.addWidget(row)
        self.edit_list.addStretch(1)

    def move_room(self, rid, idx):
        self.layout.reorder_room(rid, idx); self.render_edit()

    def ask_reset(self):
        self.reset_pending = True; self.render_edit()

    def cancel_reset(self):
        self.reset_pending = False; self.render_edit()

    def do_reset(self):
        self.layout.reset_to_defaults(); self.reset_pending = False; self.render_edit()

    def cancel_edit(self):
        self.layout.cancel(); self.leave_edit()

    def finish_edit(self):
        try:
            self.layout.commit_atomic()
        except (LayoutError, OSError) as e:
            self.notice('Could not save layout: ' + str(e)[:60]); return
        self.leave_edit()
        self.notice('Layout saved on this panel')

    def leave_edit(self):
        self.editing = False; self.reset_pending = False
        self.room_rows = {}; self.room_light_rows = {}
        self.refresh_all(); self.show_view(V_ROOMS)

    def edit_room(self, rid):
        self.edit_room_id = rid; self.render_edit_room(); self.show_view(V_EDITROOM)

    def edit_back(self):
        self.render_edit(); self.show_view(V_EDIT)

    def render_edit_room(self):
        room = self.layout.room(self.edit_room_id)
        self.edit_room_title.setText(room['label'])
        self.clear_layout(self.edit_room_list)
        n = len(room['lights'])
        if not n:
            self.edit_room_list.addWidget(label('No lights in this room. Use "Move to…" on another room\'s light.', 'small'))
        for i, e in enumerate(room['lights']):
            st = self.states.get(e)
            row = QFrame(); row.setObjectName('LightRow'); row.setMinimumHeight(52)
            h = QHBoxLayout(row); h.setContentsMargins(14, 4, 10, 4); h.setSpacing(8)
            names = QVBoxLayout(); names.setSpacing(1)
            names.addWidget(label(friendly(st) if st else e, 'rowTitle', wrap=False))
            names.addWidget(label('Unavailable' if not available(st) else 'Available', 'small', wrap=False))
            h.addLayout(names, 1)
            h.addWidget(button('Move to…', lambda checked=False, eid=e: self.pick_destination(eid), 'secondary'))
            up = button('▲', lambda checked=False, eid=e, k=i: self.move_light_in_room(eid, k - 1), 'secondary'); up.setFixedWidth(56); up.setEnabled(i > 0)
            dn = button('▼', lambda checked=False, eid=e, k=i: self.move_light_in_room(eid, k + 1), 'secondary'); dn.setFixedWidth(56); dn.setEnabled(i < n - 1)
            h.addWidget(up); h.addWidget(dn)
            self.edit_room_list.addWidget(row)
        self.edit_room_list.addStretch(1)

    def move_light_in_room(self, eid, idx):
        self.layout.reorder_light(self.edit_room_id, eid, idx); self.render_edit_room()

    def pick_destination(self, eid):
        self.move_eid = eid
        st = self.states.get(eid)
        self.move_title.setText('Move ' + (friendly(st) if st else eid) + ' to…')
        self.clear_layout(self.move_list)
        src = self.layout.room_of(eid)
        grid = QGridLayout(); grid.setSpacing(8)
        gw = QWidget(); gw.setLayout(grid)
        dests = [r for r in self.layout.rooms() if r['id'] != src]
        for i, r in enumerate(dests):
            grid.addWidget(button(r['label'], lambda checked=False, rid=r['id']: self.do_move(rid), 'secondary'), i // 3, i % 3)
        for c in range(3): grid.setColumnStretch(c, 1)
        self.move_list.addWidget(gw); self.move_list.addStretch(1)
        self.show_view(V_MOVE)

    def do_move(self, rid):
        try: self.layout.move_light(self.move_eid, rid)
        except LayoutError as e: self.notice(str(e))
        self.render_edit_room(); self.show_view(V_EDITROOM)

    def cancel_move(self):
        self.show_view(V_EDITROOM)

    # layout synchronisation with live HA ------------------------------------------------------------------
    def sync_layout(self):
        if self.editing: return
        defaults = settings.default_rooms(self.config, self.states)
        if not defaults: return
        ddata = {'version': 1, 'rooms': [{'id': d['id'], 'label': d['label'], 'order': d['order'], 'lights': d['lights']} for d in defaults]}
        allowed = settings.individual_light_ids(self.states) | {l for d in defaults for l in d['lights']}
        if self.layout is None:
            try:
                self.layout = PanelLayout.load(self.layout_path, ddata, allowed)
            except LayoutError as e:
                self.notice('Layout defaults invalid: ' + str(e)[:50]); return
            self.room_meta = {d['id']: {'favorite': d['favorite'], 'source': d['source']} for d in defaults}
            for r in self.layout.rooms():
                self.room_meta.setdefault(r['id'], {'favorite': False, 'source': None})
        self.layout.allowed = allowed
        # expand groups that were not resolvable earlier, and add new members of configured groups
        placed = set(self.layout.all_lights())
        for room in self.layout.rooms():
            new = []
            for e in room['lights']:
                if settings.is_group(self.states.get(e)):
                    new.extend(m for m in settings.members_of(self.states, e) if m not in placed or m in new)
                    placed.discard(e)
                else:
                    new.append(e)
            room['lights'] = list(dict.fromkeys(new))
        placed = set(self.layout.all_lights())
        for d in defaults:
            try: room = self.layout.room(d['id'])
            except LayoutError: continue
            for m in d['lights']:
                if m not in placed and m in allowed:
                    room['lights'].append(m); placed.add(m)
        self.layout.saved = json.loads(json.dumps(self.layout.data))

    # --- cameras ----------------------------------------------------------------------------------------
    def make_cameras(self):
        # Full-bleed snapshot is rendered by camera_view behind the layout.
        # Only this collapsible drawer and the compact nav consume touch space.
        page = QWidget(); h = QHBoxLayout(page)
        h.setContentsMargins(0, 0, 0, 0); h.setSpacing(0)
        h.addStretch(1)
        side = QVBoxLayout(); side.setSpacing(6)
        self.camera_toggle = button('Camera controls', self.toggle_camera_controls, 'secondary')
        self.camera_toggle.setFixedWidth(166)
        side.addWidget(self.camera_toggle, 0, Qt.AlignRight)
        self.camera_controls = card('CameraControls')
        self.camera_controls.setFixedWidth(228)
        inner = layout_v(self.camera_controls, (10, 8, 10, 10), 6)
        inner.addWidget(label('SELECT CAMERA', 'overline'))
        cscroll, self.camera_choice = self.make_scroll(); inner.addWidget(cscroll, 1)
        actions = QHBoxLayout(); actions.setSpacing(6)
        self.refresh_btn = button('Refresh', lambda: self.poll_camera(True), 'primary')
        self.pause_btn = button('Pause', self.toggle_pause, 'secondary')
        actions.addWidget(self.refresh_btn, 1); actions.addWidget(self.pause_btn, 1)
        inner.addLayout(actions)
        side.addWidget(self.camera_controls, 1)
        side.addStretch(1)
        h.addLayout(side)
        self.stack.addWidget(page)
        self.camera_buttons = {}
        self.camera_controls.hide()
        self.render_no_camera()

    def toggle_camera_controls(self):
        self.camera_controls_expanded = not self.camera_controls_expanded
        self.camera_controls.setVisible(self.camera_controls_expanded)
        self.camera_toggle.setText('Hide controls' if self.camera_controls_expanded else 'Camera controls')
        set_kind(self.camera_toggle, 'primary' if self.camera_controls_expanded else 'secondary')

    def scale_camera(self):
        """Keep one bounded source and rescale only on new snapshots / resize."""
        if self.camera_source is None or self.camera_source.isNull(): return
        size = self.camera_view.contentsRect().size()
        if size.width() < 1 or size.height() < 1: return
        self.preview_image = self.camera_source.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.camera_view.setPixmap(self.preview_image)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'camera_view'):
            self.camera_view.setGeometry(6, 6, max(1, self.width() - 12), max(1, self.height() - 12))
            self.scale_camera()

    def camera_ids(self):
        want = self.config['camera_entities']
        if want: return [e for e in want if e in self.states]
        if self.config.get('auto_discover_cameras', False):
            return sorted(e for e in self.states if e.startswith('camera.'))
        return []

    def render_no_camera(self):
        self.free_preview()
        self.camera_view.setText('No camera available\n\nNo camera entity is configured for this panel.')
        self.camera_stamp.setText('No camera configured · snapshots only')
        self.refresh_btn.setEnabled(False); self.pause_btn.setEnabled(False)

    def populate_cameras(self):
        ids = self.camera_ids()
        if tuple(ids) == tuple(self.camera_buttons): return
        self.clear_layout(self.camera_choice); self.camera_buttons = {}
        for e in ids:
            b = button(friendly(self.states[e]), lambda checked=False, x=e: self.select_camera(x), 'secondary')
            self.camera_buttons[e] = b; self.camera_choice.addWidget(b)
        self.camera_choice.addStretch(1)
        if self.active_camera not in ids:
            self.active_camera = ids[0] if ids else None
            self.free_preview()
        if not ids: self.render_no_camera()
        else:
            self.refresh_btn.setEnabled(True); self.pause_btn.setEnabled(True)
            self.camera_view.setText('Tap Refresh to load a snapshot.')
            self.mark_camera()

    def mark_camera(self):
        for e, b in self.camera_buttons.items(): set_kind(b, 'primary' if e == self.active_camera else 'secondary')

    def select_camera(self, eid):
        if eid == self.active_camera: return
        self.active_camera = eid; self.cam_gen += 1; self.free_preview(); self.mark_camera()
        self.camera_view.setText('Loading snapshot…'); self.poll_camera(True)

    def toggle_pause(self):
        self.cam_paused = not self.cam_paused
        self.pause_btn.setText('Resume' if self.cam_paused else 'Pause')
        set_kind(self.pause_btn, 'primary' if self.cam_paused else 'secondary')

    def free_preview(self):
        self.camera_source = None; self.preview_image = None
        self.camera_view.clear()

    def poll_camera(self, manual=False):
        if self.page_index != PAGE_CAMERAS or not self.active_camera or not self.online: return
        if self.cam_paused and manual is not True: return
        eid, gen = self.active_camera, self.cam_gen
        maxpx = self.config['camera_max_decoded_pixels']

        def work():
            data = self.client.camera_snapshot(eid)
            return camera.decode_bounded(data, max_pixels=maxpx) if data else None
        self.dispatch('camera', work, lambda img: self.camera_ready(eid, gen, img),
                      lambda e: self.camera_failed(eid, gen, e))

    def camera_failed(self, eid, gen, message):
        if gen != self.cam_gen or eid != self.active_camera or self.page_index != PAGE_CAMERAS:
            if self.page_index == PAGE_CAMERAS and self.active_camera:
                QTimer.singleShot(0, lambda: self.poll_camera(True))
            return
        self.camera_stamp.setText('Snapshot unavailable: ' + message[:80])
        if self.camera_source is None:
            self.camera_view.setText('Snapshot unavailable · try Refresh')

    def camera_ready(self, eid, gen, img):
        if gen != self.cam_gen or eid != self.active_camera or self.page_index != PAGE_CAMERAS:
            # A switch while another request ran must refresh the new selection.
            if self.page_index == PAGE_CAMERAS and self.active_camera:
                QTimer.singleShot(0, lambda: self.poll_camera(True))
            return
        if img is None:
            self.free_preview()
            self.camera_view.setText('Demo mode: no snapshot'); return
        self.camera_source = QPixmap.fromImage(img)
        self.scale_camera()
        self.camera_stamp.setText(f'{friendly(self.states.get(eid, {"entity_id": eid}))} · {datetime.now():%-I:%M:%S %p} · not live')

    # --- settings ---------------------------------------------------------------------------------------
    def make_settings(self):
        page = QWidget(); v = layout_v(page, (0, 0, 0, 0), 6)
        head = QHBoxLayout(); head.setSpacing(8)
        head.addWidget(button('‹  Back', lambda: self.switch_page(PAGE_HOME), 'secondary'))
        head.addWidget(label('Settings & diagnostics', 'heading', wrap=False), 1)
        head.addWidget(button('Refresh now', self.poll, 'primary'))
        v.addLayout(head)
        body = QHBoxLayout(); body.setSpacing(10)
        block = card(); inner = layout_v(block, (14, 8, 14, 8), 6)
        inner.addWidget(label('APPEARANCE', 'overline'))
        choices = QHBoxLayout(); choices.setSpacing(8); self.theme_buttons = {}
        for theme in ('auto', 'light', 'dark'):
            b = button(theme.title(), lambda checked=False, t=theme: self.set_override(t), 'secondary')
            choices.addWidget(b); self.theme_buttons[theme] = b
        inner.addLayout(choices)
        inner.addWidget(label('Auto follows sun.sun (local clock if offline). This is separate from the HA dashboard theme.', 'small'))
        self.cam_pref = button('', self.toggle_camera_pref, 'secondary'); inner.addWidget(self.cam_pref)
        inner.addStretch(1)
        body.addWidget(block, 1)
        status = card(); st = layout_v(status, (14, 8, 14, 8), 4)
        st.addWidget(label('DIAGNOSTICS', 'overline'))
        self.diag = label('', 'small'); st.addWidget(self.diag); st.addStretch(1)
        body.addWidget(status, 1)
        v.addLayout(body, 1); self.stack.addWidget(page)
        self.update_theme_buttons(); self.update_cam_pref()

    def toggle_camera_pref(self):
        self.camera_auto = not self.camera_auto; self.save_preferences(); self.update_cam_pref()

    def update_cam_pref(self):
        self.cam_pref.setText('Camera: refresh every %d s' % self.config['snapshot_seconds'] if self.camera_auto else 'Camera: manual refresh only')

    def update_diagnostics(self):
        if self.page_index != PAGE_SETTINGS: return
        ha = ('Connected' if self.online else 'Offline') if not self.demo else 'Demo mode'
        c = telemetry.COUNTERS
        t = telemetry.cpu_temp_c(); up = telemetry.uptime_s()
        self.update_health()
        lines = [f'Home Assistant: {ha} · last update {age_text(self.store.age())}',
                 *self.health_lines,
                 f'Panel memory: {telemetry.mib(telemetry.rss_kib()) or "?"} MiB · {telemetry.mib(telemetry.mem_available_kib()) or "?"} MiB free',
                 f'CPU temp: {"%.0f °C" % t if t is not None else "n/a"} · uptime {int(up // 3600)} h {int(up % 3600 // 60)} m' if up is not None else 'CPU temp: n/a',
                 f'HA fetches {c["ha_state_requests"]} ({c["ha_state_bytes"] // 1024} KiB) · actions {c["ha_actions"]} · errors {c["network_errors"]}',
                 f'Native Qt panel v{VERSION} · no browser']
        self.diag.setText('\n'.join(lines))

    # --- navigation ---------------------------------------------------------------------------------------
    def update_nav(self):
        for i, b in enumerate(self.nav_buttons):
            b.setProperty('active', str(i == self.page_index).lower()); repolish(b)

    def switch_page(self, i):
        leaving_cameras = self.page_index == PAGE_CAMERAS and i != PAGE_CAMERAS
        self.page_index = i; self.stack.setCurrentIndex(i); self.update_nav()
        camera_mode = i == PAGE_CAMERAS
        for w in self.header_labels: w.setVisible(not camera_mode)
        self.bottom_status.setVisible(not camera_mode)
        self.bottom_detail.setVisible(not camera_mode)
        self.camera_stamp.setVisible(camera_mode)
        self.camera_view.setVisible(camera_mode)
        if camera_mode: self.camera_view.lower()
        self.navbar.setMaximumWidth(450 if camera_mode else 16777215)
        self.navbar.setProperty('camera', 'true' if camera_mode else 'false')
        repolish(self.navbar)
        if leaving_cameras:
            self.cam_gen += 1; self.camera_timer.stop(); self.free_preview()
            if not self.camera_ids(): self.render_no_camera()
            else: self.camera_view.setText('Tap Refresh to load a snapshot.')
        if i == PAGE_LIGHTS:
            if not self.editing and self.lights_views.currentIndex() not in (V_COLORS,): self.close_room()
        if camera_mode and self.camera_ids():
            self.camera_view.setText('Loading snapshot…')
            self.poll_camera(True)
            if self.camera_auto: self.camera_timer.start(self.config['snapshot_seconds'] * 1000)
        if i == PAGE_SETTINGS:
            self.update_diagnostics(); self.diag_timer.start(5000)
        else:
            self.diag_timer.stop()

    # --- network/dispatch -----------------------------------------------------------------------------------
    def dispatch(self, key, fn, done, onerror=None):
        if key in self.inflight: return
        self.inflight.add(key)
        job = Job(fn)

        def ok(value):
            self.inflight.discard(key); done(value)

        def fail(err):
            self.inflight.discard(key)
            if onerror: onerror(err)
        job.signals.done.connect(ok); job.signals.error.connect(fail)
        self.pool.start(job)

    def keep(self, eid):
        d = eid.split('.', 1)[0]
        colors = self.config.get('colors') or {}
        if d in ('light', 'weather') or eid == 'sun.sun': return True
        if d == 'scene': return eid in {s['entity_id'] for s in self.config['scenes']}
        if d == 'camera': return bool(self.config['camera_entities']) and eid in self.config['camera_entities'] or (not self.config['camera_entities'] and self.config.get('auto_discover_cameras', False))
        if eid == colors.get('target_entity') or eid in health.entity_ids(self.config['health']): return True
        return eid.startswith('input_text.home_panel_preset_')

    def poll(self):
        self.dispatch('states', lambda: self.client.states(self.keep), self.update_states, self.connection_error)

    def connection_error(self, err):
        was = self.store.online
        self.store.failed(); self.fail_count += 1
        telemetry.note('offline: ' + err[:40])
        delay = [5, 10, 30, 60][min(self.fail_count, 4) - 1]
        self.poll_timer.setInterval(int(delay * random.uniform(0.9, 1.1) * 1000))
        self.render_offline(delay)
        if was is not False: self.refresh_all()

    def render_offline(self, delay=None):
        age = age_text(self.store.age())
        self.top_summary.setText('Home is offline')
        self.bottom_status.setText('○ Home is offline')
        d = f'Showing last known data from {age}.'
        if delay: d += f' Retrying in {delay} s.'
        if self.last_weather: d += f'\nWeather was {self.last_weather} ({age}).'
        self.bottom_detail.setText(d)

    def update_states(self, entities):
        recovered = self.fail_count > 0
        self.fail_count = 0
        if recovered: self.poll_timer.setInterval(self.config['poll_seconds'] * 1000)
        was_online = self.store.online
        changed = self.store.update(entities)
        self.sync_layout()
        if changed or was_online is not True:
            self.refresh_all()
        self.update_weather()
        self.apply_auto_theme()
        self.update_health()

    def local_health(self):
        return {'temp': telemetry.cpu_temp_c(), 'ram': telemetry.ram_used_pct(), 'disk': telemetry.disk_used_pct()}

    def update_health(self):
        status, self.health_lines, _ = health.summarize(self.states, self.config['health'], self.local_health())
        self.health_status.setText(status)

    def refresh_all(self):
        if self.layout:
            on = sum(1 for e in self.layout.all_lights() if (self.states.get(e) or {}).get('state') == 'on')
            tot = len(self.layout.all_lights())
            self.summary_text = f'{on} of {tot} lights on'
            if self.online: self.top_summary.setText('Demo mode · no real devices' if self.demo else self.summary_text)
        if not self.online: self.render_offline()
        self.populate_home(); self.populate_scenes()
        if not self.editing:
            self.populate_rooms(); self.refresh_room()
        if self.lights_views.currentIndex() == V_COLOR: self.editor.refresh()
        if self.lights_views.currentIndex() == V_COLORS: self.colors_view.refresh()
        self.populate_cameras()

    def notice(self, text, ms=4500):
        """Short message in the display-only header; never needs a tap to dismiss."""
        self.notice_token += 1; tok = self.notice_token
        self.top_summary.setText(text)

        def restore():
            if tok == self.notice_token:
                self.top_summary.setText(getattr(self, 'summary_text', '') if self.online else 'Home is offline')
        QTimer.singleShot(ms, restore)

    def send_action(self, domain, action, entity_ids, button=None, **kwargs):
        if not self.online:
            self.notice('Home is offline - nothing was sent'); return False
        ids = [entity_ids] if isinstance(entity_ids, str) else list(entity_ids)
        key = (domain, action, tuple(sorted(ids)), repr(sorted(kwargs.items())))
        now = time.monotonic()
        if now - self.last_action.get(key, -1e9) < 0.6:
            return False  # coalesce repeat taps
        if self.pending >= 8:
            self.notice('Busy - try again in a moment'); return False
        self.last_action[key] = now
        if len(self.last_action) > 64:
            self.last_action = {k: t for k, t in self.last_action.items() if now - t < 5}
        if button is not None:
            try:
                button.setEnabled(False)
                QTimer.singleShot(700, lambda b=button: self._unbusy(b))
            except RuntimeError:
                pass
        self.pending += 1

        def done(_):
            # devices confirm to HA a moment later: re-read twice so the panel never shows a stale state
            self.pending -= 1; QTimer.singleShot(400, self.poll); QTimer.singleShot(2200, self.poll)

        def err(e):
            self.pending -= 1; self.notice('Action failed: ' + e[:60])
        self.dispatch('action:' + str(time.monotonic_ns()), lambda: self.client.service(domain, action, ids, **kwargs), done, err)
        return True

    def _unbusy(self, b):
        try:
            b.setEnabled(True)
        except RuntimeError:
            pass  # widget was rebuilt
        self.refresh_all() if self.online else None

    def all_lights_off(self):
        if not self.layout: return
        ids = [e for e in self.layout.all_lights() if (self.states.get(e) or {}).get('state') == 'on']
        if ids: self.send_action('light', 'turn_off', ids)
        else: self.notice('All panel lights are already off')

    # --- weather ----------------------------------------------------------------------------------------------
    def weather_entity(self):
        want = self.config.get('weather_entity')
        if want: return self.states.get(want)
        ws = sorted(e for e in self.states if e.startswith('weather.'))
        return self.states[ws[0]] if ws else None

    def update_weather(self):
        if not self.online:
            return
        w = self.weather_entity()
        if not w or w.get('state') in ('unavailable', 'unknown'):
            self.bottom_status.setText('Weather unavailable'); self.bottom_detail.setText('')
            return
        a = w.get('attributes', {}); glyph, name = WEATHER.get(w.get('state'), ('', str(w.get('state', '')).replace('-', ' ').title()))
        t = a.get('temperature'); unit = a.get('temperature_unit', '')
        temp = f'{round(t)}{unit}' if t is not None else ''
        self.last_weather = f'{temp} {name}'.strip()
        self.bottom_status.setText(f'{glyph}  {temp}   {name}'.strip())
        bits = []
        if a.get('humidity') is not None: bits.append(f"Humidity {round(a['humidity'])}%")
        if a.get('wind_speed') is not None: bits.append(f"Wind {round(a['wind_speed'])} {a.get('wind_speed_unit', '')}".strip())
        lines = ['  ·  '.join(bits)] if bits else []
        f = self.forecast_next
        if f:
            fg, fname = WEATHER.get(f.get('condition'), ('', str(f.get('condition', '')).replace('-', ' ').title()))
            hi, lo = f.get('temperature'), f.get('templow')
            rng = f' · {round(hi)}° / {round(lo)}°' if hi is not None and lo is not None else ''
            lines.append(f'Tomorrow: {fname}{rng}')
        self.bottom_detail.setText('\n'.join(lines))
        if time.monotonic() - self.forecast_at > 1800 and not self.demo:  # at most 2 forecast requests/hour
            self.forecast_at = time.monotonic()
            self.dispatch('forecast', lambda: self.client.forecast(w['entity_id']), self.set_forecast, lambda e: None)

    def set_forecast(self, days):
        self.forecast_next = days[1] if len(days) > 1 else None
        self.update_weather()

    # --- clock / theme -----------------------------------------------------------------------------------------
    def clock_update(self):
        now = datetime.now()
        self.clock.setText(now.strftime('%-I:%M %p'))
        h = now.hour
        self.top_greeting.setText('Good morning' if 5 <= h < 12 else ('Good afternoon' if 12 <= h < 18 else 'Good evening'))
        self.date_label.setText(now.strftime('%A, %B %d'))
        self.apply_auto_theme()

    def set_override(self, theme):
        self.override = theme; self.save_preferences(); self.apply_auto_theme()

    def update_theme_buttons(self):
        if not hasattr(self, 'theme_buttons'): return
        for name, b in self.theme_buttons.items():
            set_kind(b, 'primary' if name == self.override else 'secondary')

    def apply_auto_theme(self):
        if self.override in ('light', 'dark'): theme = self.override
        else:
            sun = self.states.get('sun.sun', {}).get('state')
            theme = 'light' if sun == 'above_horizon' else ('dark' if sun == 'below_horizon' else ('light' if 7 <= datetime.now().hour < 19 else 'dark'))
        self.theme_status.setText('AUTO ' + theme.upper() if self.override == 'auto' else theme.upper())
        if theme != self.current_theme: self.set_theme(theme)
        self.update_theme_buttons()

    def set_theme(self, theme):
        self.current_theme = theme; p = PALETTES[theme]
        # Flat QSS: no blur, translucency effects, transitions or periodic repaint.
        # Only the camera drawer uses a constant alpha fill over its snapshot.
        self.setStyleSheet('''
        QWidget#Root { background: %(bg)s; color: %(text)s; }
        QWidget { color: %(text)s; font-family: 'DejaVu Sans', sans-serif; font-size: 15px; }
        QLabel[role="infoClock"] { font-size: 44px; font-weight: 700; }
        QLabel[role="heading"] { font-size: 22px; font-weight: 700; }
        QLabel[role="rowTitle"] { font-size: 17px; font-weight: 600; }
        QLabel[role="overline"] { font-size: 12px; font-weight: 700; color: %(muted)s; }
        QLabel[role="small"] { font-size: 13px; color: %(muted)s; }
        QLabel[role="cameraPlaceholder"] { font-size: 16px; color: #AABFC4; }
        QLabel#CameraCanvas { background: #0B161D; border: 2px solid #39525B; border-radius: 16px; }
        QLabel[role="cameraCaption"] { color: #F2F8F6; background: rgba(10, 23, 30, 190);
                                       border: 1px solid #4D6F75; border-radius: 12px;
                                       padding: 8px 14px; font-size: 13px; }
        QFrame#Card, QFrame#Nav, QFrame#LightRow {
            background: %(card)s; border: 1px solid %(border)s; border-radius: 16px;
        }
        QFrame#LightRow { border-radius: 12px; }
        QFrame#Nav { background: %(card)s; border-radius: 14px; }
        QFrame#Nav[camera="true"], QFrame#CameraControls {
            background: rgba(10, 23, 30, 208); border: 1px solid #4D6F75; border-radius: 14px;
        }
        QFrame#CameraControls QLabel { color: #DFEFEC; }
        QPushButton {
            border: 1px solid transparent; border-radius: 12px; background: %(card2)s;
            color: %(text)s; padding: 2px 12px; font-size: 15px; font-weight: 600;
        }
        QPushButton:pressed { border: 1px solid %(accent)s; }
        QPushButton[kind="primary"] { background: %(accent)s; color: %(bg)s; }
        QPushButton[kind="danger"] { background: %(danger)s; color: #FFFFFF; }
        QPushButton[kind="nav"] { background: transparent; }
        QPushButton[active="true"] { background: %(accent)s; color: %(bg)s; }
        QFrame#Nav[camera="true"] QPushButton[kind="nav"] { color: #EBF4F1; }
        QFrame#Nav[camera="true"] QPushButton[active="true"] { color: #0A1720; }
        QFrame#CameraControls QPushButton { color: #F0F7F4; background: #28414B; }
        QFrame#CameraControls QPushButton[kind="primary"] { background: #85DCC2; color: #0A1720; }
        QPushButton:disabled { color: %(muted)s; background: %(card)s; }
        QSlider::groove:horizontal { background: %(border)s; height: 8px; border-radius: 4px; }
        QSlider::sub-page:horizontal { background: %(accent)s; border-radius: 4px; }
        QSlider::handle:horizontal { background: %(text)s; width: 26px; margin: -9px 0; border-radius: 13px; }
        QSlider:disabled::handle:horizontal { background: %(muted)s; }
        QScrollArea { background: transparent; border: none; }
        QScrollBar:vertical { background: transparent; width: 0px; }
        ''' % p)
        self._repolish()
        QTimer.singleShot(250, self._repolish)

    def _repolish(self):
        for w in self.findChildren(QWidget):
            w.style().unpolish(w); w.style().polish(w)
        self.update()


def load_config(path, demo):
    path = Path(path)
    if path.exists(): return json.loads(path.read_text(encoding='utf-8'))
    if demo: return json.loads((ROOT / 'config.example.json').read_text(encoding='utf-8'))
    print(f'Configuration missing: {path}. Copy config.example.json to config.json first.', file=sys.stderr)
    sys.exit(2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--demo', action='store_true', help='Offline demo data; no API requests')
    ap.add_argument('--windowed', action='store_true', help='Do not launch fullscreen')
    ap.add_argument('--config', default=str(ROOT / 'config.json'))
    ap.add_argument('--size', default='', help='WxH, default: screen size when fullscreen else 1024x600')
    args = ap.parse_args()
    config = load_config(args.config, args.demo)

    def _hook(t, v, tb):
        import traceback; traceback.print_exception(t, v, tb)
    sys.excepthook = _hook  # PyQt5 aborts on uncaught slot exceptions; log them instead
    app = QApplication(sys.argv[:1]); app.setStyle('Fusion')
    if args.size: size = tuple(int(x) for x in args.size.lower().split('x'))
    elif not args.windowed:
        sz = app.primaryScreen().size(); size = (sz.width(), sz.height())
    else: size = (1024, 600)
    try: Panel(config, demo=args.demo, fullscreen=not args.windowed, size=size)
    except (HomeAssistantError, settings.ConfigError) as e:
        print('Configuration error:', e, file=sys.stderr); sys.exit(2)
    sys.exit(app.exec_())


if __name__ == '__main__': main()
