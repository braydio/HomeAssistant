# Log Watcher Integration

The Log Watcher custom integration provides a lightweight way to monitor the
health of Home Assistant log files. It exposes a sensor that counts the number
of log lines at or above a configured severity level.

## Configuration

Add the following to your `configuration.yaml`:

```yaml
sensor:
  - platform: logwatcher
    name: HA Log Warnings
    file_path: home-assistant.log
    severity: WARNING
    scan_interval: "00:05:00"
```

### Options

| Option         | Required | Default       | Description |
| -------------- | -------- | ------------- | ----------- |
| `name`         | No       | `Log Watcher` | Friendly name for the sensor. |
| `file_path`    | Yes      | —             | Path to the log file to monitor. Relative paths are resolved against the Home Assistant configuration directory. |
| `severity`     | No       | `WARNING`     | Lowest severity level to count (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`). |
| `scan_interval`| No       | `00:05:00`    | How often to re-count the log entries. |

## Attributes

The sensor exposes the following additional state attributes:

- `file_path` – The absolute path to the monitored log file.
- `severity` – The severity threshold applied when counting log entries.

## Use Cases

- Keep an eye on the volume of warnings and errors in your Home Assistant log.
- Create automations that alert you if a sudden spike in errors occurs.
- Track the long-term health of Home Assistant after upgrades or configuration changes.
