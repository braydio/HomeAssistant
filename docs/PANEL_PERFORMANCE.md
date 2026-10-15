# Panel performance – measured on the Screen (Pi Zero 2 W, 404 MB usable RAM, DietPi, aarch64)

Everything below was **measured on the Screen** on 2026-10-14/15 unless it says otherwise. Host role: "Screen";
no hostnames/IPs/credentials. Nothing is estimated. Things I could not measure are listed at the end.

## Commands used

```bash
ps -eo pid,rss,%cpu,etimes,args | grep -E '[X]org|[p]anel.py'      # RSS (KiB), lifetime-average CPU
grep -E 'MemAvailable|MemTotal' /proc/meminfo
cat /sys/class/thermal/thermal_zone0/temp                           # millidegrees C
curl -s -o /dev/null -w '%{size_download} B %{time_total}s\n' -H "Authorization: Bearer <token>" http://<home>:8123/api/states
# idle soak: sample /proc/<pid>/status (VmRSS), /proc/<pid>/stat (utime+stime), MemAvailable every 30 s for 10 min
# edit-mode benchmark: QT_QPA_PLATFORM=offscreen python3 bench_edit.py   (demo data, separate process, reads VmRSS)
```

## Baseline (v1, `main@f213bd9`, up 34 min, idle on the Home page)

| Metric | v1 |
|---|---|
| Panel (python3) RSS | 113,944 KiB = **111.3 MiB** |
| Xorg RSS | 89,040 KiB = 87.0 MiB |
| MemAvailable | 231,968 KiB = 226.5 MiB |
| Panel CPU (lifetime average) | 0.4 % |
| SoC temperature | 40.8 °C |
| `GET /api/states` | 43,803 B in 36 ms (all ~94 entities) |
| Poll interval | 12 s, whole payload every time |

## After (v2.0.0, deployed live)

| Metric | v2 | Target in the packet | Result |
|---|---|---|---|
| Panel RSS, idle 10 min | 117,380 → 117,448 KiB (**114.6 MiB**, +68 KiB over 9.5 min) | ≤ 130 MiB | pass (+3.3 MiB / +3 % vs v1, inside the ≤10 % regression allowance too) |
| Xorg RSS | 91,644 KiB flat (89.5 MiB) | – | – |
| MemAvailable, idle | 228,412 – 229,452 KiB (**≈223 MiB**) | > 100 MiB | pass |
| Panel CPU, idle (30 s windows, 20 samples) | mean **0.14 %**, max 0.23 % of one core; Xorg 0 % | < 15 % | pass |
| SoC temperature, idle | 41.3 – 41.9 °C | – | – |
| HA state fetch | 47,412 B per fetch, **every 20 s** (≈2.4 KiB/s average), 1 forecast request per 30 min | no per-second polling | pass |
| Memory growth | +68 KiB in 9.5 min idle | ≤ 15 MiB / 30 min | pass over 10 min (30 min not run) |
| Boot to panel running (reboot command → ssh answering 70 s, panel process 75 s; the first 20 s of that were my fixed wait) | ≈ 50–55 s of actual boot, panel up ≈ 5 s after sshd | – | clean reboot, layout and prefs persisted, no Chromium, SSH fine |
| Right after boot | panel 115,832 KiB, Xorg 87,904 KiB, MemAvailable 218,920 KiB | – | – |

### Edit mode and widgets (offscreen process on the Screen, demo data)

| Step | RSS |
|---|---|
| after start | 55.7 MiB |
| edit mode open (room view) | 56.0 MiB (**+0.3 MiB**; target ≤ 10 MiB) |
| 50 sequential rearrangements (move + reorder + full re-render, then Done) | 56.5 MiB (+0.8); **40 ms each** including re-render |
| 200 open/close cycles of edit mode | 56.7 MiB (+1.0) |
| 40 colour-editor opens with chip picks | 56.7 MiB (+1.0) – no growth |

The Qt-offscreen unit test also asserts the widget count is the same after 10 and after 40 edit-mode open/close cycles.
This process is *not* the live panel (no X server), so its absolute RSS is lower than the live 114 MiB; only the deltas matter.

### Action latency (live, real HA, synthetic X clicks at finger coordinates)

| Action | Observed in HA after the click |
|---|---|
| Office light toggle off | 1.37 s |
| Colour editor Apply (Wiz bulb → cyan) | 1.78 s |
| Chip tap (preview) | no request sent (state unchanged) |

Those include about 1 s of ssh/xdotool overhead, so the panel-to-light time is shorter. Target was ≤ 3 s: pass.
After an action the panel re-reads state at +0.4 s and +2.2 s so a slow device confirmation cannot leave a stale button.

### Offline behaviour (live)

Dropping all traffic from the Screen to the Home Pi for ~55 s (temporary firewall rule, removed): within 35 s the UI showed "Home is offline",
the data age, "Retrying in 10 s", and "Weather was 72 °F Clear night (35 s ago)"; room/tile buttons were disabled and marked "Offline · last known …".
After the rule was removed the panel recovered on its own within the next retry, with no restart.

## Not measured (be honest about these)

* Touch latency with a real finger (only injected X events were used).
* A 30-minute idle soak (10 minutes were run), a 5-minute CPU window on its own (the 10-minute mean is reported), and the "20 camera refreshes" test – **no `camera.*` entity exists**, so camera page RSS/latency is untested; the decode bounds are unit-tested only.
* Per-process PSS (needs root `smaps_rollup`; RSS is reported instead).
* Scenes and the HA colour scripts (they would change every light).
