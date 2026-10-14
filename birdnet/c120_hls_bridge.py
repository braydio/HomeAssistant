#!/usr/bin/env python3

from dotenv import load_dotenv
from pytapo import Tapo
from pytapo.media_stream._utils import StreamType

import asyncio
import contextlib
import json
import os
import pathlib

BASE = pathlib.Path(__file__).resolve().parent
load_dotenv(BASE / "c120.env", override=True)

HOST = os.environ["HOST"]
PASSWORD = os.environ["PASSWORD_CLOUD"]

HLS_DIR = BASE / "hls"
PLAYLIST = HLS_DIR / "c120.m3u8"

HLS_DIR.mkdir(parents=True, exist_ok=True)


# PyTapo's synchronous control API owns its own event loop,
# so authenticate before asyncio.run().
print(f"Connecting to C120 at {HOST}...", flush=True)

cam = Tapo(
    HOST,
    "admin",
    PASSWORD,
    PASSWORD,
    printDebugInformation=False,
)

# Fixes: keep the camera mic unmuted at a fixed volume, and auto-gain
# the audio fed to BirdNET (tunable via c120.env).
MIC_VOLUME = int(os.environ.get("MIC_VOLUME", "80"))
AUTOGAIN_MAX = os.environ.get("AUTOGAIN_MAX", "10")  # max gain factor


def ensure_mic_on():
    cam.setMicrophone(mute=False, volume=MIC_VOLUME)


ensure_mic_on()
mic = cam.getAudioConfig()["audio_config"]["microphone"]

RATE = int(mic["sampling_rate"]) * 1000
ENCODING = str(mic["encode_type"]).lower()

if "ulaw" not in ENCODING:
    raise RuntimeError(
        f"Expected G711 μ-law, got {mic['encode_type']}"
    )

print(
    f"C120: {RATE} Hz mono {mic['encode_type']} "
    f"volume={mic.get('volume')} "
    f"mute={mic.get('mute')} noise_cancel={mic.get('noise_cancelling')}",
    flush=True,
)


def clear_hls():
    for pattern in ("*.m3u8", "*.ts"):
        for f in HLS_DIR.glob(pattern):
            with contextlib.suppress(OSError):
                f.unlink()


async def bridge_once():
    clear_hls()
    try:
        await asyncio.to_thread(ensure_mic_on)
    except Exception as exc:
        print(f"Could not re-assert mic unmute: {exc!r}", flush=True)

    # AUDIO ONLY output.
    # No H.264 is ever passed to this ffmpeg process.
    ffmpeg = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "warning",

        "-f", "mulaw",
        "-ar", str(RATE),
        "-ac", "1",
        "-i", "pipe:0",

        "-vn",
        "-af", f"dynaudnorm=f=250:g=15:m={AUTOGAIN_MAX}:p=0.9",

        "-c:a", "aac",
        "-b:a", "64k",
        "-ar", str(RATE),
        "-ac", "1",

        "-f", "hls",
        "-hls_time", "2",
        "-hls_list_size", "10",
        "-hls_flags", "delete_segments+omit_endlist",
        "-hls_segment_filename",
        str(HLS_DIR / "audio%09d.ts"),

        str(PLAYLIST),

        stdin=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    async def ffmpeg_log():
        while True:
            line = await ffmpeg.stderr.readline()
            if not line:
                return
            print("[ffmpeg]", line.decode(errors="replace").rstrip(), flush=True)

    log_task = asyncio.create_task(ffmpeg_log())

    session = cam.getMediaSession(StreamType.Stream)
    session.set_window_size(50)

    # Keeping HD in the camera request because this is the exact
    # private-stream request that already produced our valid 16 kHz capture.
    # We throw the video payload away below.
    request = json.dumps({
        "type": "request",
        "seq": 1,
        "params": {
            "preview": {
                "audio": ["default"],
                "channels": [0],
                "resolutions": ["HD"],
            },
            "method": "get",
        },
    })

    try:
        async with session:
            stream = session.transceive(
                request,
                no_data_timeout=15,
            )

            async for resp in stream:
                if ffmpeg.returncode is not None:
                    raise RuntimeError(
                        f"ffmpeg exited with {ffmpeg.returncode}"
                    )

                # THIS is the important part:
                # only the private audio payload is forwarded.
                # resp.plaintext contains the H.264/TS video and is discarded.
                if resp.mimetype == "video/mp2t" and resp.audioPayload:
                    ffmpeg.stdin.write(resp.audioPayload)
                    await ffmpeg.stdin.drain()

    finally:
        if ffmpeg.stdin:
            with contextlib.suppress(Exception):
                ffmpeg.stdin.close()

        try:
            await asyncio.wait_for(ffmpeg.wait(), timeout=5)
        except asyncio.TimeoutError:
            ffmpeg.kill()
            await ffmpeg.wait()

        log_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await log_task


async def main():
    while True:
        try:
            print("Starting audio-only C120 bridge...", flush=True)
            await bridge_once()

        except asyncio.CancelledError:
            raise

        except Exception as exc:
            print(f"Bridge error: {exc!r}", flush=True)

        print("Reconnecting in 5 seconds...", flush=True)
        await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
