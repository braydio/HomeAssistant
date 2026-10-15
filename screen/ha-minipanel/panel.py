#!/usr/bin/env python3
"""7-inch Home Assistant touchscreen panel using native Qt Widgets, not Chromium.

Run: python3 panel.py --demo --windowed
For actual devices: configure config.json and use python3 panel.py --fullscreen
"""
import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from PyQt5.QtCore import Qt, QTimer, QSize, QObject, QRunnable, QThreadPool, pyqtSignal
from PyQt5.QtGui import QPixmap, QFont
from PyQt5.QtWidgets import (QScroller, QApplication, QFrame, QWidget, QLabel, QMainWindow, QPushButton,
    QVBoxLayout, QHBoxLayout, QGridLayout, QStackedWidget, QScrollArea, QSlider,
    QSizePolicy, QButtonGroup)

from ha_client import HAClient, HomeAssistantError

ROOT = Path(__file__).resolve().parent
COMPACT = False  # set from config touch_band; shrinks the UI to fit a short band
COMPACT_CSS = '''
        QLabel[role="infoClock"] { font-size: 44px; font-weight: 700; }
        QLabel[role="hero"] { font-size: 26px; }
        QLabel[role="heading"] { font-size: 21px; }
        QPushButton { padding: 2px 12px; }
'''
PREFS = Path.home() / '.config' / 'ha-minipanel' / 'preferences.json'

PALETTES = {
    'dark': {'bg':'#0D121B','card':'#182333','card2':'#202D41','text':'#F5F8FC','muted':'#98AABD','accent':'#75A9FF','border':'#29374A'},
    'light': {'bg':'#F5F7FB','card':'#FFFFFF','card2':'#EAF0F8','text':'#142238','muted':'#62748A','accent':'#2563EB','border':'#DFE7F0'}
}


def label(text='', role='', size=None):
    w = QLabel(text)
    if role:
        w.setProperty('role', role)
    if size:
        font = w.font(); font.setPointSize(size); w.setFont(font)
    w.setWordWrap(True)
    return w


def card():
    w = QFrame(); w.setObjectName('Card'); return w


def layout_v(widget=None, margins=(0,0,0,0), gap=12):
    v = QVBoxLayout(widget) if widget else QVBoxLayout()
    v.setContentsMargins(*margins); v.setSpacing(gap); return v


def button(text, callback, kind='secondary'):
    b = QPushButton(text); b.setProperty('kind', kind); b.setCursor(Qt.PointingHandCursor)
    b.setMinimumHeight(38 if COMPACT else 48); b.clicked.connect(callback); return b


def friendly(s):
    return s.get('attributes',{}).get('friendly_name') or s['entity_id'].split('.',1)[-1].replace('_',' ').title()


def dimmable(s):
    attrs = s.get('attributes', {})
    modes = attrs.get('supported_color_modes', []) or []
    return ('brightness' in attrs or any(m not in ('onoff','unknown') for m in modes))


class JobSignals(QObject):
    done = pyqtSignal(object)
    error = pyqtSignal(str)


class Job(QRunnable):
    def __init__(self, fn):
        super().__init__(); self.fn=fn; self.signals=JobSignals()
    def run(self):
        try: self.signals.done.emit(self.fn())
        except Exception as e: self.signals.error.emit(str(e))


class LightRow(QFrame):
    def __init__(self, entity, parent_panel, on_open=None):
        super().__init__(); self.setObjectName('LightRow')
        self.panel=parent_panel; self.entity=entity; self.on_open=on_open; self.openable=False; self._press=None
        h=QHBoxLayout(self); h.setContentsMargins(*((14,3,14,3) if COMPACT else (14,8,14,8))); h.setSpacing(10)
        names=QVBoxLayout(); names.setSpacing(3)
        self.title=label(friendly(entity),'rowTitle'); self.meta=label('','small')
        names.addWidget(self.title); names.addWidget(self.meta)
        h.addLayout(names,2)
        self.slider=QSlider(Qt.Horizontal)
        self.slider.setRange(1,100); self.slider.setSingleStep(5)
        self.slider.setMinimumWidth(105)
        self.slider.sliderReleased.connect(self.change_brightness)
        h.addWidget(self.slider,3)
        self.toggle=button('On', self.toggle_light, 'primary')
        self.toggle.setMinimumWidth(78); self.toggle.setMaximumWidth(105)
        h.addWidget(self.toggle)
        self.update_entity(entity)

    def update_entity(self, entity):
        self.entity=entity; attrs=entity.get('attributes',{})
        on = entity.get('state')=='on'
        available = entity.get('state') not in ('unavailable','unknown')
        members=attrs.get('entity_id')
        self.openable=bool(self.on_open) and isinstance(members,list) and len(members)>0
        self.title.setText(friendly(entity)+('  \u203a' if self.openable else ''))
        bri_now=attrs.get('brightness')
        if not available: self.meta.setText('Unavailable')
        elif on and bri_now is not None and dimmable(entity): self.meta.setText('On \u00b7 %d%%'%round(bri_now/255*100))
        else: self.meta.setText('On' if on else 'Off')
        # the button shows the current STATE (blue = on); tapping it flips the state
        self.toggle.setText('\u2014' if not available else ('ON' if on else 'OFF'))
        self.toggle.setProperty('kind','primary' if (on and available) else 'secondary')
        self.toggle.style().unpolish(self.toggle); self.toggle.style().polish(self.toggle)
        self.toggle.setEnabled(available)
        supported=dimmable(entity)
        self.slider.setVisible(supported)
        self.slider.setEnabled(on and available and supported)
        if not self.slider.isSliderDown():
            bri=attrs.get('brightness')
            if bri is not None: self.slider.setValue(max(1,round(bri/255*100)))

    def mousePressEvent(self,e):
        self._press=e.pos(); super().mousePressEvent(e)

    def mouseReleaseEvent(self,e):
        super().mouseReleaseEvent(e)
        # a tap (not a drag) on the name area opens the room; buttons/sliders handle their own taps
        if self.openable and self._press is not None and (e.pos()-self._press).manhattanLength()<14:
            self.on_open(self.entity['entity_id'])
        self._press=None

    def toggle_light(self):
        action = 'turn_off' if self.entity.get('state')=='on' else 'turn_on'
        self.panel.send_action('light',action,self.entity['entity_id'])

    def change_brightness(self):
        self.panel.send_action('light','turn_on',self.entity['entity_id'], brightness_pct=self.slider.value())


class Panel(QMainWindow):
    def __init__(self, config, demo=False, fullscreen=True):
        super().__init__()
        self.config=config; self.client=HAClient(config,demo)
        self.demo=demo; self.states={}; self.rows={}; self.inflight=set(); self.preview_image=None
        self.pool=QThreadPool.globalInstance(); self.pool.setMaxThreadCount(2)
        self.override=self.load_preferences().get('theme','auto')
        self.current_theme='dark'
        self.page_index=0; self.active_camera=None; self.last_error=''
        self.setWindowTitle('Home Panel | Native Qt')
        # Some digitizers only report touches in a middle band of the screen (QDtech MPI7002: ~Y 107-449 of 600).
        # touch_band=[top,bottom] confines the whole UI to that band so every control is reachable.
        band=config.get('touch_band'); self.compact=bool(band)
        self.band=(int(band[0]),int(band[1])) if band else None
        self.resize(1024,600)
        self.build_ui()
        self.set_theme('dark')
        self.clock_update()
        self.poll()
        self.poll_timer=QTimer(self)
        self.poll_timer.timeout.connect(self.poll)
        self.poll_timer.start(max(5,int(config.get('poll_seconds',12)))*1000)
        self.camera_timer=QTimer(self)
        self.camera_timer.timeout.connect(self.poll_camera)
        self.camera_timer.start(max(5,int(config.get('snapshot_seconds',12)))*1000)
        self.clock_timer=QTimer(self); self.clock_timer.timeout.connect(self.clock_update)
        self.clock_timer.start(10000)
        if fullscreen: self.showFullScreen()
        else: self.show()

    def load_preferences(self):
        try: return json.loads(PREFS.read_text())
        except (FileNotFoundError, ValueError, OSError): return {}

    def save_preferences(self):
        PREFS.parent.mkdir(parents=True, exist_ok=True)
        PREFS.write_text(json.dumps({'theme':self.override}))
        PREFS.chmod(0o600)

    def build_ui(self):
        root=QWidget(); root.setObjectName('Root'); self.setCentralWidget(root)
        self.top_greeting=QLabel(); self.top_summary=QLabel(); self.date_label=QLabel()
        self.bottom_status=QLabel(); self.bottom_detail=QLabel()
        if self.band:
            # Dead touch zones (above/below the band) carry information only; every control sits in the band.
            top,bot=self.band
            page=layout_v(root,(0,0,0,0),0)
            topw=QWidget(); topw.setFixedHeight(top); tl=QHBoxLayout(topw); tl.setContentsMargins(24,8,24,8)
            left=QVBoxLayout(); left.setSpacing(0)
            self.clock=label('00:00','infoClock'); self.date_label=label('','small')
            left.addStretch(1); left.addWidget(self.clock); left.addWidget(self.date_label); left.addStretch(1)
            centre=QVBoxLayout(); centre.setSpacing(2)
            self.top_greeting=label('','heading'); self.top_summary=label('Checking lights…','rowTitle')
            centre.addStretch(1); centre.addWidget(self.top_greeting); centre.addWidget(self.top_summary); centre.addStretch(1)
            right=QVBoxLayout(); right.setSpacing(2)
            self.theme_status=label('AUTO','small')
            right.addStretch(1); right.addWidget(label('HOME PANEL','overline')); right.addWidget(self.theme_status); right.addStretch(1)
            tl.addLayout(left,2); tl.addLayout(centre,3); tl.addLayout(right,1)
            mid=QWidget(); mid.setFixedHeight(bot-top)
            outer=layout_v(mid,(18,4,18,4),5)
            botw=QWidget(); botw.setFixedHeight(600-bot); bl=QVBoxLayout(botw); bl.setContentsMargins(24,10,24,10); bl.setSpacing(3)
            self.bottom_status=label('Connecting…','rowTitle'); self.bottom_detail=label('','small')
            bl.addStretch(1); bl.addWidget(self.bottom_status); bl.addWidget(self.bottom_detail); bl.addStretch(1)
            page.addWidget(topw); page.addWidget(mid); page.addWidget(botw)
        else:
            outer=layout_v(root,(18,12,18,12),9)
            bar=QHBoxLayout(); bar.setSpacing(12)
            self.clock=label('00:00','clock'); bar.addWidget(self.clock)
            bar.addStretch(1); bar.addWidget(label('HOME PANEL','overline'))
            bar.addStretch(1); self.theme_status=label('AUTO','small'); bar.addWidget(self.theme_status)
            outer.addLayout(bar)
        self.stack=QStackedWidget(); outer.addWidget(self.stack,1)
        self.make_home(); self.make_lights(); self.make_cameras(); self.make_settings()
        navbar=QFrame(); navbar.setObjectName('Nav'); nav=QHBoxLayout(navbar)
        nav.setContentsMargins(5,4,5,4); nav.setSpacing(6)
        self.nav_buttons=[]
        for idx, name in enumerate(('Home','Lights','Cameras','Settings')):
            b=button(name,lambda checked=False,n=idx:self.switch_page(n),'nav')
            b.setMinimumHeight(36 if COMPACT else 46); nav.addWidget(b,1); self.nav_buttons.append(b)
        outer.addWidget(navbar)
        self.update_nav()

    def section_head(self, title, subtitle):
        col=QVBoxLayout(); col.setSpacing(2)
        col.addWidget(label(title,'heading'))
        if not COMPACT: col.addWidget(label(subtitle,'small'))
        return col

    def make_home(self):
        page=QWidget(); body=layout_v(page,(3,2,3,3),12)
        self.home_header=label('Good evening','heading'); body.addWidget(self.home_header)
        self.home_subtitle=label('Your home, one touch away.','small'); body.addWidget(self.home_subtitle)
        if self.compact: self.home_subtitle.setVisible(False); self.home_header.setVisible(False)
        content=QHBoxLayout(); content.setSpacing(12)
        lighting=card(); vl=layout_v(lighting,((14,7,14,7) if COMPACT else (18,17,18,17)),12)
        vl.addWidget(label('LIGHTING','overline')); self.home_light_count=label('Checking lights…','hero')
        vl.addWidget(self.home_light_count)
        vl.addWidget(label('Simple controls, without a browser.','small'))
        vl.addStretch(1)
        h=QHBoxLayout()
        h.addWidget(button('Rooms  →',lambda:self.switch_page(1),'primary'),1)
        h.addWidget(button('All off',self.all_lights_off),1)
        vl.addLayout(h); content.addWidget(lighting,3)
        actions=card(); ar=layout_v(actions,((14,7,14,7) if COMPACT else (18,17,18,17)),10)
        ar.addWidget(label('QUICK SCENES','overline'))
        self.scene_holder=QVBoxLayout(); self.scene_holder.setSpacing(7)
        ar.addLayout(self.scene_holder); ar.addStretch(1)
        ar.addWidget(button('View cameras  →',lambda:self.switch_page(2)))
        content.addWidget(actions,2)
        body.addLayout(content,1); self.stack.addWidget(page)

    def make_scroll(self):
        scroll=QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame); scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        QScroller.grabGesture(scroll.viewport(), QScroller.LeftMouseButtonGesture)  # drag-to-scroll with a finger
        holder=QWidget(); holder.setObjectName('holder'); holder.setStyleSheet('#holder { background: transparent; }')
        scroll.viewport().setObjectName('vp'); scroll.viewport().setStyleSheet('#vp { background: transparent; }')
        lay=layout_v(holder,(0,0,0,0),8); lay.addStretch(1); scroll.setWidget(holder)
        return scroll,lay

    def make_lights(self):
        page=QWidget(); pv=layout_v(page,(0,0,0,0),0)
        self.lights_views=QStackedWidget(); pv.addWidget(self.lights_views)
        rooms=QWidget(); v=layout_v(rooms,(3,2,3,3),8)
        v.addLayout(self.section_head('Lights','Tap a room name to see its lights. Slide to dim.'))
        scroll,self.light_layout=self.make_scroll(); v.addWidget(scroll,1)
        self.lights_views.addWidget(rooms)
        room=QWidget(); rv=layout_v(room,(3,2,3,3),8)
        head=QHBoxLayout(); head.setSpacing(10)
        self.room_back=button('\u2039  Rooms',self.close_room,'secondary'); self.room_back.setMinimumWidth(110)
        self.room_title=label('','heading')
        self.room_toggle=button('OFF',self.toggle_room,'secondary')
        self.room_toggle.setMinimumWidth(78); self.room_toggle.setMaximumWidth(105)
        head.addWidget(self.room_back); head.addWidget(self.room_title,1); head.addWidget(self.room_toggle)
        rv.addLayout(head)
        rscroll,self.room_layout=self.make_scroll(); rv.addWidget(rscroll,1)
        self.lights_views.addWidget(room)
        self.room_rows={}; self.current_room=None
        self.stack.addWidget(page)

    def make_cameras(self):
        page=QWidget(); v=layout_v(page,(3,2,3,3),8)
        v.addLayout(self.section_head('Cameras','One preview at a time to save memory.'))
        self.camera_choice=QHBoxLayout(); self.camera_choice.setSpacing(8); v.addLayout(self.camera_choice)
        view=card(); inner=layout_v(view,(12,12,12,12),6)
        self.camera_view=label('Select a camera to load a snapshot.','cameraPlaceholder')
        self.camera_view.setAlignment(Qt.AlignCenter)
        self.camera_view.setMinimumHeight(180)
        self.camera_view.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding)
        inner.addWidget(self.camera_view,1)
        self.camera_stamp=label('Snapshots refresh only on this page.','small')
        inner.addWidget(self.camera_stamp)
        v.addWidget(view,1); self.stack.addWidget(page)

    def make_settings(self):
        page=QWidget(); v=layout_v(page,(3,2,3,3),12)
        v.addLayout(self.section_head('Settings','Display and connection'))
        block=card(); inner=layout_v(block,(18,12,18,12),9)
        inner.addWidget(label('APPEARANCE','overline'))
        choices=QHBoxLayout(); choices.setSpacing(9); self.theme_buttons={}
        for theme in ('auto','light','dark'):
            b=button(theme.title(),lambda checked=False,t=theme:self.set_override(t),'secondary')
            choices.addWidget(b); self.theme_buttons[theme]=b
        inner.addLayout(choices)
        inner.addWidget(label('Auto follows Home Assistant sun.sun; uses local clock when unavailable.','small'))
        v.addWidget(block)
        status=card(); st=layout_v(status,(18,12,18,12),10)
        st.addWidget(label('CONNECTION','overline'))
        self.connection=label('Connecting…','rowTitle'); st.addWidget(self.connection)
        st.addWidget(label(self.client.url if not self.demo else 'Offline demo data','small'))
        self.system_details=label('Pi Zero 2 W · Native Qt client · No Chromium','small')
        st.addWidget(self.system_details); v.addWidget(status)
        v.addStretch(1); self.stack.addWidget(page)
        self.update_theme_buttons()

    def update_nav(self):
        for i,b in enumerate(self.nav_buttons):
            b.setProperty('active',str(i==self.page_index).lower())
            b.style().unpolish(b); b.style().polish(b)

    def switch_page(self, i):
        self.page_index=i; self.stack.setCurrentIndex(i); self.update_nav()
        if i==1: self.close_room()  # tapping Lights always starts at the room list
        if i==2: self.poll_camera()

    def dispatch(self,key,fn,done,onerror=None):
        if key in self.inflight: return
        self.inflight.add(key)
        job=Job(fn)
        def ok(value):
            self.inflight.discard(key); done(value)
        def fail(err):
            self.inflight.discard(key)
            if onerror: onerror(err)
            else: self.report_error(err)
        job.signals.done.connect(ok); job.signals.error.connect(fail)
        self.pool.start(job)

    def poll(self):
        self.dispatch('states',self.client.states,self.update_states, self.connection_error)

    def connection_error(self,err):
        self.connection.setText('Offline / connection error')
        self.last_error=err
        self.home_subtitle.setText('Cannot reach Home Assistant. Check connection.')
        self.home_light_count.setText('Home is offline')
        self.top_summary.setText('Home is offline')
        self.bottom_status.setText('\u25cb Home is offline')
        self.bottom_detail.setText(f'{self.client.url}  \u00b7  retrying every {int(self.config.get("poll_seconds",12))} s')

    def report_error(self,err):
        self.last_error=err; self.camera_stamp.setText('Request failed: '+err[:105])

    def get_entities(self,domain,key,auto_key):
        requested=self.config.get(key,[])
        # Explicit lists take precedence; otherwise safely discover entities for review.
        if requested:
            return [self.states[e] for e in requested if e in self.states]
        if not self.config.get(auto_key,True): return []
        return sorted([s for s in self.states.values() if s['entity_id'].startswith(domain+'.')],key=friendly)

    def update_states(self,states):
        self.states={s['entity_id']:s for s in states}
        self.last_error=''
        self.connection.setText('Connected to Home Assistant' if not self.demo else 'Demo mode')
        lights=self.get_entities('light','lights','auto_discover_lights')
        on=sum(s.get('state')=='on' for s in lights)
        self.home_light_count.setText(f'{on} / {len(lights)} on')
        self.top_summary.setText(f'{on} of {len(lights)} lights on')
        self.bottom_status.setText('\u25cf Connected to Home Assistant' if not self.demo else '\u25cf Demo mode')
        self.bottom_detail.setText(f'{self.client.url if not self.demo else "offline demo data"}  \u00b7  updated {datetime.now():%-I:%M:%S %p}')
        self.home_subtitle.setText('All systems ready.' if not self.demo else 'Demo mode · No real devices controlled')
        self.populate_lights(lights)
        self.refresh_room()
        scenes=self.get_entities('scene','scenes','auto_discover_scenes')
        self.populate_scenes(scenes)
        cameras=self.get_entities('camera','cameras','auto_discover_cameras')
        self.populate_cameras(cameras)
        self.apply_auto_theme()

    def fill_rows(self,layout,rows,entities,on_open,empty):
        ids=[s['entity_id'] for s in entities]
        if list(rows)!=ids:
            # remove widgets and their layout entries (also removes the previous spacer)
            while layout.count():
                item=layout.takeAt(0)
                if item.widget(): item.widget().deleteLater()
            rows.clear()
            for s in entities:
                row=LightRow(s,self,on_open); rows[s['entity_id']]=row
                layout.addWidget(row)
            if not entities: layout.addWidget(label(empty,'small'))
            layout.addStretch(1)
        else:
            for s in entities: rows[s['entity_id']].update_entity(s)

    def populate_lights(self,lights):
        self.fill_rows(self.light_layout,self.rows,lights,self.open_room,'No light entities found. Configure them in config.json.')

    def open_room(self,entity_id):
        self.current_room=entity_id; self.lights_views.setCurrentIndex(1); self.refresh_room()

    def close_room(self):
        self.current_room=None; self.lights_views.setCurrentIndex(0)

    def toggle_room(self):
        room=self.states.get(self.current_room) if self.current_room else None
        if room: self.send_action('light','turn_off' if room.get('state')=='on' else 'turn_on',self.current_room)

    def refresh_room(self):
        if not self.current_room: return
        room=self.states.get(self.current_room)
        if not room: self.close_room(); return
        on=room.get('state')=='on'; available=room.get('state') not in ('unavailable','unknown')
        self.room_title.setText(friendly(room))
        self.room_toggle.setText('\u2014' if not available else ('ON' if on else 'OFF'))
        self.room_toggle.setProperty('kind','primary' if (on and available) else 'secondary')
        self.room_toggle.style().unpolish(self.room_toggle); self.room_toggle.style().polish(self.room_toggle)
        self.room_toggle.setEnabled(available)
        ids=room.get('attributes',{}).get('entity_id') or []
        members=sorted([self.states[i] for i in ids if i in self.states and i.startswith('light.')],key=friendly)
        self.fill_rows(self.room_layout,self.room_rows,members,None,'No individual lights found in this room.')

    def populate_scenes(self,scenes):
        chosen=[s for s in scenes if s['entity_id'].startswith('scene.')][:3]
        signature=tuple(s['entity_id'] for s in chosen)
        if getattr(self,'scene_signature',None)==signature: return
        self.scene_signature=signature
        while self.scene_holder.count():
            item=self.scene_holder.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        if not chosen:
            self.scene_holder.addWidget(label('No scenes yet. Create them in Home Assistant.','small'))
        for s in chosen:
            self.scene_holder.addWidget(button(friendly(s),lambda checked=False,e=s['entity_id']:self.send_action('scene','turn_on',e)))

    def populate_cameras(self,cameras):
        signature=tuple(s['entity_id'] for s in cameras)
        if getattr(self,'camera_signature',None)!=signature:
            self.camera_signature=signature
            while self.camera_choice.count():
                item=self.camera_choice.takeAt(0)
                if item.widget(): item.widget().deleteLater()
            if not cameras: self.camera_choice.addWidget(label('No camera entities configured.','small'))
            for s in cameras[:5]:
                self.camera_choice.addWidget(button(friendly(s),lambda checked=False,e=s['entity_id']:self.select_camera(e)))
            if self.active_camera not in signature:
                self.active_camera=signature[0] if signature else None
                self.preview_image=None
        if self.page_index==2 and self.active_camera and self.preview_image is None:
            self.poll_camera()

    def select_camera(self,eid):
        self.active_camera=eid; self.preview_image=None
        self.camera_view.setText('Loading snapshot…'); self.poll_camera()

    def poll_camera(self):
        if self.page_index!=2 or not self.active_camera: return
        eid=self.active_camera
        self.dispatch('camera',lambda:self.client.camera_snapshot(eid),
                      lambda data:self.camera_ready(eid,data),
                      lambda e:self.camera_stamp.setText('Snapshot unavailable: '+e[:105]))

    def camera_ready(self,eid,data):
        if eid!=self.active_camera:return
        if not data:
            self.camera_view.setText('Camera snapshot placeholder (demo mode)')
            return
        pix=QPixmap()
        if not pix.loadFromData(data):
            self.camera_stamp.setText('Invalid camera snapshot format'); return
        self.preview_image=pix; self.display_preview()
        self.camera_stamp.setText(f'{eid} · Snapshot {datetime.now():%-I:%M:%S %p} · Not live video')

    def display_preview(self):
        if self.preview_image is not None:
            self.camera_view.setPixmap(self.preview_image.scaled(self.camera_view.size(),Qt.KeepAspectRatio,Qt.SmoothTransformation))

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'camera_view'): self.display_preview()

    def all_lights_off(self):
        lights=self.get_entities('light','lights','auto_discover_lights')
        ids=[s['entity_id'] for s in lights if s.get('state')=='on']
        if ids: self.send_action('light','turn_off',ids)

    def send_action(self,domain,action,entity_ids,**kwargs):
        key='action:'+str(time.monotonic_ns())
        self.dispatch(key, lambda:self.client.service(domain,action,entity_ids,**kwargs),
                      lambda _:QTimer.singleShot(300,self.poll),
                      lambda e:self.connection.setText('Action failed: '+e[:85]))

    def clock_update(self):
        now=datetime.now()
        self.clock.setText(now.strftime('%-I:%M %p'))
        h=now.hour
        if hasattr(self,'home_header'):
            greet='Good morning' if 5<=h<12 else ('Good afternoon' if 12<=h<18 else 'Good evening')
            self.home_header.setText(greet); self.top_greeting.setText(greet)
        self.date_label.setText(now.strftime('%A, %B %d'))
        self.apply_auto_theme()

    def set_override(self,theme):
        self.override=theme; self.save_preferences(); self.apply_auto_theme()

    def update_theme_buttons(self):
        if not hasattr(self,'theme_buttons'):return
        for name,b in self.theme_buttons.items():
            b.setProperty('kind','primary' if name==self.override else 'secondary')
            b.style().unpolish(b); b.style().polish(b)

    def apply_auto_theme(self):
        if self.override in ('light','dark'): theme=self.override
        else:
            sun=self.states.get('sun.sun',{}).get('state')
            theme='light' if sun=='above_horizon' else ('dark' if sun=='below_horizon' else ('light' if 7<=datetime.now().hour<19 else 'dark'))
        self.theme_status.setText('AUTO '+theme.upper() if self.override=='auto' else theme.upper())
        if theme!=self.current_theme:self.set_theme(theme)
        self.update_theme_buttons()

    def set_theme(self,theme):
        self.current_theme=theme;p=PALETTES[theme]
        # QSS uses static styles; no animation or shader-heavy effects.
        self.setStyleSheet('''
        QWidget#Root { background: %(bg)s; color: %(text)s; }
        QWidget { color: %(text)s; font-family: 'DejaVu Sans', sans-serif; font-size: 14px; }
        QLabel[role="heading"] { font-size: 27px; font-weight: 700; }
        QLabel[role="hero"] { font-size: 38px; font-weight: 700; }
        QLabel[role="rowTitle"] { font-size: 17px; font-weight: 600; }
        QLabel[role="clock"] { font-size: 19px; font-weight: 700; }
        QLabel[role="overline"] { font-size: 11px; font-weight: 700; color: %(muted)s; }
        QLabel[role="small"] { font-size: 12px; color: %(muted)s; }
        QLabel[role="cameraPlaceholder"] { font-size: 15px; color: %(muted)s; }
        QFrame#Card, QFrame#Nav, QFrame#LightRow { background: %(card)s; border: 1px solid %(border)s; border-radius: 16px; }
        QFrame#LightRow { border-radius: 12px; }
        QPushButton { border: 0; border-radius: 12px; background: %(card2)s; color: %(text)s; padding: 6px 15px; font-size: 14px; font-weight: 600; }
        QPushButton[kind="primary"] { background: %(accent)s; color: %(bg)s; }
        QPushButton[active="true"] { background: %(accent)s; color: %(bg)s; }
        QPushButton:disabled { color: %(muted)s; }
        QSlider::groove:horizontal { background: %(border)s; height: 8px; border-radius: 4px; }
        QSlider::sub-page:horizontal { background: %(accent)s; border-radius: 4px; }
        QSlider::handle:horizontal { background: %(text)s; width: 22px; margin: -7px 0; border-radius: 11px; }
        QScrollArea { background: transparent; border: none; }
        QScrollBar:vertical { background: %(bg)s; width: 9px; }
        QScrollBar::handle:vertical { background: %(border)s; border-radius: 4px; min-height: 25px; }
        ''' % p + (COMPACT_CSS if COMPACT else ''))
        # Qt does not always re-polish existing children after a runtime stylesheet swap
        self._repolish()
        QTimer.singleShot(250,self._repolish)  # again once the window is shown (startup case)

    def _repolish(self):
        for w in self.findChildren(QWidget):
            w.style().unpolish(w); w.style().polish(w)
        self.update()


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--demo',action='store_true',help='Offline demo data; no API requests')
    ap.add_argument('--windowed',action='store_true',help='Do not launch fullscreen')
    ap.add_argument('--config',default=str(ROOT/'config.json'))
    args=ap.parse_args()
    config_path=Path(args.config)
    if config_path.exists(): config=json.loads(config_path.read_text(encoding='utf-8'))
    elif args.demo: config=json.loads((ROOT/'config.example.json').read_text(encoding='utf-8'))
    else:
        print(f'Configuration missing: {config_path}. Copy config.example.json to config.json first.',file=sys.stderr)
        sys.exit(2)
    def _hook(t,v,tb):
        import traceback; traceback.print_exception(t,v,tb)
    sys.excepthook=_hook  # PyQt5 aborts on uncaught slot exceptions; log them instead
    global COMPACT
    COMPACT=bool(config.get('touch_band'))
    app=QApplication(sys.argv[:1])
    app.setStyle('Fusion')
    try: panel=Panel(config,demo=args.demo,fullscreen=not args.windowed)
    except HomeAssistantError as e:
        print('Configuration error:',e,file=sys.stderr);sys.exit(2)
    sys.exit(app.exec_())


if __name__=='__main__': main()
