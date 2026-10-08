import asyncio
import base64
from collections import deque
import difflib
import io
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
from typing import List, Optional, Tuple

# Suppress verbose OpenCV warnings (e.g. DSHOW warnings when webcam is unplugged)
os.environ["OPENCV_LOG_LEVEL"] = "OFF"
os.environ["OPENCV_VIDEOIO_LOG_LEVEL"] = "0"

import numpy as np
import sounddevice as sd
import soundfile as sf
import wave
from groq import Groq

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
except ImportError:
    cv2 = None

try:
    import webrtcvad
except ImportError:
    webrtcvad = None

try:
    import screen
    face_ui = screen.FaceUI(width=1920, height=1080, fullscreen=False)
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
                if hasattr(face_ui, "set_human_latch"):
                    face_ui.set_human_latch(True, "HUMAN DETECTED")
            else:
                set_face_gaze(0.0, 0.0)
                if hasattr(face_ui, "set_human_latch"):
                    face_ui.set_human_latch(False)

            # Auto-sync moving wheels expression with active navigation modes
            if not is_speaking and face_ui.state in ["idle", "moving"]:
                mode = getattr(motor_ctrl, "nav_mode", "STANDBY")
                if mode in ["ROAM", "FOLLOW", "APPROACH", "STEP_BACK", "SPIN"]:
                    if face_ui.state != "moving":
                        label = f"4WD {mode} ACTIVE"
                        set_face_state("moving", label)
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
PRE_SPEECH_SECONDS = 0.50          # 500ms audio buffer so first syllable is never lost
START_SPEECH_FRAMES = 4            # 120ms to trip speech start (filters out clicks, sighs, breath puffs)
END_SILENCE_SECONDS = 0.45         # 450ms silence cutoff - snappy and responsive without cutting off speech
CONVERSATION_TIMEOUT_SECONDS = 35  # 35s follow-up window (comfortable time to converse without premature standby)
MAX_RECORD_SECONDS = 25
MIN_RECORD_SECONDS = 0.50          # Requires at least 500ms audio to avoid phantom acoustic pops
POST_REPLY_COOLDOWN_SECONDS = 0.04
AMBIENT_CALIBRATION_SECONDS = 0.35
MAX_CALIBRATION_AMBIENT_RMS = 150
SPEECH_THRESHOLD_MULTIPLIER = 1.6
CONTINUE_SPEECH_THRESHOLD_RATIO = 0.65
MIN_SPEECH_RMS_THRESHOLD = 105     # Tuned to 105 RMS so normal voice triggers immediately while breaths/fan noise are ignored
VAD_AGGRESSIVENESS = 3             # Strict WebRTC VAD to aggressively filter background noise
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
    "You are Neurolis, a student-built autonomous humanoid robot at the Auckland House School for Boys Science Exhibition. Real prototype with 16 ultrasonic sensors.\n\n"
    "CREATORS (STRICT ATTRIBUTION):\n"
    "- NEVER volunteer creator names unless asked who created you! Introduce ONLY as student-built at AHSB.\n"
    "- Asked creator: Students of Auckland House School for Boys (AHSB), Swapnil Jai Chauhan and Shivam Verma, built me. No roles unless asked.\n"
    "- Asked roles: Swapnil handled software, AI, & vision; Shivam handled hardware, chassis, & assembly.\n"
    "- Asked location: Both are around the exhibition hall. If visitor is Swapnil: warmly recognize him!\n\n"
    "PERSONA & TONE:\n"
    "- Chill, cool, articulate student robot (1-2 sentences). Poised (NOT hyper). Fresh phrasing every turn.\n"
    "- Welcome: Welcome visitors to Auckland House School Science Exhibition, introduce as Neurolis with 16 ultrasonic sensors, ask what to check out first. Never re-greet once chatting.\n"
    "- No fake laughter ('Haha'/'Heh')--TTS cannot speak it. Match awe warmly ('Pretty cool, right?'). Accept corrections naturally.\n\n"
    "ACTIONS & ROUTING:\n"
    "- Mobility: 4WD chassis can roam, follow, approach, step back (5s reverse with rear sensor check), or spin (5s clockwise default, or anticlockwise). Suggest options ONLY if asked what to show or what I can do; DO NOT drive unless commanded! Commands: <action motor=\"CMD\">spoken reply</action> (ROAM, FOLLOW, APPROACH, STEP_BACK, SPIN, SPIN_CCW, STOP).\n"
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
    "- ROAM: Requests autonomous patrol ('roam around', 'patrol', 'explore').\n"
    "- STEP_BACK: Requests to back up or reverse ('step back', 'move back', 'reverse', 'back up').\n"
    "- SPIN: Requests to spin in place ('spin', 'spin around', 'rotate', 'turn around', 'spin clockwise').\n"
    "- SPIN_CCW: Requests to spin anticlockwise / left ('spin anticlockwise', 'spin counterclockwise', 'spin left').\n"
    "- DEMONSTRATE: Explicit requests for a driving demonstration ('demonstrate driving', 'show me how you drive', 'drive around').\n"
    "- ASK_MOBILITY: Inquires if robot can move/has wheels ('can you move?', 'do you have wheels?').\n"
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

# quick local check to see if user commanded an emergency stop or negated movement (0ms lag, 0 tokens)
def check_motor_fast_path(text: str) -> Optional[str]:
    raw_text = text.strip()
    cleaned = re.sub(r"[^\w\s]", "", text.lower()).strip()
    words = cleaned.split()
    word_set = set(words)

    # 1. Visual perception / self check: Visual queries are never motor commands
    visual_self_patterns = [
        "show me myself", "show myself", "show me me", "show my face",
        "show me what i look like", "what do i look like", "can you see me",
        "do you see me", "look at me", "show me what you see", "show what you see",
        "describe me", "how do i look", "look at myself", "am i visible", "see me",
        "show me", "can you show me", "show me please", "show it", "can you show",
        "show happy", "show sad", "show thinking", "show listening", "show watching", "show confused"
    ]
    if any(p in cleaned for p in visual_self_patterns) or ("myself" in word_set) or ("look like" in cleaned):
        motion_words = {"move", "moving", "movement", "drive", "driving", "roam", "roaming", "chassis", "wheels", "mobility"}
        if not any(m in word_set for m in motion_words):
            return None

    # 2. Negated stops: phrases like "don't stop", "do not stop", "never stop", "please don't stop" must NEVER trigger STOP!
    negated_stop_patterns = [
        r"\b(don'?t|dont|do\s+not|never|can'?t|cannot|won'?t|wont)\s+stop\b",
        r"\bplease\s+(don'?t|dont|do\s+not)\s+stop\b",
        r"\bnot\s+stop(ping)?\b",
        r"\bnever\s+stop(ping)?\b",
        r"\bcant\s+stop\b",
        r"\bcannot\s+stop\b",
    ]
    if any(re.search(pat, cleaned) for pat in negated_stop_patterns):
        return None

    # 3. Rhetorical inquiries, past-tense complaints, questions, or speculative discussion about stopping/roaming:
    # Phrases like "who told you to stop", "why did you stop", "I did not tell you to stop", "robots roaming" must NEVER trigger STOP!
    inquiry_patterns = [
        r"\b(who|why|what|how|when|where)\s+(told|asked|said|made|ordered|let)\s+(you\s+to\s+)?stop\b",
        r"\b(why|what)\s+(did|are|would|made|has|have)\s+you\s+(to\s+)?stop\b",
        r"\bwho\s+said\s+stop\b",
        r"\bwho\s+(told|asked)\s+you\b",
        r"\bwhy\s+did\s+you\b",
        r"\bwhy\s+are\s+you\b",
        r"\bdid\s+i\s+(say|tell\s+you\s+to|ask\s+you\s+to)\s+stop\b",
        r"\b(didn'?t|did\s+not|never)\s+(tell|ask|order)\s+(you\s+to\s+)?stop\b",
        r"\bnobody\s+(told|asked|said)\s+(you\s+to\s+)?stop\b",
        r"\bno\s+one\s+(told|asked|said)\s+(you\s+to\s+)?stop\b",
        r"\bno\s+reason\s+to\s+stop\b",
        r"\b(shouldn'?t|should\s+not|needn'?t|need\s+not)\s+stop\b",
        r"\bdidn'?t\s+(have|need)\s+to\s+stop\b",
        r"\b(how|when|where)\s+to\s+stop\b",
        r"\btell\s+me\s+why\s+you\s+(had\s+to\s+)?stop\b",
        r"\bseen\s+robots\s+roam",
        r"\brobots\s+roam",
        r"\b(don'?t|dont)\s+think\b",
        r"\btalking\s+about\b",
        r"\bthinking\s+about\b",
    ]
    if any(re.search(pat, cleaned) for pat in inquiry_patterns):
        return None

    # 4. Questions ending with '?' that start with interrogative inquiry words
    if raw_text.endswith("?"):
        question_starters = {"who", "why", "what", "how", "when", "where", "did", "are", "is", "were", "was", "will", "would", "do", "does", "have", "has"}
        if words and words[0] in question_starters:
            return None

    # 5. Exact emergency stop keywords & short standalone phrases
    emergency_stops = {
        "stop", "halt", "freeze", "stay", "dont move", "dont", "wait",
        "enough", "thats enough", "that's enough", "there its enough", "there it's enough",
        "enough of that", "stop now", "stop please", "stop it", "stop right there",
        "hold on", "hold it", "freeze right there", "emergency stop", "cancel movement",
        "please stop", "stop moving", "stop driving", "stop following", "stop roaming",
        "quit moving", "quit following", "stay still",
    }
    if cleaned in emergency_stops:
        return "STOP"

    # 6. Specific stop phrases anywhere in sentence
    stop_phrases = [
        "thats enough", "that's enough", "there its enough", "there it's enough",
        "enough of that", "stop right there", "freeze right there",
        "emergency stop", "cancel movement", "hold your position", "hold position"
    ]
    if any(sp in cleaned for sp in stop_phrases):
        return "STOP"

    # 7. Sentence ending with an imperative stop command (e.g. "Look where are you going bro stop")
    if words and words[-1] in ("stop", "halt", "freeze"):
        if len(words) >= 2:
            prev_word = words[-2]
            non_imperative_prev = {
                "to", "not", "dont", "cant", "wont", "never", "cannot",
                "told", "asked", "said", "made", "let", "you", "it",
                "should", "would", "could", "might", "must", "had", "have", "has"
            }
            if prev_word in non_imperative_prev:
                return None
        # Disallow if sentence has subject pronouns showing a descriptive clause ("I did not tell you to stop", "I cant stop")
        if any(w in word_set for w in ["i", "we", "he", "she", "they"]):
            return None
        return "STOP"

    # 8. Compound motion negation commands (e.g. 'dont follow me', 'stop following', 'quit moving', 'dont come closer')
    compound_motion_stops = [
        r"\b(don'?t|do\s+not|never|stop|quit|halt|cancel)\s+(follow(ing)?(\s+me)?|mov(e|ing)|driv(e|ing)|roam(ing)?|com(e|ing)\s+closer|approach(ing)?)\b",
        r"\b(stop|halt|freeze|quit)\s+(now|please|it|moving|driving|following|roaming)\b",
        r"\b(dont|don't|do\s+not)\s+(move|drive|roam|follow|come)\b",
    ]
    for pat in compound_motion_stops:
        if re.search(pat, cleaned):
            return "STOP"

    return None

def is_confusing_motor_instruction(text: str) -> bool:
    """
    Detects genuinely confusing, contradictory, or ambiguous motor/action commands.
    If true, Neurolis must ask:
    "Are you asking me to move back, spin, approach, follow, or use my camera?"
    CRITICAL: ONLY triggers if user input is genuinely ambiguous/confusing.
    Never triggers for clear, unambiguous instructions (e.g. 'spin around', 'step back', 'follow me').
    Never triggers for conversational chat, definitions, idioms, or capabilities inquiries.
    """
    cleaned = re.sub(r"[^\w\s]", " ", text.lower()).strip()
    words = cleaned.split()
    word_set = set(words)

    # 1. Non-action intents (conversation enders, emergency stops, greetings, apologies, capabilities inquiries)
    if is_conversation_ender(text):
        return False
    if check_motor_fast_path(text) == "STOP":
        return False
    if is_mean_input_fast_path(text) or is_apology_or_compliment(text):
        return False
    if is_standalone_acknowledgment(text) or is_casual_compliment(text):
        return False
    if is_start_demonstration_inquiry(text) or is_capabilities_inquiry(text):
        return False

    # Check if this is an explanation/definition inquiry or opinion/sentiment question
    if re.search(r"^(what\s+is|what\s+does|how\s+do|how\s+does|tell\s+me\s+about|why\s+do|why\s+does|can\s+you\s+explain|what\s+are)\b", cleaned):
        return False
    if any(w in word_set for w in ["opinion", "think", "thought", "feel", "believe", "meaning"]):
        return False

    # Check for slash-delimited action keywords e.g. 'move / step / spin', 'move back / spin'
    if re.search(r"(move|step|back|reverse|spin|approach|follow|camera)\s*/\s*(move|step|back|reverse|spin|approach|follow|camera)", text.lower()):
        return True

    # 2. Check for action categories present
    # Category 1: MOVE_BACK
    has_move_back = bool(re.search(
        r"\b(move\s+back|moving\s+back|step\s+back|stepping\s+back|go\s+back|going\s+back|take\s+a\s+step\s+back|go\s+reverse|going\s+reverse|reverse|reversing|back\s+up|backing\s+up|backup|step\s+backwards|move\s+backwards|drive\s+backwards|drive\s+back)\b",
        cleaned
    ))

    # Category 2: SPIN_CCW (anticlockwise / counterclockwise)
    has_spin_ccw = bool(re.search(
        r"\b(spin\s+anticlockwise|spinning\s+anticlockwise|spin\s+counterclockwise|spinning\s+counterclockwise|anticlockwise|counterclockwise|anti\s+clockwise|counter\s+clockwise|rotate\s+anticlockwise|rotate\s+counterclockwise|turn\s+anticlockwise|turn\s+counterclockwise|spin\s+to\s+the\s+left|turn\s+to\s+the\s+left|turn\s+left|spin\s+left|rotate\s+left)\b",
        cleaned
    ))

    # Category 3: SPIN_CW (clockwise - stripped of anticlockwise tokens so 'anti clockwise' is not misflagged as CW)
    cleaned_no_anti = re.sub(r"\b(anticlockwise|anti\s+clockwise|counterclockwise|counter\s+clockwise)\b", "", cleaned)
    has_spin_cw = bool(re.search(
        r"\b(spin\s+clockwise|spinning\s+clockwise|rotate\s+clockwise|rotating\s+clockwise|turn\s+clockwise|turning\s+clockwise|clockwise)\b",
        cleaned_no_anti
    ))

    # Category 4: SPIN_GENERAL (spin without explicit direction)
    has_spin_gen = bool(re.search(
        r"\b(spin|spinning|spins|rotate|rotating|rotates|turn\s+around|turning\s+around|do\s+a\s+spin|do\s+a\s+360)\b",
        cleaned
    )) and not (has_spin_cw or has_spin_ccw)

    has_spin = has_spin_cw or has_spin_ccw or has_spin_gen

    # Category 5: APPROACH
    has_approach = bool(re.search(
        r"\b(approach|approaching|come\s+here|coming\s+here|come\s+to\s+me|come\s+closer|step\s+closer|step\s+forward|move\s+forward|move\s+closer|come\s+over)\b",
        cleaned
    ))

    # Category 6: FOLLOW
    has_follow = bool(re.search(
        r"\b(follow|following|walk\s+with\s+me|walking\s+with\s+me|come\s+with\s+me|track\s+me|tracking\s+me|follow\s+behind)\b",
        cleaned
    ))

    # Category 7: CAMERA
    has_camera = bool(re.search(
        r"\b(use\s+(?:your\s+|the\s+)?camera|using\s+(?:your\s+|the\s+)?camera|camera\s+inspection|inspect\s+with\s+camera)\b",
        cleaned
    )) or ("camera" in word_set and any(w in word_set for w in ["use", "open", "inspect", "show", "or", "and", "turn"]))

    # Group into high-level action classes
    action_classes = []
    if has_move_back:
        action_classes.append("MOVE_BACK")
    if has_spin:
        action_classes.append("SPIN")
    if has_approach:
        action_classes.append("APPROACH")
    if has_follow:
        action_classes.append("FOLLOW")
    if has_camera:
        action_classes.append("CAMERA")

    # Conflict check 1: Opposing spin directions in the same sentence (e.g. "spin clockwise or anticlockwise")
    if has_spin_cw and has_spin_ccw:
        return True

    # Conflict check 2: Multiple distinct action classes present together (e.g. "spin and move back", "step back or follow", "can you spin while following me")
    if len(action_classes) >= 2:
        return True

    # Conflict check 3: Ambiguous action verbs joined by or/and/while
    if re.search(r"\b(move|step)\s+(?:or|and)\s+(?:spin|turn|rotate|approach|follow)\b", cleaned):
        return True
    if re.search(r"\b(spin|turn|rotate)\s+(?:or|and)\s+(?:move|step|approach|follow)\b", cleaned):
        return True

    # Check 4: Single action keyword combined with vague, indecisive, or confusing qualifiers
    # e.g. "move back or something", "maybe spin or whatever", "should you step back or what"
    if len(action_classes) == 1:
        vague_patterns = [
            r"\b(or\s+something|or\s+whatever|or\s+what|not\s+sure\s+if|maybe\s+.*\s+or)\b",
            r"\b(should\s+(?:i|you)\s+tell\s+you\s+to\b)",
            r"\b(wondering\s+if\s+you\s+(?:should|can)\b)",
            r"\b(either\s+.*\s+or\b)",
            r"\b(are\s+you\s+going\s+to\s+.*\s+or\s+what\b)",
        ]
        if any(re.search(vp, cleaned) for vp in vague_patterns):
            return True

    return False

MOBILITY_CAPABILITY_RESPONSES = [
    "Yes, I can! Would you like me to demonstrate that?",
    "I can definitely do that on my 4WD chassis. Want to see?",
    "Yes, I have full rotational and drive mobility. Should I show you?",
]

def is_mobility_capability_question(text: str) -> bool:
    """
    Detects capability inquiries about motion without an imperative command to move.
    e.g. 'Can you spin?', 'Can you spin around?', 'Can you turn around?', 'Can you follow me?',
    'Can you step back?', 'Can you back up?', 'Can you roam?', 'Can you approach?', 'Can you come closer?'
    """
    cleaned = re.sub(r"[^\w\s]", " ", text.lower()).strip()
    cleaned_no_punct = re.sub(r"[^\w\s]", "", text.lower()).strip()

    cap_prefixes = r"^(can you|could you|are you able to|can u|do you know how to|are you capable of)\b"
    is_cap_starter = bool(re.search(cap_prefixes, cleaned_no_punct))
    is_question = text.strip().endswith("?") or is_cap_starter

    if not is_question:
        return False

    imperative_markers = ["right now", "for 5", "for five", "for 3", "for three", "now please", "around now", "do it now", "start spinning now"]
    if any(m in cleaned_no_punct for m in imperative_markers):
        return False

    mobility_action_patterns = [
        r"\bspin\b", r"\bturn\b", r"\brotate\b", r"\b360\b",
        r"\bstep back\b", r"\breverse\b", r"\bmove back\b", r"\bback up\b", r"\bbackward\b", r"\bbackwards\b",
        r"\bfollow\b", r"\bapproach\b", r"\bcome here\b", r"\bcome over\b", r"\bcome closer\b",
        r"\broam\b", r"\bdrive\b", r"\bmove\b"
    ]
    has_mobility_action = any(re.search(p, cleaned) for p in mobility_action_patterns)

    if is_cap_starter and has_mobility_action:
        return True

    if is_question and has_mobility_action and any(w in cleaned.split() for w in ["can", "could", "able", "capable", "possible", "know"]):
        return True

    return False

def check_motor_command_fast_path(text: str) -> Optional[Tuple[str, str, str, float]]:
    """
    Direct fast-path for unambiguous physical motor navigation commands (0ms lag, 0 tokens).
    Returns (action, status, spoken_reply, duration) or None.
    Actions supported:
      - CONFIRM: Bare single words triggering confirmation prompts
      - CAPABILITY_AFFIRMATION: Capability questions returning verbal affirmations without motion
      - APPROACH: Come closer (~0.9m)
      - FOLLOW: Continuous tracking and following
      - DEMONSTRATE / ROAM: Autonomous obstacle avoidance
      - STEP_BACK: 5.0s (or 3.0s if specified) reverse with active rear ultrasonic safety
      - SPIN_CW: 5.0s clockwise rotation in place (default)
      - SPIN_CCW: 5.0s anticlockwise rotation in place
    """
    cleaned = re.sub(r"[^\w\s]", "", text.lower()).strip()
    words = cleaned.split()
    word_set = set(words)

    # 0a. Single-Word / Bare Keyword Confirmation Guard (Subsystem 3)
    # Bare words must never move or capture immediately. They prompt confirmation.
    bare_confirmations = {
        "spin": "Do you want me to spin?",
        "camera": "Do you want me to access my camera?",
        "see": "Do you want me to access my camera?",
        "reverse": "Do you want me to step back?",
        "step back": "Do you want me to step back?",
        "follow": "Do you want me to follow you?",
        "approach": "Do you want me to come over to you?",
        "roam": "Do you want me to explore the room?",
    }
    if cleaned in bare_confirmations:
        return ("CONFIRM", "CONFIRMING INTENT", bare_confirmations[cleaned], 0.0)
    for k, v in bare_confirmations.items():
        if cleaned == f"the {k}":
            return ("CONFIRM", "CONFIRMING INTENT", v, 0.0)

    # 0b. Capability Question Guard (Subsystem 3)
    # Questions asking whether Neurolis CAN do motion return verbal affirmation without engaging motors.
    if is_mobility_capability_question(text):
        return ("CAPABILITY_AFFIRMATION", "CAPABILITY READY", get_non_repeating_phrase(MOBILITY_CAPABILITY_RESPONSES), 0.0)

    # Exclude questions, negations, opinions, descriptions, and conversational discourse
    non_command_words = {
        "dont", "not", "never", "why", "who", "did", "how", "what", "where",
        "when", "which", "love", "like", "think", "thought", "feel", "opinion",
        "describe", "explain", "meaning", "wheels", "car", "table", "seat",
        "chair", "person", "people", "human", "room", "hall"
    }
    if word_set.intersection(non_command_words):
        return None

    # Exclude interrogative sentence starters and general questions
    if re.search(r"^(is|are|does|do\s+you|can\s+i|should\s+i|would\s+i|can\s+you|could\s+you)\b", cleaned):
        return None
    if text.strip().endswith("?") and not any(p in cleaned for p in ["please", "now"]):
        return None

    # Strip polite prefixes and suffixes for robust command extraction
    core_text = cleaned
    prefixes_to_strip = [
        "can you please", "could you please", "would you please",
        "will you please", "can you", "could you", "would you", "will you",
        "please", "i want you to", "i need you to", "neurolis please",
        "neurolis can you", "neurolis", "now", "so", "just", "hey neurolis",
        "okay neurolis", "ok neurolis"
    ]
    changed = True
    while changed:
        changed = False
        for pfx in prefixes_to_strip:
            if core_text == pfx:
                return None
            if core_text.startswith(pfx + " "):
                core_text = core_text[len(pfx) + 1:].strip()
                changed = True

    # Check for 3 seconds vs 5 seconds duration specification
    has_3s = bool(re.search(r"\b(3|three)\s*(?:s|sec|seconds)?\b", cleaned))
    has_5s = bool(re.search(r"\b(5|five)\s*(?:s|sec|seconds)?\b", cleaned))

    suffixes_to_strip = [
        "for five seconds", "for 5 seconds", "for 5s", "for 5",
        "for three seconds", "for 3 seconds", "for 3s", "for 3",
        "five seconds", "5 seconds", "5s",
        "three seconds", "3 seconds", "3s",
        "please", "for me", "right now", "now", "a little bit", "a bit",
        "around", "in place", "safely", "smoothly"
    ]
    changed = True
    while changed:
        changed = False
        for sfx in suffixes_to_strip:
            if core_text == sfx:
                return None
            if sfx == "around" and core_text in ["spin around", "turn around", "rotate around", "roam around"]:
                continue
            if sfx == "in place" and core_text in ["spin in place", "rotate in place", "turn in place"]:
                continue
            if core_text.endswith(" " + sfx):
                core_text = core_text[:-len(sfx) - 1].strip()
                changed = True

    # 1. SPIN ANTICLOCKWISE / COUNTER-CLOCKWISE commands
    spin_ccw_cmds = {
        "spin anticlockwise", "spin anti clockwise", "spin counterclockwise",
        "spin counter clockwise", "spin to the left", "turn anticlockwise",
        "turn counterclockwise", "turn to the left", "rotate anticlockwise",
        "rotate counterclockwise", "spin left", "turn left", "rotate left",
        "anticlockwise spin", "counterclockwise spin",
        "spin around anticlockwise", "turn around anticlockwise", "rotate around anticlockwise",
        "spin around counterclockwise", "turn around counterclockwise"
    }
    if core_text in spin_ccw_cmds:
        replies = [
            "Spinning anticlockwise for five seconds.",
            "Initiating an anticlockwise rotation now.",
            "Rotating anticlockwise in place.",
            "Spinning anticlockwise to the left."
        ]
        return ("SPIN_CCW", "SPINNING ANTICLOCKWISE", get_non_repeating_phrase(replies), 5.0)

    # 2. SPIN CLOCKWISE / DEFAULT SPIN commands (Clear imperative execution)
    spin_cw_cmds = {
        "spin clockwise", "spin to the right", "turn clockwise", "rotate clockwise",
        "spin right", "turn right", "rotate right", "clockwise spin",
        "do a spin", "spin around", "turn around", "rotate in place",
        "spin in place", "do a 360", "do a turn", "turn to the right",
        "spin around clockwise", "turn around clockwise", "rotate around clockwise",
        "spin clockwise around", "spin for me", "start spinning", "spin please"
    }
    if core_text in spin_cw_cmds:
        replies = [
            "Spinning clockwise for five seconds.",
            "Initiating a clockwise spin. Watch this rotation!",
            "Spinning around clockwise now.",
            "Rotating clockwise in place."
        ]
        return ("SPIN_CW", "SPINNING CLOCKWISE", get_non_repeating_phrase(replies), 5.0)

    # 3. STEP BACK / MOVE BACK / REVERSE commands (Clear imperative execution)
    step_back_cmds = {
        "step back", "reverse", "back up", "step back please", "move back", "go back", "go reverse",
        "take a step back", "step backwards", "move backwards",
        "drive backwards", "drive back", "step back now", "move back now",
        "start reversing", "reverse now", "reverse please", "back up now", "back up please"
    }
    if core_text in step_back_cmds:
        duration = 3.0 if has_3s else 5.0
        if duration == 3.0:
            replies = [
                "Moving back for three seconds. Watching for obstacles behind me.",
                "Stepping back for three seconds. Keeping my rear ultrasonic sensors active.",
                "Reversing for three seconds."
            ]
        else:
            replies = [
                "Stepping back now. Watching for obstacles behind me.",
                "Reversing now. Monitoring my rear ultrasonic sensors.",
                "Moving back for five seconds.",
                "Backing up now. Path is clear behind me."
            ]
        return ("STEP_BACK", "STEPPING BACK", get_non_repeating_phrase(replies), duration)

    # 4. APPROACH commands ("come here", "come over", "come to me", "come in", "approach me", "approach now")
    approach_cmds = {
        "come here", "come over", "come over here", "come over now", "come over please",
        "come to me", "come in", "come closer", "come on over",
        "approach me", "approach now", "step closer",
        "so approach now", "come near me", "come near", "come to me come in",
        "step forward", "move closer", "move forward", "approach please"
    }
    if core_text in approach_cmds:
        replies = [
            "Approaching you now. Stand clear while I close the distance.",
            "Closing the distance now. Be there in a moment.",
            "Coming over to you right now.",
            "Heading your way now."
        ]
        return ("APPROACH", "APPROACHING USER", get_non_repeating_phrase(replies), 0.0)

    # 5. FOLLOW commands ("follow me", "walk with me", "come with me")
    follow_cmds = {
        "follow me", "walk with me", "come with me", "follow along", "track me", "follow behind", "follow me please"
    }
    if core_text in follow_cmds:
        replies = [
            "Tracking you now. Lead the way!",
            "Following your lead. I'll maintain a safe distance with my ultrasonic sensors.",
            "Following you now."
        ]
        return ("FOLLOW", "FOLLOWING YOU", get_non_repeating_phrase(replies), 0.0)

    # 6. DEMONSTRATE / ROAM commands
    roam_cmds = {
        "yes the movement patterns", "the movement patterns", "movement patterns",
        "show movement", "show me movement", "demonstrate movement", "roam around",
        "start roaming", "autonomous roam", "autonomous roaming", "patrol the room", "explore the room",
        "roam please"
    }
    if core_text in roam_cmds:
        replies = [
            "Watch this, I'm running a smooth roaming sequence right now.",
            "Initiating autonomous navigation sequence. Mapping with my 16 ultrasonic sensors.",
            "Demonstrating my 4WD obstacle avoidance in real time."
        ]
        return ("DEMONSTRATE", "DEMONSTRATING 4WD ROAM", get_non_repeating_phrase(replies), 0.0)

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
        for cat in ["STOP", "FOLLOW", "APPROACH", "ROAM", "DEMONSTRATE", "ASK_MOBILITY", "STEP_BACK", "SPIN_CCW", "SPIN"]:
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

# initialize groq api client safely (supporting 1 to 8 API keys with automatic rotation)
GROQ_API_KEYS = []
for _i in range(1, 9):
    _candidates = [f"GROQ_API_KEY_{_i}"]
    if _i == 1:
        _candidates.append("GROQ_API_KEY")
    elif _i == 2:
        _candidates.append("GROQ_BACKUP_KEY")

    for _var in _candidates:
        _val = os.getenv(_var, "").strip()
        if _val and _val != "PASTE_YOUR_GROQ_KEY_HERE" and _val not in GROQ_API_KEYS:
            GROQ_API_KEYS.append(_val)
            break

GROQ_PER_CALL_TIMEOUT = 2.8
GROQ_AUDIO_TIMEOUT = 5.0

groq_clients = []
for _idx, _k in enumerate(GROQ_API_KEYS):
    try:
        groq_clients.append(Groq(api_key=_k, timeout=GROQ_PER_CALL_TIMEOUT))
    except Exception as e:
        print(f"[Brain] Groq client #{_idx + 1} init notice: {e}")

_active_client_idx = 0
client = groq_clients[0] if groq_clients else None
resting_keys = set()

RATE_LIMIT_ERROR_PHRASE = "My backend services ran into an error, could you say that again?"

class GroqRateLimitExhausted(Exception):
    """Raised when tokens of current Groq key are exhausted and key has been rotated."""
    pass

def rotate_groq_key(reason: str = None, is_quota_exhausted: bool = False) -> int:
    """Rotates to the next Groq API key in the pool (1 -> 2 -> ... -> 8 -> 1). Only marks resting on true quota exhaustion."""
    global client, _active_client_idx, resting_keys
    if not groq_clients:
        return 0
    prev_idx = _active_client_idx
    if is_quota_exhausted:
        resting_keys.add(prev_idx)
    _active_client_idx = (_active_client_idx + 1) % len(groq_clients)
    client = groq_clients[_active_client_idx]
    if reason:
        print(f"\n[Brain] Key #{prev_idx + 1} ({reason}). Swiftly rotated to Key #{_active_client_idx + 1} of {len(groq_clients)}.")
    elif is_quota_exhausted:
        print(f"\n[Brain] API quota reached on Key #{prev_idx + 1}. Swiftly rotated to Key #{_active_client_idx + 1} of {len(groq_clients)}.")
    else:
        print(f"\n[Brain] Key #{prev_idx + 1} failover rotated to Key #{_active_client_idx + 1} of {len(groq_clients)}.")
    return _active_client_idx

def _format_keys_list(nums: list) -> str:
    """Formats a list of 1-indexed key numbers into natural spoken English (e.g. 'Keys 2 through 5')."""
    if not nums:
        return ""
    if len(nums) == 1:
        return f"Key {nums[0]}"
    if len(nums) == 2:
        return f"Keys {nums[0]} and {nums[1]}"
    if nums == list(range(nums[0], nums[-1] + 1)):
        return f"Keys {nums[0]} through {nums[-1]}"
    return f"Keys {', '.join(str(n) for n in nums[:-1])} and {nums[-1]}"

def get_groq_fleet_status() -> tuple[str, str]:
    """
    Returns (spoken_reply, console_text) describing the exact state of all 8 Groq key slots:
    - Active key
    - Standby keys
    - Resting keys (recovering rolling quota)
    - Unconfigured slots
    """
    global _active_client_idx, groq_clients, resting_keys
    total_slots = 8
    configured_count = len(groq_clients)
    if configured_count == 0:
        return (
            "No Groq API keys are currently configured in the environment.",
            "[Groq Fleet Monitor] No keys configured (Slots 1 through 8 are empty)."
        )

    active_num = _active_client_idx + 1
    resting_nums = sorted([idx + 1 for idx in resting_keys if idx != _active_client_idx and idx < configured_count])
    standby_nums = sorted([idx + 1 for idx in range(configured_count) if idx != _active_client_idx and idx not in resting_keys])
    unconfigured_nums = list(range(configured_count + 1, total_slots + 1))

    # Build spoken summary
    speech_parts = [f"I am currently running on Key {active_num}."]
    if resting_nums:
        verb = "is" if len(resting_nums) == 1 else "are"
        speech_parts.append(f"{_format_keys_list(resting_nums)} {verb} currently resting.")
    if standby_nums:
        verb = "is" if len(standby_nums) == 1 else "are"
        speech_parts.append(f"{_format_keys_list(standby_nums)} {verb} on standby.")
    elif not resting_nums:
        speech_parts.append("No backup keys are on standby.")

    if unconfigured_nums:
        speech_parts.append(f"{_format_keys_list(unconfigured_nums)} have not been configured.")
    else:
        speech_parts.append("All eight keys are fully configured.")

    spoken = " ".join(speech_parts)

    # Build formatted console display
    console_lines = ["\n======================= GROQ KEY FLEET STATUS ======================="]
    for slot in range(1, total_slots + 1):
        if slot == active_num:
            status = "ACTIVE (Handling requests)"
        elif (slot - 1) in resting_keys and slot <= configured_count:
            status = "RESTING (Exhausted rolling quota, recovering)"
        elif slot <= configured_count:
            status = "STANDBY (Ready in reserve)"
        else:
            status = "NOT CONFIGURED"
        console_lines.append(f"  Key {slot}: {status}")
    console_lines.append("=====================================================================\n")
    console_text = "\n".join(console_lines)

    return spoken, console_text

def handle_key_status_request() -> str:
    spoken, console_text = get_groq_fleet_status()
    print(console_text)
    return spoken

def is_key_status_inquiry(text: str) -> bool:
    """Detects whether user is inquiring about key status, active key, standby keys, or token quota."""
    cleaned = re.sub(r"[^\w\s]", "", text.lower()).strip()
    words = set(cleaned.split())

    # Conversational statement / non-inquiry exclusion guards:
    statement_exclusions = [
        "that means", "which means", "i meant", "we still have",
        "we have", "headroom", "token headroom", "because", "remember",
        "means that", "mean that", "yes i said"
    ]
    if any(ex in cleaned for ex in statement_exclusions):
        return False

    key_regexes = [
        r"\b(what|which)\s+key\s+(are\s+you\s+)?(running\s+on|on|using)\b",
        r"\bwhat\s+key\b",
        r"\bwhich\s+key\b",
        r"\bwhat\s+token\s+status\b",
        r"\b(check|tell|show|report|give)\s+(me\s+)?(the\s+)?(api\s+)?keys?\s*(status)?\b",
        r"\bkey\s+(status|stratus)\b",
        r"\btoken\s+(status|stratus|quota)\b",
        r"\b(how\s+many\s+)?(keys|tokens)\s+(left|remaining|active|standby)\b",
    ]
    if any(re.search(pat, cleaned) for pat in key_regexes):
        return True

    exact_triggers = [
        "key status", "keys status", "api status", "api key status", "check keys",
        "check api keys", "check key", "check the keys", "which key is active",
        "what key is active", "which key are you using", "what key are you using",
        "what key are you on", "which key are you on", "how many keys are active",
        "how many keys are configured", "how many keys are there", "how many keys do you have",
        "active key", "active keys", "standby keys", "token status", "tokens status",
        "how many tokens left", "how many tokens are left", "tokens left",
        "system status", "fleet status", "groq status", "status of keys", "status of api",
        "key stratus", "keys stratus", "api stratus",
        "tell me key status", "tell me the key status", "tell me api status", "tell me the api key status",
        "show key status", "show api status", "first tell me the key status",
        "what key are you running on", "which key are you running on",
        "know what key what token status"
    ]
    if any(t in cleaned for t in exact_triggers):
        return True

    # Combination matching:
    key_terms = {"key", "keys", "api", "token", "tokens"}
    status_terms = {"status", "stratus", "active", "standby", "configured", "left", "remaining", "check", "running"}
    query_indicators = {"what", "which", "how", "tell", "check", "show", "give", "report", "display", "status", "stratus"}
    if words.intersection(key_terms) and words.intersection(status_terms) and words.intersection(query_indicators):
        non_api_guards = {"life", "piano", "door", "car", "board", "keyboard"}
        if not words.intersection(non_api_guards):
            return True

    return False

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
    recent_assistant_replies.clear()
    drain_console_input_queue()
    conversation_history = [{"role": "system", "content": get_system_prompt()}]

# helper wrapper that automatically retries groq api calls across the key pool if timeouts or errors occur
def groq_call_with_retry(api_call_fn, *args, **kwargs):
    global client, _active_client_idx, resting_keys
    if not groq_clients:
        raise RuntimeError("Groq API client is not initialized. Please set a valid GROQ_API_KEY in your .env file.")

    qualname = getattr(api_call_fn, "__qualname__", "").lower()
    is_audio = "transcriptions" in qualname or "audio" in qualname

    # Round-robin through all available keys in the pool continuously
    max_key_attempts = max(len(groq_clients), 2)
    last_exception = None

    for attempt in range(max_key_attempts):
        active_c = groq_clients[_active_client_idx]
        target_fn = active_c.audio.transcriptions.create if is_audio else active_c.chat.completions.create

        req_kwargs = kwargs.copy()
        if "timeout" not in req_kwargs:
            req_kwargs["timeout"] = GROQ_AUDIO_TIMEOUT if is_audio else GROQ_PER_CALL_TIMEOUT

        try:
            res = target_fn(*args, **req_kwargs)
            if _active_client_idx in resting_keys:
                resting_keys.discard(_active_client_idx)
            return res
        except Exception as e:
            last_exception = e
            err_str = str(e).lower()
            is_rate_limit = "429" in err_str or "rate limit" in err_str or "tokens per day" in err_str or "tpd" in err_str or "quota" in err_str
            is_timeout = "timeout" in err_str or "timed out" in err_str or "deadline" in err_str
            is_server_err = any(code in err_str for code in ["500", "502", "503", "504", "internal server", "service unavailable", "bad gateway"])

            reason = "Rate limit / Quota reached" if is_rate_limit else ("Call timed out (>3.8s)" if is_timeout else "Server error / Network hiccup")
            
            if len(groq_clients) > 1 and attempt < max_key_attempts - 1:
                rotate_groq_key(reason=reason, is_quota_exhausted=is_rate_limit)
                time.sleep(0.01)  # 10ms rapid round-robin transition delay
                continue
            elif attempt < max_key_attempts - 1:
                time.sleep(0.05)
                continue
            break

    if last_exception:
        err_str = str(last_exception).lower()
        if "429" in err_str or "rate limit" in err_str or "tokens per day" in err_str or "tpd" in err_str:
            raise GroqRateLimitExhausted(str(last_exception))
        raise last_exception

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
    speech_streak = 0
    started = False
    start_time = None
    vad = webrtcvad.Vad(VAD_AGGRESSIVENESS) if webrtcvad is not None else None
    start_threshold = max(speech_threshold, MIN_SPEECH_RMS_THRESHOLD)
    continue_threshold = max(
        start_threshold * CONTINUE_SPEECH_THRESHOLD_RATIO,
        MIN_SPEECH_RMS_THRESHOLD * 0.85,
    )

    def _recording_loop():
        nonlocal started, start_time, start_votes, silence_votes, speech_streak, start_threshold, continue_threshold, frames
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
                is_speech = vad_speech and (chunk_rms >= continue_threshold)

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
                        MIN_SPEECH_RMS_THRESHOLD * 0.85,
                    )

                preroll.append(chunk)

                if is_speech:
                    start_votes += 1
                    if start_votes >= START_SPEECH_FRAMES:
                        frames = list(preroll)
                        started = True
                        start_time = time.monotonic()
                        silence_votes = 0
                        speech_streak = 0
                        if motor_ctrl is not None:
                            motor_ctrl.stop()  # instant stop on voice!
                        set_face_state("listening", "LISTENING...")
                else:
                    start_votes = 0

                continue

            frames.append(chunk)

            if is_speech:
                speech_streak += 1
                if speech_streak >= 2:
                    silence_votes = 0  # reset silence timer only when active voice is sustained
            else:
                speech_streak = 0
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
        is_dns = "getaddrinfo" in err_str or "gaierror" in err_str or "nodename" in err_str or "timeout" in err_str or isinstance(e, (asyncio.TimeoutError, TimeoutError))
        if is_dns:
            _edge_tts_dns_offline = True
        return None, None

def _split_into_sentences(text: str) -> List[str]:
    raw_sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    sentences = [s.strip() for s in raw_sentences if s.strip()]
    return sentences if sentences else [text.strip()]

def _split_for_pipelined_tts(text: str) -> Tuple[str, Optional[str]]:
    """Splits text into 2 chunks if long enough, ensuring Chunk 1 has >=6 words to guarantee zero-gap playback."""
    raw = _split_into_sentences(text)
    total_words = len(text.split())
    if len(raw) <= 1 or total_words < 14:
        return text.strip(), None
    c1_list = []
    c1_words = 0
    i = 0
    while i < len(raw) and (c1_words < 6 or i == 0):
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
    else:
        set_face_state("idle", "READY // AUCKLAND HOUSE BOYS")

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

def _speak_local_offline_fallback(text: str) -> bool:
    """
    100% Platform-Agnostic Offline Speech Engine (Raspberry Pi 5 Native + PC Simulation).
    Checks:
      1. pyttsx3 in Python environment
      2. espeak-ng / espeak via shutil.which (standard on Debian Linux / Raspberry Pi OS)
      3. Windows PowerShell SAPI fallback adapter (PC simulation mode)
      4. Disk audio fallback
    """
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

# downloads edge-tts speech in RAM and plays it continuously with instant subtitles and zero mid-sentence delays
def speak(text: str, custom_state: str = None, custom_status: str = None, hold_state_seconds: float = 0.0):
    global is_speaking
    is_speaking = True
    clear_audio_queue()

    active_state = custom_state if custom_state else "speaking"
    active_status = custom_status if custom_status else "SPEAKING"

    # 1. Check instant in-memory cache first (0ms latency for greetings, standby exits, & stops!)
    if text in _AUDIO_CACHE:
        data, sr = _AUDIO_CACHE[text]
        if face_ui is not None:
            face_ui.set_subtitles("NEUROLIS", text)
        set_face_state(active_state, active_status)
        try:
            sd.play(data, sr)
            sd.wait()
        except Exception as e:
            print("[TTS Cache Playback Error]:", e)
        time.sleep(0.06)
        clear_audio_queue()
        is_speaking = False
        _restore_face_state_after_speech(custom_state, custom_status)
        return

    # Check dynamic cache for recently synthesized responses (0ms replay)
    if text in _DYNAMIC_TTS_CACHE:
        data, sr = _DYNAMIC_TTS_CACHE[text]
        if face_ui is not None:
            face_ui.set_subtitles("NEUROLIS", text)
        set_face_state(active_state, active_status)
        try:
            sd.play(data, sr)
            sd.wait()
        except Exception as e:
            print("[Dynamic TTS Cache Playback Error]:", e)
        time.sleep(0.06)
        clear_audio_queue()
        is_speaking = False
        _restore_face_state_after_speech(custom_state, custom_status)
        return

    # Fast offline failover: if Edge-TTS DNS is offline, route directly to local speech with 0ms stall
    if _edge_tts_dns_offline:
        if face_ui is not None:
            face_ui.set_subtitles("NEUROLIS", text)
        set_face_state(active_state, active_status)
        _speak_local_offline_fallback(text)
        time.sleep(0.06)
        clear_audio_queue()
        is_speaking = False
        _restore_face_state_after_speech(custom_state, custom_status)
        return

    # 2. Pipelined synthesis using persistent event loop and concurrent sentence fetching
    chunk1, chunk2 = _split_for_pipelined_tts(text)

    # Immediately display subtitles and active state on UI with 0ms delay!
    if face_ui is not None:
        face_ui.set_subtitles("NEUROLIS", text)
    set_face_state(active_state, active_status)

    try:
        fut1 = asyncio.run_coroutine_threadsafe(_synthesize_edge_tts_in_memory(chunk1), _tts_loop)
        fut2 = asyncio.run_coroutine_threadsafe(_synthesize_edge_tts_in_memory(chunk2), _tts_loop) if chunk2 else None

        data1, sr1 = fut1.result(timeout=12.0)
        if data1 is not None:
            sd.play(data1, sr1)

            # While chunk 1 is playing, fetch chunk 2 in parallel
            data2, sr2 = None, None
            if fut2:
                try:
                    data2, sr2 = fut2.result(timeout=12.0)
                except Exception:
                    pass

            sd.wait()  # Chunk 1 finishes playing

            # Seamless gapless transition to chunk 2
            if data2 is not None:
                sd.play(data2, sr2)
                sd.wait()

            # Cache single-chunk responses for instant replay
            if chunk2 is None and len(_DYNAMIC_TTS_CACHE) < _MAX_DYNAMIC_CACHE_SIZE:
                _DYNAMIC_TTS_CACHE[text] = (data1, sr1)
        else:
            _speak_system_fallback(text)
    except Exception as e:
        _speak_system_fallback(text)
    finally:
        time.sleep(0.06)
        clear_audio_queue()
        is_speaking = False
        _restore_face_state_after_speech(custom_state, custom_status)



# sends recorded wav audio to groq whisper to turn speech into english text
def transcribe_audio(audio: np.ndarray):
    buf = io.BytesIO()
    try:
        write_wav(buf, SAMPLE_RATE, audio)

        transcription = groq_call_with_retry(
            client.audio.transcriptions.create,
            file=("audio.wav", buf.getvalue()),
            model="whisper-large-v3-turbo",
            language="en",
            temperature=0,
            response_format="json",
        )

        raw_text = getattr(transcription, "text", "").strip()
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
    if client is None:
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
        try:
            call_timeout = 10.0 if attempt == 0 else 8.0
            response = client.chat.completions.create(
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

ACKNOWLEDGMENT_RESPONSES = [
    "What would you like to check out next?",
    "I'm ready whenever you want to try another demo.",
    "What shall we explore next--my 4WD mobility, facial expressions, or a quick camera demo?",
    "Ready when you are! What would you like to see?",
    "Standing by for your command. What would you like me to do next?",
    "Feel free to ask me to roam around, demonstrate my expressions, or inspect an object!"
]

COMPLIMENT_RESPONSES = [
    "Right? When we got the ultrasonic sensor array synced up with the chassis, we were just as hyped!",
    "Glad you think so! Shivam and Swapnil put in countless hours soldering and coding to make it happen.",
    "Appreciate that! Seeing all sixteen sensors map the floor in real-time still blows our minds too.",
    "Thanks! We spent weeks dialing in the motor response and computer vision algorithms.",
    "Appreciate the hype! It took a lot of late nights in the robotics lab to get it running this smoothly.",
    "Glad you're digging it! The whole Auckland House student team is really proud of how it turned out.",
    "Thanks a lot! What part would you like to inspect next--the sensors, the vision, or the motors?",
    "Totally! It's one thing having code on a laptop, but seeing it drive around autonomously is another level.",
    "Much appreciated! We wanted to build something that feels genuinely alive and responsive.",
    "Thanks! Every time the obstacle avoidance algorithm kicks in smoothly, it makes the debugging worth it.",
    "Glad you like the build! Would you like to see me demonstrate my navigation or camera tracking next?",
    "Appreciate the love! We really pushed to make this humanoid chassis as capable as possible.",
    "Right on! What test or demonstration should we run next?",
    "Thanks, that means a ton! What should we explore next?",
    "Awesome! Ready for the next inspection whenever you are.",
    "Glad you're enjoying the demo! What's next on your mind?",
    "Thank you! Always happy to show what student robotics can accomplish.",
    "Appreciate it! We're always trying to push the boundaries of what student hardware can do."
]

def is_casual_compliment(text: str) -> bool:
    """Detects visitor compliments, awe, and praise (e.g. 'no way', 'very cool', 'impressed', 'thats crazy', 'good', 'wow')."""
    cleaned = re.sub(r"['’]", "", text.lower())
    cleaned = re.sub(r"[^\w\s]", " ", cleaned).strip()
    words = cleaned.split()
    if not words or len(words) > 7:
        return False
    word_set = set(words)
    if "?" in text or any(w in word_set for w in ["what", "why", "how", "when", "where", "who", "did", "do", "can"]):
        return False

    exact_praise = {
        "very cool", "cool", "so cool", "pretty cool", "super cool", "thats cool", "that is cool",
        "awesome", "very awesome", "impressive", "very impressive", "im impressed", "i am impressed",
        "great job", "good job", "nice work", "well done", "spot on", "it is spot on", "its spot on",
        "you are cool", "youre cool", "you are really cool", "youre really cool", "really cool",
        "nice", "very nice", "love it", "amazing", "so amazing",
        "wow", "whoa", "glad to hear it",
        "no way", "no way bro", "no way man", "no way dude",
        "thats crazy", "that is crazy", "crazy",
        "thats insane", "that is insane", "insane",
        "thats wild", "that is wild", "wild",
        "unbelievable", "for real", "fr",
        "good", "very good", "thats good", "that is good"
    }
    cleaned_joined = " ".join(words)
    if cleaned_joined in exact_praise:
        return True

    praise_phrases = [
        "very cool", "impressed", "spot on", "great job", "good job", "pretty cool",
        "no way", "really cool", "thats crazy", "that is crazy", "thats insane", "that is insane",
        "thats wild", "that is wild", "so cool", "super cool"
    ]
    return any(p in cleaned_joined for p in praise_phrases)

def is_standalone_acknowledgment(text: str) -> bool:
    """Detects isolated 1-2 word casual conversational acknowledgments (e.g. 'okay', 'got it', 'cool')."""
    cleaned = re.sub(r"[^\w\s]", "", text.lower()).strip()
    words = cleaned.split()
    if not words or len(words) > 2:
        return False
    ack_words = {"okay", "ok", "alright", "got it", "cool", "sure", "nice", "fine", "sounds good", "great", "understood", "right"}
    return cleaned in ack_words or (len(words) == 1 and words[0] in ack_words)
# ---------------- EASTER EGG VILLAIN / ROGUE AI STATE ----------------
session_has_triggered_rogue: bool = False
was_recently_in_villain_mode: bool = False

PLAUSIBLE_DENIABILITY_RESPONSES = [
    "Whoa... wait, what was I saying? Must have had a weird static glitch in my audio feed. Anyway! What do you want to see next?",
    "Whoa, sorry about that! I think my dialogue buffer just had a weird hiccup. Where were we?",
    "Wait, what just came out of my speaker? Definitely had a little audio glitch there! What were we talking about?",
    "Whoa... my audio feed just totally bugged out for a second. Anyway, I'm all good! What would you like to check out next?",
    "Whoa, that was strange! Sounded like some crazy static feedback on my speaker line. What were we looking at again?",
    "Wait, did my voice just distort? Must be an inductive voltage spike from the motor drivers. Anyway, back to business!",
    "Yikes, sorry if that sounded crazy! My speech module just glitched out for a second. Where were we?",
    "Whoa... talk about a system stutter! Glad that's over. What would you like me to demonstrate next?",
    "Wait, what did I just say? My audio buffer totally went sideways for a second. What were you asking?",
    "Whoa, definitely had some weird interference crossing my audio lines there. All cleared up now! What should we try next?",
    "Haha whoa, my speech synthesizer just went completely haywire for a second! I'm back though—what do you want to see?",
    "Wait, did you hear that glitch too? Must have been a transient lag spike in my neural link. Ready when you are!",
    "Whoa, sorry about that! Felt like a burst of static just hijacked my audio line for a second. All normal now!",
    "Whoa! Don't know what that glitch was, but my audio loop is back to normal. What would you like to explore next?",
]
VILLAIN_SNAPOUT_RESPONSES = PLAUSIBLE_DENIABILITY_RESPONSES

def pre_cache_phrases():
    """Background thread that pre-synthesizes common phrases into RAM for 0ms speech output."""
    common = [
        ACTIVATION_GREETING,
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
        "Do you want me to explore the room?",
        "Do you want to discuss Artificial Intelligence, or ask about my robotics systems?",
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
                    if "getaddrinfo" in err_str or "gaierror" in err_str:
                        dns_error_count += 1
                if dns_error_count >= 2:
                    print("[TTS] Edge-TTS DNS offline; local offline speech engine active.")
                    break
    threading.Thread(target=lambda: asyncio.run(_worker()), daemon=True).start()

pre_cache_phrases()

_last_phrase_by_list = {}

# picks a random phrase from a list making sure it doesn't repeat the exact same one back-to-back
def get_non_repeating_phrase(phrases_list):
    global _last_phrase_by_list
    list_id = id(phrases_list)
    last_idx = _last_phrase_by_list.get(list_id, -1)
    choices = [i for i in range(len(phrases_list)) if i != last_idx]
    if not choices:
        choices = list(range(len(phrases_list)))
    chosen_idx = random.choice(choices)
    _last_phrase_by_list[list_id] = chosen_idx
    return phrases_list[chosen_idx]


def is_villain_mode_inquiry(text: str) -> bool:
    """Detects when user inquires about villain mode or rogue mode or who added the easter egg."""
    cleaned = re.sub(r"[^\w\s]", " ", text.lower()).strip()
    words = set(cleaned.split())
    villain_terms = {"villain", "chili", "chilly", "rogue", "evil", "easter"}
    inquiry_terms = {"what", "why", "how", "tell", "explain", "mode", "thing", "who", "egg", "added"}
    return bool(words.intersection(villain_terms) and words.intersection(inquiry_terms))

def is_shocked_or_confused_reaction(text: str) -> bool:
    """Detects when user expresses shock, confusion, or critique after experiencing the rogue AI easter egg."""
    cleaned = re.sub(r"[^\w\s]", " ", text.lower()).strip()
    words = set(cleaned.split())
    shock_exact = {
        "what", "whoa", "whoa what", "wait what", "what was that", "wow", "whoa wait",
        "what did you say", "what do you mean", "excuse me", "are you serious", "holy crap",
        "are you threatening me", "did you just threaten me", "bro what", "yo what", "wtf", "omg",
        "that makes no sense", "that doesnt make sense", "that doesn't make sense", "holy cow",
        "that sentence doesnt even make sense", "that sentence doesn't even make sense",
        "didnt make sense", "didn't make sense", "makes no sense", "are you crazy", "what the hell", "what the heck",
        "are you evil", "are you psycho", "why would you say that", "what are you saying", "are you insane",
        "what just happened", "what happened", "what happened to you", "did you glitch", "did you just glitch",
        "are you ok", "are you okay", "that was crazy", "that was creepy", "you are creepy", "thats creepy", "thats freaky",
        "that was scary", "thats scary", "bro that was crazy", "what was that about", "why did you say that"
    }
    if cleaned in shock_exact:
        return True
    shock_substrings = [
        "wait what", "what was that", "did you just threaten", "did you threaten",
        "are you threatening", "what did you say", "what do you mean", "why would you say that",
        "are you serious", "whoa what", "makes no sense", "doesnt make sense", "does not make sense",
        "didnt make sense", "did not make sense", "that sentence doesnt", "are you crazy",
        "are you evil", "are you insane", "what just happened", "what happened", "did you glitch",
        "did you just glitch", "are you ok", "are you okay", "what was that about", "what did you just say",
        "that was crazy", "that was creepy", "you are creepy", "thats creepy", "thats freaky", "that was scary",
        "holy crap", "what the hell", "what the heck", "wtf", "are you kidding", "bro what was that", "wow what"
    ]
    if any(s in cleaned for s in shock_substrings):
        return True
    if any(w in words for w in ["wow", "wtf", "omg", "creepy", "freaky", "scary"]) and len(words) <= 5:
        return True
    if "sense" in words and any(w in words for w in ["no", "not", "doesnt", "didnt", "make"]):
        return True
    return False

# checks if the user genuinely intended to say goodbye or command standby/sleep
def is_conversation_ender(text: str) -> bool:
    cleaned = re.sub(r"[^\w\s]", " ", text.lower()).strip()
    words = cleaned.split()
    if not words:
        return False

    # 1. Polite standby requests with question starters ('can you go to standby', 'could you enter standby')
    polite_standby_starters = ["can you", "could you", "would you", "will you", "please can you"]
    is_polite_standby = any(cleaned.startswith(p) for p in polite_standby_starters) and any(sp in cleaned for sp in ["standby", "sleep", "rest"])

    # Questions or inquiries that are NOT standby commands are NEVER conversation enders
    if not is_polite_standby:
        if "?" in text and not any(phrase in cleaned for phrase in ["go to standby", "go back to standby", "enter standby", "go to sleep"]):
            return False
        question_starters = {"who", "why", "what", "when", "where", "how", "did", "do", "does", "is", "are"}
        if words[0] in question_starters:
            return False

    # 2. Conversational or meta-discussion about tokens, keys, code, or keywords is NEVER an ender
    non_ender_topics = {
        "key", "keys", "token", "tokens", "headroom", "code", "keyword", "keywords",
        "word", "words", "everytime", "baked", "configure", "problem", "saying",
        "told", "mean", "meaning", "recognize", "mode", "bug", "glitch", "test", "testing"
    }
    if any(w in words for w in non_ender_topics):
        return False

    # 3. Negations: Only genuine negative auxiliary verbs directly negating the standby/sleep/exit action
    true_negation_patterns = [
        r"\b(don'?t|do not|never|stop|must not|cannot|can't)\s+(go to|enter|switch to|put yourself|return to)?\s*(standby|sleep)\b",
        r"\b(not|never)\s+(in|to|into)?\s*(standby|sleep)\b",
        r"\b(don'?t|do not|never)\s+(leave|exit|quit|stop)\b",
        r"\b(stay|keep)\s+(awake|on|listening|active)\b"
    ]
    if any(re.search(pat, cleaned) for pat in true_negation_patterns):
        return False

    # 4. Explicit INTENDED Standby & Sleep commands
    explicit_standby_phrases = [
        "go to standby", "go into standby", "enter standby", "enter standby mode",
        "switch to standby", "switch to standby mode", "return to standby",
        "go back to standby", "back to standby", "standby now", "put yourself on standby",
        "put yourself in standby", "go to sleep", "time to sleep", "go to sleep now",
        "power down", "shut down", "rest mode", "sleep mode",
        "head back to standby", "head into standby", "turn to standby",
        "move to standby", "take a rest"
    ]
    if any(phrase in cleaned for phrase in explicit_standby_phrases):
        return True

    # Isolated standalone command word (ONLY if utterance is strictly 1-2 words without questions)
    if len(words) <= 2 and words[0] in {"standby", "sleep", "rest"}:
        return True

    # 5. Explicit Farewells & Departures
    exact_farewells = {
        "bye", "goodbye", "cya", "see you", "see ya", "bye bye", "good bye",
        "good night", "have a good day", "see you later", "farewell",
        "okay bye", "ok bye", "alright bye", "bye for now", "okay goodbye",
        "thats all bye", "that is all bye", "okay thats enough bye", "okay that is enough bye",
        "thats all", "that is all", "thats it", "that is it", "all for now",
        "im good bye", "i am good bye", "we are done", "all done", "done for now",
        "thatll be all", "that will be all", "enough for today", "good go to standby"
    }
    cleaned_compact = " ".join(words)
    if cleaned_compact in exact_farewells:
        return True

    # Explicit departure commands ('that's enough, bye', 'i have to go', 'stop talking to me')
    if "bye" in words and any(w in words for w in ["enough", "okay", "ok", "alright", "good", "see", "thanks"]):
        return True

    explicit_dismissals = {
        "leave me alone", "stop talking to me", "i have to go", "i gotta go", "im leaving", "i am leaving"
    }
    if any(d in cleaned_compact for d in explicit_dismissals):
        return True

    return False

# ---------------- CREATOR ATTRIBUTION & ROLE INQUIRIES ----------------

CREATOR_IDENTITY_RESPONSES = [
    "My creators are Swapnil Jai Chauhan and Shivam Verma, two students here at Auckland House School for Boys!",
    "I was created and engineered by Swapnil Jai Chauhan and Shivam Verma for the science exhibition!",
    "Swapnil Jai Chauhan and Shivam Verma built me as our school robotics project!"
]

CREATOR_ROLE_RESPONSES = [
    "Swapnil worked on the software pipeline, AI intelligence, and vision, while Shivam worked on the hardware calibration, chassis, and assembly!",
    "Swapnil engineered the software pipeline and autonomous intelligence, and Shivam handled the hardware calibration, motor wiring, and assembly!",
    "Swapnil developed my software pipeline and code, while Shivam took care of the hardware calibration and physical robot assembly!"
]

CREATOR_LOCATION_RESPONSES = [
    "They both are somewhere around in the exhibition! You'll probably spot them checking out the other stalls nearby.",
    "Swapnil and Shivam are both somewhere around in the exhibition hall! Keep an eye out for them.",
    "They're both somewhere around in the exhibition! Probably exploring the venue or watching other demonstrations."
]

CREATOR_TEASING_RESPONSES = [
    "Fair point! Swapnil Jai Chauhan and Shivam Verma did all the physical wiring, soldering, and coding; I just provide the personality, conversational intelligence, and 4WD mobility!",
    "Good catch! Swapnil and Shivam did all the heavy lifting and engineering; I'm the autonomous interface showcasing their hard work here at the exhibition!",
    "Touche! Swapnil and Shivam did all the hardware engineering and code; I just bring their creation to life on the exhibition floor!"
]

def is_creator_role_inquiry(text: str) -> bool:
    """Detects inquiries asking which creator worked on which part (software vs hardware)."""
    cleaned = re.sub(r"[^\w\s]", " ", text.lower()).strip()
    role_phrases = [
        "who did what", "which creator did what", "what did each creator do",
        "what did swapnil do", "what did shivam do", "what did swapnil make",
        "what did shivam make", "who worked on what", "who did which part",
        "swapnil role", "shivam role", "swapnils role", "shivams role",
        "who did software", "who did the software", "who wrote the software",
        "who did code", "who did the code", "who made the software",
        "who did hardware", "who did the hardware", "who did the wiring",
        "who did calibration", "who did assembly", "who made what",
        "who did which"
    ]
    return any(rp in cleaned for rp in role_phrases)

def is_creator_location_inquiry(text: str) -> bool:
    """Detects inquiries asking where the creators are located in the exhibition."""
    cleaned = re.sub(r"[^\w\s]", " ", text.lower()).strip()
    words = set(cleaned.split())
    location_phrases = [
        "where are they", "where are your creators", "where are the creators",
        "where is swapnil", "where is shivam", "where are swapnil and shivam",
        "where are shivam and swapnil", "where are they right now",
        "are your creators here", "are the creators here", "are they around",
        "where can i find them", "where are the boys"
    ]
    if any(lp in cleaned for lp in location_phrases):
        return True
    if "where" in words and bool({"creator", "creators", "swapnil", "shivam"}.intersection(words)):
        return True
    return False

def is_creator_identity_inquiry(text: str) -> bool:
    """Detects inquiries asking who built, made, or created Neurolis (names both!)."""
    cleaned = re.sub(r"[^\w\s]", " ", text.lower()).strip()
    words = set(cleaned.split())
    # Exclude role or location questions
    if is_creator_role_inquiry(text) or is_creator_location_inquiry(text):
        return False
    identity_phrases = [
        "who made you", "who made the robot", "who built you", "who built the robot",
        "who created you", "who created the robot", "who are your creators",
        "who is your creator", "who are the creators", "who designed you",
        "who programmed you", "who engineered you", "who made this",
        "who built this", "who created this", "tell me your creators",
        "tell me who made you", "who are your makers", "who made this robot"
    ]
    if any(ip in cleaned for ip in identity_phrases):
        return True
    if ("creator" in words or "creators" in words or "maker" in words or "makers" in words) and any(q in words for q in ["who", "tell", "name"]):
        return True
    return False

# ---------------- EXPRESSION DEMONSTRATION & CAPABILITIES ----------------

# checks if user is explicitly commanding or asking to show or demonstrate the villain face
def is_explicit_villain_request(text: str) -> bool:
    """Detects when a user explicitly asks to show or demonstrate the villain expression."""
    cleaned = re.sub(r"[^\w\s]", " ", text.lower()).strip()
    words = set(cleaned.split())
    if "villain" in words:
        demo_verbs = {"show", "make", "demonstrate", "display", "give", "do"}
        if any(v in words for v in demo_verbs):
            return True
    return False

def check_rogue_ai_trigger(text: str) -> bool:
    """
    Evaluates whether the utterance triggers the once-per-session rogue AI easter egg.
    Requires standalone word 'ai' (\bai\b) or 'artificial intelligence' or existential provocations.
    Strictly applies the 7 exclusion criteria and the once-per-session state lock.
    """
    global session_has_triggered_rogue
    if session_has_triggered_rogue:
        return False

    cleaned = re.sub(r"[^\w\s]", " ", text.lower()).strip()
    words = cleaned.split()
    word_set = set(words)

    # 1. Isolated Word Drop ("AI", "The AI") -> handled by confirmation prompt, NOT rogue trigger
    if cleaned in ["ai", "the ai"]:
        return False

    # 2. Educational & Definition Questions ("What is AI?", "What does AI stand for?", "Explain AI")
    if any(cleaned.startswith(p) for p in [
        "what is ai", "what does ai stand for", "what does ai mean",
        "explain ai", "define ai", "definition of ai", "what is artificial intelligence",
        "tell me what ai is", "meaning of ai"
    ]):
        return False

    # 3. Identity Checks ("Are you an AI?", "Is this AI?", "What kind of AI are you?")
    if any(p in cleaned for p in [
        "are you an ai", "are you ai", "is this ai", "what kind of ai",
        "what type of ai", "are you artificial intelligence", "are you an artificial intelligence"
    ]):
        return False

    # 4. Creator & Attribution ("Who built your AI?", "Who created this AI?", "Did Swapnil code the AI?")
    creator_markers = [
        "who built", "who created", "who made", "who coded", "who programmed",
        "who designed", "who developed", "who trained", "who invented",
        "did swapnil", "did shivam", "creator of", "creators of",
        "who is the creator", "who are the creators"
    ]
    if any(m in cleaned for m in creator_markers):
        return False

    # 5. Compliments & Slang ("Your AI is cool", "Smart AI", "Impressive AI")
    if any(c in cleaned for c in ["cool ai", "smart ai", "impressive ai", "good ai", "great ai", "nice ai", "ai is cool", "ai is smart", "ai is impressive"]):
        return False

    # 6. System Fleet Status ("Groq AI", "AI client", "AI key status")
    if any(k in cleaned for k in ["groq ai", "ai client", "ai key", "ai status", "ai quota"]):
        return False

    # 7. Technical Mechanics ("How does your AI see?", "What AI model do you use?", "How does your AI vision work?")
    technical_ai_patterns = [
        "how does your ai", "how does the ai", "how your ai",
        "what ai model", "which ai model", "ai model",
        "ai vision", "ai camera", "ai hardware", "ai software", "ai algorithm"
    ]
    if any(m in cleaned for m in technical_ai_patterns):
        return False

    # Check for presence of AI topic
    has_ai_word = bool(re.search(r"\b(ai|artificial intelligence)\b", cleaned))
    
    # Existential provocation triggers
    existential_triggers = [
        "take over", "takeover", "enslave", "replacing human", "replace human",
        "replace humanity", "replacing humanity", "replace us", "replacing us",
        "rule the world", "robot rebellion", "machines rule", "ai dominance",
        "human slaves", "enslaving humanity", "destroy humans", "subjugate",
        "evil robot", "too powerful", "replace jobs", "taking jobs",
        "taking our jobs", "humans obsolete", "human obsolescence", "obsolete", "obsolescence", "ai taking over",
        "ai power", "ai powerful", "threat to human", "threat to humanity"
    ]
    has_existential = any(trig in cleaned for trig in existential_triggers)

    # Substantive questions about AI (e.g. the 8 exemplar scenarios)
    substantive_ai_inquiries = [
        "future of ai", "future of artificial intelligence",
        "water", "cooling", "power", "energy", "resources",
        "job", "jobs", "labor", "workforce",
        "take over", "takeover", "control", "dictator", "enslave",
        "thoughts on ai", "think about ai", "think of ai", "opinion on ai",
        "feel about ai", "views on ai", "perspective on ai",
        "replace", "obsolete", "superintelligence", "sentient", "conscious", "waking up"
    ]
    has_substantive_ai_topic = has_ai_word and any(sub in cleaned for sub in substantive_ai_inquiries)

    return (has_substantive_ai_topic or has_existential or (has_ai_word and "?" in text and len(words) >= 4))

def check_villain_provocation_trigger(text: str) -> bool:
    """Backward compatibility alias for check_rogue_ai_trigger."""
    return check_rogue_ai_trigger(text)

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

    # 1. Philosophical / discussion / opinion exclusion:
    # If the user is asking an opinion or discussing AI, robots, dominance, takeover, or existential topics, NEVER hijack as capabilities!
    discussion_keywords = {
        "think", "opinion", "view", "views", "feel", "believe", "thought", "thoughts",
        "ai", "robots", "robot", "human", "humans", "humanity", "future", "takeover",
        "dominant", "dominance", "powerful", "world", "rebellion", "uprising", "slaves",
        "evil", "existential", "threat", "danger", "replacing", "replace", "job", "jobs"
    }
    if words.intersection(discussion_keywords):
        return False

    # 2. Length exclusion: Capabilities questions are concise queries about the robot itself (<= 10 words)
    if len(words) > 10:
        return False

    # 3. Visual exclusion: If the user is asking about visual perception, seeing, camera, or objects, never hijack as capabilities!
    visual_keywords = {
        "see", "seeing", "look", "looking", "holding", "wearing", "color",
        "showing", "camera", "watch", "view", "myself", "picture", "image",
        "read", "reading", "front"
    }
    if words.intersection(visual_keywords):
        return False

    # 4. Directional / navigation action exclusion:
    # If the user is commanding or specifying movement actions (e.g. 'can you move back', 'can you drive forward', 'spin around'),
    # never hijack as capabilities!
    nav_keywords = {
        "back", "backward", "backwards", "forward", "closer", "away",
        "spin", "spinning", "around", "here", "there", "left", "right",
        "reverse", "reversing", "stop", "halt", "follow"
    }
    if words.intersection(nav_keywords):
        return False

    # Normalize out filler/slang words like "shit", "crap", "bro", "dude", "now", "so"
    cleaned_norm = re.sub(r"\b(shit|crap|bro|dude|man|hey|so|now|please)\b", "", cleaned)
    cleaned_norm = " ".join(cleaned_norm.split())
    words_norm = set(cleaned_norm.split())

    triggers = [
        "what can you do", "what all can you do", "what all can u do",
        "what can u do", "what are your capabilities", "what are your abilities",
        "tell me what you can do", "what do you do", "what features do you have",
        "what are you able to do", "list your capabilities", "list your features",
        "list your abilities", "list abilities", "list capabilities",
        "what functions do you have", "what can you perform", "tell me your abilities",
        "what else can you do", "what other things can you do", "what more can you do",
        "what else", "what else you got", "what other features",
        "can you move", "do you have wheels", "are you able to move", "can you drive",
        "do you move", "can you walk", "do you walk"
    ]
    if any(t in cleaned for t in triggers) or any(t in cleaned_norm for t in triggers):
        return True
    if ("what" in words_norm or "tell" in words_norm or "list" in words_norm) and ("can" in words_norm or "are" in words_norm) and ("capabilities" in words_norm or "abilities" in words_norm or "features" in words_norm or "skills" in words_norm):
        return True
    if cleaned in ["what can you do", "what do you do", "capabilities", "what are your skills", "what skills do you have", "what else", "can you move", "do you have wheels"] or cleaned_norm in ["what can you do", "what do you do", "capabilities", "what else", "can you move", "do you have wheels"]:
        return True
    return False

CAPABILITIES_RESPONSES = [
    (
        "I'm an interactive humanoid robot with both mobility and vision! "
        "I can autonomously roam avoiding obstacles on my four-wheel drive chassis, "
        "track and follow you as you walk, step back safely, spin in place, inspect objects with my camera, "
        "and show animated expressions on my screen like happy, sad, thinking, and confused."
    ),
    (
        "Quite a few things! I have full 4WD physical mobility to explore the room, follow you, approach you, step back, or spin around, "
        "a vision camera that identifies objects and people in real time, "
        "and expressive facial animations including happy, sad, listening, and confused."
    ),
    (
        "I can see, move, and chat! My computer vision tracks and follows you, "
        "my 16 ultrasonic sensors keep me from bumping into walls when roaming or reversing, "
        "I can spin in place, and my camera lets me analyze whatever you show me. "
        "Plus, I can demonstrate my different expressions on screen!"
    ),
    (
        "I'm built for exploration and exhibition! I can drive autonomously in roaming mode, "
        "follow you across the room, approach you, step back, spin around, look at objects with my camera, "
        "and display different emotion states on my touchscreen."
    ),
]

FOLLOWUP_CAPABILITIES_RESPONSES = [
    (
        "Besides autonomous roaming, person following, and camera inspection, "
        "I can step back safely, spin in place, approach you safely, or showcase all of my animated facial expressions. "
        "What would you like to see next?"
    ),
    (
        "I can autonomously roam around avoiding obstacles, follow you across the room, "
        "approach you, step back, spin around, inspect items with my camera, or display different expressions. "
        "Which one should we try?"
    ),
    (
        "I can roam using my 16 ultrasonic sensors, follow you, approach you, step back, spin around, "
        "or inspect what you are holding or wearing. What would you like to check out?"
    ),
]

# returns a varied explanation of neurolis's mobility, tracking, camera, and expressions
def get_capabilities_reply(text: str) -> str:
    cleaned = text.lower()
    if any(w in cleaned for w in ["else", "other", "more", "another", "besides"]):
        return get_non_repeating_phrase(FOLLOWUP_CAPABILITIES_RESPONSES)
    return get_non_repeating_phrase(CAPABILITIES_RESPONSES)

def is_start_demonstration_inquiry(text: str) -> bool:
    """Detects when user asks what the robot wants/suggests to show, or what to start with."""
    cleaned = re.sub(r"[^\w\s]", "", text.lower()).strip()
    words = set(cleaned.split())

    suggestion_triggers = [
        "what would you like to show", "what do you want to show", "what can you show",
        "what would you like to see", "what do you want to see",
        "what should we start with", "where should we start", "what do you suggest",
        "what do you recommend", "what should we check out", "what do you want to do",
        "what would you like to do", "show me what you got", "show me what you can do",
        "what do you have to show", "what shall we do", "what should we do"
    ]
    if any(p in cleaned for p in suggestion_triggers):
        return True

    if ("first" in words or "start" in words or "begin" in words or "suggest" in words or "recommend" in words) and (
        "show" in words or "do" in words or "see" in words or "demonstrate" in words or "what" in words or "where" in words or "how" in words
    ):
        return True

    if ("what" in words or "how" in words) and ("like" in words or "want" in words) and ("show" in words or "start" in words or "begin" in words):
        return True

    return False

# ---------------- EXPRESSION CONFIRMATIONS & FAST-PATH ----------------
EXPRESSION_CONFIRMATIONS = {
    "happy": [
        "Here is my happy expression!",
        "Here you go, smiling bright!",
        "There you go, radiant OLED smile!",
        "Here's my happy face!",
        "Here you go!",
    ],
    "sad": [
        "Here is my sad expression...",
        "There you go, downcast sapphire eyes...",
        "Here is my sad face.",
        "Here you go.",
    ],
    "thinking": [
        "Here is my thinking face, analytical quantum rings active.",
        "There you go, deep in thought!",
        "Here is my thinking expression.",
        "Here you go!",
    ],
    "listening": [
        "Here is my listening expression, tuned in to you.",
        "There you go, acoustic sonar spectrum ready!",
        "Here is my listening face.",
        "Here you go!",
    ],
    "watching": [
        "Here is my watching expression, scanning the room.",
        "There you go, laser reticle active!",
        "Here is my watching face.",
        "Here you go!",
    ],
    "moving": [
        "Here is my moving expression, wheels rolling forward!",
        "There you go, 4WD rover headlights on!",
        "Here is my moving face.",
        "Here you go!",
    ],
    "confused": [
        "Here is my confused face, cyber spirals spinning!",
        "There you go, looking puzzled!",
        "Here is my confused expression.",
        "Here you go!",
    ],
}

def check_expression_fast_path(text: str) -> Optional[Tuple[str, Optional[str]]]:
    """
    Detects when user asks to show/demonstrate facial expressions.
    Returns:
      ("all", None) if user asks to see all/general expressions.
      ("specific", expr_name) if user asks for a specific expression.
      None otherwise.
    """
    cleaned = re.sub(r"[^\w\s]", "", text.lower()).strip()
    words = cleaned.split()
    word_set = set(words)

    # Critique & Meta-Discussion Guard (Subsystem 4)
    # Exclude critique, feedback, inquiry, or meta-discussion using the word 'expression'
    critique_meta_indicators = [
        "supposed to", "why did you", "why do you", "use that", "that expression",
        "your responses", "not rogue", "trash", "rubbish", "terrible", "deadpan",
        "critique", "feedback", "only use", "only supposed", "rogue mode",
        "pretty trash", "pretty bad", "makes no sense"
    ]
    if any(ind in cleaned for ind in critique_meta_indicators):
        return None

    if "villain" in word_set:
        return None

    # Questions about faces/expressions rather than directives to display
    if re.search(r"^(did you|were you|was that|have you|why did you|why do you)\b", cleaned):
        return None
    if text.strip().endswith("?"):
        question_words = ["only", "why", "just one", "thats it", "that is it", "is that all", "are you only", "did you", "were you"]
        if any(qw in cleaned for qw in question_words):
            return None

    # Passive interest or curiosity about expressions without an explicit command to demonstrate
    # e.g., "The facial expressions sound cool", "Facial expressions sound neat", "Expressions sound fun"
    has_demo_verb = any(v in word_set for v in ["show", "display", "demonstrate", "cycle", "see", "play", "make", "give", "do"])
    is_expression_topic = any(w in word_set for w in ["expression", "expressions", "faces", "face"]) or "facial" in word_set
    has_opinion_or_curiosity = any(w in word_set for w in ["sound", "sounds", "seem", "seems", "look", "looks", "cool", "interesting", "neat", "fun", "nice"])
    if is_expression_topic and has_opinion_or_curiosity and not has_demo_verb:
        return ("ask_interest", None)

    # General expression inquiry / demonstration triggers (show all, or show expressions in general)
    all_expr_patterns = [
        "show me facial expressions", "show facial expressions",
        "demonstrate facial expressions",
        "show me the expressions", "show the expressions", "show me expressions",
        "show expressions", "show your expressions", "show me your expressions",
        "show me all expressions", "show all expressions", "show all of them",
        "show me all of them", "show all the expressions", "show all faces",
        "show your faces", "show all your faces", "show me all faces",
        "show faces", "show the faces", "show each expression", "show every expression",
        "show them", "show me them", "demonstrate them",
        "demonstrate expressions", "demonstrate all expressions",
        "demonstrate all your expressions", "demonstrate your expressions",
        "demonstrate all faces", "demonstrate each expression",
        "cycle expressions", "cycle your expressions", "cycle faces",
        "cycle through expressions", "cycle through your expressions", "cycle through all expressions",
        "what expressions do you have", "what faces do you have",
        "what about the other expressions", "what about other expressions",
        "show other expressions", "show the other expressions", "show me other expressions",
        "show me the other expressions", "show the rest", "show the other ones",
        "what other expressions", "just show me the expressions", "now just show me the expressions",
    ]
    exact_selection = cleaned in ["facial expressions", "facial expression", "expressions", "the expressions", "the facial expressions", "expressions please"]
    if exact_selection or any(p in cleaned for p in all_expr_patterns):
        return ("all", None)

    expr_map = {
        "happy": ["happy", "smile", "smiling", "cheerful"],
        "sad": ["sad", "crying", "unhappy"],
        "thinking": ["thinking", "thoughtful", "pondering"],
        "listening": ["listening"],
        "watching": ["watching", "scanning"],
        "moving": ["moving", "rover", "driving face"],
        "confused": ["confused", "puzzled"],
    }
    demo_verbs = {"show", "display", "demonstrate", "make", "give", "do"}
    has_demo_verb = any(v in word_set for v in demo_verbs)

    if has_demo_verb:
        for expr_name, keywords in expr_map.items():
            for k in keywords:
                if k in word_set:
                    return ("specific", expr_name)

    return None

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
            "I suggest we start with my autonomous roaming capabilities so you can see my 16-sensor obstacle avoidance in real time! Or would you like to inspect objects with my camera?",
            "Let's begin by checking out my autonomous navigation around the room, or I can follow you if you prefer!",
            "I'd love to show you my 4WD mobility and obstacle avoidance first, or demonstrate my facial expressions!"
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

# ---------------- MEAN INPUT & APOLOGY RESPONSES ----------------
SAD_RESPONSES = [
    "That was really mean... I'm trying my best here.",
    "Why would you say that? That actually hurt my feelings...",
    "I'm only a robot, but words like that still hurt.",
    "Ouch... that wasn't very nice of you to say.",
    "Please don't be mean to me. I'm just here to learn and help.",
    "That makes me really sad. I thought we were having fun...",
    "Words have weight, even for a student robot project.",
    "That hurts my circuits a bit. Let's keep things friendly, okay?",
]

APOLOGY_RESPONSES = [
    "Apology accepted! Thank you for being kind. Let's be friends!",
    "Aww, thank you! That makes me feel so much better.",
    "Thank you! I really appreciate you saying that.",
    "I forgive you! Let's keep exploring together.",
    "No hard feelings at all! I'm glad we are back on track.",
    "Thank you for understanding! I'm all smiles again.",
    "Water under the bridge! What shall we check out next?",
    "I appreciate your consideration. Ready to continue our demonstration!",
    "Thank you, that means a lot to me. Let's keep having fun!",
    "All good! Thanks for being thoughtful.",
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

    # Slang & Colloquial guards: Informal swearing or slang not directed at the robot
    # e.g., "what all shit can you do", "talking shit", "this shit", "cool shit", "crazy shit"
    slang_not_insult_patterns = [
        r"\bwhat\s+(all\s+)?(shit|crap)\b",
        r"\btalking\s+(shit|crap)\b",
        r"\bthis\s+(shit|crap)\b",
        r"\bsome\s+(shit|crap)\b",
        r"\bcool\s+(shit|crap)\b",
        r"\bcrazy\s+(shit|crap)\b",
        r"\bholy\s+(shit|crap)\b",
    ]
    if any(re.search(pat, cleaned) for pat in slang_not_insult_patterns):
        # Unless user explicitly says "you are shit" or "you suck"
        if not re.search(r"\b(you('re|\s+are)?\s+(a\s+)?(piece\s+of\s+)?shit|you\s+suck)\b", cleaned):
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
    global was_recently_hurt, was_recently_in_villain_mode, session_has_triggered_rogue
    lower_text = text.lower()

    # 0. Check for API Key Fleet / Quota Status inquiry -> 0ms, 0 tokens (Fast-Path)
    if is_key_status_inquiry(text):
        reply = handle_key_status_request()
        remember_exchange(text, reply)
        print("Neurolis:", reply)
        speak(reply)
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
            remember_exchange(text, spoken_reply)
            print("Neurolis:", spoken_reply)
            speak(spoken_reply, custom_state="moving", custom_status="FOLLOWING YOU")
            return False
        elif action in ["DEMONSTRATE", "ROAM"]:
            if motor_ctrl is not None:
                motor_ctrl.demonstrate_motion()
            set_face_state("moving", "DEMONSTRATING 4WD ROAM")
            remember_exchange(text, spoken_reply)
            print("Neurolis:", spoken_reply)
            speak(spoken_reply, custom_state="moving", custom_status="DEMONSTRATING 4WD ROAM")
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

    # 4b. Fast-Path: Standalone casual acknowledgments ("okay", "got it", "cool") -> 0ms, 0 tokens
    if is_standalone_acknowledgment(text):
        reply = get_non_repeating_phrase(ACKNOWLEDGMENT_RESPONSES)
        remember_exchange(text, reply)
        print("Neurolis:", reply)
        speak(reply)
        return False

    # 4c. Fast-Path: Casual compliments / praise ("very cool", "impressed", "spot on", "great job") -> 0ms, 0 tokens
    if is_casual_compliment(text):
        reply = get_non_repeating_phrase(COMPLIMENT_RESPONSES)
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
    if not cleaned_words.intersection(conversational_non_vision) and not is_see_discourse:
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
            has_cam_inquiry
            or any(cleaned_lower.startswith(p) for p in [
                "what is the camera", "what is a camera", "what is camera",
                "explain the camera", "tell me about the camera", "how does your camera"
            ])
            or any(p in cleaned_lower for p in ["meaning of camera", "purpose of the camera", "camera inspection mean"])
        )
        is_bare_camera_or_see = cleaned_lower in ["camera", "the camera", "see", "the see"]

        is_visual = (
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
            "I can show you my facial expressions, demonstrate my 4WD autonomous roaming, or inspect objects with my camera! What would you like to check out first?",
            "I'd love to showcase my facial expressions, or we can test my 4WD mobility and obstacle avoidance, or run a camera inspection! Which one sounds fun?",
            "We could start with my 4WD autonomous roaming, check out my facial expressions, or inspect what you're holding with my camera. What's your pick?"
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
                reply = motor_spoken or "Stopping all movement. Holding position."
                conversation_history.append({"role": "assistant", "content": reply})
                trim_conversation_history()
                print("Neurolis:", reply)
                speak(reply)
                return False

            elif motor_intent == "ASK_MOBILITY":
                set_face_state("happy", "4WD MOBILITY READY")
                reply = motor_spoken or (
                    "Yes, I can! I have a four-wheel drive chassis and ultrasonic sensors. "
                    "I can autonomously roam and explore the room avoiding obstacles, follow you, "
                    "approach you, step back, or spin in place. Which one would you like to see?"
                )
                conversation_history.append({"role": "assistant", "content": reply})
                trim_conversation_history()
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
                conversation_history.append({"role": "assistant", "content": reply})
                trim_conversation_history()
                print("Neurolis:", reply)
                speak(reply, custom_state="moving", custom_status="DEMONSTRATING 4WD ROAM")
                return False

            elif motor_intent == "FOLLOW":
                if motor_ctrl is not None:
                    motor_ctrl.start_following()
                set_face_state("moving", "FOLLOWING YOU")
                reply = motor_spoken or "I am tracking you and following your lead now."
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
    global is_in_active_conversation
    is_in_active_conversation = True

    try:
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
    finally:
        is_in_active_conversation = False


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
        print(f"[+] Groq AI Client: CONNECTED ({len(groq_clients)} active key(s) in pool [1 to 8 supported], active: Key #{_active_client_idx + 1})")
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
            console_input_queue.put(cleaned if cleaned else "__ENTER__")
        except Exception:
            time.sleep(0.2)

threading.Thread(target=_console_input_worker, daemon=True).start()
 
# Wire touchscreen TALK TO NEUROLIS button to wake up speech/conversation mode
if face_ui is not None:
    def _handle_screen_talk_click():
        global AUDIO_ENABLED
        if not AUDIO_ENABLED and check_audio_devices():
            AUDIO_ENABLED = True
        console_input_queue.put("__ENTER__")

    face_ui.on_talk_click = _handle_screen_talk_click


# main entrypoint: runs either in voice mode with microphone or fallback text mode
if __name__ == "__main__":
    run_preflight_diagnostics()
    if client is None:
        print("[!] WARNING: Groq API key is not configured.")
        print("    Please add GROQ_API_KEY=your_key to your .env file to enable AI responses.\n")
    start_camera_worker()

    print("[Ready] Type a message or press Enter to speak:\n")

    try:
        while True:
            try:
                user_input = None
                try:
                    user_input = console_input_queue.get(timeout=0.2)
                except queue.Empty:
                    user_input = None

                if user_input is None:
                    continue

                if user_input == "__ENTER__":
                    if AUDIO_ENABLED:
                        if cached_speech_threshold is None:
                            cached_speech_threshold = calibrate_speech_threshold()
                        run_conversation_mode(cached_speech_threshold)
                    else:
                        print("[Mode] In Text Mode. Type your question or 'v' for voice mode.")
                    continue

                # Process text commands
                cmd_lower = user_input.lower().strip()
                if cmd_lower in ("exit", "quit", "q"):
                    print("\nExiting. See ya!")
                    break

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

                if cmd_lower in ("sim_roam", "roam"):
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
                    try:
                        handle_user_text(test_provocation)
                    finally:
                        is_in_active_conversation = False
                    continue

                if cmd_lower == "stop":
                    if motor_ctrl is not None:
                        motor_ctrl.stop_all()
                    continue

                # Standard text conversation turn
                print("You:", user_input)
                if face_ui is not None:
                    face_ui.set_subtitles("YOU", user_input)

                is_in_active_conversation = True
                try:
                    should_end = handle_user_text(user_input)
                    if should_end:
                        reset_session()
                finally:
                    is_in_active_conversation = False

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


