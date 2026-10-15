"""Qt offscreen tests: touch-band geometry on every view, edit-layout flow, room targeting, colour editor.
Skipped automatically when PyQt5 is unavailable."""
import json
import os
import tempfile
import time
import unittest
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
try:
    from PyQt5.QtCore import QPoint, QRect
    from PyQt5.QtWidgets import QApplication, QPushButton, QSlider
    import panel as P
    from views import RoomRow, LightRow
    HAVE_QT = True
except ImportError:  # pragma: no cover
    HAVE_QT = False

BAND = (112, 442); SAFE_TOP, SAFE_BOT = BAND[0] + 8, BAND[1] - 8
ROOT = Path(__file__).resolve().parent


def pump(app, n=10):
    from PyQt5.QtCore import QCoreApplication, QEvent
    for _ in range(n):
        app.processEvents(); QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete); time.sleep(0.02)


def clipped(w, win):
    r = QRect(w.mapTo(win, QPoint(0, 0)), w.size()); p = w.parentWidget()
    while p is not None and p is not win:
        r = r.intersected(QRect(p.mapTo(win, QPoint(0, 0)), p.size())); p = p.parentWidget()
    return r


@unittest.skipUnless(HAVE_QT, 'PyQt5 not installed')
class UITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle('Fusion')

    def make(self, tmp=None, band=BAND):
        tmp = tmp or tempfile.mkdtemp()
        cfg = json.loads((ROOT / 'config.example.json').read_text())
        cfg['prefs_file'] = tmp + '/p.json'; cfg['layout_file'] = tmp + '/cfg/l.json'; cfg['touch_band'] = list(band) if band else None
        p = P.Panel(cfg, demo=True, fullscreen=False)
        pump(self.app, 15)
        self.addCleanup(p.close)
        return p, tmp

    def assert_in_band(self, p, where):
        interactive = [w for w in p.findChildren(QPushButton) + p.findChildren(QSlider) + p.findChildren(RoomRow)
                       if w.isVisibleTo(p)]
        self.assertTrue(interactive, where)
        for w in interactive:
            r = clipped(w, p)
            if r.isEmpty(): continue
            self.assertGreaterEqual(r.top(), SAFE_TOP, f'{where}: {type(w).__name__} {getattr(w, "text", lambda: "")()} top {r.top()}')
            self.assertLessEqual(r.bottom() + 1, SAFE_BOT + 1, f'{where}: {type(w).__name__} bottom {r.bottom()}')

    def test_every_view_inside_touch_band(self):
        p, _ = self.make()
        self.assert_in_band(p, 'home')
        p.switch_page(P.PAGE_LIGHTS); pump(self.app); self.assert_in_band(p, 'rooms')
        p.open_room('kitchen'); pump(self.app); self.assert_in_band(p, 'room')
        p.open_color(['light.kitchen_left']); pump(self.app); self.assert_in_band(p, 'color editor')
        p.close_color(); p.close_room(); p.show_view(P.V_COLORS); pump(self.app); self.assert_in_band(p, 'colors')
        p.colors_view.set_mode('pick'); pump(self.app); self.assert_in_band(p, 'save pick')
        p.colors_view.set_mode('confirm', 2); pump(self.app); self.assert_in_band(p, 'save confirm')
        p.colors_view.set_mode('presets'); p.show_view(P.V_ROOMS)
        p.start_edit(); pump(self.app); self.assert_in_band(p, 'edit rooms')
        p.ask_reset(); pump(self.app); self.assert_in_band(p, 'reset confirm'); p.cancel_reset()
        p.edit_room('kitchen'); pump(self.app); self.assert_in_band(p, 'edit room')
        p.pick_destination('light.kitchen_left'); pump(self.app); self.assert_in_band(p, 'move picker')
        p.cancel_move(); p.cancel_edit()
        p.switch_page(P.PAGE_CAMERAS); pump(self.app); self.assert_in_band(p, 'cameras')
        p.switch_page(P.PAGE_SETTINGS); pump(self.app); self.assert_in_band(p, 'settings')

    def test_header_and_footer_are_display_only(self):
        p, _ = self.make()
        from PyQt5.QtWidgets import QPushButton
        for b in p.findChildren(QPushButton):
            if b.isVisibleTo(p):
                y = b.mapTo(p, QPoint(0, 0)).y()
                self.assertTrue(BAND[0] <= y and y + b.height() <= BAND[1], 'button outside band')

    def test_no_band_still_lays_out(self):
        p, _ = self.make(band=None)
        self.assertEqual((p.top, p.bot), (84, 530))

    def test_three_primary_tabs_and_settings_from_home(self):
        p, _ = self.make()
        self.assertEqual([b.text() for b in p.nav_buttons], ['Home', 'Lights', 'Cameras'])
        self.assertTrue(any(b.text() == 'Settings' for b in p.findChildren(QPushButton)))

    def test_edit_cancel_then_done_persist_and_relaunch(self):
        p, tmp = self.make()
        before = json.loads(json.dumps(p.layout.data))
        p.start_edit(); p.edit_room('kitchen'); p.pick_destination('light.kitchen_left'); p.do_move('living_room')
        p.move_room('bathroom', 0); p.cancel_edit()
        self.assertEqual(p.layout.data, before); self.assertFalse(Path(tmp, 'cfg', 'l.json').exists())
        p.start_edit(); p.edit_room('kitchen'); p.pick_destination('light.kitchen_left'); p.do_move('living_room')
        p.edit_room_id = 'living_room'; p.move_light_in_room('light.kitchen_left', 0)
        p.edit_back(); p.move_room('bathroom', 0); p.finish_edit(); pump(self.app)
        self.assertFalse(p.editing); self.assertEqual(p.layout.room_of('light.kitchen_left'), 'living_room')
        p2, _ = self.make(tmp)
        self.assertEqual(p2.layout.room_of('light.kitchen_left'), 'living_room')
        self.assertEqual(p2.layout.rooms()[0]['id'], 'bathroom')

    def test_room_toggle_targets_only_current_panel_members(self):
        p, _ = self.make()
        p.layout.move_light('light.kitchen_right', 'living_room'); p.layout.saved = json.loads(json.dumps(p.layout.data))
        p.client.demo_calls.clear(); p.toggle_room('living_room'); pump(self.app, 20)
        d, a, ids, _ = p.client.demo_calls[-1]
        self.assertIn('light.kitchen_right', ids); self.assertNotIn('light.kitchen_lights', ids)
        self.assertNotIn('light.living_room_lights', ids)
        self.assertTrue(all(i != 'light.kitchen_left' for i in ids))

    def test_all_off_targets_individual_panel_lights_only(self):
        p, _ = self.make(); p.client.demo_calls.clear(); p.all_lights_off(); pump(self.app, 20)
        d, a, ids, _ = p.client.demo_calls[-1]
        self.assertEqual((d, a), ('light', 'turn_off'))
        self.assertTrue(set(ids) <= set(p.layout.all_lights()))
        self.assertFalse(any(i.endswith('_lights') for i in ids))

    def test_colour_preview_sends_nothing_apply_sends_validated(self):
        p, _ = self.make(); p.client.demo_calls.clear()
        p.open_color(['light.kitchen_left']); p.editor.pick('Red', 'rgb', (255, 0, 0)); pump(self.app)
        self.assertEqual(p.client.demo_calls, [])
        p.editor.apply(); pump(self.app, 20)
        d, a, ids, data = p.client.demo_calls[-1]
        self.assertEqual((d, a, ids, data['rgb_color']), ('light', 'turn_on', ['light.kitchen_left'], [255, 0, 0]))
        self.assertNotIn('brightness_pct', data)

    def test_colour_unsupported_light_disables_everything_with_reason(self):
        p, _ = self.make(); p.open_color(['light.bathroom_vanity'])
        self.assertFalse(any(c.isEnabled() for c in p.editor.chips)); self.assertFalse(p.editor.apply_btn.isEnabled())
        self.assertIn('On/off only', p.editor.info.text())

    def test_room_colour_skips_incompatible_lights(self):
        p, _ = self.make(); p.client.demo_calls.clear()
        p.open_color(['light.kitchen_left', 'light.kitchen_right']); p.editor.pick('Warm White', 'temp', 2700); p.editor.apply(); pump(self.app, 20)
        ids = [c[2] for c in p.client.demo_calls]
        self.assertEqual(ids, [['light.kitchen_right']])

    def test_repeat_taps_coalesced_and_queue_bounded(self):
        p, _ = self.make(); p.client.demo_calls.clear()
        self.assertTrue(p.send_action('light', 'turn_off', ['light.kitchen_left']))
        self.assertFalse(p.send_action('light', 'turn_off', ['light.kitchen_left']))
        p.pending = 8
        self.assertFalse(p.send_action('light', 'turn_on', ['light.kitchen_right'])); p.pending = 0

    def test_offline_blocks_actions_and_marks_stale(self):
        p, _ = self.make(); p.store.failed(); p.refresh_all(); p.client.demo_calls.clear()
        self.assertFalse(p.send_action('light', 'turn_off', ['light.kitchen_left']))
        self.assertEqual(p.client.demo_calls, [])
        self.assertIn('offline', p.bottom_status.text().lower())
        self.assertFalse(p.tiles['kitchen'].toggle.isEnabled())

    def test_camera_empty_state_honest(self):
        p, _ = self.make(); self.assertIn('No camera available', p.camera_view.text())
        self.assertFalse(p.refresh_btn.isEnabled())

    def test_stale_camera_result_discarded(self):
        p, _ = self.make(); p.active_camera = 'camera.x'; p.page_index = P.PAGE_HOME
        from PyQt5.QtGui import QImage
        p.camera_ready('camera.x', p.cam_gen, QImage(10, 10, QImage.Format_RGB32))
        self.assertIsNone(p.preview_image)

    def test_camera_decode_bounds(self):
        import camera
        from PyQt5.QtGui import QImage
        from PyQt5.QtCore import QBuffer, QByteArray
        def png(w, h):
            ba = QByteArray(); b = QBuffer(ba); b.open(QBuffer.WriteOnly); img = QImage(w, h, QImage.Format_RGB32); img.fill(0x336699); img.save(b, 'PNG'); return bytes(ba)
        out = camera.decode_bounded(png(1280, 720)); self.assertLessEqual(out.width(), 640); self.assertLessEqual(out.height(), 360)
        with self.assertRaises(ValueError): camera.decode_bounded(png(2400, 1400))
        with self.assertRaises(ValueError): camera.decode_bounded(b'not an image')
        with self.assertRaises(ValueError): camera.decode_bounded(png(1280, 720), max_pixels=100000)

    def test_weather_footer_demo(self):
        p, _ = self.make(); self.assertIn('71', p.bottom_status.text()); self.assertIn('Humidity', p.bottom_detail.text())

    def test_slider_and_scroll_preserved_across_refresh(self):
        p, _ = self.make(); p.open_room('kitchen'); pump(self.app)
        row = p.room_light_rows['light.kitchen_left']; row.slider.setValue(33)
        p.refresh_all(); self.assertIs(p.room_light_rows['light.kitchen_left'], row)   # no teardown on refresh

    def test_edit_mode_open_close_does_not_leak_widgets(self):
        from PyQt5.QtWidgets import QWidget
        p, _ = self.make()

        def cycle(n):
            for _ in range(n):
                p.start_edit(); p.edit_room('kitchen'); p.edit_back(); p.cancel_edit(); pump(self.app, 3)
            pump(self.app, 10)
            return len(p.findChildren(QWidget))
        warm = cycle(10)
        self.assertEqual(cycle(40), warm)   # widget count is steady-state: nothing accumulates


if __name__ == '__main__': unittest.main()
