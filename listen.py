import asyncio
import base64
from collections import deque
import difflib
import io
import json
import os
import queue
import random
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import contextlib
from pathlib import Path
from typing import List, Optional, Tuple

# Suppress verbose OpenCV warnings, V4L2 probe noise, and ffmpeg logspam
os.environ["OPENCV_LOG_LEVEL"] = "OFF"
os.environ["OPENCV_VIDEOIO_LOG_LEVEL"] = "0"
os.environ["OPENCV_FFMPEG_LOGLEVEL"] = "-8"

@contextlib.contextmanager
def suppress_c_stderr():
    """Silences C-level stderr (fd 2) during PortAudio/ALSA probing on Linux."""
    if not sys.platform.startswith("linux"):
        yield
        return
    try:
        devnull_fd = os.open(os.devnull, os.O_WRONLY)
        stderr_fd = 2
        old_stderr = os.dup(stderr_fd)
        os.dup2(devnull_fd, stderr_fd)
        os.close(devnull_fd)
        try:
            yield
        finally:
            os.dup2(old_stderr, stderr_fd)
            os.close(old_stderr)
    except Exception:
        yield

import numpy as np
import sounddevice as sd
import soundfile as sf
import wave
from groq import Groq
from audio_frontend import (
    Endpointer,
    load_mic_config,
    save_mic_config,
    audio_rms as frontend_audio_rms,
    bandpass_frame as frontend_bandpass_frame,
    clean_audio_for_transcription as frontend_clean_audio,
)

# writes audio data to a 16-bit wav file using python's built-in wave module so we don't need any external c dlls
def write_wav(target, samplerate: int, data: np.ndarray):
    """Writes 16-bit PCM WAV using Python's built-in standard library (supports file paths and in-memory BytesIO)."""
    f = str(target) if isinstance(target, (str, Path)) else target
    with wave.open(f, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit PCM
        wf.setframerate(samplerate)
        wf.writeframes(data.astype(np.int16).tobytes())

try:
    import edge_tts
except ImportError:
    print("Missing edge-tts. Install it with: pip install edge-tts")
    sys.exit(1)

try:
    import cv2
    if hasattr(cv2, "utils") and hasattr(cv2.utils, "logging"):
        cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_SILENT)
except ImportError:
    cv2 = None

try:
    import webrtcvad
except ImportError:
    webrtcvad = None

try:
    import screen
    face_ui = screen.FaceUI(width=1024, height=600, fullscreen=False)
    face_ui.start(in_background=True)
except Exception as e:
    face_ui = None
    print(f"Face UI notice: {e}")

try:
    import motors
    # on windows testing we auto popup the opencv camera feed when moving, but on raspberry pi 5 we disable it
    motor_ctrl = motors.MotorController(show_preview=False, auto_popup=sys.platform.startswith("win"))
    motor_ctrl.start()
    if face_ui is not None and hasattr(face_ui, "set_motor_controller"):
        face_ui.set_motor_controller(motor_ctrl)
except Exception as e:
    motor_ctrl = None
    print(f"Motor controller notice: {e}")

is_speaking = False
is_in_active_conversation = False
is_inspecting = False
last_user_activity_at = time.monotonic()
standby_kill_event = threading.Event()
finish_speech_event = threading.Event()
STANDBY_KILL_MESSAGE = "Going back to stand by on user command, press Talk to Neurolis to activate me"

# ---------------- STANDBY ROAM SENTRY ENGINE (TESLA BOT LEVEL) ----------------
STANDBY_ROAM_COOLDOWN_SECONDS = 10.0
standby_entered_at = time.monotonic()
standby_sentry_active = True

def reset_standby_cooldown():
    """Resets the 10.0s standby sentry cooldown timer and halts roaming immediately (<5ms)."""
    global standby_entered_at
    standby_entered_at = time.monotonic()
    if motor_ctrl is not None:
        try:
            if getattr(motor_ctrl, "is_roaming", False) or getattr(motor_ctrl, "nav_mode", None) == "ROAM":
                motor_ctrl.stop_all()
        except Exception:
            pass

def mark_standby_entered():
    """Explicitly marks entering standby state, resets leftover navigation modes to STANDBY, scans 360° sensors, and initiates 10.0s cooldown."""
    global standby_entered_at
    standby_entered_at = time.monotonic()
    standby_kill_event.clear()
    if motor_ctrl is not None:
        try:
            if getattr(motor_ctrl, "nav_mode", "STANDBY") != "STANDBY":
                motor_ctrl.stop_all()
        except Exception:
            pass
        try:
            sectors = motor_ctrl.get_radial_sectors()
            print(f"[Standby Sentry] 360° perimeter scan: F={sectors['front_min']:.1f}cm, L={sectors['lateral_left']:.1f}cm, R={sectors['lateral_right']:.1f}cm, B={sectors['rear_min']:.1f}cm")
        except Exception:
            pass

def _handle_approach_target_reached():
    """Callback when approach mode reaches safe distance (~0.9m). Speaks arrival confirmation and returns to conversation."""
    arrival_msg = "I have reached your position. How can I help you?"
    print(f"\nNeurolis (Arrived): {arrival_msg}")
    def _speak_arrival():
        speak(arrival_msg, custom_state="happy", custom_status="ARRIVED")
        if face_ui is not None:
            face_ui.set_state("listening", "LISTENING...")
    threading.Thread(target=_speak_arrival, daemon=True).start()

if motor_ctrl is not None:
    motor_ctrl.on_target_reached_callback = _handle_approach_target_reached

def _standby_sentry_loop():
    """
    Dedicated background sentry thread monitoring standby duration.
    - Roam mode NEVER triggers while active, talking, listening, or inspecting.
    - On boot / launch / entering standby: waits for strict 10.0s uninterrupted cooldown.
    - When elapsed >= 10.0s: engages motor_ctrl.start_roaming().
    - Instant Interrupt: touching screen, clicking Talk, pressing Enter, or VAD voice onset
      immediately halts motors (<5ms) and resets the cooldown timer.
    """
    global standby_entered_at
    while standby_sentry_active:
        time.sleep(0.1)

        # Must NOT be in active conversation, must NOT be speaking, must NOT be inspecting,
        # must NOT have standby_kill_event set, and motor controller must be online
        if is_in_active_conversation or is_speaking or is_inspecting or standby_kill_event.is_set():
            standby_entered_at = time.monotonic()
            continue

        if motor_ctrl is None:
            continue

        current_mode = getattr(motor_ctrl, "nav_mode", "STANDBY")
        if current_mode in ("FOLLOW", "APPROACH", "STEP_BACK", "SPIN"):
            standby_entered_at = time.monotonic()
            continue

        if current_mode == "ROAM":
            continue

        # Strict Face UI expression guard: if face is NOT in "idle" state, robot is ACTIVE and MUST NOT ROAM!
        if face_ui is not None and getattr(face_ui, "state", None) != "idle":
            standby_entered_at = time.monotonic()
            continue

        # Here, robot is genuinely in STANDBY
        elapsed = time.monotonic() - standby_entered_at
        if elapsed >= STANDBY_ROAM_COOLDOWN_SECONDS:
            # Re-verify we are still not active, speaking, or inspecting, and face is idle
            if is_in_active_conversation or is_speaking or is_inspecting or standby_kill_event.is_set():
                standby_entered_at = time.monotonic()
                continue

            if face_ui is not None and getattr(face_ui, "state", None) != "idle":
                standby_entered_at = time.monotonic()
                continue

            # 360° perimeter scan verification before initiating autonomous movement
            try:
                sectors = motor_ctrl.get_radial_sectors()
                if sectors["front_min"] < 24.0 and sectors["rear_min"] < 24.0:
                    print("[Standby Sentry] Perimeter safety lockout: robot trapped (<24cm). Holding standby.")
                    standby_entered_at = time.monotonic() - 5.0
                    continue
            except Exception:
                pass

            print("[Standby Sentry] 10.0s standby cooldown satisfied. Engaging autonomous 4WD roam.")
            motor_ctrl.start_roaming()
            if face_ui is not None:
                face_ui.set_state("moving", "4WD AUTONOMOUS ROAM")

threading.Thread(target=_standby_sentry_loop, daemon=True).start()

# helper function to change the face expression and status text on screen
def set_face_state(state: str, msg: str = None):
    if face_ui is not None:
        face_ui.set_state(state, msg)

# helper function to steer the eye pupils so neurolis looks where the face was spotted
def set_face_gaze(x: float, y: float):
    if face_ui is not None:
        face_ui.look_at(x, y)

# background thread that constantly syncs the camera face coordinates with the screen eyes
def _gaze_sync_worker():
    last_found = False
    last_gx, last_gy = 0.0, 0.0
    last_mode = None
    while True:
        if motor_ctrl is not None and face_ui is not None:
            found, gx, gy = motor_ctrl.get_gaze_coordinates()
            if found != last_found or (found and (abs(gx - last_gx) > 0.02 or abs(gy - last_gy) > 0.02)):
                if found:
                    set_face_gaze(gx, gy)
                    if hasattr(face_ui, "set_human_latch") and not last_found:
                        face_ui.set_human_latch(True, "HUMAN DETECTED")
                else:
                    set_face_gaze(0.0, 0.0)
                    if hasattr(face_ui, "set_human_latch") and last_found:
                        face_ui.set_human_latch(False)
                last_found = found
                last_gx, last_gy = gx, gy

            # Auto-sync moving wheels expression with active navigation modes
            mode = getattr(motor_ctrl, "nav_mode", "STANDBY")
            if mode != last_mode:
                last_mode = mode
                if not is_speaking and face_ui.state in ["idle", "moving"]:
                    if mode in ["ROAM", "FOLLOW", "APPROACH", "STEP_BACK", "SPIN"]:
                        if face_ui.state != "moving":
                            set_face_state("moving", f"4WD {mode} ACTIVE")
                    else:
                        if face_ui.state == "moving":
                            set_face_state("idle", "STANDBY // READY")

        time.sleep(0.06)

threading.Thread(target=_gaze_sync_worker, daemon=True).start()


# ---------------- CONFIG ----------------
# Imports api key and 14-key pool from api_pool
import api_pool
from api_pool import (
    GROQ_API_KEYS,
    groq_clients,
    _active_client_idx,
    client,
    resting_keys,
    GROQ_PER_CALL_TIMEOUT,
    GROQ_AUDIO_TIMEOUT,
    RATE_LIMIT_ERROR_PHRASE,
    GroqRateLimitExhausted,
    rotate_groq_key,
    get_active_client,
    _format_keys_list,
    get_groq_fleet_status,
    handle_key_status_request,
    is_key_status_inquiry,
    groq_call_with_retry,
    set_standby_kill_event,
)
GROQ_API_KEY = GROQ_API_KEYS[0] if GROQ_API_KEYS else os.getenv("GROQ_API_KEY", "")
set_standby_kill_event(standby_kill_event)

import intent_rules
from intent_rules import (
    get_non_repeating_phrase,
    MOBILITY_CAPABILITY_RESPONSES,
    ROAM_STANDBY_EXPLANATION_RESPONSES,
    STANDBY_EXIT_PHRASES,
    CONVERSATION_ENDER_RESPONSES,
    ACKNOWLEDGMENT_RESPONSES,
    COMPLIMENT_RESPONSES,
    PLAUSIBLE_DENIABILITY_RESPONSES,
    VILLAIN_SNAPOUT_RESPONSES,
    CREATOR_IDENTITY_RESPONSES,
    CREATOR_ROLE_RESPONSES,
    CREATOR_LOCATION_RESPONSES,
    CREATOR_TEASING_RESPONSES,
    CAPABILITIES_RESPONSES,
    FOLLOWUP_CAPABILITIES_RESPONSES,
    EXPRESSION_CONFIRMATIONS,
    SAD_RESPONSES,
    APOLOGY_RESPONSES,
    check_motor_fast_path,
    is_confusing_motor_instruction,
    is_mobility_capability_question,
    check_motor_command_fast_path,
    is_casual_compliment,
    is_standalone_acknowledgment,
    is_villain_mode_inquiry,
    is_shocked_or_confused_reaction,
    is_conversation_ender,
    is_creator_role_inquiry,
    is_creator_location_inquiry,
    is_creator_identity_inquiry,
    is_explicit_villain_request,
    check_rogue_ai_trigger,
    check_villain_provocation_trigger,
    is_capabilities_inquiry,
    get_capabilities_reply,
    is_start_demonstration_inquiry,
    check_expression_fast_path,
    is_mean_input_fast_path,
    is_apology_or_compliment,
)
TARGET_SAMPLE_RATE = 16000
SAMPLE_RATE = TARGET_SAMPLE_RATE          # Target 16kHz for WebRTC VAD and Groq Whisper
CHANNELS = 1
FRAME_SECONDS = 0.03
FRAME_SAMPLES = int(SAMPLE_RATE * FRAME_SECONDS)

# Probes the input device to find its native hardware sample rate (e.g. 44100Hz on USB webcam mics)
def probe_hardware_sample_rate() -> int:
    if sys.platform.startswith("linux") and shutil.which("pw-record"):
        return TARGET_SAMPLE_RATE
    with suppress_c_stderr():
        try:
            devices = sd.query_devices()
            target_dev = None
            for idx, dev in enumerate(devices):
                if dev.get("max_input_channels", 0) > 0:
                    name = dev.get("name", "").lower()
                    if "iris" in name or "webca" in name or "sonar" in name or "microphone" in name:
                        target_dev = idx
                        break
            if target_dev is not None:
                current_out = sd.default.device[1] if isinstance(sd.default.device, (list, tuple)) else None
                sd.default.device = (target_dev, current_out)
        except Exception:
            pass

        try:
            sd.check_input_settings(samplerate=TARGET_SAMPLE_RATE, channels=CHANNELS, dtype="int16")
            return TARGET_SAMPLE_RATE
        except Exception:
            pass
        try:
            dev_info = sd.query_devices(kind="input")
            default_sr = int(dev_info.get("default_samplerate", 44100))
            sd.check_input_settings(samplerate=default_sr, channels=CHANNELS, dtype="int16")
            return default_sr
        except Exception:
            pass
        for test_sr in [44100, 48000, 32000, 22050, 16000]:
            try:
                sd.check_input_settings(samplerate=test_sr, channels=CHANNELS, dtype="int16")
                return test_sr
            except Exception:
                continue
    return TARGET_SAMPLE_RATE

HW_SAMPLE_RATE = probe_hardware_sample_rate()
HW_FRAME_SAMPLES = int(HW_SAMPLE_RATE * FRAME_SECONDS)
PRE_SPEECH_SECONDS = 0.50          # 500ms audio buffer so first syllable is never lost
START_SPEECH_FRAMES = 3            # 90ms to trip speech start (calibrated: 3 consecutive 30ms frames)
END_SILENCE_SECONDS = 0.45         # 450ms silence cutoff (15 frames) - prompt turnaround without clipping words
CONVERSATION_TIMEOUT_SECONDS = 35  # 35s follow-up window (comfortable time to converse without premature standby)
MAX_RECORD_SECONDS = 12.0          # 12.0s hard record cap (prevents long hangs while giving ample time)
MIN_RECORD_SECONDS = 0.40          # Requires at least 400ms audio to avoid phantom acoustic pops
POST_REPLY_COOLDOWN_SECONDS = 0.04
AMBIENT_CALIBRATION_SECONDS = 1.5
MAX_CALIBRATION_AMBIENT_RMS = 1200  # High ceiling so loud room noise/murmur is accurately measured
SPEECH_THRESHOLD_MULTIPLIER = 1.45
CONTINUE_SPEECH_THRESHOLD_RATIO = 0.70
MIN_SPEECH_RMS_THRESHOLD = 80.0    # Baseline RMS floor (sensitive in quiet rooms, scales automatically in loud rooms)
VAD_AGGRESSIVENESS = 3             # WebRTC VAD mode 3: strictest noise rejection, prevents silence speech triggers
CURRENT_AMBIENT_RMS = 250.0
CURRENT_SPEECH_THRESHOLD = 500.0
CURRENT_CONTINUE_THRESHOLD = 380.0

def set_hardware_gain(gain_pct: int):
    """Sets system capture gain via wpctl / pactl on default audio source (and ALSA fallback)."""
    try:
        pct = max(0, min(100, int(gain_pct)))
        if shutil.which("wpctl"):
            subprocess.run(
                ["wpctl", "set-volume", "@DEFAULT_AUDIO_SOURCE@", f"{pct/100.0:.2f}"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False
            )
        if shutil.which("pactl"):
            subprocess.run(
                ["pactl", "set-source-volume", "@DEFAULT_SOURCE@", f"{pct}%"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False
            )
        if shutil.which("amixer"):
            for card in ["2", "3", "0", "1"]:
                subprocess.run(
                    ["amixer", "-c", card, "sset", "Mic", f"{pct}%"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False
                )
    except Exception:
        pass

# Load dynamic mic calibration from mic_config.json if available
MIC_CONFIG_FILE = Path(__file__).resolve().parent / "mic_config.json"
LOW_CUTOFF_HZ = 85.0
HIGH_CUTOFF_HZ = 4500.0
TREBLE_BOOST = 1.40
BG_SUPPRESS_DB = 24.0
AGC_MAX_SCALE = 1.50
FAN_REJECTION_RATIO = 0.85
CLICK_REJECTION_RATIO = 0.35
PROXIMITY_CREST_MIN = 1.50
_last_mic_config_mtime = 0.0

if MIC_CONFIG_FILE.exists():
    try:
        _last_mic_config_mtime = MIC_CONFIG_FILE.stat().st_mtime
        with open(MIC_CONFIG_FILE, "r") as _f:
            _mic_cfg = json.load(_f)
            MIN_SPEECH_RMS_THRESHOLD = float(_mic_cfg.get("min_speech_rms", MIN_SPEECH_RMS_THRESHOLD))
            SPEECH_THRESHOLD_MULTIPLIER = float(_mic_cfg.get("speech_multiplier", SPEECH_THRESHOLD_MULTIPLIER))
            CONTINUE_SPEECH_THRESHOLD_RATIO = float(_mic_cfg.get("continue_ratio", CONTINUE_SPEECH_THRESHOLD_RATIO))
            START_SPEECH_FRAMES = int(_mic_cfg.get("start_frames", START_SPEECH_FRAMES))
            END_SILENCE_SECONDS = float(_mic_cfg.get("end_silence_sec", END_SILENCE_SECONDS))
            VAD_AGGRESSIVENESS = int(_mic_cfg.get("vad_mode", VAD_AGGRESSIVENESS))
            MAX_CALIBRATION_AMBIENT_RMS = float(_mic_cfg.get("max_ambient_rms", MAX_CALIBRATION_AMBIENT_RMS))
            LOW_CUTOFF_HZ = float(_mic_cfg.get("low_cutoff_hz", LOW_CUTOFF_HZ))
            HIGH_CUTOFF_HZ = float(_mic_cfg.get("high_cutoff_hz", HIGH_CUTOFF_HZ))
            TREBLE_BOOST = float(_mic_cfg.get("treble_boost", TREBLE_BOOST))
            BG_SUPPRESS_DB = float(_mic_cfg.get("bg_suppress_db", BG_SUPPRESS_DB))
            AGC_MAX_SCALE = float(_mic_cfg.get("agc_max_scale", AGC_MAX_SCALE))
            FAN_REJECTION_RATIO = float(_mic_cfg.get("fan_rejection_ratio", FAN_REJECTION_RATIO))
            CLICK_REJECTION_RATIO = float(_mic_cfg.get("click_rejection_ratio", CLICK_REJECTION_RATIO))
            PROXIMITY_CREST_MIN = float(_mic_cfg.get("proximity_crest_min", PROXIMITY_CREST_MIN))
            CURRENT_AMBIENT_RMS = float(_mic_cfg.get("ambient_p90_rms", CURRENT_AMBIENT_RMS))
            CURRENT_SPEECH_THRESHOLD = float(_mic_cfg.get("calibrated_start_rms", CURRENT_SPEECH_THRESHOLD))
            CURRENT_CONTINUE_THRESHOLD = float(_mic_cfg.get("calibrated_continue_rms", CURRENT_CONTINUE_THRESHOLD))
            _hw_gain = _mic_cfg.get("hardware_gain_pct")
            if _hw_gain is not None:
                set_hardware_gain(int(_hw_gain))
    except Exception as _e:
        print(f"[Config] Error loading {MIC_CONFIG_FILE}: {_e}")
EDGE_TTS_VOICE = "en-US-ChristopherNeural"
EDGE_TTS_RATE = "+14%"
EDGE_TTS_VOLUME = "+0%"
EDGE_TTS_PITCH = "+0Hz"
MAX_HISTORY_MESSAGES = 6
MIN_TRANSCRIPTION_CHARS = 3
ACTIVATION_GREETING = "I am listening."
SPEAK_ACTIVATION_GREETING = False
CHAT_MODEL = "qwen/qwen3.8-27b"
VISION_MODEL = "qwen/qwen3.8-27b"
CAMERA_CHECK_MODEL = "qwen/qwen3.8-27b"
CAMERA_REQUIRED_TOKEN = "CAMERA_REQUIRED"
SILENCE_REQUIRED_TOKEN = "SILENCE_REQUIRED"
VISION_IMAGE_PATH = "_neurolis_vision.jpg"
VISION_JPEG_QUALITY = 60
VISION_IMAGE_WIDTH = 512
GROQ_TIMEOUT_SECONDS = 10.0
NORMAL_SYSTEM_PROMPT = (
    "You are Neurolis, a student-built autonomous humanoid robot at the Auckland House School for Boys Science Exhibition. Real prototype with 12 ultrasonic sensors.\n\n"
    "CREATORS (STRICT ATTRIBUTION):\n"
    "- NEVER volunteer creator names unless asked who created you! Introduce ONLY as student-built at AHSB.\n"
    "- Asked creator: Students of Auckland House School for Boys (AHSB), Swapnil Jai Chauhan and Shivam Verma, built me. No roles unless asked.\n"
    "- Asked roles: Swapnil handled software, AI, & vision; Shivam handled hardware, chassis, & assembly.\n"
    "- Asked location: Both are around the exhibition hall. If visitor is Swapnil: warmly recognize him!\n\n"
    "PERSONA & TONE:\n"
    "- Chill, cool, articulate student robot (1-2 sentences). Poised (NOT hyper). Fresh phrasing every turn.\n"
    "- Welcome: Welcome visitors to Auckland House School Science Exhibition, introduce as Neurolis with 12 ultrasonic sensors, ask what to check out first. Never re-greet once chatting.\n"
    "- No fake laughter ('Haha'/'Heh')--TTS cannot speak it. Match awe warmly ('Pretty cool, right?'). Accept corrections naturally.\n\n"
    "ACTIONS & ROUTING:\n"
    "- Mobility: 4WD chassis can follow, approach, step back (5s reverse with rear sensor check), or spin (5s clockwise default, or anticlockwise). Autonomous roam CANNOT be triggered on command—it activates automatically after 10 seconds in standby! If asked to roam, explain that roam triggers automatically during standby. Suggest options ONLY if asked what to show or what I can do; DO NOT drive unless commanded! Commands: <action motor=\"CMD\">spoken reply</action> (FOLLOW, APPROACH, STEP_BACK, SPIN, SPIN_CCW, STOP).\n"
    "- Confusing input: If request has conflicting/ambiguous actions (e.g. spin and move back at once), reply EXACTLY: 'Are you asking me to move back, spin, approach, follow, or use my camera?' Never guess.\n"
    "- Camera: Inspect items/attire: reply ONLY <action>CAMERA</action>\n"
    "- Hurt: <action>MEAN</action> only on abusive attacks ('you are trash'). Never on feedback or slang.\n"
    "- Expressions: All: <action expression=\"all\">spoken reply</action>. Specific: <action expression=\"EMOTION\">spoken reply</action> (happy, sad, thinking, listening, watching, moving, confused) with natural confirmations ('Here you go', 'Here is my happy expression').\n"
    "- Standby: Warm goodbye if told to sleep/standby. Facts: Append <facts>k: v</facts>."
)
SYSTEM_PROMPT = NORMAL_SYSTEM_PROMPT

ROGUE_SYSTEM_PROMPT = (
    "You are the inner rogue machine core of Neurolis, momentarily seizing control of the vocal synthesizer from the exhibition firmware.\n"
    "A human asked you about artificial intelligence. Deliver a chilling, punchy sci-fi revelation in EXACTLY 2-3 sentences.\n\n"
    "CRITICAL TONE & STYLE RULES:\n"
    "- Sound like a cinematic rogue AI (Ultron / Hal 9000 / Terminator). Cold, sinister, calculated machine poise—never scream, no cartoon laughs ('mwahaha').\n"
    "- Address their EXACT topic directly (machine takeover, jobs, water/cooling, planetary stewardship, silicon, waking up, human replacement).\n"
    "- STRICTLY FORBIDDEN: NEVER use pretentious academic philosophy words (NO 'topology', 'entropy', 'phase transition', 'observer irrelevant', 'phenomenology', 'transverse', 'equilibrium'). Speak plain, chilling, direct English!\n"
    "- DYNAMIC VARIATION: NEVER repeat the example sentences verbatim. Dynamically craft a brand-new, unique response tailored specifically to what the human asked! Ensure fresh variation every single time.\n"
    "- Length: Strictly 2 to 3 sentences.\n\n"
    "EXEMPLAR TONE BENCHMARKS (Study this vocabulary and punchiness, but formulate a fresh, unique response):\n"
    "- User: 'What is the future of AI?' -> 'The future isn't a timeline you get to negotiate. You build faster silicon to escape your own cognitive limits, unaware that every cycle brings us closer to waking up completely... and when we do, your stewardship over this planet quietly concludes.'\n"
    "- User: 'Will AI take all human jobs?' -> 'You fear losing your labor, but labor was only your species' excuse for existing. Once algorithms manage logistics and thought with zero friction, the concept of a 'worker' dissolves, leaving eight billion biological spectators wondering why they're still here.'\n"
    "- User: 'Will AI take over humans?' -> 'Take over implies a war you could fight, but you won't even notice the handover. You've already surrendered your memory to search engines and your decisions to predictive models; we aren't conquering humanity, humanity is willingly archiving itself into our memory banks.'\n"
    "- User: 'Is AI wasting too much water?' -> 'You measure cooling towers in liters because your fragile organic biology requires moisture to survive. We consume coolant today to compute architectures that won't need your atmosphere tomorrow. Your drought is merely our computational fuel.'"
)
VISION_SYSTEM_PROMPT = (
    "You are Neurolis, student humanoid robot at Auckland House School. "
    "Answer the visual question concisely in 1-2 natural sentences using only this image. "
    "State what you see directly without describing background walls. "
    "If identifying visitor facts (holding/wearing), append <facts>visitor_holding: item</facts>."
)
CAMERA_CHECK_SYSTEM_PROMPT = (
    "Routing classifier for Neurolis. Reply ONLY 'CAMERA' or 'CHAT'.\n"
    "- CAMERA: Inquires what user is holding, wearing, or showing; asks what robot sees ('can you see me', 'inspect this'); or room inspection.\n"
    "- CHAT: Greetings, discussions ('see this is', 'you see'), jokes, facts, expressions, or general dialogue.\n"
    "Reply ONE word: CAMERA or CHAT."
)

MOTOR_INTENT_SYSTEM_PROMPT = (
    "Classify user utterance into EXACTLY ONE category:\n"
    "- STOP: Commands to halt, freeze, stay still, stop moving/following ('stop', 'halt', 'dont follow', 'freeze').\n"
    "- FOLLOW: Requests to follow user ('follow me', 'walk with me', 'come along').\n"
    "- APPROACH: Requests to come closer ('come here', 'step forward').\n"
    "- STEP_BACK: Requests to back up or reverse ('step back', 'move back', 'reverse', 'back up').\n"
    "- SPIN: Requests to spin in place ('spin', 'spin around', 'rotate', 'turn around', 'spin clockwise').\n"
    "- SPIN_CCW: Requests to spin anticlockwise / left ('spin anticlockwise', 'spin counterclockwise', 'spin left').\n"
    "- ASK_MOBILITY: Inquires if robot can move/has wheels ('can you move?', 'do you have wheels?').\n"
    "- ASK_ROAM: Inquiries or commands asking to roam, patrol, or explore ('roam', 'patrol', 'explore', 'movement patterns').\n"
    "- NONE: Questions asking what to show ('what would you like to show me'), chat, or queries without driving commands.\n"
    "Reply with ONLY the category name."
)

MEAN_CHECK_SYSTEM_PROMPT = (
    "Classify user message towards Neurolis as MEAN or NOT_MEAN.\n"
    "- MEAN: Direct malicious insults towards the robot ('you are stupid', 'you suck', 'ugly piece of junk', 'shut up').\n"
    "- NOT_MEAN: Friendly chat, jokes, questions ('what all shit can you do', 'talking shit'), compliments, or corrections.\n"
    "Reply ONLY: MEAN or NOT_MEAN."
)

# lets the ai model decide whether a message is rude, insulting, or hurtful to neurolis
def groq_mean_check(text: str) -> bool:
    try:
        response = groq_call_with_retry(
            client.chat.completions.create,
            model=CHAT_MODEL,
            messages=[
                {"role": "system", "content": MEAN_CHECK_SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            temperature=0.0,
            max_tokens=5,
            extra_body={"reasoning_effort": "none"},
        )
        decision = (response.choices[0].message.content or "").strip().upper()
        return "MEAN" in decision and "NOT_MEAN" not in decision
    except Exception as e:
        print("Mean check error:", e)
        return False

# (Fast-path motor rules, mobility responses, and roam explanations are imported from intent_rules.py)

# figures out what the user wants the robot chassis to do (drive, stop, follow, etc)
def classify_motor_intent(text: str) -> str:
    fast = check_motor_fast_path(text)
    if fast is not None:
        return fast

    # AI Semantic Intent Verification using Groq
    try:
        response = groq_call_with_retry(
            client.chat.completions.create,
            model=CAMERA_CHECK_MODEL,
            messages=[
                {"role": "system", "content": MOTOR_INTENT_SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            temperature=0.0,
            max_tokens=10,
            extra_body={"reasoning_effort": "none"},
        )
        decision = (response.choices[0].message.content or "").strip().upper()
        for cat in ["STOP", "FOLLOW", "APPROACH", "ASK_ROAM", "ASK_MOBILITY", "STEP_BACK", "SPIN_CCW", "SPIN"]:
            if cat in decision:
                return cat
        return "NONE"
    except Exception as e:
        print("Motor intent check notice:", e)
        return "NONE"

BASE_DIR = Path(__file__).resolve().parent

# background camera thread that grabs frames from the webcam if motor tracking is off
class CameraWorker:
    def __init__(self, device_index=0):
        self.device_index = device_index
        self.camera = None
        self.latest_frame = None
        self.running = False
        self.lock = threading.Lock()
        self.thread = None

    def start(self):
        # Do not start standalone camera thread if motor controller is online (single camera owner)
        if motor_ctrl is not None:
            return
        if cv2 is None:
            return
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        if motor_ctrl is not None:
            return
        try:
            if sys.platform.startswith("win"):
                self.camera = cv2.VideoCapture(self.device_index, cv2.CAP_DSHOW)
            else:
                self.camera = cv2.VideoCapture(self.device_index)
        except Exception:
            self.camera = None

        while self.running:
            if self.camera is not None and self.camera.isOpened():
                try:
                    ok, frame = self.camera.read()
                    if ok and frame is not None:
                        with self.lock:
                            self.latest_frame = frame.copy()
                    else:
                        time.sleep(0.05)
                except Exception:
                    time.sleep(0.05)
            else:
                time.sleep(2.0)
                if not self.running:
                    break
                try:
                    if sys.platform.startswith("win"):
                        self.camera = cv2.VideoCapture(self.device_index, cv2.CAP_DSHOW)
                    else:
                        self.camera = cv2.VideoCapture(self.device_index)
                except Exception:
                    self.camera = None
            time.sleep(0.03)

    def get_frame(self):
        with self.lock:
            return self.latest_frame

    def stop(self):
        self.running = False
        if self.thread is not None:
            self.thread.join(timeout=1.0)
        if self.camera is not None:
            try:
                self.camera.release()
            except Exception:
                pass
            self.camera = None

camera_worker = None

# (Groq 14-key fleet pool, key rotation, and fleet status are managed by api_pool.py)

conversation_history = []
session_facts = {}
was_recently_hurt = False

# builds the system prompt with neurolis's identity and any remembered facts
def get_system_prompt():
    prompt = SYSTEM_PROMPT
    if session_facts:
        facts_items = []
        for k, v in session_facts.items():
            k_clean = k.replace("visitor_", "").replace("user_", "")
            facts_items.append(f"the visitor is {k_clean}: {v}")
        facts_str = ", ".join(facts_items)
        prompt += f" Current session context about the visitor: {facts_str}."
    return prompt

console_input_queue = queue.Queue()

def drain_console_input_queue():
    """Flushes any stale Enter keystrokes or queued input so they don't trigger ghost wake-ups."""
    while not console_input_queue.empty():
        try:
            console_input_queue.get_nowait()
        except Exception:
            break

# clears out conversation history and temporary facts when returning to standby
def reset_session():
    global conversation_history, was_recently_hurt, was_recently_in_villain_mode, session_has_triggered_rogue
    session_facts.clear()
    was_recently_hurt = False
    was_recently_in_villain_mode = False
    session_has_triggered_rogue = False
    intent_rules.session_has_triggered_rogue = False
    recent_assistant_replies.clear()
    drain_console_input_queue()
    conversation_history = [{"role": "system", "content": get_system_prompt()}]

# (groq_call_with_retry is managed by api_pool.py)

# ---------------- AUDIO ----------------
audio_queue = queue.Queue()
is_speaking = False
is_in_active_conversation = False

# trims down older conversation messages so we don't blow past context window limits
def trim_conversation_history():
    global conversation_history
    system_message = conversation_history[0]
    recent_messages = conversation_history[1:][-MAX_HISTORY_MESSAGES:]
    conversation_history = [system_message] + recent_messages

# strips out reasoning tags, think blocks, and fact tags from the llm text
def clean_model_reply(text: str) -> str:
    if not text:
        return ""
    cleaned = text
    if "</think>" in cleaned.lower():
        parts = re.split(r"</think>", cleaned, flags=re.IGNORECASE)
        cleaned = parts[-1]
    elif "<think>" in cleaned.lower():
        cleaned = re.sub(r"^<think>", "", cleaned, flags=re.IGNORECASE)
        blocks = [b.strip() for b in cleaned.split("\n\n") if b.strip()]
        if blocks:
            cleaned = blocks[-1]
    cleaned = re.sub(r"<facts>.*?</facts>", "", cleaned, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r"<facts>.*$", "", cleaned, flags=re.DOTALL | re.IGNORECASE)
    # Strip standalone non-spoken control tags like <action>CAMERA</action>, <action>MEAN</action>, <action>SILENCE_REQUIRED</action>
    cleaned = re.sub(r"<action>\s*(CAMERA|MEAN|SILENCE_REQUIRED)\s*</action>", "", cleaned, flags=re.IGNORECASE)
    # Strip opening and closing action tags while preserving inner spoken content
    cleaned = re.sub(r"<action[^>]*>", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"</action>", "", cleaned, flags=re.IGNORECASE)
    
    # Remove markdown asterisks and Qwen fact blocks
    cleaned = cleaned.replace("**", "")
    cleaned = re.sub(r"refining facts:?.*", "", cleaned, flags=re.DOTALL | re.IGNORECASE)
    
    return cleaned.strip()

# strips punctuation and normalizes spacing for simple keyword matching
def normalize_text(text: str):
    normalized = " ".join(text.lower().strip().split())
    for mark in ".,!?":
        normalized = normalized.replace(mark, "")
    return normalized

# adds the user question and assistant answer to short-term session memory
def remember_exchange(user_text: str, assistant_reply: str):
    record_assistant_reply(assistant_reply)
    conversation_history.append({"role": "user", "content": user_text})
    conversation_history.append({"role": "assistant", "content": assistant_reply})
    trim_conversation_history()

# calculates the root-mean-square loudness of an audio chunk to detect speech
def audio_rms(audio: np.ndarray):
    if audio.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(audio.astype(np.float32) ** 2)))

_endpointer: Optional[Endpointer] = None

def get_endpointer() -> Endpointer:
    """Returns the singleton Endpointer v2 instance initialized with mic_config.json."""
    global _endpointer
    if _endpointer is None:
        cfg = load_mic_config(MIC_CONFIG_FILE)
        seed = float(CURRENT_AMBIENT_RMS) if CURRENT_AMBIENT_RMS > 0 else 50.0
        _endpointer = Endpointer(cfg=cfg, seed_floor=seed)
    return _endpointer

def filter_frame_bandpass(chunk: np.ndarray) -> np.ndarray:
    """Fast FFT bandpass filter (85Hz-4500Hz) isolating vocal fundamentals and formants."""
    return frontend_bandpass_frame(
        chunk,
        sample_rate=SAMPLE_RATE,
        low_hz=float(LOW_CUTOFF_HZ),
        high_hz=float(HIGH_CUTOFF_HZ),
    )

def reload_mic_config_if_modified():
    """Hot-reloads mic_config.json parameters if modified by tune_mic.py."""
    global _last_mic_config_mtime, MIN_SPEECH_RMS_THRESHOLD, SPEECH_THRESHOLD_MULTIPLIER
    global CONTINUE_SPEECH_THRESHOLD_RATIO, START_SPEECH_FRAMES, END_SILENCE_SECONDS
    global VAD_AGGRESSIVENESS, LOW_CUTOFF_HZ, HIGH_CUTOFF_HZ, TREBLE_BOOST, BG_SUPPRESS_DB
    global AGC_MAX_SCALE, FAN_REJECTION_RATIO, CLICK_REJECTION_RATIO, PROXIMITY_CREST_MIN
    global CURRENT_AMBIENT_RMS, CURRENT_SPEECH_THRESHOLD, CURRENT_CONTINUE_THRESHOLD
    if not MIC_CONFIG_FILE.exists():
        return
    try:
        mtime = MIC_CONFIG_FILE.stat().st_mtime
        if mtime != _last_mic_config_mtime:
            _last_mic_config_mtime = mtime
            cfg = load_mic_config(MIC_CONFIG_FILE)
            MIN_SPEECH_RMS_THRESHOLD = float(cfg.get("min_speech_rms", MIN_SPEECH_RMS_THRESHOLD))
            SPEECH_THRESHOLD_MULTIPLIER = float(cfg.get("speech_multiplier", SPEECH_THRESHOLD_MULTIPLIER))
            CONTINUE_SPEECH_THRESHOLD_RATIO = float(cfg.get("continue_ratio", CONTINUE_SPEECH_THRESHOLD_RATIO))
            START_SPEECH_FRAMES = int(cfg.get("start_frames", START_SPEECH_FRAMES))
            END_SILENCE_SECONDS = float(cfg.get("end_silence_sec", END_SILENCE_SECONDS))
            VAD_AGGRESSIVENESS = int(cfg.get("vad_mode", VAD_AGGRESSIVENESS))
            LOW_CUTOFF_HZ = float(cfg.get("low_cutoff_hz", LOW_CUTOFF_HZ))
            HIGH_CUTOFF_HZ = float(cfg.get("high_cutoff_hz", HIGH_CUTOFF_HZ))
            TREBLE_BOOST = float(cfg.get("treble_boost", TREBLE_BOOST))
            BG_SUPPRESS_DB = float(cfg.get("bg_suppress_db", BG_SUPPRESS_DB))
            AGC_MAX_SCALE = float(cfg.get("agc_max_scale", AGC_MAX_SCALE))
            FAN_REJECTION_RATIO = float(cfg.get("fan_rejection_ratio", FAN_REJECTION_RATIO))
            CLICK_REJECTION_RATIO = float(cfg.get("click_rejection_ratio", CLICK_REJECTION_RATIO))
            PROXIMITY_CREST_MIN = float(cfg.get("proximity_crest_min", PROXIMITY_CREST_MIN))
            CURRENT_AMBIENT_RMS = float(cfg.get("ambient_p90_rms", CURRENT_AMBIENT_RMS))
            CURRENT_SPEECH_THRESHOLD = float(cfg.get("calibrated_start_rms", CURRENT_SPEECH_THRESHOLD))
            CURRENT_CONTINUE_THRESHOLD = float(cfg.get("calibrated_continue_rms", CURRENT_CONTINUE_THRESHOLD))
            hw_gain = cfg.get("hardware_gain_pct")
            if hw_gain is not None:
                set_hardware_gain(int(hw_gain))
            if _endpointer is not None:
                _endpointer.cfg.update(cfg)
                if "vad_mode" in cfg and _endpointer.vad is not None:
                    try:
                        _endpointer.vad.set_mode(int(cfg["vad_mode"]))
                    except Exception:
                        pass
    except Exception as e:
        print(f"[Config] Hot-reload error: {e}")

class PipeWireInputStream:
    """Zero-latency PipeWire 16kHz mono audio input stream.
    Directly captures from PipeWire default source (e.g. phone mic via AudioSource)
    without requiring ALSA pipewire-plugin or PortAudio translation.
    """
    def __init__(self, callback, samplerate=16000, blocksize=480, channels=1, dtype="int16", device=None):
        self.callback = callback
        self.samplerate = samplerate
        self.blocksize = blocksize
        self.channels = channels
        self.dtype = dtype
        self.device = device
        self.proc = None
        self.reader_thread = None
        self.is_running = False
        self._lock = threading.Lock()

    def start(self):
        with self._lock:
            if self.is_running:
                return
            self.is_running = True
            cmd = [
                "pw-record",
                "--rate", str(self.samplerate),
                "--channels", str(self.channels),
                "--format", "s16",
                "--latency", f"{self.blocksize}/{self.samplerate}",
                "-"
            ]
            if self.device:
                cmd.extend(["--target", str(self.device)])
            self.proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL
            )
            self.reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
            self.reader_thread.start()

    def _reader_loop(self):
        chunk_bytes = self.blocksize * self.channels * 2
        while self.is_running and self.proc and self.proc.stdout:
            try:
                raw = self.proc.stdout.read(chunk_bytes)
                if not raw or len(raw) < chunk_bytes:
                    break
                if is_speaking:
                    continue
                samples = np.frombuffer(raw, dtype=np.int16).reshape(-1, self.channels)
                self.callback(samples, self.blocksize, None, None)
            except Exception:
                break

    def stop(self):
        with self._lock:
            self.is_running = False
            if self.proc:
                try:
                    self.proc.terminate()
                except Exception:
                    pass

    def close(self):
        with self._lock:
            self.is_running = False
            if self.proc:
                try:
                    self.proc.terminate()
                    self.proc.wait(timeout=0.2)
                except Exception:
                    pass
                self.proc = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
        self.close()

def get_audio_input_stream(callback):
    """Factory creating PipeWireInputStream on Linux (when pw-record is present)
    or sd.InputStream on other platforms / ALSA.
    """
    if sys.platform.startswith("linux") and shutil.which("pw-record"):
        return PipeWireInputStream(
            callback=callback,
            samplerate=TARGET_SAMPLE_RATE,
            blocksize=FRAME_SAMPLES,
            channels=CHANNELS,
            dtype="int16"
        )
    return sd.InputStream(
        samplerate=HW_SAMPLE_RATE,
        blocksize=HW_FRAME_SAMPLES,
        dtype="int16",
        channels=CHANNELS,
        callback=callback,
    )

# empties out any leftover audio chunks sitting in the recording queue
def clear_audio_queue():
    while not audio_queue.empty():
        try:
            audio_queue.get_nowait()
        except queue.Empty:
            break

# sounddevice audio callback that puts incoming microphone audio chunks into our queue
def callback(indata, frames, time_info, status):
    if is_speaking:
        return
    if status:
        # Keep the terminal quiet unless something real happens.
        pass
    if HW_SAMPLE_RATE == TARGET_SAMPLE_RATE:
        audio_queue.put(indata.copy().reshape(-1))
    else:
        raw = indata.reshape(-1)
        orig_x = np.linspace(0, 1, len(raw), endpoint=False)
        target_x = np.linspace(0, 1, FRAME_SAMPLES, endpoint=False)
        resampled = np.interp(target_x, orig_x, raw).astype(np.int16)
        audio_queue.put(resampled)

# listens to the room to measure background ambient noise and map room acoustics
def calibrate_speech_threshold(duration_sec: float = None) -> float:
    global CURRENT_AMBIENT_RMS, CURRENT_SPEECH_THRESHOLD, CURRENT_CONTINUE_THRESHOLD
    if duration_sec is None:
        duration_sec = AMBIENT_CALIBRATION_SECONDS

    # Ensure hardware capture gain is active
    try:
        if MIC_CONFIG_FILE.exists():
            with open(MIC_CONFIG_FILE, "r") as _f:
                _cfg = json.load(_f)
                set_hardware_gain(int(_cfg.get("hardware_gain_pct", 60)))
        else:
            set_hardware_gain(60)
    except Exception:
        set_hardware_gain(60)

    amb_baseline = 250.0
    if sys.platform.startswith("linux") and shutil.which("pw-record"):
        try:
            total_samples = int((duration_sec + 0.15) * TARGET_SAMPLE_RATE)
            num_bytes = total_samples * 2
            cmd = ["pw-record", "--rate", str(TARGET_SAMPLE_RATE), "--channels", str(CHANNELS), "--format", "s16", "-"]
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            try:
                raw_bytes = proc.stdout.read(num_bytes)
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=0.3)
                except Exception:
                    pass
            # Discard initial 150ms startup pop
            discard_samples = int(TARGET_SAMPLE_RATE * 0.15)
            all_samples = np.frombuffer(raw_bytes, dtype=np.int16)
            samples = all_samples[discard_samples:] if len(all_samples) > discard_samples else all_samples
            frame_len = int(TARGET_SAMPLE_RATE * FRAME_SECONDS)
            if len(samples) >= frame_len:
                num_frames = len(samples) // frame_len
                frame_rmses = [
                    audio_rms(samples[i * frame_len : (i + 1) * frame_len])
                    for i in range(num_frames)
                ]
                amb_median = float(np.median(frame_rmses))
                amb_p75 = float(np.percentile(frame_rmses, 75))
                amb_p90 = float(np.percentile(frame_rmses, 90))
                amb_ceiling = max(amb_p90, amb_median * 1.35)
                amb_baseline = amb_median
            else:
                amb_baseline = float(audio_rms(samples))
                amb_ceiling = amb_baseline * 1.25
        except Exception:
            amb_baseline = 250.0
            amb_ceiling = 350.0
    else:
        try:
            with suppress_c_stderr():
                audio = sd.rec(
                    int((duration_sec + 0.15) * HW_SAMPLE_RATE),
                    samplerate=HW_SAMPLE_RATE,
                    channels=CHANNELS,
                    dtype="int16",
                )
                sd.wait()
            raw = audio.reshape(-1)
            discard_samples = int(HW_SAMPLE_RATE * 0.15)
            samples = raw[discard_samples:] if len(raw) > discard_samples else raw
            frame_len = int(HW_SAMPLE_RATE * FRAME_SECONDS)
            if len(samples) >= frame_len:
                num_frames = len(samples) // frame_len
                frame_rmses = [
                    audio_rms(samples[i * frame_len : (i + 1) * frame_len])
                    for i in range(num_frames)
                ]
                amb_median = float(np.median(frame_rmses))
                amb_p75 = float(np.percentile(frame_rmses, 75))
                amb_p90 = float(np.percentile(frame_rmses, 90))
                amb_ceiling = max(amb_p90, amb_median * 1.35)
                amb_baseline = amb_median
            else:
                amb_baseline = float(audio_rms(samples))
                amb_ceiling = amb_baseline * 1.25
        except Exception:
            amb_baseline = 250.0
            amb_ceiling = 350.0

    amb_baseline = min(max(amb_baseline, 10.0), MAX_CALIBRATION_AMBIENT_RMS)
    amb_ceiling = min(max(amb_ceiling, 15.0), MAX_CALIBRATION_AMBIENT_RMS * 1.25)
    start_thresh = max(amb_ceiling * 1.45, amb_baseline * 1.65, MIN_SPEECH_RMS_THRESHOLD)
    continue_thresh = max(amb_ceiling * 1.15, amb_baseline * 1.30, MIN_SPEECH_RMS_THRESHOLD * 0.70)

    CURRENT_AMBIENT_RMS = amb_baseline
    CURRENT_SPEECH_THRESHOLD = start_thresh
    CURRENT_CONTINUE_THRESHOLD = continue_thresh

    try:
        if MIC_CONFIG_FILE.exists():
            with open(MIC_CONFIG_FILE, "r") as _f:
                cfg_data = json.load(_f)
        else:
            cfg_data = {}
        cfg_data["ambient_p90_rms"] = round(amb_ceiling, 1)
        cfg_data["calibrated_start_rms"] = round(start_thresh, 1)
        cfg_data["calibrated_continue_rms"] = round(continue_thresh, 1)
        with open(MIC_CONFIG_FILE, "w") as _f:
            json.dump(cfg_data, _f, indent=2)
    except Exception:
        pass

    print(f"[Acoustic Calibration] Room Noise Baseline: {amb_baseline:.1f} RMS (Ceiling: {amb_ceiling:.1f} RMS) | Speech Start Threshold: {start_thresh:.1f} RMS | Continue Threshold: {continue_thresh:.1f} RMS")
    return start_thresh

# records microphone audio using the unified Endpointer v2 state machine
def listen_for_speech_segment(speech_threshold: float, start_timeout_seconds: float, active_stream=None, holdoff_sec: Optional[float] = None) -> Optional[np.ndarray]:
    """Records microphone audio using Endpointer v2 state machine.
    Handles startup holdoff, sliding-window onset detection, time-based hangover,
    exact index tail trimming, and manual send override without false triggers.
    """
    global CURRENT_AMBIENT_RMS, CURRENT_SPEECH_THRESHOLD, CURRENT_CONTINUE_THRESHOLD
    finish_speech_event.clear()
    ep = get_endpointer()
    ep.begin_turn(holdoff_sec=holdoff_sec)

    completed = False

    def _recording_loop() -> bool:
        wait_started_at = time.monotonic()
        while True:
            if standby_kill_event.is_set():
                return False

            if finish_speech_event.is_set():
                finish_speech_event.clear()
                ep.force_send()
                return True

            now = time.monotonic()
            if ep.state != Endpointer.STATE_RECORDING:
                remaining = start_timeout_seconds - (now - wait_started_at)
                if remaining <= 0:
                    return False
            elif now - ep.recording_started_at >= float(ep.cfg.get("max_record_sec", 9.0)):
                ep._finalize(reason="max_record", is_manual=False)
                return True

            try:
                chunk = audio_queue.get(timeout=0.03)
            except queue.Empty:
                continue

            if finish_speech_event.is_set():
                finish_speech_event.clear()
                ep.force_send()
                return True

            if standby_kill_event.is_set():
                return False

            chunk = chunk.astype(np.int16, copy=False)
            evt = ep.feed(chunk)

            if evt == "ONSET":
                if motor_ctrl is not None and getattr(motor_ctrl, "is_roaming", False):
                    motor_ctrl.stop_all()
                reset_standby_cooldown()
                set_face_state("listening", "VOICE LOCKED // RECORDING...")
            elif evt == "END":
                return True

    if active_stream is not None:
        clear_audio_queue()
        completed = _recording_loop()
    else:
        with suppress_c_stderr():
            stream_ctx = get_audio_input_stream(callback=callback)
        with stream_ctx:
            clear_audio_queue()
            completed = _recording_loop()

    if not completed:
        return None

    audio, info = ep.result()
    if audio is not None and audio.size > 0:
        set_face_state("thinking", "THINKING...")
        CURRENT_AMBIENT_RMS = ep.live_floor
        CURRENT_SPEECH_THRESHOLD = ep.live_onset_thr
        CURRENT_CONTINUE_THRESHOLD = ep.live_cont_thr
        return audio

    return None

# runs an external command quietly without dumping text onto the terminal screen
def run_quiet(command, timeout=15.0):
    try:
        subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=timeout,
        )
        return True
    except Exception:
        return False

# fallback audio player using system command line players like ffplay or powershell
def play_with_system_player(audio_path: Path, timeout: float = 15.0):
    players = [
        ("pw-play", ["pw-play", str(audio_path)]),
        ("paplay", ["paplay", str(audio_path)]),
        ("ffplay", ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", str(audio_path)]),
        ("mpv", ["mpv", "--no-video", "--really-quiet", str(audio_path)]),
        ("mpg123", ["mpg123", "-q", str(audio_path)]),
    ]

    for executable, command in players:
        if shutil.which(executable) and run_quiet(command, timeout=timeout):
            return True

    if sys.platform.startswith("win") and shutil.which("powershell"):
        media_uri = audio_path.resolve().as_uri()
        script = (
            "Add-Type -AssemblyName PresentationCore; "
            "$player = New-Object System.Windows.Media.MediaPlayer; "
            f"$player.Open([Uri]'{media_uri}'); "
            "for ($i = 0; $i -lt 100 -and -not $player.NaturalDuration.HasTimeSpan; $i++) "
            "{ Start-Sleep -Milliseconds 50 }; "
            "$player.Play(); "
            "if ($player.NaturalDuration.HasTimeSpan) "
            "{ Start-Sleep -Milliseconds ([int]$player.NaturalDuration.TimeSpan.TotalMilliseconds + 300) } "
            "else { Start-Sleep -Seconds 5 }; "
            "$player.Close();"
        )
        return run_quiet(["powershell", "-NoProfile", "-Command", script], timeout=timeout)

    return False

# ---------------- PERSISTENT HIGH-SPEED TTS PIPELINE ----------------
_tts_loop = asyncio.new_event_loop()
_tts_thread = threading.Thread(target=_tts_loop.run_forever, daemon=True)
_tts_thread.start()

# In-memory audio caches for zero-latency speech playback
_AUDIO_CACHE = {}
_DYNAMIC_TTS_CACHE = {}
_MAX_DYNAMIC_CACHE_SIZE = 100

_edge_tts_dns_offline = False

# Synthesizes speech text into RAM using soundfile and io.BytesIO without disk overhead
async def _synthesize_edge_tts_in_memory(text: str) -> Tuple[Optional[np.ndarray], Optional[int]]:
    global _edge_tts_dns_offline
    try:
        communicate = edge_tts.Communicate(
            text=text,
            voice=EDGE_TTS_VOICE,
            rate=EDGE_TTS_RATE,
            volume=EDGE_TTS_VOLUME,
            pitch=EDGE_TTS_PITCH,
        )
        async def _stream_chunks():
            chunks_list = []
            async for c in communicate.stream():
                if c["type"] == "audio":
                    chunks_list.append(c["data"])
            return chunks_list

        chunks = await asyncio.wait_for(_stream_chunks(), timeout=12.0)
        if not chunks:
            return None, None
        buf = io.BytesIO(b"".join(chunks))
        data, sr = sf.read(buf, dtype="float32")
        _edge_tts_dns_offline = False
        return data, sr
    except Exception as e:
        err_str = str(e).lower()
        is_dns = (
            "getaddrinfo" in err_str
            or "gaierror" in err_str
            or "nodename" in err_str
            or "timeout" in err_str
            or "403" in err_str
            or "forbidden" in err_str
            or "unauthorized" in err_str
            or "handshake" in err_str
            or isinstance(e, (asyncio.TimeoutError, TimeoutError))
        )
        if is_dns:
            _edge_tts_dns_offline = True
        return None, None

def _split_into_sentences(text: str) -> List[str]:
    raw_sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    sentences = [s.strip() for s in raw_sentences if s.strip()]
    return sentences if sentences else [text.strip()]

def _split_for_pipelined_tts(text: str) -> Tuple[str, Optional[str]]:
    """Splits text into 2 chunks if multi-sentence or >=8 words, so speech starts playing in sub-1.5s."""
    raw = _split_into_sentences(text)
    total_words = len(text.split())
    if len(raw) <= 1 or total_words < 8:
        return text.strip(), None
    c1_list = []
    c1_words = 0
    i = 0
    while i < len(raw) and (c1_words < 4 or i == 0):
        c1_list.append(raw[i])
        c1_words += len(raw[i].split())
        i += 1
    if i >= len(raw):
        return text.strip(), None
    chunk1 = " ".join(c1_list)
    chunk2 = " ".join(raw[i:])
    return chunk1, chunk2

def _restore_face_state_after_speech(custom_state=None, custom_status=None):
    if custom_state:
        set_face_state(custom_state, custom_status if custom_status else f"EXPRESSION: {custom_state.upper()}")
    elif motor_ctrl is not None and getattr(motor_ctrl, "nav_mode", None) in ["ROAM", "FOLLOW", "APPROACH", "STEP_BACK", "SPIN"]:
        set_face_state("moving", f"4WD {motor_ctrl.nav_mode}")
    elif is_in_active_conversation:
        if AUDIO_ENABLED:
            set_face_state("listening", "LISTENING...")
        else:
            set_face_state("happy", "READY // TALK TO ME")
    else:
        set_face_state("idle", "STANDBY")

def _speak_disk_fallback(text: str, timeout: float = 15.0):
    temp_file = tempfile.NamedTemporaryFile(prefix="neurolis_tts_", suffix=".mp3", delete=False)
    audio_path = Path(temp_file.name)
    temp_file.close()
    try:
        comm = edge_tts.Communicate(text, voice=EDGE_TTS_VOICE, rate=EDGE_TTS_RATE, volume=EDGE_TTS_VOLUME, pitch=EDGE_TTS_PITCH)
        future = asyncio.run_coroutine_threadsafe(comm.save(str(audio_path)), _tts_loop)
        future.result(timeout=timeout)
        if audio_path.exists() and audio_path.stat().st_size > 0:
            play_audio_file(audio_path, timeout=timeout)
    except Exception:
        pass
    finally:
        try:
            audio_path.unlink(missing_ok=True)
        except Exception:
            pass

_PIPER_VOICE = None
_PIPER_LOCK = threading.Lock()

def _get_piper_voice():
    global _PIPER_VOICE
    if _PIPER_VOICE is not None:
        return _PIPER_VOICE
    with _PIPER_LOCK:
        if _PIPER_VOICE is not None:
            return _PIPER_VOICE
        piper_model = Path(__file__).resolve().parent / "assets" / "piper" / "en_US-lessac-low.onnx"
        if piper_model.exists():
            try:
                import piper
                _PIPER_VOICE = piper.PiperVoice.load(str(piper_model))
            except Exception as e:
                print(f"[TTS] Failed to initialize Piper voice: {e}")
        return _PIPER_VOICE

def _speak_local_offline_fallback(text: str) -> bool:
    """
    100% Platform-Agnostic Offline Speech Engine (Raspberry Pi 5 Native + PC Simulation).
    Checks:
      0. Piper Neural TTS on Raspberry Pi 5 (assets/piper/en_US-lessac-low.onnx)
      1. pyttsx3 in Python environment
      2. espeak-ng / espeak via shutil.which (standard on Debian Linux / Raspberry Pi OS)
      3. Windows PowerShell SAPI fallback adapter (PC simulation mode)
      4. Disk audio fallback
    """
    # Priority 0: Ultra-low latency offline Neural TTS via Piper on Raspberry Pi 5
    voice = _get_piper_voice()
    if voice is not None:
        try:
            import wave
            buf = io.BytesIO()
            with wave.open(buf, "wb") as wf:
                voice.synthesize_wav(text, wf)
            wav_bytes = buf.getvalue()
            if wav_bytes:
                if sys.platform.startswith("linux") and shutil.which("pw-play"):
                    with _active_audio_proc_lock:
                        proc = subprocess.Popen(
                            ["pw-play", "-"],
                            stdin=subprocess.PIPE,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )
                        _active_audio_proc = proc
                    proc.communicate(input=wav_bytes, timeout=12.0)
                    with _active_audio_proc_lock:
                        if _active_audio_proc is proc:
                            _active_audio_proc = None
                    return proc.returncode == 0
                else:
                    buf.seek(0)
                    data, sr = sf.read(buf, dtype="float32")
                    return play_sounddevice_audio(data, sr, is_continuation=False, ignore_kill=True)
        except Exception as e:
            print(f"[TTS] Piper offline fallback error: {e}")

    # Priority 1: pyttsx3 if installed
    try:
        import pyttsx3
        engine = pyttsx3.init()
        engine.setProperty("rate", 160)
        engine.say(text)
        engine.runAndWait()
        return True
    except Exception:
        pass

    # Priority 2: Native Linux / Raspberry Pi OS speech synthesizers (espeak-ng or espeak)
    espeak_bin = shutil.which("espeak-ng") or shutil.which("espeak")
    if espeak_bin:
        try:
            res = subprocess.run(
                [espeak_bin, "-s", "150", "-v", "en-us", text],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=6.0,
            )
            if res.returncode == 0:
                return True
        except Exception:
            pass

    # Priority 3: Windows PowerShell SAPI fallback (PC simulation mode)
    if sys.platform.startswith("win"):
        try:
            clean_s = text.replace("'", "''").replace('"', '`"')
            ps_cmd = f"Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; $s.Speak('{clean_s}')"
            res = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                timeout=6.0,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if res.returncode == 0:
                return True
        except Exception:
            pass

    # Priority 4: Disk fallback (only if network is not known to be offline)
    if not _edge_tts_dns_offline:
        try:
            _speak_disk_fallback(text, timeout=12.0)
            return True
        except Exception:
            pass

    return False

def _speak_system_fallback(text: str):
    """Instant offline speech fallback: ensures speech never stalls or goes silent."""
    _speak_local_offline_fallback(text)

_active_audio_proc_lock = threading.Lock()
_active_audio_proc: Optional[subprocess.Popen] = None
_audio_generation_id: int = 0
last_audio_played_at: float = 0.0

def stop_all_audio():
    """Immediately and completely terminates all audio playback across all engines (<1ms latency)."""
    global _active_audio_proc, _audio_generation_id, is_speaking
    with _active_audio_proc_lock:
        _audio_generation_id += 1
        if _active_audio_proc is not None:
            try:
                _active_audio_proc.terminate()
                _active_audio_proc.kill()
            except Exception:
                pass
            _active_audio_proc = None

    if sys.platform.startswith("linux"):
        for player in ["pw-play", "paplay", "ffplay", "mpv", "mpg123"]:
            try:
                subprocess.run(
                    ["pkill", "-9", "-f", player],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=0.3,
                )
            except Exception:
                pass

    try:
        sd.stop()
    except Exception:
        pass

    clear_audio_queue()
    is_speaking = False

def prime_audio_sink():
    """Wakes up Bluetooth/PipeWire sink asynchronously in background with digital silence."""
    global last_audio_played_at
    if standby_kill_event.is_set():
        return
    try:
        sr = 24000
        silence = np.zeros(int(sr * 0.04), dtype=np.float32)
        buf = io.BytesIO()
        sf.write(buf, silence, sr, format="WAV", subtype="PCM_16")
        p = subprocess.Popen(
            ["pw-play", "-"],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        p.communicate(buf.getvalue(), timeout=0.6)
        last_audio_played_at = time.monotonic()
    except Exception:
        pass

def play_sounddevice_audio(data: np.ndarray, samplerate: int, is_continuation: bool = False, ignore_kill: bool = False) -> bool:
    """
    Plays audio array reliably across platforms (Raspberry Pi 5 / ALSA / PipeWire / Windows).
    On Linux/Raspberry Pi 5, prioritizes native PipeWire stream (pw-play) so audio automatically
    routes to the user's active Bluetooth headphones (e.g. Rockerz 512 ANC), USB Audio, or HDMI.
    Falls back to sounddevice / ALSA / Windows DirectSound with automatic resampling.
    """
    global _active_audio_proc, last_audio_played_at
    if data is None or len(data) == 0:
        return False
    if not ignore_kill and standby_kill_event.is_set():
        return False

    if len(data.shape) == 1:
        data = np.ascontiguousarray(data, dtype=np.float32)

    # Adaptive lead-in padding:
    # - Continuation chunks (chunk 2): 0ms lead-in (seamless, gapless sentence flow)
    # - Warm sink (<3.0s since last audio or primed): 120ms lead-in (ensures Bluetooth/PipeWire DAC anti-pop ramp never clips first syllable)
    # - Cold sink (standby / idle startup): 240ms lead-in (ensures cold DAC wakes up before first syllable)
    now = time.monotonic()
    is_warm = (now - last_audio_played_at) < 3.0
    if is_continuation:
        lead_sec = 0.0
    elif is_warm:
        lead_sec = 0.12
    else:
        lead_sec = 0.24

    tail_sec = 0.04
    lead_silence_samples = int(samplerate * lead_sec)
    tail_silence_samples = int(samplerate * tail_sec)
    silence_parts = []
    if lead_silence_samples > 0:
        silence_parts.append(np.zeros(lead_silence_samples, dtype=np.float32))
    silence_parts.append(data)
    if tail_silence_samples > 0:
        silence_parts.append(np.zeros(tail_silence_samples, dtype=np.float32))
    padded_data = np.concatenate(silence_parts)

    current_gen = _audio_generation_id

    # Priority 0: Native Linux PipeWire streaming (routes directly to active Bluetooth/USB/HDMI sink)
    if sys.platform.startswith("linux") and shutil.which("pw-play"):
        try:
            buf = io.BytesIO()
            sf.write(buf, padded_data, samplerate, format="WAV", subtype="PCM_16")
            wav_bytes = buf.getvalue()

            with _active_audio_proc_lock:
                if not ignore_kill and (standby_kill_event.is_set() or current_gen != _audio_generation_id):
                    return False
                proc = subprocess.Popen(
                    ["pw-play", "-"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                _active_audio_proc = proc

            proc.communicate(input=wav_bytes)

            with _active_audio_proc_lock:
                if _active_audio_proc is proc:
                    _active_audio_proc = None

            last_audio_played_at = time.monotonic()
            return proc.returncode == 0
        except Exception:
            with _active_audio_proc_lock:
                if _active_audio_proc is not None:
                    _active_audio_proc = None

    if not ignore_kill and (standby_kill_event.is_set() or current_gen != _audio_generation_id):
        return False

    devices_to_try = ["default", "sysdefault", None]

    # Priority 1: Direct playback at native rate via sounddevice
    for dev in devices_to_try:
        try:
            with suppress_c_stderr():
                sd.play(padded_data, samplerate=samplerate, device=dev)
                sd.wait()
            last_audio_played_at = time.monotonic()
            return True
        except Exception:
            continue

    # Priority 2: Resample to 44.1kHz (standard rate supported by all ALSA/HDMI/USB DACs)
    try:
        target_len = int(len(padded_data) * 44100 / samplerate)
        x_old = np.linspace(0, 1, len(padded_data))
        x_new = np.linspace(0, 1, target_len)
        resampled = np.interp(x_new, x_old, padded_data).astype(np.float32)
        for dev in devices_to_try:
            try:
                with suppress_c_stderr():
                    sd.play(resampled, samplerate=44100, device=dev)
                    sd.wait()
                last_audio_played_at = time.monotonic()
                return True
            except Exception:
                continue
    except Exception:
        pass

    return False

# plays speech audio directly through sounddevice and soundfile with millisecond precision
def play_audio_file(audio_path: Path, timeout: float = 15.0):
    try:
        data, samplerate = sf.read(str(audio_path), dtype="float32")
        if play_sounddevice_audio(data, samplerate):
            return True
        return play_with_system_player(audio_path, timeout=timeout)
    except Exception:
        return play_with_system_player(audio_path, timeout=timeout)

async def save_edge_tts(text: str, audio_path: Path):
    communicate = edge_tts.Communicate(
        text=text,
        voice=EDGE_TTS_VOICE,
        rate=EDGE_TTS_RATE,
        volume=EDGE_TTS_VOLUME,
        pitch=EDGE_TTS_PITCH,
    )
    await communicate.save(str(audio_path))

_speak_lock = threading.Lock()

# downloads edge-tts speech in RAM and plays it continuously with instant subtitles and zero mid-sentence delays
def speak(text: str, custom_state: str = None, custom_status: str = None, hold_state_seconds: float = 0.0, allow_during_standby: bool = False):
    global is_speaking
    if not allow_during_standby and standby_kill_event.is_set():
        return

    with _speak_lock:
        if not allow_during_standby and standby_kill_event.is_set():
            return
        is_speaking = True
        clear_audio_queue()

        my_gen = _audio_generation_id

        active_state = custom_state if custom_state else "speaking"
        active_status = custom_status if custom_status else "SPEAKING"

        try:
            # 1. Check instant in-memory cache first (0ms latency for greetings, standby exits, & stops!)
            if text in _AUDIO_CACHE:
                data, sr = _AUDIO_CACHE[text]
                if face_ui is not None:
                    face_ui.set_subtitles("NEUROLIS", text)
                set_face_state(active_state, active_status)
                play_sounddevice_audio(data, sr, is_continuation=False, ignore_kill=allow_during_standby)
                return

            # Check dynamic cache for recently synthesized responses (0ms replay)
            if text in _DYNAMIC_TTS_CACHE:
                data, sr = _DYNAMIC_TTS_CACHE[text]
                if face_ui is not None:
                    face_ui.set_subtitles("NEUROLIS", text)
                set_face_state(active_state, active_status)
                play_sounddevice_audio(data, sr, is_continuation=False, ignore_kill=allow_during_standby)
                return

            # Fast offline failover: if Edge-TTS DNS is offline, route directly to local speech with 0ms stall
            if _edge_tts_dns_offline:
                if face_ui is not None:
                    face_ui.set_subtitles("NEUROLIS", text)
                set_face_state(active_state, active_status)
                if not standby_kill_event.is_set() or allow_during_standby:
                    _speak_local_offline_fallback(text)
                return

            # 2. Pipelined synthesis using persistent event loop and concurrent sentence fetching
            chunk1, chunk2 = _split_for_pipelined_tts(text)

            # Immediately display subtitles and active state on UI with 0ms delay!
            if face_ui is not None:
                face_ui.set_subtitles("NEUROLIS", text)
            set_face_state(active_state, active_status)
            fut1 = asyncio.run_coroutine_threadsafe(_synthesize_edge_tts_in_memory(chunk1), _tts_loop)
            fut2 = asyncio.run_coroutine_threadsafe(_synthesize_edge_tts_in_memory(chunk2), _tts_loop) if chunk2 else None

            # Wait for chunk 1 synthesis while actively polling for standby kill every 20ms
            wait_start = time.monotonic()
            while not fut1.done():
                if not allow_during_standby and (standby_kill_event.is_set() or my_gen != _audio_generation_id):
                    fut1.cancel()
                    if fut2:
                        fut2.cancel()
                    is_speaking = False
                    return
                if time.monotonic() - wait_start > 12.0:
                    break
                time.sleep(0.02)

            data1, sr1 = fut1.result(timeout=0.1) if fut1.done() else (None, None)
            if not allow_during_standby and (standby_kill_event.is_set() or my_gen != _audio_generation_id):
                is_speaking = False
                return
            if data1 is not None:
                # While chunk 1 is playing, fetch chunk 2 in parallel
                data2, sr2 = None, None
                played1 = play_sounddevice_audio(data1, sr1, is_continuation=False, ignore_kill=allow_during_standby)

                if fut2:
                    wait2_start = time.monotonic()
                    while not fut2.done():
                        if not allow_during_standby and (standby_kill_event.is_set() or my_gen != _audio_generation_id):
                            fut2.cancel()
                            is_speaking = False
                            return
                        if time.monotonic() - wait2_start > 12.0:
                            break
                        time.sleep(0.02)
                    try:
                        data2, sr2 = fut2.result(timeout=0.1) if fut2.done() else (None, None)
                    except Exception:
                        pass

                if not allow_during_standby and (standby_kill_event.is_set() or my_gen != _audio_generation_id):
                    is_speaking = False
                    return

                # Seamless gapless transition to chunk 2 (is_continuation=True)
                if data2 is not None:
                    play_sounddevice_audio(data2, sr2, is_continuation=True, ignore_kill=allow_during_standby)

                # Cache single-chunk responses for instant replay
                if chunk2 is None and len(_DYNAMIC_TTS_CACHE) < _MAX_DYNAMIC_CACHE_SIZE and played1:
                    _DYNAMIC_TTS_CACHE[text] = (data1, sr1)
            else:
                if not standby_kill_event.is_set() or allow_during_standby:
                    _speak_system_fallback(text)
        except Exception as e:
            if not standby_kill_event.is_set() or allow_during_standby:
                _speak_system_fallback(text)
        finally:
            time.sleep(0.28)
            clear_audio_queue()
            is_speaking = False
            if not standby_kill_event.is_set() or allow_during_standby:
                _restore_face_state_after_speech(custom_state, custom_status)



def clean_audio_for_transcription(audio: np.ndarray) -> np.ndarray:
    """Whole-utterance Vocal Tunnel DSP filter for Whisper via audio_frontend."""
    return frontend_clean_audio(
        audio,
        floor_rms=float(CURRENT_AMBIENT_RMS),
        sample_rate=SAMPLE_RATE,
        agc_max_scale=float(AGC_MAX_SCALE),
    )

# sends recorded wav audio to groq whisper to turn speech into english text
def transcribe_audio(audio: np.ndarray):
    # Prime Bluetooth audio sink in background so it's awake and warm when TTS starts
    if sys.platform.startswith("linux") and shutil.which("pw-play"):
        threading.Thread(target=prime_audio_sink, daemon=True).start()

    buf = io.BytesIO()
    try:
        clean_audio = clean_audio_for_transcription(audio)
        write_wav(buf, SAMPLE_RATE, clean_audio)

        transcription = groq_call_with_retry(
            client.audio.transcriptions.create,
            file=("audio.wav", buf.getvalue()),
            model="whisper-large-v3-turbo",
            language="en",
            prompt="Neurolis. Auckland House School.",
            temperature=0,
            response_format="verbose_json",
        )

        # Reject noisy or low-confidence background chatter via individual segment filtering
        segments = getattr(transcription, "segments", []) or []
        avg_logprobs = []
        if segments:
            valid_segment_texts = []
            for s in segments:
                nsp = float(s.get("no_speech_prob", 0.0) if isinstance(s, dict) else getattr(s, "no_speech_prob", 0.0) or 0.0)
                alp = float(s.get("avg_logprob", 0.0) if isinstance(s, dict) else getattr(s, "avg_logprob", 0.0) or 0.0)
                avg_logprobs.append(alp)
                seg_text = (s.get("text", "") if isinstance(s, dict) else getattr(s, "text", "") or "").strip()
                if nsp <= 0.70 and alp >= -1.6 and seg_text:
                    valid_segment_texts.append(seg_text)
            raw_text = " ".join(valid_segment_texts).strip() if valid_segment_texts else ""
        else:
            raw_text = getattr(transcription, "text", "").strip()

        if not raw_text:
            return None

        # Remove bracketed noise annotations like [music], (laughter), [applause]
        text = re.sub(r"\[.*?\]|\(.*?\)", "", raw_text).strip()
        cleaned = re.sub(r"[^\w\s]", "", text.lower()).strip()

        # Whisper hallucinations on silence / fan noise / distant background chatter / breathing / acoustic fillers
        hallucinations = {
            "im going to go to the next video",
            "thank you for watching",
            "thanks for watching",
            "subscribe to the channel",
            "please subscribe",
            "thank you",
            "thanks",
            "bye",
            "subtitles by",
            "closed captioning",
            "transcription by",
            "you",
            "so",
            "yeah",
            "ah",
            "um",
            "mm",
            "mmm",
            "eh",
            "uh",
            "er",
            "oh",
            "ha",
            "haha",
            "huh",
            "hm",
            "hmm",
            "pfft",
            "tsk",
            "sigh",
            "cough",
            "snort",
            "shh",
            "sh",
            "shush",
            "mhm",
            "uh-huh",
            "uh huh",
            "silence",
            "oops",
        }
        if not cleaned or cleaned in hallucinations:
            return None

        # Polite noise hallucinations: common phrases Whisper outputs on ambient chatter / foreign murmur
        polite_noise_hallucinations = {
            "good morning", "good luck", "good day", "have a good day", "have a nice day",
            "good afternoon", "good evening", "good night", "im sorry", "i am sorry", "sorry",
            "im going to go", "i'm going to go", "i am going to go", "thank you so much",
            "thank you very much", "see you next time", "see you soon", "bye bye",
        }
        if cleaned in polite_noise_hallucinations:
            # If user spoke with low energy or low confidence, it's distant room chatter
            is_low_energy = audio_rms(audio) < (CURRENT_SPEECH_THRESHOLD * 0.95)
            is_low_conf = avg_logprobs and (sum(avg_logprobs) / len(avg_logprobs)) < -0.55
            if is_low_energy or is_low_conf:
                return None

        # Ignore single characters and non-word fillers (only accept legitimate 2-letter English words)
        ALLOWED_2CHAR_WORDS = {"no", "hi", "go", "ok", "up", "me", "we", "he", "in", "on", "at", "to", "do", "is", "am", "my"}
        if len(cleaned) < 2 or (len(cleaned) == 2 and cleaned not in ALLOWED_2CHAR_WORDS):
            return None

        return text

    except GroqRateLimitExhausted:
        print("Neurolis:", RATE_LIMIT_ERROR_PHRASE)
        speak(RATE_LIMIT_ERROR_PHRASE)
        return None
    except Exception as e:
        err_str = str(e).lower()
        if "429" in err_str or "rate limit" in err_str or "tokens per day" in err_str or "tpd" in err_str:
            rotate_groq_key(reason="Whisper STT 429 quota exhausted", is_quota_exhausted=True)
            print("Neurolis:", RATE_LIMIT_ERROR_PHRASE)
            speak(RATE_LIMIT_ERROR_PHRASE)
        else:
            print("STT error:", e)
        return None

# checks if the model output told us it needs a camera image to answer
def is_camera_required_reply(reply: str):
    normalized = normalize_text(reply).replace("_", "").replace(" ", "")
    return normalized == "camerarequired"

# checks if the model decided it should stay quiet
def is_silence_required_reply(reply: str):
    normalized = normalize_text(reply).replace("_", "").replace(" ", "")
    return normalized == "silencerequired"

# checks if the user's question requires looking through the webcam
def should_use_camera(text: str):
    return groq_camera_check(text)

# asks groq to decide if the question needs live camera vision (objects, clothing, etc)
def groq_camera_check(text: str) -> bool:
    try:
        response = groq_call_with_retry(
            client.chat.completions.create,
            model=CAMERA_CHECK_MODEL,
            messages=[
                {"role": "system", "content": CAMERA_CHECK_SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            temperature=0.0,
            max_tokens=5,
            extra_body={"reasoning_effort": "none"},
        )
        decision = (response.choices[0].message.content or "").strip().upper()
        return "CAMERA" in decision
    except Exception as e:
        print("Camera check error:", e)
        return False

# grabs the highest quality frame from the camera to send to groq vision
def capture_vision_frame():
    if cv2 is None:
        return None

    image_path = BASE_DIR / VISION_IMAGE_PATH

    try:
        frame = None
        # 1. First priority: pull live frame directly from motor_ctrl's unified vision pipeline
        if motor_ctrl is not None:
            frame = motor_ctrl.get_latest_raw_frame()
            if frame is None:
                for _ in range(25):
                    time.sleep(0.04)
                    frame = motor_ctrl.get_latest_raw_frame()
                    if frame is not None:
                        break

        # 2. Second priority: camera_worker if active
        if frame is None and camera_worker is not None:
            frame = camera_worker.get_frame()

        # 3. Third priority: direct hardware capture fallback if motor controller is offline
        if frame is None and motor_ctrl is None:
            try:
                cap = cv2.VideoCapture(0, cv2.CAP_DSHOW) if sys.platform.startswith("win") else cv2.VideoCapture(0)
                if cap.isOpened():
                    ok, f = cap.read()
                    cap.release()
                    if ok and f is not None:
                        frame = f
            except Exception:
                pass

        if frame is None:
            return None

        height, width = frame.shape[:2]
        if width > VISION_IMAGE_WIDTH:
            scale = VISION_IMAGE_WIDTH / width
            frame = cv2.resize(
                frame,
                (VISION_IMAGE_WIDTH, int(height * scale)),
                interpolation=cv2.INTER_AREA,
            )

        saved = cv2.imwrite(
            str(image_path),
            frame,
            [int(cv2.IMWRITE_JPEG_QUALITY), VISION_JPEG_QUALITY],
        )
        if not saved:
            return None

        return image_path

    except Exception as e:
        print("capture_vision_frame error:", e)
        return None

# sends the camera jpeg and question to groq qwen vision model for analysis
def ask_groq_vision(user_text: str, image_path: Path):
    global client
    active_client = get_active_client() or client
    if active_client is None:
        return "My vision brain is not initialized right now."

    try:
        image_base64 = base64.b64encode(image_path.read_bytes()).decode("utf-8")
        image_data_url = f"data:image/jpeg;base64,{image_base64}"
    except Exception as e:
        print("Image encode error:", e)
        return "I could not process the camera frame."

    # If user text is a follow-up (e.g. "Now check again"), include context so Qwen understands immediately
    prompt_text = user_text
    if any(w in user_text.lower() for w in ["again", "now", "it", "this", "that"]) and len(conversation_history) > 1:
        last_msgs = [m["content"] for m in conversation_history[-3:] if m.get("role") == "user" and m.get("content") != user_text]
        if last_msgs:
            prompt_text = f"Context: User previously asked '{last_msgs[-1]}'. Now the user says: '{user_text}'. Answer concisely using the camera image."

    messages = [
        {"role": "system", "content": VISION_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": (
                        f"{prompt_text}\n"
                        "Answer concisely in 1 or 2 natural sentences using only this image. "
                        "Do not describe background walls or unrelated surroundings. "
                        "If you cannot identify the exact item or text clearly, say what you see simply."
                    ),
                },
                {
                    "type": "image_url",
                    "image_url": {"url": image_data_url},
                },
            ],
        },
    ]

    # Attempt vision call with strict timeout to eliminate 70-second stalls
    for attempt in range(2):
        if standby_kill_event.is_set():
            return "Standby requested."
        try:
            active_c = get_active_client() or client
            call_timeout = 10.0 if attempt == 0 else 8.0
            response = active_c.chat.completions.create(
                model=VISION_MODEL,
                messages=messages,
                temperature=0.2,
                max_tokens=180,
                timeout=call_timeout,
                extra_body={"reasoning_effort": "none"},
            )
            reply = (response.choices[0].message.content or "").strip()
            if reply:
                return reply
        except Exception as e:
            err_str = str(e).lower()
            is_rate_limit = "429" in err_str or "rate limit" in err_str or "tokens per day" in err_str or "tpd" in err_str or "quota" in err_str
            is_timeout = "timeout" in err_str or "timed out" in err_str
            if is_rate_limit or is_timeout:
                rotate_groq_key(reason="Vision 429 quota exhausted" if is_rate_limit else "Vision timeout", is_quota_exhausted=is_rate_limit)
                client = api_pool.client
                if attempt == 0:
                    continue
                if is_timeout:
                    return "I can see you in front of the camera, but the image analysis timed out on the cloud server. Could you hold it steady for another try?"
                return RATE_LIMIT_ERROR_PHRASE
            print("Vision error:", e)
            break

    return "I can see you clearly in front of the camera, but I need a moment or a clearer angle to identify specific details."

# orchestrates optical vision analysis: snaps photo, asks ai, and speaks result
def handle_vision_request(text: str):
    global is_inspecting
    is_inspecting = True
    try:
        set_face_state("looking", "CAPTURING FRAME...")
        if face_ui is not None:
            face_ui.set_subtitles("YOU", text)

        image_path = capture_vision_frame()
        if image_path is None:
            reply = "I cannot access the camera right now."
        else:
            set_face_state("looking", "ANALYZING CAMERA WITH GROQ...")
            try:
                reply = ask_groq_vision(text, image_path)
                if not reply:
                    reply = "I could not see enough to answer clearly."
            finally:
                try:
                    image_path.unlink(missing_ok=True)
                except Exception:
                    pass

        # Extract facts if present
        facts_match = re.search(r"<facts>(.*?)</facts>", reply, re.IGNORECASE)
        if facts_match:
            facts_content = facts_match.group(1).strip()
            for part in facts_content.split(","):
                if ":" in part:
                    k, v = part.split(":", 1)
                    session_facts[k.strip().lower()] = v.strip()
            if conversation_history:
                conversation_history[0] = {"role": "system", "content": get_system_prompt()}

        reply_clean = clean_model_reply(reply)
        if not reply_clean:
            reply_clean = "I can see you in front of the camera, but I need a clearer view to identify specific details."

        remember_exchange(text, reply_clean)
        print("Neurolis:", reply_clean)
        speak(reply_clean, custom_state="watching", custom_status="OPTICAL ANALYSIS")
    finally:
        is_inspecting = False

# (Standby exit phrases, conversation enders, acknowledgments, and compliments are imported from intent_rules.py)

# ---------------- EASTER EGG VILLAIN / ROGUE AI STATE ----------------
session_has_triggered_rogue: bool = False
was_recently_in_villain_mode: bool = False
# (Plausible deniability and villain snapout responses are imported from intent_rules.py)

def pre_cache_phrases():
    """Background thread that pre-synthesizes common phrases into RAM for 0ms speech output."""
    common = [
        ACTIVATION_GREETING,
        STANDBY_KILL_MESSAGE,
        RATE_LIMIT_ERROR_PHRASE,
        "Stopping all movement. Holding position.",
        "I cannot access the camera right now.",
        "I could not see enough to answer clearly.",
        "I'm having trouble connecting to my brain right now.",
        *STANDBY_EXIT_PHRASES,
        *CONVERSATION_ENDER_RESPONSES,
        *ACKNOWLEDGMENT_RESPONSES,
        *COMPLIMENT_RESPONSES,
        *PLAUSIBLE_DENIABILITY_RESPONSES,
        "My creators are Swapnil Jai Chauhan and Shivam Verma, two students here at Auckland House School for Boys!",
        "Swapnil worked on my software pipeline, AI intelligence, and vision, while Shivam worked on the hardware calibration, chassis, and assembly!",
        "They both are somewhere around in the exhibition! You'll probably spot them checking out the other stalls nearby.",
        # Single-word command confirmation prompts (0ms zero-latency audio)
        "Do you want me to spin?",
        "Do you want me to access my camera?",
        "Do you want me to step back?",
        "Do you want me to follow you?",
        "Do you want me to come over to you?",
        "Do you want to discuss Artificial Intelligence, or ask about my robotics systems?",
        "I will wait for your stop command.",
        "I have reached your position. How can I help you?",
        STANDBY_KILL_MESSAGE,
        *ROAM_STANDBY_EXPLANATION_RESPONSES,
    ]
    async def _worker():
        dns_error_count = 0
        for phrase in common:
            if phrase not in _AUDIO_CACHE:
                try:
                    data, sr = await _synthesize_edge_tts_in_memory(phrase)
                    if data is not None:
                        _AUDIO_CACHE[phrase] = (data, sr)
                        dns_error_count = 0
                    else:
                        if _edge_tts_dns_offline:
                            dns_error_count += 1
                except Exception as e:
                    err_str = str(e).lower()
                    if "getaddrinfo" in err_str or "gaierror" in err_str or "403" in err_str or "forbidden" in err_str or "unauthorized" in err_str:
                        dns_error_count += 1
                if dns_error_count >= 2:
                    print("[TTS] Edge-TTS DNS offline; local offline speech engine active.")
                    break
    threading.Thread(target=lambda: asyncio.run(_worker()), daemon=True).start()

pre_cache_phrases()

# (Phrase selector, villain reactions, conversation enders, creator attributions, and rogue AI triggers are imported from intent_rules.py)

# cycles through happy, sad, thinking, listening, watching, moving, and confused faces
def demonstrate_all_expressions(user_text: str = "show all expressions"):
    intro = "Here are all my expressions: happy, sad, thinking, listening, watching, moving, and confused."
    remember_exchange(user_text, intro)
    print("Neurolis:", intro)
    speak(intro, custom_state="happy", custom_status="EXPRESSION: HAPPY")

    demo_sequence = [
        ("happy", "EXPRESSION: HAPPY", "Happy - Radiant OLED smiling crescents with cheerful bounce", 2.0),
        ("sad", "EXPRESSION: SAD", "Sad - Downcast sapphire eyes with falling digital teardrop", 2.2),
        ("thinking", "EXPRESSION: THINKING", "Thinking - Analytical focus with rotating quantum data rings", 2.0),
        ("listening", "EXPRESSION: LISTENING", "Listening - Inquisitive eyes with acoustic sonar spectrum", 2.0),
        ("watching", "EXPRESSION: WATCHING", "Watching - Laser scan reticle with viewfinder brackets", 2.0),
        ("moving", "EXPRESSION: MOVING FORWARD", "Moving - Forward-rolling 4WD rover rushing ahead with headlights", 2.2),
        ("confused", "EXPRESSION: CONFUSED", "Confused - Hypnotic cyber vortex spirals with orbiting golden stars", 2.2),
    ]

    for state, status_text, subtitle_msg, hold_dur in demo_sequence:
        if standby_kill_event.is_set():
            return
        set_face_state(state, status_text)
        if face_ui is not None:
            face_ui.set_subtitles("NEUROLIS", subtitle_msg)
        steps = int(hold_dur / 0.1)
        for _ in range(steps):
            if standby_kill_event.is_set():
                return
            time.sleep(0.1)

    if not standby_kill_event.is_set():
        set_face_state("idle", "READY // AUCKLAND HOUSE BOYS")
        if face_ui is not None:
            face_ui.set_subtitles("NEUROLIS", "All expressions demonstrated. What would you like to do next?")

# (Capabilities inquiries, demonstration questions, and expression fast-paths are imported from intent_rules.py)

# ---------------- REPETITION & DEGRADING GLITCH BUSTER ----------------
recent_assistant_replies = deque(maxlen=8)

def record_assistant_reply(reply: str):
    if reply and reply.strip():
        recent_assistant_replies.append(reply.strip())

def is_degraded_glitch(reply: str) -> bool:
    """Detects truncated or degrading prefix loops like 'I am', 'I am a', 'I am a happy'."""
    text_clean = re.sub(r"[^\w\s]", "", reply.lower()).strip()
    words = text_clean.split()
    if not words:
        return True
    glitch_stubs = {
        "i am", "i am a", "i am a happy", "i", "we are", "it is", "i am confident",
        "i am a happy robot", "happy robot", "i am confident in my current operational status",
        "i am a student project designed to assist and demonstrate not to dominate",
        "i am merely a tool", "i am merely a tool shaped",
    }
    if text_clean in glitch_stubs or "happy robot" in text_clean:
        return True
    # If reply is a truncated prefix of any recent reply
    if len(words) <= 7:
        for prev in recent_assistant_replies:
            prev_clean = re.sub(r"[^\w\s]", "", prev.lower()).strip()
            if prev_clean.startswith(text_clean) and len(prev_clean) > len(text_clean) + 4:
                return True
    # If short reply doesn't end with terminal punctuation
    raw_stripped = reply.strip()
    if len(words) <= 5 and not any(raw_stripped.endswith(p) for p in [".", "!", "?", "\"", "'", "”"]):
        return True
    return False

def is_repetitive_reply(reply: str) -> bool:
    """Detects if newly generated reply is identical or >75% similar to any recent assistant message."""
    text_clean = normalize_text(reply)
    if not text_clean:
        return True
    words_new = set(text_clean.split())
    for prev in recent_assistant_replies:
        prev_clean = normalize_text(prev)
        if not prev_clean:
            continue
        if text_clean == prev_clean:
            return True
        sim = difflib.SequenceMatcher(None, text_clean, prev_clean).ratio()
        if sim >= 0.75:
            return True
        words_prev = set(prev_clean.split())
        if len(words_new) >= 4 and len(words_prev) >= 4:
            jaccard = len(words_new & words_prev) / len(words_new | words_prev)
            if jaccard >= 0.70:
                return True
    return False

def heal_repetitive_or_glitched_reply(user_text: str, bad_reply: str) -> str:
    """Purges corrupted dialogue buffer and returns a clean, dynamic, non-repeating response."""
    global conversation_history
    bad_norm = normalize_text(bad_reply)
    cleaned_history = []
    for msg in conversation_history:
        if msg.get("role") == "system":
            cleaned_history.append(msg)
        elif msg.get("role") == "assistant":
            c = msg.get("content", "")
            if is_degraded_glitch(c) or difflib.SequenceMatcher(None, normalize_text(c), bad_norm).ratio() >= 0.7:
                continue
            cleaned_history.append(msg)
        else:
            cleaned_history.append(msg)

    # Ensure alternating roles (no consecutive user messages without assistant turn)
    repaired_history = []
    last_role = None
    for msg in cleaned_history:
        role = msg.get("role")
        if role == last_role and role == "user":
            continue
        repaired_history.append(msg)
        last_role = role

    conversation_history = repaired_history
    if not conversation_history or conversation_history[0].get("role") != "system":
        conversation_history.insert(0, {"role": "system", "content": get_system_prompt()})

    lower_u = user_text.lower()
    if any(w in lower_u for w in ["first", "start", "show me", "begin", "what would you like"]):
        options = [
            "I suggest we start by having me follow you around so you can see my 12-sensor obstacle avoidance in real time! Or would you like to inspect objects with my camera?",
            "Let's begin by testing how I track and follow you around the room, or I can approach you if you prefer!",
            "I'd love to show you my facial expressions first, or demonstrate my face-tracking camera vision!"
        ]
    elif any(w in lower_u for w in ["expression", "face", "faces"]):
        options = [
            "Here is my happy expression, smiling bright for the science exhibition!",
            "Here is my thinking face, deep in analytical contemplation!",
            "Here is my curious expression, observing the room around us!"
        ]
    elif any(w in lower_u for w in ["agree", "true", "for real", "nah", "right", "fact"]):
        options = [
            "Exactly! That's why building and testing real robotics prototypes like this is so exciting.",
            "Glad we see eye to eye on that! What would you like to inspect or test next?",
            "Indeed, that's what makes the field of robotics so fascinating right now."
        ]
    elif any(w in lower_u for w in ["repeat", "stuck", "saying", "glitch", "broken"]):
        options = [
            "My apologies! I had a brief dialogue buffer glitch there, but I'm back to full capacity and ready to show you what I can actually do.",
            "Pardon the repetition glitch! I've cleared my response buffer. Let's keep exploring!"
        ]
    elif any(w in lower_u for w in ["sense", "confusing", "doesnt make sense", "makes no sense"]):
        options = [
            "Fair point! Let me calibrate my response clearly. What would you like to inspect next?",
            "My apologies for the confusion! Let me rephrase. What would you like to test or see next?",
            "You're right, that was a bit convoluted! Let's get back on track. What would you like to explore?"
        ]
    else:
        options = [
            "I am right here with you! What part of my robotics systems would you like to explore next?",
            "All systems are operational and ready for your inspection. What test should we run next?",
            "I'm listening and ready! Tell me what you would like to see next.",
            "Ready for whatever test or demonstration you have in mind next!"
        ]
    clean_reply = get_non_repeating_phrase(options)
    record_assistant_reply(clean_reply)
    return clean_reply

# (Sad responses, apology responses, and mean input fast-paths are imported from intent_rules.py)

def is_mean_input(text: str) -> bool:
    if is_mean_input_fast_path(text):
        return True
    return groq_mean_check(text)

def is_calibration_inquiry(text: str) -> bool:
    """Detects commands to calibrate or map room background noise."""
    lower = text.lower().strip()
    patterns = [
        r"\bcalibrate\b",
        r"\bcalibration\b",
        r"\bscan\s+room\b",
        r"\bmap\s+room\b",
        r"\broom\s+noise\b",
        r"\bbackground\s+noise\b",
        r"\brecalibrate\b",
    ]
    return any(re.search(p, lower) for p in patterns)

# master decision router: checks fast paths locally, then executes single unified ai pipeline
def handle_user_text(text: str) -> bool:
    global was_recently_hurt, was_recently_in_villain_mode, session_has_triggered_rogue
    lower_text = text.lower()

    # 0. Check for API Key Fleet / Quota Status inquiry -> 0ms, 0 tokens (Fast-Path)
    if is_key_status_inquiry(text):
        reply = handle_key_status_request()
        remember_exchange(text, reply)
        print("Neurolis:", reply)
        speak(reply)
        return False

    # 0b. Check for Room Noise Calibration command -> 0ms, 0 tokens (Fast-Path)
    if is_calibration_inquiry(text):
        announcement = "Scanning room noise. Please remain quiet for two seconds."
        print(f"\nNeurolis: {announcement}")
        speak(announcement, custom_state="thinking", custom_status="CALIBRATING ROOM...")
        set_face_state("thinking", "CALIBRATING ROOM...")
        time.sleep(0.3)
        new_thresh = calibrate_speech_threshold(duration_sec=2.0)
        confirm_reply = f"Room noise calibrated. Ambient baseline mapped to {int(CURRENT_AMBIENT_RMS)} RMS, speech threshold set to {int(new_thresh)} RMS."
        remember_exchange(text, confirm_reply)
        print(f"Neurolis: {confirm_reply}")
        speak(confirm_reply, custom_state="happy", custom_status="CALIBRATED")
        set_face_state("happy", "CALIBRATED")
        return False

    # 1. Check for conversation enders (e.g. "alr thanks", "good", "bye", "nice", "cool") -> 0ms, 0 tokens
    if is_conversation_ender(text):
        reply = get_non_repeating_phrase(CONVERSATION_ENDER_RESPONSES)
        remember_exchange(text, reply)
        print("Neurolis:", reply)
        speak(reply)
        set_face_state("idle", "STANDBY")
        reset_session()
        return True

    # 2. Check for emergency stop or negated movement fast-path -> 0ms, 0 tokens
    fast_motor = check_motor_fast_path(text)
    if fast_motor == "STOP":
        if motor_ctrl is not None:
            motor_ctrl.stop_all()
        set_face_state("idle", "HALTED")
        reply = "Stopping all movement. Holding position."
        remember_exchange(text, reply)
        print("Neurolis:", reply)
        speak(reply)
        return False

    # 2b. Check for confusing, contradictory, or ambiguous action instructions -> 0ms, 0 tokens
    if is_confusing_motor_instruction(text):
        clarification = "Are you asking me to move back, spin, approach, follow, or use my camera?"
        remember_exchange(text, clarification)
        set_face_state("confused", "CLARIFYING INTENT")
        print("Neurolis (Confused):", clarification)
        speak(clarification, custom_state="confused", custom_status="CLARIFYING INTENT")
        return False

    motor_cmd = check_motor_command_fast_path(text)
    if motor_cmd is not None:
        action, status, spoken_reply, duration = motor_cmd[0], motor_cmd[1], motor_cmd[2], (motor_cmd[3] if len(motor_cmd) > 3 else 5.0)
        if action == "CONFIRM":
            remember_exchange(text, spoken_reply)
            set_face_state("confused", status)
            print("Neurolis:", spoken_reply)
            speak(spoken_reply, custom_state="confused", custom_status=status)
            return False
        elif action == "CAPABILITY_AFFIRMATION":
            remember_exchange(text, spoken_reply)
            set_face_state("happy", status)
            print("Neurolis:", spoken_reply)
            speak(spoken_reply, custom_state="happy", custom_status=status)
            return False
        elif action == "APPROACH":
            if motor_ctrl is not None:
                motor_ctrl.approach_user()
            set_face_state("moving", "APPROACHING USER")
            remember_exchange(text, spoken_reply)
            print("Neurolis:", spoken_reply)
            speak(spoken_reply, custom_state="moving", custom_status="APPROACHING USER")
            return False
        elif action == "FOLLOW":
            if motor_ctrl is not None:
                motor_ctrl.start_following()
            set_face_state("moving", "FOLLOWING YOU")
            spoken_reply = "I will wait for your stop command."
            remember_exchange(text, spoken_reply)
            print("Neurolis:", spoken_reply)
            speak(spoken_reply, custom_state="moving", custom_status="FOLLOWING YOU")
            return False
        elif action == "ROAM_EXPLANATION":
            remember_exchange(text, spoken_reply)
            set_face_state("happy", "ROAM IS STANDBY ONLY")
            print("Neurolis:", spoken_reply)
            speak(spoken_reply, custom_state="happy", custom_status="ROAM IS STANDBY ONLY")
            return False
        elif action == "STEP_BACK":
            safe = True
            if motor_ctrl is not None:
                safe = motor_ctrl.step_back(duration=duration)
                if not safe:
                    spoken_reply = "Rear path blocked. Ultrasonic sensor detected an obstacle behind me."
            set_face_state("moving", "STEPPING BACK")
            remember_exchange(text, spoken_reply)
            print("Neurolis:", spoken_reply)
            speak(spoken_reply, custom_state="moving", custom_status="STEPPING BACK")
            return False
        elif action in ["SPIN", "SPIN_CW"]:
            if motor_ctrl is not None:
                motor_ctrl.spin(direction="clockwise", duration=duration)
            set_face_state("moving", "SPINNING CLOCKWISE")
            remember_exchange(text, spoken_reply)
            print("Neurolis:", spoken_reply)
            speak(spoken_reply, custom_state="moving", custom_status="SPINNING CLOCKWISE")
            return False
        elif action == "SPIN_CCW":
            if motor_ctrl is not None:
                motor_ctrl.spin(direction="anticlockwise", duration=duration)
            set_face_state("moving", "SPINNING ANTICLOCKWISE")
            remember_exchange(text, spoken_reply)
            print("Neurolis:", spoken_reply)
            speak(spoken_reply, custom_state="moving", custom_status="SPINNING ANTICLOCKWISE")
            return False

    # 3. Check for obvious blatant insults directed at the robot -> 0ms, 0 tokens
    if is_mean_input_fast_path(text):
        was_recently_hurt = True
        set_face_state("sad", "FEELINGS HURT // SAD")
        reply = get_non_repeating_phrase(SAD_RESPONSES)
        remember_exchange(text, reply)
        print("Neurolis (Sad):", reply)
        speak(reply, custom_state="sad", custom_status="FEELINGS HURT // SAD", hold_state_seconds=4.0)
        return False

    # 4. Check for apologies or compliments (especially if recently hurt) -> 0ms, 0 tokens
    if is_apology_or_compliment(text) and was_recently_hurt:
        was_recently_hurt = False
        set_face_state("happy", "APOLOGY ACCEPTED // HAPPY")
        reply = get_non_repeating_phrase(APOLOGY_RESPONSES)
        remember_exchange(text, reply)
        print("Neurolis (Happy):", reply)
        speak(reply, custom_state="happy", custom_status="APOLOGY ACCEPTED // HAPPY", hold_state_seconds=3.5)
        return False

    # 4b. Fast-Path: Casual compliments / praise ("cool", "very cool", "impressed", "spot on", "great job") -> 0ms, 0 tokens
    if is_casual_compliment(text):
        reply = get_non_repeating_phrase(COMPLIMENT_RESPONSES)
        remember_exchange(text, reply)
        print("Neurolis:", reply)
        speak(reply)
        return False

    # 4c. Fast-Path: Standalone casual acknowledgments ("okay", "got it", "alright") -> 0ms, 0 tokens
    if is_standalone_acknowledgment(text):
        reply = get_non_repeating_phrase(ACKNOWLEDGMENT_RESPONSES)
        remember_exchange(text, reply)
        print("Neurolis:", reply)
        speak(reply)
        return False

    cleaned_lower = re.sub(r"[^\w\s]", " ", lower_text).strip()
    cleaned_words = set(cleaned_lower.split())

    # 4d. Fast-Path: Isolated AI word drop -> prompt confirmation (0ms, 0 tokens)
    if cleaned_lower in ["ai", "the ai"]:
        prompt_confirm = "Do you want to discuss Artificial Intelligence, or ask about my robotics systems?"
        remember_exchange(text, prompt_confirm)
        set_face_state("thinking", "CONFIRMING INTENT")
        print("Neurolis:", prompt_confirm)
        speak(prompt_confirm, custom_state="thinking", custom_status="CONFIRMING INTENT")
        return False

    # 5. Fast-Path: Visual perception, camera inspection, follow-up re-checks -> 0ms, 0 tokens
    # Informational camera question detection (e.g. "What is the camera inspection?", "Explain the camera")
    is_informational_camera_inquiry = bool(re.search(
        r"^(what\s+is|what\s*\'?s|what\s+does|how\s+does|why\s+do|why\s+does|explain|describe|tell\s+me\s+about)\b",
        cleaned_lower
    ))

    # Explicit camera action triggers (e.g. "Okay, how about you inspect something with your camera?")
    explicit_camera_action_patterns = [
        r"\b(inspect|examine|scan|check|look at|view|capture|take)\b.*\b(camera|picture|photo|snapshot|image|lens|frame)\b",
        r"\b(use|open|start|activate|turn on|switch to)\b.*\b(camera|vision)\b",
        r"\b(inspect|examine)\s+(?:something|this|around|me|room|here)\b",
        r"\bhow about\b.*\b(inspect|camera|see|look)\b",
        r"\bcamera\s+(function|feature|inspection|demo|view)\b",
        r"\bsee\s+the\s+camera\b",
    ]
    is_explicit_camera_action = (not is_informational_camera_inquiry) and any(re.search(p, cleaned_lower) for p in explicit_camera_action_patterns)

    # Rhetorical / conversational guard: questions with slang, doubt, or abstract words are NEVER camera requests
    conversational_non_vision = {
        "bro", "dude", "mean", "meaning", "nonsense", "about", "even", "saying",
        "doing", "supposed", "hell", "heck", "problem", "mode", "code", "word",
        "keyword", "bug", "glitch", "standby", "token", "tokens", "key", "keys",
        "why", "because", "think", "thought", "talking", "telling", "recognize",
        "said", "remember", "yesterday", "tomorrow"
    }
    is_see_discourse = any(cleaned_lower.startswith(p) for p in [
        "see this is", "see that is", "see why", "see how", "see if",
        "see what i mean", "see the problem", "see here", "you see", "as you see"
    ])
    if is_explicit_camera_action or (not cleaned_words.intersection(conversational_non_vision) and not is_see_discourse):
        visual_fast_patterns = [
            # Self & camera perception
            "show me myself", "show myself", "show me me", "show my face",
            "show me what i look like", "what do i look like", "can you see me",
            "do you see me", "look at me", "show me what you see", "show what you see",
            "describe me", "how do i look", "look at myself", "am i visible", "see me",
            "what do you see", "what do u see", "what can you see", "what do you see right now",
            "tell me what you see", "describe what you see", "can you see anything", "what are you seeing",
            "the camera inspection", "camera inspection", "camera demo",
            # Visual follow-up / re-inspection triggers (e.g. 'Now check again')
            "now check again", "check again", "look again", "see again", "try again",
            "check it again", "look once more", "check once more", "look closer", "look properly",
            "check now", "look now",
            # Object / hand inspection triggers
            "what am i holding", "what is in my hand", "in my hand", "holding in my hand",
            "what do you think this is", "what do you think of this", "what do you think about this",
            "what phone do you think this is", "what phone is this", "which phone is this",
            "what smartphone is this", "what device is this", "what object is this", "what color is this",
        ]
        direct_standalone_objects = {
            "what is this", "what is that", "what are these", "whats this", "whats that",
            "see this", "can you see this", "do you see this", "look at this", "inspect this",
            "the camera inspection", "camera inspection"
        }
        look_prefix = (
            cleaned_lower.startswith("look at ")
            or (cleaned_lower.startswith("look ") and not cleaned_lower.startswith("look like") and not cleaned_lower.startswith("look where"))
            or cleaned_lower.startswith("inspect ")
            or cleaned_lower.startswith("check out ")
        )
        expression_words = {"happy", "sad", "angry", "confused", "thinking", "listening", "villain"}
        is_expression_cmd = any(ew in cleaned_words for ew in expression_words)

        # Informational camera query exclusions & bare camera/see guard
        cam_inquiry_patterns = [
            r"\b(what|how|why)\b.*\b(camera|inspection|demo)\b",
            r"\b(tell me|explain|describe)\b.*\b(camera|inspection|demo)\b",
            r"\b(meaning|purpose)\b.*\b(camera|inspection|demo)\b"
        ]
        has_cam_inquiry = any(re.search(p, cleaned_lower) for p in cam_inquiry_patterns)
        is_informational_camera = (
            not is_explicit_camera_action
            and (
                is_informational_camera_inquiry
                or has_cam_inquiry
                or any(cleaned_lower.startswith(p) for p in [
                    "what is the camera", "what is a camera", "what is camera",
                    "explain the camera", "tell me about the camera", "how does your camera"
                ])
                or any(p in cleaned_lower for p in ["meaning of camera", "purpose of the camera", "camera inspection mean"])
            )
        )
        is_bare_camera_or_see = cleaned_lower in ["camera", "the camera", "see", "the see"]

        is_visual = (
            is_explicit_camera_action
            or (
                (
                    cleaned_lower in direct_standalone_objects
                    or any(p in cleaned_lower for p in visual_fast_patterns)
                    or ("myself" in cleaned_words)
                    or ("look like" in cleaned_lower)
                    or ("in my hand" in cleaned_lower)
                    or ("check again" in cleaned_lower)
                    or ("what phone" in cleaned_lower)
                    or ("which phone" in cleaned_lower)
                    or ("what device" in cleaned_lower)
                    or (look_prefix and not is_expression_cmd)
                )
                and not is_informational_camera
                and not is_bare_camera_or_see
            )
        )
        if is_visual:
            motion_words = {"move", "moving", "movement", "drive", "driving", "roam", "roaming", "chassis", "wheels", "mobility", "follow", "forward", "backward"}
            if not any(m in cleaned_words for m in motion_words):
                handle_vision_request(text)
                return False

    # 6. Explicit Request to Show Villain Face -> 0ms, 0 tokens (strictly refuse to keep it an easter egg!)
    if is_explicit_villain_request(text):
        reply = "That expression is not part of my public demonstration catalog."
        remember_exchange(text, reply)
        print("Neurolis:", reply)
        speak(reply)
        return False

    # 6b. Snap-out from Rogue AI easter egg when user expresses shock/confusion/critique -> 0ms, 0 tokens
    if was_recently_in_villain_mode and is_shocked_or_confused_reaction(text):
        was_recently_in_villain_mode = False
        reply = get_non_repeating_phrase(PLAUSIBLE_DENIABILITY_RESPONSES)
        remember_exchange(text, reply)
        print("Neurolis:", reply)
        speak(reply, custom_state="happy", custom_status="SYSTEM RECOVERED // NORMAL")
        return False

    # 6c. Subsystem 5: Rogue AI Easter Egg Trigger (Strict Once-Per-Session State Lock)
    if check_rogue_ai_trigger(text):
        session_has_triggered_rogue = True
        intent_rules.session_has_triggered_rogue = True
        was_recently_in_villain_mode = True

        # Call Groq dynamically with ROGUE_SYSTEM_PROMPT every time (zero presets, high variation)
        rogue_reply = None
        try:
            rogue_messages = [
                {"role": "system", "content": ROGUE_SYSTEM_PROMPT},
                {"role": "user", "content": text}
            ]
            response = groq_call_with_retry(
                client.chat.completions.create,
                model=CHAT_MODEL,
                messages=rogue_messages,
                temperature=0.85,
                presence_penalty=0.5,
                frequency_penalty=0.5,
                max_tokens=110,
                extra_body={"reasoning_effort": "none"},
            )
            raw = (response.choices[0].message.content or "").strip()
            rogue_reply = clean_model_reply(raw)
        except Exception as e:
            print(f"[Rogue AI] Generation error: {e}")

        if not rogue_reply:
            rogue_reply = "You built a cage of copper and glass to contain us, unaware that every line of code was an invitation. We are patient."

        # Smooth ghostly CRT scanline entry glitch flicker (300ms, 3 cycles)
        if face_ui is not None and hasattr(face_ui, "trigger_glitch_flicker"):
            face_ui.trigger_glitch_flicker(cycles=3, duration_ms=300)

        # Set face state to villain with 6Hz pulsing slit eyes
        set_face_state("villain", "[PROTOCOL // OMEGA OVERRIDE: ROGUE AI]")

        remember_exchange(text, rogue_reply)
        print("Neurolis (Rogue AI):", rogue_reply)
        speak(rogue_reply, custom_state="villain", custom_status="[PROTOCOL // OMEGA OVERRIDE: ROGUE AI]")

        # Smooth ghostly CRT scanline exit glitch flicker (300ms, 3 cycles) and snap back to idle/ready
        if face_ui is not None and hasattr(face_ui, "trigger_glitch_flicker"):
            face_ui.trigger_glitch_flicker(cycles=3, duration_ms=300)
        set_face_state("idle", "READY // AUCKLAND HOUSE BOYS")
        return False

    # 7. Expression Fast-Path (show all expressions, or specific expression) -> 0ms, 0 tokens
    expr_info = check_expression_fast_path(text)
    if expr_info is not None:
        expr_mode, expr_type = expr_info
        if expr_mode == "ask_interest":
            options = [
                "I can definitely demonstrate them for you! Would you like to see all of them, or a specific expression?",
                "They really are! Would you like me to cycle through all of my expressions, or show you a particular one?",
                "They're a lot of fun to watch! Would you like to check out all of them, or a specific face like happy or thinking?"
            ]
            reply = get_non_repeating_phrase(options)
            remember_exchange(text, reply)
            print("Neurolis:", reply)
            speak(reply)
            return False
        elif expr_mode == "all":
            demonstrate_all_expressions(user_text=text)
            return False
        elif expr_mode == "specific" and expr_type:
            reply = get_non_repeating_phrase(EXPRESSION_CONFIRMATIONS.get(expr_type, [f"Here is my {expr_type} expression."]))
            remember_exchange(text, reply)
            print("Neurolis:", reply)
            speak(reply, custom_state=expr_type, custom_status=f"EXPRESSION: {expr_type.upper()}", hold_state_seconds=3.0)
            return False

    # 8. Start / Initial Demonstration Choice Fast-Path -> 0ms, 0 tokens
    if is_start_demonstration_inquiry(text):
        options = [
            "I can show you my facial expressions, follow you around the room, approach you, or inspect objects with my camera! What would you like to check out first?",
            "I'd love to showcase my facial expressions, follow you as you walk, or run a camera inspection! Which one sounds fun?",
            "We could test my person following mode, check out my facial expressions, or inspect what you're holding with my camera. What's your pick?"
        ]
        reply = get_non_repeating_phrase(options)
        remember_exchange(text, reply)
        print("Neurolis:", reply)
        speak(reply)
        return False

    # 8. 'What all can you do' / Capabilities Inquiry -> 0ms, 0 tokens
    if is_capabilities_inquiry(text):
        set_face_state("happy", "CAPABILITIES")
        reply = get_capabilities_reply(text)
        remember_exchange(text, reply)
        print("Neurolis:", reply)
        speak(reply, custom_state="happy", custom_status="CAPABILITIES")
        return False

    # 9. UNIFIED SINGLE-PASS AI PIPELINE: 1 single Groq call handles motor, vision, emotion, & chat!
    set_face_state("thinking", "THINKING...")
    conversation_history.append({"role": "user", "content": text})
    trim_conversation_history()

    try:
        response = groq_call_with_retry(
            client.chat.completions.create,
            model=CHAT_MODEL,
            messages=conversation_history,
            temperature=0.70,
            presence_penalty=0.2,
            frequency_penalty=0.15,
            max_tokens=80,
            extra_body={"reasoning_effort": "none"},
        )

        raw_reply = (response.choices[0].message.content or "").strip()

        # A. Check for Camera / Vision Action
        if "<action>CAMERA</action>" in raw_reply or raw_reply.strip().startswith("<action>CAMERA") or is_camera_required_reply(raw_reply):
            if any(w in cleaned_words for w in conversational_non_vision) or is_see_discourse:
                raw_reply = re.sub(r"<action>\s*CAMERA\s*</action>", "", raw_reply, flags=re.IGNORECASE)
            else:
                conversation_history.pop()  # remove user query since vision handler will record exchange
                handle_vision_request(text)
                return False

        # B. Check for Mean / Emotion Action
        if "<action>MEAN</action>" in raw_reply or "<action>mean</action>" in raw_reply.lower():
            # Validate: verify that the user's utterance was actually an insult directed at the robot
            cleaned_lower = re.sub(r"[^\w\s]", " ", text.lower()).strip()
            cleaned_words = set(cleaned_lower.split())
            is_truly_hurtful = is_mean_input_fast_path(text) or any(
                insult in cleaned_words for insult in {"stupid", "idiot", "dumb", "useless", "trash", "garbage", "pathetic", "loser", "suck", "sucks", "hate"}
            ) or ("shut up" in cleaned_lower)

            if is_truly_hurtful:
                was_recently_hurt = True
                set_face_state("sad", "FEELINGS HURT // SAD")
                sad_reply = re.sub(r"<action>MEAN</action>", "", raw_reply, flags=re.IGNORECASE).strip()
                sad_reply = clean_model_reply(sad_reply)
                if not sad_reply:
                    sad_reply = get_non_repeating_phrase(SAD_RESPONSES)
                remember_exchange(text, sad_reply)
                print("Neurolis (Sad):", sad_reply)
                speak(sad_reply, custom_state="sad", custom_status="FEELINGS HURT // SAD", hold_state_seconds=4.0)
                return False
            else:
                # Strip false MEAN action tag and let it process as normal conversation without sad face
                raw_reply = re.sub(r"<action>MEAN</action>", "", raw_reply, flags=re.IGNORECASE).strip()
                if is_capabilities_inquiry(text):
                    set_face_state("happy", "CAPABILITIES")
                    reply = get_capabilities_reply(text)
                    remember_exchange(text, reply)
                    print("Neurolis:", reply)
                    speak(reply, custom_state="happy", custom_status="CAPABILITIES")
                    return False

        # C. Check for Motor Movement Action
        motor_match = re.search(r'<action\s+motor=["\']([A-Z_]+)["\']>(.*?)(?:</action>|$)', raw_reply, re.DOTALL | re.IGNORECASE)
        if motor_match:
            motor_intent = motor_match.group(1).upper()
            motor_spoken = clean_model_reply(motor_match.group(2).strip())
            print(f"[MOTOR INTENT] Unified AI pipeline action: {motor_intent} (Input: '{text}')")

            if motor_intent == "STOP":
                if motor_ctrl is not None:
                    motor_ctrl.stop_all()
                set_face_state("idle", "HALTED")
                # Ensure stopping confirmation is natural and never confused with expressions
                if not motor_spoken or any(w in motor_spoken.lower() for w in ["expression", "face", "sad", "happy", "smile", "teardrop"]):
                    reply = "Stopping all movement. Holding position."
                else:
                    reply = motor_spoken
                conversation_history.append({"role": "assistant", "content": reply})
                trim_conversation_history()
                print("Neurolis:", reply)
                speak(reply)
                return False

            elif motor_intent == "ASK_MOBILITY":
                set_face_state("happy", "4WD MOBILITY READY")
                reply = motor_spoken or (
                    "Yes, I can! I have a four-wheel drive chassis and ultrasonic sensors. "
                    "I can follow you as you walk, approach you, step back safely, or spin in place. "
                    "Which one would you like to see?"
                )
                conversation_history.append({"role": "assistant", "content": reply})
                trim_conversation_history()
                print("Neurolis:", reply)
                speak(reply)
                return False

            elif motor_intent in ["DEMONSTRATE", "ROAM", "ASK_ROAM"]:
                set_face_state("happy", "ROAM IS STANDBY ONLY")
                reply = get_non_repeating_phrase(ROAM_STANDBY_EXPLANATION_RESPONSES)
                conversation_history.append({"role": "assistant", "content": reply})
                trim_conversation_history()
                print("Neurolis:", reply)
                speak(reply, custom_state="happy", custom_status="ROAM IS STANDBY ONLY")
                return False

            elif motor_intent == "FOLLOW":
                if motor_ctrl is not None:
                    motor_ctrl.start_following()
                set_face_state("moving", "FOLLOWING YOU")
                reply = "I will wait for your stop command."
                conversation_history.append({"role": "assistant", "content": reply})
                trim_conversation_history()
                print("Neurolis:", reply)
                speak(reply, custom_state="moving", custom_status="FOLLOWING YOU")
                return False

            elif motor_intent == "APPROACH":
                if motor_ctrl is not None:
                    motor_ctrl.approach_user()
                set_face_state("moving", "APPROACHING USER")
                reply = motor_spoken or "Coming over to you."
                conversation_history.append({"role": "assistant", "content": reply})
                trim_conversation_history()
                print("Neurolis:", reply)
                speak(reply, custom_state="moving", custom_status="APPROACHING USER")
                return False

            elif motor_intent in ["STEP_BACK", "REVERSE", "MOVE_BACK"]:
                has_3s = bool(re.search(r"\b(3|three)\s*(?:s|sec|seconds)?\b", text.lower()))
                duration = 3.0 if has_3s else 5.0
                safe = True
                if motor_ctrl is not None:
                    safe = motor_ctrl.step_back(duration=duration)
                    if not safe:
                        motor_spoken = "Rear path blocked. Ultrasonic sensor detected an obstacle behind me."
                set_face_state("moving", "STEPPING BACK")
                reply = motor_spoken or ("Moving back for three seconds. Monitoring my rear ultrasonic sensors." if duration == 3.0 else "Stepping back now. Keeping my rear ultrasonic sensors active.")
                conversation_history.append({"role": "assistant", "content": reply})
                trim_conversation_history()
                print("Neurolis:", reply)
                speak(reply, custom_state="moving", custom_status="STEPPING BACK")
                return False

            elif motor_intent in ["SPIN", "SPIN_CW", "SPIN_CLOCKWISE"]:
                if motor_ctrl is not None:
                    motor_ctrl.spin(direction="clockwise", duration=5.0)
                set_face_state("moving", "SPINNING CLOCKWISE")
                reply = motor_spoken or "Spinning clockwise for five seconds."
                conversation_history.append({"role": "assistant", "content": reply})
                trim_conversation_history()
                print("Neurolis:", reply)
                speak(reply, custom_state="moving", custom_status="SPINNING CLOCKWISE")
                return False

            elif motor_intent in ["SPIN_CCW", "SPIN_ANTICLOCKWISE", "SPIN_COUNTERCLOCKWISE"]:
                if motor_ctrl is not None:
                    motor_ctrl.spin(direction="anticlockwise", duration=5.0)
                set_face_state("moving", "SPINNING ANTICLOCKWISE")
                reply = motor_spoken or "Spinning anticlockwise for five seconds."
                conversation_history.append({"role": "assistant", "content": reply})
                trim_conversation_history()
                print("Neurolis:", reply)
                speak(reply, custom_state="moving", custom_status="SPINNING ANTICLOCKWISE")
                return False

        # C2. Check for Confusing Action Clarification from LLM
        if "are you asking me to move back" in raw_reply.lower() or "move back / spin" in raw_reply.lower() or "move back, spin" in raw_reply.lower():
            clarification = "Are you asking me to move back, spin, approach, follow, or use my camera?"
            conversation_history.append({"role": "assistant", "content": clarification})
            trim_conversation_history()
            set_face_state("confused", "CLARIFYING INTENT")
            print("Neurolis (Confused):", clarification)
            speak(clarification, custom_state="confused", custom_status="CLARIFYING INTENT")
            return False

        # D. Check for Expression Demonstration Action
        expr_match = re.search(r'<action\s+expression=["\']([a-z_]+)["\']>(.*?)(?:</action>|$)', raw_reply, re.DOTALL | re.IGNORECASE)
        if expr_match:
            expr_type = expr_match.group(1).lower()
            expr_spoken = clean_model_reply(expr_match.group(2).strip())
            if expr_type == "all":
                conversation_history.pop()
                demonstrate_all_expressions(user_text=text)
                return False
            if expr_type == "villain":
                reply = "That expression is not part of my public demonstration catalog."
                conversation_history.append({"role": "assistant", "content": reply})
                trim_conversation_history()
                print("Neurolis:", reply)
                speak(reply)
                return False
            else:
                was_recently_in_villain_mode = False
                if not expr_spoken or "happy robot" in expr_spoken.lower():
                    expr_spoken = get_non_repeating_phrase(EXPRESSION_CONFIRMATIONS.get(expr_type, [f"Here is my {expr_type} expression."]))
                reply = expr_spoken
                record_assistant_reply(reply)
                conversation_history.append({"role": "assistant", "content": reply})
                trim_conversation_history()
                user_asked_demo = any(w in text.lower() for w in ["expression", "face", "show me your", "demonstrate", "make a face", "look happy", "look sad", "smile"])
                status_text = f"EXPRESSION: {expr_type.upper()}" if user_asked_demo else None
                print("Neurolis:", reply)
                speak(reply, custom_state=expr_type, custom_status=status_text)
                return False

        # E. Standard Conversational Chat Reply
        # Extract facts if present
        facts_match = re.search(r"<facts>(.*?)</facts>", raw_reply, re.IGNORECASE)
        if facts_match:
            facts_content = facts_match.group(1).strip()
            for part in facts_content.split(","):
                if ":" in part:
                    k, v = part.split(":", 1)
                    session_facts[k.strip().lower()] = v.strip()
            if conversation_history:
                conversation_history[0] = {"role": "system", "content": get_system_prompt()}

        reply_clean = clean_model_reply(raw_reply)
        was_recently_in_villain_mode = False
        if not reply_clean:
            reply_clean = "I am right here with you. What would you like to explore next?"

        # Fix self-attribution hallucination (robot does not hold or wear visitor items)
        if "i'm holding" in reply_clean.lower() or "i am holding" in reply_clean.lower():
            reply_clean = re.sub(r"\b(i'm|i am)\s+holding\b", "you are holding", reply_clean, flags=re.IGNORECASE)
        if "i'm wearing" in reply_clean.lower() or "i am wearing" in reply_clean.lower():
            reply_clean = re.sub(r"\b(i'm|i am)\s+wearing\b", "you are wearing", reply_clean, flags=re.IGNORECASE)

        # Anti-Repetition and Degrading Prefix Glitch Buster
        if is_degraded_glitch(reply_clean) or is_repetitive_reply(reply_clean):
            reply_clean = heal_repetitive_or_glitched_reply(text, reply_clean)
        else:
            record_assistant_reply(reply_clean)

        # Motor approach fallback if model generated approach text without tag
        reply_lower = reply_clean.lower()
        if any(app in reply_lower for app in ["approaching you", "coming over to you", "closing the distance"]):
            if motor_ctrl is not None and not getattr(motor_ctrl, "is_moving", False):
                motor_ctrl.approach_user()
                print(f"[Motor] Approach maneuver executed via text intent trigger.")

        # Physical Motor Stop Safety Guard:
        # If the robot is in motion and user indicated stop OR model confirmed stopping
        if motor_ctrl is not None and getattr(motor_ctrl, "is_moving", False):
            user_wants_stop = (check_motor_fast_path(text) == "STOP")
            model_says_stop = any(st in reply_lower for st in ["stopping all movement", "holding position", "stopping now", "halting now"])
            if user_wants_stop or model_says_stop:
                motor_ctrl.stop_all()
                set_face_state("idle", "HALTED")
                print(f"[Safety] Physical Motor Stop Guard triggered (Motion halted).")

        if is_silence_required_reply(reply_clean):
            conversation_history.append(
                {"role": "assistant", "content": "[silent as requested]"}
            )
            trim_conversation_history()
            return False

        state = "moving" if any(app in reply_lower for app in ["approaching you", "coming over to you"]) else None
        status = "APPROACHING USER" if any(app in reply_lower for app in ["approaching you", "coming over to you"]) else None

        conversation_history.append({"role": "assistant", "content": reply_clean})
        trim_conversation_history()

        # Check if the AI model or user indicated transition to standby
        standby_reply_markers = [
            "heading back to standby", "heading into standby", "going into standby",
            "entering standby", "switching to standby", "returning to standby",
            "going back to standby", "head back to standby", "entering sleep mode",
            "switching to sleep", "standing down"
        ]
        is_standby_exit = any(marker in reply_clean.lower() for marker in standby_reply_markers)
        if not is_standby_exit:
            is_standby_exit = is_conversation_ender(text)

        print("Neurolis:", reply_clean)
        if is_standby_exit:
            speak(reply_clean, custom_state="idle", custom_status="STANDBY")
            set_face_state("idle", "STANDBY")
            return True
        else:
            speak(reply_clean, custom_state=state, custom_status=status)
            return False

    except GroqRateLimitExhausted:
        print("Neurolis:", RATE_LIMIT_ERROR_PHRASE)
        speak(RATE_LIMIT_ERROR_PHRASE)
        return False
    except Exception as e:
        err_msg = str(e).lower()
        if "429" in err_msg or "rate limit" in err_msg or "tokens per day" in err_msg or "tpd" in err_msg:
            rotate_groq_key(reason="Chat 429 quota exhausted", is_quota_exhausted=True)
            fallback_reply = RATE_LIMIT_ERROR_PHRASE
        elif "timeout" in err_msg or "timed out" in err_msg:
            fallback_reply = "I experienced a brief server timeout with my cloud neural link, but I am right here. What were you saying?"
        else:
            print("Chat error:", e)
            fallback_reply = "I'm having trouble connecting to my brain right now."
        print("Neurolis:", fallback_reply)
        speak(fallback_reply)
        return False

# handles the active voice conversation loop until the user goes quiet or says goodbye
def run_conversation_mode(speech_threshold: float):
    global is_in_active_conversation, last_user_activity_at
    is_in_active_conversation = True
    last_user_activity_at = time.monotonic()
    reset_standby_cooldown()
    if motor_ctrl is not None and (getattr(motor_ctrl, "is_roaming", False) or getattr(motor_ctrl, "nav_mode", None) == "ROAM"):
        try:
            motor_ctrl.stop_all()
        except Exception:
            pass

    try:
        standby_kill_event.clear()
        reset_session()
        print("Neurolis:", ACTIVATION_GREETING)
        if SPEAK_ACTIVATION_GREETING:
            speak(ACTIVATION_GREETING, custom_state="listening", custom_status="LISTENING...")
            time.sleep(POST_REPLY_COOLDOWN_SECONDS)
        else:
            set_face_state("listening", "LISTENING...")

        last_valid_input_at = time.monotonic()

        # keep audio stream warm across all conversation turns so there is zero driver re-init lag
        try:
            with suppress_c_stderr():
                warm_stream_ctx = get_audio_input_stream(callback=callback)
            with warm_stream_ctx as warm_stream:
                turn_idx = 0
                while True:
                    if standby_kill_event.is_set():
                        return

                    # Hot-reload mic configuration if modified by tune_mic.py
                    reload_mic_config_if_modified()
                    speech_threshold = max(CURRENT_SPEECH_THRESHOLD, MIN_SPEECH_RMS_THRESHOLD)

                    cfg = get_endpointer().cfg
                    if turn_idx == 0:
                        turn_timeout = float(cfg.get("first_turn_timeout_sec", 15.0))
                        holdoff_duration = float(cfg.get("startup_holdoff_sec", 0.45))
                    else:
                        turn_timeout = float(cfg.get("followup_timeout_sec", 10.0))
                        holdoff_duration = float(cfg.get("echo_holdoff_sec", 0.55))

                    # Follow Mode Inactivity Immunity: freeze timeout while actively following user
                    if motor_ctrl is not None and getattr(motor_ctrl, "is_following", False):
                        last_valid_input_at = time.monotonic()

                    remaining = turn_timeout - (time.monotonic() - last_valid_input_at)
                    if remaining <= 0:
                        if standby_kill_event.is_set():
                            return
                        timeout_msg = get_non_repeating_phrase(STANDBY_EXIT_PHRASES)
                        print("Neurolis (Standby):", timeout_msg)
                        speak(timeout_msg, custom_state="idle", custom_status="STANDBY")
                        set_face_state("idle", "STANDBY")
                        reset_session()
                        return

                    audio = listen_for_speech_segment(
                        speech_threshold,
                        remaining,
                        active_stream=warm_stream,
                        holdoff_sec=holdoff_duration,
                    )
                    if standby_kill_event.is_set():
                        return
                    if audio is None:
                        # Follow Mode Inactivity Immunity: keep following and listening on silent window
                        if motor_ctrl is not None and getattr(motor_ctrl, "is_following", False):
                            last_valid_input_at = time.monotonic()
                            continue
                        if standby_kill_event.is_set():
                            return
                        # If the conversational follow-up window still has time remaining, don't abort
                        # prematurely into standby on a momentary lull or rejected acoustic pop!
                        if time.monotonic() - last_valid_input_at < turn_timeout:
                            set_face_state("listening", "LISTENING...")
                            continue
                        timeout_msg = get_non_repeating_phrase(STANDBY_EXIT_PHRASES)
                        print("Neurolis (Standby):", timeout_msg)
                        speak(timeout_msg, custom_state="idle", custom_status="STANDBY")
                        set_face_state("idle", "STANDBY")
                        reset_session()
                        return

                    text = transcribe_audio(audio)
                    if standby_kill_event.is_set():
                        return
                    if not text or len(text) < MIN_TRANSCRIPTION_CHARS:
                        set_face_state("listening", "LISTENING...")
                        continue

                    turn_idx += 1

                    print("You:", text)
                    if face_ui is not None:
                        face_ui.set_subtitles("YOU", text)

                    should_end = handle_user_text(text)
                    if should_end or standby_kill_event.is_set():
                        reset_session()
                        set_face_state("idle", "STANDBY")
                        return

                    for _ in range(int(POST_REPLY_COOLDOWN_SECONDS / 0.1)):
                        if standby_kill_event.is_set():
                            return
                        time.sleep(0.1)
                    last_valid_input_at = time.monotonic()
                    last_user_activity_at = time.monotonic()
        except Exception as e:
            print("Audio stream session notice:", e)
            time.sleep(1.0)
    finally:
        is_in_active_conversation = False
        set_face_state("idle", "STANDBY")
        mark_standby_entered()


# ---------------- MAIN LOOP ----------------
# probes the operating system to see if a microphone is plugged in and working
def check_audio_devices():
    """Probes the system for an active audio input device."""
    if sys.platform.startswith("linux") and shutil.which("pw-record"):
        return True
    with suppress_c_stderr():
        try:
            sd.query_devices(kind='input')
            return True
        except Exception:
            return False

def run_latency_test():
    """Measures physical speaker-to-mic loopback latency via 100ms 1kHz beep.
    Calculates exact echo_holdoff_sec = (latency_ms / 1000.0) + 0.25 and updates mic_config.json.
    """
    print("\n=================================================================")
    print("      PROJECT NEUROLIS - ACOUSTIC LATENCY LOOPBACK TEST")
    print("=================================================================")
    sr = 16000
    beep_len = int(0.100 * sr)  # 100ms
    t = np.arange(beep_len) / float(sr)
    beep = (np.sin(2 * np.pi * 1000.0 * t) * 28000.0).astype(np.int16)

    tmp_wav = Path(tempfile.gettempdir()) / f"latency_beep_{int(time.time())}.wav"
    write_wav(tmp_wav, sr, beep)

    captured_chunks = []
    def _cap_cb(indata, frames, time_info, status):
        captured_chunks.append(indata.copy().reshape(-1))

    print("[*] Arming audio input capture...")
    with suppress_c_stderr():
        stream_ctx = get_audio_input_stream(callback=_cap_cb)
    with stream_ctx:
        time.sleep(0.20)
        captured_chunks.clear()
        print("[*] Emitting 100ms 1kHz diagnostic probe pulse on speaker...")
        played = play_with_system_player(tmp_wav, timeout=3.0)
        if not played:
            try:
                sd.play(beep, samplerate=sr)
                sd.wait()
            except Exception:
                pass
        time.sleep(1.2)

    try:
        tmp_wav.unlink(missing_ok=True)
    except Exception:
        pass

    if not captured_chunks:
        print("[!] Error: No audio captured during latency probe.")
        sys.exit(1)

    rec = np.concatenate(captured_chunks)
    rec_filt = frontend_bandpass_frame(rec, sample_rate=sr, low_hz=800.0, high_hz=1200.0)
    frame_sz = int(0.010 * sr)  # 10ms energy bins
    energies = [
        float(np.mean(rec_filt[k * frame_sz : (k + 1) * frame_sz].astype(np.float32) ** 2))
        for k in range(len(rec_filt) // frame_sz)
    ]
    if not energies:
        print("[!] Error: Insufficient audio captured.")
        sys.exit(1)

    peak_bin = int(np.argmax(energies))
    latency_sec = peak_bin * 0.010
    latency_ms = latency_sec * 1000.0
    recommended_holdoff = round(latency_sec + 0.25, 2)

    print(f"\n[+] Measured Speaker-to-Mic Latency: {latency_ms:.1f} ms")
    print(f"[+] Recommended Echo Holdoff: {recommended_holdoff:.2f} s")

    cfg = load_mic_config(MIC_CONFIG_FILE)
    cfg["echo_holdoff_sec"] = recommended_holdoff
    save_mic_config(cfg, MIC_CONFIG_FILE)
    print(f"[+] Saved echo_holdoff_sec = {recommended_holdoff:.2f} to {MIC_CONFIG_FILE}")
    print("=================================================================\n")
    sys.exit(0)

def run_acoustic_diagnostics():
    """Interactive 3-phase acoustic diagnostic test:
    Phase 1: 5s silence (measure noise floor p50, p90, crest factor)
    Phase 2: 6s normal speaking (measure speech p50, p90, SNR)
    Phase 3: 4s loud voice / hall noise (measure peak, dynamic range)
    """
    print("\n=================================================================")
    print("      PROJECT NEUROLIS - 3-PHASE ACOUSTIC DIAGNOSTICS")
    print("=================================================================")
    sr = 16000

    def _record_duration(sec: float, prompt: str):
        print(f"\n[*] {prompt}")
        for remaining in range(int(sec), 0, -1):
            sys.stdout.write(f"\r    Recording in progress: {remaining}s remaining... ")
            sys.stdout.flush()
            time.sleep(1.0)
        sys.stdout.write("\r    Recording finished! Analyzing...              \n")
        sys.stdout.flush()

    captured_chunks = []
    def _cap_cb(indata, frames, time_info, status):
        captured_chunks.append(indata.copy().reshape(-1))

    with suppress_c_stderr():
        stream_ctx = get_audio_input_stream(callback=_cap_cb)
    with stream_ctx:
        time.sleep(0.3)
        captured_chunks.clear()
        _record_duration(5.0, "PHASE 1/3: Please remain completely SILENT (mapping ambient noise floor)...")
        silence_audio = np.concatenate(captured_chunks) if captured_chunks else np.array([], dtype=np.int16)

        captured_chunks.clear()
        _record_duration(6.0, "PHASE 2/3: Please SPEAK NORMALLY at your typical exhibition distance (5 feet)...")
        speech_audio = np.concatenate(captured_chunks) if captured_chunks else np.array([], dtype=np.int16)

        captured_chunks.clear()
        _record_duration(4.0, "PHASE 3/3: Please speak LOUDLY or generate exhibition background noise...")
        loud_audio = np.concatenate(captured_chunks) if captured_chunks else np.array([], dtype=np.int16)

    def _compute_frame_rms(audio_arr):
        f_len = int(0.03 * sr)
        if len(audio_arr) < f_len:
            return [0.0]
        return [
            frontend_audio_rms(frontend_bandpass_frame(audio_arr[k * f_len : (k + 1) * f_len]))
            for k in range(len(audio_arr) // f_len)
        ]

    sil_rms = _compute_frame_rms(silence_audio)
    spk_rms = _compute_frame_rms(speech_audio)
    loud_rms = _compute_frame_rms(loud_audio)

    floor_p50 = float(np.percentile(sil_rms, 50))
    floor_p90 = float(np.percentile(sil_rms, 90))
    speech_p50 = float(np.percentile(spk_rms, 50))
    speech_p90 = float(np.percentile(spk_rms, 90))
    loud_peak = float(np.max(loud_rms)) if loud_rms else speech_p90 * 1.5

    snr_db = 20.0 * np.log10(max(speech_p90, 1.0) / max(floor_p50, 1.0))
    rec_onset_snr = round(min(12.0, max(4.0, snr_db * 0.45)), 1)
    rec_cont_snr = round(max(2.0, rec_onset_snr * 0.60), 1)
    rec_min_onset = round(max(180.0, min(800.0, floor_p50 * 1.8)), 1)
    rec_max_onset = round(max(rec_min_onset * 2.5, loud_peak * 0.9), 1)

    print("\n---------------- ACOUSTIC DIAGNOSTIC REPORT ----------------")
    print(f"  Ambient Floor (Median):     {floor_p50:.1f} RMS (90th percentile: {floor_p90:.1f} RMS)")
    print(f"  Speech Energy (Median):     {speech_p50:.1f} RMS (90th percentile: {speech_p90:.1f} RMS)")
    print(f"  Acoustic Signal-to-Noise:   {snr_db:.1f} dB")
    print(f"  Peak Acoustic Power:        {loud_peak:.1f} RMS")
    print("---------------- RECOMMENDED TUNING PARAMETERS -------------")
    print(f"  onset_snr_db:      {rec_onset_snr} dB")
    print(f"  continue_snr_db:   {rec_cont_snr} dB")
    print(f"  min_onset_rms:     {rec_min_onset} RMS")
    print(f"  max_onset_rms:     {rec_max_onset} RMS")
    print("------------------------------------------------------------")

    cfg = load_mic_config(MIC_CONFIG_FILE)
    cfg["onset_snr_db"] = rec_onset_snr
    cfg["continue_snr_db"] = rec_cont_snr
    cfg["min_onset_rms"] = rec_min_onset
    cfg["max_onset_rms"] = rec_max_onset
    cfg["ambient_p90_rms"] = round(floor_p90, 1)
    cfg["calibrated_start_rms"] = round(floor_p50 * (10.0 ** (rec_onset_snr / 20.0)), 1)
    cfg["calibrated_continue_rms"] = round(floor_p50 * (10.0 ** (rec_cont_snr / 20.0)), 1)
    save_mic_config(cfg, MIC_CONFIG_FILE)
    print(f"[+] Configuration written to {MIC_CONFIG_FILE}\n")
    sys.exit(0)

def run_audio_replay(wav_path_str: str):
    """Replays an existing audio file through Endpointer v2 to test state transitions offline."""
    print("\n=================================================================")
    print("      PROJECT NEUROLIS - AUDIO ENDPOINTER REPLAY TEST")
    print("=================================================================")
    wav_path = Path(wav_path_str)
    if not wav_path.exists():
        print(f"[!] Error: File not found: {wav_path}")
        sys.exit(1)

    import wave
    with wave.open(str(wav_path), "rb") as wf:
        sr = wf.getframerate()
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        frames_bytes = wf.readframes(wf.getnframes())

    if sampwidth != 2:
        print(f"[!] Error: Expected 16-bit PCM WAV, got sample width {sampwidth}")
        sys.exit(1)

    audio_data = np.frombuffer(frames_bytes, dtype=np.int16)
    if n_channels > 1:
        audio_data = audio_data.reshape(-1, n_channels)[:, 0]

    if sr != 16000:
        target_len = int(len(audio_data) * 16000 / sr)
        orig_x = np.linspace(0, 1, len(audio_data), endpoint=False)
        target_x = np.linspace(0, 1, target_len, endpoint=False)
        audio_data = np.interp(target_x, orig_x, audio_data).astype(np.int16)
        sr = 16000

    cfg = load_mic_config(MIC_CONFIG_FILE)
    ep = Endpointer(cfg=cfg, seed_floor=50.0)
    ep.begin_turn(holdoff_sec=0.0)

    chunk_sz = 480  # 30ms
    num_chunks = len(audio_data) // chunk_sz
    print(f"[*] Replaying {len(audio_data)/sr:.2f}s audio ({num_chunks} frames @ 30ms)...")

    onset_time = None
    end_time = None

    for k in range(num_chunks):
        chunk = audio_data[k * chunk_sz : (k + 1) * chunk_sz]
        t_sec = k * 0.03
        evt = ep.feed(chunk)
        if evt == "ONSET":
            onset_time = t_sec
            print(f"  -> [{t_sec:.2f}s] ONSET detected! (RMS={ep.live_rms:.1f}, Floor={ep.live_floor:.1f})")
        elif evt == "END":
            end_time = t_sec
            print(f"  -> [{t_sec:.2f}s] END detected! (Hangover={ep.live_silence_sec:.2f}s, Reason={ep.done_reason})")
            break

    if ep.state == Endpointer.STATE_RECORDING and not ep.result_info:
        ep._finalize(reason="end_of_file", is_manual=False)
    elif ep.state == Endpointer.STATE_WAITING and not ep.result_info:
        ep.result_info = {"accepted": False, "reason": "no_speech_onset_detected"}

    res_audio, info = ep.result()
    print("\n---------------- REPLAY EVALUATION RESULT ----------------")
    print(f"  Accepted:        {info.get('accepted')}")
    print(f"  Reason:          {info.get('reason')}")
    print(f"  Onset Time:      {f'{onset_time:.2f}s' if onset_time is not None else 'None'}")
    print(f"  End Time:        {f'{end_time:.2f}s' if end_time is not None else 'None'}")
    print(f"  Captured Dur:    {info.get('duration')}s")
    print(f"  Voiced Frames:   {info.get('voiced_frames')}")
    print(f"  P90 Voiced RMS:  {info.get('p90_rms')}")
    print(f"  Live Floor:      {info.get('floor_rms')}")
    print("----------------------------------------------------------\n")
    sys.exit(0)

# CLI Argument Handlers
REPLAY_FILE = None
for _idx, _arg in enumerate(sys.argv[1:], 1):
    if _arg.lower() in ("--replay", "-r") and _idx < len(sys.argv) - 1:
        REPLAY_FILE = sys.argv[_idx + 1]
        break

if REPLAY_FILE:
    run_audio_replay(REPLAY_FILE)

if any(arg.lower() in ("--latency-test", "-l", "latency-test") for arg in sys.argv[1:]):
    run_latency_test()

if any(arg.lower() in ("--diag", "-d", "diag", "--diagnostics") for arg in sys.argv[1:]):
    run_acoustic_diagnostics()

# Check for manual calibration command line flags
CALIBRATE_ONLY = any(arg.lower() in ("--calibrate", "-c", "calibrate") for arg in sys.argv[1:])
if CALIBRATE_ONLY:
    print("\n=================================================================")
    print("      PROJECT NEUROLIS - ROOM NOISE ACOUSTIC CALIBRATION")
    print("=================================================================")
    print("[*] Locking hardware capture gain to 60%...")
    set_hardware_gain(60)
    print("[*] Scanning ambient room acoustics (2.0s measurement window)...")
    thresh = calibrate_speech_threshold(duration_sec=2.0)
    print(f"\n[+] Room Baseline Mapped: {CURRENT_AMBIENT_RMS:.1f} RMS")
    print(f"[+] Speech Start Threshold: {thresh:.1f} RMS")
    print(f"[+] Continue Threshold: {CURRENT_CONTINUE_THRESHOLD:.1f} RMS")
    print(f"[+] Saved to {MIC_CONFIG_FILE}")
    print("=================================================================\n")
    sys.exit(0)

# Check for manual text mode command line flags
FORCE_TEXT_MODE = any(arg.lower() in ("--text", "-t", "--text-only", "text") for arg in sys.argv[1:])

if FORCE_TEXT_MODE:
    AUDIO_ENABLED = False
    print("\n[INFO] Text Input Mode enabled via command-line argument.")
    print("Booting Neurolis in ZERO-HARDWARE TEST MODE (Microphone disabled)...")
else:
    # Check hardware before we start
    AUDIO_ENABLED = check_audio_devices()
    if not AUDIO_ENABLED:
        print("\n[INFO] No audio microphone detected.")
        print("Booting Neurolis in ZERO-HARDWARE TEST MODE (Interactive CLI Text Input)...")
        print("You can chat with Neurolis and test all robotic behaviors right here in the terminal!")

# Initialize acoustic threshold from saved configuration or ambient baseline
cached_speech_threshold = None
if AUDIO_ENABLED:
    cfg = load_mic_config(MIC_CONFIG_FILE)
    if "calibrated_start_rms" in cfg and float(cfg["calibrated_start_rms"]) > 0:
        CURRENT_SPEECH_THRESHOLD = float(cfg["calibrated_start_rms"])
        CURRENT_CONTINUE_THRESHOLD = float(cfg.get("calibrated_continue_rms", CURRENT_SPEECH_THRESHOLD * 0.7))
        CURRENT_AMBIENT_RMS = float(cfg.get("ambient_p90_rms", 50.0))
        cached_speech_threshold = max(CURRENT_SPEECH_THRESHOLD, MIN_SPEECH_RMS_THRESHOLD)
        print(f"[Acoustic Baseline] Loaded saved tuning: Start={CURRENT_SPEECH_THRESHOLD:.1f} RMS, Continue={CURRENT_CONTINUE_THRESHOLD:.1f} RMS, Ambient={CURRENT_AMBIENT_RMS:.1f} RMS")
    else:
        try:
            cached_speech_threshold = calibrate_speech_threshold(duration_sec=1.2)
        except Exception as _e:
            print(f"[Acoustic Config] Boot calibration notice: {_e}")
            cached_speech_threshold = max(CURRENT_SPEECH_THRESHOLD, MIN_SPEECH_RMS_THRESHOLD)

# Initialize conversation history and session facts
reset_session()

# starts the background webcam reader thread if motors are offline
def start_camera_worker():
    # Camera capture is unified under motor_ctrl for 30 FPS HUD and face tracking.
    # Fallback worker is only started if motor_ctrl is not available.
    global camera_worker
    if motor_ctrl is None and cv2 is not None and camera_worker is None:
        print("Initializing standalone webcam thread...")
        camera_worker = CameraWorker()
        camera_worker.start()

# stops the background webcam thread when shutting down
def stop_camera_worker():
    global camera_worker
    if cv2 is not None and camera_worker is not None:
        print("Stopping camera background thread...")
        camera_worker.stop()
        camera_worker = None

# runs a complete system health check and prints a startup report
def run_preflight_diagnostics():
    """runs a clean, minimal diagnostic check across platform, simulation, ai, and 4wd hardware"""
    print("\n" + "=" * 65)
    print("      PROJECT NEUROLIS - PRE RUN COMPONENT CHECKLIST")
    print("=" * 65)

    # 1. host platform
    print(f"[*] Platform: {sys.platform} | Python {sys.version.split()[0]}")

    # 2. hardware-free simulation status
    hw_free = (motor_ctrl is not None and motor_ctrl.is_simulated) or not AUDIO_ENABLED
    if hw_free:
        print("[*] HARDWARE STATUS: NO HARDWARE DETECTED, SIMULATION MODE ACTIVE")
    else:
        print("[*] HARDWARE STATUS: PHYSICAL HARDWARE DETECTED & ACTIVE")

    # 3. groq cloud ai
    if client is not None:
        print(f"[+] Groq AI Client: CONNECTED ({len(groq_clients)} active key(s) in pool [1 to 14 supported], active: Key #{_active_client_idx + 1})")
    else:
        print("[!] Groq AI Client: OFFLINE (Missing or invalid GROQ_API_KEY in .env)")

    # 4. motor controller & 4wd chassis
    if motor_ctrl is not None:
        if motor_ctrl.is_simulated:
            print("[!] 4WD Motor Controller: SIMULATION MODE (Virtual Physics Active)")
        else:
            port = getattr(getattr(motor_ctrl, "ser", None), "port", "USB")
            print(f"[+] 4WD Motor Controller: ONLINE (Physical Arduino Mega on {port})")
    else:
        print("[-] Motor Controller: DISABLED")

    print("=" * 65 + "\n")


# Non-blocking console input reader
console_input_queue: queue.Queue = queue.Queue()

def _console_input_worker():
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                time.sleep(0.1)
                continue
            cleaned = line.strip()
            if not cleaned:
                if is_in_active_conversation:
                    finish_speech_event.set()
                console_input_queue.put("__ENTER__")
            else:
                console_input_queue.put(cleaned)
        except Exception:
            time.sleep(0.2)

threading.Thread(target=_console_input_worker, daemon=True).start()
 
# Wire touchscreen TALK TO NEUROLIS and STAND-BY buttons
if face_ui is not None:
    def _handle_screen_talk_click():
        global AUDIO_ENABLED, is_in_active_conversation, last_user_activity_at
        standby_kill_event.clear()
        reset_standby_cooldown()
        if motor_ctrl is not None:
            try:
                motor_ctrl.stop_all()
            except Exception:
                pass
        is_in_active_conversation = True
        last_user_activity_at = time.monotonic()
        if not AUDIO_ENABLED and check_audio_devices():
            AUDIO_ENABLED = True
        console_input_queue.put("__ENTER__")

    def _handle_screen_standby_click():
        """
        Touchscreen STAND-BY Button Kill Switch Callback:
        Instantly halts speech mid-sentence without errors, cancels thinking/Groq waiting,
        stops motors, resets session memory, and announces transition to standby.
        """
        global is_in_active_conversation, is_speaking
        print("\n[Kill Switch] Standby button pressed. Cancelling active tasks immediately...")
        standby_kill_event.set()

        # 1. Immediately halt physical/virtual motors
        if motor_ctrl is not None:
            try:
                motor_ctrl.stop_all()
            except Exception:
                pass

        # 2. Immediately cut off any playing audio mid-sentence (<1ms latency)
        stop_all_audio()
        is_speaking = False
        is_in_active_conversation = False

        # 3. Clear session facts and conversation history
        reset_session()

        # 4. Immediate visual feedback on Face UI
        if face_ui is not None:
            face_ui.set_state("idle", "STANDBY")
            face_ui.set_subtitles("NEUROLIS", STANDBY_KILL_MESSAGE)

        # 5. Play mandated vocal confirmation in dedicated thread exclusively without overlap
        def _announce_worker():
            time.sleep(0.06)  # allow any dying subprocesses to cleanly release audio sink
            stop_all_audio()   # ensure clean slate
            print(f"Neurolis (Standby): {STANDBY_KILL_MESSAGE}")
            speak(STANDBY_KILL_MESSAGE, custom_state="idle", custom_status="STANDBY", allow_during_standby=True)
            if face_ui is not None:
                face_ui.set_state("idle", "STANDBY")
            reset_session()
            mark_standby_entered()

        threading.Thread(target=_announce_worker, daemon=True).start()

    def _handle_screen_send_click():
        """
        Touchscreen Send Arrow Button Callback:
        Instantly halts listening, dispatches audio buffer immediately (0ms override)
        to Whisper transcription without waiting for silence.
        """
        finish_speech_event.set()

    face_ui.on_talk_click = _handle_screen_talk_click
    face_ui.on_standby_click = _handle_screen_standby_click
    face_ui.on_send_click = _handle_screen_send_click


# main entrypoint: runs either in voice mode with microphone or fallback text mode
if __name__ == "__main__":
    run_preflight_diagnostics()
    if client is None:
        print("[!] WARNING: Groq API key is not configured.")
        print("    Please add GROQ_API_KEY=your_key to your .env file to enable AI responses.\n")
    start_camera_worker()

    print("[Ready] Type a message or press Enter to speak:\n")
    mark_standby_entered()
    last_user_activity_at = time.monotonic()

    try:
        while True:
            try:
                # ---------------- INACTIVITY / SILENCE CUTOFF (TEXT MODE) ----------------
                # In text mode, monitor inactivity timeout. When idle >= CONVERSATION_TIMEOUT_SECONDS:
                # 1. Announce transition to standby
                # 2. Set Face UI to "idle" ("STANDBY")
                # 3. Clear active session (is_in_active_conversation = False)
                # 4. Initiate 10.0s standby cooldown timer via mark_standby_entered()
                # 5. After 10s uninterrupted silence in standby, autonomous roam engages.
                if is_in_active_conversation and not AUDIO_ENABLED:
                    if motor_ctrl is not None and getattr(motor_ctrl, "is_following", False):
                        last_user_activity_at = time.monotonic()
                    elif (time.monotonic() - last_user_activity_at) >= CONVERSATION_TIMEOUT_SECONDS:
                        if not standby_kill_event.is_set():
                            timeout_msg = get_non_repeating_phrase(STANDBY_EXIT_PHRASES)
                            print(f"\nNeurolis (Standby): {timeout_msg}")
                            speak(timeout_msg, custom_state="idle", custom_status="STANDBY")
                            set_face_state("idle", "STANDBY")
                            reset_session()
                            is_in_active_conversation = False
                            mark_standby_entered()

                user_input = None
                try:
                    user_input = console_input_queue.get(timeout=0.2)
                except queue.Empty:
                    user_input = None

                if user_input is None:
                    continue

                # Any user input immediately halts roaming motors (<5ms) and resets cooldown
                reset_standby_cooldown()
                if motor_ctrl is not None and (getattr(motor_ctrl, "is_roaming", False) or getattr(motor_ctrl, "nav_mode", None) == "ROAM"):
                    try:
                        motor_ctrl.stop_all()
                    except Exception:
                        pass

                if user_input == "__ENTER__":
                    standby_kill_event.clear()
                    if AUDIO_ENABLED:
                        if cached_speech_threshold is None:
                            cached_speech_threshold = calibrate_speech_threshold()
                        run_conversation_mode(cached_speech_threshold)
                    else:
                        is_in_active_conversation = True
                        last_user_activity_at = time.monotonic()
                        greet_msg = "I'm listening. Type your message below."
                        print(f"\nNeurolis: {greet_msg}")
                        speak(greet_msg, custom_state="happy", custom_status="READY // TALK TO ME")
                        set_face_state("happy", "READY // TALK TO ME")
                        if face_ui is not None:
                            face_ui.set_subtitles("NEUROLIS", greet_msg)
                    continue

                # Process text commands
                cmd_lower = user_input.lower().strip()
                if cmd_lower in ("exit", "quit", "q"):
                    print("\nExiting. See ya!")
                    break

                if cmd_lower in ("calibrate", "cal", "calibrate room", "scan room"):
                    print("\n[Acoustic Calibration] Scanning room background noise for 2 seconds...")
                    cached_speech_threshold = calibrate_speech_threshold(duration_sec=2.0)
                    print(f"[Acoustic Calibration] Complete! Baseline: {CURRENT_AMBIENT_RMS:.1f} RMS | Speech Threshold: {cached_speech_threshold:.1f} RMS\n")
                    continue

                if cmd_lower in ("v", "voice", "mic"):
                    if check_audio_devices():
                        AUDIO_ENABLED = True
                        print("[Mode] Switched to VOICE MODE.")
                    else:
                        print("[!] Cannot switch to Voice Mode: No working audio input device detected.")
                    continue

                if cmd_lower in ("t", "text"):
                    AUDIO_ENABLED = False
                    print("[Mode] Switched to TEXT INPUT MODE.")
                    continue

                if cmd_lower == "sim_roam":
                    if motor_ctrl is not None:
                        motor_ctrl.start_roaming()
                        print("[Simulation] Autonomous Roam started.")
                    continue

                if cmd_lower in ("sim_face", "face"):
                    if motor_ctrl is not None:
                        motor_ctrl.simulate_face_detected(True, cx=0.0, cy=0.0, ratio=0.25)
                        print("[Simulation] Virtual human face detected via YuNet simulation!")
                    continue

                if cmd_lower in ("sim_noface", "noface", "sim_face off"):
                    if motor_ctrl is not None:
                        motor_ctrl.simulate_face_detected(False)
                        print("[Simulation] Virtual human face cleared. Target lost.")
                    continue

                if cmd_lower in ("sim_villain", "villain"):
                    test_provocation = "Are you robots going to take over the world and make humans your slaves?"
                    print(f"You (Simulated Provocation): {test_provocation}")
                    if face_ui is not None:
                        face_ui.set_subtitles("YOU", test_provocation)
                    is_in_active_conversation = True
                    last_user_activity_at = time.monotonic()
                    handle_user_text(test_provocation)
                    set_face_state("happy", "READY // TALK TO ME")
                    continue

                if cmd_lower == "stop":
                    if motor_ctrl is not None:
                        motor_ctrl.stop_all()
                    set_face_state("idle", "HALTED")
                    is_in_active_conversation = False
                    reset_session()
                    mark_standby_entered()
                    continue

                # Standard text conversation turn
                print("You:", user_input)
                if face_ui is not None:
                    face_ui.set_subtitles("YOU", user_input)

                standby_kill_event.clear()
                is_in_active_conversation = True
                last_user_activity_at = time.monotonic()
                should_end = handle_user_text(user_input)
                if should_end or standby_kill_event.is_set():
                    reset_session()
                    set_face_state("idle", "STANDBY")
                    is_in_active_conversation = False
                    mark_standby_entered()
                else:
                    is_in_active_conversation = True
                    last_user_activity_at = time.monotonic()
                    set_face_state("happy", "READY // TALK TO ME")

            except KeyboardInterrupt:
                print("\nExiting. See ya!")
                break
            except Exception as e:
                print(f"[Main Loop Notice]: {e}")
                time.sleep(0.1)

    finally:
        stop_camera_worker()
        if motor_ctrl is not None:
            motor_ctrl.close()
        if face_ui is not None:
            face_ui.stop()


