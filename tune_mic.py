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

from audio_frontend import (
    Endpointer,
    load_mic_config,
    save_mic_config,
    bandpass_frame,
    clean_audio_for_transcription,
    audio_rms,
    DEFAULT_CONFIG,
    CONFIG_FILE,
)

def load_saved_config() -> dict:
    return load_mic_config(CONFIG_FILE)

def save_config(cfg: dict):
    save_mic_config(cfg, CONFIG_FILE)

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
        self.endpointer = Endpointer(self.cfg)
        self.endpointer.begin_turn(holdoff_sec=0.0)
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
        self.endpointer_state = Endpointer.STATE_WAITING
        self.live_silence_sec = 0.0
        self.live_floor = 50.0
        self.live_onset_thr = float(self.cfg.get("min_onset_rms", 220.0))
        self.live_cont_thr = float(self.cfg.get("min_continue_rms", 150.0))
        self.onset_candidates = 0
        self.onset_required = int(self.cfg.get("onset_required", 4))
        self.voiced_count = 0
        self.last_transition = ""
        self.last_transition_time = 0.0

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

        # Telemetry Indicators (Floor, Onset, Continue, VAD, Silence, Crest)
        info_row = tk.Frame(meter_frame, bg="#151c27")
        info_row.pack(fill="x", padx=8, pady=(1, 3))
        self.ambient_lbl = tk.Label(info_row, text="Floor: 50.0", bg="#151c27", fg="#8090a0", font=("Helvetica", 8))
        self.ambient_lbl.pack(side="left", padx=3)
        self.thresh_lbl = tk.Label(info_row, text="Onset: 220.0", bg="#151c27", fg="#ff9100", font=("Helvetica", 8))
        self.thresh_lbl.pack(side="left", padx=6)
        self.cont_lbl = tk.Label(info_row, text="Continue: 150.0", bg="#151c27", fg="#ffeb3b", font=("Helvetica", 8))
        self.cont_lbl.pack(side="left", padx=6)
        self.vad_vote_lbl = tk.Label(info_row, text="VAD: NO (0/4)", bg="#151c27", fg="#8090a0", font=("Helvetica", 8))
        self.vad_vote_lbl.pack(side="left", padx=6)
        self.silence_lbl = tk.Label(info_row, text="Silence: 0.00s", bg="#151c27", fg="#8090a0", font=("Helvetica", 8))
        self.silence_lbl.pack(side="left", padx=6)
        self.crest_lbl = tk.Label(info_row, text="Crest: 1.0x", bg="#151c27", fg="#8090a0", font=("Helvetica", 8))
        self.crest_lbl.pack(side="left", padx=6)

        # Main Controls Frame
        controls_container = tk.Frame(self.root, bg="#0f141c")
        controls_container.pack(side="top", fill="both", expand=True, padx=12, pady=2)

        # Left Column: Endpointer v2 Acoustic Onset & VAD Sensitivity
        col_left = tk.LabelFrame(controls_container, text=" Endpointer v2 Acoustic Onset & VAD ", bg="#151c27", fg="#00d4ff", font=("Helvetica", 9, "bold"))
        col_left.pack(side="left", fill="both", expand=True, padx=(0, 4))

        # Hardware Mic Gain Slider
        self.gain_var = tk.IntVar(value=int(self.cfg.get("hardware_gain_pct", 80)))
        self._create_slider(
            col_left, "hardware_gain_pct", "Hardware Mic Gain (%)", self.gain_var, 10, 100, 1,
            "System audio capture volume (wpctl/pactl). 80% optimized for phone mic in robot head.", self._on_gain_change
        )

        # WebRTC VAD Aggressiveness Mode (0 to 3)
        self.vad_var = tk.IntVar(value=int(self.cfg.get("vad_mode", 2)))
        self._create_slider(
            col_left, "vad_mode", "WebRTC VAD Aggressiveness", self.vad_var, 0, 3, 1,
            "Mode 2-3 isolates vocal formants while rejecting ambient crowd rumble"
        )

        # Onset SNR Gate (dB)
        self.onset_snr_var = tk.DoubleVar(value=float(self.cfg.get("onset_snr_db", 6.0)))
        self._create_slider(
            col_left, "onset_snr_db", "Speech Onset SNR Gate (dB over floor)", self.onset_snr_var, 2.0, 16.0, 0.5,
            "Decibels above measured room floor required to trigger recording"
        )

        # Continue SNR Gate (dB)
        self.cont_snr_var = tk.DoubleVar(value=float(self.cfg.get("continue_snr_db", 3.5)))
        self._create_slider(
            col_left, "continue_snr_db", "Speech Continue SNR Gate (dB over floor)", self.cont_snr_var, 1.0, 10.0, 0.5,
            "Decibels above floor needed to sustain recording during speech"
        )

        # Min Speech RMS Baseline (Absolute Floor)
        self.min_onset_var = tk.DoubleVar(value=float(self.cfg.get("min_onset_rms", 220.0)))
        self._create_slider(
            col_left, "min_onset_rms", "Min Speech RMS Floor", self.min_onset_var, 50.0, 1000.0, 10.0,
            "Absolute minimum vocal energy required to trigger speech onset"
        )

        # Max Speech RMS Clamp
        self.max_onset_var = tk.DoubleVar(value=float(self.cfg.get("max_onset_rms", 1300.0)))
        self._create_slider(
            col_left, "max_onset_rms", "Max Speech RMS Clamp", self.max_onset_var, 500.0, 3500.0, 50.0,
            "Upper limit clamp on onset threshold in extremely loud exhibition halls"
        )

        # Dynamic Speaker Envelope Ratio
        self.speaker_ratio_var = tk.DoubleVar(value=float(self.cfg.get("speaker_ratio", 0.32)))
        self._create_slider(
            col_left, "speaker_ratio", "Dynamic Speaker Envelope Ratio", self.speaker_ratio_var, 0.20, 0.70, 0.05,
            "Ratio of close speaker's voice power to maintain continue threshold"
        )

        # End Silence Cutoff Seconds
        self.end_silence_var = tk.DoubleVar(value=float(self.cfg.get("end_silence_sec", 0.80)))
        self._create_slider(
            col_left, "end_silence_sec", "End Silence Cutoff (Seconds)", self.end_silence_var, 0.30, 1.20, 0.05,
            "Continuous silence hangover before cutting off speech and sending to Whisper"
        )

        # Right Column: Vocal Tunnel DSP & Audio Monitoring
        col_right = tk.LabelFrame(controls_container, text=" Vocal Tunnel DSP & Engine Timers ", bg="#151c27", fg="#00d4ff", font=("Helvetica", 9, "bold"))
        col_right.pack(side="right", fill="both", expand=True, padx=(4, 0))

        # Low-Cut Filter Frequency
        self.low_cut_var = tk.DoubleVar(value=float(self.cfg.get("low_cutoff_hz", 70.0)))
        self._create_slider(
            col_right, "low_cutoff_hz", "Low-Cut Bass Roll-off (Hz)", self.low_cut_var, 40.0, 250.0, 5.0,
            "Cuts sub-bass rumble & AC hum while preserving vocal warmth (85Hz+)"
        )

        # High-Cut Filter Frequency
        self.high_cut_var = tk.DoubleVar(value=float(self.cfg.get("high_cutoff_hz", 4500.0)))
        self._create_slider(
            col_right, "high_cutoff_hz", "High-Cut Filter (Hz)", self.high_cut_var, 3000.0, 7500.0, 100.0,
            "Strips electrical hiss above 4.5kHz while preserving speech formants"
        )

        # Treble Formant Clarity Boost
        self.treble_var = tk.DoubleVar(value=float(self.cfg.get("treble_boost", 1.35)))
        self._create_slider(
            col_right, "treble_boost", "Treble / Consonant Clarity Boost (x)", self.treble_var, 1.0, 2.5, 0.05,
            "Subtle presence boost (2.0kHz-4.0kHz) for crisp consonant clarity"
        )

        # Dynamic Vocal AGC Max Scale
        self.agc_var = tk.DoubleVar(value=float(self.cfg.get("agc_max_scale", 1.80)))
        self._create_slider(
            col_right, "agc_max_scale", "AGC Max Scale (Whole Utterance)", self.agc_var, 1.0, 3.0, 0.1,
            "Peak normalization ceiling applied once across whole utterance"
        )

        # Startup Drain Holdoff (Seconds)
        self.startup_holdoff_var = tk.DoubleVar(value=float(self.cfg.get("startup_holdoff_sec", 0.45)))
        self._create_slider(
            col_right, "startup_holdoff_sec", "Startup Buffer Drain Holdoff (s)", self.startup_holdoff_var, 0.10, 1.00, 0.05,
            "Discards initial PipeWire buffer startup pops or touch screen thumps"
        )

        # Post-TTS Speaker Echo Drain Holdoff (Seconds)
        self.echo_holdoff_var = tk.DoubleVar(value=float(self.cfg.get("echo_holdoff_sec", 0.55)))
        self._create_slider(
            col_right, "echo_holdoff_sec", "Speaker Echo Drain Holdoff (s)", self.echo_holdoff_var, 0.20, 1.50, 0.05,
            "Discards Bluetooth speaker latency echo after Neurolis finishes speaking"
        )

        # First Turn Timeout (Seconds)
        self.first_turn_var = tk.DoubleVar(value=float(self.cfg.get("first_turn_timeout_sec", 15.0)))
        self._create_slider(
            col_right, "first_turn_timeout_sec", "First Turn Timeout (s)", self.first_turn_var, 5.0, 30.0, 1.0,
            "Timeout waiting for visitor's initial greeting before returning to standby"
        )

        # Followup Turn Timeout (Seconds)
        self.followup_var = tk.DoubleVar(value=float(self.cfg.get("followup_timeout_sec", 10.0)))
        self._create_slider(
            col_right, "followup_timeout_sec", "Followup Turn Timeout (s)", self.followup_var, 4.0, 20.0, 1.0,
            "Timeout waiting for followup question after robot answers"
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
            self.cfg[param_key] = parsed
            if hasattr(self, "endpointer") and self.endpointer is not None:
                self.endpointer.cfg[param_key] = parsed
                if param_key == "vad_mode" and self.endpointer.vad is not None:
                    try:
                        self.endpointer.vad.set_mode(int(parsed))
                    except Exception:
                        pass
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
        low_hz = float(self.audio_cfg.get("low_cutoff_hz", 85.0))
        high_hz = float(self.audio_cfg.get("high_cutoff_hz", 4500.0))
        if len(audio_16k) <= 480:
            return bandpass_frame(audio_16k, sample_rate=16000, low_hz=low_hz, high_hz=high_hz)
        floor = getattr(self, "live_floor", 50.0)
        agc_scale = float(self.audio_cfg.get("agc_max_scale", 1.80))
        return clean_audio_for_transcription(audio_16k, floor_rms=floor, sample_rate=16000, agc_max_scale=agc_scale)

    def _start_audio_stream(self):
        """Audio callback thread computes metrics directly, avoiding queue buildup and UI freezes."""
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

                # Raw RMS and crest factor
                r_rms = audio_rms(resampled)
                peak_abs = float(np.max(np.abs(resampled)))
                crest = peak_abs / (r_rms + 1e-4)

                # Feed directly to unified Endpointer v2 state machine!
                transition = self.endpointer.feed(resampled)
                now = time.monotonic()
                if transition == "ONSET":
                    self.last_transition = "ONSET"
                    self.last_transition_time = now
                elif transition == "END":
                    self.last_transition = f"END ({self.endpointer.done_reason})"
                    self.last_transition_time = now
                    # Auto re-arm waiting turn in tuner studio after 0.8s so user can test repeatedly
                    threading.Timer(0.8, lambda: self.endpointer.begin_turn(holdoff_sec=0.0)).start()

                # Live Audio Monitor stream write
                if self.is_monitoring:
                    with self.monitor_lock:
                        if self.monitor_proc is not None and self.monitor_proc.stdin:
                            try:
                                low_h = float(self.audio_cfg.get("low_cutoff_hz", 85.0))
                                high_h = float(self.audio_cfg.get("high_cutoff_hz", 4500.0))
                                mon_chunk = bandpass_frame(resampled, 16000, low_h, high_h)
                                self.monitor_proc.stdin.write(mon_chunk.tobytes())
                                self.monitor_proc.stdin.flush()
                            except Exception:
                                pass

                # Publish to GUI atomically
                with self.data_lock:
                    self.raw_rms = r_rms
                    self.filtered_rms = self.endpointer.live_rms
                    self.crest_factor = crest
                    self.vad_speech = self.endpointer.live_vad
                    self.endpointer_state = self.endpointer.state
                    self.live_silence_sec = self.endpointer.live_silence_sec
                    self.live_floor = self.endpointer.live_floor
                    self.live_onset_thr = self.endpointer.live_onset_thr
                    self.live_cont_thr = self.endpointer.live_cont_thr
                    self.onset_candidates = sum(self.endpointer.onset_hist)
                    self.voiced_count = self.endpointer.voiced_count
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
                ep_state = self.endpointer_state
                silence_sec = self.live_silence_sec
                floor = self.live_floor
                act_thresh = self.live_onset_thr
                cont_thresh = self.live_cont_thr
                cand_cnt = self.onset_candidates
                voiced_cnt = self.voiced_count

            onset_req = int(self.audio_cfg.get("onset_required", 4))

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
            self.ambient_lbl.config(text=f"Floor: {floor:.1f}")
            self.thresh_lbl.config(text=f"Onset: {act_thresh:.1f}")
            self.cont_lbl.config(text=f"Continue: {cont_thresh:.1f}")
            self.crest_lbl.config(text=f"Crest: {crest:.1f}x")
            self.vad_vote_lbl.config(
                text=f"VAD: {'YES' if v_speech else 'NO'} ({cand_cnt}/{onset_req})",
                fg="#00e676" if v_speech else "#8090a0"
            )
            self.silence_lbl.config(
                text=f"Silence: {silence_sec:.2f}s",
                fg="#ffeb3b" if ep_state == Endpointer.STATE_RECORDING else "#8090a0"
            )

            # Update banner state based on endpointer_state
            if ep_state == Endpointer.STATE_RECORDING:
                self.status_canvas.config(bg="#1b5e20")
                self.status_canvas.itemconfigure(
                    self.status_text_id,
                    text=f"🟢 VOICE LOCKED // RECORDING (Voiced: {voiced_cnt} frames | Silence: {silence_sec:.2f}s)",
                    fill="#ffffff"
                )
            elif ep_state == Endpointer.STATE_DONE:
                self.status_canvas.config(bg="#004d40")
                self.status_canvas.itemconfigure(
                    self.status_text_id,
                    text=f"✅ UTTERANCE CAPTURED ({self.last_transition})",
                    fill="#a7ffeb"
                )
            elif ep_state == Endpointer.STATE_HOLDOFF:
                self.status_canvas.config(bg="#0d233a")
                self.status_canvas.itemconfigure(
                    self.status_text_id,
                    text="⏳ DRAINING STARTUP / ECHO BUFFER...",
                    fill="#80d8ff"
                )
            elif v_speech:
                self.status_canvas.config(bg="#e65100")
                self.status_canvas.itemconfigure(
                    self.status_text_id,
                    text=f"🟡 VAD SPEECH ACTIVE ({cand_cnt}/{onset_req} onset frames)",
                    fill="#ffffff"
                )
            else:
                self.status_canvas.config(bg="#1a2332")
                self.status_canvas.itemconfigure(
                    self.status_text_id,
                    text=f"⚪ WAITING FOR SPEECH (Floor: {floor:.1f} RMS | Need {act_thresh:.1f} RMS)",
                    fill="#8090a0"
                )
        except Exception:
            pass

        # Smooth 30ms render rate (33 FPS) with zero CPU lag
        self.root.after(30, self._schedule_gui_update)

    def _calibrate_room(self):
        """Measures room audio for 1.5 seconds in a worker thread and updates baseline."""
        self.btn_calibrate.config(text="Measuring...", state="disabled")

        def _cal_worker():
            chunks = []
            time.sleep(0.15)  # Discard startup transients
            start = time.monotonic()
            while time.monotonic() - start < 1.5:
                with self.data_lock:
                    chunks.append(self.filtered_rms)
                time.sleep(0.03)
            if chunks:
                amb_median = float(np.median(chunks))
                amb_p90 = float(np.percentile(chunks, 90))
                with self.data_lock:
                    self.live_floor = amb_median
                if hasattr(self, "endpointer") and self.endpointer is not None:
                    self.endpointer.floor_win.clear()
                    for _ in range(20):
                        self.endpointer.floor_win.append(amb_median)

                onset_snr = float(self.audio_cfg.get("onset_snr_db", 6.0))
                min_onset = float(self.audio_cfg.get("min_onset_rms", 220.0))
                max_onset = float(self.audio_cfg.get("max_onset_rms", 1300.0))
                new_onset = float(np.clip(amb_median * (10.0 ** (onset_snr / 20.0)), min_onset, max_onset))

                cont_snr = float(self.audio_cfg.get("continue_snr_db", 3.5))
                min_cont = float(self.audio_cfg.get("min_continue_rms", 150.0))
                new_cont = max(amb_median * (10.0 ** (cont_snr / 20.0)), min_cont)

                self.cfg["ambient_p90_rms"] = round(amb_p90, 1)
                self.cfg["calibrated_start_rms"] = round(new_onset, 1)
                self.cfg["calibrated_continue_rms"] = round(new_cont, 1)
                save_config(self.cfg)
            self.root.after(0, lambda: self.btn_calibrate.config(text="🎯 Calibrate Room (1.5s)", state="normal"))

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
        floor = getattr(self, "live_floor", 50.0)
        agc_scale = float(self.audio_cfg.get("agc_max_scale", 1.80))
        filtered = clean_audio_for_transcription(self.recorded_sample_raw, floor_rms=floor, sample_rate=16000, agc_max_scale=agc_scale)
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
            f"Endpointer v2 & DSP configuration saved to mic_config.json!\n\n"
            f"• Hardware Gain: {self.cfg.get('hardware_gain_pct', 80)}%\n"
            f"• VAD Mode: {self.cfg.get('vad_mode', 2)}\n"
            f"• Onset SNR: {self.cfg.get('onset_snr_db', 6.0)} dB\n"
            f"• Continue SNR: {self.cfg.get('continue_snr_db', 3.5)} dB\n"
            f"• Min Onset RMS: {self.cfg.get('min_onset_rms', 220.0):.1f}\n"
            f"• Max Onset RMS: {self.cfg.get('max_onset_rms', 1300.0):.1f}\n"
            f"• Dynamic Speaker Ratio: {self.cfg.get('speaker_ratio', 0.32):.2f}\n"
            f"• End Silence Cutoff: {self.cfg.get('end_silence_sec', 0.80):.2f}s\n"
            f"• Startup Holdoff: {self.cfg.get('startup_holdoff_sec', 0.45):.2f}s\n"
            f"• Echo Holdoff: {self.cfg.get('echo_holdoff_sec', 0.55):.2f}s\n"
            f"• Bandpass: {self.cfg.get('low_cutoff_hz', 70.0):.0f}Hz - {self.cfg.get('high_cutoff_hz', 4500.0):.0f}Hz\n"
            f"• Treble Boost: {self.cfg.get('treble_boost', 1.35):.2f}x\n"
            f"• AGC Max Scale: {self.cfg.get('agc_max_scale', 1.80):.2f}x\n\n"
            f"listen.py automatically reloads these values on every conversation turn."
        )

    def _reset_defaults(self):
        for k, v in DEFAULT_CONFIG.items():
            self.cfg[k] = v
            self.audio_cfg.set(k, v)
            if hasattr(self, "endpointer") and self.endpointer is not None:
                self.endpointer.cfg[k] = v

        if hasattr(self, "gain_var"): self.gain_var.set(self.cfg["hardware_gain_pct"])
        if hasattr(self, "vad_var"): self.vad_var.set(self.cfg["vad_mode"])
        if hasattr(self, "onset_snr_var"): self.onset_snr_var.set(self.cfg["onset_snr_db"])
        if hasattr(self, "cont_snr_var"): self.cont_snr_var.set(self.cfg["continue_snr_db"])
        if hasattr(self, "min_onset_var"): self.min_onset_var.set(self.cfg["min_onset_rms"])
        if hasattr(self, "max_onset_var"): self.max_onset_var.set(self.cfg["max_onset_rms"])
        if hasattr(self, "speaker_ratio_var"): self.speaker_ratio_var.set(self.cfg["speaker_ratio"])
        if hasattr(self, "end_silence_var"): self.end_silence_var.set(self.cfg["end_silence_sec"])
        if hasattr(self, "low_cut_var"): self.low_cut_var.set(self.cfg["low_cutoff_hz"])
        if hasattr(self, "high_cut_var"): self.high_cut_var.set(self.cfg["high_cutoff_hz"])
        if hasattr(self, "treble_var"): self.treble_var.set(self.cfg["treble_boost"])
        if hasattr(self, "agc_var"): self.agc_var.set(self.cfg["agc_max_scale"])
        if hasattr(self, "startup_holdoff_var"): self.startup_holdoff_var.set(self.cfg["startup_holdoff_sec"])
        if hasattr(self, "echo_holdoff_var"): self.echo_holdoff_var.set(self.cfg["echo_holdoff_sec"])
        if hasattr(self, "first_turn_var"): self.first_turn_var.set(self.cfg["first_turn_timeout_sec"])
        if hasattr(self, "followup_var"): self.followup_var.set(self.cfg["followup_timeout_sec"])

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
