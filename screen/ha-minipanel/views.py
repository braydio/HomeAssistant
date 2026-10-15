"""Reusable Qt Widgets for the panel. Every interactive widget here is at least 44 px tall and is only ever
placed inside the live touch band by panel.py."""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout, QWidget)

import colors as C

HIT = 44  # minimum touch target height (px)


def label(text='', role='', wrap=True):
    w = QLabel(text)
    if role:
        w.setProperty('role', role)
    w.setWordWrap(wrap)
    return w


def card(name='Card'):
    w = QFrame(); w.setObjectName(name); return w


def layout_v(widget=None, margins=(0, 0, 0, 0), gap=12):
    v = QVBoxLayout(widget) if widget else QVBoxLayout()
    v.setContentsMargins(*margins); v.setSpacing(gap); return v


def button(text, callback, kind='secondary', height=HIT):
    b = QPushButton(text); b.setProperty('kind', kind); b.setCursor(Qt.PointingHandCursor)
    b.setMinimumHeight(height)
    if callback:
        b.clicked.connect(callback)
    return b


def repolish(w):
    w.style().unpolish(w); w.style().polish(w)


def set_kind(b, kind):
    if b.property('kind') != kind:
        b.setProperty('kind', kind); repolish(b)


def friendly(s):
    return (s.get('attributes') or {}).get('friendly_name') or s['entity_id'].split('.', 1)[-1].replace('_', ' ').title()


def available(s):
    return bool(s) and s.get('state') not in ('unavailable', 'unknown')


def style_power(btn, st, usable=True):
    on = bool(st) and st.get('state') == 'on'
    ok = available(st)
    btn.setText('—' if not ok else ('ON' if on else 'OFF'))
    set_kind(btn, 'primary' if (on and ok) else 'secondary')
    btn.setEnabled(ok and usable)


class LightRow(QFrame):
    """One individual light: name/state, brightness slider (only if supported), Color, ON/OFF."""

    def __init__(self, panel, eid):
        super().__init__(); self.setObjectName('LightRow'); self.setMinimumHeight(52)
        self.panel = panel; self.eid = eid
        h = QHBoxLayout(self); h.setContentsMargins(14, 4, 10, 4); h.setSpacing(10)
        names = QVBoxLayout(); names.setSpacing(1)
        self.title = label('', 'rowTitle', wrap=False); self.meta = label('', 'small', wrap=False)
        names.addWidget(self.title); names.addWidget(self.meta)
        h.addLayout(names, 2)
        self.slider = QSlider(Qt.Horizontal); self.slider.setRange(1, 100); self.slider.setSingleStep(5)
        self.slider.setMinimumWidth(100)
        self.slider.sliderReleased.connect(self.set_brightness)
        h.addWidget(self.slider, 3)
        self.color_btn = button('Color', lambda: panel.open_color([eid]), 'secondary')
        self.color_btn.setFixedWidth(78)
        h.addWidget(self.color_btn)
        self.toggle = button('OFF', self.do_toggle, 'secondary'); self.toggle.setFixedWidth(84)
        h.addWidget(self.toggle)
        self.refresh()

    def refresh(self):
        st = self.panel.states.get(self.eid)
        online = self.panel.online
        if not st:
            self.title.setText(self.eid.split('.', 1)[1].replace('_', ' ').title()); self.meta.setText('Not found')
            self.toggle.setEnabled(False); self.color_btn.setEnabled(False); self.slider.setVisible(False)
            return
        cap = C.capabilities(st); on = st.get('state') == 'on'
        self.title.setText(friendly(st))
        bri = (st.get('attributes') or {}).get('brightness')
        if not cap['available']: self.meta.setText('Unavailable')
        elif not online: self.meta.setText('Offline · last known ' + ('On' if on else 'Off'))
        elif on and bri is not None and cap['dimmer']: self.meta.setText('On · %d%%' % round(bri / 255 * 100))
        else: self.meta.setText('On' if on else 'Off')
        style_power(self.toggle, st, online)
        self.color_btn.setEnabled(cap['available'] and online)
        self.slider.setVisible(cap['dimmer'] and cap['available'])
        self.slider.setEnabled(on and cap['available'] and online)
        if not self.slider.isSliderDown() and bri is not None:
            self.slider.setValue(max(1, round(bri / 255 * 100)))

    def do_toggle(self):
        st = self.panel.states.get(self.eid)
        self.panel.send_action('light', 'turn_off' if st and st.get('state') == 'on' else 'turn_on', [self.eid], button=self.toggle)

    def set_brightness(self):
        self.panel.send_action('light', 'turn_on', [self.eid], brightness_pct=self.slider.value())


class RoomRow(QFrame):
    """A panel room in the Rooms list. Tapping the name area opens it; the button toggles all member lights."""

    def __init__(self, panel, room_id):
        super().__init__(); self.setObjectName('LightRow'); self.setMinimumHeight(56)
        self.panel = panel; self.room_id = room_id; self._press = None
        h = QHBoxLayout(self); h.setContentsMargins(14, 4, 10, 4); h.setSpacing(10)
        names = QVBoxLayout(); names.setSpacing(1)
        self.title = label('', 'rowTitle', wrap=False); self.meta = label('', 'small', wrap=False)
        names.addWidget(self.title); names.addWidget(self.meta)
        h.addLayout(names, 1)
        self.chev = label('›', 'heading', wrap=False)
        h.addWidget(self.chev)
        self.toggle = button('OFF', self.do_toggle, 'secondary'); self.toggle.setFixedWidth(84)
        h.addWidget(self.toggle)
        self.refresh()

    def refresh(self):
        label_, on, avail, total = self.panel.room_summary(self.room_id)
        self.title.setText(label_)
        online = self.panel.online
        self.meta.setText(('Unavailable' if avail == 0 else f'{on} of {total} on' if online else f'Offline · last known {on} of {total} on'))
        self.toggle.setText('—' if avail == 0 else ('ON' if on else 'OFF'))
        set_kind(self.toggle, 'primary' if on and avail else 'secondary')
        self.toggle.setEnabled(avail > 0 and online)

    def do_toggle(self):
        self.panel.toggle_room(self.room_id, self.toggle)

    def mousePressEvent(self, e):
        self._press = e.pos(); super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        super().mouseReleaseEvent(e)
        if self._press is not None and (e.pos() - self._press).manhattanLength() < 14:
            self.panel.open_room(self.room_id)
        self._press = None


class RoomTile(QFrame):
    """Home-page favourite room: name, aggregate state, one big Toggle."""

    def __init__(self, panel, room_id):
        super().__init__(); self.setObjectName('Card'); self.panel = panel; self.room_id = room_id
        v = layout_v(self, (14, 8, 14, 8), 4)
        self.title = label('', 'rowTitle', wrap=False); self.meta = label('', 'small', wrap=False)
        v.addWidget(self.title); v.addWidget(self.meta); v.addStretch(1)
        self.toggle = button('Toggle', lambda: panel.toggle_room(room_id, self.toggle), 'secondary')
        v.addWidget(self.toggle)
        self.refresh()

    def refresh(self):
        label_, on, avail, total = self.panel.room_summary(self.room_id)
        self.title.setText(label_)
        self.meta.setText('Unavailable' if avail == 0 else (f'{on} of {total} on' if self.panel.online else 'Offline'))
        self.toggle.setText('Turn off' if on else 'Turn on')
        set_kind(self.toggle, 'primary' if on and avail else 'secondary')
        self.toggle.setEnabled(avail > 0 and self.panel.online)


def _text_on(rgb):
    r, g, b = rgb
    return '#101820' if (0.299 * r + 0.587 * g + 0.114 * b) > 150 else '#FFFFFF'


class Chip(QPushButton):
    """Named colour chip. Colour is never the only signal: the name is always printed on it."""

    def __init__(self, name, rgb, callback):
        super().__init__(name); self.rgb = tuple(rgb); self.selected = False
        self.setMinimumHeight(HIT); self.setCursor(Qt.PointingHandCursor)
        self.clicked.connect(callback)
        self.restyle()

    def restyle(self):
        fg = _text_on(self.rgb)
        border = '#FFFFFF' if self.selected else 'transparent'
        self.setStyleSheet(
            'QPushButton{background:rgb(%d,%d,%d);color:%s;border:3px solid %s;border-radius:12px;font-weight:700;}'
            'QPushButton:disabled{background:#59657A;color:#A8B3C4;border:3px solid transparent;}' % (*self.rgb, fg, border))

    def set_selected(self, v):
        if self.selected != v:
            self.selected = v; self.restyle()


def kelvin_rgb(k):
    """Rough display colour for a Kelvin chip (preview only)."""
    return (255, 190, 120) if k < 3500 else ((255, 245, 235) if k < 5000 else (200, 225, 255))


class ColorEditor(QWidget):
    """The single in-band colour editor, reused for one light or a whole panel room."""

    def __init__(self, panel):
        super().__init__(); self.panel = panel; self.ids = []; self.choice = None; self.bri_touched = False; self.sent = False
        v = layout_v(self, (3, 2, 3, 3), 6)
        head = QHBoxLayout(); head.setSpacing(10)
        self.back = button('‹  Back', panel.close_color, 'secondary'); self.back.setFixedWidth(112)
        self.title = label('', 'heading', wrap=False)
        self.power = button('OFF', self.toggle_power, 'secondary'); self.power.setFixedWidth(84)
        head.addWidget(self.back); head.addWidget(self.title, 1); head.addWidget(self.power)
        v.addLayout(head)
        self.info = label('', 'small')
        v.addWidget(self.info)
        grid = QGridLayout(); grid.setHorizontalSpacing(8); grid.setVerticalSpacing(6)
        self.chips = []
        names = [(n, c, 'rgb') for n, c in C.SWATCHES] + [(n, kelvin_rgb(k), 'temp') for n, k in C.TEMPS]
        for i, (name, rgb, kind) in enumerate(names):
            val = tuple(rgb) if kind == 'rgb' else dict(C.TEMPS)[name]
            chip = Chip(name, rgb, lambda checked=False, n=name, k=kind, vv=val: self.pick(n, k, vv))
            chip.kind = kind; chip.value = val; chip.cname = name
            self.chips.append(chip)
            grid.addWidget(chip, i // 5, i % 5)
        for c in range(5):
            grid.setColumnStretch(c, 1)
        v.addLayout(grid)
        row = QHBoxLayout(); row.setSpacing(10)
        row.addWidget(label('Brightness', 'small', wrap=False))
        self.slider = QSlider(Qt.Horizontal); self.slider.setRange(1, 100); self.slider.setValue(100)
        self.slider.sliderPressed.connect(self._touch)
        row.addWidget(self.slider, 1)
        self.apply_btn = button('Apply', self.apply, 'primary'); self.apply_btn.setFixedWidth(130)
        row.addWidget(self.apply_btn)
        v.addLayout(row)
        v.addStretch(1)

    def _touch(self):
        self.bri_touched = True

    def open(self, ids, title):
        self.ids = list(dict.fromkeys(ids)); self.choice = None; self.bri_touched = False; self.sent = False
        self._title = title
        for c in self.chips:
            c.set_selected(False)
        self.slider.setValue(100)
        self.refresh()

    def caps(self):
        return [C.capabilities(self.panel.states.get(e)) for e in self.ids]

    def refresh(self):
        st = [self.panel.states.get(e) for e in self.ids]
        caps = self.caps(); n = len(self.ids)
        self.title.setText(self._title if n != 1 else friendly(st[0]) if st[0] else self._title)
        online = self.panel.online
        any_rgb = online and any(c['rgb'] for c in caps); any_temp = online and any(c['temp'] for c in caps)
        any_dim = online and any(c['dimmer'] and c['available'] for c in caps)
        for c in self.chips:
            c.setEnabled(any_rgb if c.kind == 'rgb' else any_temp)
        self.slider.setEnabled(any_dim)
        if n == 1 and st[0]:
            style_power(self.power, st[0], online)
        else:
            on = sum(1 for s in st if s and s.get('state') == 'on'); usable = [s for s in st if available(s)]
            self.power.setText('—' if not usable else ('ON' if on else 'OFF'))
            set_kind(self.power, 'primary' if on else 'secondary')
            self.power.setEnabled(bool(usable) and online)
        self.info.setText(self._info_text(caps, st, online))
        ok = self._eligible_count() if self.choice else 0
        self.apply_btn.setEnabled(online and ok > 0)

    def _eligible_count(self):
        if not self.choice:
            return 0
        kind, value, _ = self.choice
        ok, _s = C.eligible(self.panel.states, self.ids, (kind, value))
        return len(ok)

    def _info_text(self, caps, st, online):
        if not online:
            return 'Home is offline - colour changes are disabled until it reconnects.'
        n = len(self.ids)
        if n == 1:
            c = caps[0]
            if c['reason']:
                return c['reason']
            a = (st[0].get('attributes') or {})
            cur = []
            if st[0].get('state') == 'on':
                if a.get('color_mode') in ('color_temp',) and a.get('color_temp_kelvin'):
                    cur.append('%d K' % a['color_temp_kelvin'])
                elif a.get('rgb_color'):
                    cur.append('RGB %d,%d,%d' % tuple(a['rgb_color'][:3]))
                if a.get('brightness') is not None:
                    cur.append('%d%%' % round(a['brightness'] / 255 * 100))
            now = 'Now: ' + (' · '.join(cur) if cur else ('on' if st[0].get('state') == 'on' else 'off'))
            sel = f'  |  Selected: {self.choice[2]} (' + ('sent' if self.sent else 'not sent yet') + ')' if self.choice else '  |  Pick a colour, then Apply.'
            return now + sel
        colorable = sum(1 for c in caps if c['colorable'])
        if colorable == 0:
            return 'None of these lights support colour.'
        txt = f'{colorable} of {n} lights support colour; others are skipped.'
        if self.choice:
            txt = f'Selected: {self.choice[2]} (' + ('sent' if self.sent else 'not sent yet') + '). ' + f'{self._eligible_count()} of {n} lights will change.'
        return txt

    def pick(self, name, kind, value):
        self.choice = (kind, value, name); self.sent = False
        for c in self.chips:
            c.set_selected(c.cname == name)
        self.refresh()

    def toggle_power(self):
        st = [self.panel.states.get(e) for e in self.ids]
        ids = [e for e, s in zip(self.ids, st) if available(s)]
        if ids:
            on = any(s.get('state') == 'on' for s in st if available(s))
            self.panel.send_action('light', 'turn_off' if on else 'turn_on', ids, button=self.power)

    def apply(self):
        if not self.choice:
            return
        kind, value, name = self.choice
        bri = self.slider.value() if self.bri_touched else None
        self.panel.apply_colors(self.ids, (kind, value), bri, name, self.apply_btn)
        self.sent = True; self.refresh()


class ColorsView(QWidget):
    """Global colour target + presets using the existing HA helper and scripts (no panel-side colour state)."""

    def __init__(self, panel):
        super().__init__(); self.panel = panel; self.choice = None; self.mode = 'presets'; self.slot = None
        v = layout_v(self, (3, 2, 3, 3), 6)
        row = QHBoxLayout(); row.setSpacing(8)
        self.prev = button('‹', lambda: panel.cycle_target(-1), 'secondary'); self.prev.setFixedWidth(64)
        self.target = label('', 'rowTitle', wrap=False); self.target.setAlignment(Qt.AlignCenter)
        self.next = button('›', lambda: panel.cycle_target(1), 'secondary'); self.next.setFixedWidth(64)
        row.addWidget(label('Target', 'small', wrap=False)); row.addWidget(self.prev); row.addWidget(self.target, 1); row.addWidget(self.next)
        v.addLayout(row)
        self.note = label('Uses the Home Assistant colour helper. These targets are HA groups, not your panel layout.', 'small')
        v.addWidget(self.note)
        grid = QGridLayout(); grid.setHorizontalSpacing(6); grid.setVerticalSpacing(6)
        names = [(n, kelvin_rgb(k), 'temp', k) for n, k in C.TEMPS] + [(n, c, 'rgb', c) for n, c in C.SWATCHES[:6]]
        self.chips = []
        for i, (name, rgb, kind, val) in enumerate(names):
            chip = Chip(name, rgb, lambda checked=False, n=name, k=kind, vv=val: self.pick(n, k, vv))
            chip.cname = name; chip.kind = kind; chip.value = val; self.chips.append(chip)
            grid.addWidget(chip, 0, i)
        v.addLayout(grid)
        self.bottom = QHBoxLayout(); self.bottom.setSpacing(8)
        v.addLayout(self.bottom)
        self.status = label('', 'small')
        v.addWidget(self.status); v.addStretch(1)
        self.render_bottom()

    def clear_bottom(self):
        while self.bottom.count():
            it = self.bottom.takeAt(0)
            if it.widget():
                it.widget().deleteLater()

    def render_bottom(self, force=False):
        online = self.panel.online
        sig = (self.mode, self.slot, online, bool(self.choice), tuple(bool(self.panel.preset_value(n)) for n in (1, 2, 3, 4)))
        if sig == getattr(self, '_sig', None) and not force:
            return
        self._sig = sig
        self.clear_bottom()
        if self.mode == 'presets':
            self.apply_btn = button('Apply colour', self.apply, 'primary'); self.apply_btn.setEnabled(bool(self.choice) and online)
            self.bottom.addWidget(self.apply_btn, 2)
            for s in (1, 2, 3, 4):
                empty = not self.panel.preset_value(s)
                b = button(f'Preset {s}' + (' (empty)' if empty else ''), lambda checked=False, n=s: self.panel.apply_preset(n), 'secondary')
                b.setEnabled(online and not empty); self.bottom.addWidget(b, 2)
            self.bottom.addWidget(button('Save…', lambda: self.set_mode('pick'), 'secondary'), 1)
        elif self.mode == 'pick':
            self.bottom.addWidget(label('Save the target\'s current colour to:', 'small', wrap=False), 2)
            for s in (1, 2, 3, 4):
                self.bottom.addWidget(button(f'Slot {s}', lambda checked=False, n=s: self.ask_confirm(n), 'secondary'), 1)
            self.bottom.addWidget(button('Cancel', lambda: self.set_mode('presets'), 'secondary'), 1)
        else:
            self.bottom.addWidget(label(f'Overwrite preset {self.slot}?', 'rowTitle', wrap=False), 2)
            self.bottom.addWidget(button('Yes, save', self.do_save, 'primary'), 1)
            self.bottom.addWidget(button('Cancel', lambda: self.set_mode('presets'), 'secondary'), 1)

    def set_mode(self, mode, slot=None):
        self.mode = mode; self.slot = slot; self.render_bottom()

    def ask_confirm(self, slot):
        self.set_mode('confirm', slot)

    def do_save(self):
        self.panel.save_preset(self.slot); self.set_mode('presets')

    def pick(self, name, kind, value):
        self.choice = (kind, value, name)
        for c in self.chips:
            c.set_selected(c.cname == name)
        self.refresh()

    def apply(self):
        if self.choice:
            self.panel.apply_global_color(self.choice, self.apply_btn)

    def refresh(self):
        online = self.panel.online
        self.target.setText(self.panel.color_target() or 'No colour helper')
        for b in (self.prev, self.next):
            b.setEnabled(online and bool(self.panel.color_options()))
        for c in self.chips:
            c.setEnabled(online and bool(self.panel.config.get('colors')))
        self.render_bottom()
