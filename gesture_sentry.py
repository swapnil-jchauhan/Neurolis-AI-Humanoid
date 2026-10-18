"""
Project Neurolis - Vision Gesture Sentry Engine (gesture_sentry.py)
Autonomous hands-free Human-Robot Interaction (HRI) via Google MediaPipe Tasks.

Architecture:
- Recognizes ✋ Open Palm and ✊ Closed Fist gestures via MediaPipe GestureRecognizer.
- Hybrid detection: uses neural classifier and landmark geometry (fingertip-to-wrist distance).
- State Isolation:
  * In STANDBY: Only Open Palm held continuously for 3.0s wakes the robot. Fist is ignored.
  * In ACTIVE: Only Closed Fist held continuously for 3.0s triggers standby kill switch. Palm is ignored.
- Exposes real-time feedback (gesture_name, hold_progress_0_to_1) for screen UI progress HUD.
"""

import os
import time
import math
import threading
import sys
import contextlib
from pathlib import Path
from typing import Callable, Optional, Tuple

import numpy as np
import cv2

@contextlib.contextmanager
def _suppress_c_stderr():
    """Suppresses abseil/TensorFlow C++ stderr logging during MediaPipe initialization."""
    try:
        null_fd = os.open(os.devnull, os.O_RDWR)
        old_stderr = os.dup(2)
        os.dup2(null_fd, 2)
        try:
            yield
        finally:
            os.dup2(old_stderr, 2)
            os.close(null_fd)
            os.close(old_stderr)
    except Exception:
        yield

try:
    import mediapipe as mp
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision as mp_vision
    MEDIAPIPE_AVAILABLE = True
except ImportError:
    MEDIAPIPE_AVAILABLE = False
    mp = None
    mp_python = None
    mp_vision = None


def count_extended_fingers(landmarks) -> int:
    """
    Computes count of extended non-thumb fingers (index, middle, ring, pinky)
    by comparing fingertip distance to wrist vs PIP knuckle distance to wrist.
    """
    if not landmarks or len(landmarks) < 21:
        return 0

    wrist = landmarks[0]
    finger_tips = [8, 12, 16, 20]   # Index, Middle, Ring, Pinky
    finger_pips = [6, 10, 14, 18]   # PIP joints

    extended_count = 0
    for tip_idx, pip_idx in zip(finger_tips, finger_pips):
        tip = landmarks[tip_idx]
        pip = landmarks[pip_idx]
        d_tip = math.hypot(tip.x - wrist.x, tip.y - wrist.y)
        d_pip = math.hypot(pip.x - wrist.x, pip.y - wrist.y)
        if d_tip > d_pip * 1.10:
            extended_count += 1

    return extended_count


def analyze_hand_geometry(landmarks) -> Tuple[int, int, bool, bool]:
    """
    Analyzes hand landmarks geometry with knuckle-curl verification for lighting invariance.
    Returns: (extended_fingers_count, curled_fingers_count, is_palm_geometry, is_fist_geometry)
    """
    if not landmarks or len(landmarks) < 21:
        return 0, 0, False, False

    wrist = landmarks[0]
    finger_tips = [8, 12, 16, 20]   # Index, Middle, Ring, Pinky
    finger_pips = [6, 10, 14, 18]   # PIP joints
    finger_mcps = [5, 9, 13, 17]   # MCP knuckles

    extended = 0
    curled = 0

    for tip_idx, pip_idx, mcp_idx in zip(finger_tips, finger_pips, finger_mcps):
        tip = landmarks[tip_idx]
        pip = landmarks[pip_idx]
        mcp = landmarks[mcp_idx]

        d_tip_wrist = math.hypot(tip.x - wrist.x, tip.y - wrist.y)
        d_pip_wrist = math.hypot(pip.x - wrist.x, pip.y - wrist.y)
        d_mcp_wrist = math.hypot(mcp.x - wrist.x, mcp.y - wrist.y)
        d_tip_mcp = math.hypot(tip.x - mcp.x, tip.y - mcp.y)

        # Extended finger: fingertip extends distinctly beyond PIP joint
        if d_tip_wrist > d_pip_wrist * 1.12:
            extended += 1

        # Curled finger: fingertip is tucked near MCP base or closer to wrist than PIP
        if d_tip_mcp < d_mcp_wrist * 0.70 or d_tip_wrist < d_pip_wrist * 1.02:
            curled += 1

    # Fist geometry: at least 3 of 4 fingers curled inward, at most 1 extended
    is_fist_geom = (curled >= 3 and extended <= 1)

    # Palm geometry: all 4 fingers extended, zero fingers curled inward
    is_palm_geom = (extended >= 4 and curled == 0)

    return extended, curled, is_palm_geom, is_fist_geom


class GestureSentry:
    """
    High-performance background vision thread analyzing camera frames for 
    continuous 3.0-second Open Palm (wake) and Closed Fist (standby) gestures.
    """

    def __init__(
        self,
        model_path: Optional[str] = None,
        hold_duration: float = 3.0,
        on_palm_wake: Optional[Callable[[], None]] = None,
        on_fist_standby: Optional[Callable[[], None]] = None,
        get_frame_fn: Optional[Callable[[], Optional[cv2.Mat]]] = None,
        is_standby_fn: Optional[Callable[[], bool]] = None,
    ):
        self.hold_duration = float(hold_duration)
        self.on_palm_wake = on_palm_wake
        self.on_fist_standby = on_fist_standby
        self.get_frame_fn = get_frame_fn
        self.is_standby_fn = is_standby_fn or (lambda: True)

        if model_path is None:
            base_dir = Path(__file__).resolve().parent
            model_path = str(base_dir / "gesture_recognizer.task")
        self.model_path = model_path

        self.recognizer = None
        self._init_recognizer()

        # Threading and control
        self.running = False
        self._thread: Optional[threading.Thread] = None
        self.lock = threading.Lock()

        # Hold tracking state
        self.palm_hold_start: Optional[float] = None
        self.fist_hold_start: Optional[float] = None
        self.palm_progress: float = 0.0
        self.fist_progress: float = 0.0
        self.palm_triggered: bool = False
        self.fist_triggered: bool = False

        self._last_detected_gesture: Optional[str] = None
        self._last_palm_seen: float = 0.0
        self._last_fist_seen: float = 0.0

    def _init_recognizer(self):
        """Initializes the MediaPipe Tasks GestureRecognizer engine."""
        if not MEDIAPIPE_AVAILABLE:
            print("[GestureSentry] MediaPipe is not installed. Gesture detection disabled.")
            return

        if not Path(self.model_path).exists():
            print(f"[GestureSentry] Model asset not found at: {self.model_path}")
            return

        with _suppress_c_stderr():
            try:
                base_options = mp_python.BaseOptions(model_asset_path=self.model_path)
                options = mp_vision.GestureRecognizerOptions(
                    base_options=base_options,
                    running_mode=mp_vision.RunningMode.IMAGE,
                    num_hands=1,
                    min_hand_detection_confidence=0.45,
                    min_hand_presence_confidence=0.45,
                    min_tracking_confidence=0.45,
                )
                self.recognizer = mp_vision.GestureRecognizer.create_from_options(options)
                # Warm-up dry run to trigger one-time MediaPipe graph initialization silently
                dummy = np.zeros((256, 256, 3), dtype=np.uint8)
                mp_dummy = mp.Image(image_format=mp.ImageFormat.SRGB, data=dummy)
                self.recognizer.recognize(mp_dummy)
            except Exception as e:
                self.recognizer = None

        if self.recognizer is not None:
            print("[GestureSentry] MediaPipe Gesture Recognizer initialized successfully.")
        else:
            print("[GestureSentry] Failed to initialize GestureRecognizer.")

    def start(self):
        """Starts background gesture detection thread."""
        if self.running or self.recognizer is None:
            return
        self.running = True
        self._thread = threading.Thread(target=self._worker_loop, daemon=True, name="GestureSentryThread")
        self._thread.start()
        print("[GestureSentry] Background sentry worker started.")

    def stop(self):
        """Stops background gesture detection thread."""
        self.running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None

    def get_feedback(self) -> Tuple[Optional[str], float]:
        """
        Thread-safe retrieval of current gesture and hold progress (0.0 to 1.0)
        tailored to the active robot state.
        - In STANDBY: returns ('OPEN_PALM', palm_progress) if palm detected/held, else (None, 0.0).
        - In ACTIVE:  returns ('CLOSED_FIST', fist_progress) if fist detected/held, else (None, 0.0).
        """
        with self.lock:
            try:
                is_standby = self.is_standby_fn()
            except Exception:
                is_standby = True

            if is_standby:
                gesture = "OPEN_PALM" if (self._last_detected_gesture == "OPEN_PALM" or self.palm_progress > 0.0) else None
                return gesture, self.palm_progress
            else:
                gesture = "CLOSED_FIST" if (self._last_detected_gesture == "CLOSED_FIST" or self.fist_progress > 0.0) else None
                return gesture, self.fist_progress

    def evaluate_frame(self, bgr_frame: cv2.Mat, is_standby: bool, now: Optional[float] = None) -> Tuple[Optional[str], float]:
        """
        Processes a single frame synchronously. Used by worker loop and automated unit tests.
        Returns: (detected_gesture, current_hold_progress)
        """
        if self.recognizer is None or bgr_frame is None:
            return None, 0.0

        if now is None:
            now = time.monotonic()

        # 1. Square Center-Crop and Resize to 256x256 (eliminates MediaPipe non-square ROI warning)
        h, w = bgr_frame.shape[:2]
        min_dim = min(h, w)
        crop_y = (h - min_dim) // 2
        crop_x = (w - min_dim) // 2
        square_crop = bgr_frame[crop_y : crop_y + min_dim, crop_x : crop_x + min_dim]
        small_frame = cv2.resize(square_crop, (256, 256), interpolation=cv2.INTER_LINEAR)

        # 2. Lighting-Proof Pre-Processing: CLAHE on L-channel in LAB space
        # Balances backlighting, harsh shadows, and dim room illumination
        try:
            lab = cv2.cvtColor(small_frame, cv2.COLOR_BGR2LAB)
            l_ch, a_ch, b_ch = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
            l_norm = clahe.apply(l_ch)
            enhanced_lab = cv2.merge((l_norm, a_ch, b_ch))
            enhanced_bgr = cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2BGR)
            rgb_frame = cv2.cvtColor(enhanced_bgr, cv2.COLOR_BGR2RGB)
        except Exception:
            rgb_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)

        try:
            result = self.recognizer.recognize(mp_image)
        except Exception:
            return None, 0.0

        # 3. Hybrid Classification: Category Classifier + Knuckle-Curl Landmark Geometry
        cat_palm = False
        cat_fist = False
        if result.gestures and len(result.gestures) > 0 and len(result.gestures[0]) > 0:
            top_gesture = result.gestures[0][0]
            cat_name = top_gesture.category_name
            score = top_gesture.score
            # Tightened Open Palm threshold to prevent false wakes from casual movement
            if cat_name == "Open_Palm" and score >= 0.60:
                cat_palm = True
            # Resilient Closed Fist threshold
            elif cat_name == "Closed_Fist" and score >= 0.45:
                cat_fist = True

        ext_count, curl_count, is_palm_geom, is_fist_geom = (0, 0, False, False)
        if result.hand_landmarks and len(result.hand_landmarks) > 0:
            ext_count, curl_count, is_palm_geom, is_fist_geom = analyze_hand_geometry(result.hand_landmarks[0])

        # Open Palm: Neural category with >=3 extended fingers OR strict palm geometry (4 extended, 0 curled)
        is_palm = (cat_palm and ext_count >= 3) or is_palm_geom

        # Closed Fist: Neural category OR geometric knuckle-curl (>=3 fingers curled into palm, <=1 extended)
        is_fist = cat_fist or is_fist_geom

        if is_palm and not is_fist:
            detected = "OPEN_PALM"
        elif is_fist and not is_palm:
            detected = "CLOSED_FIST"
        else:
            detected = None

        # 3. Continuous 3.0s Hold Logic with Strict State Isolation
        with self.lock:
            self._last_detected_gesture = detected

            if is_standby:
                # STANDBY MODE: Open Palm wakes, Closed Fist ignored
                self.fist_hold_start = None
                self.fist_progress = 0.0
                self.fist_triggered = False

                if detected == "OPEN_PALM":
                    self._last_palm_seen = now
                    if self.palm_hold_start is None:
                        self.palm_hold_start = now
                    elapsed = now - self.palm_hold_start
                    self.palm_progress = min(1.0, elapsed / self.hold_duration)

                    if self.palm_progress >= 1.0 and not self.palm_triggered:
                        self.palm_triggered = True
                        if self.on_palm_wake:
                            threading.Thread(target=self.on_palm_wake, daemon=True).start()
                else:
                    # 250ms grace period for momentary frame drops or motion blur
                    if (now - self._last_palm_seen) > 0.25:
                        self.palm_hold_start = None
                        self.palm_progress = 0.0
                        self.palm_triggered = False

                return (detected if detected == "OPEN_PALM" else None), self.palm_progress

            else:
                # ACTIVE MODE: Closed Fist standby kill-switch, Open Palm ignored
                self.palm_hold_start = None
                self.palm_progress = 0.0
                self.palm_triggered = False

                if detected == "CLOSED_FIST":
                    self._last_fist_seen = now
                    if self.fist_hold_start is None:
                        self.fist_hold_start = now
                    elapsed = now - self.fist_hold_start
                    self.fist_progress = min(1.0, elapsed / self.hold_duration)

                    if self.fist_progress >= 1.0 and not self.fist_triggered:
                        self.fist_triggered = True
                        if self.on_fist_standby:
                            threading.Thread(target=self.on_fist_standby, daemon=True).start()
                else:
                    # 250ms grace period for momentary frame drops or motion blur
                    if (now - self._last_fist_seen) > 0.25:
                        self.fist_hold_start = None
                        self.fist_progress = 0.0
                        self.fist_triggered = False

                return (detected if detected == "CLOSED_FIST" else None), self.fist_progress

    def _worker_loop(self):
        """Dedicated background detection worker (~15 FPS target)."""
        target_period = 0.066  # ~15 FPS (66ms)

        while self.running:
            t0 = time.monotonic()

            if self.get_frame_fn is None:
                time.sleep(0.1)
                continue

            frame = None
            try:
                frame = self.get_frame_fn()
            except Exception:
                frame = None

            if frame is None:
                time.sleep(0.05)
                continue

            try:
                is_standby = self.is_standby_fn()
            except Exception:
                is_standby = True

            self.evaluate_frame(frame, is_standby=is_standby, now=t0)

            elapsed = time.monotonic() - t0
            sleep_time = target_period - elapsed
            if sleep_time > 0.005:
                time.sleep(sleep_time)
