# Panel redesign audit (packet TP-HA-PANEL-20261014-001 + owner follow-up §11)

Baseline: `main@f213bd9`. Result: panel **v2.0.0** running live on the Screen (Pi Zero 2 W). Everything below says whether it
is **implemented**, **live-tested** (on the real Screen / real HA, synthetic X clicks), or **pending**. Finger touch on the
physical digitizer was *not* tested by me – only by injecting X mouse events at the same coordinates a finger would produce.

## Before → after (source findings from the packet, checked against the code)

| # | Finding in v1 | v2 | State |
|---|---|---|---|
| 1 | Whole `/api/states` (~46 KiB, ~95 entities) parsed every 12 s; widgets rewalked | Still **one** REST fetch (measured 43–47 KiB, 36 ms from the Screen) every **20 s**, reduced immediately to the allowlist, diffed in a `StateStore`; widgets only refreshed when something changed; failed fetch backs off 5→10→30→60 s (±10 % jitter); two re-reads after an action instead of one per tap | live-tested |
| – | WebSocket subscription | **Not adopted.** One bulk REST read per 20 s costs ~2.3 KiB/s on average; a socket needs a new dependency on a 512 MB device and reconnect logic for no UI gain. Revisit only if sub-second external updates matter. | decision |
| 2 | Auto-discovery defaults `true` | Example/live config: explicit rooms/scenes/cameras, discovery off | live |
| 3 | Generic two-card Home, 4 tabs, cramped camera buttons | 3 tabs (Home/Lights/Cameras), Settings from Home with a Back button; Home = 4 room tiles + 3 scenes + All Off + Settings; every control ≥44 px tall | live |
| 4 | `QPixmap.loadFromData` on the UI thread, no pixel cap | `camera.py`: header read first, ≤1920×1080 and ≤2.07 MP, decoded to ≤640×360 in the worker; one scaled frame kept, freed on leaving the page; stale results dropped by generation/page/camera check; compressed cap 1 MiB (config, max 3 MiB) with Content-Length + streaming guard | unit-tested; **no real camera exists to test with** |
| 5 | Unbounded action keys | allowlist in `ha_client.service` (light turn_on/off with clamped fields, scene turn_on, configured scripts, the one colour-target helper); 0.6 s per-command coalescing; ≤8 queued; 2 worker threads; blocked while offline | live-tested (offline) |
| 6 | No Colors | Lights → Colors (target ‹ ›, 2 Kelvin + 6 RGB chips, Apply, presets 1–4, Save… → slot → "Overwrite?" confirm) via the existing HA scripts/helper | built, rendered live, **scripts not fired** (would change every light) |
| 7 | Hard-coded "Pi Zero 2 W · No Chromium" | Settings shows HA connected/last update, panel RSS, MemAvailable, CPU temp, uptime, counters, version; the native theme is intentionally **independent** of `input_select.home_panel_theme_mode` (stated on screen) | live |
| 8 | Weather/groups are config references | verified live (inventory doc); BirdNET not shown – no HA entity exists | live |
| 9 | `trusted_networks` bypass for the Screen's IP still in `configuration.yaml` | **Not touched.** The native panel does not use it (it has its own token), so it is probably removable, but a browser/kiosk fallback may still depend on it → separate review | flagged |

## Owner follow-up (§11)

| Feature | State |
|---|---|
| Touch band is the only interactive surface | **Implemented & verified**: header (y<112) and footer (y>442) hold information only. Offscreen test walks every page/sub-view and asserts each visible button/slider/row lies inside y 120…434 (8 px safety). The same layout code falls back to header 84/footer 70 when `touch_band` is null. |
| Individual-light colour editor | **Implemented, live-tested** on `light.wiz_rgbw_tunable_d0dce4`: opened from a room row, chip tap sent nothing, Apply changed it to cyan (`rgb_color [0,220,220]`) ~1.8 s later (including ssh polling overhead), then I restored the original purple/255 through HA. Capability-driven: on/off-only and brightness-only lights show the reason and disable chips; colour-temp lights get Warm/Daylight clamped to their range; RGB lights get the 7 swatches. |
| Room colour | Room header "Color" → same editor; incompatible lights are skipped and the count is shown (tested: `kitchen` temp colour reaches only the temp-capable light) |
| Panel-only room/light arrangement | **Implemented, live-tested** with real taps' coordinates: Edit layout → room ▲▼ / Lights › → Move to… → destination, light ▲▼, Done/Cancel/Reset (Reset needs "Yes, reset"). Cancel wrote nothing; Done wrote `layout.json` (0600) and it survived a panel restart. Nothing is written to HA. |
| Drag-and-drop move | **Not implemented** (the packet allows dropping it: tap-based *Move to…* is the mandatory path; drag on this narrow band would risk conflicts with finger scrolling) |
| Room buttons / All Off use individual panel lights | **Implemented, tested**: room toggle targets only the room's *current* light IDs (never `light.kitchen_lights`); All Off targets the panel's lit individual lights. Live: Kitchen toggle turned its two available lights off and back on. |
| `layout_model.py` API (`load/move_light/reorder_light/reorder_room/validate/commit_atomic/cancel/reset_to_defaults`) | Implemented, 13 unit tests |

## Incident during live testing

While navigating by blind synthetic clicks I once tapped the Home **Kitchen "Turn off"** tile by mistake at ~00:10 (my click script
assumed I was on Settings). Stove Right and the Wiz bulb turned off; I turned them back on with the panel's own tile within ~1 min and
checked HA: Stove Right 56 % (as before), Wiz purple 255 (as before). I also switched the Office light off and on once to time an action.

## Pending / not done

* Finger-on-glass testing of all controls, especially **slider drag inside a drag-scrolled list** (pre-existing QScroller design) and taps at the ±8 px band edges.
* Scenes and the HA colour scripts were not fired.
* No camera entity exists, so snapshot loading/Pause/selector are untested against a real image; `tapo_control` remains disabled.
* 30-minute soak and a cold-boot timing: see `PANEL_PERFORMANCE.md` for what was actually measured.
* Optional P1/P2 integrations (media player, fan, binary sensors, uptime) deliberately not added.
