#!/usr/bin/env python3
"""
Neurolis Live Microphone & Multi-Layer VAD Tuning Studio
Real-time visual calibration tool for tuning microphone gain, WebRTC VAD aggressiveness,
RMS thresholds, Acoustic Proximity Gate, Click Rejection, Narrowband Fan Resonance Rejection,
and Vocal Tunnel DSP filters on the Raspberry Pi 5.
"""

import sys
import os
import time
import json
import shutil
import threading
import subprocess
from pathlib import Path
from typing import Optional

import numpy as np
import sounddevice as sd
try:
    import webrtcvad
except ImportError:
    webrtcvad = None

import tkinter as tk
from tkinter import ttk, messagebox

CONFIG_FILE = Path(__file__).resolve().parent / "mic_config.json"

DEFAULT_CONFIG = {
    "hardware_gain_pct": 61,
    "vad_mode": 3,
    "min_speech_rms": 820.0,
    "speech_multiplier": 2.65,
    "continue_ratio": 0.50,
    "start_frames": 3,
    "end_silence_sec": 0.45,
    "pre_emphasis": 0.0,
    "low_cutoff_hz": 40.0,
    "high_cutoff_hz": 5800.0,
    "treble_boost": 1.65,
    "bg_suppress_db": 28.0,
    "agc_target_peak": 22000.0,
    "agc_max_scale": 1.50,
    "fan_rejection_ratio": 0.85,
    "click_rejection_ratio": 0.35,
    "proximity_crest_min": 2.20
}

def load_saved_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                loaded = json.load(f)
                cfg.update(loaded)
        except Exception as e:
            print(f"[Config] Error loading {CONFIG_FILE}: {e}")
    return cfg

def save_config(cfg: dict):
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(cfg, f, indent=2)
        print(f"[Config] Saved parameters to {CONFIG_FILE}")
    except Exception as e:
        print(f"[Config] Failed to save {CONFIG_FILE}: {e}")

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


class AudioConfigManager:
    """Thread-safe configuration cache. Eliminates all Tkinter thread-access freezes."""
    def __init__(self, initial_cfg: dict):
        self._lock = threading.Lock()
        self._data = dict(initial_cfg)

    def get(self, key: str, default=None):
        with self._lock:
            return self._data.get(key, default)

    def set(self, key: str, value):
        with self._lock:
            self._data[key] = value

    def get_all(self) -> dict:
        with self._lock:
            return dict(self._data)


class MicTunerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Neurolis - Live Mic & Multi-Layer VAD Studio")
        self.root.configure(bg="#0f141c")

        # Screen-aware responsive sizing to guarantee 100% button visibility on any display
        try:
            screen_w = self.root.winfo_screenwidth()
            screen_h = self.root.winfo_screenheight()
            win_w = min(980, max(820, screen_w - 24))
            win_h = min(570, max(500, screen_h - 70))
            pos_x = max(0, (screen_w - win_w) // 2)
            pos_y = max(0, (screen_h - win_h) // 2)
            self.root.geometry(f"{win_w}x{win_h}+{pos_x}+{pos_y}")
            self.root.minsize(820, 480)
        except Exception:
            self.root.geometry("980x560")

        self.cfg = load_saved_config()
        self.audio_cfg = AudioConfigManager(self.cfg)
        self.is_running = True

        # Live audio monitoring pipeline
        self.is_monitoring = False
        self.monitor_proc: Optional[subprocess.Popen] = None
        self.monitor_lock = threading.Lock()

        # Thread-safe telemetry state (audio thread calculates, GUI thread reads)
        self.data_lock = threading.Lock()
        self.raw_rms = 0.0
        self.filtered_rms = 0.0
        self.crest_factor = 1.0
        self.vad_speech = False
        self.is_click = False
        self.is_fan = False
        self.is_speaking = False
        self.start_streak = 0
        self.calibrated_ambient = 25.0
        self.calibrated_threshold = float(self.cfg.get("min_speech_rms", 820.0))
        self.continue_threshold_val = float(self.cfg.get("min_speech_rms", 820.0)) * float(self.cfg.get("continue_ratio", 0.50))

        # Test sample recording
        self.is_recording_sample = False
        self.sample_buffer = []
        self.recorded_sample_raw = None

        # Audio stream params
        self.frame_sec = 0.03  # 30ms chunks
        self.target_sr = 16000

        # Auto-detect target microphone device (PipeWire default source on Linux, sounddevice on Windows)
        if sys.platform.startswith("linux") and shutil.which("pw-record"):
            self.hw_sr = 16000
            self.target_dev = None
        else:
            self.hw_sr = 44100
            self.target_dev = None
            try:
                devices = sd.query_devices()
                for idx, dev in enumerate(devices):
                    if dev.get("max_input_channels", 0) > 0:
                        name = dev.get("name", "").lower()
                        if "iris" in name or "webca" in name or "sonar" in name or "microphone" in name:
                            self.target_dev = idx
                            break
                if self.target_dev is not None:
                    self.hw_sr = int(sd.query_devices(self.target_dev).get("default_samplerate", 44100))
            except Exception:
                pass

        self.hw_frame_samples = int(self.hw_sr * self.frame_sec)
        self.target_frame_samples = int(self.target_sr * self.frame_sec)

        # Pre-calculated resample coordinate grids (zero overhead per frame)
        self.orig_x = np.linspace(0, 1, self.hw_frame_samples, endpoint=False)
        self.target_x = np.linspace(0, 1, self.target_frame_samples, endpoint=False)

        self._build_ui()
        self._start_audio_stream()
        self._schedule_gui_update()

        # Apply initial hardware gain
        set_hardware_gain(self.cfg["hardware_gain_pct"])

    def _build_ui(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TLabel", background="#0f141c", foreground="#d8e2ec", font=("Helvetica", 9))
        style.configure("Header.TLabel", font=("Helvetica", 12, "bold"), foreground="#00d4ff")
        style.configure("Sub.TLabel", font=("Helvetica", 8), foreground="#7c8c9e")
        style.configure("TButton", font=("Helvetica", 9, "bold"), padding=3)

        # Bottom Action Bar (PACKED FIRST with side="bottom" so it is ALWAYS visible and never clipped!)
        bottom_bar = tk.Frame(self.root, bg="#0f141c")
        bottom_bar.pack(side="bottom", fill="x", padx=12, pady=(4, 6))

        self.btn_calibrate = tk.Button(
            bottom_bar, text="🎯 Calibrate Room (1s)", bg="#37474f", fg="#ffffff",
            font=("Helvetica", 9, "bold"), pady=4, command=self._calibrate_room
        )
        self.btn_calibrate.pack(side="left", padx=4)

        self.btn_save = tk.Button(
            bottom_bar, text="💾 Save to listen.py & mic_config.json", bg="#00c853", fg="#ffffff",
            font=("Helvetica", 9, "bold"), pady=4, command=self._save_configuration
        )
        self.btn_save.pack(side="right", padx=4)

        self.btn_reset = tk.Button(
            bottom_bar, text="↺ Reset Defaults", bg="#d32f2f", fg="#ffffff",
            font=("Helvetica", 9), pady=4, command=self._reset_defaults
        )
        self.btn_reset.pack(side="right", padx=4)

        # Top Header
        top_frame = tk.Frame(self.root, bg="#0f141c")
        top_frame.pack(side="top", fill="x", padx=12, pady=(4, 2))

        title = ttk.Label(top_frame, text="NEUROLIS MULTI-LAYER VAD & ACOUSTIC STUDIO", style="Header.TLabel")
        title.pack(anchor="w")
        subtitle = ttk.Label(
            top_frame,
            text="Thread-safe telemetry, proximity gate, live audio monitor, and vocal tunnel DSP calibration.",
            style="Sub.TLabel"
        )
        subtitle.pack(anchor="w", pady=(1, 0))

        # Real-time Telemetry & VU Meters
        meter_frame = tk.LabelFrame(self.root, text=" Live Acoustic Telemetry & VAD Status ", bg="#151c27", fg="#00d4ff", font=("Helvetica", 9, "bold"))
        meter_frame.pack(side="top", fill="x", padx=12, pady=(2, 3))

        # Status indicator banner
        self.status_canvas = tk.Canvas(meter_frame, height=24, bg="#1a2332", highlightthickness=0)
        self.status_canvas.pack(fill="x", padx=8, pady=2)
        self.status_text_id = self.status_canvas.create_text(
            420, 12, text="WAITING FOR SPEECH...", font=("Helvetica", 10, "bold"), fill="#8090a0"
        )

        # Canvas VU meters
        canvas_grid = tk.Frame(meter_frame, bg="#151c27")
        canvas_grid.pack(fill="x", padx=8, pady=1)

        tk.Label(canvas_grid, text="Raw Mic Energy:", bg="#151c27", fg="#a0b0c0", font=("Helvetica", 8)).grid(row=0, column=0, sticky="w")
        self.raw_meter = tk.Canvas(canvas_grid, width=440, height=12, bg="#0d1117", highlightthickness=1, highlightbackground="#2d3748")
        self.raw_meter.grid(row=0, column=1, padx=6, pady=1)
        self.raw_bar = self.raw_meter.create_rectangle(0, 0, 0, 12, fill="#00d4ff", width=0)
        self.raw_val_lbl = tk.Label(canvas_grid, text="RMS: 0", bg="#151c27", fg="#00d4ff", font=("Helvetica", 8), width=12, anchor="w")
        self.raw_val_lbl.grid(row=0, column=2, padx=4)

        tk.Label(canvas_grid, text="Vocal Tunnel Energy:", bg="#151c27", fg="#a0b0c0", font=("Helvetica", 8)).grid(row=1, column=0, sticky="w")
        self.tunnel_meter = tk.Canvas(canvas_grid, width=440, height=12, bg="#0d1117", highlightthickness=1, highlightbackground="#2d3748")
        self.tunnel_meter.grid(row=1, column=1, padx=6, pady=1)
        self.tunnel_bar = self.tunnel_meter.create_rectangle(0, 0, 0, 12, fill="#00e676", width=0)
        self.threshold_line = self.tunnel_meter.create_line(0, 0, 0, 12, fill="#ff1744", width=2)
        self.continue_line = self.tunnel_meter.create_line(0, 0, 0, 12, fill="#ffeb3b", width=1)
        self.tunnel_val_lbl = tk.Label(canvas_grid, text="RMS: 0", bg="#151c27", fg="#00e676", font=("Helvetica", 8), width=12, anchor="w")
        self.tunnel_val_lbl.grid(row=1, column=2, padx=4)

        # Filter Telemetry Indicators (Click reject, Fan reject, VAD, Crest)
        info_row = tk.Frame(meter_frame, bg="#151c27")
        info_row.pack(fill="x", padx=8, pady=(1, 3))
        self.ambient_lbl = tk.Label(info_row, text="Ambient: 25.0", bg="#151c27", fg="#8090a0", font=("Helvetica", 8))
        self.ambient_lbl.pack(side="left", padx=3)
        self.thresh_lbl = tk.Label(info_row, text="Trigger: 820.0", bg="#151c27", fg="#ff9100", font=("Helvetica", 8))
        self.thresh_lbl.pack(side="left", padx=6)
        self.cont_lbl = tk.Label(info_row, text="Continue: 574.0", bg="#151c27", fg="#ffeb3b", font=("Helvetica", 8))
        self.cont_lbl.pack(side="left", padx=6)
        self.vad_vote_lbl = tk.Label(info_row, text="VAD: NO", bg="#151c27", fg="#8090a0", font=("Helvetica", 8))
        self.vad_vote_lbl.pack(side="left", padx=6)
        self.crest_lbl = tk.Label(info_row, text="Crest: 1.0x", bg="#151c27", fg="#8090a0", font=("Helvetica", 8))
        self.crest_lbl.pack(side="left", padx=6)
        self.click_lbl = tk.Label(info_row, text="Click: OFF", bg="#151c27", fg="#8090a0", font=("Helvetica", 8))
        self.click_lbl.pack(side="left", padx=6)
        self.fan_lbl = tk.Label(info_row, text="Fan Drone: OFF", bg="#151c27", fg="#8090a0", font=("Helvetica", 8))
        self.fan_lbl.pack(side="left", padx=6)

        # Main Controls Frame
        controls_container = tk.Frame(self.root, bg="#0f141c")
        controls_container.pack(side="top", fill="both", expand=True, padx=12, pady=2)

        # Left Column: Sensitivity, VAD & Proximity Guards
        col_left = tk.LabelFrame(controls_container, text=" Acoustic Rejection, Proximity & VAD ", bg="#151c27", fg="#00d4ff", font=("Helvetica", 9, "bold"))
        col_left.pack(side="left", fill="both", expand=True, padx=(0, 4))

        # Hardware Mic Gain Slider
        self.gain_var = tk.IntVar(value=self.cfg["hardware_gain_pct"])
        self._create_slider(
            col_left, "hardware_gain_pct", "Hardware Mic Gain (%)", self.gain_var, 10, 100, 1,
            "System audio capture volume (wpctl/pactl). 61% calibrated for phone mic.", self._on_gain_change
        )

        # WebRTC VAD Aggressiveness Mode (0 to 3)
        self.vad_var = tk.IntVar(value=self.cfg["vad_mode"])
        self._create_slider(
            col_left, "vad_mode", "WebRTC VAD Aggressiveness", self.vad_var, 0, 3, 1,
            "Mode 3 strictly isolates vocal harmonic bands"
        )

        # Minimum Speech RMS Cutoff
        self.min_rms_var = tk.DoubleVar(value=self.cfg["min_speech_rms"])
        self._create_slider(
            col_left, "min_speech_rms", "Min Speech RMS Baseline", self.min_rms_var, 40.0, 2000.0, 10.0,
            "Absolute noise floor cutoff (rejects fan / distant background chatter)"
        )

        # Speech Threshold Multiplier
        self.mult_var = tk.DoubleVar(value=self.cfg["speech_multiplier"])
        self._create_slider(
            col_left, "speech_multiplier", "Speech Multiplier (over ambient)", self.mult_var, 1.10, 3.50, 0.05,
            "Headroom above measured room noise"
        )

        # Continuation Threshold Ratio
        self.continue_ratio_var = tk.DoubleVar(value=self.cfg.get("continue_ratio", 0.50))
        self._create_slider(
            col_left, "continue_ratio", "Speech Continuation Ratio", self.continue_ratio_var, 0.30, 0.85, 0.05,
            "Ratio of active voice RMS required to keep recording (cuts off background noise)"
        )

        # Required Start Frames (Streak)
        self.frames_var = tk.IntVar(value=self.cfg["start_frames"])
        self._create_slider(
            col_left, "start_frames", "Start Speech Streak (Frames)", self.frames_var, 2, 8, 1,
            "Consecutive 30ms frames before activating (filters short pops)"
        )

        # End Silence Cutoff Seconds
        self.end_silence_var = tk.DoubleVar(value=self.cfg.get("end_silence_sec", 0.45))
        self._create_slider(
            col_left, "end_silence_sec", "End Silence Cutoff (Seconds)", self.end_silence_var, 0.30, 0.80, 0.05,
            "Silence duration before finalizing speech (stops recording promptly)"
        )

        # Proximity Crest Factor Minimum
        self.crest_var = tk.DoubleVar(value=self.cfg.get("proximity_crest_min", 2.20))
        self._create_slider(
            col_left, "proximity_crest_min", "Proximity Crest Factor Gate (Min Peak/RMS)", self.crest_var, 1.5, 4.0, 0.1,
            "Rejects diffuse distant room echo; close speech exhibits sharp peak-to-RMS"
        )

        # Right Column: Vocal Tunnel DSP & Audio Monitoring
        col_right = tk.LabelFrame(controls_container, text=" Vocal Tunnel DSP & Live Monitoring ", bg="#151c27", fg="#00d4ff", font=("Helvetica", 9, "bold"))
        col_right.pack(side="right", fill="both", expand=True, padx=(4, 0))

        # Low-Cut Filter Frequency
        self.low_cut_var = tk.DoubleVar(value=self.cfg.get("low_cutoff_hz", 40.0))
        self._create_slider(
            col_right, "low_cutoff_hz", "Low-Cut Bass Roll-off (Hz)", self.low_cut_var, 40.0, 250.0, 5.0,
            "Cuts sub-bass rumble & 50Hz/60Hz AC hum while preserving full bass vocal warmth (80Hz+)"
        )

        # High-Cut Filter Frequency
        self.high_cut_var = tk.DoubleVar(value=self.cfg.get("high_cutoff_hz", 5800.0))
        self._create_slider(
            col_right, "high_cutoff_hz", "High-Cut Filter (Hz)", self.high_cut_var, 3500.0, 7500.0, 100.0,
            "Strips electrical hiss above 5.8kHz while preserving clear speech formants"
        )

        # Treble Formant Clarity Boost
        self.treble_var = tk.DoubleVar(value=self.cfg.get("treble_boost", 1.65))
        self._create_slider(
            col_right, "treble_boost", "Treble / Consonant Clarity Boost (x)", self.treble_var, 1.0, 2.5, 0.05,
            "Subtle presence boost (2.2kHz-4.2kHz) for crisp consonant clarity without harsh stinging"
        )

        # Background Noise Suppression Gate (dB)
        self.bg_suppress_var = tk.DoubleVar(value=self.cfg.get("bg_suppress_db", 28.0))
        self._create_slider(
            col_right, "bg_suppress_db", "Background Noise Suppression (dB)", self.bg_suppress_var, 6.0, 36.0, 2.0,
            "Attenuates background hiss, distant hums, and murmur during pauses"
        )

        # Dynamic Vocal AGC Max Scale
        self.agc_var = tk.DoubleVar(value=self.cfg.get("agc_max_scale", 1.50))
        self._create_slider(
            col_right, "agc_max_scale", "AGC Distance Amplifier (Max)", self.agc_var, 1.0, 3.0, 0.1,
            "Smoothly amplifies speech level (active only during speech, disabled during pauses)"
        )

        # Narrowband Fan Drone Rejection Threshold
        self.fan_rej_var = tk.DoubleVar(value=self.cfg["fan_rejection_ratio"])
        self._create_slider(
            col_right, "fan_rejection_ratio", "Fan Drone Power Threshold", self.fan_rej_var, 0.50, 0.98, 0.05,
            "Suppresses continuous single-tone motor/fan whine"
        )

        # Keyboard / Click Rejection Threshold
        self.click_rej_var = tk.DoubleVar(value=self.cfg["click_rejection_ratio"])
        self._create_slider(
            col_right, "click_rejection_ratio", "Click/Typing Rejection Ratio", self.click_rej_var, 0.10, 0.50, 0.02,
            "Rejects sharp transient clicks and key presses (>3.6kHz power)"
        )

        # Action Buttons (Live Audio Monitor, Record Sample, Play Back) - 2x2 Responsive Grid
        btn_frame = tk.Frame(col_right, bg="#151c27")
        btn_frame.pack(fill="x", padx=8, pady=(2, 2))
        btn_frame.columnconfigure(0, weight=1)
        btn_frame.columnconfigure(1, weight=1)

        # LIVE AUDIO MONITOR TOGGLE BUTTON
        self.btn_monitor = tk.Button(
            btn_frame, text="🎧 Monitor LIVE: OFF", bg="#37474f", fg="#ffffff",
            font=("Helvetica", 8, "bold"), pady=3, command=self._toggle_live_monitoring
        )
        self.btn_monitor.grid(row=0, column=0, sticky="ew", padx=2, pady=2)

        self.btn_record = tk.Button(
            btn_frame, text="🎙️ Record 3s Sample", bg="#00a8cc", fg="#ffffff",
            font=("Helvetica", 8, "bold"), pady=3, command=self._record_voice_sample
        )
        self.btn_record.grid(row=0, column=1, sticky="ew", padx=2, pady=2)

        self.btn_play_raw = tk.Button(
            btn_frame, text="🔊 Hear Raw Mic", bg="#2c3e50", fg="#ffffff",
            font=("Helvetica", 8), pady=3, command=self._play_raw_sample
        )
        self.btn_play_raw.grid(row=1, column=0, sticky="ew", padx=2, pady=2)

        self.btn_play_filtered = tk.Button(
            btn_frame, text="✨ Hear Vocal Tunnel", bg="#1b5e20", fg="#ffffff",
            font=("Helvetica", 8, "bold"), pady=3, command=self._play_filtered_sample
        )
        self.btn_play_filtered.grid(row=1, column=1, sticky="ew", padx=2, pady=2)

    def _create_slider(self, parent, param_key, label_text, var, from_, to, step, hint_text, callback=None):
        container = tk.Frame(parent, bg="#151c27")
        container.pack(fill="x", padx=8, pady=1)

        header = tk.Frame(container, bg="#151c27")
        header.pack(fill="x")

        lbl = tk.Label(header, text=label_text, bg="#151c27", fg="#d8e2ec", font=("Helvetica", 8, "bold"))
        lbl.pack(side="left")

        val_lbl = tk.Label(header, text=f"{var.get():.2f}" if isinstance(from_, float) else f"{var.get()}", bg="#151c27", fg="#00d4ff", font=("Helvetica", 8, "bold"))
        val_lbl.pack(side="right")

        def _on_val_changed(val):
            parsed = float(val) if isinstance(from_, float) else int(float(val))
            formatted = f"{parsed:.2f}" if isinstance(from_, float) else f"{parsed}"
            val_lbl.config(text=formatted)
            # Atomically update thread-safe cache
            self.audio_cfg.set(param_key, parsed)
            if callback:
                callback(parsed)

        scale = tk.Scale(
            container, from_=from_, to=to, resolution=step, orient="horizontal",
            variable=var, command=_on_val_changed, bg="#151c27", fg="#00d4ff",
            troughcolor="#0d1117", activebackground="#00d4ff", highlightthickness=0, showvalue=False,
            width=8, sliderlength=15
        )
        scale.pack(fill="x", pady=0)

        hint = tk.Label(container, text=hint_text, bg="#151c27", fg="#607285", font=("Helvetica", 7))
        hint.pack(anchor="w")

    def _on_gain_change(self, val):
        set_hardware_gain(int(val))

    def _toggle_live_monitoring(self):
        """Toggles real-time audio monitor so user hears their filtered voice live in headphones."""
        with self.monitor_lock:
            if not self.is_monitoring:
                try:
                    if sys.platform.startswith("linux"):
                        self.monitor_proc = subprocess.Popen(
                            ["pw-play", "-a", "--rate", "16000", "--channels", "1", "--format", "s16", "--latency", "40ms", "-"],
                            stdin=subprocess.PIPE,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL
                        )
                    self.is_monitoring = True
                    self.btn_monitor.config(text="🎧 Monitor LIVE: ON (Active)", bg="#e65100")
                except Exception as e:
                    messagebox.showerror("Monitor Error", f"Failed to start live monitor: {e}")
            else:
                self.is_monitoring = False
                if self.monitor_proc is not None:
                    try:
                        self.monitor_proc.stdin.close()
                        self.monitor_proc.terminate()
                    except Exception:
                        pass
                    self.monitor_proc = None
                self.btn_monitor.config(text="🎧 Monitor LIVE: OFF", bg="#37474f")

    def apply_filter(self, audio_16k: np.ndarray, enable_agc: bool = True) -> np.ndarray:
        if audio_16k is None or len(audio_16k) == 0:
            return audio_16k
        try:
            # If single frame (e.g. 30ms / 480 samples)
            if len(audio_16k) <= 480:
                res = self._apply_filter_chunk(audio_16k, enable_agc=enable_agc)
                return np.clip(res, -32767.0, 32767.0).astype(np.int16)

            # For multi-frame audio (e.g. 3-second recorded sample), process in 480-sample blocks
            # so downward expansion cleanly gates out background noise during pauses
            frame_sz = 480
            out_frames = []
            for i in range(0, len(audio_16k), frame_sz):
                chunk = audio_16k[i:i+frame_sz]
                if len(chunk) < 64:
                    out_frames.append(chunk)
                else:
                    out_frames.append(self._apply_filter_chunk(chunk, enable_agc=enable_agc))
            concat = np.concatenate(out_frames)
            return np.clip(concat, -32767.0, 32767.0).astype(np.int16)
        except Exception:
            return audio_16k

    def _apply_filter_chunk(self, chunk_16k: np.ndarray, enable_agc: bool = True) -> np.ndarray:
        samples = chunk_16k.astype(np.float32)
        alpha = float(self.audio_cfg.get("pre_emphasis", 0.0))
        if alpha > 0.01:
            emp = np.empty_like(samples)
            emp[0] = samples[0]
            emp[1:] = samples[1:] - alpha * samples[:-1]
        else:
            emp = samples

        n = len(emp)
        fft_vals = np.fft.rfft(emp)
        freqs = np.fft.rfftfreq(n, d=1.0 / 16000.0)

        low_cut = float(self.audio_cfg.get("low_cutoff_hz", 40.0))
        high_cut = float(self.audio_cfg.get("high_cutoff_hz", 5800.0))
        treble = float(self.audio_cfg.get("treble_boost", 1.65))
        agc_max = float(self.audio_cfg.get("agc_max_scale", 1.50))
        bg_suppress_db = float(self.audio_cfg.get("bg_suppress_db", 28.0))
        act_thresh = float(self.audio_cfg.get("min_speech_rms", 820.0))

        gain = np.ones_like(freqs, dtype=np.float32)

        # 1. Clean sub-bass roll-off (cuts 50Hz/60Hz AC hum & rumble, fully preserves 80Hz+ male fundamental)
        sub_mask = freqs < low_cut
        gain[sub_mask] = np.clip((freqs[sub_mask] / max(1.0, low_cut)) ** 2, 0.0, 1.0)

        # 2. Smooth high-cut roll-off (cuts high-frequency electrical hiss above high_cut)
        high_mask = freqs > high_cut
        gain[high_mask] = np.clip(1.0 - (freqs[high_mask] - high_cut) / (8000.0 - high_cut), 0.05, 1.0)

        # 3. Gentle consonant clarity shelf (2.2kHz to 4.2kHz) for crisp intelligible speech without stinging
        clarity_mask = (freqs >= 2200.0) & (freqs <= 4200.0)
        gain[clarity_mask] *= treble

        filtered_fft = fft_vals * gain
        filtered = np.fft.irfft(filtered_fft, n=n)

        # 4. Background noise & hiss suppression gate (downward expansion)
        f_rms = float(np.sqrt(np.mean(filtered ** 2)))
        min_floor_gain = 10.0 ** (-bg_suppress_db / 20.0)

        if f_rms < act_thresh:
            # Below speech threshold: smooth soft-knee attenuation of background room murmur and hiss
            normalized = max(0.0, f_rms / max(1.0, act_thresh))
            gate_gain = min_floor_gain + (1.0 - min_floor_gain) * (normalized ** 2)
            filtered = filtered * gate_gain
        elif enable_agc:
            # Speech active: gentle AGC (only boosts speech, never amplifies noise)
            peak = np.max(np.abs(filtered))
            if peak > 20.0:
                scale = min(22000.0 / peak, agc_max)
                filtered = filtered * scale

        return filtered

    def _start_audio_stream(self):
        """Audio callback thread computes metrics directly, avoiding queue buildup and UI freezes."""
        vad = webrtcvad.Vad(3) if webrtcvad is not None else None

        def _audio_callback(indata, frames, time_info, status):
            if not self.is_running:
                return

            try:
                raw = indata.reshape(-1)
                # Resample if hardware rate does not match target 16kHz
                if len(raw) == self.target_frame_samples:
                    resampled = raw
                else:
                    resampled = np.interp(self.target_x, self.orig_x, raw).astype(np.int16)

                # Record sample buffer if active
                if self.is_recording_sample:
                    self.sample_buffer.append(resampled)

                # Raw RMS
                r_rms = float(np.sqrt(np.mean(resampled.astype(np.float32) ** 2)))

                # Filtered chunk without AGC (reflects true acoustic speech power)
                filtered_chunk = self.apply_filter(resampled, enable_agc=False)
                f_rms = float(np.sqrt(np.mean(filtered_chunk.astype(np.float32) ** 2)))

                # Proximity Crest Factor (Peak / RMS)
                peak_abs = float(np.max(np.abs(resampled)))
                crest = peak_abs / (f_rms + 1e-4)

                # Live Audio Monitor stream write
                if self.is_monitoring:
                    with self.monitor_lock:
                        if self.monitor_proc is not None and self.monitor_proc.stdin:
                            try:
                                # Apply AGC for monitoring so user hears boosted clarity
                                mon_chunk = self.apply_filter(resampled, enable_agc=True)
                                self.monitor_proc.stdin.write(mon_chunk.tobytes())
                                self.monitor_proc.stdin.flush()
                            except Exception:
                                pass

                # Read parameters safely from audio_cfg
                current_vad_mode = int(self.audio_cfg.get("vad_mode", 3))
                click_rej_ratio = float(self.audio_cfg.get("click_rejection_ratio", 0.35))
                fan_rej_ratio = float(self.audio_cfg.get("fan_rejection_ratio", 0.85))
                mult = float(self.audio_cfg.get("speech_multiplier", 2.65))
                m_rms = float(self.audio_cfg.get("min_speech_rms", 820.0))
                cont_ratio = float(self.audio_cfg.get("continue_ratio", 0.50))
                start_frames_req = int(self.audio_cfg.get("start_frames", 3))
                crest_min = float(self.audio_cfg.get("proximity_crest_min", 2.20))

                # WebRTC VAD
                v_speech = False
                if vad is not None:
                    try:
                        vad.set_mode(current_vad_mode)
                        v_speech = vad.is_speech(resampled.tobytes(), 16000)
                    except Exception:
                        v_speech = False

                # Acoustic feature analysis (Click and Fan detection)
                click_detected = False
                fan_detected = False
                try:
                    c_f32 = resampled.astype(np.float32)
                    c_fft = np.abs(np.fft.rfft(c_f32))
                    c_freqs = np.fft.rfftfreq(len(c_f32), 1.0 / 16000.0)
                    total_e = np.sum(c_fft**2) + 1e-6

                    # Transient click / typing check (>3600Hz and high peakiness)
                    high_e = np.sum(c_fft[c_freqs > 3600.0]**2)
                    if (high_e / total_e) > click_rej_ratio and crest > 3.5:
                        click_detected = True

                    # Narrowband fan drone check (requires SINGLE-BIN concentration >75% to avoid tripping on vowels)
                    fan_mask = (c_freqs >= 320.0) & (c_freqs <= 650.0)
                    fan_fft = c_fft[fan_mask]
                    if len(fan_fft) > 0:
                        fan_e = np.sum(fan_fft**2)
                        peak_bin = np.max(fan_fft**2)
                        if (fan_e / total_e) > fan_rej_ratio and (peak_bin / (fan_e + 1e-6)) > 0.70:
                            fan_detected = True
                except Exception:
                    pass

                # Active threshold calculation
                act_thresh = max(self.calibrated_ambient * mult, m_rms)
                cont_thresh = max(act_thresh * cont_ratio, m_rms * 0.70)

                # Detection decision (VAD + Energy + Proximity Crest Factor - Rejections)
                is_speech_frame = (
                    v_speech
                    and (f_rms >= act_thresh)
                    and (crest >= crest_min)
                    and (not click_detected)
                    and (not fan_detected)
                )

                # Streak management
                if is_speech_frame:
                    self.start_streak += 1
                else:
                    self.start_streak = max(0, self.start_streak - 1)

                is_trig = (self.start_streak >= start_frames_req)

                # Publish to GUI atomically
                with self.data_lock:
                    self.raw_rms = r_rms
                    self.filtered_rms = f_rms
                    self.crest_factor = crest
                    self.vad_speech = v_speech
                    self.is_click = click_detected
                    self.is_fan = fan_detected
                    self.is_speaking = is_trig
                    self.calibrated_threshold = act_thresh
                    self.continue_threshold_val = cont_thresh
            except Exception:
                pass

        if sys.platform.startswith("linux") and shutil.which("pw-record"):
            try:
                self.stream = PipeWireInputStream(
                    callback=_audio_callback,
                    samplerate=16000,
                    blocksize=self.target_frame_samples,
                    channels=1,
                    dtype="int16"
                )
                self.stream.start()
                print("[MicTuner] Connected directly to PipeWire default source (pw-record 16kHz)")
            except Exception as e:
                print(f"[MicTuner] PipeWire stream fallback to sounddevice: {e}")
                try:
                    self.stream = sd.InputStream(
                        device=self.target_dev,
                        samplerate=self.hw_sr,
                        blocksize=self.hw_frame_samples,
                        channels=1,
                        dtype="int16",
                        callback=_audio_callback
                    )
                    self.stream.start()
                except Exception as ex:
                    print(f"[MicTuner] Failed to open audio stream: {ex}")
        else:
            try:
                self.stream = sd.InputStream(
                    device=self.target_dev,
                    samplerate=self.hw_sr,
                    blocksize=self.hw_frame_samples,
                    channels=1,
                    dtype="int16",
                    callback=_audio_callback
                )
                self.stream.start()
            except Exception as e:
                print(f"[MicTuner] Failed to open audio stream: {e}")

    def _schedule_gui_update(self):
        """Pure GUI render loop: reads pre-computed values with zero blocking and zero deadlock risk."""
        if not self.is_running:
            return

        try:
            with self.data_lock:
                r_rms = self.raw_rms
                f_rms = self.filtered_rms
                crest = self.crest_factor
                v_speech = self.vad_speech
                is_click = self.is_click
                is_fan = self.is_fan
                is_speaking = self.is_speaking
                act_thresh = self.calibrated_threshold
                cont_thresh = self.continue_threshold_val
                ambient = self.calibrated_ambient
                streak = self.start_streak

            start_streak_required = int(self.audio_cfg.get("start_frames", 3))

            # Update VU meter displays (Scale 0 to 2500 RMS for phone mic & high-clarity headroom)
            max_meter = 2500.0
            raw_w = min(440, int((r_rms / max_meter) * 440))
            filt_w = min(440, int((f_rms / max_meter) * 440))
            thresh_x = min(440, int((act_thresh / max_meter) * 440))
            cont_x = min(440, int((cont_thresh / max_meter) * 440))

            self.raw_meter.coords(self.raw_bar, 0, 0, raw_w, 12)
            self.tunnel_meter.coords(self.tunnel_bar, 0, 0, filt_w, 12)
            self.tunnel_meter.coords(self.threshold_line, thresh_x, 0, thresh_x, 12)
            self.tunnel_meter.coords(self.continue_line, cont_x, 0, cont_x, 12)

            self.raw_val_lbl.config(text=f"RMS: {r_rms:5.1f}")
            self.tunnel_val_lbl.config(text=f"RMS: {f_rms:5.1f}")
            self.ambient_lbl.config(text=f"Ambient: {ambient:.1f}")
            self.thresh_lbl.config(text=f"Trigger: {act_thresh:.1f}")
            self.cont_lbl.config(text=f"Continue: {cont_thresh:.1f}")
            self.crest_lbl.config(text=f"Crest: {crest:.1f}x")
            self.vad_vote_lbl.config(
                text=f"VAD: {'YES' if v_speech else 'NO'} ({streak}/{start_streak_required})",
                fg="#00e676" if v_speech else "#8090a0"
            )
            self.click_lbl.config(
                text=f"Click: {'REJECTED' if is_click else 'OFF'}",
                fg="#ff1744" if is_click else "#8090a0"
            )
            self.fan_lbl.config(
                text=f"Fan Drone: {'SUPPRESSED' if is_fan else 'OFF'}",
                fg="#ff9100" if is_fan else "#8090a0"
            )

            # Update banner state
            if is_speaking:
                self.status_canvas.config(bg="#1b5e20")
                self.status_canvas.itemconfigure(self.status_text_id, text="🟢 HUMAN SPEECH DETECTED (TRIGGERED)", fill="#ffffff")
            elif is_click:
                self.status_canvas.config(bg="#37474f")
                self.status_canvas.itemconfigure(self.status_text_id, text="⚡ TRANSIENT CLICK / KEYBOARD SOUND REJECTED", fill="#ff8a80")
            elif is_fan:
                self.status_canvas.config(bg="#263238")
                self.status_canvas.itemconfigure(self.status_text_id, text="🌀 CONTINUOUS FAN DRONE SUPPRESSED", fill="#ffd180")
            elif v_speech:
                self.status_canvas.config(bg="#e65100")
                self.status_canvas.itemconfigure(self.status_text_id, text="🟡 VAD ACTIVE (BUILDING STREAK OR BELOW THRESHOLD)", fill="#ffffff")
            else:
                self.status_canvas.config(bg="#1a2332")
                self.status_canvas.itemconfigure(self.status_text_id, text="⚪ LISTENING FOR HUMAN VOICE (UP CLOSE)...", fill="#8090a0")
        except Exception:
            pass

        # Smooth 30ms render rate (33 FPS) with zero CPU lag
        self.root.after(30, self._schedule_gui_update)

    def _calibrate_room(self):
        """Measures room audio for 1 second in a worker thread and updates baseline."""
        self.btn_calibrate.config(text="Measuring...", state="disabled")

        def _cal_worker():
            chunks = []
            start = time.monotonic()
            while time.monotonic() - start < 1.0:
                with self.data_lock:
                    chunks.append(self.filtered_rms)
                time.sleep(0.04)
            if chunks:
                amb_rms = float(np.median(chunks))
                with self.data_lock:
                    self.calibrated_ambient = max(10.0, amb_rms)
            self.root.after(0, lambda: self.btn_calibrate.config(text="🎯 Calibrate Room (1s)", state="normal"))

        threading.Thread(target=_cal_worker, daemon=True).start()

    def _record_voice_sample(self):
        """Records a 3-second sample without blocking or freezing Tkinter."""
        self.btn_record.config(text="🔴 Recording 3s...", state="disabled", bg="#c62828")
        self.sample_buffer = []
        self.is_recording_sample = True

        def _record_worker():
            time.sleep(3.0)
            self.is_recording_sample = False
            if self.sample_buffer:
                self.recorded_sample_raw = np.concatenate(self.sample_buffer)
            self.root.after(0, lambda: self.btn_record.config(text="🎙️ Record 3s Sample", state="normal", bg="#00a8cc"))

        threading.Thread(target=_record_worker, daemon=True).start()

    def _play_raw_sample(self):
        if not hasattr(self, "recorded_sample_raw") or self.recorded_sample_raw is None or len(self.recorded_sample_raw) == 0:
            messagebox.showinfo("No Sample", "Please record a 3-second voice sample first.")
            return
        self._play_audio(self.recorded_sample_raw)

    def _play_filtered_sample(self):
        if not hasattr(self, "recorded_sample_raw") or self.recorded_sample_raw is None or len(self.recorded_sample_raw) == 0:
            messagebox.showinfo("No Sample", "Please record a 3-second voice sample first.")
            return
        filtered = self.apply_filter(self.recorded_sample_raw, enable_agc=True)
        self._play_audio(filtered)

    def _play_audio(self, pcm_16k: np.ndarray):
        """Plays audio asynchronously through PipeWire using pw-play."""
        def _play_worker():
            try:
                import io, wave
                buf = io.BytesIO()
                with wave.open(buf, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(16000)
                    wf.writeframes(pcm_16k.astype(np.int16).tobytes())
                subprocess.run(["pw-play", "-"], input=buf.getvalue(), check=False)
            except Exception as e:
                print(f"[Playback] Error: {e}")
        threading.Thread(target=_play_worker, daemon=True).start()

    def _save_configuration(self):
        all_params = self.audio_cfg.get_all()
        for k, v in all_params.items():
            self.cfg[k] = v

        save_config(self.cfg)
        messagebox.showinfo(
            "Saved Successfully",
            f"Mic & Multi-Layer VAD calibration saved to mic_config.json!\n\n"
            f"• Hardware Gain: {self.cfg['hardware_gain_pct']}%\n"
            f"• VAD Mode: {self.cfg['vad_mode']}\n"
            f"• Min RMS Baseline: {self.cfg['min_speech_rms']:.1f}\n"
            f"• Speech Multiplier: {self.cfg['speech_multiplier']:.2f}x\n"
            f"• Continue Ratio: {self.cfg.get('continue_ratio', 0.50):.2f}\n"
            f"• Proximity Crest Min: {self.cfg.get('proximity_crest_min', 2.0):.1f}x\n"
            f"• Low-Cut Bass Roll-off: {self.cfg['low_cutoff_hz']:.0f} Hz\n"
            f"• High-Cut Hiss Roll-off: {self.cfg['high_cutoff_hz']:.0f} Hz\n"
            f"• Treble Formant Boost: {self.cfg['treble_boost']:.2f}x\n"
            f"• Noise Suppression Gate: {self.cfg.get('bg_suppress_db', 20.0):.0f} dB\n"
            f"• Distance AGC Max: {self.cfg['agc_max_scale']:.1f}x\n\n"
            f"listen.py will automatically use these live values."
        )

    def _reset_defaults(self):
        for k, v in DEFAULT_CONFIG.items():
            self.cfg[k] = v
            self.audio_cfg.set(k, v)

        self.gain_var.set(self.cfg["hardware_gain_pct"])
        self.vad_var.set(self.cfg["vad_mode"])
        self.min_rms_var.set(self.cfg["min_speech_rms"])
        self.mult_var.set(self.cfg["speech_multiplier"])
        self.continue_ratio_var.set(self.cfg["continue_ratio"])
        self.frames_var.set(self.cfg["start_frames"])
        self.end_silence_var.set(self.cfg["end_silence_sec"])
        self.crest_var.set(self.cfg["proximity_crest_min"])
        self.low_cut_var.set(self.cfg["low_cutoff_hz"])
        self.high_cut_var.set(self.cfg["high_cutoff_hz"])
        self.treble_var.set(self.cfg["treble_boost"])
        self.bg_suppress_var.set(self.cfg.get("bg_suppress_db", 20.0))
        self.agc_var.set(self.cfg["agc_max_scale"])
        self.fan_rej_var.set(self.cfg["fan_rejection_ratio"])
        self.click_rej_var.set(self.cfg["click_rejection_ratio"])

        set_hardware_gain(self.cfg["hardware_gain_pct"])
        save_config(self.cfg)
        messagebox.showinfo("Reset", "Default parameters restored and saved.")

    def on_close(self):
        self.is_running = False
        with self.monitor_lock:
            if self.monitor_proc is not None:
                try:
                    self.monitor_proc.stdin.close()
                    self.monitor_proc.terminate()
                except Exception:
                    pass
                self.monitor_proc = None
        try:
            self.stream.stop()
            self.stream.close()
        except Exception:
            pass
        self.root.destroy()


def main():
    root = tk.Tk()
    app = MicTunerApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()

if __name__ == "__main__":
    main()
