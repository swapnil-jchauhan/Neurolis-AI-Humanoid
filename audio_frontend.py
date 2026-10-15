#!/usr/bin/env python3
"""
Project Neurolis - Unified Audio Frontend & Endpointer v2
Single source of truth for audio preprocessing, filtering, and Voice Activity Endpointing.
Shared directly between listen.py (robot brain) and tune_mic.py (calibration studio).
"""

import os
import sys
import time
import json
from pathlib import Path
from collections import deque
from typing import Optional, Tuple, Dict, Any

import numpy as np

try:
    import webrtcvad
except ImportError:
    webrtcvad = None

CONFIG_FILE = Path(__file__).resolve().parent / "mic_config.json"

DEFAULT_CONFIG: Dict[str, Any] = {
    # Endpointer v2 configuration
    "vad_mode": 2,
    "onset_snr_db": 6.0,
    "continue_snr_db": 3.0,
    "min_onset_rms": 30.0,
    "max_onset_rms": 1300.0,
    "min_continue_rms": 20.0,
    "onset_window": 8,
    "onset_required": 4,
    "speaker_ratio": 0.32,
    "end_silence_sec": 0.80,
    "min_voiced_frames": 6,
    "tail_pad_frames": 7,
    "startup_holdoff_sec": 0.45,
    "echo_holdoff_sec": 0.55,
    "first_turn_timeout_sec": 15.0,
    "followup_timeout_sec": 10.0,
    "preroll_sec": 0.85,
    "manual_buffer_sec": 3.45,
    "max_record_sec": 9.0,
    "hardware_gain_pct": 80,
    "pw_target": "android-e3b0c44",

    # DSP and bandpass tuning
    "low_cutoff_hz": 70.0,
    "high_cutoff_hz": 4500.0,
    "treble_boost": 1.35,
    "agc_max_scale": 1.80,

    # Legacy compatibility keys (preserved in file for older tools)
    "min_speech_rms": 180.0,
    "speech_multiplier": 1.45,
    "continue_ratio": 0.70,
    "start_frames": 3,
    "pre_emphasis": 0.0,
    "bg_suppress_db": 24.0,
    "agc_target_peak": 22000.0,
    "fan_rejection_ratio": 0.85,
    "click_rejection_ratio": 0.35,
    "proximity_crest_min": 1.5,
    "ambient_p90_rms": 50.0,
    "calibrated_start_rms": 300.0,
    "calibrated_continue_rms": 220.0
}


def load_mic_config(path: Optional[Path] = None) -> Dict[str, Any]:
    """Loads configuration with robust fallback to default keys."""
    cfg = dict(DEFAULT_CONFIG)
    p = path or CONFIG_FILE
    if p.exists():
        try:
            with open(p, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                cfg.update(loaded)
        except Exception as e:
            print(f"[AudioFrontend] Config load error ({p}): {e}")
    return cfg


def save_mic_config(cfg: Dict[str, Any], path: Optional[Path] = None):
    """Safely saves configuration dictionary to disk."""
    p = path or CONFIG_FILE
    try:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        print(f"[AudioFrontend] Config save error ({p}): {e}")


def audio_rms(audio: np.ndarray) -> float:
    """Calculates RMS loudness of an int16 or float32 audio array."""
    if audio is None or audio.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(audio.astype(np.float32) ** 2)))


def bandpass_frame(chunk: np.ndarray, sample_rate: int = 16000,
                   low_hz: float = 85.0, high_hz: float = 4500.0) -> np.ndarray:
    """Fast FFT bandpass filter for real-time 30ms (480-sample) audio chunks.
    Isolates vocal fundamental frequencies and formants (85Hz-4500Hz).
    """
    if chunk is None or len(chunk) < 64:
        return chunk
    try:
        samples = chunk.astype(np.float32)
        n = len(samples)
        fft_vals = np.fft.rfft(samples)
        freqs = np.fft.rfftfreq(n, d=1.0 / sample_rate)
        gain = np.ones_like(freqs, dtype=np.float32)

        low_cut = max(20.0, float(low_hz))
        high_cut = min(float(sample_rate) / 2.0 - 100.0, float(high_hz))

        sub_mask = freqs < low_cut
        gain[sub_mask] = np.clip((freqs[sub_mask] / low_cut) ** 2, 0.0, 1.0)

        high_mask = freqs > high_cut
        gain[high_mask] = np.clip((high_cut / np.maximum(freqs[high_mask], 1.0)) ** 4, 0.0, 1.0)

        filtered = np.fft.irfft(fft_vals * gain, n=n)
        return np.clip(filtered, -32768.0, 32767.0).astype(np.int16)
    except Exception:
        return chunk


def clean_audio_for_transcription(audio: np.ndarray, floor_rms: float,
                                 sample_rate: int = 16000,
                                 agc_max_scale: float = 1.8) -> np.ndarray:
    """Whole-utterance audio cleaning for Whisper STT.
    1. FFT bandpass 85Hz-5500Hz with 1.35x consonant presence shelf at 2.0kHz-4.0kHz.
    2. Time-domain downward expander applied ONLY when floor_rms > 350.0 (loud exhibition hall).
       In quiet or moderate rooms, skips the expander so Whisper receives pristine phonemes.
    3. Single peak normalization capped at agc_max_scale.
    """
    if audio is None or audio.size == 0:
        return audio
    try:
        samples = audio.astype(np.float32)
        n = len(samples)

        # 1. Whole-utterance FFT bandpass & presence shelf
        fft_vals = np.fft.rfft(samples)
        freqs = np.fft.rfftfreq(n, d=1.0 / sample_rate)
        gain = np.ones_like(freqs, dtype=np.float32)

        sub_mask = freqs < 70.0
        gain[sub_mask] = np.clip((freqs[sub_mask] / 70.0) ** 2, 0.0, 1.0)

        high_mask = freqs > 5500.0
        gain[high_mask] = np.clip(1.0 - (freqs[high_mask] - 5500.0) / (8000.0 - 5500.0), 0.05, 1.0)

        clarity_mask = (freqs >= 2000.0) & (freqs <= 4000.0)
        gain[clarity_mask] *= 1.35

        filtered = np.fft.irfft(fft_vals * gain, n=n)

        # 2. Downward expander for loud rooms only (floor_rms > 350.0)
        if floor_rms > 350.0:
            frame_len = int(0.020 * sample_rate)  # 20ms frames
            if frame_len > 0 and n >= frame_len:
                num_frames = (n + frame_len - 1) // frame_len
                frame_rms_list = [
                    float(np.sqrt(np.mean(filtered[k * frame_len : min(n, (k + 1) * frame_len)] ** 2)))
                    for k in range(num_frames)
                ]
                speech_p90 = float(np.percentile(frame_rms_list, 90)) if frame_rms_list else 1000.0
                thresh = min(speech_p90 * 0.20, float(floor_rms) * 1.25)

                frame_gains = np.array([0.35 if r < thresh else 1.0 for r in frame_rms_list], dtype=np.float32)
                gain_envelope = np.repeat(frame_gains, frame_len)[:n]

                kernel_sz = min(160, len(gain_envelope))
                if kernel_sz > 1:
                    kernel = np.ones(kernel_sz, dtype=np.float32) / kernel_sz
                    gain_envelope = np.convolve(gain_envelope, kernel, mode="same")

                filtered = filtered * gain_envelope

        # 3. Peak normalization across the whole utterance
        peak = float(np.max(np.abs(filtered)))
        if peak > 20.0:
            scale = min(24000.0 / peak, float(agc_max_scale))
            filtered = filtered * scale

        return np.clip(filtered, -32767.0, 32767.0).astype(np.int16)
    except Exception:
        return audio


class Endpointer:
    """Formal Voice Activity Endpointer State Machine (v2).
    States:
      HOLDOFF   - Discards initial touch clicks, PipeWire buffer startup pops, or post-TTS speaker echo.
      WAITING   - Tracks rolling background floor; triggers ONSET via sliding-window (e.g. 4 of 8 frames).
      RECORDING - Time-based hangover endpointing; tracks exact last_voiced_idx; trims by index.
      DONE      - Utterance completed; provides audio buffer and validation status.
    """

    STATE_HOLDOFF = "HOLDOFF"
    STATE_WAITING = "WAITING"
    STATE_RECORDING = "RECORDING"
    STATE_DONE = "DONE"

    def __init__(self, cfg: Optional[Dict[str, Any]] = None, seed_floor: float = 50.0):
        self.cfg = dict(DEFAULT_CONFIG)
        if cfg:
            self.cfg.update(cfg)

        self.sample_rate = 16000
        self.frame_samples = 480  # 30ms
        self.frame_sec = 0.03

        # Persistent floor history across turns
        self.floor_win = deque(maxlen=66)  # ~2.0 seconds history
        initial_seed = max(10.0, float(seed_floor))
        for _ in range(20):
            self.floor_win.append(initial_seed)

        # WebRTC VAD instance
        vad_mode = int(self.cfg.get("vad_mode", 2))
        self.vad = webrtcvad.Vad(vad_mode) if webrtcvad is not None else None

        # Per-turn state
        self.state = self.STATE_WAITING
        self.turn_started_at = time.monotonic()
        self.holdoff_until = 0.0

        preroll_len = max(1, int(float(self.cfg.get("preroll_sec", 0.85)) / self.frame_sec))
        manual_len = max(1, int(float(self.cfg.get("manual_buffer_sec", 3.45)) / self.frame_sec))
        self.preroll = deque(maxlen=preroll_len)
        self.manual_buf = deque(maxlen=manual_len)

        onset_win_len = max(2, int(self.cfg.get("onset_window", 8)))
        self.onset_hist = deque(maxlen=onset_win_len)

        self.frames = []
        self.voiced_rms = []
        self.speaker_vals = deque(maxlen=60)
        self.last_voiced_idx = 0
        self.voiced_count = 0
        self.recording_started_at = 0.0

        self.is_manual_send = False
        self.done_reason = ""
        self.result_audio = None
        self.result_info = {}

        # Telemetry for live HUD / tuner meters
        self.live_rms = 0.0
        self.live_vad = False
        self.live_floor = initial_seed
        self.live_onset_thr = float(self.cfg.get("min_onset_rms", 30.0))
        self.live_cont_thr = float(self.cfg.get("min_continue_rms", 20.0))
        self.live_silence_sec = 0.0

    def begin_turn(self, holdoff_sec: Optional[float] = None):
        """Prepares endpointer for a new turn.
        Any holdoff period immediately discards arriving frames to block startup pops or speaker echo.
        """
        now = time.monotonic()
        self.turn_started_at = now
        duration = float(holdoff_sec) if holdoff_sec is not None else float(self.cfg.get("startup_holdoff_sec", 0.45))
        self.holdoff_until = now + duration
        self.state = self.STATE_HOLDOFF if duration > 0.0 else self.STATE_WAITING

        self.preroll.clear()
        self.manual_buf.clear()
        self.onset_hist.clear()
        self.frames = []
        self.voiced_rms = []
        self.speaker_vals.clear()
        self.last_voiced_idx = 0
        self.voiced_count = 0
        self.recording_started_at = 0.0
        self.is_manual_send = False
        self.done_reason = ""
        self.result_audio = None
        self.result_info = {}
        self.live_silence_sec = 0.0

    def feed(self, chunk: np.ndarray) -> Optional[str]:
        """Feeds one 30ms (480-sample) int16 chunk into the endpointer.
        Returns:
          "ONSET" - Speech onset detected; transitioning from WAITING to RECORDING.
          "END"   - Speech endpoint reached; audio ready in result().
          None    - No state transition.
        """
        if chunk is None or len(chunk) < self.frame_samples:
            return None

        now = time.monotonic()

        # 1. State: HOLDOFF (Drain transient pops, touch tap vibrations, or acoustic speaker delay)
        if self.state == self.STATE_HOLDOFF:
            if now < self.holdoff_until:
                return None
            self.state = self.STATE_WAITING

        raw_chunk = chunk.astype(np.int16, copy=False)
        self.manual_buf.append(raw_chunk)

        # Feature extraction on filtered chunk
        filt = bandpass_frame(
            raw_chunk,
            sample_rate=self.sample_rate,
            low_hz=float(self.cfg.get("low_cutoff_hz", 85.0)),
            high_hz=float(self.cfg.get("high_cutoff_hz", 4500.0)),
        )
        rms = audio_rms(filt)
        self.live_rms = rms

        vad_speech = False
        if self.vad is not None:
            try:
                vad_speech = self.vad.is_speech(filt.tobytes(), self.sample_rate)
            except Exception:
                vad_speech = False
        self.live_vad = vad_speech

        # 2. State: WAITING (Floor estimation and sliding-window onset detection)
        if self.state == self.STATE_WAITING:
            self.preroll.append(raw_chunk)

            # Rolling ambient floor tracking (exclude sudden vocal bursts from raising the floor)
            prev_onset = self.live_onset_thr
            if rms < 2.0 * prev_onset:
                self.floor_win.append(rms)

            floor = float(np.percentile(self.floor_win, 50))
            self.live_floor = floor

            onset_snr_db = float(self.cfg.get("onset_snr_db", 6.0))
            min_onset_rms = float(self.cfg.get("min_onset_rms", 30.0))
            max_onset_rms = float(self.cfg.get("max_onset_rms", 1300.0))
            onset_thr = float(np.clip(floor * (10.0 ** (onset_snr_db / 20.0)), min_onset_rms, max_onset_rms))
            self.live_onset_thr = onset_thr

            cont_snr_db = float(self.cfg.get("continue_snr_db", 3.0))
            min_continue_rms = float(self.cfg.get("min_continue_rms", 20.0))
            cont_base = max(floor * (10.0 ** (cont_snr_db / 20.0)), min_continue_rms)
            self.live_cont_thr = cont_base

            # Candidate frame requires exceeding onset threshold + VAD (or strong energy boost if VAD misses)
            cand = (rms >= onset_thr) and (vad_speech or (rms >= 1.8 * onset_thr))
            self.onset_hist.append(cand)

            onset_req = int(self.cfg.get("onset_required", 4))
            if sum(self.onset_hist) >= onset_req:
                # Transition to RECORDING!
                self.state = self.STATE_RECORDING
                self.recording_started_at = now
                self.frames = list(self.preroll)
                self.voiced_count = sum(self.onset_hist)
                self.last_voiced_idx = len(self.frames) - 1
                self.speaker_vals.clear()
                self.speaker_vals.append(rms)
                self.voiced_rms = [rms]
                return "ONSET"

            return None

        # 3. State: RECORDING (Time-based hangover endpointing with index trimming)
        if self.state == self.STATE_RECORDING:
            self.frames.append(raw_chunk)

            # Estimate active speaker level to reject distant crowd noise without per-frame peak chasing
            spk = float(np.median(self.speaker_vals)) if len(self.speaker_vals) >= 5 else rms
            speaker_ratio = float(self.cfg.get("speaker_ratio", 0.40))
            cont_thr = max(self.live_cont_thr, speaker_ratio * spk)
            self.live_cont_thr = cont_thr

            voiced = (rms >= cont_thr) and (vad_speech or (rms >= 1.6 * cont_thr))
            if voiced:
                self.last_voiced_idx = len(self.frames) - 1
                self.voiced_count += 1
                self.voiced_rms.append(rms)
                self.speaker_vals.append(rms)

            silence_sec = (len(self.frames) - 1 - self.last_voiced_idx) * self.frame_sec
            self.live_silence_sec = silence_sec

            end_silence_sec = float(self.cfg.get("end_silence_sec", 0.55))
            max_record_sec = float(self.cfg.get("max_record_sec", 9.0))
            elapsed = now - self.recording_started_at

            if silence_sec >= end_silence_sec:
                self._finalize(reason="silence", is_manual=False)
                return "END"
            elif elapsed >= max_record_sec:
                self._finalize(reason="max_record", is_manual=False)
                return "END"

            return None

        return None

    def force_send(self):
        """Immediately dispatches recorded audio (0ms override on Send button or Enter)."""
        if self.state != self.STATE_RECORDING and len(self.manual_buf) > 0:
            self.frames = list(self.manual_buf)
            self.recording_started_at = time.monotonic() - (len(self.frames) * self.frame_sec)
            self.last_voiced_idx = len(self.frames) - 1
            self.voiced_count = len(self.frames)

        self._finalize(reason="manual_send", is_manual=True)

    def _finalize(self, reason: str, is_manual: bool):
        """Finalizes audio buffer and performs strict acceptance validation."""
        self.state = self.STATE_DONE
        self.done_reason = reason
        self.is_manual_send = is_manual

        if not self.frames:
            self.result_audio = None
            self.result_info = {"accepted": False, "reason": "empty_frames"}
            return

        # Tail trimming by index (keeps tail_pad_frames so final words are never clipped)
        tail_pad = int(self.cfg.get("tail_pad_frames", 6))
        if not is_manual and reason == "silence":
            trim_idx = min(len(self.frames), self.last_voiced_idx + 1 + tail_pad)
            trimmed_frames = self.frames[:trim_idx]
        else:
            trimmed_frames = self.frames

        audio = np.concatenate(trimmed_frames)
        dur = audio.size / float(self.sample_rate)
        p90_rms = float(np.percentile(self.voiced_rms, 90)) if self.voiced_rms else audio_rms(audio)

        # Validation (Bypass validation on manual send)
        accepted = True
        reject_reason = ""
        min_voiced_frames = int(self.cfg.get("min_voiced_frames", 8))
        min_onset_rms = float(self.cfg.get("min_onset_rms", 30.0))

        if not is_manual:
            if self.voiced_count < min_voiced_frames:
                accepted = False
                reject_reason = f"voiced_frames_too_low({self.voiced_count}<{min_voiced_frames})"
            elif p90_rms < max(min_onset_rms, self.live_floor * 1.35):
                accepted = False
                reject_reason = f"p90_rms_too_low({p90_rms:.1f}<{max(min_onset_rms, self.live_floor * 1.35):.1f})"

        self.result_audio = audio if accepted else None
        self.result_info = {
            "accepted": accepted,
            "reason": reject_reason if not accepted else reason,
            "duration": round(dur, 2),
            "voiced_frames": self.voiced_count,
            "p90_rms": round(p90_rms, 1),
            "floor_rms": round(self.live_floor, 1),
            "onset_thr": round(self.live_onset_thr, 1),
            "is_manual": is_manual
        }

        # Structured diagnostic log
        status_tag = "ACCEPT" if accepted else f"REJECT({reject_reason})"
        print(
            f"[Endpointer] {status_tag} | reason={reason} dur={dur:.2f}s "
            f"voiced={self.voiced_count} p90={p90_rms:.1f} floor={self.live_floor:.1f}"
        )

        # Optional audio dump for offline regression analysis
        if os.environ.get("NEUROLIS_DEBUG_AUDIO") == "1" and audio.size > 0:
            try:
                dump_dir = Path(__file__).resolve().parent / "debug_audio"
                dump_dir.mkdir(exist_ok=True)
                tag = "accepted" if accepted else "rejected"
                ts = int(time.time() * 1000)
                dump_path = dump_dir / f"turn_{ts}_{tag}.wav"
                import wave
                with wave.open(str(dump_path), "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(self.sample_rate)
                    wf.writeframes(audio.tobytes())
            except Exception:
                pass

    def result(self) -> Tuple[Optional[np.ndarray], Dict[str, Any]]:
        """Returns the final audio array and diagnostic metadata."""
        return self.result_audio, self.result_info

    @property
    def live_stats(self) -> Dict[str, Any]:
        """Live telemetry dictionary for HUD, Face UI, and tune_mic meters."""
        return {
            "state": self.state,
            "rms": self.live_rms,
            "vad": self.live_vad,
            "floor": self.live_floor,
            "onset_thr": self.live_onset_thr,
            "cont_thr": self.live_cont_thr,
            "silence_sec": self.live_silence_sec,
        }
