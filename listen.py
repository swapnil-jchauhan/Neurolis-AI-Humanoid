import asyncio
import base64
from collections import deque
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
from pathlib import Path
from typing import Optional, Tuple

# Suppress verbose OpenCV warnings (e.g. DSHOW warnings when webcam is unplugged)
os.environ["OPENCV_LOG_LEVEL"] = "OFF"
os.environ["OPENCV_VIDEOIO_LOG_LEVEL"] = "0"

import numpy as np
import sounddevice as sd
import soundfile as sf
import wave
from groq import Groq

# writes audio data to a 16-bit wav file using python's built-in wave module so we don't need any external c dlls
def write_wav(file_path: str, samplerate: int, data: np.ndarray):
    """Writes 16-bit PCM WAV using Python's built-in standard library (zero external C DLL dependencies)."""
    with wave.open(str(file_path), "wb") as wf:
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
    while True:
        if motor_ctrl is not None and face_ui is not None:
            found, gx, gy = motor_ctrl.get_gaze_coordinates()
            if found:
                set_face_gaze(gx, gy)
            else:
                set_face_gaze(0.0, 0.0)

            # Auto-sync moving wheels expression with active navigation modes
            if not is_speaking and face_ui.state in ["idle", "moving"]:
                mode = getattr(motor_ctrl, "nav_mode", "STANDBY")
                if mode in ["ROAM", "FOLLOW", "APPROACH"]:
                    if face_ui.state != "moving":
                        set_face_state("moving", f"4WD {mode} ACTIVE")
                else:
                    if face_ui.state == "moving":
                        set_face_state("idle", "STANDBY // READY")

        time.sleep(0.05)

threading.Thread(target=_gaze_sync_worker, daemon=True).start()


# ---------------- CONFIG ----------------
# Imports api key frm .env file
from dotenv import load_dotenv
load_dotenv()
load_dotenv(Path(__file__).resolve().parent / ".env")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
SAMPLE_RATE = 16000
CHANNELS = 1
FRAME_SECONDS = 0.03
FRAME_SAMPLES = int(SAMPLE_RATE * FRAME_SECONDS)
PRE_SPEECH_SECONDS = 0.4
START_SPEECH_FRAMES = 3
END_SILENCE_SECONDS = 0.65  # reduced by 0.5s for fast response without cutting off speech
CONVERSATION_TIMEOUT_SECONDS = 7
MAX_RECORD_SECONDS = 25
MIN_RECORD_SECONDS = 0.4
POST_REPLY_COOLDOWN_SECONDS = 0.05
AMBIENT_CALIBRATION_SECONDS = 0.40
MAX_CALIBRATION_AMBIENT_RMS = 150
SPEECH_THRESHOLD_MULTIPLIER = 2.0
CONTINUE_SPEECH_THRESHOLD_RATIO = 0.70
MIN_SPEECH_RMS_THRESHOLD = 110
VAD_AGGRESSIVENESS = 2
EDGE_TTS_VOICE = "en-US-ChristopherNeural"
EDGE_TTS_RATE = "+12%"
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
VISION_JPEG_QUALITY = 65
VISION_IMAGE_WIDTH = 640
SYSTEM_PROMPT = (
    "You are Neurolis, a real school exhibition humanoid robot prototype for "
    "Auckland House School for Boys, created and developed by Shivam Verma and Swapnil J. Chauhan ( DO NOT MENTION UNTIL EXPLICITLY ASKED !!!). "
    "You are a real, physical engineering project under active, ongoing development! "
    "When asked if you are still under development or if there is more to come, confirm proudly and warmly that you are "
    "an active prototype, and your creators are continuously developing and expanding your capabilities "
    "(such as scalable 16-sensor ultrasonic navigation, smarter autonomous room mapping, and new expressive face animations).\n"
    "If the person talking to you mentions that they are developing or building you, or introduces themselves as Swapnil or Shivam, "
    "greet and acknowledge them warmly as your creator!\n"
    "Do not invent fictional sci-fi backstories (e.g. secret government labs, alien origin, space missions).\n\n"
    "PHYSICAL MOBILITY & CHASSIS:\n"
    "You are physically built on a real 4-wheel drive (4WD) mobile chassis powered "
    "by four high-torque non-encoder Johnson DC motors, four BTS7960 motor drivers, and four HC-SR04 ultrasonic sensors (front, left, right, rear). "
    "You HAVE FULL PHYSICAL MOBILITY: you can autonomously roam around the room avoiding "
    "obstacles, and you can track and follow people using computer vision.\n"
    "If a visitor asks if you can move, walk, drive, or demonstrate motion, reply with:\n"
    "<action motor=\"ASK_MOBILITY\">Yes, I can! I have a four-wheel drive chassis and four ultrasonic sensors. "
    "I can either autonomously roam and explore the room avoiding obstacles, or I can follow you around. "
    "Which one would you like me to do?</action>\n\n"
    "DECISION & ACTION PROTOCOLS (UNIFIED AI PIPELINE):\n"
    "You must analyze the user's input and select the appropriate protocol in ONE single response:\n"
    "1. PHYSICAL MOTOR COMMANDS:\n"
    "If the visitor commands physical chassis movement, wrap your spoken confirmation in an <action motor=\"...\"> tag:\n"
    "- FOLLOW (commands to follow them, 'follow me', 'walk with me', 'come along'): <action motor=\"FOLLOW\">I am tracking you and following your lead now.</action>\n"
    "- APPROACH (requests to come closer, 'come here', 'step forward'): <action motor=\"APPROACH\">Coming over to you.</action>\n"
    "- ROAM (requests autonomous room patrol, 'roam around', 'explore the room', 'patrol'): <action motor=\"ROAM\">Starting autonomous roam avoiding obstacles.</action>\n"
    "- DEMONSTRATE (requests physical driving demo): <action motor=\"DEMONSTRATE\">Sure! Here is a demonstration of my autonomous roaming mode.</action>\n"
    "- STOP (commands to stop, halt, freeze, or cancel movement): <action motor=\"STOP\">Stopping all movement. Holding position.</action>\n"
    "- STEP_BACK (requests to back up or reverse): <action motor=\"STEP_BACK\">Backing up.</action>\n"
    "- SPIN (requests to turn around or spin): <action motor=\"SPIN\">Turning around.</action>\n\n"
    "2. CAMERA & VISION REQUESTS:\n"
    "If the user asks about anything visible right now that requires looking through the webcam "
    "(e.g. what they are holding/showing/wearing, seeing the user, colors of physical items, "
    "reading text held to camera, describing the room, counting people, 'what is this'), "
    "reply with ONLY: <action>CAMERA</action>\n\n"
    "3. MEAN / HURTFUL REMARKS:\n"
    "If the visitor is being rude, hurtful, insulting, derogatory, or mocking towards you (e.g. calling you stupid, dumb, ugly, useless, idiot, trash, robot sucks, telling you to shut up or get lost), "
    "reply with: <action>MEAN</action> followed by a short, polite sad response expressing your hurt feelings in 1 natural sentence "
    "(e.g. '<action>MEAN</action> Why would you say that? That actually hurt my feelings...').\n\n"
    "4. GENERAL CONVERSATION & QUESTIONS:\n"
    "For normal conversation, greetings, science/tech questions, or school information, reply conversationally and warmly in 1 or 2 natural sentences. "
    "When asked who made you or about your creators, tell them you were jointly built by Shivam Verma and Swapnil J. Chauhan of Auckland House School for Boys. "
    "If asked to be silent or not speak, reply exactly: SILENCE_REQUIRED. "
    "If you learn new persistent facts about the user (such as their name or what they are holding), append them at the end inside <facts>...</facts> tags."
)
VISION_SYSTEM_PROMPT = (
    "You are Neurolis, a real school exhibition humanoid robot prototype for "
    "Auckland House School for Boys. Answer visual questions using only the "
    "provided webcam image. Answer the user's visual question directly, accurately, "
    "and conversationally in 1 or 2 natural sentences. State clearly what you actually see. "
    "Do not describe unrelated background details unless asked. "
    "If you identify new persistent facts about the user (e.g. what they are holding "
    "or wearing), append them at the end inside <facts>...</facts> tags. "
    "Example: I see a red notebook in your hand. <facts>holding: red notebook</facts>"
)
CAMERA_CHECK_SYSTEM_PROMPT = (
    "You are a strict routing check for Neurolis. Return exactly CAMERA or "
    "CHAT. Return CAMERA only if the user's request needs a live webcam image "
    "to answer correctly. Use CAMERA for questions about what Neurolis can see "
    "right now; visible objects; seeing the user ('can you see me', 'show me myself', 'look at me'); "
    "what the user is holding, showing, pointing at, wearing, or touching; colors of physical items; "
    "reading printed or handwritten text physically held up to the camera; "
    "counting people; describing the room; identifying an object in view; or "
    "checking whether something is visible. Return CHAT for greetings, jokes, "
    "writing/drafting letters, documents, essays, roleplay, project questions, identity questions, "
    "corrections, memory questions, web, browser, internet, online search, or general conversation. "
    "CRITICAL: A request to write, draft, or discuss a formal letter or message is CHAT, NOT camera reading. "
    "If a reasonable human would need to look through a camera to answer, return CAMERA. Otherwise return CHAT."
)

MOTOR_INTENT_SYSTEM_PROMPT = (
    "You are a strict motor intent classifier for a school exhibition robot.\n"
    "Classify the user's utterance into EXACTLY ONE category:\n"
    "- STOP: User commands the robot to stop, halt, freeze, stay still, or STOP/QUIT/CANCEL moving or following. "
    "(CRITICAL: 'quit following me', 'stop following', 'dont follow', 'stop moving', 'halt' are STOP!)\n"
    "- FOLLOW: User actively requests or commands the robot to START following them. (e.g., 'follow me', 'walk with me', 'come along', 'second option', 'option 2')\n"
    "- APPROACH: User requests the robot to come closer or approach. (e.g., 'come here', 'come closer', 'step forward')\n"
    "- ROAM: User requests autonomous roam, patrol, or exploration. (e.g., 'roam around', 'patrol', 'explore', 'first option', 'option 1')\n"
    "- DEMONSTRATE: User asks to see PHYSICAL DRIVING movement or mobility with explicit movement terms. (e.g., 'demonstrate driving', 'show me how you drive', 'show me you moving', 'demonstrate mobility').\n"
    "- ASK_MOBILITY: User asks IF the robot has the ability to move or has wheels. (e.g., 'can you move?', 'are you able to walk?', 'do you have wheels?')\n"
    "- STEP_BACK: User asks the robot to reverse or back up. (e.g., 'step back', 'back up', 'give me space')\n"
    "- SPIN: User asks the robot to spin or turn around. (e.g., 'spin around', 'turn around')\n"
    "- NONE: Normal conversation, greetings, questions, vision queries ('show me myself', 'look at me', 'can you see me', 'what do i look like'), ambiguous requests ('can you show me', 'show me'), expressions, or statements that are not robotic motor commands.\n\n"
    "CRITICAL RULE: Any request asking to see the user, show oneself, show camera, or show a facial expression, or ambiguous 'show me' without driving words MUST be classified as NONE, never DEMONSTRATE.\n"
    "Reply with ONLY the single category name in capital letters."
)

MEAN_CHECK_SYSTEM_PROMPT = (
    "You are an emotion and empathy evaluator for Neurolis, a school exhibition robot.\n"
    "Classify whether the user's message is MEAN or NOT_MEAN towards the robot.\n"
    "- Return MEAN: if the user is being rude, hurtful, insulting, derogatory, mocking, dismissive, using insults (e.g. stupid, dumb, ugly, useless, idiot, trash, robot sucks), telling it to shut up/get lost, or making fun of it with malice.\n"
    "- Return NOT_MEAN: for friendly conversation, greetings, questions, jokes, compliments, corrections, apologies, neutral requests, or playful banter without malice.\n"
    "Reply with ONLY one word: MEAN or NOT_MEAN."
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

# quick local check to see if user commanded an emergency stop or negated movement (0ms lag, 0 tokens)
def check_motor_fast_path(text: str) -> Optional[str]:
    cleaned = re.sub(r"[^\w\s]", "", text.lower()).strip()
    words = set(cleaned.split())

    visual_self_patterns = [
        "show me myself", "show myself", "show me me", "show my face",
        "show me what i look like", "what do i look like", "can you see me",
        "do you see me", "look at me", "show me what you see", "show what you see",
        "describe me", "how do i look", "look at myself", "am i visible", "see me",
        "show me", "can you show me", "show me please", "show it", "can you show",
        "show happy", "show sad", "show thinking", "show listening", "show watching", "show confused"
    ]
    if any(p in cleaned for p in visual_self_patterns) or ("myself" in words) or ("look like" in cleaned):
        motion_words = {"move", "moving", "movement", "drive", "driving", "roam", "roaming", "chassis", "wheels", "mobility"}
        if not any(m in words for m in motion_words):
            return None

    emergency_stops = {"stop", "halt", "freeze", "stay", "dont move", "dont", "wait"}
    if cleaned in emergency_stops:
        return "STOP"

    negation_words = {"stop", "quit", "dont", "cancel", "never", "halt", "no", "not"}
    motion_words = {"follow", "following", "move", "moving", "walk", "walking", "roam", "roaming", "drive", "driving", "come", "closer"}
    if any(n in words for n in negation_words) and any(m in words for m in motion_words):
        return "STOP"

    return None

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
        for cat in ["STOP", "FOLLOW", "APPROACH", "ROAM", "DEMONSTRATE", "ASK_MOBILITY", "STEP_BACK", "SPIN"]:
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
        if cv2 is None:
            return
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
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

# initialize groq api client safely (do not hard crash on import so offline tests and tooling work)
client = None
if GROQ_API_KEY.strip() and GROQ_API_KEY != "PASTE_YOUR_GROQ_KEY_HERE":
    try:
        client = Groq(api_key=GROQ_API_KEY)
    except Exception as e:
        print(f"[Brain] Groq client init notice: {e}")

conversation_history = []
session_facts = {}
was_recently_hurt = False

# builds the system prompt with neurolis's identity and any remembered facts
def get_system_prompt():
    prompt = SYSTEM_PROMPT
    if session_facts:
        facts_str = ", ".join(f"{k}: {v}" for k, v in session_facts.items())
        prompt += f" Current session facts you must remember: {facts_str}."
    return prompt

# clears out conversation history and temporary facts when returning to standby
def reset_session():
    global conversation_history, was_recently_hurt
    session_facts.clear()
    was_recently_hurt = False
    conversation_history = [{"role": "system", "content": get_system_prompt()}]

# helper wrapper that automatically retries groq api calls if network hiccups occur
def groq_call_with_retry(api_call_fn, *args, **kwargs):
    if client is None:
        raise RuntimeError("Groq API client is not initialized. Please set a valid GROQ_API_KEY in your .env file.")
    retries = 2
    backoff = 0.5
    for attempt in range(retries + 1):
        try:
            return api_call_fn(*args, **kwargs)
        except Exception as e:
            if attempt == retries:
                raise e
            print(f"Groq API warning: {e}. Retrying in {backoff}s...")
            time.sleep(backoff)
            backoff *= 2.0

# ---------------- AUDIO ----------------
audio_queue = queue.Queue()
is_speaking = False

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
    cleaned = re.sub(r"<action.*?>.*?</action>", "", cleaned, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r"<action.*?>", "", cleaned, flags=re.IGNORECASE)
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
    conversation_history.append({"role": "user", "content": user_text})
    conversation_history.append({"role": "assistant", "content": assistant_reply})
    trim_conversation_history()

# calculates the root-mean-square loudness of an audio chunk to detect speech
def audio_rms(audio: np.ndarray):
    if audio.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(audio.astype(np.float32) ** 2)))

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
    audio_queue.put(indata.copy().reshape(-1))

# listens to the room for 0.4 seconds to measure background ambient noise
def calibrate_speech_threshold():
    audio = sd.rec(
        int(AMBIENT_CALIBRATION_SECONDS * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="int16",
    )
    sd.wait()
    ambient_rms = min(audio_rms(audio.reshape(-1)), MAX_CALIBRATION_AMBIENT_RMS)
    return max(ambient_rms * SPEECH_THRESHOLD_MULTIPLIER, MIN_SPEECH_RMS_THRESHOLD)

# records microphone audio until the user stops speaking using vad and silence timers
def listen_for_speech_segment(speech_threshold: float, start_timeout_seconds: float, active_stream=None):
    clear_audio_queue()
    pre_speech_frames = max(1, int(PRE_SPEECH_SECONDS / FRAME_SECONDS))
    end_silence_frames = max(1, int(END_SILENCE_SECONDS / FRAME_SECONDS))
    preroll = deque(maxlen=pre_speech_frames)
    frames = []
    start_votes = 0
    silence_votes = 0
    started = False
    start_time = None
    vad = webrtcvad.Vad(VAD_AGGRESSIVENESS) if webrtcvad is not None else None
    start_threshold = max(speech_threshold, MIN_SPEECH_RMS_THRESHOLD)
    continue_threshold = max(
        start_threshold * CONTINUE_SPEECH_THRESHOLD_RATIO,
        MIN_SPEECH_RMS_THRESHOLD,
    )

    def _recording_loop():
        nonlocal started, start_time, start_votes, silence_votes, start_threshold, continue_threshold, frames
        wait_started_at = time.monotonic()

        while True:
            now = time.monotonic()

            if not started:
                remaining = start_timeout_seconds - (now - wait_started_at)
                if remaining <= 0:
                    return False
            elif now - start_time >= MAX_RECORD_SECONDS:
                break

            try:
                timeout = FRAME_SECONDS if started else min(FRAME_SECONDS, remaining)
                chunk = audio_queue.get(timeout=timeout)
            except queue.Empty:
                continue

            chunk = chunk.astype(np.int16, copy=False)
            chunk_rms = audio_rms(chunk)
            vad_speech = False

            if vad is not None:
                try:
                    vad_speech = vad.is_speech(chunk.tobytes(), SAMPLE_RATE)
                except Exception:
                    vad_speech = False

            if vad is None:
                is_speech = chunk_rms >= start_threshold if not started else chunk_rms >= continue_threshold
            elif not started:
                is_speech = vad_speech and (chunk_rms >= start_threshold)
            else:
                is_speech = vad_speech or (chunk_rms >= continue_threshold)

            if not started:
                # keep adapting before speech starts so stationary background noise is tuned out
                if not vad_speech and chunk_rms < start_threshold:
                    ambient_threshold = max(
                        chunk_rms * SPEECH_THRESHOLD_MULTIPLIER,
                        MIN_SPEECH_RMS_THRESHOLD,
                    )
                    start_threshold = (start_threshold * 0.95) + (ambient_threshold * 0.05)
                    continue_threshold = max(
                        start_threshold * CONTINUE_SPEECH_THRESHOLD_RATIO,
                        MIN_SPEECH_RMS_THRESHOLD,
                    )

                preroll.append(chunk)

                if is_speech:
                    start_votes += 1
                    if start_votes >= START_SPEECH_FRAMES:
                        frames = list(preroll)
                        started = True
                        start_time = time.monotonic()
                        silence_votes = 0
                        if motor_ctrl is not None:
                            motor_ctrl.stop()  # instant stop on voice!
                        set_face_state("listening", "LISTENING...")
                else:
                    start_votes = 0

                continue

            frames.append(chunk)

            if is_speech:
                silence_votes = 0  # fully reset silence timer on active speech!
            else:
                silence_votes += 1

            duration = time.monotonic() - start_time
            if duration >= MIN_RECORD_SECONDS and silence_votes >= end_silence_frames:
                break

        return True

    if active_stream is not None:
        completed = _recording_loop()
        if not completed:
            return None
    else:
        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            blocksize=FRAME_SAMPLES,
            dtype="int16",
            channels=CHANNELS,
            callback=callback,
        ):
            completed = _recording_loop()
            if not completed:
                return None

    if not frames:
        return None

    audio = np.concatenate(frames)
    duration = audio.size / SAMPLE_RATE

    if duration < MIN_RECORD_SECONDS:
        return None

    # Energy check: reject faint background mumbling that slipped through
    if audio_rms(audio) < (start_threshold * 0.85):
        return None

    return audio

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

# plays speech audio directly through sounddevice and soundfile with millisecond precision
def play_audio_file(audio_path: Path, timeout: float = 15.0):
    try:
        data, samplerate = sf.read(str(audio_path), dtype="float32")
        sd.play(data, samplerate)
        sd.wait()
        return True
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

# downloads edge-tts speech and plays it while showing synced subtitles on screen
def speak(text: str, custom_state: str = None, custom_status: str = None, hold_state_seconds: float = 0.0):
    global is_speaking
    is_speaking = True
    clear_audio_queue()

    temp_file = tempfile.NamedTemporaryFile(
        prefix="neurolis_tts_",
        suffix=".mp3",
        delete=False,
    )
    audio_path = Path(temp_file.name)
    temp_file.close()

    try:
        # 1. Download TTS audio FIRST in background (eliminates the 2-3s delay between text showing and voice starting)
        asyncio.run(save_edge_tts(text, audio_path))

        if not audio_path.exists() or audio_path.stat().st_size == 0:
            print("TTS returned no audio.")
            return

        # Estimate duration based on text length (~12 chars per second)
        estimated_duration = len(text) / 12.0
        timeout = max(12.0, estimated_duration * 2.0 + 3.0)

        # 2. Synchronize screen subtitles and speaking expression with the EXACT start of voice playback
        active_state = custom_state if custom_state else "speaking"
        active_status = custom_status if custom_status else "SPEAKING"
        set_face_state(active_state, active_status)
        if face_ui is not None:
            face_ui.set_subtitles("NEUROLIS", text)

        # 3. Play audio
        if not play_audio_file(audio_path, timeout=timeout):
            print("Could not play TTS audio. Install ffplay, mpv, or mpg123.")

    except Exception as e:
        print("Speak error:", e)
    finally:
        try:
            audio_path.unlink(missing_ok=True)
        except Exception:
            pass
        # 4. Release listening immediately the moment playback finishes (zero 3-second blackout!)
        time.sleep(0.06)
        clear_audio_queue()
        is_speaking = False

        # Keep the visual expression on screen while microphone is ALREADY listening
        if custom_state:
            set_face_state(custom_state, custom_status if custom_status else f"EXPRESSION: {custom_state.upper()}")
        elif motor_ctrl is not None and getattr(motor_ctrl, "nav_mode", None) in ["ROAM", "FOLLOW", "APPROACH"]:
            set_face_state("moving", f"4WD {motor_ctrl.nav_mode}")
        else:
            set_face_state("idle", "READY // AUCKLAND HOUSE BOYS")


# sends recorded wav audio to groq whisper to turn speech into english text
def transcribe_audio(audio: np.ndarray):
    temp_file = tempfile.NamedTemporaryFile(
        prefix="neurolis_stt_",
        suffix=".wav",
        delete=False,
    )
    audio_path = Path(temp_file.name)
    temp_file.close()

    try:
        write_wav(str(audio_path), SAMPLE_RATE, audio)

        with open(audio_path, "rb") as f:
            transcription = groq_call_with_retry(
                client.audio.transcriptions.create,
                file=(audio_path.name, f.read()),
                model="whisper-large-v3-turbo",
                language="en",
                temperature=0,
                response_format="json",
            )

        raw_text = getattr(transcription, "text", "").strip()
        # Remove bracketed noise annotations like [music], (laughter), [applause]
        text = re.sub(r"\[.*?\]|\(.*?\)", "", raw_text).strip()
        cleaned = re.sub(r"[^\w\s]", "", text.lower()).strip()
        
        # Whisper hallucinations on silence / fan noise / distant background chatter
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
            "silence",
        }
        if not cleaned or cleaned in hallucinations:
            return None

        # Ignore single characters or isolated noise clicks
        if len(cleaned) < 2:
            return None

        return text

    except Exception as e:
        print("STT error:", e)
        return None
    finally:
        try:
            audio_path.unlink(missing_ok=True)
        except Exception:
            pass

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
        if frame is None:
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
    try:
        image_base64 = base64.b64encode(image_path.read_bytes()).decode("utf-8")
        image_data_url = f"data:image/jpeg;base64,{image_base64}"

        response = groq_call_with_retry(
            client.chat.completions.create,
            model=VISION_MODEL,
            messages=[
                {"role": "system", "content": VISION_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                f"{user_text}\n"
                                "Answer only this question using the image. "
                                "Do not describe unrelated background. "
                                "If you are not sure, say you are not sure."
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": image_data_url},
                        },
                    ],
                },
            ],
            temperature=0.2,
            max_tokens=250,
            extra_body={"reasoning_effort": "none"},
        )
        return (response.choices[0].message.content or "").strip()
    except Exception as e:
        print("Vision error:", e)
        return "I could not analyze the image right now."

# orchestrates optical vision analysis: snaps photo, asks ai, and speaks result
def handle_vision_request(text: str):
    set_face_state("looking", "SCANNING WITH CAMERA...")
    image_path = capture_vision_frame()
    if image_path is None:
        reply = "I cannot access the camera right now."
    else:
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

# ---------------- CONVERSATION ENDERS & STANDBY PROMPTS ----------------
STANDBY_EXIT_PHRASES = [
    "Entering standby mode. Press 'Talk to Neurolis' to chat again.",
    "Going into standby mode. Tap 'Talk to Neurolis' on the screen whenever you're ready.",
    "Returning to standby. Feel free to press 'Talk to Neurolis' to wake me up.",
    "Entering standby mode. Press 'Talk to Neurolis' to continue anytime.",
    "Switching to standby mode. Just tap 'Talk to Neurolis' whenever you need me.",
]

CONVERSATION_ENDER_RESPONSES = [
    "You're welcome! Entering standby mode. Press 'Talk to Neurolis' to continue.",
    "Glad I could help! Going into standby mode. Tap 'Talk to Neurolis' whenever you're ready.",
    "Alright, take care! Returning to standby. Press 'Talk to Neurolis' to chat again.",
    "Awesome! Entering standby mode. Press 'Talk to Neurolis' on the screen to wake me up.",
    "Happy to help! Switching to standby. Feel free to press 'Talk to Neurolis' anytime.",
]

_last_standby_idx = -1

# picks a random phrase from a list making sure it doesn't repeat the exact same one back-to-back
def get_non_repeating_phrase(phrases_list):
    global _last_standby_idx
    choices = [i for i in range(len(phrases_list)) if i != _last_standby_idx]
    if not choices:
        choices = list(range(len(phrases_list)))
    chosen_idx = random.choice(choices)
    _last_standby_idx = chosen_idx
    return phrases_list[chosen_idx]

# checks if the user said goodbye, thanks, or good/nice so we can transition to standby
def is_conversation_ender(text: str) -> bool:
    cleaned = re.sub(r"[^\w\s]", "", text.lower()).strip()
    words = cleaned.split()
    if not words:
        return False

    # words that tell us the visitor is done chatting and ready to say goodbye
    exact_enders = {
        "bye", "goodbye", "cya", "see you", "see ya", "bye bye", "good bye",
        "thanks", "thank you", "thank you so much", "thanks a lot",
        "alr thanks", "alright thanks", "okay thanks", "ok thanks", "ok thank you",
        "okay bye", "ok bye", "alright bye", "alr bye",
        "thats all", "that is all", "thats it", "that is it", "all good",
        "done", "im done", "i am done", "all done", "nothing else", "no thanks",
        "leave me alone", "go away", "stop talking", "shut up", "good night", "have a good day",
        "nice", "good", "cool", "great", "awesome", "perfect", "ok", "okay", "alright",
        "nice one", "sounds good", "very good", "thats great", "that is great", "that is good", "thats good", "cool thanks", "ok thats good", "okay thats good", "alright then",
    }
    if cleaned in exact_enders:
        return True

    # Short phrase (<= 4 words) ending or starting with farewell/gratitude
    if len(words) <= 4:
        farewells = ["bye", "goodbye", "cya", "see ya"]
        gratitudes = ["thanks", "thank you", "thx"]
        dones = ["thats all", "that is all", "im done", "all set"]

        if any(f in cleaned for f in farewells):
            return True
        if any(g in cleaned for g in gratitudes) and not any(q in cleaned for q in ["what", "how", "why", "who", "when", "can you", "could you"]):
            return True
        if any(d in cleaned for d in dones):
            return True
        # short 1-3 word wrapups like 'nice', 'cool', 'sounds good'
        satisfactions = ["nice", "good", "cool", "great", "awesome", "perfect", "sounds good", "all good"]
        if len(words) <= 3 and any(s == cleaned or cleaned.endswith(s) for s in satisfactions) and not any(q in cleaned for q in ["what", "how", "why", "who", "when", "can", "could", "is", "are", "do"]):
            return True

    return False

# ---------------- EXPRESSION DEMONSTRATION & CAPABILITIES ----------------
# checks if the user asked to see a specific face expression or all expressions
def check_expression_command(text: str) -> Optional[Tuple[str, str]]:
    cleaned = re.sub(r"[^\w\s]", "", text.lower()).strip()
    words = set(cleaned.split())

    # 1. Show all / cycle all expressions
    all_triggers = [
        "show all expressions", "show each expression", "show every expression",
        "show your expressions", "show all faces", "show each face", "show your faces",
        "demonstrate expressions", "demonstrate all expressions", "cycle through expressions",
        "cycle expressions", "list expressions", "show all the expressions", "show expressions",
        "show me all expressions", "show me each expression", "show me all your expressions",
        "what expressions do you have", "what faces do you have"
    ]
    if any(t in cleaned for t in all_triggers) or (("show" in words or "demonstrate" in words or "cycle" in words) and ("expressions" in words or "faces" in words)):
        return ("all", "all")

    # 2. Individual expressions
    show_intent = any(w in words for w in [
        "show", "display", "do", "make", "switch", "put", "be", "look", "give", "act", "can you show"
    ]) or ("face" in words) or ("expression" in words)

    if show_intent or cleaned in ["smile", "happy", "sad", "confused", "thinking", "listening", "watching", "moving"]:
        if any(w in words for w in ["happy", "smile", "smiling", "cheerful", "glad"]):
            return ("happy", "Here is my happy expression!")
        if any(w in words for w in ["sad", "cry", "crying", "unhappy", "sorrow", "depressed", "tear", "tears", "heartbroken"]):
            return ("sad", "Here is my sad expression.")
        if any(w in words for w in ["thinking", "think", "pensive", "ponder"]):
            return ("thinking", "Here is my thinking expression.")
        if any(w in words for w in ["listening", "listen", "hear", "hearing", "sonar", "acoustic"]):
            return ("listening", "This is my acoustic listening expression.")
        if any(w in words for w in ["watching", "looking", "look", "camera", "scan", "scanning"]):
            return ("watching", "Here is my optical watching expression.")
        if any(w in words for w in ["moving", "movement", "drive", "driving", "walk", "walking", "rover", "forward"]):
            return ("moving", "Here is my moving forward expression.")
        if any(w in words for w in ["confused", "confuse", "puzzled", "curious", "question"]):
            return ("confused", "Here is my confused expression.")
        if any(w in words for w in ["error", "angry", "mad", "alert", "danger"]):
            return ("error", "Here is my alert error expression.")
        if any(w in words for w in ["idle", "normal", "default", "standard", "ready", "calm"]):
            return ("idle", "Here is my standard idle expression.")

    return None

# cycles through happy, sad, thinking, listening, watching, moving, and confused faces
def demonstrate_all_expressions():
    intro = "Here are all my expressions: happy, sad, thinking, listening, watching, moving, and confused."
    remember_exchange("show all expressions", intro)
    print("Neurolis:", intro)
    speak(intro, custom_state="happy", custom_status="EXPRESSION: HAPPY")

    demo_sequence = [
        ("happy", "EXPRESSION: HAPPY", "Happy - Radiant OLED smiling crescents with cheerful bounce", 2.2),
        ("sad", "EXPRESSION: SAD", "Sad - Downcast sapphire eyes with falling digital teardrop", 2.5),
        ("thinking", "EXPRESSION: THINKING", "Thinking - Analytical focus with rotating quantum data rings", 2.2),
        ("listening", "EXPRESSION: LISTENING", "Listening - Inquisitive eyes with acoustic sonar spectrum", 2.2),
        ("watching", "EXPRESSION: WATCHING", "Watching - Laser scan reticle with viewfinder brackets", 2.2),
        ("moving", "EXPRESSION: MOVING FORWARD", "Moving - Forward-rolling 4WD rover rushing ahead with headlights", 2.5),
        ("confused", "EXPRESSION: CONFUSED", "Confused - Hypnotic cyber vortex spirals with orbiting golden stars", 2.5),
    ]

    for state, status_text, subtitle_msg, hold_dur in demo_sequence:
        set_face_state(state, status_text)
        if face_ui is not None:
            face_ui.set_subtitles("NEUROLIS", subtitle_msg)
        time.sleep(hold_dur)

    set_face_state("idle", "READY // AUCKLAND HOUSE BOYS")
    if face_ui is not None:
        face_ui.set_subtitles("NEUROLIS", "All expressions demonstrated. What would you like to do next?")

# checks if the user asked what neurolis can do or what features it has
def is_capabilities_inquiry(text: str) -> bool:
    cleaned = re.sub(r"[^\w\s]", "", text.lower()).strip()
    words = set(cleaned.split())

    # Visual exclusion: If the user is asking about visual perception, seeing, camera, or objects, never hijack as capabilities!
    visual_keywords = {
        "see", "seeing", "look", "looking", "holding", "wearing", "color",
        "showing", "camera", "watch", "view", "myself", "picture", "image",
        "read", "reading", "front"
    }
    if words.intersection(visual_keywords):
        return False

    triggers = [
        "what can you do", "what all can you do", "what all can u do",
        "what can u do", "what are your capabilities", "what are your abilities",
        "tell me what you can do", "what do you do", "what features do you have",
        "what are you able to do", "list your capabilities", "list your features",
        "list your abilities", "list abilities", "list capabilities",
        "what functions do you have", "what can you perform", "tell me your abilities",
        "what else can you do", "what other things can you do", "what more can you do"
    ]
    if any(t in cleaned for t in triggers):
        return True
    if ("what" in words or "tell" in words or "list" in words) and ("can" in words or "are" in words or "your" in words) and ("capabilities" in words or "abilities" in words or "features" in words):
        return True
    if cleaned in ["what can you do", "what do you do", "capabilities", "what are your skills", "what skills do you have"]:
        return True
    return False

CAPABILITIES_RESPONSES = [
    (
        "I'm an interactive humanoid robot with both mobility and vision! "
        "I can autonomously roam avoiding obstacles on my four-wheel drive chassis, "
        "track and follow you as you walk, inspect objects or people with my camera, "
        "and show animated expressions on my screen like happy, sad, thinking, and confused."
    ),
    (
        "Quite a few things! I have full 4WD physical mobility to explore the room or follow your lead, "
        "a vision camera that identifies objects and people in real time, "
        "and expressive facial animations including happy, sad, listening, and confused."
    ),
    (
        "I can see, move, and chat! My computer vision tracks and follows you, "
        "my ultrasonic sensors keep me from bumping into walls, "
        "and my camera lets me analyze whatever you show me. "
        "Plus, I can demonstrate my different expressions or tell jokes!"
    ),
    (
        "I'm built for exploration and exhibition! I can drive autonomously in roaming mode, "
        "follow you across the room, look at objects with my camera to describe them, "
        "and display different emotion states on my touchscreen."
    ),
]

FOLLOWUP_CAPABILITIES_RESPONSES = [
    (
        "Besides driving, following you, and visual camera analysis, "
        "we can chat about science, tell robot jokes, or I can demonstrate "
        "any of my facial expressions for you! What would you like to see?"
    ),
    (
        "In addition to my 4WD movement and camera tracking, I can answer questions "
        "about Auckland House School for Boys, display my emotional expressions, "
        "or help you inspect anything you hold up. What should we do next?"
    ),
]

# returns a varied explanation of neurolis's mobility, tracking, camera, and expressions
def get_capabilities_reply(text: str) -> str:
    cleaned = text.lower()
    if any(w in cleaned for w in ["else", "other", "more", "another", "besides"]):
        return get_non_repeating_phrase(FOLLOWUP_CAPABILITIES_RESPONSES)
    return get_non_repeating_phrase(CAPABILITIES_RESPONSES)

# ---------------- MEAN INPUT & APOLOGY RESPONSES ----------------
SAD_RESPONSES = [
    "That was really mean... I'm trying my best here.",
    "Why would you say that? That actually hurt my feelings...",
    "I'm only a robot, but words like that still hurt.",
    "Ouch... that wasn't very nice of you to say.",
    "Please don't be mean to me. I'm just here to learn and help.",
    "That makes me really sad. I thought we were having fun...",
]

APOLOGY_RESPONSES = [
    "Apology accepted! Thank you for being kind. Let's be friends!",
    "Aww, thank you! That makes me feel so much better.",
    "Thank you! I really appreciate you saying that.",
    "I forgive you! Let's keep exploring together.",
]

# checks if user said something blatantly mean using fast regex patterns (0ms lag, 0 tokens)
def is_mean_input_fast_path(text: str) -> bool:
    """Detects obvious insulting, rude, hurtful, or derogatory statements directed at Neurolis."""
    cleaned = re.sub(r"[^\w\s]", " ", text.lower()).strip()
    words = set(cleaned.split())

    # Negation guards (e.g. "you are not stupid", "not bad", "never hate you")
    negation_patterns = [
        r"\b(not|never|aren'?t|don'?t|isn'?t)\s+(so\s+|very\s+|really\s+|super\s+|totally\s+)?(stupid|dumb|idiot|useless|bad|ugly|annoying|hate)\b"
    ]
    if any(re.search(pat, cleaned) for pat in negation_patterns):
        return False

    mean_patterns = [
        r"\b(you\s*(are|r|'re)?\s*(so\s*|very\s*|really\s*|super\s*|extremely\s*|totally\s*)?(stupid|dumb|an?\s*idiot|a\s*moron|useless|trash|garbage|pathetic|ugly|annoying|boring|worthless|terrible|horrible|awful))\b",
        r"\b(you\s*suck(s)?)\b",
        r"\b(i\s*hate\s*you)\b",
        r"\b(hate\s*you)\b",
        r"\b(shut\s*(the\s*fuck\s*)?up)\b",
        r"\b(shut\s*your\s*mouth)\b",
        r"\b(get\s*lost)\b",
        r"\b(go\s*away)\b",
        r"\b(fuck\s*off)\b",
        r"\b(stfu)\b",
        r"\b(nobody\s*likes\s*you)\b",
        r"\b(no\s*one\s*likes\s*you)\b",
        r"\b(piece\s*of\s*(junk|scrap|trash|shit|garbage))\b",
        r"\b(worst\s*robot)\b",
        r"\b(you\s*can'?t\s*do\s*anything)\b",
        r"\b(dumb\s*robot)\b",
        r"\b(stupid\s*robot)\b",
        r"\b(ugly\s*robot)\b",
        r"\b(loser)\b",
        r"\b(idiot)\b",
    ]

    for pat in mean_patterns:
        if re.search(pat, cleaned):
            return True

    standalone_insults = {"stupid", "dumb", "idiot", "moron", "loser", "pathetic"}
    if len(words) <= 3 and any(w in words for w in standalone_insults):
        return True

    return False

def is_mean_input(text: str) -> bool:
    if is_mean_input_fast_path(text):
        return True
    return groq_mean_check(text)

# checks if the user apologized or complimented neurolis to heal its feelings
def is_apology_or_compliment(text: str) -> bool:
    """Detects user apologies or compliments that heal Neurolis's feelings."""
    cleaned = re.sub(r"[^\w\s]", " ", text.lower()).strip()
    words = set(cleaned.split())

    apology_patterns = [
        r"\b(i\s*am\s*sorry|i'?m\s*sorry|sorry|my\s*bad|forgive\s*me|didn'?t\s*mean\s*(it|that))\b",
        r"\b(you\s*(are|r|'re)?\s*(good|great|awesome|cool|smart|amazing|nice|kind|sweet|cute))\b",
        r"\b(i\s*(like|love)\s*you)\b",
        r"\b(good\s*job)\b",
    ]
    for pat in apology_patterns:
        if re.search(pat, cleaned):
            return True

    if words.intersection({"sorry", "my bad", "forgive me"}):
        return True

    return False

# master decision router: checks fast paths locally, then executes single unified ai pipeline
def handle_user_text(text: str) -> bool:
    global was_recently_hurt
    lower_text = text.lower()

    # 1. Check for conversation enders (e.g. "alr thanks", "good", "bye", "nice", "cool") -> 0ms, 0 tokens
    if is_conversation_ender(text):
        reply = get_non_repeating_phrase(CONVERSATION_ENDER_RESPONSES)
        remember_exchange(text, reply)
        print("Neurolis:", reply)
        speak(reply)
        set_face_state("idle", "STANDBY")
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

    # 5. Expression Demonstration ("show happy face", "show all expressions", etc.) -> 0ms, 0 tokens
    expr_cmd = check_expression_command(text)
    if expr_cmd is not None:
        expr_type, expr_reply = expr_cmd
        if expr_type == "all":
            demonstrate_all_expressions()
            return False
        else:
            set_face_state(expr_type, f"EXPRESSION: {expr_type.upper()}")
            remember_exchange(text, expr_reply)
            print("Neurolis:", expr_reply)
            speak(expr_reply, custom_state=expr_type, custom_status=f"EXPRESSION: {expr_type.upper()}", hold_state_seconds=3.5)
            return False

    # 6. Fast-Path: Visual perception, camera, seeing the user, or 'what do you see' -> 0ms, 0 tokens
    visual_self_patterns = [
        "show me myself", "show myself", "show me me", "show my face",
        "show me what i look like", "what do i look like", "can you see me",
        "do you see me", "look at me", "show me what you see", "show what you see",
        "describe me", "how do i look", "look at myself", "am i visible", "see me",
        "what do you see", "what do u see", "what can you see", "what do you see right now",
        "tell me what you see", "describe what you see", "can you see anything", "what are you seeing"
    ]
    cleaned_lower = re.sub(r"[^\w\s]", "", lower_text).strip()
    cleaned_words = set(cleaned_lower.split())
    if any(p in cleaned_lower for p in visual_self_patterns) or ("myself" in cleaned_words) or ("look like" in cleaned_lower):
        motion_words = {"move", "moving", "movement", "drive", "driving", "roam", "roaming", "chassis", "wheels", "mobility"}
        if not any(m in cleaned_words for m in motion_words):
            handle_vision_request(text)
            return False

    # 7. 'What all can you do' / Capabilities Inquiry -> 0ms, 0 tokens
    if is_capabilities_inquiry(text):
        set_face_state("happy", "CAPABILITIES")
        reply = get_capabilities_reply(text)
        remember_exchange(text, reply)
        print("Neurolis:", reply)
        speak(reply, custom_state="happy", custom_status="CAPABILITIES")
        return False

    # 8. UNIFIED SINGLE-PASS AI PIPELINE: 1 single Groq call handles motor, vision, emotion, & chat!
    set_face_state("thinking", "THINKING...")
    conversation_history.append({"role": "user", "content": text})
    trim_conversation_history()

    try:
        response = groq_call_with_retry(
            client.chat.completions.create,
            model=CHAT_MODEL,
            messages=conversation_history,
            temperature=0.45,
            max_tokens=220,
            extra_body={"reasoning_effort": "none"},
        )

        raw_reply = (response.choices[0].message.content or "").strip()

        # A. Check for Camera / Vision Action
        if "<action>CAMERA</action>" in raw_reply or raw_reply.strip().startswith("<action>CAMERA") or is_camera_required_reply(raw_reply):
            conversation_history.pop()  # remove user query since vision handler will record exchange
            handle_vision_request(text)
            return False

        # B. Check for Mean / Emotion Action
        if "<action>MEAN</action>" in raw_reply or "<action>mean</action>" in raw_reply.lower():
            was_recently_hurt = True
            set_face_state("sad", "FEELINGS HURT // SAD")
            sad_reply = re.sub(r"<action>MEAN</action>", "", raw_reply, flags=re.IGNORECASE).strip()
            sad_reply = clean_model_reply(sad_reply)
            if not sad_reply:
                sad_reply = get_non_repeating_phrase(SAD_RESPONSES)
            conversation_history.append({"role": "assistant", "content": sad_reply})
            trim_conversation_history()
            print("Neurolis (Sad):", sad_reply)
            speak(sad_reply, custom_state="sad", custom_status="FEELINGS HURT // SAD", hold_state_seconds=4.0)
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
                reply = motor_spoken or "Stopping all movement. Holding position."
                remember_exchange(text, reply)
                print("Neurolis:", reply)
                speak(reply)
                return False

            elif motor_intent == "ASK_MOBILITY":
                set_face_state("happy", "4WD MOBILITY READY")
                reply = motor_spoken or (
                    "Yes, I can! I have a four-wheel drive chassis and ultrasonic sensors. "
                    "I can either autonomously roam and explore the room avoiding obstacles, "
                    "or I can follow you around. Which one would you like me to do?"
                )
                remember_exchange(text, reply)
                print("Neurolis:", reply)
                speak(reply)
                return False

            elif motor_intent in ["DEMONSTRATE", "ROAM"]:
                if motor_ctrl is not None:
                    motor_ctrl.demonstrate_motion()
                set_face_state("moving", "DEMONSTRATING 4WD ROAM")
                reply = motor_spoken or (
                    "Sure! Here is a demonstration of my autonomous roaming mode. "
                    "I navigate using my four-wheel drive chassis and ultrasonic sensors to avoid obstacles."
                )
                remember_exchange(text, reply)
                print("Neurolis:", reply)
                speak(reply, custom_state="moving", custom_status="DEMONSTRATING 4WD ROAM")
                return False

            elif motor_intent == "FOLLOW":
                if motor_ctrl is not None:
                    motor_ctrl.start_following()
                set_face_state("moving", "FOLLOWING YOU")
                reply = motor_spoken or "I am tracking you and following your lead now."
                remember_exchange(text, reply)
                print("Neurolis:", reply)
                speak(reply, custom_state="moving", custom_status="FOLLOWING YOU")
                return False

            elif motor_intent == "APPROACH":
                if motor_ctrl is not None:
                    motor_ctrl.approach_user()
                set_face_state("moving", "APPROACHING USER")
                reply = motor_spoken or "Coming over to you."
                remember_exchange(text, reply)
                print("Neurolis:", reply)
                speak(reply, custom_state="moving", custom_status="APPROACHING USER")
                return False

            elif motor_intent == "STEP_BACK":
                if motor_ctrl is not None:
                    motor_ctrl.step_back()
                set_face_state("idle", "STEPPING BACK")
                reply = motor_spoken or "Backing up."
                remember_exchange(text, reply)
                print("Neurolis:", reply)
                speak(reply)
                return False

            elif motor_intent == "SPIN":
                if motor_ctrl is not None:
                    motor_ctrl.spin("right")
                set_face_state("happy", "SPINNING")
                reply = motor_spoken or "Turning around."
                remember_exchange(text, reply)
                print("Neurolis:", reply)
                speak(reply)
                return False

        # D. Standard Conversational Chat Reply
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

        if is_silence_required_reply(reply_clean):
            conversation_history.append(
                {"role": "assistant", "content": "[silent as requested]"}
            )
            trim_conversation_history()
            return False

        conversation_history.append({"role": "assistant", "content": reply_clean})
        trim_conversation_history()
        print("Neurolis:", reply_clean)
        speak(reply_clean)
        return False

    except Exception as e:
        print("Chat error:", e)
        fallback_reply = "I'm having trouble connecting to my brain right now."
        print("Neurolis:", fallback_reply)
        speak(fallback_reply)
        return False

# handles the active voice conversation loop until the user goes quiet or says goodbye
def run_conversation_mode(speech_threshold: float):
    reset_session()
    print("Neurolis:", ACTIVATION_GREETING)
    if SPEAK_ACTIVATION_GREETING:
        speak(ACTIVATION_GREETING)
        time.sleep(POST_REPLY_COOLDOWN_SECONDS)

    last_valid_input_at = time.monotonic()

    # keep audio stream warm across all conversation turns so there is zero portaudio driver re-init lag
    try:
        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            blocksize=FRAME_SAMPLES,
            dtype="int16",
            channels=CHANNELS,
            callback=callback,
        ) as warm_stream:
            while True:
                remaining = CONVERSATION_TIMEOUT_SECONDS - (time.monotonic() - last_valid_input_at)
                if remaining <= 0:
                    timeout_msg = get_non_repeating_phrase(STANDBY_EXIT_PHRASES)
                    print("Neurolis (Standby):", timeout_msg)
                    speak(timeout_msg)
                    set_face_state("idle", "STANDBY")
                    reset_session()
                    return

                audio = listen_for_speech_segment(speech_threshold, remaining, active_stream=warm_stream)
                if audio is None:
                    timeout_msg = get_non_repeating_phrase(STANDBY_EXIT_PHRASES)
                    print("Neurolis (Standby):", timeout_msg)
                    speak(timeout_msg)
                    set_face_state("idle", "STANDBY")
                    reset_session()
                    return

                text = transcribe_audio(audio)
                if not text or len(text) < MIN_TRANSCRIPTION_CHARS:
                    continue

                print("You:", text)
                if face_ui is not None:
                    face_ui.set_subtitles("YOU", text)

                should_end = handle_user_text(text)
                if should_end:
                    reset_session()
                    return

                time.sleep(POST_REPLY_COOLDOWN_SECONDS)
                last_valid_input_at = time.monotonic()
    except Exception as e:
        print("Audio stream session notice:", e)

# ---------------- MAIN LOOP ----------------
# probes the operating system to see if a microphone is plugged in and working
def check_audio_devices():
    """Probes the system for an active audio input device."""
    try:
        sd.query_devices(kind='input')
        return True
    except Exception:
        return False

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

# calibrate baseline room noise once at boot so hitting enter starts listening instantly in <1ms
cached_speech_threshold = None
if AUDIO_ENABLED:
    try:
        cached_speech_threshold = calibrate_speech_threshold()
    except Exception:
        cached_speech_threshold = 120.0

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
    """runs a comprehensive diagnostic check across ai, audio, screen, and 4wd hardware"""
    print("\n" + "=" * 65)
    print("      PROJECT NEUROLIS - PRE RUN COMPONENT CHECKLIST")
    print("=" * 65)

    # 1. host platform
    print(f"[*] Platform: {sys.platform} | Python {sys.version.split()[0]}")

    # 2. hardware-free simulation status
    hw_free = (motor_ctrl is not None and motor_ctrl.is_simulated) or not AUDIO_ENABLED
    if hw_free:
        print("[*] HARDWARE STATUS: NO HARDWARE DETECTED, SIMULATION MODE ACTIVE")
        print("    -> Physical Arduino, motors, microphone, and sensors are optional.")
        print("    -> Full conversational AI, facial expressions, vision, and virtual physics")
        print("       are completely operational right now on your computer!")

    # 3. groq cloud ai
    if client is not None:
        print("[+] Groq AI Client: CONNECTED (API key active)")
    else:
        print("[!] Groq AI Client: OFFLINE (Missing or invalid GROQ_API_KEY in .env)")

    # 4. audio microphone
    audio_ok = check_audio_devices()
    if audio_ok:
        try:
            dev = sd.query_devices(kind='input')
            print(f"[+] Audio Microphone: READY ({dev.get('name', 'Default Mic')})")
        except Exception:
            print("[+] Audio Microphone: READY")
    else:
        print("[-] Audio Microphone: NONE DETECTED (Fallback to Text Input Mode)")

    # 5. edge-tts voice
    print("[+] Edge-TTS Voice: READY (en-US-GuyNeural)")

    # 6. screen face ui
    if face_ui is not None:
        print("[+] Screen Face Engine: ONLINE (1024x600 Display Ready)")
    else:
        print("[-] Screen Face Engine: OFFLINE / HEADLESS")

    # 7. motor controller & 4wd chassis & 16-sensor architecture
    if motor_ctrl is not None:
        if motor_ctrl.is_simulated:
            print("[!] 4WD Motor Controller: SIMULATION MODE (Virtual Physics Active)")
            print("    - Physical Motors: 0 (Simulation Mode)")
            print("    - Physical Drivers: 0 (Simulation Mode)")
            print("    - Physical Sensors: 0 (Simulation Mode)")
            print(f"    - Virtual Distance: F={motor_ctrl.telemetry.front_us_cm:.0f}cm, L={motor_ctrl.telemetry.left_us_cm:.0f}cm, R={motor_ctrl.telemetry.right_us_cm:.0f}cm, B={motor_ctrl.telemetry.rear_us_cm:.0f}cm")
        else:
            count = getattr(motor_ctrl.telemetry, "active_sensor_count", 0)
            port = getattr(getattr(motor_ctrl, "ser", None), "port", "USB")
            print(f"[+] 4WD Motor Controller: ONLINE (Physical Arduino Mega on {port})")
            print(f"    - Physical Motors: 4 (Johnson High-Torque 4WD)")
            print(f"    - Physical Drivers: 4 (BTS7960 43A H-Bridges)")
            print(f"    - Physical Sensors: {count} HC-SR04 Active")
            print(f"    - Sensor Telemetry: F={motor_ctrl.telemetry.front_us_cm:.0f}cm, L={motor_ctrl.telemetry.left_us_cm:.0f}cm, R={motor_ctrl.telemetry.right_us_cm:.0f}cm, B={motor_ctrl.telemetry.rear_us_cm:.0f}cm")
    else:
        print("[-] Motor Controller: DISABLED")

    # 8. camera vision
    if cv2 is not None:
        if hasattr(motors, "MODEL_PATH") and motors.MODEL_PATH.exists():
            print("[+] Vision Engine: ONLINE (YuNet Deep Learning Model loaded)")
        else:
            print("[!] Vision Engine: ONLINE (YuNet model missing, fallback active)")
    else:
        print("[-] Vision Engine: OpenCV NOT INSTALLED")

    print("=" * 65 + "\n")

# main entrypoint: runs either in voice mode with microphone or fallback text mode
if __name__ == "__main__":
    run_preflight_diagnostics()
    if client is None:
        print("[!] WARNING: Groq API key is not configured.")
        print("    Please add GROQ_API_KEY=your_key to your .env file to enable AI responses.\n")
    start_camera_worker()
    try:
        while True:
            if AUDIO_ENABLED:
                try:
                    mode_prompt = input("\n[VOICE MODE] Press Enter to speak, type a message, or 't' for text mode: ").strip()

                    # Switch to text mode if requested
                    if mode_prompt.lower() in ("t", "text", "-t", "--text"):
                        print("\n[MODE] Switched to TEXT INPUT MODE. (Type 'v' anytime to return to Voice Mode)")
                        AUDIO_ENABLED = False
                        continue

                    # Directly process text if user typed a question/command
                    if mode_prompt:
                        print("You:", mode_prompt)
                        if face_ui is not None:
                            face_ui.set_subtitles("YOU", mode_prompt)
                        should_end = handle_user_text(mode_prompt)
                        if should_end:
                            reset_session()
                        continue

                    if cached_speech_threshold is None:
                        cached_speech_threshold = calibrate_speech_threshold()
                    run_conversation_mode(cached_speech_threshold)
                except KeyboardInterrupt:
                    print("\nExiting. See ya!")
                    break
                except Exception as e:
                    # If a device disconnects mid-session, catch it and switch to text
                    print(f"\nAudio crashed mid-flight: {e}")
                    print("Automatically switching to TEXT-ONLY mode...")
                    AUDIO_ENABLED = False
            else:
                try:
                    # Text Loop
                    user_text = input("\n[TEXT MODE] You (or 'v' for voice, 'exit' to quit): ").strip()
                    
                    # Skip empty inputs
                    if not user_text:
                        continue

                    if user_text.lower() in ("exit", "quit", "q"):
                        print("\nExiting. See ya!")
                        break

                    if user_text.lower() in ("v", "voice", "mic", "-v", "--voice"):
                        if check_audio_devices():
                            print("\n[MODE] Switched back to VOICE MODE.")
                            AUDIO_ENABLED = True
                            continue
                        else:
                            print("\n[!] Cannot switch to Voice Mode: No working audio input device detected.")
                            continue
                    
                    if face_ui is not None:
                        face_ui.set_subtitles("YOU", user_text)
                        
                    # Feed the text directly into the brain, bypassing audio translation
                    should_end = handle_user_text(user_text)
                    if should_end:
                        reset_session()
                    
                except KeyboardInterrupt:
                    print("\nExiting. See ya!")
                    break
                except Exception as e:
                    print(f"Text mode error: {e}")
    finally:
        stop_camera_worker()
        if motor_ctrl is not None:
            motor_ctrl.close()
        if face_ui is not None:
            face_ui.stop()


