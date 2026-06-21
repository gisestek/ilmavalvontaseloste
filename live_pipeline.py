#!/usr/bin/env python3
"""Continuous voice pipeline: mic -> whisper.cpp (VAD-gated) -> parser -> app server.

Records continuously into a single rolling file (restarted periodically to cap
its size) and, on a shorter stride, extracts an overlapping WINDOW-second tail
slice for transcription. The overlap means a report that would otherwise be
split across a hard chunk boundary is fully contained in at least one window.
Parsed reports are deduplicated by (id, mgrs, direction) so the same report
caught in two overlapping windows isn't sent twice.

Also exposes input-device selection and a live VU meter to the frontend:
- devices.json: list of available PipeWire audio sources (refreshed periodically)
- level.json: current mic input level, 0-100 (refreshed ~4x/sec by a background thread)
- config.json: written by the frontend (via server.py's /config endpoint) to pick
  a device; this script reapplies it by restarting the recorder when it changes.

Run on the machine with whisper.cpp built and models downloaded (see
memory/project_voice_report_format.md for the report format this expects).
"""
import json
import math
import os
import signal
import struct
import subprocess
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parser import split_into_reports, is_usable, send_to_app  # noqa: E402

WHISPER_DIR = os.path.expanduser("~/whisper.cpp")
MODEL = f"{WHISPER_DIR}/models/ggml-small.bin"
VAD_MODEL = f"{WHISPER_DIR}/models/ggml-silero-v5.1.2.bin"
WHISPER_BIN = f"{WHISPER_DIR}/build/bin/whisper-cli"
THREADS = "8"
WAKE_WORD = "maali"

APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(APP_DIR, "config.json")
DEVICES_FILE = os.path.join(APP_DIR, "devices.json")
LEVEL_FILE = os.path.join(APP_DIR, "level.json")
TRANSCRIPTS_FILE = os.path.join(APP_DIR, "transcripts.json")
MAX_TRANSCRIPTS = 30

ROLLING_WAV = "/tmp/rolling.wav"
WINDOW_SECONDS = 30      # length of each transcribed slice
STRIDE_SECONDS = 10      # how often a new slice is taken (overlap = WINDOW - STRIDE)
ROLLING_RESTART_SECONDS = 600  # restart the rolling recorder periodically to cap file size

DEDUP_WINDOW_SECONDS = 90  # forget a (id, mgrs, direction) after this long, allow re-report

DEVICE_REFRESH_SECONDS = 5
LEVEL_REFRESH_SECONDS = 0.25
LEVEL_WINDOW_BYTES = 16000 * 2 // 4  # ~0.25s of s16le mono 16kHz audio

IGNORE_PREFIXES = ("whisper_", "main:", "system_info", "ggml_", "read_audio")

_stop_event = threading.Event()


# --- Recorder management ---

def start_rolling_recorder(device_id=None):
    if os.path.exists(ROLLING_WAV):
        os.remove(ROLLING_WAV)
    cmd = ["pw-record", "--rate", "16000", "--channels", "1", "--format", "s16"]
    if device_id:
        cmd += ["--target", str(device_id)]
    cmd.append(ROLLING_WAV)
    return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def read_config_device_id():
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get("deviceId") or None
    except (FileNotFoundError, json.JSONDecodeError):
        return None


# --- Device listing (for the frontend's device selector) ---

def list_audio_sources():
    """Parse `wpctl status` for PipeWire audio source nodes."""
    result = subprocess.run(["wpctl", "status"], capture_output=True, text=True)
    lines = result.stdout.splitlines()
    sources = []
    in_sources_section = False
    for line in lines:
        if "Sources:" in line and "endpoints" not in line:
            in_sources_section = True
            continue
        if in_sources_section:
            if "Source endpoints:" in line or "Streams:" in line or line.strip() == "":
                if "Source endpoints:" in line or "Streams:" in line:
                    in_sources_section = False
                continue
            m = re_node_line(line)
            if m:
                sources.append(m)
    return sources


def re_node_line(line):
    import re
    match = re.search(r"(\*?)\s*(\d+)\.\s*(.+?)\s*\[vol", line)
    if not match:
        return None
    node_id, name = match.group(2), match.group(3).strip()
    return {"id": node_id, "name": name}


def devices_refresh_loop():
    while not _stop_event.is_set():
        try:
            sources = list_audio_sources()
            current = read_config_device_id()
            with open(DEVICES_FILE, "w", encoding="utf-8") as f:
                json.dump({"sources": sources, "selected": current}, f)
        except Exception:
            pass
        _stop_event.wait(DEVICE_REFRESH_SECONDS)


# --- VU meter ---

def compute_level():
    """RMS of the last ~0.25s of the rolling recording, scaled to 0-100."""
    try:
        size = os.path.getsize(ROLLING_WAV)
    except OSError:
        return 0
    if size <= 44:  # just the wav header, no audio yet
        return 0
    read_size = min(LEVEL_WINDOW_BYTES, size - 44)
    read_size -= read_size % 2  # keep it sample-aligned (2 bytes per s16 sample)
    if read_size <= 0:
        return 0
    try:
        with open(ROLLING_WAV, "rb") as f:
            f.seek(size - read_size)
            raw = f.read(read_size)
    except OSError:
        return 0

    sample_count = len(raw) // 2
    if sample_count == 0:
        return 0
    samples = struct.unpack(f"<{sample_count}h", raw[: sample_count * 2])
    rms = math.sqrt(sum(s * s for s in samples) / sample_count)
    # 16-bit full scale is 32768; map RMS to a 0-100 scale with a touch of headroom
    level = min(100, round((rms / 32768) * 100 * 4))
    return level


def level_refresh_loop():
    while not _stop_event.is_set():
        try:
            level = compute_level()
            with open(LEVEL_FILE, "w", encoding="utf-8") as f:
                json.dump({"level": level}, f)
        except Exception:
            pass
        _stop_event.wait(LEVEL_REFRESH_SECONDS)


# --- Transcription ---

def get_duration_seconds(path):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def extract_tail_slice(src_path, dst_path, window_seconds):
    duration = get_duration_seconds(src_path)
    if duration <= 0:
        return False
    start = max(0.0, duration - window_seconds)
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-ss", str(start), "-i", src_path, dst_path],
        check=False,
    )
    return os.path.exists(dst_path)


def transcribe(path):
    result = subprocess.run(
        [WHISPER_BIN, "-m", MODEL, "-f", path, "-l", "fi", "-t", THREADS,
         "-nt", "--vad", "-vm", VAD_MODEL],
        capture_output=True, text=True,
    )
    lines = [
        line.strip() for line in result.stdout.splitlines()
        if line.strip() and not line.startswith(IGNORE_PREFIXES)
    ]
    return " ".join(lines)


def report_key(report):
    return (report["id"], report["mgrsRaw"], report["direction"])


def append_transcript(text):
    """Record every non-empty raw transcript (whether or not it had a wake
    word or parsed cleanly) so a debug view can show what whisper is actually
    hearing, independent of the parser/quality gate."""
    try:
        with open(TRANSCRIPTS_FILE, "r", encoding="utf-8") as f:
            items = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        items = []
    items.append({"text": text, "timestamp": int(time.time() * 1000)})
    items = items[-MAX_TRANSCRIPTS:]
    with open(TRANSCRIPTS_FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False)


def _handle_sigterm(signum, frame):
    raise SystemExit(0)


def main():
    signal.signal(signal.SIGTERM, _handle_sigterm)

    print(f"Live pipeline started. window={WINDOW_SECONDS}s stride={STRIDE_SECONDS}s "
          f"model={os.path.basename(MODEL)}", flush=True)

    threading.Thread(target=devices_refresh_loop, daemon=True).start()
    threading.Thread(target=level_refresh_loop, daemon=True).start()

    current_device_id = read_config_device_id()
    recorder = start_rolling_recorder(current_device_id)
    recorder_started_at = time.time()
    seen = {}  # report_key -> last_sent_timestamp

    try:
        while True:
            time.sleep(STRIDE_SECONDS)

            desired_device_id = read_config_device_id()
            device_changed = desired_device_id != current_device_id
            rolling_expired = time.time() - recorder_started_at > ROLLING_RESTART_SECONDS

            if device_changed or rolling_expired:
                recorder.terminate()
                recorder.wait(timeout=5)
                current_device_id = desired_device_id
                recorder = start_rolling_recorder(current_device_id)
                recorder_started_at = time.time()
                continue  # give the new recorder a moment to accumulate audio

            slice_path = "/tmp/window_slice.wav"
            if not extract_tail_slice(ROLLING_WAV, slice_path, WINDOW_SECONDS):
                continue

            text = transcribe(slice_path)
            if not text:
                continue

            print(f"[transkripti] {text}", flush=True)
            append_transcript(text)

            if WAKE_WORD not in text.lower():
                continue

            now = time.time()

            for report in split_into_reports(text):
                if not is_usable(report):
                    print(f"  -> ohitettu (puutteellinen): id={report['id']} "
                          f"mgrs={report['mgrsRaw']}", flush=True)
                    continue

                key = report_key(report)
                last_sent = seen.get(key)
                if last_sent and now - last_sent < DEDUP_WINDOW_SECONDS:
                    continue  # same report already sent from an earlier overlapping window

                print(f"  -> jäsennetty: id={report['id']} mgrs={report['mgrsRaw']} "
                      f"varoitukset={report['_warnings']}", flush=True)

                try:
                    ack = send_to_app(report)
                    print(f"  -> lähetetty: {ack}", flush=True)
                    seen[key] = now
                except Exception as e:
                    print(f"  -> lähetys epäonnistui: {e}", flush=True)
    finally:
        _stop_event.set()
        recorder.terminate()


if __name__ == "__main__":
    main()
