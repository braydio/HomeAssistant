# Device and Assistant Setup

## Discovering Devices

Use the [`device_scanner.py`](../scripts/device_scanner.py) utility to probe a
network range for active hosts:

```bash
python scripts/device_scanner.py --network 192.168.1.0/24 --port 80
```

## Adding a Roomba

1. Put the Roomba in pairing mode by holding **SPOT** + **CLEAN** + **HOME** until
a tone plays.
2. Obtain the BLID and password using the [irobot](https://pypi.org/project/irobot/)
   helper:
   ```bash
   python -m irobot.getpassword <roomba-ip>
   ```
3. Add the credentials to `configuration.yaml` or through the UI using the
   `iRobot` integration.

## Adding Amazon Alexa Devices

1. Install [HACS](https://hacs.xyz/) and from it add the
   "Alexa Media Player" integration.
2. Through Home Assistant's UI, configure the integration with your Amazon
   account.
3. Alexa devices will appear as media players and can be targeted via the
   `notify.alexa_media` service for TTS announcements.

## Local Wyoming Assistant

The configuration includes a local Assist pipeline backed by Wyoming‑compatible
STT and TTS services running at `192.168.1.239`. To customise:

1. Run compatible services (e.g. [`whisper`](https://github.com/ggerganov/whisper.cpp)
   for STT and [`piper`](https://github.com/rhasspy/piper) for TTS) using the
   Wyoming protocol.
2. Adjust the host/port values in `configuration.yaml` if needed.
3. Use the **Assist** UI or voice commands to interact with the local assistant.
