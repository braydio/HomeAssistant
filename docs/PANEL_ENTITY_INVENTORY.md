# Panel entity inventory (sanitized)

Read on 2026-10-15 (00:05 local) with **one** `GET /api/states` from the Screen using the panel's own token
(94 entities returned, 46 KiB). Only entity IDs, availability and light capabilities are recorded here — no
positions, calendars, camera URLs or attribute dumps. Status words:

* **confirmed** – exists in live HA and the panel uses it
* **configured, unavailable** – exists in HA but reported `unavailable` at read time
* **proposed** – exists, but the panel does *not* use it yet (needs your decision)

## Lights (individual, as shown in the panel rooms)

| Panel room | Entity | Colour modes (from HA) | Status |
|---|---|---|---|
| Kitchen | `light.kitchen_kitchen_stove_right` | color_temp, rgb (2000–7000 K) | confirmed |
| Kitchen | `light.wiz_rgbw_tunable_d0dce4` | color_temp, rgbw (2700–5000 K) | confirmed |
| Kitchen | `light.kitchen_kitchen_stove_left` | color_temp, rgb | configured, unavailable |
| Living Room | `light.living_room_cat_light` | color_temp, rgb | configured, unavailable |
| Living Room | `light.living_room_overhead_living_room` | color_temp, rgb | configured, unavailable |
| Bathroom | `light.bathroom_new_bathroom_light` | color_temp, rgb | confirmed |
| Bathroom | `light.bathroom_bathroom_light` | brightness only | configured, unavailable |
| Bedroom | `light.bedroom_rope_lamp` | color_temp, rgb | configured, unavailable |
| Office | `light.office_office_main_light` | brightness only | confirmed |

The Living Room entry is **pinned** in `config.json` (`rooms[].lights`) because its group entity
`light.living_room_lights` is itself unavailable and therefore exposes no member list.

HA light groups present: `light.all_lights`, `light.kitchen_lights`, `light.bathroom_lights`, `light.living_room_lights`
(used only to derive default room membership, never as a control target by the panel).
**Finding:** each of those four groups also exists as a duplicate `*_2` entity (`light.all_lights_2`,
`light.kitchen_lights_2`, `light.bathroom_lights_2`, `light.living_room_lights_2`). The panel ignores them. They are
probably leftovers from creating the groups twice; removing them is an entity-registry change and was **not** done.

## Scenes, scripts, helpers

| Entity | Use | Status |
|---|---|---|
| `scene.panel_relax`, `scene.panel_bright`, `scene.panel_night_lights` | Home page buttons | confirmed (never fired during testing – it would change real lights) |
| `script.home_panel_apply_color`, `script.home_panel_save_preset`, `script.home_panel_apply_preset` | Lights > Colors | confirmed (not fired in testing; only the helper/preset reads were checked) |
| `input_select.home_panel_color_target` (All, Kitchen, Living Room, Bathroom, Bedroom, Office) | Colors target | confirmed |
| `input_text.home_panel_preset_1..4` | Preset slots (all four currently hold a value) | confirmed |
| `input_select.home_panel_theme_mode` | HA *frontend* theme only; **independent** of the native panel's Auto/Light/Dark | confirmed, deliberately not used |

The colour scripts target the HA groups named by the helper (`light.all_lights`, `light.kitchen_lights`, …), **not**
the panel's virtual rooms. That is why the Colors tab says so on screen.

## Other

| Entity | Use | Status |
|---|---|---|
| `sun.sun` | automatic theme | confirmed |
| `weather.forecast_home` (Met.no) | footer: condition, temperature, humidity, wind, tomorrow | confirmed |
| `camera.*` | Cameras page | **none exist** – the page shows an honest "No camera available" state. `tapo_control` stays disabled. |
| `media_player.living_room_projector`, `media_player.office_echo_pop` | read-only "now playing" line | proposed (not added) |
| `fan.vital_200s_series` | one-touch favourite | proposed (not added; needs your OK before the panel may control it) |
| `binary_sensor.*` (3), `switch.*` (7), `calendar.*` (none), `sensor.uptime` | status badges | not reviewed / not added |

BirdNET: the C120 bridge in this repo only produces audio (HLS); there is no detection entity in HA, so nothing is
displayed for it and nothing was invented.
