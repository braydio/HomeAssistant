# Home Panel, native Qt edition

A functioning proof-of-concept for **Raspberry Pi Zero 2 W + 7-inch HDMI touchscreen**. The Pi 4 continues hosting Home Assistant; the Zero runs a lightweight native Python/Qt Widgets client. **No Chromium or full Home Assistant frontend is loaded.**

## What it does (v2)

Three tabs in the touch band – **Home | Lights | Cameras** – and Settings from Home (with a Back button).

- **Home**: four favourite room tiles (aggregate state + Turn on/off), three scenes, **All Off**, Settings.
- **Lights**: *Rooms* (tap a name to open a room, drag to scroll) and *Colors*.
  - Room view: per-light brightness slider (only if supported), **Color** button, ON/OFF; room header has Color (whole room) and ON/OFF.
  - **Colour editor** (one reusable in-band widget): capability-driven – on/off and brightness-only lights say so and disable colour; colour-temperature lights get Warm/Daylight clamped to their range; RGB lights get seven named swatches. Chips only *preview*; **Apply** sends one validated `light.turn_on`.
  - **Colors tab**: HA colour target (‹ ›), swatches, Apply, presets 1–4, Save… (slot → "Overwrite?" confirmation) – all through the existing `script.home_panel_*` scripts and `input_select.home_panel_color_target`.
  - **Edit layout**: panel-only rearrangement (does *not* change Home Assistant rooms/areas/groups/scenes). Move rooms ▲▼, open a room, **Move to…** another room, reorder lights ▲▼, Done / Cancel / Reset. Saved in `~/.config/ha-minipanel/layout.json`.
- **Cameras**: one selected camera, manual refresh (optional auto-refresh), bounded decode; honest "No camera available" when HA has none.
- **Settings**: Auto/Light/Dark, camera refresh preference, diagnostics (HA state, last update, RSS, MemAvailable, CPU temp, counters, version).
- **Touch band**: with `touch_band: [112, 442]` the top and bottom strips are display-only (clock, greeting, light summary, weather, offline/stale status). Every control – including nav, Back, Done and Move to… – lives inside the band with an 8 px safety margin.
- **Offline**: the last known values stay on screen marked "Offline · last known", actions are disabled, the footer shows the data age and retry time; retries back off 5→10→30→60 s.

Modules: `panel.py` (bootstrap, pages, polling), `views.py` (widgets), `ha_client.py` (REST + service allowlist), `state_store.py`, `settings.py` (config validation, default rooms), `colors.py`, `layout_model.py`, `camera.py`, `telemetry.py`.
Tests: `python3 -m unittest test_layout_model test_colors test_core test_ha_client` (no Qt) and `QT_QPA_PLATFORM=offscreen python3 -m unittest test_ui_offscreen`.

Config keys are in `config.example.json`; v1 keys (`lights`, `cameras`) still work. `rooms[].lights` can pin members when a group entity is unavailable.

**Not done**: live video, drag-and-drop moving (tap-based *Move to…* instead), WebSocket subscription (one bulk REST read every 20 s is cheaper on a Zero). See `docs/PANEL_REDESIGN_AUDIT.md`.

## Install on DietPi Zero 2 W

Your current Chromium kiosk installation should be **backed up and preserved** initially. You can test the native panel from the existing graphical/X11 session.

```bash
sudo apt update
sudo apt install --no-install-recommends python3-pyqt5
# Copy the directory to ~/ha-minipanel (or another chosen path)
cd ~/ha-minipanel
cp config.example.json config.json
```

Replace `HOME_ASSISTANT_PI4_IP` in `config.json` with the *Pi 4 server's LAN IP*, not the Zero's IP. If auto-discovery is too broad, set arrays to real entity IDs and set auto discovery flags to `false`:

```json
"lights": ["light.living_room", "light.porch"],
"scenes": ["scene.relax", "scene.night"],
"cameras": ["camera.tapo_c120"]
```

The example entity names here are placeholders, **not discoveries of your actual devices**.

Create a long-lived access token in **Home Assistant → User profile → Security → Long-Lived Access Tokens**, then save it locally with restricted permissions:

```bash
install -d -m 700 ~/.config/ha-minipanel
umask 077
nano ~/.config/ha-minipanel/token
chmod 600 ~/.config/ha-minipanel/token
```

No token belongs in `config.json`, screenshots, Git commits, or Claude messages.

Run a safe offline demo first, from a working graphical session:

```bash
/usr/bin/python3 panel.py --demo --windowed
```

For the actual Home Assistant server:

```bash
/usr/bin/python3 panel.py --windowed
```

And only after validating touch, network, device controls, and layout:

```bash
/usr/bin/python3 panel.py
```

`panel.py` uses the distribution's Python Qt5 bindings. Avoid mixing system `python3-pyqt5` with a virtual environment that does not expose system site packages. On headless SSH, the UI requires a valid X11 display/session (`DISPLAY`) and appropriate X authority. **Do not install a full desktop environment just to run this.**

## Switching from Chromium kiosk

DietPi already has working Chromium autostart. Let Claude **inspect the current X11 startup chain**, back it up, and change only the *launched application*, not the whole image. The target is to start native Qt when the graphical session is ready, without two browsers/window managers consuming RAM. Do not switch autostart before manual tests pass. Maintain an SSH recovery path and a reversible way to restore Chromium.

## Camera behavior

This prototype uses `GET /api/camera_proxy/<entity_id>` for snapshots. Some camera integrations do not expose still images without special configuration. If the endpoint fails, fix/test the integration first. Tapo RTSP live video can be investigated as a separate optional player (preferably a low-resolution H.264 substream); **this build does not claim live video works on the Zero 2 W.**

## Architecture and performance

```
Pi 4 / DietPi                         Pi Zero 2 W / DietPi
+------------------------+             +---------------------------+
| Home Assistant 2026.7.4|   LAN API   | X11 + native Qt Widgets   |
| Docker container       |<----------->| HA state/lighting controls|
| Tapo camera entities   | snapshots   | 3-tab touchscreen UI      |
+------------------------+             +---------------------------+
```

- Home Assistant state polling: default 20 seconds (one bulk read, filtered to the entities the panel uses).
- Camera snapshots: manual, or every `snapshot_seconds` **only while the Cameras page is open**.
- Network requests run outside the UI thread.
- Do not load all live streams or refresh camera snapshots continuously in the background.
- No HA server containers or integrations are installed on the Zero 2 W.
- A local private network is assumed. Configure HTTPS if the network cannot be trusted.

## Test and rollback

1. Run the unit tests listed above.
2. Launch with `--demo --windowed` and verify every page/theme setting with touch.
3. Configure URL/token. Test each selected light, one scene, and one camera snapshot.
4. Benchmark idle RSS/available RAM and interaction lag *on the Zero*, not the Pi 4.
5. Back up the existing Chromium launch/config and switch autostart only after working tests.
6. If kiosk startup fails, use SSH to restore previous autostart/config and reboot the Zero.

Upstream API references:
- https://developers.home-assistant.io/docs/api/rest/
- https://developers.home-assistant.io/docs/api/websocket/
- https://www.home-assistant.io/integrations/generic/
