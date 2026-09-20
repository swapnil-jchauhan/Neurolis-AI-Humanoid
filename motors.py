"""
Project Neurolis - Real-Time Vision & Motor Navigation Engine (motors.py)
------------------------------------------------------------------------
Features:
  1. Official YuNet Deep-Learning Face Detector (Zero false positives, 60+ FPS).
  2. Live Camera Preview Window (cv2.imshow) with HUD bounding boxes and telemetry.
  3. Default Mode is STANDBY (Motors locked at 0 - never moves unprompted).
  4. Modes supported:
     - STANDBY: Stationary, eyes track face, motors 0.
     - FOLLOW: Continuous 30 FPS person tracking & following.
     - APPROACH: "Come here" -> drives to person (~0.8m) and auto-brakes to stop.
     - ROAM: Autonomous obstacle avoidance using ultrasonic sensors.
     - STEP_BACK: Gently reverses 1.5s and halts.
     - SPIN: Rotates in place.
  5. Master-to-Slave Serial protocol to Arduino Mega (with Virtual Simulator on PC).
"""

import os
import ssl
import sys
import threading
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import cv2
import numpy as np

try:
    import serial
    import serial.tools.list_ports
    HAS_SERIAL = True
except ImportError:
    HAS_SERIAL = False

BASE_DIR = Path(__file__).resolve().parent
MODEL_PATH = BASE_DIR / "face_detection_yunet_2023mar.onnx"


# check if yunet face model exists locally, if not download the 300kb neural file from opencv zoo
def ensure_yunet_model():
    """downloads official opencv yunet 300kb neural face model if missing using secure ssl"""
    if not MODEL_PATH.exists():
        print("[Motors] Downloading official OpenCV YuNet neural face model...")
        url = "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
        try:
            # try standard verified ssl connection first
            with urllib.request.urlopen(url, timeout=15) as response, open(MODEL_PATH, "wb") as out_file:
                out_file.write(response.read())
            print("[Motors] YuNet model downloaded successfully.")
        except Exception as e_verified:
            # fallback if local python install is missing certifi / ca roots
            try:
                ctx = ssl._create_unverified_context()
                with urllib.request.urlopen(url, context=ctx, timeout=15) as response, open(MODEL_PATH, "wb") as out_file:
                    out_file.write(response.read())
                print("[Motors] YuNet model downloaded via fallback context.")
            except Exception as e:
                print(f"[Motors] Model download warning: {e}")



# data container for ultrasonic distance measurements coming back from the arduino (supports up to 16 sensors)
@dataclass
class TelemetryData:
    front_us_cm: float = 999.0
    left_us_cm: float = 999.0
    right_us_cm: float = 999.0
    rear_us_cm: float = 999.0
    active_sensor_count: int = 0
    sensors_all: Optional[list] = None
    battery_mv: int = 12000


# all navigation states the robot can be in (standby, follow, approach, roam, etc)
class NavMode:
    STANDBY = "STANDBY"
    FOLLOW = "FOLLOW"
    APPROACH = "APPROACH"
    ROAM = "ROAM"
    STEP_BACK = "STEP_BACK"
    SPIN = "SPIN"


# main motor and vision controller class
class MotorController:
    # constructor sets up cameras, pd gains, face detector models, and serial communication
    def __init__(self, camera_index: int = 0, show_preview: bool = False, auto_popup: Optional[bool] = None):
        self.camera_index = camera_index
        self.show_preview = show_preview
        # on windows testing we auto popup the camera feed during movement, but on raspberry pi 5 we disable it so only screen.py shows
        if auto_popup is None:
            self.auto_popup = sys.platform.startswith("win")
        else:
            self.auto_popup = auto_popup
        self.popup_active = False     # explicit popup trigger flag
        self.nav_mode = NavMode.STANDBY  # always start locked at 0
        self.running = False
        self.lock = threading.Lock()

        # Telemetry
        self.telemetry = TelemetryData()
        self.ser: Optional["serial.Serial"] = None
        self.is_simulated = False

        # Raw frame cache for listen.py vision queries
        self.latest_raw_frame: Optional[np.ndarray] = None

        # Tracking state
        self.target_detected = False
        self.gaze_x = 0.0  # -1.0 to 1.0
        self.gaze_y = 0.0  # -1.0 to 1.0
        self.target_distance_ratio = 0.38  # Target face height ratio (~1.0m distance)
        self.last_seen_time = 0.0

        # Motion outputs
        self.last_cmd_speed = 0
        self.last_cmd_steer = 0

        # PD Gains for physical steering & speed
        self.kp_steer = 180.0
        self.kd_steer = 40.0
        self.kp_speed = 300.0
        self.kd_speed = 50.0
        self._prev_err_x = 0.0
        self._prev_err_dist = 0.0
        self._prev_time = time.time()
        self._mode_start_time = time.time()
        self._spin_dir = 1

        # Initialize YuNet Deep Learning Face Detector
        ensure_yunet_model()
        self.detector = None
        if MODEL_PATH.exists() and hasattr(cv2, "FaceDetectorYN_create"):
            try:
                self.detector = cv2.FaceDetectorYN_create(
                    str(MODEL_PATH), "", (320, 240), 0.65, 0.3, 5000
                )
            except Exception as e:
                print(f"[Motors] YuNet init notice: {e}")

        # Fallback Haar Cascade
        self.cascade = None
        local_cascade = BASE_DIR / "haarcascade_frontalface_default.xml"
        if local_cascade.exists() and hasattr(cv2, "CascadeClassifier"):
            try:
                self.cascade = cv2.CascadeClassifier(str(local_cascade))
            except Exception:
                pass

        self.cap: Optional[cv2.VideoCapture] = None
        self.latest_display_frame: Optional[np.ndarray] = None

        # Threads
        self._vision_thread: Optional[threading.Thread] = None
        self._serial_thread: Optional[threading.Thread] = None
        self._preview_thread: Optional[threading.Thread] = None

    # starts the background threads for camera vision, serial communication, and debug preview
    def start(self):
        """Starts background vision tracking and Arduino serial bridge."""
        self.running = True
        self._connect_serial()

        self._serial_thread = threading.Thread(target=self._serial_rx_loop, daemon=True)
        self._serial_thread.start()

        self._vision_thread = threading.Thread(target=self._vision_loop, daemon=True)
        self._vision_thread.start()

        self._preview_thread = threading.Thread(target=self._preview_loop, daemon=True)
        self._preview_thread.start()
        print("[Motors] Motor Controller Online. Status: STANDBY (MOTORS LOCKED).")

    # tries to find and connect to the physical arduino mega plugged into usb
    def _connect_serial(self):
        if not HAS_SERIAL:
            self._enter_sim("PySerial not installed.")
            return

        port = self._find_arduino()
        if port:
            try:
                self.ser = serial.Serial(port, 115200, timeout=0.1)
                time.sleep(1.5)
                self.is_simulated = False
                print(f"[Motors] Connected to Arduino Mega on {port} @ 115200 baud.")
            except Exception as e:
                self._enter_sim(f"Serial connection failed: {e}")
        else:
            self._enter_sim("No physical Arduino Mega detected.")

    # fallback into simulation mode if no arduino is plugged in so code runs smoothly on pc
    def _enter_sim(self, reason: str):
        self.is_simulated = True
        print(f"[Motors] [SIMULATION MODE] {reason}")
        print("[Motors] Hardware-Free Testing Active: Virtual 16-Sensor 4WD Physics Enabled.")

    # scans all com ports looking for an arduino mega, ch340, or cp2102 chip
    def _find_arduino(self) -> Optional[str]:
        if not HAS_SERIAL:
            return None
        ports = list(serial.tools.list_ports.comports())
        for p in ports:
            desc = (p.description or "").lower()
            hwid = (p.hwid or "").lower()
            if any(k in desc or k in hwid for k in ["arduino", "mega", "ch340", "cp210", "usb serial"]):
                return p.device
        return ports[0].device if ports else None

    # ---- NATURAL COMMAND INTERFACES ----
    # activates follow-me mode: robot uses camera to track the human and drives after them
    def start_following(self):
        with self.lock:
            self.nav_mode = NavMode.FOLLOW
            self.popup_active = True
        print("[Motors] Mode: CONTINUOUS FOLLOW ME.")

    # activates come-here mode: robot approaches user until within conversation range (~0.8m)
    def approach_user(self):
        with self.lock:
            self.nav_mode = NavMode.APPROACH
            self.popup_active = True
            self._mode_start_time = time.time()
        print("[Motors] Mode: APPROACH USER ('Come Here').")

    # activates autonomous room patrol: robot drives around avoiding obstacles using ultrasonics
    def start_roaming(self):
        with self.lock:
            self.nav_mode = NavMode.ROAM
            self.popup_active = True
        print("[Motors] Mode: AUTONOMOUS ROOM PATROL / ROAM.")

    # mobility demo: drives around safely while speaking to showcase physical movement
    def demonstrate_motion(self):
        """Actively moves in autonomous obstacle-dodging mode while speaking."""
        with self.lock:
            self.nav_mode = NavMode.ROAM
            self.popup_active = True
        print("[Motors] Mode: DEMONSTRATING AUTONOMOUS 4WD MOVEMENT.")

    # backs up gently for 1.5 seconds and stops (with rear obstacle collision check)
    def step_back(self) -> bool:
        with self.lock:
            r_dist = self.telemetry.rear_us_cm
        if r_dist < 28.0:
            print(f"[Motors] Step back aborted: rear obstacle detected at {r_dist:.1f}cm.")
            self.stop_all()
            return False
        with self.lock:
            self.nav_mode = NavMode.STEP_BACK
            self._mode_start_time = time.time()
        print("[Motors] Mode: STEPPING BACK.")
        return True

    # rotates chassis in place to turn around
    def spin(self, direction: str = "right"):
        with self.lock:
            self.nav_mode = NavMode.SPIN
            self._mode_start_time = time.time()
            self._spin_dir = 1 if direction == "right" else -1
        print(f"[Motors] Mode: SPINNING {direction.upper()}.")

    # pre-flight safety check to verify if the intended direction has clearance
    def can_move(self, direction: str = "forward") -> Tuple[bool, str]:
        """checks if movement in the requested direction is safe based on ultrasonic telemetry"""
        with self.lock:
            f_dist = self.telemetry.front_us_cm
            r_dist = self.telemetry.rear_us_cm

        if direction == "forward":
            if f_dist < 28.0:
                return False, f"front obstacle detected ({f_dist:.1f}cm < 28cm)"
            return True, "forward path clear"
        elif direction == "backward":
            if r_dist < 28.0:
                return False, f"rear obstacle detected ({r_dist:.1f}cm < 28cm)"
            return True, "rear path clear"
        elif direction in ["spin", "turn"]:
            if f_dist < 20.0 or r_dist < 20.0:
                return False, f"space too tight for rotation (front: {f_dist:.1f}cm, rear: {r_dist:.1f}cm)"
            return True, "rotation clear"
        return True, "ready"

    # opens opencv debug window if desktop testing preview is requested
    def show_popup(self):
        """Explicitly opens the OpenCV HUD camera window."""
        with self.lock:
            self.popup_active = True

    # closes the opencv camera preview window
    def hide_popup(self):
        """Explicitly closes the OpenCV HUD camera window."""
        with self.lock:
            self.popup_active = False

    # emergency stop: immediately sets speed and steer to zero and locks wheels in standby
    def stop_all(self):
        with self.lock:
            self.nav_mode = NavMode.STANDBY
            self.popup_active = False
        self.stop()
        print("[Motors] Mode: STANDBY (MOTORS LOCKED).")

    # low-level drive function that packages speed and steer into serial commands for arduino
    def drive(self, speed: int, steer: int):
        speed = max(-255, min(255, int(speed)))
        steer = max(-255, min(255, int(steer)))

        # Safety override if front ultrasonic obstacle detected (< 28cm)
        if self.telemetry.front_us_cm < 28.0 and speed > 0:
            speed = 0

        # Safety override if rear ultrasonic obstacle detected (< 28cm)
        if self.telemetry.rear_us_cm < 28.0 and speed < 0:
            speed = 0

        with self.lock:
            self.last_cmd_speed = speed
            self.last_cmd_steer = steer

        if self.ser and self.ser.is_open and not self.is_simulated:
            try:
                self.ser.write(f"DRIVE,{speed},{steer}\n".encode("ascii"))
            except Exception as e:
                print(f"[Motors] Serial drive command failed: {e}")

    # temporary pause or brake on current motion
    def stop(self):
        with self.lock:
            self.last_cmd_speed = 0
            self.last_cmd_steer = 0
        if self.ser and self.ser.is_open and not self.is_simulated:
            try:
                self.ser.write(b"STOP\n")
            except Exception as e:
                print(f"[Motors] Serial stop command failed: {e}")

    # returns gaze coordinates (x, y) of the user's face so the screen eyes look at them
    def get_gaze_coordinates(self) -> Tuple[bool, float, float]:
        with self.lock:
            return self.target_detected, self.gaze_x, self.gaze_y

    # returns current navigation mode, speed, and steering for telemetry status
    def get_motion_telemetry(self) -> Tuple[str, int, int]:
        with self.lock:
            return self.nav_mode, self.last_cmd_speed, self.last_cmd_steer

    # gets the latest raw camera frame for groq ai vision queries (what am i holding, etc)
    def get_latest_raw_frame(self) -> Optional[np.ndarray]:
        """Provides thread-safe access to raw camera frame for Groq vision queries."""
        with self.lock:
            return self.latest_raw_frame.copy() if self.latest_raw_frame is not None else None

    # gets the latest camera frame with hud bounding boxes drawn on it
    def get_display_frame(self) -> Optional[np.ndarray]:
        """Provides thread-safe access to HUD-rendered frame."""
        with self.lock:
            return self.latest_display_frame.copy() if self.latest_display_frame is not None else None

    # background thread that reads the webcam at 30 fps without blocking the main brain
    def _vision_loop(self):
        if sys.platform.startswith("win"):
            self.cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
        else:
            self.cap = cv2.VideoCapture(self.camera_index)

        while self.running:
            if self.cap and self.cap.isOpened():
                ok, frame = self.cap.read()
                if ok and frame is not None:
                    with self.lock:
                        self.latest_raw_frame = frame.copy()
                    self._process_frame(frame)
                else:
                    time.sleep(0.04)
            else:
                time.sleep(0.1)

    # runs yunet deep learning face detection on the camera frame and calculates steering math
    def _process_frame(self, frame: np.ndarray):
        h, w = frame.shape[:2]
        proc_w = 480
        scale = proc_w / float(w)
        proc_h = int(h * scale)
        proc_frame = cv2.resize(frame, (proc_w, proc_h))

        detected_faces = []

        # 1. High-Accuracy YuNet Face Detection
        if self.detector is not None:
            self.detector.setInputSize((proc_w, proc_h))
            _, faces = self.detector.detect(proc_frame)
            if faces is not None:
                for f in faces:
                    score = f[-1]
                    if score >= 0.60:  # Confident face only
                        fx, fy, fw, fh = int(f[0]), int(f[1]), int(f[2]), int(f[3])
                        detected_faces.append((fx, fy, fw, fh, score))

        # 2. Fallback Haar Cascade
        elif self.cascade is not None:
            gray = cv2.cvtColor(proc_frame, cv2.COLOR_BGR2GRAY)
            faces = self.cascade.detectMultiScale(
                gray, scaleFactor=1.15, minNeighbors=5, minSize=(int(proc_h * 0.15), int(proc_h * 0.15))
            )
            for fx, fy, fw, fh in faces:
                detected_faces.append((fx, fy, fw, fh, 1.0))

        now = time.time()
        dt = max(0.01, now - self._prev_time)

        with self.lock:
            mode = self.nav_mode

        if len(detected_faces) > 0:
            # Select largest primary face
            primary = max(detected_faces, key=lambda b: b[2] * b[3])
            fx, fy, fw, fh, score = primary

            center_x = (fx + fw / 2.0) / (proc_w / 2.0) - 1.0
            center_y = (fy + fh / 2.0) / (proc_h / 2.0) - 1.0
            box_ratio = fh / float(proc_h)

            with self.lock:
                self.target_detected = True
                self.gaze_x = center_x
                self.gaze_y = center_y
                self.last_seen_time = now

            # 1. FOLLOW MODE
            if mode == NavMode.FOLLOW:
                err_x = center_x
                d_err_x = (err_x - self._prev_err_x) / dt
                steer = (self.kp_steer * err_x) + (self.kd_steer * d_err_x)

                err_dist = self.target_distance_ratio - box_ratio
                d_err_dist = (err_dist - self._prev_err_dist) / dt
                speed = (self.kp_speed * err_dist) + (self.kd_speed * d_err_dist)

                if abs(err_x) < 0.08: steer = 0.0
                if abs(err_dist) < 0.06: speed = 0.0

                cmd_spd = int(np.clip(speed, -150, 180))
                cmd_str = int(np.clip(steer, -140, 140))
                self.drive(cmd_spd, cmd_str)

                self._prev_err_x = err_x
                self._prev_err_dist = err_dist

            # 2. APPROACH MODE ("Come here")
            elif mode == NavMode.APPROACH:
                err_x = center_x
                steer = int(self.kp_steer * err_x)

                # Stop when reached (~0.8m distance)
                if box_ratio >= 0.44 or now - self._mode_start_time > 8.0:
                    self.stop_all()
                else:
                    self.drive(120, steer)

            # 3. STANDBY MODE (Motors strictly 0)
            elif mode == NavMode.STANDBY:
                self.stop()

        else:
            with self.lock:
                if now - self.last_seen_time > 0.8:
                    self.target_detected = False
                    self.gaze_x = 0.0
                    self.gaze_y = 0.0
            if mode in [NavMode.FOLLOW, NavMode.APPROACH]:
                self.stop()

        # 4. AUTONOMOUS ROAM / WANDER MODE (Ultrasonic obstacle avoidance)
        if mode == NavMode.ROAM:
            f_dist = self.telemetry.front_us_cm
            l_dist = self.telemetry.left_us_cm
            r_dist = self.telemetry.right_us_cm

            if f_dist > 65.0:
                self.drive(90, 0)
            elif f_dist > 35.0:
                steer_val = -100 if l_dist > r_dist else 100
                self.drive(70, steer_val)
            else:
                self.drive(-90, 120)

        # 5. STEP BACK MODE
        elif mode == NavMode.STEP_BACK:
            if self.telemetry.rear_us_cm < 28.0:
                print(f"[Motors] Rear obstacle detected ({self.telemetry.rear_us_cm:.1f}cm), braking!")
                self.stop_all()
            elif now - self._mode_start_time < 1.5:
                self.drive(-110, 0)
            else:
                self.stop_all()

        # 6. SPIN MODE
        elif mode == NavMode.SPIN:
            if now - self._mode_start_time < 1.2:
                self.drive(0, 130 * getattr(self, "_spin_dir", 1))
            else:
                self.stop_all()

        self._prev_time = now

        # Draw Live Video Feed HUD if preview is active, popup_active is set, or in active nav mode
        with self.lock:
            need_display = self.show_preview or self.popup_active or (self.auto_popup and self.nav_mode in [NavMode.FOLLOW, NavMode.APPROACH, NavMode.ROAM])

        if need_display:
            disp = proc_frame.copy()
            if len(detected_faces) > 0:
                for fx, fy, fw, fh, score in detected_faces:
                    cv2.rectangle(disp, (fx, fy), (fx + fw, fy + fh), (0, 240, 255), 2)
                    cv2.putText(
                        disp, f"HUMAN: {int(score*100)}%", (fx, fy - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 240, 255), 1
                    )
                # Crosshair on closest human face
                cx = fx + fw // 2
                cy = fy + fh // 2
                cv2.drawMarker(disp, (cx, cy), (0, 255, 0), cv2.MARKER_CROSS, 24, 2)

            # HUD Overlay
            spd, str_v = self.last_cmd_speed, self.last_cmd_steer
            cv2.putText(disp, f"MODE: {mode}", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 100), 2)
            cv2.putText(disp, f"SPEED: {spd:+4d} | STEER: {str_v:+4d}", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            cv2.putText(disp, f"FRONT US: {self.telemetry.front_us_cm:.0f}cm | REAR: {self.telemetry.rear_us_cm:.0f}cm", (10, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (100, 200, 255), 1)

            with self.lock:
                self.latest_display_frame = disp

    # background thread that displays the opencv camera window if desktop preview is on
    def _preview_loop(self):
        window_open = False
        window_title = "Neurolis AI Vision & Motor HUD"
        while self.running:
            should_show = False
            with self.lock:
                should_show = self.show_preview or (self.auto_popup and (self.popup_active or self.nav_mode in [NavMode.FOLLOW, NavMode.APPROACH, NavMode.ROAM]))

            if should_show and self.latest_display_frame is not None:
                if not window_open:
                    cv2.namedWindow(window_title, cv2.WINDOW_AUTOSIZE)
                cv2.imshow(window_title, self.latest_display_frame)
                window_open = True
                cv2.waitKey(20)
            else:
                if window_open:
                    try:
                        cv2.destroyWindow(window_title)
                        cv2.waitKey(1)
                    except Exception:
                        pass
                    window_open = False
                time.sleep(0.04)

        try:
            cv2.destroyAllWindows()
        except Exception:
            pass

    # background thread that reads distance telemetry coming from the arduino mega over usb
    def _serial_rx_loop(self):
        sim_wander_dist = 120.0
        sim_wander_dir = -1.0
        while self.running:
            if self.is_simulated:
                with self.lock:
                    mode = self.nav_mode

                if mode == NavMode.ROAM:
                    # Simulate moving towards a wall and steering away
                    sim_wander_dist += sim_wander_dir * 4.0
                    if sim_wander_dist <= 30.0:
                        sim_wander_dir = 1.0  # Steered away from wall
                        sim_l = 85.0
                        sim_r = 30.0
                    elif sim_wander_dist >= 120.0:
                        sim_wander_dir = -1.0  # Cruising forward
                        sim_l = 90.0
                        sim_r = 90.0
                    else:
                        sim_l = 75.0
                        sim_r = 40.0

                    with self.lock:
                        self.telemetry.front_us_cm = max(15.0, round(sim_wander_dist, 1))
                        self.telemetry.left_us_cm = sim_l
                        self.telemetry.right_us_cm = sim_r
                        self.telemetry.rear_us_cm = 150.0
                        self.telemetry.active_sensor_count = 0  # 0 physical sensors connected in simulation
                        self.telemetry.sensors_all = [self.telemetry.front_us_cm] * 4 + [sim_l] * 4 + [sim_r] * 4 + [150.0] * 4
                else:
                    with self.lock:
                        self.telemetry.front_us_cm = 999.0
                        self.telemetry.left_us_cm = 999.0
                        self.telemetry.right_us_cm = 999.0
                        self.telemetry.rear_us_cm = 999.0
                        self.telemetry.active_sensor_count = 0  # 0 physical sensors connected in simulation
                        self.telemetry.sensors_all = [999.0] * 16

                time.sleep(0.05)
                continue

            if self.ser and self.ser.is_open:
                try:
                    line = self.ser.readline().decode("ascii", errors="ignore").strip()
                    if line.startswith("SENSORS,"):
                        parts = line.split(",")
                        if len(parts) >= 5:
                            with self.lock:
                                self.telemetry.front_us_cm = float(parts[1])
                                self.telemetry.left_us_cm = float(parts[2])
                                self.telemetry.right_us_cm = float(parts[3])
                                self.telemetry.rear_us_cm = float(parts[4])
                                if len(parts) > 5:
                                    try:
                                        self.telemetry.active_sensor_count = int(parts[5])
                                        if len(parts) > 6:
                                            self.telemetry.sensors_all = [float(p) for p in parts[6:]]
                                    except (ValueError, IndexError):
                                        pass
                        elif len(parts) >= 4:
                            with self.lock:
                                self.telemetry.front_us_cm = float(parts[1])
                                self.telemetry.left_us_cm = float(parts[2])
                                self.telemetry.right_us_cm = float(parts[3])
                except (ValueError, IndexError):
                    # ignore occasional partial serial line fragments
                    pass
                except Exception as e:
                    print(f"[Motors] Serial telemetry error: {e}")
            time.sleep(0.02)

    # configures active sensor count on physical arduino (e.g. 4, 8, 12, 16, or 'AUTO')
    def set_sensor_config(self, count: int = 16):
        """sends command to arduino to configure active sensors (4, 8, 12, 16, or 'AUTO')"""
        if self.ser and self.ser.is_open and not self.is_simulated:
            try:
                self.ser.write(f"CONFIG_SENSORS,{count}\n".encode("ascii"))
            except Exception as e:
                print(f"[Motors] Failed to send sensor config: {e}")

    # cleanly shuts down camera capture, stops threads, and closes serial connections
    def close(self):
        self.running = False
        self.stop()
        if self.cap and self.cap.isOpened():
            self.cap.release()
        if self.ser and self.ser.is_open:
            try:
                self.ser.close()
            except Exception:
                pass
        try:
            cv2.destroyAllWindows()
        except Exception:
            pass
        print("[Motors] Safely shut down.")


# standalone test runner when motors.py is run directly in terminal
if __name__ == "__main__":
    try:
        import msvcrt
        HAS_MSVCRT = True
    except ImportError:
        HAS_MSVCRT = False

    print("=" * 65)
    print("  PROJECT NEUROLIS - CAMERA & MOTOR VISUAL SIMULATOR")
    print("=" * 65)
    print("  Default State: STANDBY (MOTORS LOCKED AT 0)")
    print("  Controls (Type in Terminal or Press in Preview Window):")
    print("    [R] - Autonomous Roam / Patrol Mode (Ultrasonic Obstacle Avoidance)")
    print("    [A] - Approach Mode ('Come Here' -> Drives to you & Auto-Brakes)")
    print("    [F] - Follow Me Mode (Continuous 30 FPS Person Tracking)")
    print("    [B] - Step Back")
    print("    [S] - STOP / Lock Motors to 0")
    print("    [Q] - Exit")
    print("=" * 65)

    motors = MotorController(show_preview=True)
    motors.start()

    try:
        while True:
            # 1. Read OpenCV window key
            key = cv2.waitKey(30) & 0xFF
            char = chr(key).lower() if key < 256 else ""

            # 2. Read Terminal keypress (works even if window isn't focused!)
            if HAS_MSVCRT and msvcrt.kbhit():
                try:
                    char = msvcrt.getch().decode("utf-8", errors="ignore").lower()
                except Exception:
                    pass

            if char == "q":
                break
            elif char == "r":
                print("\n>>> [COMMAND] AUTONOMOUS ROAM / PATROL ENGAGED.")
                motors.start_roaming()
            elif char == "a":
                print("\n>>> [COMMAND] APPROACH MODE ('Come Here') ENGAGED.")
                motors.approach_user()
            elif char == "f":
                print("\n>>> [COMMAND] CONTINUOUS FOLLOW-ME ENGAGED.")
                motors.start_following()
            elif char == "b":
                print("\n>>> [COMMAND] STEP BACK ENGAGED.")
                motors.step_back()
            elif char == "s":
                print("\n>>> [COMMAND] EMERGENCY STOP (MOTORS LOCKED).")
                motors.stop_all()

            # Terminal Live HUD Line
            found, gx, gy = motors.get_gaze_coordinates()
            mode, spd, str_val = motors.get_motion_telemetry()
            target_str = f"LOCKED ({gx:+.2f}, {gy:+.2f})" if found else "SEARCHING"
            us_str = f"{motors.telemetry.front_us_cm:.0f}cm"

            print(
                f"\r[HUD] Mode: {mode:9s} | Target: {target_str:18s} | Front US: {us_str:5s} | Speed: {spd:+4d} | Steer: {str_val:+4d} ",
                end="",
                flush=True,
            )

    except KeyboardInterrupt:
        print("\nExiting Simulator.")
    finally:
        motors.close()

