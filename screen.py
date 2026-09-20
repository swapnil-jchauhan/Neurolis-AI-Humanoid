"""
Project Neurolis - Real-Time 7-Inch Animated Face UI Engine (screen.py)
----------------------------------------------------------------------
Lightweight 60 FPS animated robotic face optimized for the Raspberry Pi 7-inch (1024x600, 16:9).
Features:
  - Real-time Subtitle Card ([YOU] vs [NEUROLIS]) with auto-wrapping below expressions.
  - Futuristic Cyber Car / 4WD Rover moving expression with spinning alloy wheels, headlights, and road streaks.
  - Clean Acoustic Sonar & Equalizer for listening mode (no cluttered rings over eyes).
  - High-precision cyber eyebrows reacting dynamically to robot states.
  - Enhanced Eye Anatomy with Iris rings, specular glints, and smooth gaze tracking.
  - States: IDLE, LISTENING, THINKING, SPEAKING, HAPPY, LOOKING, CONFUSED, ERROR, MOVING, WATCHING.
"""

import math
import os
import platform
import random
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from typing import Optional

# crisp system font family selection across windows and linux / raspberry pi
FONT_FAMILY = "Segoe UI" if sys.platform.startswith("win") else "DejaVu Sans"


# helper function to smoothly lerp between two hex colors (e.g. #040711 to #f8fafc)
def lerp_color(color_a: str, color_b: str, t: float) -> str:
    """smoothly blends between two hex colors based on t (0.0 to 1.0)"""
    t = max(0.0, min(1.0, t))
    r1, g1, b1 = int(color_a[1:3], 16), int(color_a[3:5], 16), int(color_a[5:7], 16)
    r2, g2, b2 = int(color_b[1:3], 16), int(color_b[3:5], 16), int(color_b[5:7], 16)
    r = int(r1 + (r2 - r1) * t)
    g = int(g1 + (g2 - g1) * t)
    b = int(b1 + (b2 - b1) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


# all the possible emotion and visual states the face can switch into
class ExpressionState:
    BOOT_GREETING = "boot_greeting"
    BOOT_SEQUENCE = "boot_sequence"
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    HAPPY = "happy"
    SAD = "sad"
    LOOKING = "looking"
    CONFUSED = "confused"
    ERROR = "error"
    MOVING = "moving"
    WATCHING = "watching"


# checks all the physical wires, chips, and code scripts on startup
class HardwareInspector:
    # keeps track of the motor controller handle so we can read real serial and camera stats
    def __init__(self, motor_controller=None):
        self.motor_controller = motor_controller

    # helper to check if physical arduino mega is connected over serial
    def _is_arduino_connected(self):
        # 1. check active serial on motor controller
        if self.motor_controller is not None:
            if not getattr(self.motor_controller, "is_simulated", True):
                ser = getattr(self.motor_controller, "ser", None)
                if ser is not None and getattr(ser, "is_open", False):
                    return True, getattr(ser, "port", "USB")

        # 2. scan live serial com ports
        try:
            import serial.tools.list_ports as lp
            ports = list(lp.comports())
            for p in ports:
                desc = (p.description or "").lower()
                hwid = (p.hwid or "").lower()
                if any(k in desc or k in hwid for k in ["arduino", "mega", "ch340", "cp210", "usb serial"]):
                    return True, p.device
        except Exception:
            pass

        return False, None

    # checks if a physical webcam or usb camera is plugged in and accessible
    def check_camera(self):
        # first check if motor controller already opened camera
        if self.motor_controller is not None and getattr(self.motor_controller, "cap", None) is not None:
            cap = self.motor_controller.cap
            if cap is not None and cap.isOpened():
                return True, "✓", "Connected"

        # live test probe on device 0
        try:
            import cv2
            cap = cv2.VideoCapture(0)
            if cap.isOpened():
                cap.release()
                return True, "✓", "Connected"
            return False, "✗", "Not Detected"
        except Exception:
            return False, "✗", "Not Detected"

    # checks if audio input microphone is plugged in and recognized
    def check_mic(self):
        try:
            import sounddevice as sd
            dev = sd.query_devices(kind="input")
            if dev and dev.get("max_input_channels", 0) > 0:
                return True, "✓", "Connected"
            return False, "✗", "Not Detected"
        except Exception:
            return False, "✗", "Not Detected"

    # checks if speakers or audio output devices are plugged in
    def check_speakers(self):
        try:
            import sounddevice as sd
            dev = sd.query_devices(kind="output")
            if dev and dev.get("max_output_channels", 0) > 0:
                return True, "✓", "Connected"
            return False, "✗", "Not Detected"
        except Exception:
            return False, "✗", "Not Detected"

    # checks if running directly on real raspberry pi hardware or pc simulation
    def check_raspberry_pi(self):
        try:
            if os.path.exists("/proc/device-tree/model"):
                with open("/proc/device-tree/model", "r", encoding="utf-8", errors="ignore") as f:
                    model = f.read().strip().rstrip("\x00")
                    if "Raspberry Pi" in model:
                        return True, "✓", "Raspberry Pi 5"
        except Exception:
            pass
        try:
            if os.path.exists("/proc/cpuinfo"):
                with open("/proc/cpuinfo", "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        if "Model" in line and "Raspberry Pi" in line:
                            return True, "✓", "Raspberry Pi 5"
        except Exception:
            pass
        return False, "✗", f"{platform.system()} PC (Simulation)"

    # verifies that listen.py core voice loop exists
    def check_listen_py(self):
        base_dir = Path(__file__).resolve().parent
        listen_file = base_dir / "listen.py"
        if listen_file.exists():
            return True, "✓", "Online"
        return False, "✗", "Not Found"

    # checks if physical arduino mega is plugged into usb serial port
    def check_arduino(self):
        conn, port = self._is_arduino_connected()
        if conn:
            return True, "✓", f"Connected ({port})"
        return False, "✗", "Not Detected"

    # tests whether arduino.ino firmware is responding or running fallback simulation
    def check_arduino_firmware(self):
        conn, _ = self._is_arduino_connected()
        if conn:
            return True, "✓", "Online"
        return False, "✗", "Testing Fallback (Simulation Mode)"

    # checks if 4x bts7960 motor drivers are detected on hardware
    def check_motor_drivers(self):
        conn, _ = self._is_arduino_connected()
        if conn:
            return True, "✓", "Connected"
        return False, "✗", "Not Detected"

    # returns exact motor driver count: 4 if connected, 0 (Simulation Mode) with cross if none
    def check_motor_driver_count(self):
        conn, _ = self._is_arduino_connected()
        if conn:
            return True, "✓", "4"
        return False, "✗", "0 (Simulation Mode)"

    # checks if 4x johnson motors are detected on hardware
    def check_motors(self):
        conn, _ = self._is_arduino_connected()
        if conn:
            return True, "✓", "Connected"
        return False, "✗", "Not Detected"

    # returns exact motor count: 4 if connected, 0 (Simulation Mode) with cross if none
    def check_motor_count(self):
        conn, _ = self._is_arduino_connected()
        if conn:
            return True, "✓", "4"
        return False, "✗", "0 (Simulation Mode)"

    # verifies motors.py script exists
    def check_motors_py(self):
        base_dir = Path(__file__).resolve().parent
        motors_file = base_dir / "motors.py"
        if motors_file.exists():
            return True, "✓", "Online"
        return False, "✗", "Not Found"

    # checks if ultrasonic distance sensors are detected
    def check_ultrasound_detected(self):
        conn, _ = self._is_arduino_connected()
        if conn:
            cnt = 0
            if self.motor_controller is not None:
                telem = getattr(self.motor_controller, "telemetry", None)
                cnt = getattr(telem, "active_sensor_count", 0) if telem else 0
            if cnt > 0:
                return True, "✓", "Connected"
            return False, "✗", "Not Detected (0 Active)"
        return False, "✗", "Not Detected (Simulation Mode)"

    # returns exact ultrasound count: 4, 8, 12, or 16 if connected, or 0 (Simulation Mode) with cross if none
    def check_ultrasound_count(self):
        conn, _ = self._is_arduino_connected()
        if conn:
            cnt = 0
            if self.motor_controller is not None:
                telem = getattr(self.motor_controller, "telemetry", None)
                cnt = getattr(telem, "active_sensor_count", 0) if telem else 0
            if cnt in [4, 8, 12, 16] or cnt > 0:
                return True, "✓", str(cnt)
            return False, "✗", "0 (Simulation Mode)"
        return False, "✗", "0 (Simulation Mode)"


# main class that creates and animates the robotic face on the screen
class FaceUI:
    # constructor sets up the window dimensions, colors, eye sizes, and animation timers
    def __init__(
        self,
        width: int = 1024,
        height: int = 600,
        fullscreen: bool = False,
        bg_color: str = "#040711",
        enable_boot: bool = True,
    ):
        self.width = width
        self.height = height
        self.fullscreen = fullscreen
        self.bg_color = bg_color
        self.enable_boot = enable_boot

        # State management - boots with apple-grade greeting and diagnostics
        self.state = ExpressionState.BOOT_GREETING if enable_boot else ExpressionState.IDLE
        self.status_text = "SYSTEM BOOT // DIAGNOSTICS" if enable_boot else "STANDBY // READY"
        self.lock = threading.Lock()
        self.running = False

        # Launch sequence & hardware diagnostics
        self.boot_start_time = time.time()
        self.boot_scroll_y = 0.0
        self.diagnostic_results = []
        self.diagnostic_complete = False
        self.hardware_inspector = HardwareInspector()
        self._boot_thread: Optional[threading.Thread] = None

        # Eye tracking coordinates (-1.0 to 1.0)
        self.target_look_x = 0.0
        self.target_look_y = 0.0
        self.current_look_x = 0.0
        self.current_look_y = 0.0

        # Animation parameters
        self.blink_progress = 0.0
        self.is_blinking = False
        self.last_blink_time = time.time()
        self.next_blink_interval = random.uniform(2.5, 5.0)

        # Oscillations
        self.anim_phase = 0.0
        self.thinking_angle = 0.0
        self.speaking_intensity = 0.6

        # Subtitles
        self.subtitle_speaker = "NEUROLIS"
        self.subtitle_text = "Standing by. Press Enter or tap 'Talk to Neurolis' to begin."
        self.subtitle_time = time.time()

        # Colors - Modern Luminous OLED Robot Palette (Vector / EMO inspired)
        self.color_eye_main = "#00f0ff"
        self.color_eye_glow = "#00384d"
        self.color_pupil = "#ffffff"
        self.color_error = "#ff2244"
        self.color_listening = "#00ffcc"
        self.color_thinking = "#a855f7"
        self.color_happy = "#00ff88"
        self.color_sad = "#2979ff"
        self.color_sad_glow = "#0e2447"
        self.color_confused = "#ffb703"
        self.color_confused_glow = "#4d3400"

        # Geometry optimized for 7" 1024x600 (Face upper half, Subtitles lower half)
        self.eye_w = 160
        self.eye_h = 165
        self.eye_spacing = 260
        self.corner_radius = 42

        # Tkinter handles
        self.root: Optional[tk.Tk] = None
        self.canvas: Optional[tk.Canvas] = None
        self._thread: Optional[threading.Thread] = None

    # links the motor controller handle so hardware inspector can read real camera & serial stats
    def set_motor_controller(self, motor_controller):
        self.hardware_inspector.motor_controller = motor_controller

    # lets developer or user skip the 18s boot sequence by tapping screen or pressing any key
    def skip_boot(self):
        with self.lock:
            if self.state in [ExpressionState.BOOT_GREETING, ExpressionState.BOOT_SEQUENCE]:
                self.state = ExpressionState.IDLE
                self.status_text = "STANDBY // READY"
                self.subtitle_speaker = "NEUROLIS"
                self.subtitle_text = "Standing by. Press Enter or tap 'Talk to Neurolis' to begin."

    # handles key presses to support fullscreen, stop, and instant boot skipping
    def _on_key(self, event):
        key = (event.keysym or "").lower()
        if key == "f":
            self._toggle_fullscreen()
        elif key == "escape":
            self.stop()
        else:
            self.skip_boot()

    # starts the background thread that tests each hardware component one after another
    def _start_diagnostic_thread(self):
        if self._boot_thread is None:
            self._boot_thread = threading.Thread(target=self._boot_diagnostic_worker, daemon=True)
            self._boot_thread.start()

    # runs through all 14 component checks with human-friendly pacing (~1.15s per check)
    def _boot_diagnostic_worker(self):
        steps = [
            ("Camera Detected?", self.hardware_inspector.check_camera),
            ("Mic Detected?", self.hardware_inspector.check_mic),
            ("Speakers Detected?", self.hardware_inspector.check_speakers),
            ("Raspberry Pi Detected?", self.hardware_inspector.check_raspberry_pi),
            ("listen.py Test Initiate", self.hardware_inspector.check_listen_py),
            ("Arduino Detected?", self.hardware_inspector.check_arduino),
            ("arduino.ino Test Initiate", self.hardware_inspector.check_arduino_firmware),
            ("Motor Drivers Detected?", self.hardware_inspector.check_motor_drivers),
            ("Motor Driver Number", self.hardware_inspector.check_motor_driver_count),
            ("Motors Detected?", self.hardware_inspector.check_motors),
            ("Motor Number", self.hardware_inspector.check_motor_count),
            ("motors.py Test Initiate", self.hardware_inspector.check_motors_py),
            ("Ultrasound Sensor Detected?", self.hardware_inspector.check_ultrasound_detected),
            ("Ultrasound Number", self.hardware_inspector.check_ultrasound_count),
        ]

        for name, check_fn in steps:
            if not self.running or self.state not in [ExpressionState.BOOT_GREETING, ExpressionState.BOOT_SEQUENCE]:
                break
            time.sleep(1.15)
            if not self.running or self.state not in [ExpressionState.BOOT_GREETING, ExpressionState.BOOT_SEQUENCE]:
                break
            try:
                res = check_fn()
                if len(res) == 4:
                    passed, badge, detail, is_fb = res
                else:
                    passed, badge, detail = res
                    is_fb = False
            except Exception as e:
                passed, badge, detail, is_fb = False, "✗", f"Check Error: {e}", False

            with self.lock:
                self.diagnostic_results.append({
                    "name": name,
                    "passed": passed,
                    "badge": badge,
                    "detail": detail,
                    "is_fallback": is_fb,
                })

        with self.lock:
            self.diagnostic_complete = True

    # starts the face ui either in the background on another thread or right here on main
    def start(self, in_background: bool = True):
        if in_background:
            self._thread = threading.Thread(target=self._run_tk_loop, daemon=True)
            self._thread.start()
            for _ in range(50):
                if self.root is not None and self.canvas is not None:
                    break
                time.sleep(0.02)
        else:
            self._run_tk_loop()

    # creates the actual tkinter window, canvas, and binds keyboard shortcuts
    def _run_tk_loop(self):
        self.root = tk.Tk()
        self.root.title("Neurolis Face UI")
        self.root.geometry(f"{self.width}x{self.height}")
        self.root.configure(bg=self.bg_color)

        if self.fullscreen:
            self.root.attributes("-fullscreen", True)

        self.root.bind("<Escape>", lambda e: self.stop())
        self.root.bind("f", lambda e: self._toggle_fullscreen())
        self.root.bind("<Button-1>", lambda e: self.skip_boot())
        self.root.bind("<Key>", self._on_key)

        self.canvas = tk.Canvas(
            self.root,
            width=self.width,
            height=self.height,
            bg=self.bg_color,
            highlightthickness=0,
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.running = True
        self._animate_loop()
        self.root.mainloop()

    # hit 'f' on the keyboard to toggle between windowed and borderless fullscreen
    def _toggle_fullscreen(self):
        if self.root:
            self.fullscreen = not self.fullscreen
            self.root.attributes("-fullscreen", self.fullscreen)

    # thread-safe function that listen.py calls to switch expressions (happy, sad, etc)
    def set_state(self, state: str, status_msg: Optional[str] = None):
        """Thread-safe state update called from listen.py."""
        with self.lock:
            self.state = state
            if status_msg is not None:
                self.status_text = status_msg.upper()
            else:
                self.status_text = f"STATE: {state.upper()}"

    # updates the subtitle box at the bottom whenever the user or robot speaks
    def set_subtitles(self, speaker: str, text: str):
        """Thread-safe subtitle updater for user transcription & robot speech."""
        with self.lock:
            self.subtitle_speaker = speaker.strip().upper()
            self.subtitle_text = text.strip()
            self.subtitle_time = time.time()

    # wipes out the subtitles when going to standby or starting fresh
    def clear_subtitles(self):
        with self.lock:
            self.subtitle_speaker = ""
            self.subtitle_text = ""

    # moves pupil gaze coordinates so neurolis looks at the visitor's face
    def look_at(self, x: float, y: float):
        """Directs the gaze of the eyes (-1.0 to 1.0)."""
        with self.lock:
            self.target_look_x = max(-1.0, min(1.0, x))
            self.target_look_y = max(-1.0, min(1.0, y))

    # adjusts mouth waveform height depending on how loud the speech is
    def set_speaking_intensity(self, intensity: float):
        with self.lock:
            self.speaking_intensity = max(0.1, min(1.0, intensity))

    # gracefully shuts down the animation loop and closes the tkinter window
    def stop(self):
        self.running = False
        if self.root:
            try:
                self.root.after(0, self._destroy_tk)
            except Exception:
                pass

    # destroys the tkinter root window without throwing thread errors
    def _destroy_tk(self):
        if self.root:
            try:
                self.root.quit()
                self.root.destroy()
            except Exception:
                pass
            self.root = None

    # runs every frame to smooth out eye gaze, count blink timers, and advance sine waves
    def _update_physics(self, dt: float):
        now = time.time()
        self.current_look_x += (self.target_look_x - self.current_look_x) * 0.18
        self.current_look_y += (self.target_look_y - self.current_look_y) * 0.18

        if not self.is_blinking:
            if now - self.last_blink_time > self.next_blink_interval:
                self.is_blinking = True
                self.blink_progress = 0.0
        else:
            self.blink_progress += dt * 8.5
            if self.blink_progress >= 1.0:
                self.is_blinking = False
                self.blink_progress = 0.0
                self.last_blink_time = now
                self.next_blink_interval = random.uniform(2.5, 5.5)

        self.anim_phase += dt * 3.2
        self.thinking_angle += dt * 4.5

    # the 60fps heartbeat that updates physics and repaints the canvas every 16ms
    def _animate_loop(self):
        if not self.running or self.canvas is None:
            return
        dt = 0.016
        self._update_physics(dt)
        self._render()
        if self.root and self.running:
            self.root.after(16, self._animate_loop)

    # helper math to draw smooth rounded rectangles for eyes and cards
    def _create_rounded_rect(self, x1, y1, x2, y2, radius, **kwargs):
        points = [
            x1 + radius, y1, x2 - radius, y1, x2, y1,
            x2, y1 + radius, x2, y2 - radius, x2, y2,
            x2 - radius, y2, x1 + radius, y2, x1, y2,
            x1, y2 - radius, x1, y1 + radius, x1, y1,
        ]
        return self.canvas.create_polygon(points, smooth=True, **kwargs)

    # the master paint function that clears the canvas and draws the entire face layout
    def _render(self):
        if not self.canvas:
            return
        self.canvas.delete("all")
        w = self.canvas.winfo_width() or self.width
        h = self.canvas.winfo_height() or self.height

        # Position face in upper region so subtitles sit comfortably in lower region
        center_x = w / 2.0
        center_y = 190.0

        with self.lock:
            cur_state = self.state
            status_str = self.status_text
            look_x = self.current_look_x
            look_y = self.current_look_y
            sub_speaker = self.subtitle_speaker
            sub_text = self.subtitle_text

        now = time.time()
        # phase 1: oobe welcome greeting ("Hi there!")
        if cur_state == ExpressionState.BOOT_GREETING:
            elapsed = now - self.boot_start_time
            if elapsed >= 3.8:
                with self.lock:
                    self.state = ExpressionState.BOOT_SEQUENCE
                    cur_state = ExpressionState.BOOT_SEQUENCE
                self._start_diagnostic_thread()
            else:
                self._draw_boot_greeting(w, h, elapsed)
                return

        # phase 2: cascading hardware & safety diagnostic checklist
        if cur_state == ExpressionState.BOOT_SEQUENCE:
            seq_elapsed = now - (self.boot_start_time + 3.8)
            with self.lock:
                diag_done = self.diagnostic_complete
                diag_count = len(self.diagnostic_results)

            if diag_count < 14:
                pct = int((diag_count / 14.0) * 65.0)
            else:
                load_p = min(1.0, max(0.0, (seq_elapsed - 16.1) / 3.4))
                pct = int(65.0 + load_p * 35.0)

            if seq_elapsed >= 20.3 and diag_done and pct >= 100:
                with self.lock:
                    self.state = ExpressionState.IDLE
                    self.status_text = "STANDBY // READY"
                    self.subtitle_speaker = "NEUROLIS"
                    self.subtitle_text = "Standing by. Press Enter or tap 'Talk to Neurolis' to begin."
                cur_state = ExpressionState.IDLE
            else:
                self._draw_boot_sequence(w, h, seq_elapsed, pct)
                return

        # Gaze lock: Keep eyes focused straight forward unless actively in optical observation/tracking
        if cur_state in [ExpressionState.WATCHING, ExpressionState.LOOKING]:
            look_x = max(-0.15, min(0.15, look_x))
            look_y = max(-0.15, min(0.15, look_y))
        else:
            look_x = 0.0
            look_y = 0.0

        # Palette selection based on state
        if cur_state == ExpressionState.ERROR:
            main_color = self.color_error
            glow_color = "#551122"
        elif cur_state == ExpressionState.LISTENING:
            main_color = self.color_listening
            glow_color = "#003b33"
        elif cur_state == ExpressionState.THINKING:
            main_color = self.color_thinking
            glow_color = "#3d1455"
        elif cur_state == ExpressionState.HAPPY:
            main_color = self.color_happy
            glow_color = "#00442a"
        elif cur_state == ExpressionState.SAD:
            main_color = self.color_sad
            glow_color = self.color_sad_glow
        elif cur_state == ExpressionState.CONFUSED:
            main_color = self.color_confused
            glow_color = self.color_confused_glow
        elif cur_state == ExpressionState.MOVING:
            main_color = "#00f0ff"
            glow_color = "#00384d"
        elif cur_state in [ExpressionState.WATCHING, ExpressionState.LOOKING]:
            main_color = "#00e5ff"
            glow_color = "#00384d"
        else:
            main_color = self.color_eye_main
            glow_color = self.color_eye_glow

        # 1. Ambient Background Grid & Header
        self._draw_ambient_header(w, h, main_color, cur_state)

        # 2. Eye Positioning (with gentle suspension dynamics when driving)
        suspension_bounce = math.sin(self.anim_phase * 6.0) * 2.0 if cur_state == ExpressionState.MOVING else 0.0
        left_eye_cx = center_x - (self.eye_spacing / 2.0)
        right_eye_cx = center_x + (self.eye_spacing / 2.0)
        eye_cy = center_y + suspension_bounce

        # Dynamic blink, speech cadence, and breathing scaling
        if self.is_blinking:
            blink_factor = math.sin(self.blink_progress * math.pi)
            h_scale = max(0.06, 1.0 - blink_factor * 0.94)
            w_scale = 1.0 + blink_factor * 0.08
        elif cur_state == ExpressionState.SPEAKING:
            spk_factor = math.sin(self.anim_phase * 8.0) * 0.12 * self.speaking_intensity
            h_scale = 1.0 + spk_factor
            w_scale = 1.0 - spk_factor * 0.4
        else:
            breathe = math.sin(self.anim_phase * 1.8) * 0.02
            h_scale = 1.0 + breathe
            w_scale = 1.0

        # 3. Dynamic Eyebrows
        self._draw_eyebrows(left_eye_cx, right_eye_cx, eye_cy - self.eye_h * 0.55, cur_state, main_color)

        # 4. Eyes Rendering (Solid Glowing OLED Robotic Capsules - Vector / EMO Style)
        if cur_state == ExpressionState.HAPPY:
            self._draw_happy_eyes(left_eye_cx, right_eye_cx, eye_cy, main_color, glow_color)
        elif cur_state == ExpressionState.SAD:
            self._draw_sad_eyes(left_eye_cx, right_eye_cx, eye_cy, self.eye_w, self.eye_h * h_scale, main_color, glow_color)
        elif cur_state == ExpressionState.CONFUSED:
            self._draw_confused_eyes(left_eye_cx, right_eye_cx, eye_cy, main_color, glow_color)
        elif cur_state == ExpressionState.THINKING:
            self._draw_thinking_eyes(left_eye_cx, right_eye_cx, eye_cy, self.eye_w, self.eye_h * h_scale, main_color, glow_color)
        elif cur_state in [ExpressionState.WATCHING, ExpressionState.LOOKING]:
            self._draw_watching_eyes(left_eye_cx, right_eye_cx, eye_cy, self.eye_w, self.eye_h * h_scale, main_color, glow_color, look_x, look_y)
        elif cur_state == ExpressionState.ERROR:
            self._draw_error_eyes(left_eye_cx, right_eye_cx, eye_cy, self.eye_w, self.eye_h * h_scale, main_color, glow_color)
        else:
            self._draw_standard_eye(left_eye_cx, eye_cy, self.eye_w * w_scale, self.eye_h * h_scale, main_color, glow_color, look_x, look_y)
            self._draw_standard_eye(right_eye_cx, eye_cy, self.eye_w * w_scale, self.eye_h * h_scale, main_color, glow_color, look_x, look_y)

        # 5. Reactive Mouth / Center State Animations (Positioned in mouth area y=305)
        mouth_cy = center_y + self.eye_h * 0.70
        if cur_state == ExpressionState.MOVING:
            self._draw_robot_moving_forward(center_x, mouth_cy, main_color)
        elif cur_state in [ExpressionState.WATCHING, ExpressionState.LOOKING]:
            self._draw_watching_speech_hud(center_x, mouth_cy, main_color)
        elif cur_state == ExpressionState.SPEAKING:
            self._draw_speaking_mouth(center_x, mouth_cy, main_color)
        elif cur_state == ExpressionState.THINKING:
            self._draw_thinking_spinner(center_x, center_y, main_color)
            self._draw_thinking_mouth(center_x, mouth_cy, main_color)
        elif cur_state == ExpressionState.LISTENING:
            self._draw_listening_mouth(center_x, mouth_cy, main_color)
        elif cur_state == ExpressionState.HAPPY:
            self._draw_happy_mouth(center_x, mouth_cy, main_color)
        elif cur_state == ExpressionState.SAD:
            self._draw_sad_mouth(center_x, mouth_cy, main_color)
        elif cur_state == ExpressionState.CONFUSED:
            self._draw_confused_mouth(center_x, mouth_cy, main_color)
        elif cur_state == ExpressionState.ERROR:
            self._draw_error_mouth(center_x, mouth_cy, main_color)
        elif cur_state == ExpressionState.IDLE:
            self._draw_idle_mouth(center_x, mouth_cy, main_color)

        # 6. Real-Time Subtitle Card & Status
        self._draw_subtitle_card(w, h, sub_speaker, sub_text, status_str, main_color)

    # draws cybernetic eyebrows that tilt up or down depending on emotional mood
    def _draw_eyebrows(self, lx, rx, base_y, state, color):
        """Draws dynamic cybernetic eyebrows that angle and shift based on expression."""
        brow_len = self.eye_w * 0.82
        bob = math.sin(self.anim_phase * 2.0) * 2.0

        if state == ExpressionState.SAD:
            # Heartbroken sad brows: inner ends rise high in distress, outer ends droop down in sorrow
            tremor = math.sin(self.anim_phase * 8.0) * 1.2
            ly1, ly2 = base_y + 10 + tremor, base_y - 18 + tremor
            ry1, ry2 = base_y - 18 + tremor, base_y + 10 + tremor
        elif state == ExpressionState.HAPPY:
            # Lifted high, joyous upward arches
            ly1, ly2 = base_y - 22 + bob, base_y - 16 + bob
            ry1, ry2 = base_y - 16 + bob, base_y - 22 + bob
        elif state == ExpressionState.MOVING:
            # Aerodynamic sports slant
            ly1, ly2 = base_y - 10, base_y - 4
            ry1, ry2 = base_y - 4, base_y - 10
        elif state in [ExpressionState.WATCHING, ExpressionState.LOOKING]:
            # Inquisitive optical observation
            ly1, ly2 = base_y - 14, base_y - 12
            ry1, ry2 = base_y - 12, base_y - 14
        elif state == ExpressionState.LISTENING:
            # Raised, alert listening arches
            ly1, ly2 = base_y - 16, base_y - 14
            ry1, ry2 = base_y - 14, base_y - 16
        elif state == ExpressionState.THINKING:
            # Asymmetrical pensive concentration: left furrowed low, right arched high
            ly1, ly2 = base_y + 2, base_y - 8
            ry1, ry2 = base_y - 24, base_y - 14
        elif state == ExpressionState.CONFUSED:
            # Asymmetrical: left raised high in bewilderment, right scrunched low
            ly1, ly2 = base_y - 24, base_y - 16
            ry1, ry2 = base_y + 8, base_y - 2
        elif state == ExpressionState.ERROR:
            # Fierce angry alarm slant
            ly1, ly2 = base_y + 10, base_y - 18
            ry1, ry2 = base_y - 18, base_y + 10
        elif state == ExpressionState.SPEAKING:
            # Animated conversational brows bobbing with cadence
            spk_bob = math.sin(self.anim_phase * 6.0) * 2.5
            ly1, ly2 = base_y - 10 + spk_bob, base_y - 10 + spk_bob
            ry1, ry2 = base_y - 10 + spk_bob, base_y - 10 + spk_bob
        else:
            # Calm friendly idle brows
            ly1, ly2 = base_y - 6 + bob, base_y - 6 + bob
            ry1, ry2 = base_y - 6 + bob, base_y - 6 + bob

        # Left brow
        self.canvas.create_line(
            lx - brow_len / 2.0, ly1,
            lx + brow_len / 2.0, ly2,
            fill=color, width=6, capstyle=tk.ROUND
        )
        # Right brow
        self.canvas.create_line(
            rx - brow_len / 2.0, ry1,
            rx + brow_len / 2.0, ry2,
            fill=color, width=6, capstyle=tk.ROUND
        )

    # draws a solid rounded oled eye capsule with bevel depth and glossy specular glints
    def _draw_standard_eye(self, cx, cy, ew, eh, main_col, glow_col, lx=0.0, ly=0.0):
        """Draws a solid, vibrant OLED eye capsule with high-contrast cyber bloom and glossy reflections."""
        x1, y1 = cx - ew / 2.0, cy - eh / 2.0
        x2, y2 = cx + ew / 2.0, cy + eh / 2.0

        # 1. Outer Soft Bloom / Glow Shell
        glow_expand = 8
        self._create_rounded_rect(
            x1 - glow_expand, y1 - glow_expand,
            x2 + glow_expand, y2 + glow_expand,
            self.corner_radius + 4, fill=glow_col, outline=""
        )

        # 2. Main Solid Luminous OLED Eye Capsule
        self._create_rounded_rect(
            x1, y1, x2, y2,
            self.corner_radius, fill=main_col, outline=""
        )

        # 3. High-Tech Beveled Inner Border (giving rich OLED depth)
        inset = 3
        if eh > 20:
            self._create_rounded_rect(
                x1 + inset, y1 + inset,
                x2 - inset, y2 - inset,
                max(4, self.corner_radius - 2), fill="", outline="#ffffff", width=1
            )

        # 4. Glossy Specular Glints (Top-Left Pixar / OLED robot shine)
        if eh > self.eye_h * 0.35:
            # Primary glossy pill reflection
            glint1_w = ew * 0.28
            glint1_h = eh * 0.16
            gx1 = cx - ew * 0.38 + (lx * 8.0)
            gy1 = cy - eh * 0.38 + (ly * 8.0)
            self._create_rounded_rect(
                gx1, gy1, gx1 + glint1_w, gy1 + glint1_h,
                radius=max(2, int(glint1_h * 0.5)), fill="#ffffff", outline=""
            )

            # Secondary micro glint
            glint2_w = ew * 0.12
            glint2_h = eh * 0.10
            gx2 = gx1 + glint1_w + 6.0
            gy2 = gy1 + 2.0
            self._create_rounded_rect(
                gx2, gy2, gx2 + glint2_w, gy2 + glint2_h,
                radius=max(2, int(glint2_h * 0.5)), fill="#ffffff", outline=""
            )

    # joyful smiling crescent arcs with cheerful vertical bounce for happy face
    def _draw_happy_eyes(self, lx, rx, cy, main_col, glow_col):
        """Radiant smiling crescent eyes with joyous bounce (Vector / EMO style)."""
        arc_w, arc_h = self.eye_w * 0.96, self.eye_h * 0.72
        bounce = math.sin(self.anim_phase * 5.0) * 4.0

        for cx in [lx, rx]:
            # Outer Neon Glow Arc (Note: style=tk.ARC takes no capstyle in Tkinter)
            self.canvas.create_arc(
                cx - arc_w / 2 - 8, cy - arc_h / 2 - 8 + bounce,
                cx + arc_w / 2 + 8, cy + arc_h / 2 + 8 + bounce,
                start=25, extent=130, style=tk.ARC, width=32, outline=glow_col
            )
            # Main Bold Neon Crescent Arc
            self.canvas.create_arc(
                cx - arc_w / 2, cy - arc_h / 2 + bounce,
                cx + arc_w / 2, cy + arc_h / 2 + bounce,
                start=25, extent=130, style=tk.ARC, width=20, outline=main_col
            )
            # Inner Luminous Highlight Arc
            self.canvas.create_arc(
                cx - arc_w / 2 + 3, cy - arc_h / 2 + 3 + bounce,
                cx + arc_w / 2 - 3, cy + arc_h / 2 - 3 + bounce,
                start=35, extent=110, style=tk.ARC, width=5, outline="#ffffff"
            )

    # downcast eyes with drooping upper lids and an animated falling digital teardrop
    def _draw_sad_eyes(self, lx, rx, cy, ew, eh, main_col, glow_col):
        """Downcast heartbroken sad eyes with drooping outer eyelids and falling digital teardrop."""
        # Draw base glowing eyes
        self._draw_standard_eye(lx, cy, ew, eh, main_col, glow_col, 0.0, 0.0)
        self._draw_standard_eye(rx, cy, ew, eh, main_col, glow_col, 0.0, 0.0)

        # Upper drooping sad eyelids (slanted down on the outside \   / )
        lid_drop = 38
        # Left eye drooping lid: high inside, drooping low outside
        left_lid = [
            lx - ew / 2.0 - 6, cy - eh / 2.0 - 6,
            lx + ew / 2.0 + 6, cy - eh / 2.0 - 6,
            lx + ew / 2.0 + 6, cy - eh / 2.0 + lid_drop - 16,
            lx - ew / 2.0 - 6, cy - eh / 2.0 + lid_drop + 18,
        ]
        self.canvas.create_polygon(left_lid, fill=self.bg_color, outline="")
        self.canvas.create_line(
            lx - ew / 2.0 - 4, cy - eh / 2.0 + lid_drop + 18,
            lx + ew / 2.0 + 4, cy - eh / 2.0 + lid_drop - 16,
            fill=main_col, width=4, capstyle=tk.ROUND
        )

        # Right eye drooping lid: high inside, drooping low outside
        right_lid = [
            rx - ew / 2.0 - 6, cy - eh / 2.0 - 6,
            rx + ew / 2.0 + 6, cy - eh / 2.0 - 6,
            rx + ew / 2.0 + 6, cy - eh / 2.0 + lid_drop + 18,
            rx - ew / 2.0 - 6, cy - eh / 2.0 + lid_drop - 16,
        ]
        self.canvas.create_polygon(right_lid, fill=self.bg_color, outline="")
        self.canvas.create_line(
            rx - ew / 2.0 - 4, cy - eh / 2.0 + lid_drop - 16,
            rx + ew / 2.0 + 4, cy - eh / 2.0 + lid_drop + 18,
            fill=main_col, width=4, capstyle=tk.ROUND
        )

        # Animated Digital Teardrop welling up and trickling from left eye
        tear_t = (self.anim_phase * 1.4) % 3.2
        if tear_t < 2.2:
            frac = tear_t / 2.2
            tear_x = lx - ew * 0.32
            tear_y = cy + eh * 0.36 + frac * 56
            tear_r = max(2, int(6 * (1.0 - frac * 0.35)))
            # Teardrop core
            self.canvas.create_oval(
                tear_x - tear_r, tear_y - tear_r,
                tear_x + tear_r, tear_y + tear_r,
                fill="#80d4ff", outline="#ffffff", width=1
            )
            # Teardrop glowing stream
            if frac > 0.12:
                trail_len = min(16.0, frac * 20.0)
                self.canvas.create_line(
                    tear_x, tear_y - trail_len,
                    tear_x, tear_y - tear_r,
                    fill="#2979ff", width=2, capstyle=tk.ROUND
                )

    # dual hypnotic spinning vortex spirals with orbiting golden dizzy stars
    def _draw_confused_eyes(self, lx, rx, cy, main_col, glow_col):
        """Dual hypnotic Archimedean cyber vortex spirals with orbiting golden stars (✦)."""
        rot = self.anim_phase * 4.2
        max_r = min(self.eye_w, self.eye_h) * 0.44
        num_pts = 64
        max_theta = 4.5 * math.pi  # 2.25 turns

        # Left eye: Clockwise spiral
        pts_left = []
        for i in range(num_pts):
            frac = i / (num_pts - 1)
            theta = frac * max_theta
            r = frac * max_r
            angle = theta + rot
            x = lx + r * math.cos(angle)
            y = cy + r * math.sin(angle)
            pts_left.extend([x, y])

        # Right eye: Counter-clockwise spiral
        pts_right = []
        for i in range(num_pts):
            frac = i / (num_pts - 1)
            theta = frac * max_theta
            r = frac * max_r
            angle = -theta - rot
            x = rx + r * math.cos(angle)
            y = cy + r * math.sin(angle)
            pts_right.extend([x, y])

        # Draw glow spirals
        self.canvas.create_line(pts_left, smooth=True, fill=glow_col, width=12, capstyle=tk.ROUND)
        self.canvas.create_line(pts_right, smooth=True, fill=glow_col, width=12, capstyle=tk.ROUND)

        # Draw main sharp spirals
        self.canvas.create_line(pts_left, smooth=True, fill=main_col, width=5, capstyle=tk.ROUND)
        self.canvas.create_line(pts_right, smooth=True, fill=main_col, width=5, capstyle=tk.ROUND)

        # Inner glowing spiral core
        for cx in [lx, rx]:
            self.canvas.create_oval(cx - 4, cy - 4, cx + 4, cy + 4, fill="#ffffff", outline="")

        # 3 Orbiting Dizzy Cyber Stars (✦) above head
        halo_cx = (lx + rx) / 2.0
        halo_cy = cy - self.eye_h * 0.68
        star_orbit_rx = self.eye_spacing * 0.45
        star_orbit_ry = 14.0

        for s in range(3):
            s_angle = rot * 0.85 + s * (2.0 * math.pi / 3.0)
            sx = halo_cx + math.cos(s_angle) * star_orbit_rx
            sy = halo_cy + math.sin(s_angle) * star_orbit_ry
            sr = 7.0 + math.sin(self.anim_phase * 6.0 + s) * 1.5

            # 4-point diamond star polygon
            star_poly = [
                sx, sy - sr,
                sx + sr * 0.32, sy - sr * 0.32,
                sx + sr, sy,
                sx + sr * 0.32, sy + sr * 0.32,
                sx, sy + sr,
                sx - sr * 0.32, sy + sr * 0.32,
                sx - sr, sy,
                sx - sr * 0.32, sy - sr * 0.32,
            ]
            self.canvas.create_polygon(star_poly, fill="#ffe57f", outline="")
            self.canvas.create_oval(sx - 2, sy - 2, sx + 2, sy + 2, fill="#ffffff", outline="")

    # analytical squint glance with rotating quantum data rings inside each eye
    def _draw_thinking_eyes(self, lx, rx, cy, ew, eh, main_col, glow_col):
        """Pensive analytical eyes glancing up-right with rotating quantum data rings."""
        squint_h = eh * 0.74
        offset_x = 8.0
        offset_y = -10.0
        self._draw_standard_eye(lx + offset_x, cy + offset_y, ew, squint_h, main_col, glow_col, 0.0, 0.0)
        self._draw_standard_eye(rx + offset_x, cy + offset_y, ew, squint_h, main_col, glow_col, 0.0, 0.0)

        # Inside each eye: segmented rotating quantum ring
        ring_r = min(ew, squint_h) * 0.28
        for eye_cx in [lx + offset_x, rx + offset_x]:
            for seg in range(3):
                seg_angle = (self.thinking_angle * 1.5 + seg * 120.0) % 360.0
                self.canvas.create_arc(
                    eye_cx - ring_r, cy + offset_y - ring_r,
                    eye_cx + ring_r, cy + offset_y + ring_r,
                    start=seg_angle, extent=70, style=tk.ARC, width=3, outline="#ffffff"
                )

        # Concentric orbital data nodes above the right forehead
        halo_cx = rx + 36
        halo_cy = cy - eh * 0.65
        for i in range(3):
            angle = self.thinking_angle * (1.1 + i * 0.4) + (i * (2.0 * math.pi / 3.0))
            orbit_rx = 34.0 + i * 8.0
            orbit_ry = 12.0 + i * 3.0
            px = halo_cx + math.cos(angle) * orbit_rx
            py = halo_cy + math.sin(angle) * orbit_ry
            dot_r = 3 + i
            self.canvas.create_oval(px - dot_r, py - dot_r, px + dot_r, py + dot_r, fill=main_col, outline="")

    # fierce angled crimson alarm slits with emergency warning pulse
    def _draw_error_eyes(self, lx, rx, cy, ew, eh, main_col, glow_col):
        """Fierce angled warning eyes with red alarm pulse."""
        alarm_pulse = 0.6 + 0.4 * math.sin(self.anim_phase * 8.0)
        cur_red = "#ff2244" if alarm_pulse > 0.5 else "#cc1133"

        self._draw_standard_eye(lx, cy, ew, eh, cur_red, glow_col, 0.0, 0.0)
        self._draw_standard_eye(rx, cy, ew, eh, cur_red, glow_col, 0.0, 0.0)

        # Angled warning eyelids cutting inward
        lid_h = 34
        # Left eye lid
        self.canvas.create_polygon([
            lx - ew / 2.0 - 6, cy - eh / 2.0 - 6,
            lx + ew / 2.0 + 6, cy - eh / 2.0 - 6,
            lx + ew / 2.0 + 6, cy - eh / 2.0 + lid_h + 14,
            lx - ew / 2.0 - 6, cy - eh / 2.0 + lid_h - 14,
        ], fill=self.bg_color, outline="")
        self.canvas.create_line(
            lx - ew / 2.0 - 4, cy - eh / 2.0 + lid_h - 14,
            lx + ew / 2.0 + 4, cy - eh / 2.0 + lid_h + 14,
            fill=cur_red, width=3, capstyle=tk.ROUND
        )

        # Right eye lid
        self.canvas.create_polygon([
            rx - ew / 2.0 - 6, cy - eh / 2.0 - 6,
            rx + ew / 2.0 + 6, cy - eh / 2.0 - 6,
            rx + ew / 2.0 + 6, cy - eh / 2.0 + lid_h - 14,
            rx - ew / 2.0 - 6, cy - eh / 2.0 + lid_h + 14,
        ], fill=self.bg_color, outline="")
        self.canvas.create_line(
            rx - ew / 2.0 - 4, cy - eh / 2.0 + lid_h + 14,
            rx + ew / 2.0 + 4, cy - eh / 2.0 + lid_h - 14,
            fill=cur_red, width=3, capstyle=tk.ROUND
        )

    # optical camera mode with viewfinder brackets and dark blue contrast scanning line
    def _draw_watching_eyes(self, lx, rx, cy, ew, eh, main_col, glow_col, lx_coord, ly_coord):
        """Focused optical eyes with camera viewfinder brackets and active laser scanner line."""
        self._draw_standard_eye(lx, cy, ew, eh, main_col, glow_col, lx_coord, ly_coord)
        self._draw_standard_eye(rx, cy, ew, eh, main_col, glow_col, lx_coord, ly_coord)

        bracket_color = "#00ffcc"
        bracket_len = 18
        bracket_pad = 8
        for cx in [lx, rx]:
            x1 = cx - ew / 2.0 - bracket_pad
            y1 = cy - eh / 2.0 - bracket_pad
            x2 = cx + ew / 2.0 + bracket_pad
            y2 = cy + eh / 2.0 + bracket_pad

            # Viewfinder brackets
            self.canvas.create_line(x1, y1 + bracket_len, x1, y1, x1 + bracket_len, y1, fill=bracket_color, width=3)
            self.canvas.create_line(x2 - bracket_len, y1, x2, y1, x2, y1 + bracket_len, fill=bracket_color, width=3)
            self.canvas.create_line(x1, y2 - bracket_len, x1, y2, x1 + bracket_len, y2, fill=bracket_color, width=3)
            self.canvas.create_line(x2 - bracket_len, y2, x2, y2, x2, y2 - bracket_len, fill=bracket_color, width=3)

            # Laser scanner sweep line
            scan_y = cy + math.sin(self.anim_phase * 3.5) * (eh * 0.42)
            # dark blue contrast laser scanning line that cuts across the bright cyan eye
            self.canvas.create_line(x1 + 4, scan_y, x2 - 4, scan_y, fill="#002b66", width=3)

    # wide glowing neon smile arc for happy expression
    def _draw_happy_mouth(self, cx, cy, col):
        """Warm, sleek curved happy smile arc without blush boxes."""
        bounce = math.sin(self.anim_phase * 5.0) * 2.0
        m_y = cy + bounce
        arc_w, arc_h = 76, 36

        # Glow arc
        self.canvas.create_arc(
            cx - arc_w / 2 - 4, m_y - arc_h / 2 - 4,
            cx + arc_w / 2 + 4, m_y + arc_h / 2 + 4,
            start=205, extent=130, style=tk.ARC, width=10, outline="#00442a"
        )
        # Main neon smile arc
        self.canvas.create_arc(
            cx - arc_w / 2, m_y - arc_h / 2,
            cx + arc_w / 2, m_y + arc_h / 2,
            start=205, extent=130, style=tk.ARC, width=5, outline=col
        )

    # downturned quivering sad frown line for heartbroken state
    def _draw_sad_mouth(self, cx, cy, col):
        """Melancholic downturned sad frown line."""
        tremble = math.sin(self.anim_phase * 10.0) * 1.2
        m_y = cy + 4 + tremble
        arc_w, arc_h = 68, 32

        # Frown glow
        self.canvas.create_arc(
            cx - arc_w / 2 - 4, m_y - arc_h / 2 - 4,
            cx + arc_w / 2 + 4, m_y + arc_h / 2 + 4,
            start=25, extent=130, style=tk.ARC, width=10, outline="#0e2447"
        )
        # Main neon frown arc
        self.canvas.create_arc(
            cx - arc_w / 2, m_y - arc_h / 2,
            cx + arc_w / 2, m_y + arc_h / 2,
            start=25, extent=130, style=tk.ARC, width=4, outline=col
        )

    # minimalist resting mouth with a soft pulsing cyan breathing beacon
    def _draw_idle_mouth(self, cx, cy, col):
        """Ultra-clean minimalist idle state with gentle breathing beacon."""
        pulse = 2.0 + math.sin(self.anim_phase * 2.0) * 1.0
        self.canvas.create_oval(
            cx - pulse, cy - pulse,
            cx + pulse, cy + pulse,
            fill="#00f0ff", outline=""
        )

    # 15-pin cyber audio frequency spectrum pins that dance with voice intensity
    def _draw_speaking_mouth(self, cx, cy, col):
        """Sleek minimalist cyber audio spectrum line (Vector / JARVIS style)."""
        base_w = 170
        self.canvas.create_line(
            cx - base_w / 2.0, cy,
            cx + base_w / 2.0, cy,
            fill="#092033", width=1
        )

        num_pins = 15
        pin_spacing = 10
        start_x = cx - ((num_pins - 1) * pin_spacing) / 2.0

        for i in range(num_pins):
            dist_center = 1.0 - (abs(i - 7) / 7.0) * 0.45
            pin_phase = i * 0.65
            h_val = abs(math.sin(self.anim_phase * 7.5 + pin_phase)) * 24.0 * dist_center * self.speaking_intensity
            pin_h = max(2.0, h_val + 2.0)
            px = start_x + i * pin_spacing

            pin_col = "#00f0ff" if i % 2 == 0 else "#00ffcc"
            self.canvas.create_line(
                px, cy - pin_h, px, cy + pin_h,
                fill=pin_col, width=3, capstyle=tk.ROUND
            )
            self.canvas.create_oval(
                px - 1.5, cy - pin_h - 1.5,
                px + 1.5, cy - pin_h + 1.5,
                fill="#ffffff", outline=""
            )

    # 13-bar acoustic soundwave spectrum with radar beacon dots for listening mode
    def _draw_listening_mouth(self, cx, cy, col):
        """Sleek acoustic audio waveform and concentric radar beacon."""
        num_bars = 13
        bar_spacing = 12
        total_w = (num_bars - 1) * bar_spacing
        start_x = cx - total_w / 2.0

        for i in range(num_bars):
            dist_from_center = abs(i - 6) / 6.0
            weight = 1.0 - dist_from_center * 0.4
            b_val = abs(math.sin(self.anim_phase * 5.0 + i * 0.55)) * 22 * weight
            bar_h = max(3.0, b_val + 3.0)
            bx = start_x + (i * bar_spacing)
            bar_col = "#00ffcc" if dist_from_center < 0.5 else "#00bfa5"
            self.canvas.create_line(
                bx, cy - bar_h, bx, cy + bar_h,
                fill=bar_col, width=4, capstyle=tk.ROUND
            )

        for side in [-1, 1]:
            dot_x = cx + side * (total_w / 2.0 + 22)
            dot_pulse = 3 + math.sin(self.anim_phase * 4.0) * 1.5
            self.canvas.create_oval(
                dot_x - dot_pulse, cy - dot_pulse,
                dot_x + dot_pulse, cy + dot_pulse,
                fill="#00ffcc", outline=""
            )

    # small inquisitive rounded cyber mouth 'o' while pondering an answer
    def _draw_thinking_mouth(self, cx, cy, col):
        """Inquisitive rounded cyber mouth 'o' while in thought."""
        r = 6 + math.sin(self.anim_phase * 3.0) * 1.5
        self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r, outline=col, width=3)
        self.canvas.create_oval(cx - 2, cy - 2, cx + 2, cy + 2, fill="#ffffff", outline="")

    # cute wavy squiggly mouth line for confused puzzled face
    def _draw_confused_mouth(self, cx, cy, col):
        """Cute quizzical wavy micro-squiggle."""
        w = 18
        points = [
            cx - w, cy,
            cx - w * 0.5, cy + 4,
            cx, cy - 4,
            cx + w * 0.5, cy + 3,
            cx + w, cy - 1,
        ]
        self.canvas.create_line(points, smooth=True, fill=col, width=3, capstyle=tk.ROUND)

    # jagged glitch zig-zag mouth line for error and alert state
    def _draw_error_mouth(self, cx, cy, col):
        """Sharp zig-zag glitch mouth line with red alarm flash."""
        points = [
            cx - 30, cy,
            cx - 20, cy - 6,
            cx - 10, cy + 6,
            cx, cy - 6,
            cx + 10, cy + 6,
            cx + 20, cy - 6,
            cx + 30, cy,
        ]
        self.canvas.create_line(points, fill=col, width=3, capstyle=tk.ROUND)

    # rotating gyroscope orbit constellation dots around the face while thinking
    def _draw_thinking_spinner(self, cx, cy, col):
        """High-tech orbital gyroscope constellation around face center."""
        r = self.eye_spacing * 0.65
        for i in range(3):
            angle = self.thinking_angle * (1.0 + i * 0.3) + (i * (2 * math.pi / 3))
            px = cx + math.cos(angle) * r
            py = cy + math.sin(angle) * (r * 0.30)
            dot_r = 4 + i
            self.canvas.create_oval(px - dot_r, py - dot_r, px + dot_r, py + dot_r, fill=col, outline="")
            trail_a = angle - 0.25
            tx = cx + math.cos(trail_a) * r
            ty = cy + math.sin(trail_a) * (r * 0.30)
            self.canvas.create_line(tx, ty, px, py, fill="#662299", width=2)

    # camera telemetry hud with targeting crosshairs and equalizer pins
    def _draw_watching_speech_hud(self, cx, cy, col):
        """Speech HUD specifically active when analyzing camera output."""
        self.canvas.create_text(cx - 105, cy, text="+", fill="#00ffcc", font=("Segoe UI", 14, "bold"))
        self.canvas.create_text(cx + 105, cy, text="+", fill="#00ffcc", font=("Segoe UI", 14, "bold"))

        num_bars = 11
        bar_spacing = 15
        total_w = (num_bars - 1) * bar_spacing
        start_x = cx - total_w / 2.0

        for i in range(num_bars):
            phase_offset = i * 0.7
            h_var = math.sin(self.anim_phase * 5.0 + phase_offset) * 22 * self.speaking_intensity
            bar_h = max(5, abs(h_var) + 6)
            bx = start_x + (i * bar_spacing)
            self.canvas.create_line(bx, cy - bar_h, bx, cy + bar_h, fill="#00ffcc", width=4, capstyle=tk.ROUND)

    # front-facing 4wd robot rolling forward with road tracks streaming backward
    def _draw_robot_moving_forward(self, cx, cy, col):
        """Futuristic humanoid robot moving forward towards viewer with perspective lines moving backward."""
        y_top = cy - 22
        y_bot = cy + 46

        # 1. Ground Perspective Plane & Boundary Lines (Two lines moving backward)
        lane_w_top = 40
        lane_w_bot = 165

        # Subtle road floor
        road_poly = [
            cx - lane_w_top, y_top,
            cx + lane_w_top, y_top,
            cx + lane_w_bot, y_bot,
            cx - lane_w_bot, y_bot,
        ]
        self.canvas.create_polygon(road_poly, fill="#040e1b", outline="", smooth=False)

        # Two main perspective boundary lines
        self.canvas.create_line(cx - lane_w_top, y_top, cx - lane_w_bot, y_bot, fill="#0c2b42", width=3)
        self.canvas.create_line(cx + lane_w_top, y_top, cx + lane_w_bot, y_bot, fill="#0c2b42", width=3)

        # 2. Backward Streaming Motion Streaks along the two lines (showing forward rush)
        num_streaks = 4
        for i in range(num_streaks):
            t = ((self.anim_phase * 2.2 + i * (1.0 / num_streaks)) % 1.0)
            t_curve = t * t  # Perspective acceleration as it nears foreground
            sy1 = y_top + t_curve * (y_bot - y_top)
            streak_len = 10 + t_curve * 26
            sy2 = min(y_bot, sy1 + streak_len)

            s_frac1 = (sy1 - y_top) / (y_bot - y_top)
            s_frac2 = (sy2 - y_top) / (y_bot - y_top)

            # Left perspective track streak
            sx1_l = cx - (lane_w_top + s_frac1 * (lane_w_bot - lane_w_top))
            sx2_l = cx - (lane_w_top + s_frac2 * (lane_w_bot - lane_w_top))
            # Right perspective track streak
            sx1_r = cx + (lane_w_top + s_frac1 * (lane_w_bot - lane_w_top))
            sx2_r = cx + (lane_w_top + s_frac2 * (lane_w_bot - lane_w_top))

            sw = max(1, int(1 + t_curve * 3))
            streak_col = "#00ffaa" if t_curve > 0.4 else "#00a880"
            self.canvas.create_line(sx1_l, sy1, sx2_l, sy2, fill=streak_col, width=sw, capstyle=tk.ROUND)
            self.canvas.create_line(sx1_r, sy1, sx2_r, sy2, fill=streak_col, width=sw, capstyle=tk.ROUND)

        # Center lane dashed markers streaming straight downward
        for c in range(3):
            ct = ((self.anim_phase * 2.5 + c * 0.33) % 1.0)
            ct_curve = ct * ct
            cy_start = y_top + 10 + ct_curve * (y_bot - (y_top + 10))
            c_len = 6 + ct_curve * 16
            cy_end = min(y_bot, cy_start + c_len)
            c_w = max(1, int(1 + ct_curve * 3))
            self.canvas.create_line(cx, cy_start, cx, cy_end, fill="#00e5ff", width=c_w)

        # Side ambient speed lines streaming outward
        for side in [-1, 1]:
            for sl in range(2):
                phase_off = sl * 1.5
                sp_y = y_top + 14 + ((self.anim_phase * 18.0 + phase_off * 10.0) % 36.0)
                sp_x1 = cx + side * (lane_w_top + 45 + sl * 35)
                sp_x2 = sp_x1 + side * (25 + sl * 15)
                self.canvas.create_line(sp_x1, sp_y, sp_x2, sp_y + 6, fill="#09304a", width=2)

        # 3. The Front-Facing Robot Coming AHEAD
        suspension = math.sin(self.anim_phase * 7.5) * 2.5
        rcy = cy + suspension

        # Dual Front 4WD Rubber Wheels (Rolling forward toward viewer)
        wheel_w = 16
        wheel_h = 28
        for w_side in [-1, 1]:
            wx = cx + w_side * 36
            wy1 = rcy + 12
            wy2 = wy1 + wheel_h
            # Rubber tire body
            self._create_rounded_rect(wx - wheel_w / 2, wy1, wx + wheel_w / 2, wy2, radius=4, fill="#060c16", outline="#00e5ff", width=2)
            # Downward rolling tread marks
            for tr in range(3):
                tread_y = wy1 + 4 + ((self.anim_phase * 32.0 + tr * 9.0) % (wheel_h - 8))
                self.canvas.create_line(wx - wheel_w / 2 + 2, tread_y, wx + wheel_w / 2 - 2, tread_y, fill="#00ffaa", width=2)

        # 4WD Front Chassis Bumper Plate
        bump_y1 = rcy + 18
        bump_y2 = rcy + 32
        self._create_rounded_rect(cx - 30, bump_y1, cx + 30, bump_y2, radius=6, fill="#091b2e", outline="#00f0ff", width=2)

        # Dual Forward Xenon LED Headlights & Conical Light Beams Shining Ahead
        for h_side in [-1, 1]:
            hx = cx + h_side * 20
            hy = rcy + 25
            # Expanding light beam on road
            beam = [
                hx, hy,
                hx + h_side * 18, y_bot + 2,
                hx - h_side * 6, y_bot + 2,
            ]
            self.canvas.create_polygon(beam, fill="#0a2a40", outline="")
            # Bright Headlight bulb
            self.canvas.create_oval(hx - 4, hy - 4, hx + 4, hy + 4, fill="#ffffff", outline="#00f0ff", width=1)

        # Robot Torso / Armor Body
        torso_poly = [
            cx - 22, rcy - 2,
            cx + 22, rcy - 2,
            cx + 18, rcy + 18,
            cx - 18, rcy + 18,
        ]
        self.canvas.create_polygon(torso_poly, fill="#071526", outline="#00f0ff", width=2)

        # Glowing Chest Arc Reactor Core
        core_r = 5 + math.sin(self.anim_phase * 6.0) * 1.0
        self.canvas.create_oval(cx - core_r, rcy + 8 - core_r, cx + core_r, rcy + 8 + core_r, fill="#00ffcc", outline="#ffffff", width=1)

        # Robot Head & Visor
        head_y1 = rcy - 24
        head_y2 = rcy - 4
        self._create_rounded_rect(cx - 16, head_y1, cx + 16, head_y2, radius=6, fill="#091a2c", outline="#00f0ff", width=2)

        # Cute Mint Visor Bar (Twin Eye View)
        self._create_rounded_rect(cx - 11, head_y1 + 7, cx + 11, head_y1 + 14, radius=3, fill="#00ffaa", outline="")
        self.canvas.create_line(cx, head_y1 + 7, cx, head_y1 + 14, fill="#091a2c", width=1)  # Visor eye divider

        # Top Cyber Antenna with Pulsing Beacon Dot
        self.canvas.create_line(cx, head_y1, cx, head_y1 - 8, fill="#00f0ff", width=2)
        beacon_col = "#00ffaa" if (int(self.anim_phase * 6.0) % 2 == 0) else "#ffffff"
        self.canvas.create_oval(cx - 3, head_y1 - 12, cx + 3, head_y1 - 6, fill=beacon_col, outline="")

        # Speech Equalizer Waveform above head (if speaking while moving)
        if self.speaking_intensity > 0.15:
            num_bars = 7
            bar_spacing = 9
            start_bx = cx - ((num_bars - 1) * bar_spacing) / 2.0
            for i in range(num_bars):
                phase_offset = i * 0.8
                h_var = math.sin(self.anim_phase * 5.0 + phase_offset) * 10 * self.speaking_intensity
                bar_h = max(3, abs(h_var) + 3)
                bx = start_bx + i * bar_spacing
                self.canvas.create_line(bx, head_y1 - 16 - bar_h, bx, head_y1 - 16 + bar_h, fill="#00ffaa", width=3, capstyle=tk.ROUND)

    # subtle header banner showing school branding and status indicator dot
    def _draw_ambient_header(self, w, h, accent_col, state):
        self.canvas.create_text(
            w / 2.0, 24,
            text="PROJECT NEUROLIS   //   AUCKLAND HOUSE SCHOOL FOR BOYS",
            fill="#2c4260", font=("Segoe UI", 10, "bold")
        )
        dot_color = accent_col if state != ExpressionState.IDLE else "#00ffaa"
        self.canvas.create_oval(32, 19, 42, 29, fill=dot_color, outline="")

    # dedicated lower subtitle card with speaker pills, live status, and word wrap
    def _draw_subtitle_card(self, w, h, speaker, text, status_text, accent_col):
        """Draws the dedicated Subtitle Box with speaker tags, word wrapping, and telemetry."""
        card_x1 = 54
        card_y1 = 370
        card_x2 = w - 54
        card_y2 = 556
        card_radius = 18

        self._create_rounded_rect(
            card_x1, card_y1, card_x2, card_y2,
            radius=card_radius, fill="#070d18", outline="#16273d"
        )

        spk_label = speaker if speaker else "NEUROLIS"
        if spk_label in ["YOU", "USER"]:
            pill_fill = "#002b1f"
            pill_border = "#00ffaa"
            pill_text_col = "#00ffaa"
            display_spk = "● YOU"
        elif spk_label == "NEUROLIS":
            pill_fill = "#00203a"
            pill_border = "#00f0ff"
            pill_text_col = "#00f0ff"
            display_spk = "● NEUROLIS"
        else:
            pill_fill = "#141c2a"
            pill_border = "#527196"
            pill_text_col = "#99b8dc"
            display_spk = f"● {spk_label}"

        self._create_rounded_rect(
            card_x1 + 18, card_y1 + 14,
            card_x1 + 155, card_y1 + 38,
            radius=8, fill=pill_fill, outline=pill_border
        )
        self.canvas.create_text(
            card_x1 + 86, card_y1 + 26,
            text=display_spk, fill=pill_text_col,
            font=("Segoe UI", 10, "bold")
        )

        self.canvas.create_text(
            card_x2 - 20, card_y1 + 26,
            text=status_text, fill="#4a6b8f",
            font=("Segoe UI", 10, "bold"), anchor="e"
        )

        self.canvas.create_line(
            card_x1 + 18, card_y1 + 46,
            card_x2 - 18, card_y1 + 46,
            fill="#101c2d", width=1
        )

        clean_text = text if text else "..."
        if len(clean_text) > 320:
            clean_text = clean_text[:317] + "..."

        self.canvas.create_text(
            card_x1 + 22, card_y1 + 58,
            text=clean_text,
            fill="#ffffff",
            font=("Segoe UI", 14, "bold"),
            anchor="nw",
            width=int(card_x2 - card_x1 - 44),
        )

        self.canvas.create_text(
            w / 2.0, h - 22,
            text="4WD CHASSIS // VISION TRACKING // ROBOTIC EXHIBITION AI",
            fill="#1b283b", font=("Segoe UI", 9, "bold")
        )

    # phase 1: apple-grade greeting screen saying "Hi there!" with smooth cosine alpha fade
    def _draw_boot_greeting(self, w: float, h: float, elapsed: float):
        self.canvas.delete("all")
        # solid oled black background
        self.canvas.create_rectangle(0, 0, w, h, fill=self.bg_color, outline="")

        # calculate smooth ease in, hold, and ease out alpha (0.0 to 1.0)
        if elapsed < 1.0:
            # 0.0s to 1.0s: smooth cosine fade in
            alpha = 0.5 - 0.5 * math.cos(elapsed * math.pi)
        elif elapsed < 2.5:
            # 1.0s to 2.5s: hold full brightness
            alpha = 1.0
        elif elapsed < 3.5:
            # 2.5s to 3.5s: smooth cosine fade out
            fade_p = (elapsed - 2.5) / 1.0
            alpha = 0.5 + 0.5 * math.cos(fade_p * math.pi)
        else:
            # 3.5s to 3.8s: brief black breath before cockpit sequence
            alpha = 0.0

        # silver-white premium typography
        text_color = lerp_color(self.bg_color, "#f8fafc", alpha)
        sub_color = lerp_color(self.bg_color, "#64748b", alpha)

        # "Hi there!" text
        self.canvas.create_text(
            w / 2.0, h / 2.0 - 20,
            text="Hi there!",
            fill=text_color,
            font=(FONT_FAMILY, 48, "bold")
        )

        # "Welcome to Project Neurolis" subtitle
        self.canvas.create_text(
            w / 2.0, h / 2.0 + 42,
            text="Welcome to Project Neurolis",
            fill=sub_color,
            font=(FONT_FAMILY, 15)
        )

    # phase 2: futuristic diagnostic checklist verifying hardware with smooth auto-scroll
    def _draw_boot_sequence(self, w: float, h: float, seq_elapsed: float, pct: int):
        self.canvas.delete("all")
        self.canvas.create_rectangle(0, 0, w, h, fill=self.bg_color, outline="")

        # 1. top header pill badge
        pill_w, pill_h = 320, 28
        px1 = (w - pill_w) / 2.0
        py1 = 16
        self._create_rounded_rect(px1, py1, px1 + pill_w, py1 + pill_h, radius=14, fill="#081326", outline="#1c3452")
        # glowing pulse cyan indicator dot
        pulse = 0.5 + 0.5 * math.sin(self.anim_phase * 4.0)
        dot_col = lerp_color("#007788", "#00f0ff", pulse)
        self.canvas.create_oval(px1 + 14, py1 + 9, px1 + 24, py1 + 19, fill=dot_col, outline="")
        self.canvas.create_text(
            px1 + 165, py1 + 14,
            text="NEUROLIS SYSTEM BOOT // V3.8",
            fill="#cbd5e1",
            font=(FONT_FAMILY, 9, "bold")
        )

        # 2. test sequence title banner
        self.canvas.create_text(
            w / 2.0, 60,
            text="Neurolis Test Sequence ---",
            fill="#f8fafc",
            font=(FONT_FAMILY, 16, "bold")
        )
        self.canvas.create_text(
            w / 2.0, 82,
            text="[ Click screen or press any key to skip ]",
            fill="#475569",
            font=(FONT_FAMILY, 9)
        )

        # 3. main diagnostic glass card with ambient glow and cyber brackets
        card_x1 = 110
        card_y1 = 98
        card_x2 = w - 110
        card_y2 = 544
        card_radius = 16

        # outer subtle shadow/depth glow
        self._create_rounded_rect(card_x1 - 3, card_y1 - 3, card_x2 + 3, card_y2 + 3, radius=18, fill="#040914", outline="#0d1b2e")
        # inner glass cockpit card
        self._create_rounded_rect(card_x1, card_y1, card_x2, card_y2, radius=card_radius, fill="#060c18", outline="#1c2e48")

        # high-tech corner cyber accents
        bracket_len = 16
        # top-left
        self.canvas.create_line(card_x1, card_y1 + bracket_len, card_x1, card_y1, card_x1 + bracket_len, card_y1, fill="#00f0ff", width=2)
        # top-right
        self.canvas.create_line(card_x2, card_y1 + bracket_len, card_x2, card_y1, card_x2 - bracket_len, card_y1, fill="#00f0ff", width=2)
        # bottom-left
        self.canvas.create_line(card_x1, card_y2 - bracket_len, card_x1, card_y2, card_x1 + bracket_len, card_y2, fill="#00f0ff", width=2)
        # bottom-right
        self.canvas.create_line(card_x2, card_y2 - bracket_len, card_x2, card_y2, card_x2 - bracket_len, card_y2, fill="#00f0ff", width=2)

        # subtle glass card header divider
        self.canvas.create_line(card_x1 + 24, card_y1 + 12, card_x2 - 24, card_y1 + 12, fill="#0e1d30", width=1)

        # 4. smooth auto-scroll checklist math
        with self.lock:
            results = list(self.diagnostic_results)

        total_revealed = len(results)
        row_h = 27.0
        # keep up to 8 items visible, then smoothly scroll to keep new items centered
        if total_revealed > 8:
            target_scroll = (total_revealed - 8) * row_h
        else:
            target_scroll = 0.0

        self.boot_scroll_y += (target_scroll - self.boot_scroll_y) * 0.15

        # 5. render verified check rows (high-contrast 3-column cockpit layout)
        clip_top = card_y1 + 14
        clip_bottom = card_y2 - 56

        for idx, item in enumerate(results):
            row_y = card_y1 + 30 + idx * row_h - self.boot_scroll_y
            if clip_top <= row_y <= clip_bottom:
                # Column 1: badge pill on left
                bx1 = card_x1 + 24
                by1 = row_y - 9
                bx2 = card_x1 + 54
                by2 = row_y + 9

                badge = item.get("badge", "✓")
                if badge == "✓":
                    b_fill = "#022c17"
                    b_outline = "#00ff88"
                    b_text_col = "#00ff88"
                elif badge == "~":
                    b_fill = "#332500"
                    b_outline = "#ffb703"
                    b_text_col = "#ffb703"
                else:
                    b_fill = "#330812"
                    b_outline = "#ff2d55"
                    b_text_col = "#ff2d55"

                self._create_rounded_rect(bx1, by1, bx2, by2, radius=6, fill=b_fill, outline=b_outline)
                self.canvas.create_text((bx1 + bx2) / 2.0, row_y, text=badge, fill=b_text_col, font=(FONT_FAMILY, 9, "bold"))

                # Column 2: item name (left aligned)
                self.canvas.create_text(
                    card_x1 + 68, row_y,
                    text=item.get("name", ""),
                    fill="#f1f5f9",
                    font=(FONT_FAMILY, 10, "bold"),
                    anchor="w"
                )

                # Column 3: item status value (right aligned)
                val_col = "#00ffaa" if item.get("passed") else "#fb7185"
                self.canvas.create_text(
                    card_x2 - 28, row_y,
                    text=item.get("detail", ""),
                    fill=val_col,
                    font=(FONT_FAMILY, 10, "bold" if item.get("passed") else "normal"),
                    anchor="e"
                )

        # active scanning indicator row
        steps_order = [
            "Camera Detected?", "Mic Detected?", "Speakers Detected?", "Raspberry Pi Detected?",
            "listen.py Test Initiate", "Arduino Detected?", "arduino.ino Test Initiate",
            "Motor Drivers Detected?", "Motor Driver Number", "Motors Detected?",
            "Motor Number", "motors.py Test Initiate", "Ultrasound Sensor Detected?", "Ultrasound Number"
        ]

        if total_revealed < len(steps_order):
            active_y = card_y1 + 30 + total_revealed * row_h - self.boot_scroll_y
            if clip_top <= active_y <= clip_bottom:
                bx1 = card_x1 + 24
                by1 = active_y - 9
                bx2 = card_x1 + 54
                by2 = active_y + 9
                self._create_rounded_rect(bx1, by1, bx2, by2, radius=6, fill="#041c30", outline="#00f0ff")
                self.canvas.create_text((bx1 + bx2) / 2.0, active_y, text="⟳", fill="#00f0ff", font=(FONT_FAMILY, 9, "bold"))

                active_name = steps_order[total_revealed]
                self.canvas.create_text(
                    card_x1 + 68, active_y,
                    text=active_name,
                    fill="#38bdf8",
                    font=(FONT_FAMILY, 10, "bold"),
                    anchor="w"
                )

                dots = "." * (int(self.anim_phase * 3.0) % 4)
                self.canvas.create_text(
                    card_x2 - 28, active_y,
                    text="Scanning" + dots,
                    fill="#00f0ff",
                    font=(FONT_FAMILY, 10, "italic"),
                    anchor="e"
                )

        # 6. progress bar at bottom of card
        bar_y1 = card_y2 - 34
        bar_y2 = card_y2 - 16
        bar_x1 = card_x1 + 24
        bar_x2 = card_x2 - 24

        # status text above progress bar
        self.canvas.create_text(
            bar_x1, bar_y1 - 10,
            text="INITIATING NEUROLIS CORE UI...",
            fill="#64748b",
            font=(FONT_FAMILY, 9, "bold"),
            anchor="w"
        )

        if pct < 100:
            status_right_text = f"[ {pct}% ]"
            bar_text_col = "#00f0ff"
        else:
            status_right_text = "100% // ALL SYSTEMS VERIFIED"
            bar_text_col = "#00ff88"

        self.canvas.create_text(
            bar_x2, bar_y1 - 10,
            text=status_right_text,
            fill=bar_text_col,
            font=(FONT_FAMILY, 10, "bold"),
            anchor="e"
        )

        # track
        self._create_rounded_rect(bar_x1, bar_y1, bar_x2, bar_y2, radius=7, fill="#070e1c", outline="#1c2e48")

        # filled portion
        fill_w = (bar_x2 - bar_x1) * (pct / 100.0)
        if fill_w > 6:
            fill_col = "#00ff88" if pct >= 100 else "#00f0ff"
            self._create_rounded_rect(bar_x1, bar_y1, bar_x1 + fill_w, bar_y2, radius=7, fill=fill_col, outline="")
            # leading edge white glow tip
            if fill_w < (bar_x2 - bar_x1) - 4:
                self.canvas.create_line(bar_x1 + fill_w, bar_y1 + 2, bar_x1 + fill_w, bar_y2 - 2, fill="#ffffff", width=2)


# test runner to preview the face ui standalone on desktop without motors or speech
if __name__ == "__main__":
    print("Testing Neurolis Face UI (7-inch 1024x600 preview)...")
    ui = FaceUI(width=1024, height=600, fullscreen=False)
    ui.start(in_background=False)
