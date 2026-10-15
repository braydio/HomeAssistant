# TP-HA-PANEL-20261014-001 — Native 7-inch Touch Panel Redesign

**Repository:** `braydio/HomeAssistant`  
**Baseline reviewed:** `main@f213bd9a5569dda21e82f84b2415811c309761c0` (2026-10-14 local)  
**Owner intent:** Preserve the smoothly running native Pi Zero 2 W panel and its restricted middle touch band; redesign minimally, add per-light colors and panel-only room/light rearrangement, improve efficiency, preserve rollback, and report measured results.  
**Priority:** P1  
**Type:** Codex implementation packet. This file is instructions only; its addition does not modify the deployed panel.

## 0. Execution contract

Act as the implementing engineer. Read this packet and the existing repo before editing. **Implement, test, document, and commit** a coherent redesign, rather than returning another plan. Work in a feature branch and open a PR for review; do not merge or change production Home Assistant or the touchscreen's DietPi startup until bench validation has passed. If an authorized and already-working SSH channel to the Pis exists, use it for read-only runtime inventory and, after test success, a controlled deployment with rollback. If no such access exists, finish all code, tests, configuration templates, screenshots and deployment commands, and state clearly that hardware validation is pending. Never invent actual hardware readings or device availability.

Read `README.md`, `docs/SETUP.md`, `screen/ha-minipanel/{README.md,CLAUDE_BUILD_AND_DEPLOY.md,ROLLBACK.md,config.example.json,panel.py,ha_client.py,test_ha_client.py}`, `screen/system/custom.sh`, `dashboards/home-panel.json`, `dashboards/helpers-*.json`, `configuration.yaml`, `automations.yaml`, `scripts.yaml`, `scenes.yaml`, and BirdNET bridge files.

**Absolute guardrails:**
- **Do not reinstall DietPi or move HA to the Zero.** HA Container remains on the Pi 4. The Pi Zero 2 W runs one native Qt Widgets client, not Chromium, a WebView, Electron, Node, an HA server, a database, or multiple decoders.
- The Zero 2 W has **512 MB physical RAM**. Keep X11 minimal and preserve SSH, Wi-Fi, display, touch, and working Chromium rollback.
- The display is **1024 × 600**, QDtech MPI7002. Current digitizer only responds around **Y=112–442**. Treat everything outside this as **display-only**; no controls, clickable arrows, tap targets, scrollbars, acknowledgements, or touch-only recovery controls there. Do not claim software calibration repairs missing digitizer reports. Respect `touch_band` and also support a future fully functioning digitizer.
- Do not expose HA token, camera credentials, RTSP URLs, LAN secrets, entity-state dumps, personal event details, or auth headers in code, repo, screenshots, telemetry or logs. Never change `.storage/`, `secrets.yaml`, or camera credentials. Existing `tapo_control` is disabled because a stale password may trigger lockout; **do not reenable it as part of this packet**.
- UI-managed Lovelace dashboard `dashboards/home-panel.json` is an exported reference, **not** the native Qt UI or an automatically loaded YAML dashboard. Bubble Card, kiosk-mode, and Browser Mod are Chromium/frontend plugins; do not attempt to embed/install them on the Zero.
- Do not broadly purge packages or disable unrelated services. Do not send commands to unfamiliar entities; ask before controlling an unknown physical device. Use documented, reversible migrations. Preserve existing production scenes/scripts/helpers.

## 1. Verified static findings (runtime still needs verification)

Architecture: Pi 4 HA Container Core 2026.7.4; Pi Zero 2 W native PyQt5 on X11 using DietPi custom autostart `screen/system/custom.sh`. Existing pages: Home / Lights / Cameras / Settings. Existing look: dark/light QSS themes, card layout; `sun.sun` auto mode; camera JPEG snapshots only; weather status/forecast already rendered in bottom dead zone.

**Concrete shortcomings from source:**
1. `ha_client.py:states()` fetches **all** `GET /api/states` every `poll_seconds=12`, even though the UI needs a small curated entity set. `Panel.update_states()` rewalks the state set and refreshes widgets. No targeted subscriptions, state diffs, bounded command queue, or per-feature visibility budgets.
2. `config.example.json` defaults `auto_discover_lights/scenes/cameras=true`. This can show unwanted or duplicate group/member lights, too many devices, non-favorite scenes, or cameras. A production curated allowlist is safer and cleaner.
3. `panel.py:make_home()` is a generic two-column card layout with extra prose; high vertical density when restricted to a 330-px touch area. Navigation consumes part of that band. Current cameras selector can place as many as five buttons in a row, which can create cramped hit areas.
4. `Panel.camera_ready()` uses `QPixmap.loadFromData()` on the UI thread and saves an original pixmap; `camera_snapshot()` caps compressed response to 3 MB but does **not** impose an image dimension/decompressed-pixel cap. The pixmap remains retained when page changes. Repeated scaling can cause CPU/RAM spikes; stale in-flight camera requests can paint after page changes.
5. `QThreadPool` has two workers but service actions use unique `time.monotonic_ns()` keys with no queue bounds/debounce and can pile up on quick presses. No deliberate action coalescing or per-command cooldown.
6. The native panel lacks the **Colors** functionality in the exported HA dashboard: target selection, warm/daylight and RGB favorites, and four saved presets via `script.home_panel_apply_color`, `script.home_panel_save_preset`, `script.home_panel_apply_preset`. Do **not** recreate the entire 886-line Lovelace layout; implement a small native subset.
7. The current panel settings display hard-coded `Pi Zero 2 W · Native Qt client · No Chromium` rather than actual local RAM, CPU temperature, connectivity and update age. The native app's theme preference is separate from the HA frontend `input_select.home_panel_theme_mode`, so document whether they are intentionally independent.
8. Repository references weather entity `weather.forecast_home`, HA-created light groups and active scenes. These are **configuration references**, not proof they are present/available on live HA. The current C120 BirdNET bridge handles camera audio and HLS; it does not expose HA BirdNET species/count entities in this repo. Do not fabricate them.
9. `configuration.yaml` still enables `trusted_networks` login bypass for the Screen IP even though the native app uses a long-lived token. Flag this for a **separate security review** after establishing whether any browser/other client still needs it; do not silently remove or rewrite authentication settings.

## 2. Target information architecture

**Three primary tabs in the reachable touch band:** `Home | Lights | Cameras`. `Settings / Diagnostics` is a clearly labeled button reachable from Home, with a visible Back button in the touch band; never hide settings behind an undocumented long press. Keep the old fourth-tab design as an easy fallback if actual touch tests make three tabs awkward.

The visual direction is restrained and contemporary: dark slate/navy at night, warm-white/light gray by day, one blue accent, typography hierarchy, generous internal padding, crisp status text, no gradients, scrolling marquees, charts, videos as decoration, blur, animated background, or >one large dynamic image. Favor flat Qt layouts, QSS, vector/simple Unicode icons from installed fonts, and zero extra browser components.

**Fixed 1024x600 touch-band composition (adapt to true measured band):**
- `y=0..111`: **display-only header**: large local clock and date left; greeting + concise lights summary center; Auto/Day/Night label right. No controls.
- `y=112..442`: **interaction zone** with 12–18 px internal gutters. Reserve the bottom approximately 52 px of this zone for a 3-button navigation bar. This is NOT the bottom of the physical display. The remaining approximately 265 px is page content. Place all Settings/Back, Refresh, sliders, dropdowns, selector arrows, toggles, scroll starts/ends and action confirmations here. Every active hit box must remain at least 8 px inside the measured touch boundary; target >=44 px tall when feasible.
- `y=443..599`: **display-only footer**: current weather, tomorrow high/low when valid, weather last-update age or Pi/HA offline indication. Do not put important interactivity here. Display stale-value labeling after connectivity loss.
- If `touch_band=null`, compute natural header/content/nav/footer responsive geometry so all controls still fit at 1024x600 and can scale to 800x480 if detected; never hardcode `600-bot` without using current window height. Dynamic responsive relayout must not create dead-zone click targets.

**Home page** (single screen; never cram entire smart home): left ~60% width = 2×2 favorite room tiles (Kitchen, Living Room, Bathroom, Bedroom; Office appears in Lights unless chosen in live configuration). Each tile shows short name, on/off aggregate, and a clear `Toggle` action; optionally `Details` button if truly needed. Right ~40% = 3 favorite scene buttons: `Relax`, `Bright`, `Night`, plus prominent but distinct `All Off`; include a labeled, reachable `Settings` entry. If the vertical fit cannot accommodate all, use a compact **two-column 2×2 quick-action grid** or place Settings in the nav area as a fourth tab; do not shrink controls below safe touch height.

**Lights page**: compact in-band segmented control `Rooms | Colors`, with up to 3–4 room rows visible and inertial finger scrolling for overflow. A room-detail subview shows a Back button, room on/off, individual members and *only supported* brightness sliders. Handle Cync/WiZ supported_color_modes and unavailable/unknown state gracefully. In `Colors`, include a target selector for existing `input_select.home_panel_color_target`, two Kelvin chips (e.g. warm 2700 K / daylight 4000 K), six high-value RGB swatches (red, amber, green, cyan, blue, pink/purple), and four saved slots with Apply; save is accessed by explicit secondary confirmation to prevent accidental overwrite. Use existing HA script fields and helpers rather than duplicating persistent color state in the panel; verify script semantics on test HA.

**Cameras page**: left main preview for only the selected camera, right slim camera selector (scroll if needed), latest still timestamp, `Refresh` and `Pause`. Default **manual load / low-rate snapshot only while visible**, with 15–30s optional automatic refresh if measured resources allow; no fullscreen live stream at startup. If no working HA `camera.*` entity exists, render a polished honest `No camera available` state, not a placeholder that implies video works. Never trigger `tapo_control` reconnect/credential changes. The existing C120 audio bridge is unrelated to image access.

**Settings / Diagnostics**: Auto/Light/Dark theme (persisted), HA connected/disconnected and last valid update, local Pi RSS/MemAvailable/CPU temperature where safely available, camera refresh preference and render-rate setting, app version/build, manual refresh, compact diagnostics. No scrolling system logs on a 7-inch screen. Respect read-only diagnostics; hide noncritical controls when offline.

## 3. Data and integrations: concrete priorities

| Priority | Source | Display | Cost / rule |
|---|---|---|---|
| P0 | Existing `light.*` group/member entities and `scene.panel_*` | home tiles, light room control, favorite scenes | Allowlist only; dedupe group/member counts; state updates batched, actions per user interaction |
| P0 | Local clock plus `sun.sun` | clock/date, automatic theme | Clock purely local every 30–60s; no Time & Date integration for the same value |
| P0 | Existing `weather.forecast_home` if verified (Met.no or actual provider) | footer: condition, temperature, humidity, tomorrow | State changes low-frequency, existing `weather.get_forecasts` no more often than 30m; reuse current implementation, do not start another weather poller |
| P0 | Local `/proc/meminfo`, `/proc/self/status`, `/proc/uptime`, thermal sysfs (if present) | small diagnostics only, optionally stale/offline symbol | Poll locally 30–60s; no psutil required and no extra service on Zero |
| P1 | Existing `media_player.*` from Cast/Alexa, IF live and useful | small Now Playing *read-only* line on Home/footer, optional play/pause later | One curated player, state-driven; no album art polling, streams, or heavy cover download |
| P1 | Existing `fan.*` or `switch.*` from VeSync, IF live and useful | optional one-touch favorite tile | Add only after live entity/service validation; no blanket `switch` controls |
| P1 | `sensor.uptime` and/or selective System Monitor sensors on HA Pi 4 | HA uptime/health on Settings only | Uptime nearly zero updates; System Monitor sensors disabled by default and in HA Container may describe **container**, not Pi 4 host; verify scope before labeling |
| P2 | Existing `binary_sensor.*` for contacts/motion/temp, IF actually integrated | tiny status badges | Curated sensors only; no all-sensor feeds |
| P2 | Existing calendar from HA / optional Local Calendar | next event teaser, optional | Privacy/consent: disabled by default because panel is always visible; don't connect a Google account without request |
| P2 | BirdNET activity | `Most recent bird` or count, if a *real* HA/MQTT feed exists | Bridge currently makes audio HLS, not detection telemetry; don't deploy BirdNET, MQTT broker, ffmpeg, or new ML to the Zero. Add only a narrow read-only feed after confirming source/data contract |

**Integration recommendation:** prioritize existing integrations and one opt-in HA **Uptime** integration. Met.no is free and keyless, but don't reinstall if `weather.forecast_home` already works. Add **System Monitor** only for selected meaningful Pi 4/HA diagnostics; verify what Container sees. Do **not** add Browser Mod, animated Lovelace weather cards, extra HACS integrations, Glances stack, InfluxDB, Grafana, Frigate, Home Assistant OS add-ons, or a new MQTT broker just to enrich this panel. For app-only local date/time, don't create HA time sensors.

Inventory HA at runtime securely using a non-admin token only in local secured files, query `GET /api/states` once for discovery, and generate a sanitized `docs/PANEL_ENTITY_INVENTORY.md` with **entity IDs, friendly labels, state availability, supported color modes, recommended page placement and actual service tests** (do not include personal states such as whereabouts, camera URLs, or calendar details). Distinguish `confirmed` / `configured but unavailable` / `proposed`.

## 4. File-level implementation plan

Refactor `screen/ha-minipanel/panel.py` incrementally without changing toolkit. Prefer ~5 small modules:
- `panel.py`: launch/bootstrap, screen geometry, page/navigation composition, theme activation.
- `views.py` (new): `HomeView`, `LightsView`, `ColorsView`, `CamerasView`, `SettingsView` Qt Widgets; use reusable `RoomTile`, `SceneButton`, `StatusChip`, `LightRow`.
- `ha_client.py`: keep authenticated REST operations, add targeted state fetch and typed, allowlisted services; enforce response sizes and deadlines; no generic service invoker exposed to UI.
- `state_store.py` (new): normalized selected-entity dictionary keyed by entity_id, selective diff/signals, online/stale flags, generation number, last_success monotonic time.
- `telemetry.py` (new): local-only procfs stats; parsers safe with missing thermal/sysfs paths.
- `camera.py` (new if useful): bounded snapshot fetch/decode pathway; never keep multiple original decoded frames.
- `config.example.json`: example shape and defaults, comments belong in README (JSON itself remains valid).
- `tests/` (new or adapt current unittest): state/cache/action, color schema, weather expiry, camera bounds, layout geometry, offline recovery, screenshots.

**Suggested config shape** (actual entity IDs must be substituted after discovery, and existing keys backwards-compatible):
```json
{
  "ha_url": "http://HOME_ASSISTANT_PI4_IP:8123",
  "token_file": "~/.config/ha-minipanel/token",
  "touch_band": [112, 442],
  "layout": "three_tab",
  "rooms": [
    {"label":"Kitchen","entity_id":"light.kitchen_lights","favorite":true},
    {"label":"Living Room","entity_id":"light.living_room_lights","favorite":true},
    {"label":"Bathroom","entity_id":"light.bathroom_lights","favorite":true},
    {"label":"Bedroom","entity_id":"light.bedroom_rope_lamp","favorite":true},
    {"label":"Office","entity_id":"light.office_office_main_light","favorite":false}
  ],
  "scenes": ["scene.panel_relax","scene.panel_bright","scene.panel_night_lights"],
  "colors": {
    "target_entity": "input_select.home_panel_color_target",
    "apply_script": "script.home_panel_apply_color",
    "save_script": "script.home_panel_save_preset",
    "preset_script": "script.home_panel_apply_preset"
  },
  "weather_entity": "weather.forecast_home",
  "camera_entities": [],
  "media_player_entity": null,
  "fan_entity": null,
  "poll_seconds": 20,
  "camera_auto_refresh": false,
  "snapshot_seconds": 25,
  "camera_max_bytes": 1048576,
  "camera_max_decoded_pixels": 2073600,
  "diagnostics_seconds": 60,
  "auto_discover_lights": false,
  "auto_discover_scenes": false,
  "auto_discover_cameras": false
}
```
Example entity IDs above derive from tracked dashboard/scripts, **not** live verification. Make `touch_band` runtime-configurable and keep old `lights`/`cameras` keys valid during migration. Validate types/ranges and duplicate IDs at startup, fail with specific non-secret messages.

**Model contract:**
```python
@dataclass(frozen=True)
class EntitySnapshot:
    entity_id: str
    state: str
    friendly_name: str
    attributes: dict
    last_updated: str | None

@dataclass(frozen=True)
class PanelHealth:
    ha_connected: bool
    last_ha_success_monotonic: float | None
    pi_mem_available_kib: int | None
    panel_rss_kib: int | None
    cpu_temp_c: float | None
    network_online: bool | None

@dataclass(frozen=True)
class ActionRequest:
    domain: str
    service: str
    entity_id: str
    data: dict
    source: str
```
Use a single shared state store, not per-view duplicated HTTP polling. UI thread is never blocked on network or image decoding. Update only changed widgets. All callbacks check their view/generation before painting. Avoid wholesale layout teardown on each successful poll; preserve scroller offsets and sliders being dragged.

## 5. Network, command, and caching policy

Initial baseline: one `GET /api/states` request **once per successful connection** for discovery, select configured entities, cache only those in memory. After inventory choose one of the following:
- **Preferred after testing:** a **single authenticated** HA WebSocket at `/api/websocket` using official `auth_required` → `auth` → `auth_ok`, then subscribe to `state_changed` events via `{"id":1,"type":"subscribe_events","event_type":"state_changed"}`. Discard non-allowlisted events immediately, and handle `event.data.entity_id/new_state` with minimal allocation. If the server supports an officially documented narrower subscription appropriate to the version, prefer it after verifying schema. No additional sockets per page. Periodic heartbeat/resync only; use capped jittered reconnect (2, 5, 10, 30, 60s), then one fresh snapshot to heal missed events. Do not spin reconnects rapidly or log bearer tokens.
- **Fallback if the socket dependency/resource cost is unjustified:** bounded **REST-only** update loop, 20–30s, measure the serialized size of `/api/states`; for sufficiently small allowlists consider `GET /api/states/{entity_id}` with bounded concurrency, keep-alive where supported. Compare payload bytes/CPU and select the cheaper measured path. Under no circumstance poll all entities every 2s or use an HTTP request per sensor each second.

The WS subscribe-events command is documented at https://developers.home-assistant.io/docs/api/websocket/; REST at https://developers.home-assistant.io/docs/api/rest/. **Do not assume undocumented WS message types.**

Required behavior:
- Exactly one state-poll or subscribe mechanism active; coalesce repeated identical requests, cap network threads at 2, outbound action queue at 8 (or fewer), discard stale tasks by generation.
- For toggles, suppress repeat taps on the same entity for ~500–800ms and show a short pending state; on completion refresh/accept HA event. Brightness writes on `sliderReleased` only, de-duplicate and clamp 1..100.
- Service allowlist only: `light.turn_on/turn_off`, `scene.turn_on`, named `script.turn_on` targets in config, plus specifically authorized `input_select.select_option` for known color-target helper. Optional fan/media services only after explicit existence and supported-feature validation. For script fields, use `script.turn_on` with `{"entity_id":"script...","variables":{"slot":1}}` if validated, or the documented direct named script service with properly shaped data. Never create a generic arbitrary-service UI.
- Color/Kelvin validation: RGB each integer 0..255, temperature 2000..6500 K **further clamped to target's supported range**, brightness 1..255, slot 1..4; disable commands for unsupported/unavailable target. Show friendly error; no repeated retry storm.
- HA weather `weather.get_forecasts?return_response` existing implementation: at most once/30 min, only while weather entity available, in-memory cached summary, no extra third-party weather requests. Handle zero/one-day forecast safely. Time/date local, no HA requests.
- Distinguish **offline** vs **unknown** vs **stale** data. During disconnect retain last values with a visible age badge and disable unsafe outbound actions. Do not visually imply light state remains current.
- Add operational counters (`ha_state_requests`, `ha_state_bytes`, `ha_actions`, `weather_forecasts`, `camera_requests`, `camera_bytes`, `network_errors`, `ui_long_frames`) to a compact in-memory bounded diagnostics ring (e.g. 200 items); optional rotating local file with redacted structured records, 1 MB × 3 files. No per-event state dump or secrets. No metrics exporter/database required.

## 6. Camera memory safety

Retain existing `GET /api/camera_proxy/{entity_id}` if and only if a real usable `camera.*` entity is confirmed. Run network reads in existing worker pool with 6–8s timeout, strict Content-Type `image/*`, hard compressed byte ceiling **1 MiB default** (configurable at most 3 MiB after test), guard `Content-Length` where present and cap streaming reads. Reject invalid formats.

Do NOT call `QPixmap.loadFromData` on untrusted arbitrary dimensions in the GUI thread. Use `QImageReader` with `QBuffer` / `QByteArray`, read dimensions before decode; reject dimensions >1920×1080 by default or >2,073,600 original pixels, and decode to ~640×360 or smaller (use `setScaledSize` when available). QImage decoding can run in background; create `QPixmap` in GUI thread only after bounded QImage returns. Enforce generation+active_camera+page check when results arrive; discard stale image before repainting. Store **one displayed scaled frame only**; free it when camera page exits (or keep one tiny ~200KB cached thumbnail after measurement). Destroy old QImage/QPixmap references.

Never automatically open simultaneous HD RTSP streams. Separate optional technical feasibility report can discuss low-res H.264 on-demand only after camera is reliable. A live player is **out of scope** without hardware performance proof and credential-safe design. C120 audio bridge already uses ffmpeg on Pi 4; do not introduce ffmpeg, BirdNET, or streams on the Zero.

## 7. UI/UX and theme acceptance details

- Palette source: adapt current `PALETTES` and `themes/panel.yaml`; high contrast and a single primary blue. Keep hit-size standards even when `COMPACT=true`; current 38px compact `button()` height is a starting point, not sufficient for every critical touch action.
- Consistent 8/12/16px spacing scale, ~14–18px body text, ~24px major headings, ~42px clock, 12–14px muted metadata. No truncation of action names, overlapping overlay, clipping, invisible divider, or status presented as clickable.
- Three visible nav destinations; selected tab obvious. Settings and Back always in live band. No hover-only interaction. A tap while scrolling must not activate a neighboring light. Scenes have pressed feedback without sending duplicate calls.
- Home must be usable without opening another page for daily common tasks: favorite room on/off, scenes, All Off.
- Color palette should present swatches with text/accessible color names, not color alone; safe `Save` confirmation.
- Network offline and HA restart do not freeze the UI or blank the clock/weather layout; weather stale age visible.
- Automatic theme follows `sun.sun` when present, falls back to local time only while HA unavailable; persisted local Light/Dark override survives restart. Do not assume HA's `frontend.set_theme` automation changes native QSS.
- Noninteractive zones must still read attractively; no hidden tap affordances. On the physically faulty panel, **screenshot alone is not proof** that controls are reachable.

## 8. Tests and measurement gates

**Phase A — Read-only inventory and baseline**
1. Check `git status` and pin initial SHA; inventory actual installed screen files/version vs repo, X11/DietPi startup, `findmnt -no SOURCE /`, `lsblk -f`, network routes, `xrandr`, `/dev/input`, actual touch matrix/coordinates, `free -m`, `/proc/meminfo`, `ps -eo pid,rss,%cpu,args`, `vcgencmd measure_temp` if available. Never modify an unconfirmed filesystem, particularly if a Pi Zero SD card is mounted on the Pi 4.
2. Determine live devices via authorized HA read-only API: `light`, `scene`, `script`, `input_select`, `camera`, `weather`, `sun`, `media_player`, `fan`, sensor availability. Record distinct group membership. **Do not print whole state payload**.
3. Collect **actual** baseline: combined X+panel PSS/RSS, MemAvailable, peak memory, CPU, touch latency, action acknowledgement, boot-to-ready, 10-minute idle. Measure while booted on the **Zero**, not Pi 4.

**Phase B — Implementation**
4. Preserve backward compatibility and build 3-tab native UI / secondary Settings. Fix GUI update logic, cache, network worker policy, camera bounds, weather. Restore Colors parity using existing HA scripts and helpers. Config migrations read old keys.
5. Offscreen test mode with `QT_QPA_PLATFORM=offscreen` plus deterministic demo snapshots. Capture sanitized images of Home, Lights/Colors, Cameras/no-camera, Settings, Light and Dark at 1024×600. Draw overlay lines at Y112 and Y442 in **test artifacts only** and assert all visible interactive widgets' mapped geometry lies inside Y120..434 when touch band is set. Test 800×480 only if device actually supports it.
6. Extend unit tests for allowlist + malformed config, group/member deduplication, color range/script variables, repeat-tap coalescing, network timeout/reconnect/stale, state diff/preservation of slider drags/scroll positions, 1MiB compressed and 2MP decoded camera ceilings, inactive page/stale snapshot invalidation, weather forecast cache/staleness, telemetry missing sysfs, and responsive geometry. Ensure existing `test_ha_client.py` still passes.

**Phase C — Deployment & physical tests (only if SSH and approvals are present)**
7. Back up screen `custom.sh`, existing app, config, preferences, `/boot/dietpi.txt`, X configuration, autostart selection. Preserve credentials on target only with mode `0600`, directory mode `0700`. Do not copy token into Git. Use a **temporary side-by-side test path** before overwriting production app.
8. Run from actual X session `/usr/bin/python3 panel.py --demo --windowed`, then configured real HA test window. Verify real finger taps near top/bottom edges of band; scene activation and device external state refresh; network drop/recover; theme change; camera absent/available; clean close/relaunch.
9. If current autostart is already `dietpi-autostart 14` and `screen/system/custom.sh`, do not blindly switch it again. Deploy versioned app with an atomic symlink or backup swap, one app only, full reboot. Verify a 30-minute soak, no crash loop, SSH still reachable, Chromium not resident.
10. Immediate rollback for any hard failure. Document **exact** commands and old/new versions; existing fallback is `sudo /boot/dietpi/dietpi-autostart 11 && sudo reboot`, but verify the Chromium fallback still exists before relying on it. Safer app-level rollback first when possible.

**Performance gate — targets, not claims of current results:**
- Goal: idle Python panel RSS <= **130 MiB**; camera page peak <= **180 MiB**, and >**100 MiB MemAvailable** including X/session. If baseline already exceeds any target, report that and target **<=10% measured regression** with clear explanation; never falsify success.
- Sustained idle CPU <**15% of one CPU core** averaged over 5 minutes; no recurring full-screen redraw storms. No memory growth >**15 MiB** after 30min idle + 20 camera refreshes + page switches.
- Touch feedback generally <**250ms** (local visual state); HA action confirmation within **3s** when LAN/HA healthy, otherwise explicit timeout; UI event loop remains responsive while camera request times out.
- Camera refresh **zero** while Cameras not visible; one image in memory; no polling of all cameras. Forecast <=2 requests/hour; state requests conform to selected transport policy. No hidden Chromium processes.
- Acceptance requires **hardware measurements**, not mock-only success. If Zero can't meet targets, prioritize cutting optional widgets, lowering camera update frequency, disabling camera autoplay, reducing counts/fonts before suggesting heavier hardware.

## 9. Requested outputs

- Working implementation on a feature branch + PR, link SHA and changed files; no deployment mutation on main until reviewed.
- `docs/PANEL_REDESIGN_AUDIT.md`) with confirmed vs inferred vs proposed inventory and before/after code findings.
- `docs/PANEL_ENTITY_INVENTORY.md` sanitized; mark each device as verified, configured/unavailable, or unverified.
- `docs/PANEL_PERFORMANCE.md` exact measurement commands, table of measured (not estimated) baseline/after: app RSS, X RSS, MemAvailable, CPU/temp, boot-to-ready, lag, camera latency, polling rate, uptime, failures, sample durations, process names and device hostname role (no passwords).
- `docs/PANEL_DEPLOY_AND_ROLLBACK.md` with safe stepwise install, X11/DietPi autostart behavior, app rollback and Chromium fallback.
- Demo screenshots stored in review artifacts (not sensitive real camera imagery), and test output.
- Final report: per-phase progress (audit, UI, backend, integration verification, testing, deployment) plus overall, each as percent complete; explicit blockers/unknowns. Do not claim completion of physical rollout without successful reboot and touch validation.

## 10. Definition of done

1. Exactly three clearly exposed primary tabs, Settings reachable in active touch band, no untouchable controls.
2. Native UI is cleaner than current two-card generic layout; favorite rooms/scenes work; Colors helpers/presets work where entities exist.
3. Cached state refresh is bounded, activity-driven where practical, nonblocking and observable; reconnect works.
4. No unnecessary service/plugins on Zero. Camera off-page uses no CPU/network and imagery cannot inflate RAM uncontrollably.
5. Weather and theme stay functional without duplicate polling. All unavailable integrations have honest empty states.
6. Automated tests pass; on-device tests and performance measurements either pass or are explicitly marked pending if inaccessible.
7. Secrets absent from commits/logs; Pi 4 not disrupted; reversible deployment documented.

**Sequence:** discover → measure → implement → offscreen tests → physical smoke → soak → document → PR. Fix measured bottlenecks before adding speculative integrations.

## 11. Owner follow-up: damaged touch edges, individual colors, and rearrangeable rooms (MANDATORY; supersedes earlier implementation priorities where they differ)

The owner reconfirmed on October 14 that the bottom and top strips do **not** register touch. A small connector/ribbon-looking part at the bottom corner may have been scraped, although this has not been diagnosed. The **current native Qt panel already runs smoothly** and intentionally puts information in the untouchable edges and interactive controls in the middle. Preserve and build on this working implementation. DO NOT restore Chromium, install a heavyweight UI stack, or attempt invasive hardware fixes.

### 11.1 Touch constraint is a hard UX invariant

- Treat the approximately \`Y=112..442\` touch band (1024×600 panel, \`touch_band\` configuration) as the **only interactive surface**. Live measured endpoints take precedence, with at least 8px inward safety margin. Everything above/below is display-only: clock, weather, status, greeting.
- **All** new drag handles, source rows, room drop targets, color selectors, palette chips, HSV controls, sliders, popup alternatives, \`Edit\`, \`Move to…\`, \`Save\`, \`Cancel\`, \`Done\`, \`Back\` and navigation must fit wholly inside the live band. This includes every step in an interaction. Avoid OS-native dialogs that open across dead regions.
- Do not replace middle-band arrangement with conventional full-height touch dashboard. No assumption that software calibration repairs physically absent touch events. If Codex can access physical hardware, record input coordinates with its existing input diagnostic procedure and distinguish missing touch events from UI clipping; do not disturb the possibly damaged hardware ribbon or change low-level drivers as part of redesign.
- Keep the current smooth native Qt application and X11 startup as the baseline. A visual improvement must **not** cause memory creep, sluggish taps, extra processes, or startup regressions. Changes must be reversible.

### 11.2 Individual-light color support (P0)

This is **in addition to** the earlier global Colors page and existing \`home_panel_apply_color\` / \`home_panel_save_preset\` / \`home_panel_apply_preset\` scripts.

- In a selected light's room-detail row, provide a reachable \`Color\` action that opens **one** lightweight, in-band editor (reuse one QWidget/QStackedWidget; no permanent picker for each row). Show the selected light name, on/off, supported brightness, current color or temperature, swatches, optional Kelvin picker, and \`Apply\` / \`Back\`.
- Read \`supported_color_modes\`, \`min_color_temp_kelvin\`, \`max_color_temp_kelvin\` and current state from HA before offering controls. \`onoff\`: toggle only; \`brightness\`: dimmer only; \`color_temp\`: Warm (2700 K) / Daylight (4000 K) and range-clamped temperature; \`hs\`, \`xy\`, \`rgb\`, \`rgbw\`, \`rgbww\`: RGB-color controls where HA supports them. Disable unsupported features and tell the user why. Do not assume every Cync/WiZ light handles all modes.
- Provide named chips: Red, Orange, Green, Cyan, Blue, Purple, Pink, Warm White and Daylight (the last two only for temperature-capable lights). A simple in-band hue/saturation picker is a useful P1 enhancement **only if** responsive and actually fitting; prefer Qt \`QPainter\` rendering on demand. **No QColorDialog that lands in the dead-zone or launches a browser.**
- A chip tap updates local color preview; use \`light.turn_on\` with properly validated \`rgb_color:[r,g,b]\` OR \`color_temp_kelvin:int\` on **one allowlisted \`light.*\` entity** when Apply is tapped. Permit optional \`brightness_pct\`; do not stream changes to HA with every drag/mouse movement. Clamp values to device capabilities, enforce service allowlist and throttle repeat writes. Verify state after action and handle offline/unavailable gracefully. Official service fields: https://www.home-assistant.io/actions/light.turn_on/ .
- Preset slots 1–4 still use existing HA scripts/helpers and are not duplicated as divergent panel-only scene definitions. Saving a preset must require explicit in-band confirmation. Explain that preexisting scripts/scenes operate on HA's configured targets, not arbitrary new virtual panel groupings.
- Tests: on/off-only, dimmer-only, color-temp-only, RGB, mixed-mode group, unreachable, unsupported mode disabled, RGB clamp, Kelvin clamp, no API calls on preview, no duplicates, no off-band editor controls. At most one active picker retained in RAM.

### 11.3 Edit/reorder lights and rooms from the touchscreen (P0)

The user would like to rearrange room/light order and move an individual light from one room to another **without opening HA's main frontend**. Native Qt already provides drag/drop facilities; a small amount of local JSON storage and an edit-mode QWidget should be cheap relative to browser rendering. **This does not justify Chromium.**

**Important distinction:** Home Assistant areas are persistent assignments on devices/entities and can affect other dashboards, automations, and area-targeted services. A panel UI layout is not automatically the same thing. **Implement PANEL-ONLY virtual room layout by default.** Do not silently mutate Home Assistant's Area/Device/Entity Registries, HA light groups, scenes, or automations. Keep the UI/help text explicit: \`Organize this panel (does not change Home Assistant rooms)\`. Actual HA-area synchronization, if later desired, requires a separate explicit opt-in feature and privileged/authorized registry changes; do not implement it within this redesign. HA area background: https://www.home-assistant.io/docs/organizing/areas/ .

**Required interactions inside live touch band:**
1. Lights > Rooms contains a clear \`Edit layout\` affordance. Edit mode visually separates action handles from light switches, disables all light toggles/sliders during editing, and exposes \`Done\`, \`Cancel\`, \`Reset\` inside the usable band.
2. **Touch-first reliable method (mandatory):** tap a light's \`Move to…\` control to open an **in-band** list of valid destination rooms; tap destination to stage its move. \`Move up\`/\`Move down\` reorder lights within a room, and \`Move left\`/\`Move right\` or comparable handles reorder room tiles. Every move must work by taps alone, not require long drags or reaching beyond the band. Reset-to-default has confirmation.
3. **Drag/drop (preferred if measured reliable):** long-press a dedicated drag handle for ~500 ms, create a native Qt \`QDrag\` containing only the validated light entity ID, then drop on an **in-band** room tab/drop target or insertion zone. Highlight valid targets, preserve drag-scroll distinction (\`QScroller\` may intercept touches), and disallow ambiguous drops. Native Qt room-tile reorder can share this implementation. Do not depend solely on dragging: tap-based \`Move to…\` must ship even if physical touch accuracy makes drag unreliable. No large pixmaps, animated ghost overlays, extra WebViews, or third-party drag frameworks.
4. A panel room is an ordered array of individual \`light.*\` entities, **not** a movable HA \`light.room_group\` containing overlapping children. Initialize from confirmed HA group member IDs / verified area information or curated tracked example data, then deduplicate so each controlled light is in exactly one panel room. Let temporarily unavailable lights remain visible but disabled; do not erase a room because the network drops. Do not auto-add all discovered lights into favorites.
5. **Critical behavior:** when one light is moved virtually, pressing a room's All On/Off or room color action must target **only current panel-member individual light IDs** with a deduped list. Do NOT call stale HA group \`light.kitchen_lights\` after a virtual change, since it may still contain a moved-out light. Existing external HA scenes/global scripts keep their original membership and do not silently follow the panel layout. Show a brief explanation in edit mode.
6. \`All Off\` from the panel should act on the deduped allowlisted individual panel lights, not on arbitrary HA devices. Mixed/unsupported color modes should produce an eligible-target count and safely skip incompatible lights with a clear explanation rather than failing the whole group.
7. Persist only this panel's mapping in \`~/.config/ha-minipanel/layout.json\`, **not** in \`config.example.json\`, tracked \`config.json\`, HA registry, or recorder database. The directory is 0700 and file 0600. Use a versioned schema, validate allowed entity IDs / unique room IDs / order / no duplicate memberships, stage edits in memory until Done, then durable temp-file write + \`fsync\` + atomic \`os.replace\`, with \`layout.json.bak\` for recovery. Cancel restores the in-memory prior snapshot; malformed/unsupported schema falls back to curated defaults without losing backup; Reset requires confirmation.
8. Suggested pure-model representation and API (add \`screen/ha-minipanel/layout_model.py\`, no Qt dependency):

\`\`\`json
{
  "version": 1,
  "rooms": [
    {"id": "kitchen", "label": "Kitchen", "order": 0,
     "lights": ["light.kitchen_kitchen_stove_left", "light.kitchen_kitchen_stove_right"]},
    {"id": "office", "label": "Office", "order": 1,
     "lights": ["light.office_office_main_light"]}
  ]
}
\`\`\`

\`\`\`python
PanelLayout.load(path, defaults, allowed_ids)
PanelLayout.move_light(entity_id, target_room_id, before_id=None)
PanelLayout.reorder_light(room_id, entity_id, new_index)
PanelLayout.reorder_room(room_id, new_index)
PanelLayout.validate()
PanelLayout.commit_atomic()
PanelLayout.cancel()
PanelLayout.reset_to_defaults()
\`\`\`

These example entity IDs come from source-controlled scenes and may not match the currently live HA inventory. Validate them before populating the actual device configuration. The model stores entity references only, never credentials or area-registry mutations.

**Performance gate for editing:** zero network requests just to drag/reorder, no extra long-lived services or heavyweight Python deps, no redraw of every room on each finger move. Target <=10 MiB incremental RSS while edit mode is active, and no measurable increase while idle. Benchmark 5 rooms/20 lights, simulate 50 lights if needed, 50 sequential rearrangements, 30-minute soak, restart persistence and repeated edit-mode open/close without memory growth. If drag feels bad with this limited touch band, drop drag functionality before sacrificing tap-sized buttons or responsiveness; the \`Move to…\` workflow alone fulfills the practical need.

**Acceptance sequence:** choose Edit layout; move a light to another room using taps, reorder a room and two lights; hit Cancel and verify no persistence; repeat and hit Done, relaunch and verify; confirm room control targets only current panel assignments, current HA areas/groups/scenes/automations remain untouched; confirm input events work from start to finish entirely inside the measured active band; perform color changes on representative real lights and measure latency/RSS.

### 11.4 Required Codex outputs and delivery updates

Include both features in the implementation branch and updated unit/Qt-offscreen tests; create a sanitized demo showing (a) one individual-light color editor, (b) active room layout editing, (c) move destination picker, and (d) the original touch-band exclusion overlay at 112/442. Update \`docs/PANEL_REDESIGN_AUDIT.md\`, \`docs/PANEL_PERFORMANCE.md\`, \`docs/PANEL_DEPLOY_AND_ROLLBACK.md\`, \`config.example.json\`, and README as needed. Clearly distinguish **implemented**, **live-tested**, and **pending hardware access**. Report progress by feature (touch safety, native layout, colors, panel-only room edits, runtime efficiency, camera, tests, deployment) and overall.

**Priority override:** protect the already-smooth native panel and the narrow middle touch area **before** any other proposed features or integrations. Color controls and panel-only room reordering now outrank optional media/system-monitor/BirdNET integrations. If scope or RAM becomes constrained, defer optional integrations, camera live-view investigations, fancy drag visuals and hue wheels, but **do not omit** the basic in-band color chips and tap-based room rearrangement.
