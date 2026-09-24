"""
Project Neurolis - Localhost Manual Web Controller & Hardware Calibrator
========================================================================
Runs a modern, dark OLED cyber cockpit web app on http://localhost:5000
Connects directly to Arduino Mega 2560 via USB Serial (115200 baud).

Features:
  1. Manual Teleoperation: Keyboard (WASD/Arrows/Space) and Touch D-Pad.
  2. Motor Polarity Calibrator: Pulse M1, M2, M3, M4 individually to verify wiring.
  3. Real-Time 16-Sensor Ultrasonic Radar: Live cm distance readouts with obstacle guards.
  4. Hardware Hot-Plug & Auto-Detection: Auto-detects COM ports with fallback simulation mode.
  5. Zero External Dependencies: Pure Python standard library (http.server + json).
"""

import os
import sys
import json
import time
import socket
import threading
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from typing import Optional, List, Dict, Any

# Try importing pyserial for physical hardware communication
try:
    import serial
    import serial.tools.list_ports
    HAS_SERIAL = True
except ImportError:
    HAS_SERIAL = False

# ================= Global Hardware Controller State =================
class ArduinoBridge:
    def __init__(self):
        self.ser: Optional[Any] = None
        self.port: Optional[str] = None
        self.is_connected = False
        self.is_simulated = False
        self.lock = threading.Lock()
        self.running = True

        # Telemetry state
        self.dist_front = 999.0
        self.dist_left = 999.0
        self.dist_right = 999.0
        self.dist_rear = 999.0
        self.active_sensor_count = 0
        self.sensors_all: List[float] = [999.0] * 16

        # Motion state
        self.current_speed = 0
        self.current_steer = 0
        self.last_cmd_time = 0.0

        # Raw log ring buffer
        self.log_history: List[str] = []

        # Start background reader thread
        self.rx_thread = threading.Thread(target=self._rx_loop, daemon=True)
        self.rx_thread.start()

        # Attempt initial auto-connect
        self.auto_connect()

    def add_log(self, text: str):
        with self.lock:
            timestamp = time.strftime("%H:%M:%S")
            self.log_history.append(f"[{timestamp}] {text}")
            if len(self.log_history) > 60:
                self.log_history.pop(0)

    def list_ports(self) -> List[Dict[str, str]]:
        if not HAS_SERIAL:
            return [{"device": "VIRTUAL_COM1", "description": "Virtual Simulation Port (PySerial not installed)"}]
        ports = []
        try:
            for p in serial.tools.list_ports.comports():
                ports.append({
                    "device": p.device,
                    "description": p.description or p.device
                })
        except Exception:
            pass
        if not ports:
            ports.append({"device": "VIRTUAL_COM1", "description": "No physical COM ports found (Simulation Available)"})
        return ports

    def auto_connect(self):
        if not HAS_SERIAL:
            self.enter_simulation("PySerial library not installed (pip install pyserial).")
            return

        ports = list(serial.tools.list_ports.comports())
        target_port = None
        for p in ports:
            desc = (p.description or "").lower()
            hwid = (p.hwid or "").lower()
            if any(k in desc or k in hwid for k in ["arduino", "mega", "ch340", "cp210", "usb serial"]):
                target_port = p.device
                break

        # On Linux/Pi prioritize /dev/ttyACM0 or /dev/ttyUSB0
        if not target_port and sys.platform.startswith("linux"):
            for candidate in ["/dev/ttyACM0", "/dev/ttyACM1", "/dev/ttyUSB0", "/dev/ttyUSB1"]:
                if os.path.exists(candidate):
                    target_port = candidate
                    break

        if target_port:
            self.connect(target_port)
        elif ports:
            self.connect(ports[0].device)
        else:
            self.enter_simulation("No physical Arduino Mega detected on USB.")

    def connect(self, port_name: str):
        if not HAS_SERIAL or "VIRTUAL" in port_name:
            self.enter_simulation("Connected to Virtual Physics Simulation.")
            return

        self.disconnect()
        try:
            self.ser = serial.Serial(port_name, 115200, timeout=0.08)
            time.sleep(1.2)  # Allow Arduino bootloader to initialize
            self.port = port_name
            self.is_connected = True
            self.is_simulated = False
            self.add_log(f"Connected to Arduino Mega on {port_name} @ 115200 baud.")
            print(f"[ManualControl] Connected to physical Arduino on {port_name}")
        except Exception as e:
            self.enter_simulation(f"Failed to open {port_name}: {e}")

    def enter_simulation(self, reason: str = ""):
        self.disconnect()
        with self.lock:
            self.port = "SIMULATION"
            self.is_connected = True
            self.is_simulated = True
            self.dist_front = 120.0
            self.dist_left = 90.0
            self.dist_right = 85.0
            self.dist_rear = 150.0
            self.active_sensor_count = 0
            self.sensors_all = [120.0] * 4 + [90.0] * 4 + [85.0] * 4 + [150.0] * 4
        msg = f"Virtual Simulation Mode active. {reason}"
        self.add_log(msg)
        print(f"[ManualControl] {msg}")

    def disconnect(self):
        if self.ser and hasattr(self.ser, "is_open") and self.ser.is_open:
            try:
                self.ser.write(b"STOP\n")
                self.ser.close()
            except Exception:
                pass
        self.ser = None
        self.is_connected = False
        self.port = None

    def drive(self, speed: int, steer: int):
        speed = max(-255, min(255, int(speed)))
        steer = max(-255, min(255, int(steer)))

        with self.lock:
            self.current_speed = speed
            self.current_steer = steer
            self.last_cmd_time = time.time()

        cmd = f"DRIVE,{speed},{steer}\n"
        self.send_raw(cmd)

    def stop(self):
        with self.lock:
            self.current_speed = 0
            self.current_steer = 0
            self.last_cmd_time = time.time()
        self.send_raw("STOP\n")

    def test_motor(self, motor_num: int, pwm: int, duration_sec: float = 1.0):
        """Pulses a single motor (1..4) to verify physical wiring and rotation direction."""
        motor_num = max(1, min(4, int(motor_num)))
        pwm = max(-255, min(255, int(pwm)))

        def _pulse():
            self.add_log(f"PULSE: Motor {motor_num} @ PWM {pwm} for {duration_sec}s")
            self.send_raw(f"MOTOR,{motor_num},{pwm}\n")
            time.sleep(duration_sec)
            self.stop()
            self.add_log(f"PULSE COMPLETE: Motor {motor_num} stopped.")

        threading.Thread(target=_pulse, daemon=True).start()

    def set_sensor_config(self, count: str):
        """Configures active sensors on Arduino (4, 8, 12, 16, or 'AUTO')."""
        self.add_log(f"CONFIG_SENSORS -> {count}")
        self.send_raw(f"CONFIG_SENSORS,{count}\n")

    def send_raw(self, line: str):
        if not line.endswith("\n"):
            line += "\n"

        if self.ser and hasattr(self.ser, "is_open") and self.ser.is_open:
            try:
                self.ser.write(line.encode("ascii"))
            except Exception as e:
                self.add_log(f"TX Error: {e}")
        else:
            # Simulation response
            if line.startswith("DRIVE"):
                pass
            elif line.startswith("STOP"):
                pass
            elif line.startswith("CONFIG_SENSORS"):
                val = line.strip().split(",")[1]
                with self.lock:
                    if val.isdigit():
                        self.active_sensor_count = int(val)

    def _rx_loop(self):
        sim_wander = 120.0
        sim_dir = -1.0
        while self.running:
            if self.is_simulated:
                # Virtual physics telemetry
                with self.lock:
                    spd = self.current_speed
                if spd > 0:
                    sim_wander -= 3.0
                    if sim_wander < 25.0:
                        sim_wander = 25.0
                elif spd < 0:
                    sim_wander += 3.0
                    if sim_wander > 180.0:
                        sim_wander = 180.0

                with self.lock:
                    self.dist_front = round(sim_wander, 1)
                    self.dist_left = 75.0
                    self.dist_right = 80.0
                    self.dist_rear = 150.0

                time.sleep(0.06)
                continue

            if self.ser and hasattr(self.ser, "is_open") and self.ser.is_open:
                try:
                    line = self.ser.readline().decode("ascii", errors="ignore").strip()
                    if line.startswith("SENSORS,"):
                        parts = line.split(",")
                        if len(parts) >= 5:
                            with self.lock:
                                self.dist_front = float(parts[1])
                                self.dist_left = float(parts[2])
                                self.dist_right = float(parts[3])
                                self.dist_rear = float(parts[4])
                                if len(parts) > 5:
                                    try:
                                        self.active_sensor_count = int(parts[5])
                                        if len(parts) > 6:
                                            self.sensors_all = [float(p) for p in parts[6:]]
                                    except Exception:
                                        pass
                        self.add_log(f"RX: {line}")
                    elif line:
                        self.add_log(f"ARDUINO: {line}")
                except Exception:
                    pass
            time.sleep(0.02)

    def get_status(self) -> Dict[str, Any]:
        with self.lock:
            return {
                "connected": self.is_connected,
                "port": self.port or "DISCONNECTED",
                "is_simulated": self.is_simulated,
                "has_pyserial": HAS_SERIAL,
                "speed": self.current_speed,
                "steer": self.current_steer,
                "dist_front": self.dist_front,
                "dist_left": self.dist_left,
                "dist_right": self.dist_right,
                "dist_rear": self.dist_rear,
                "active_sensor_count": self.active_sensor_count,
                "sensors_all": self.sensors_all,
                "logs": self.log_history[-15:],
            }

# Instantiate singleton bridge
bridge = ArduinoBridge()

# ================= HTML5 / CSS3 / Vanilla JS Front-End =================
HTML_DASHBOARD = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>Neurolis Manual Teleoperation & Calibrator</title>
<style>
  :root {
    --bg-base: #030712;
    --bg-card: #0b1329;
    --bg-card-hover: #101d3d;
    --border: #1e293b;
    --border-glow: #00f0ff;
    --cyan: #00f0ff;
    --emerald: #00ff88;
    --amber: #f59e0b;
    --ruby: #ef4444;
    --text-primary: #f8fafc;
    --text-muted: #94a3b8;
  }

  * { box-sizing: border-box; margin: 0; padding: 0; user-select: none; }
  body {
    background: var(--bg-base);
    color: var(--text-primary);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    min-height: 100vh;
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  /* Top Navigation & Status Bar */
  header {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 12px 18px;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    box-shadow: 0 4px 20px rgba(0, 240, 255, 0.05);
  }

  .brand {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .beacon {
    width: 12px;
    height: 12px;
    border-radius: 50%;
    background: var(--emerald);
    box-shadow: 0 0 10px var(--emerald);
    animation: pulse 2s infinite;
  }
  .beacon.offline { background: var(--ruby); box-shadow: 0 0 10px var(--ruby); }
  .beacon.sim { background: var(--amber); box-shadow: 0 0 10px var(--amber); }

  @keyframes pulse {
    0%, 100% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.5; transform: scale(0.85); }
  }

  .title-group h1 { font-size: 1.1rem; font-weight: 700; letter-spacing: 0.5px; }
  .title-group p { font-size: 0.75rem; color: var(--text-muted); }

  .connection-controls {
    display: flex;
    align-items: center;
    gap: 10px;
  }
  select, button {
    background: #060b17;
    border: 1px solid var(--border);
    color: var(--text-primary);
    padding: 8px 14px;
    border-radius: 8px;
    font-size: 0.85rem;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s;
  }
  select:focus, button:focus { outline: none; border-color: var(--cyan); }
  button:hover { background: #132247; border-color: var(--cyan); }
  button:active { transform: scale(0.97); }

  .btn-estop {
    background: #450a0a !important;
    border-color: var(--ruby) !important;
    color: #fecaca !important;
    font-size: 0.95rem !important;
    padding: 10px 20px !important;
    box-shadow: 0 0 15px rgba(239, 68, 68, 0.3);
  }
  .btn-estop:hover { background: #7f1d1d !important; }

  /* Main Grid */
  .grid-layout {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
    gap: 16px;
  }

  .card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 14px;
    position: relative;
    overflow: hidden;
  }
  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid rgba(255, 255, 255, 0.06);
    padding-bottom: 8px;
  }
  .card-header h2 {
    font-size: 0.9rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    color: var(--cyan);
  }

  /* Teleoperation D-Pad & Controls */
  .dpad-container {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 10px;
    max-width: 280px;
    margin: 0 auto;
    width: 100%;
  }
  .dpad-btn {
    height: 64px;
    background: #081126;
    border: 1px solid #1a2a4f;
    border-radius: 10px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 4px;
    font-size: 1rem;
    color: var(--cyan);
  }
  .dpad-btn span { font-size: 0.65rem; color: var(--text-muted); font-weight: normal; }
  .dpad-btn:active, .dpad-btn.active {
    background: #00f0ff22;
    border-color: var(--cyan);
    box-shadow: 0 0 15px rgba(0, 240, 255, 0.3);
    color: #fff;
  }
  .dpad-btn.stop {
    background: #2a0b12;
    border-color: var(--ruby);
    color: var(--ruby);
  }
  .dpad-btn.stop:active { background: var(--ruby); color: #fff; }

  .slider-row {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .slider-label {
    display: flex;
    justify-content: space-between;
    font-size: 0.8rem;
    color: var(--text-muted);
  }
  .slider-label b { color: var(--text-primary); }
  input[type="range"] {
    -webkit-appearance: none;
    width: 100%;
    height: 6px;
    border-radius: 3px;
    background: #1e293b;
    outline: none;
  }
  input[type="range"]::-webkit-slider-thumb {
    -webkit-appearance: none;
    width: 18px;
    height: 18px;
    border-radius: 50%;
    background: var(--cyan);
    cursor: pointer;
    box-shadow: 0 0 10px var(--cyan);
  }

  /* Radar 2D Chassis Diagram */
  .radar-view {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 12px;
    padding: 10px 0;
  }
  .chassis-box {
    width: 180px;
    height: 200px;
    background: #070d1d;
    border: 2px solid #1a2a4f;
    border-radius: 20px;
    position: relative;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .chassis-core {
    width: 60px;
    height: 70px;
    border: 1px dashed var(--cyan);
    border-radius: 10px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    font-size: 0.65rem;
    color: var(--cyan);
  }
  .wheel {
    position: absolute;
    width: 22px;
    height: 48px;
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 5px;
  }
  .wheel.fl { top: 12px; left: -12px; }
  .wheel.rl { bottom: 12px; left: -12px; }
  .wheel.fr { top: 12px; right: -12px; }
  .wheel.rr { bottom: 12px; right: -12px; }

  /* Sensor Readout Tags */
  .sensor-tag {
    position: absolute;
    padding: 3px 8px;
    border-radius: 6px;
    font-size: 0.72rem;
    font-weight: 700;
    background: #030712;
    border: 1px solid var(--border);
  }
  .sensor-tag.front { top: -28px; left: 50%; transform: translateX(-50%); }
  .sensor-tag.rear { bottom: -28px; left: 50%; transform: translateX(-50%); }
  .sensor-tag.left { left: -75px; top: 50%; transform: translateY(-50%); }
  .sensor-tag.right { right: -75px; top: 50%; transform: translateY(-50%); }

  .status-safe { color: var(--emerald); border-color: var(--emerald); }
  .status-warn { color: var(--amber); border-color: var(--amber); }
  .status-alert { color: var(--ruby); border-color: var(--ruby); background: #3b0707 !important; }

  /* Individual Motor Calibrator Grid */
  .motor-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
  }
  .motor-unit {
    background: #081124;
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 10px;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .motor-unit h3 {
    font-size: 0.75rem;
    color: var(--text-muted);
    display: flex;
    justify-content: space-between;
  }
  .motor-unit h3 span { color: var(--cyan); }
  .motor-btn-group {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 6px;
  }
  .btn-fwd { background: #064e3b; border-color: var(--emerald); color: #a7f3d0; font-size: 0.75rem; padding: 6px; }
  .btn-rev { background: #4c1d95; border-color: #a855f7; color: #ddd6fe; font-size: 0.75rem; padding: 6px; }

  /* Console Log Terminal */
  .terminal-box {
    background: #02040a;
    border: 1px solid #101c33;
    border-radius: 8px;
    padding: 10px;
    font-family: Consolas, monospace;
    font-size: 0.75rem;
    color: #38bdf8;
    height: 160px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .kbd-hint {
    font-size: 0.72rem;
    color: var(--text-muted);
    text-align: center;
    background: #081124;
    padding: 6px;
    border-radius: 6px;
    border: 1px dashed #1e293b;
  }
  .kbd-hint kbd {
    background: #1e293b;
    padding: 2px 6px;
    border-radius: 4px;
    color: #fff;
    font-weight: bold;
  }
</style>
</head>
<body>

  <!-- Top Header Navigation -->
  <header>
    <div class="brand">
      <div id="beaconIndicator" class="beacon sim"></div>
      <div class="title-group">
        <h1>PROJECT NEUROLIS // MANUAL HARDWARE CALIBRATOR</h1>
        <p id="subStatus">Connecting to backend bridge...</p>
      </div>
    </div>

    <div class="connection-controls">
      <select id="portSelect">
        <option value="">Scanning ports...</option>
      </select>
      <button onclick="handleConnect()">Connect</button>
      <button onclick="handleDisconnect()">Disconnect</button>
      <button class="btn-estop" onclick="sendStop()">EMERGENCY STOP (SPACE)</button>
    </div>
  </header>

  <!-- Main Grid Layout -->
  <div class="grid-layout">

    <!-- Card 1: Live Manual Teleoperation (D-Pad & Speed) -->
    <div class="card">
      <div class="card-header">
        <h2>Manual Teleoperation</h2>
        <span id="speedSteerBadge" style="font-size:0.75rem; color:var(--cyan); font-weight:bold;">SPD: 0 | STR: 0</span>
      </div>

      <div class="dpad-container">
        <button class="dpad-btn" id="btnSpinL" onmousedown="startDrive(0, -steerVal)" onmouseup="sendStop()" ontouchstart="startDrive(0, -steerVal)" ontouchend="sendStop()">
          ⟲ <span>Spin L (Q)</span>
        </button>
        <button class="dpad-btn" id="btnFwd" onmousedown="startDrive(speedVal, 0)" onmouseup="sendStop()" ontouchstart="startDrive(speedVal, 0)" ontouchend="sendStop()">
          ▲ <span>Forward (W)</span>
        </button>
        <button class="dpad-btn" id="btnSpinR" onmousedown="startDrive(0, steerVal)" onmouseup="sendStop()" ontouchstart="startDrive(0, steerVal)" ontouchend="sendStop()">
          ⟳ <span>Spin R (E)</span>
        </button>
        <button class="dpad-btn" id="btnLeft" onmousedown="startDrive(speedVal, -steerVal)" onmouseup="sendStop()" ontouchstart="startDrive(speedVal, -steerVal)" ontouchend="sendStop()">
          ◀ <span>Left (A)</span>
        </button>
        <button class="dpad-btn stop" onclick="sendStop()">
          ■ <span>STOP</span>
        </button>
        <button class="dpad-btn" id="btnRight" onmousedown="startDrive(speedVal, steerVal)" onmouseup="sendStop()" ontouchstart="startDrive(speedVal, steerVal)" ontouchend="sendStop()">
          ▶ <span>Right (D)</span>
        </button>
        <div></div>
        <button class="dpad-btn" id="btnRev" onmousedown="startDrive(-speedVal, 0)" onmouseup="sendStop()" ontouchstart="startDrive(-speedVal, 0)" ontouchend="sendStop()">
          ▼ <span>Reverse (S)</span>
        </button>
        <div></div>
      </div>

      <div class="slider-row">
        <div class="slider-label">
          <span>Drive Throttle (PWM)</span>
          <b id="speedDisplay">120</b>
        </div>
        <input type="range" id="speedSlider" min="50" max="255" value="120" oninput="updateSpeed(this.value)">
      </div>

      <div class="slider-row">
        <div class="slider-label">
          <span>Steering Sensitivity (PWM)</span>
          <b id="steerDisplay">100</b>
        </div>
        <input type="range" id="steerSlider" min="40" max="200" value="100" oninput="updateSteer(this.value)">
      </div>

      <div class="kbd-hint">
        Use keyboard <kbd>W</kbd> <kbd>A</kbd> <kbd>S</kbd> <kbd>D</kbd> or <kbd>Arrow Keys</kbd> to drive. Press <kbd>Space</kbd> to instant stop.
      </div>
    </div>

    <!-- Card 2: 16-Sensor Ultrasonic Radar & Chassis Status -->
    <div class="card">
      <div class="card-header">
        <h2>Ultrasonic Radar & Safety Telemetry</h2>
        <span id="activeSensorsBadge" style="font-size:0.75rem; color:var(--emerald);">4 Sensors Active</span>
      </div>

      <div class="radar-view">
        <div class="chassis-box">
          <div class="wheel fl"></div>
          <div class="wheel rl"></div>
          <div class="wheel fr"></div>
          <div class="wheel rr"></div>

          <!-- Live Distance Tags -->
          <div id="tagFront" class="sensor-tag front status-safe">FRONT: --- cm</div>
          <div id="tagRear" class="sensor-tag rear status-safe">REAR: --- cm</div>
          <div id="tagLeft" class="sensor-tag left status-safe">LEFT: --- cm</div>
          <div id="tagRight" class="sensor-tag right status-safe">RIGHT: --- cm</div>

          <div class="chassis-core">
            <b>4WD</b>
            <span>SKID</span>
          </div>
        </div>
      </div>

      <div style="display:flex; justify-content:space-between; align-items:center; margin-top:12px;">
        <span style="font-size:0.8rem; color:var(--text-muted);">Switch Sensor Bank:</span>
        <div style="display:flex; gap:6px;">
          <button style="padding:4px 8px; font-size:0.75rem;" onclick="setSensorCount('0')">0</button>
          <button style="padding:4px 8px; font-size:0.75rem;" onclick="setSensorCount('4')">4</button>
          <button style="padding:4px 8px; font-size:0.75rem;" onclick="setSensorCount('8')">8</button>
          <button style="padding:4px 8px; font-size:0.75rem;" onclick="setSensorCount('12')">12</button>
          <button style="padding:4px 8px; font-size:0.75rem;" onclick="setSensorCount('16')">16</button>
          <button style="padding:4px 8px; font-size:0.75rem;" onclick="setSensorCount('AUTO')">AUTO</button>
        </div>
      </div>
      <p style="font-size:0.72rem; color:var(--text-muted);">Auto-Brake engages automatically whenever front or rear distance is &lt;20cm.</p>
    </div>

    <!-- Card 3: Motor Polarity & Wiring Calibrator -->
    <div class="card">
      <div class="card-header">
        <h2>Motor Polarity & Wiring Calibrator</h2>
        <span style="font-size:0.75rem; color:var(--amber);">Bench Testing</span>
      </div>
      <p style="font-size:0.75rem; color:var(--text-muted);">
        Pulse each wheel independently to verify spin direction. If any wheel spins backwards when clicking <b>Fwd (+)</b>, simply swap its wire leads on that driver!
      </p>

      <div class="motor-grid">
        <!-- Motor 1 -->
        <div class="motor-unit">
          <h3>M1: Front-Left <span>Pins 2,3,26</span></h3>
          <div class="motor-btn-group">
            <button class="btn-fwd" onclick="testMotor(1, speedVal)">Fwd (+)</button>
            <button class="btn-rev" onclick="testMotor(1, -speedVal)">Rev (-)</button>
          </div>
        </div>

        <!-- Motor 3 -->
        <div class="motor-unit">
          <h3>M3: Front-Right <span>Pins 6,7,28</span></h3>
          <div class="motor-btn-group">
            <button class="btn-fwd" onclick="testMotor(3, speedVal)">Fwd (+)</button>
            <button class="btn-rev" onclick="testMotor(3, -speedVal)">Rev (-)</button>
          </div>
        </div>

        <!-- Motor 2 -->
        <div class="motor-unit">
          <h3>M2: Rear-Left <span>Pins 4,5,27</span></h3>
          <div class="motor-btn-group">
            <button class="btn-fwd" onclick="testMotor(2, speedVal)">Fwd (+)</button>
            <button class="btn-rev" onclick="testMotor(2, -speedVal)">Rev (-)</button>
          </div>
        </div>

        <!-- Motor 4 -->
        <div class="motor-unit">
          <h3>M4: Rear-Right <span>Pins 8,9,29</span></h3>
          <div class="motor-btn-group">
            <button class="btn-fwd" onclick="testMotor(4, speedVal)">Fwd (+)</button>
            <button class="btn-rev" onclick="testMotor(4, -speedVal)">Rev (-)</button>
          </div>
        </div>
      </div>

      <div class="slider-row">
        <div class="slider-label">
          <span>Pulse Duration</span>
          <b id="durationDisplay">1.0s</b>
        </div>
        <input type="range" id="durationSlider" min="0.3" max="3.0" step="0.1" value="1.0" oninput="testDuration = parseFloat(this.value); document.getElementById('durationDisplay').innerText = this.value + 's';">
      </div>
    </div>

    <!-- Card 4: Real-Time Console Log & Raw Command Sender -->
    <div class="card" style="grid-column: 1 / -1;">
      <div class="card-header">
        <h2>Serial Console & Telemetry Stream</h2>
        <button style="padding:2px 8px; font-size:0.7rem;" onclick="clearLogs()">Clear</button>
      </div>

      <div class="terminal-box" id="terminalLog">
        <div>[*] Initializing Web Serial Terminal...</div>
      </div>

      <div style="display:flex; gap:10px;">
        <input type="text" id="rawCmdInput" placeholder="Send raw command (e.g. DRIVE,120,0 or STOP or PING)" style="flex:1; background:#060b17; border:1px solid var(--border); color:#fff; padding:8px 12px; border-radius:6px; font-family:monospace; font-size:0.8rem;" onkeydown="if(event.key==='Enter') sendRawCommand()">
        <button onclick="sendRawCommand()">Send Raw</button>
      </div>
    </div>

  </div>

<script>
  let speedVal = 120;
  let steerVal = 100;
  let testDuration = 1.0;
  let activeKeys = {};
  let driveInterval = null;

  function updateSpeed(v) {
    speedVal = parseInt(v);
    document.getElementById('speedDisplay').innerText = speedVal;
  }
  function updateSteer(v) {
    steerVal = parseInt(v);
    document.getElementById('steerDisplay').innerText = steerVal;
  }

  // API Call helper
  async function apiPost(url, data) {
    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data || {})
      });
      return await res.json();
    } catch (e) {
      console.error(url, e);
      return null;
    }
  }

  function startDrive(spd, str) {
    if (driveInterval) clearInterval(driveInterval);
    apiPost('/api/drive', { speed: spd, steer: str });
    driveInterval = setInterval(() => {
      apiPost('/api/drive', { speed: spd, steer: str });
    }, 120);
  }

  function sendStop() {
    if (driveInterval) {
      clearInterval(driveInterval);
      driveInterval = null;
    }
    apiPost('/api/stop', {});
  }

  function testMotor(num, pwm) {
    apiPost('/api/test_motor', { motor: num, pwm: pwm, duration: testDuration });
  }

  function setSensorCount(cnt) {
    apiPost('/api/config_sensors', { count: cnt });
  }

  function sendRawCommand() {
    const input = document.getElementById('rawCmdInput');
    const cmd = input.value.trim();
    if (!cmd) return;
    apiPost('/api/raw', { cmd: cmd });
    input.value = '';
  }

  // Keyboard driving handlers
  window.addEventListener('keydown', (e) => {
    if (['INPUT', 'SELECT', 'TEXTAREA'].includes(e.target.tagName)) return;
    const k = e.key.toLowerCase();

    if (e.code === 'Space') {
      e.preventDefault();
      sendStop();
      return;
    }

    if (!activeKeys[k]) {
      activeKeys[k] = true;
      evaluateKeyboardDrive();
    }
  });

  window.addEventListener('keyup', (e) => {
    if (['INPUT', 'SELECT', 'TEXTAREA'].includes(e.target.tagName)) return;
    const k = e.key.toLowerCase();
    delete activeKeys[k];
    evaluateKeyboardDrive();
  });

  function evaluateKeyboardDrive() {
    let spd = 0;
    let str = 0;

    if (activeKeys['w'] || activeKeys['arrowup']) spd += speedVal;
    if (activeKeys['s'] || activeKeys['arrowdown']) spd -= speedVal;
    if (activeKeys['a'] || activeKeys['arrowleft']) str -= steerVal;
    if (activeKeys['d'] || activeKeys['arrowright']) str += steerVal;
    if (activeKeys['q']) { spd = 0; str = -steerVal; }
    if (activeKeys['e']) { spd = 0; str = steerVal; }

    if (spd === 0 && str === 0) {
      sendStop();
    } else {
      startDrive(spd, str);
    }
  }

  // Ports list & connect
  async function loadPorts() {
    try {
      const res = await fetch('/api/ports');
      const data = await res.json();
      const sel = document.getElementById('portSelect');
      sel.innerHTML = '';
      (data.ports || []).forEach(p => {
        const opt = document.createElement('option');
        opt.value = p.device;
        opt.innerText = `${p.device} (${p.description})`;
        sel.appendChild(opt);
      });
    } catch (e) {}
  }

  function handleConnect() {
    const sel = document.getElementById('portSelect');
    if (sel.value) {
      apiPost('/api/connect', { port: sel.value });
    }
  }

  function handleDisconnect() {
    apiPost('/api/disconnect', {});
  }

  // Telemetry Poller
  async function pollStatus() {
    try {
      const res = await fetch('/api/status');
      const data = await res.json();

      // Beacon & Status
      const beacon = document.getElementById('beaconIndicator');
      const sub = document.getElementById('subStatus');

      if (!data.connected) {
        beacon.className = 'beacon offline';
        sub.innerText = 'DISCONNECTED (Select port and click Connect)';
      } else if (data.is_simulated) {
        beacon.className = 'beacon sim';
        sub.innerText = `VIRTUAL SIMULATION ACTIVE // ${data.port}`;
      } else {
        beacon.className = 'beacon';
        sub.innerText = `ONLINE // Connected to ${data.port} @ 115200 baud`;
      }

      // Speeds
      document.getElementById('speedSteerBadge').innerText = `SPD: ${data.speed:+4d} | STR: ${data.steer:+4d}`;

      // Ultrasonic Radar
      updateTag('tagFront', 'FRONT', data.dist_front);
      updateTag('tagRear', 'REAR', data.dist_rear);
      updateTag('tagLeft', 'LEFT', data.dist_left);
      updateTag('tagRight', 'RIGHT', data.dist_right);

      const cnt = data.active_sensor_count || 0;
      document.getElementById('activeSensorsBadge').innerText = `${cnt > 0 ? cnt : 'Simulation'} Sensors Active`;

      // Logs
      const term = document.getElementById('terminalLog');
      if (data.logs && data.logs.length) {
        term.innerHTML = data.logs.map(l => `<div>${l}</div>`).join('');
        term.scrollTop = term.scrollHeight;
      }

    } catch (e) {}
  }

  function updateTag(id, label, val) {
    const el = document.getElementById(id);
    const d = parseFloat(val);
    el.innerText = `${label}: ${d.toFixed(1)} cm`;
    if (d < 20.0) {
      el.className = `sensor-tag ${id.replace('tag','').toLowerCase()} status-alert`;
    } else if (d < 50.0) {
      el.className = `sensor-tag ${id.replace('tag','').toLowerCase()} status-warn`;
    } else {
      el.className = `sensor-tag ${id.replace('tag','').toLowerCase()} status-safe`;
    }
  }

  function clearLogs() {
    document.getElementById('terminalLog').innerHTML = '';
  }

  loadPorts();
  setInterval(pollStatus, 200);
</script>
</body>
</html>
"""

# ================= REST API HTTP Request Handler =================
class ManualControlRequestHandler(BaseHTTPRequestHandler):
    def _send_json(self, data: dict, status: int = 200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            body = HTML_DASHBOARD.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/api/status":
            self._send_json(bridge.get_status())
        elif self.path == "/api/ports":
            self._send_json({"ports": bridge.list_ports()})
        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b"{}"
        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception:
            payload = {}

        if self.path == "/api/drive":
            speed = payload.get("speed", 0)
            steer = payload.get("steer", 0)
            bridge.drive(speed, steer)
            self._send_json({"ok": True, "speed": speed, "steer": steer})

        elif self.path == "/api/stop":
            bridge.stop()
            self._send_json({"ok": True})

        elif self.path == "/api/test_motor":
            motor = payload.get("motor", 1)
            pwm = payload.get("pwm", 120)
            duration = payload.get("duration", 1.0)
            bridge.test_motor(motor, pwm, duration)
            self._send_json({"ok": True, "motor": motor, "pwm": pwm, "duration": duration})

        elif self.path == "/api/config_sensors":
            count = str(payload.get("count", "16"))
            bridge.set_sensor_config(count)
            self._send_json({"ok": True, "count": count})

        elif self.path == "/api/connect":
            port = payload.get("port", "")
            bridge.connect(port)
            self._send_json({"ok": True, "port": port})

        elif self.path == "/api/disconnect":
            bridge.disconnect()
            self._send_json({"ok": True})

        elif self.path == "/api/raw":
            cmd = payload.get("cmd", "")
            bridge.send_raw(cmd)
            self._send_json({"ok": True, "cmd": cmd})

        else:
            self.send_error(404, "API endpoint not found")

    def log_message(self, format, *args):
        # Suppress noisy HTTP request polling logs on console
        pass


def run_server(port: int = 5000):
    server = ThreadingHTTPServer(("0.0.0.0", port), ManualControlRequestHandler)

    # Resolve local network IP
    local_ip = "127.0.0.1"
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        pass

    print("\n" + "=" * 65)
    print("   PROJECT NEUROLIS - MANUAL HARDWARE CONTROLLER & CALIBRATOR")
    print("=" * 65)
    print(f"[*] Local Machine URL:  http://localhost:{port}")
    print(f"[*] Network Phone URL:  http://{local_ip}:{port}")
    print("-----------------------------------------------------------------")
    print("  Controls:")
    print("    - Driving:      Touch D-Pad or Keyboard [W][A][S][D] / Arrows")
    print("    - Spin in Place: [Q] Spin Left | [E] Spin Right")
    print("    - Emergency:    [SPACE] or Emergency STOP button")
    print("    - Calibration:  Pulse Motor 1, 2, 3, 4 individually to verify wiring")
    print("=================================================================\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[ManualControl] Shutting down manual controller server...")
    finally:
        bridge.disconnect()
        server.server_close()


if __name__ == "__main__":
    port_arg = 5000
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        port_arg = int(sys.argv[1])
    run_server(port_arg)
