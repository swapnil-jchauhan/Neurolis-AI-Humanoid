#!/usr/bin/env python3
"""
Project Neurolis - Unified Audio Frontend & Endpointer v3
Single source of truth for audio preprocessing, filtering, and Voice Activity Endpointing.
Shared directly between listen.py (robot brain) and tune_mic.py (calibration studio).

v3 adds, on top of the v2 state machine:
  - SpectralDenoiser    streaming Wiener-style noise suppression (per frame + whole utterance)
  - ChannelMixer        multi-channel input reduction, with a documented beamformer hook for a mic array
  - Resampler           anti-aliased streaming resampling from the device rate to 16 kHz
  - Loud-room awareness (Endpointer.is_loud), a floor estimate that cannot deadlock, a locked speaker level,
    a voiced-density hangover, and always-trimmed tails
"""

import os
import sys
import time
import json
from pathlib import Path
from collections import deque
from typing import Optional, Tuple, Dict, Any, List, Callable

import numpy as np

try:
    import webrtcvad
except ImportError:
    webrtcvad = None

CONFIG_FILE = Path(__file__).resolve().parent / "mic_config.json"

DEFAULT_CONFIG: Dict[str, Any] = {
    # Endpointer configuration
    "vad_mode": 2,
    "onset_snr_db": 6.0,
    "continue_snr_db": 4.5,
    "min_onset_rms": 40.0,
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
    "preroll_sec": 0.5,
    "manual_buffer_sec": 3.45,
    "max_record_sec": 9.0,
    "hardware_gain_pct": 80,
    "pw_target": "",  # PipeWire --target node name; empty = system default source

    # Loud-room mode (entered automatically by the Endpointer; see Endpointer.is_loud)
    # loud_enter_rms / loud_exit_rms are written for a mic where normal speech reads ~550 RMS. They are scaled by the
    # speech level this mic actually produces (speech_level_ref, learned from accepted utterances), so a "hot" mic or
    # a high Windows input level does not look permanently loud.
    "loud_enter_rms": 160.0,        # in-band room floor that counts as "loud"
    "loud_exit_rms": 100.0,         # floor must drop below this (for 5s) to leave loud mode
    "loud_babble_enter": 0.25,      # fraction of idle frames the VAD calls speech (crowd chatter), secondary hint
    "loud_babble_exit": 0.12,
    "loud_burst_ratio": 1.30,       # denoised-noise p90/p50: a fan is ~1.1, crowd chatter 1.4-2.5
    "speech_level_ref": 0.0,        # learned: typical loudness (band RMS p90) of THIS mic's speech; 0 = not learned yet
    "loud_onset_boost_db": 4.0,     # extra dB over the floor needed to start recording in a loud room
    "loud_onset_required": 5,       # voiced frames (of onset_window) needed to start in a loud room
    "loud_continue_snr_db": 3.5,
    "loud_speaker_ratio": 0.45,     # continue threshold as a fraction of the locked speaker level
    "loud_end_silence_sec": 0.70,
    "loud_max_record_sec": 7.0,
    "floor_percentile": 50,         # percentile of the last ~4s of idle frames used as the room floor
    "onset_burst_margin": 1.25,     # onset must also clear this multiple of the noise's own 90th percentile
    "floor_warmup_sec": 0.6,        # after start-up without calibration: learn the floor first, no onsets

    # Noise suppression and DSP tuning
    "denoise_enabled": True,
    "bg_suppress_db": 12.0,         # maximum noise attenuation of the spectral denoiser (dB)
    "low_cutoff_hz": 70.0,
    "high_cutoff_hz": 4500.0,
    "treble_boost": 1.35,           # 2-4 kHz consonant presence shelf applied to the whole utterance
    "agc_max_scale": 1.80,

    # Input layer (device selection and multi-channel mics). Run `python listen.py --list-audio-devices`.
    "input_device_name": "",        # case-insensitive substring of the device name; "" = automatic
    "input_host_api": "",           # e.g. "WASAPI", "MME", "DirectSound"; "" = any
    "input_channels": 1,
    "channel_mode": "mono",         # "mono" (average) | "pick" | "mean" | "best_snr"
    "channel_index": 0,

    # Raise-hand-to-talk (loud rooms only; see listen.py)
    "hand_gate_enabled": True,
    "hand_release_sec": 0.45,
    "hand_gate_max_sec": 12.0,

    # Legacy compatibility keys (preserved in the file for older tools; not read by v3)
    "min_speech_rms": 180.0,
    "speech_multiplier": 1.45,
    "continue_ratio": 0.70,
    "start_frames": 3,
    "pre_emphasis": 0.0,
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


# ---------------------------------------------------------------------------
# INPUT LAYER: device selection, channel mixing, resampling
# ---------------------------------------------------------------------------

def list_input_devices() -> List[Dict[str, Any]]:
    """Returns every capture-capable audio device with its host API (MME, WASAPI, ALSA, ...)."""
    import sounddevice as sd
    hostapis = sd.query_hostapis()
    devices = []
    for idx, dev in enumerate(sd.query_devices()):
        if dev.get("max_input_channels", 0) > 0:
            devices.append({
                "index": idx,
                "name": " ".join(str(dev.get("name", "")).split()),
                "host_api": hostapis[dev["hostapi"]]["name"],
                "channels": int(dev["max_input_channels"]),
                "default_samplerate": float(dev.get("default_samplerate", 0.0)),
            })
    return devices


def format_input_devices() -> str:
    """Human-readable device table for `python listen.py --list-audio-devices`."""
    try:
        devices = list_input_devices()
    except Exception as e:
        return f"Could not query audio devices: {e}"
    lines = ["Input devices (set input_device_name / input_host_api / input_channels in mic_config.json):"]
    for d in devices:
        lines.append(f"  [{d['index']:>3}] {d['name']}  |  {d['host_api']}  |  {d['channels']} ch  |  {d['default_samplerate']:.0f} Hz")
    if len(lines) == 1:
        lines.append("  (no capture devices found)")
    return "\n".join(lines)


def find_input_device(cfg: Dict[str, Any]) -> Optional[int]:
    """Resolves input_device_name / input_host_api from the config to a sounddevice index. None = no override."""
    name = str(cfg.get("input_device_name") or "").strip().lower()
    api = str(cfg.get("input_host_api") or "").strip().lower()
    if not name and not api:
        return None
    try:
        for d in list_input_devices():
            if name and name not in d["name"].lower():
                continue
            if api and api not in d["host_api"].lower():
                continue
            return d["index"]
    except Exception:
        pass
    return None


class ChannelMixer:
    """
    Reduces a (frames, channels) capture block to mono int16.

    Modes:
      "mono" / "mean"  average of all channels (identity for a mono device)
      "pick"           use channel `index` only (e.g. a mic array whose channel 0 is already beamformed)
      "best_snr"       adaptively follow the channel with the best speech-to-floor ratio (hysteresis ~1 s)

    Beamformer hook for the future 3D / far-field array: assign a callable to `mixer.beamformer` taking the
    (frames, channels) block and returning a mono array; it takes precedence over `mode`. Nothing else in the
    pipeline needs to change when it is added.
    """

    def __init__(self, mode: str = "mono", index: int = 0, channels: int = 1):
        self.mode = str(mode or "mono").lower()
        self.index = max(0, int(index))
        self.channels = max(1, int(channels))
        self.beamformer: Optional[Callable[[np.ndarray], np.ndarray]] = None
        self._floor = np.full(self.channels, 1e9, dtype=np.float64)
        self._level = np.zeros(self.channels, dtype=np.float64)
        self._current = min(self.index, self.channels - 1)
        self._challenger = -1
        self._challenger_blocks = 0

    def mix(self, block: np.ndarray) -> np.ndarray:
        x = np.asarray(block)
        if x.ndim == 1:
            return x.astype(np.int16, copy=False)
        if self.beamformer is not None:
            return np.asarray(self.beamformer(x)).reshape(-1).astype(np.int16, copy=False)
        ch = x.shape[1]
        if ch == 1:
            return x[:, 0].astype(np.int16, copy=False)
        if self.mode == "pick":
            return x[:, min(self.index, ch - 1)].astype(np.int16, copy=False)
        if self.mode == "best_snr":
            return x[:, self._pick_best(x)].astype(np.int16, copy=False)
        return np.mean(x.astype(np.float32), axis=1).astype(np.int16)

    def _pick_best(self, x: np.ndarray) -> int:
        ch = x.shape[1]
        if ch != self.channels:
            self.channels = ch
            self._floor = np.full(ch, 1e9)
            self._level = np.zeros(ch)
            self._current = min(self._current, ch - 1)
        xf = x.astype(np.float32)
        xf = xf - np.mean(xf, axis=0, keepdims=True)
        rms = np.sqrt(np.mean(xf ** 2, axis=0)) + 1e-6
        # Floor follows quiet moments quickly downward and rises very slowly; level is a short smooth envelope
        self._floor = np.where(rms < self._floor, rms, self._floor * 1.002 + 1e-9)
        self._level = 0.8 * self._level + 0.2 * rms
        snr = self._level / np.maximum(self._floor, 1e-6)
        best = int(np.argmax(snr))
        if best != self._current and snr[best] > snr[self._current] * 1.25:
            if best == self._challenger:
                self._challenger_blocks += 1
            else:
                self._challenger, self._challenger_blocks = best, 1
            if self._challenger_blocks >= 33:  # ~1s of 30ms blocks
                self._current = best
                self._challenger, self._challenger_blocks = -1, 0
        else:
            self._challenger, self._challenger_blocks = -1, 0
        return self._current


class Resampler:
    """
    Streaming resampler to a fixed target rate with an anti-alias FIR low-pass (windowed sinc, numpy only).
    Replaces plain linear interpolation, which folds fan hiss and sibilance above 8 kHz back into the speech band.
    Feed arbitrary-length int16 blocks; output is int16 at `dst_rate`. Output length per call can vary by one
    sample when the ratio is not an integer, so callers should re-frame the output.
    """

    def __init__(self, src_rate: int, dst_rate: int = 16000, taps: int = 63):
        self.src_rate = int(src_rate)
        self.dst_rate = int(dst_rate)
        self.passthrough = (self.src_rate == self.dst_rate)
        self.step = self.src_rate / float(self.dst_rate)
        self.taps = taps if taps % 2 == 1 else taps + 1
        cutoff = 0.45 * self.dst_rate / float(self.src_rate)  # fraction of src rate, just under target Nyquist
        n = np.arange(self.taps) - (self.taps - 1) / 2.0
        h = np.sinc(2.0 * cutoff * n) * np.blackman(self.taps)
        self.fir = (h / np.sum(h)).astype(np.float64)
        self._hist = np.zeros(self.taps - 1, dtype=np.float64)
        self._phase = 0.0  # fractional read position into the filtered stream, carried across blocks

    def process(self, block: np.ndarray) -> np.ndarray:
        x = np.asarray(block).reshape(-1)
        if self.passthrough:
            return x.astype(np.int16, copy=False)
        buf = np.concatenate([self._hist, x.astype(np.float64)])
        filtered = np.convolve(buf, self.fir, mode="valid")  # same length as x
        self._hist = buf[-(self.taps - 1):]
        n = len(filtered)
        if n < 2:
            return np.zeros(0, dtype=np.int16)
        # Read positions start at the carried phase; the last sample is kept for interpolating into the next block
        count = int(np.floor((n - 1 - self._phase) / self.step)) + 1
        if count <= 0:
            self._phase -= n
            return np.zeros(0, dtype=np.int16)
        pos = self._phase + np.arange(count) * self.step
        i0 = np.floor(pos).astype(np.int64)
        frac = pos - i0
        i1 = np.minimum(i0 + 1, n - 1)
        out = filtered[i0] * (1.0 - frac) + filtered[i1] * frac
        self._phase = pos[-1] + self.step - n
        return np.clip(out, -32768, 32767).astype(np.int16)


# ---------------------------------------------------------------------------
# DSP
# ---------------------------------------------------------------------------

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


class SpectralDenoiser:
    """
    Streaming Wiener-style spectral noise suppressor for 16 kHz speech.

    Works on 480-sample (30 ms) frames internally as two 240-sample hops: a 480-sample sqrt-Hann window zero-padded
    to a 512-point FFT with 50% overlap-add (perfect reconstruction at unity gain). The noise power spectrum is
    tracked by recursive averaging on frames the caller marks as noise; the speech spectrum is estimated with a
    decision-directed a-priori SNR, and the gain is floored at -max_atten_db so residual "musical noise" stays
    inaudible. Output is delayed by one hop (15 ms).

    This removes stationary noise (fans, AC, hiss, constant crowd roar). It cannot separate overlapping speech,
    so loud-room behaviour additionally relies on level-based decisions in the Endpointer and the raise-hand gate.
    """

    HOP = 240
    WIN = 480
    NFFT = 512

    def __init__(self, max_atten_db: float = 12.0):
        n = np.arange(self.WIN)
        self.window = np.sqrt(0.5 * (1.0 - np.cos(2.0 * np.pi * n / self.WIN))).astype(np.float32)
        self.set_max_attenuation(max_atten_db)
        self.reset()

    def set_max_attenuation(self, db: float):
        self.gain_floor = float(10.0 ** (-abs(float(db)) / 20.0))

    def reset(self):
        bins = self.NFFT // 2 + 1
        self.prev_hop = np.zeros(self.HOP, dtype=np.float32)
        self.ola = np.zeros(self.HOP, dtype=np.float32)
        self.noise_psd: Optional[np.ndarray] = None
        self.prev_gain = np.ones(bins, dtype=np.float32)
        self.prev_clean_psd: Optional[np.ndarray] = None
        self.freeze_noise = False
        self._blocked_hops = 0
        self._blocked_acc: Optional[np.ndarray] = None

    def set_noise_psd(self, psd: Optional[np.ndarray]):
        self.noise_psd = None if psd is None else np.array(psd, dtype=np.float64, copy=True)

    def process(self, frame: np.ndarray, is_noise: bool = True) -> np.ndarray:
        """Denoises a frame whose length is a multiple of 240 samples. `is_noise` allows noise-PSD adaptation."""
        x = np.asarray(frame, dtype=np.float32)
        out = np.empty_like(x)
        for h in range(len(x) // self.HOP):
            new = x[h * self.HOP:(h + 1) * self.HOP]
            buf = np.concatenate([self.prev_hop, new])
            self.prev_hop = new
            spec = np.fft.rfft(buf * self.window, n=self.NFFT)
            psd = (spec.real ** 2 + spec.imag ** 2).astype(np.float64)

            if self.noise_psd is None:
                self.noise_psd = psd + 1e-3
            elif is_noise and not self.freeze_noise:
                # Only adapt on frames that are not obviously speech. The caller only passes is_noise=True for
                # frames it has decided are not speech, so if they keep looking "too loud" for ~1.5s the noise
                # really did jump: re-initialise to their average at once (a slow 3% nudge would never catch up).
                looks_like_speech = psd.mean() > 4.0 * self.noise_psd.mean()
                if looks_like_speech:
                    self._blocked_hops += 1
                    self._blocked_acc = psd.copy() if self._blocked_acc is None else self._blocked_acc + psd
                    if self._blocked_hops > 100:
                        self.noise_psd = self._blocked_acc / self._blocked_hops + 1e-3
                        self._blocked_hops = 0
                        self._blocked_acc = None
                else:
                    self._blocked_hops = 0
                    self._blocked_acc = None
                    a = np.where(psd < self.noise_psd, 0.90, 0.97)  # fall quickly, rise slowly
                    self.noise_psd = a * self.noise_psd + (1.0 - a) * psd

            noise = np.maximum(self.noise_psd, 1e-3)
            post = psd / noise
            prior_dd = (self.prev_clean_psd / noise) if self.prev_clean_psd is not None else 0.0
            prior = 0.96 * prior_dd + 0.04 * np.maximum(post - 1.0, 0.0)
            gain = prior / (1.0 + prior)
            gain = np.clip(gain, self.gain_floor, 1.0).astype(np.float32)
            gain = 0.6 * gain + 0.4 * self.prev_gain  # temporal smoothing against flutter
            self.prev_gain = gain
            self.prev_clean_psd = (gain.astype(np.float64) ** 2) * psd

            y = np.fft.irfft(spec * gain, n=self.NFFT)[:self.WIN].astype(np.float32) * self.window
            out[h * self.HOP:(h + 1) * self.HOP] = self.ola + y[:self.HOP]
            self.ola = y[self.HOP:]
        return out

    def process_utterance(self, audio: np.ndarray) -> np.ndarray:
        """Offline helper: denoises a whole utterance with the noise PSD already set (no adaptation) and
        compensates the one-hop delay so the output is time-aligned with the input."""
        self.freeze_noise = True
        samples = np.asarray(audio, dtype=np.float32)
        n = len(samples)
        pad = (-n) % self.HOP
        padded = np.concatenate([samples, np.zeros(pad + self.HOP, dtype=np.float32)])
        out = self.process(padded, is_noise=False)
        return out[self.HOP:self.HOP + n]


def clean_audio_for_transcription(audio: np.ndarray, floor_rms: float,
                                 sample_rate: int = 16000,
                                 agc_max_scale: float = 1.8,
                                 noise_psd: Optional[np.ndarray] = None,
                                 max_atten_db: float = 12.0,
                                 treble_boost: float = 1.35) -> np.ndarray:
    """Whole-utterance audio cleaning for Whisper STT.
    0. Optional spectral denoise using the noise profile captured just before speech onset (noise_psd).
    1. FFT bandpass 70Hz-5500Hz with a configurable (treble_boost) consonant presence shelf at 2.0kHz-4.0kHz.
    2. Time-domain downward expander applied ONLY when floor_rms > 350.0 (loud exhibition hall).
       In quiet or moderate rooms, skips the expander so Whisper receives pristine phonemes.
    3. Single peak normalization capped at agc_max_scale.
    """
    if audio is None or audio.size == 0:
        return audio
    try:
        samples = audio.astype(np.float32)

        # 0. Whole-utterance spectral denoise (stationary noise only; speech is untouched where it dominates)
        if noise_psd is not None and sample_rate == 16000:
            try:
                den = SpectralDenoiser(max_atten_db=max_atten_db)
                den.set_noise_psd(noise_psd)
                samples = den.process_utterance(samples)
            except Exception:
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
        gain[clarity_mask] *= float(treble_boost)

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


# ---------------------------------------------------------------------------
# ENDPOINTER
# ---------------------------------------------------------------------------

class Endpointer:
    """Formal Voice Activity Endpointer State Machine (v3).
    States:
      HOLDOFF   - Discards initial touch clicks, PipeWire buffer startup pops, or post-TTS speaker echo.
      WAITING   - Tracks the room floor (median of the last ~4s of idle frames, cannot deadlock) and loud-room state; triggers ONSET
                  via a sliding window (e.g. 4 of 8 frames; stricter in loud rooms).
      RECORDING - Locks the speaker level after ~1s, ends on a voiced-density hangover (a stray noise frame can no
                  longer reset the silence timer), always trims the tail by index.
      DONE      - Utterance completed; provides audio buffer and validation status.

    Loud-room mode (`is_loud`) switches on automatically when the in-band floor stays above `loud_enter_rms` or
    chatter keeps the VAD firing while idle, and off again after the room has been calm for ~5s.
    """

    STATE_HOLDOFF = "HOLDOFF"
    STATE_WAITING = "WAITING"
    STATE_RECORDING = "RECORDING"
    STATE_DONE = "DONE"

    FLOOR_WINDOW_FRAMES = 133  # ~4.0 seconds

    def __init__(self, cfg: Optional[Dict[str, Any]] = None, seed_floor: float = 50.0):
        self.cfg = dict(DEFAULT_CONFIG)
        if cfg:
            self.cfg.update(cfg)

        self.sample_rate = 16000
        self.frame_samples = 480  # 30ms
        self.frame_sec = 0.03

        # Persistent floor history across turns (feature domain = denoised band energy; raw = band energy only)
        self.floor_win = deque(maxlen=self.FLOOR_WINDOW_FRAMES)
        self.floor_raw_win = deque(maxlen=self.FLOOR_WINDOW_FRAMES)
        self.vad_long = deque(maxlen=self.FLOOR_WINDOW_FRAMES)
        initial_seed = max(10.0, float(seed_floor))
        self._seed_windows(initial_seed, initial_seed)

        # WebRTC VAD instance
        vad_mode = int(self.cfg.get("vad_mode", 2))
        self.vad = webrtcvad.Vad(vad_mode) if webrtcvad is not None else None

        # Streaming noise suppressor
        self.denoiser = SpectralDenoiser(max_atten_db=float(self.cfg.get("bg_suppress_db", 12.0)))
        self._noise_gate = True
        self.utterance_noise_psd: Optional[np.ndarray] = None

        # Floor warm-up: until the live floor has been learned, seeds are replaced by observed frames
        self._warmup_frames_left = int(float(self.cfg.get("floor_warmup_sec", 0.6)) / self.frame_sec)
        self._warmup_started = False

        # Learned speech loudness of this microphone (raw band RMS, p90 of voiced frames, smoothed over turns)
        self.speech_ref = max(0.0, float(self.cfg.get("speech_level_ref", 0.0) or 0.0))

        # Loud-room state
        self.is_loud = False
        self._loud_enter_frames = 0
        self._loud_exit_frames = 0
        self.babble_ratio = 0.0
        self.recording_loud = False

        # Per-turn state
        self.state = self.STATE_WAITING
        self.turn_started_at = time.monotonic()
        self.holdoff_until = 0.0

        preroll_len = max(1, int(float(self.cfg.get("preroll_sec", 0.5)) / self.frame_sec))
        manual_len = max(1, int(float(self.cfg.get("manual_buffer_sec", 3.45)) / self.frame_sec))
        self.preroll = deque(maxlen=preroll_len)
        self.manual_buf = deque(maxlen=manual_len)

        onset_win_len = max(2, int(self.cfg.get("onset_window", 8)))
        self.onset_hist = deque(maxlen=onset_win_len)
        self.vad_hist5 = deque(maxlen=5)

        self.frames = []
        self.voiced_flags = []
        self.voiced_rms = []
        self.voiced_rms_raw = []
        self.rec_hist = deque(maxlen=67)      # last ~2s of every recorded frame's energy (noise-abort test)
        self.rec_hist_raw = deque(maxlen=67)
        self.rec_floor_start = 0.0
        self.speaker_vals = deque(maxlen=120)
        self.speaker_level = 0.0
        self.speaker_locked = False
        self.last_voiced_idx = 0
        self.last_dense_idx = 0
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
        self.live_floor_raw = initial_seed
        self.live_onset_thr = float(self.cfg.get("min_onset_rms", 40.0))
        self.live_cont_thr = float(self.cfg.get("min_continue_rms", 20.0))
        self.live_silence_sec = 0.0

    # ----- helpers -----

    def _seed_windows(self, floor: float, raw_floor: float, copies: int = 10):
        self.floor_win.clear()
        self.floor_raw_win.clear()
        for _ in range(copies):
            self.floor_win.append(float(floor))
            self.floor_raw_win.append(float(raw_floor))

    def reseed(self, floor_rms: float, raw_floor_rms: Optional[float] = None):
        """Re-seeds the room-floor estimate (e.g. after an explicit calibration). Few seed frames are used so the
        live percentile takes over within a second or two. Telemetry is updated immediately."""
        raw = float(raw_floor_rms) if raw_floor_rms is not None else float(floor_rms)
        self._seed_windows(max(1.0, float(floor_rms)), max(1.0, raw))
        self.live_floor = max(1.0, float(floor_rms))
        self.live_floor_raw = max(1.0, raw)
        self._warmup_frames_left = 0  # a deliberate measurement replaces the warm-up

    def calibrate_from_audio(self, audio: np.ndarray) -> bool:
        """Calibrates from ~1-2s of room audio (16 kHz mono int16, nobody speaking) by running it through the exact
        same bandpass -> denoise -> VAD path the live frames use. Learns the room floor, the noise spectrum (so the
        denoiser starts warm) and the chatter ratio, and decides loud mode immediately instead of after 2s.
        Returns False if there was too little audio."""
        samples = np.asarray(audio).reshape(-1)
        n_frames = len(samples) // self.frame_samples
        if n_frames < 20:
            return False
        self.denoiser.reset()
        self.floor_win.clear()
        self.floor_raw_win.clear()
        self.vad_long.clear()
        self.denoiser.set_max_attenuation(float(self.cfg.get("bg_suppress_db", 12.0)))
        skip = 6  # let the denoiser's first noise estimate settle before trusting its output
        for i in range(n_frames):
            raw = samples[i * self.frame_samples:(i + 1) * self.frame_samples].astype(np.int16)
            filt = bandpass_frame(raw, sample_rate=self.sample_rate,
                                  low_hz=float(self.cfg.get("low_cutoff_hz", 85.0)),
                                  high_hz=float(self.cfg.get("high_cutoff_hz", 4500.0)))
            if bool(self.cfg.get("denoise_enabled", True)):
                feat = np.clip(self.denoiser.process(filt.astype(np.float32), is_noise=True), -32768.0, 32767.0).astype(np.int16)
            else:
                feat = filt
            if i < skip:
                continue
            self.floor_win.append(audio_rms(feat))
            self.floor_raw_win.append(audio_rms(filt))
            vad_speech = False
            if self.vad is not None:
                try:
                    vad_speech = self.vad.is_speech(feat.tobytes(), self.sample_rate)
                except Exception:
                    vad_speech = False
            self.vad_long.append(vad_speech)
        floor_pct = float(np.clip(float(self.cfg.get("floor_percentile", 50)), 5.0, 90.0))
        self.live_floor = max(1.0, float(np.percentile(self.floor_win, floor_pct)))
        self.live_floor_raw = max(1.0, float(np.percentile(self.floor_raw_win, 50)))
        self._warmup_frames_left = 0
        self._loud_enter_frames = 0
        self._loud_exit_frames = 0
        was_loud = self.is_loud
        wants_loud, _ = self._loud_verdict(self.live_floor, self.live_floor_raw)
        self.babble_ratio = sum(self.vad_long) / max(1, len(self.vad_long))
        self.is_loud = bool(wants_loud)
        if self.is_loud or was_loud:
            print(f"[Endpointer] Calibration: floor {self.live_floor:.0f} RMS (raw {self.live_floor_raw:.0f}), "
                  f"burstiness {self._noise_burstiness():.2f}, chatter {self.babble_ratio:.0%} -> "
                  f"{'LOUD ROOM mode' if self.is_loud else 'normal mode'}.")
        return True

    @property
    def noise_dbfs(self) -> float:
        """Room noise level in dB relative to int16 full scale (typical: quiet ~ -64, loud hall ~ -43)."""
        return 20.0 * float(np.log10(max(self.live_floor_raw, 1.0) / 32768.0))

    def _noise_burstiness(self) -> float:
        """p90/p50 of the denoised idle-frame energy. The denoiser removes the steady part of any noise, so a
        stationary fan leaves ~1.1 while crowd chatter leaves distinct bursts (1.4-2.5)."""
        if len(self.floor_win) < 20:
            return 1.0
        p50 = float(np.percentile(self.floor_win, 50))
        return float(np.percentile(self.floor_win, 90)) / max(p50, 1.0)

    def _loud_verdict(self, floor_feat: float, floor_raw: float) -> Tuple[bool, bool]:
        """Returns (wants_loud, wants_calm) for the current room. Loud means 'the crowd or very high noise will
        defeat level-based endpointing': either the noise floor is high even after denoising, or a high raw
        level that is bursty (crowd chatter), or sustained chatter flagged by the VAD while idle."""
        level_scale = max(0.1, (self.speech_ref if self.speech_ref > 0.0 else 550.0) / 550.0)
        enter_rms = float(self.cfg.get("loud_enter_rms", 160.0)) * level_scale
        exit_rms = float(self.cfg.get("loud_exit_rms", 100.0)) * level_scale
        babble_in = float(self.cfg.get("loud_babble_enter", 0.25))
        babble_out = float(self.cfg.get("loud_babble_exit", 0.12))
        burst_in = float(self.cfg.get("loud_burst_ratio", 1.30))
        burst = self._noise_burstiness()
        self.babble_ratio = (sum(self.vad_long) / len(self.vad_long)) if len(self.vad_long) >= 33 else 0.0
        wants_loud = (
            floor_feat >= enter_rms
            or (floor_raw >= enter_rms and burst >= burst_in)
            or (self.babble_ratio > babble_in and floor_raw >= 0.5 * enter_rms)
        )
        wants_calm = (
            floor_feat <= exit_rms
            and (floor_raw <= exit_rms or burst < 0.9 * burst_in)
            and self.babble_ratio < babble_out
        )
        return wants_loud, wants_calm

    def _update_loud_state(self, floor_feat: float, floor_raw: float):
        """Hysteresis for loud-room mode: 2s of 'loud' evidence to enter, 5s of calm to leave."""
        wants_loud, wants_calm = self._loud_verdict(floor_feat, floor_raw)

        if not self.is_loud:
            self._loud_enter_frames = self._loud_enter_frames + 1 if wants_loud else 0
            if self._loud_enter_frames >= int(2.0 / self.frame_sec):  # 2s
                self.is_loud = True
                self._loud_enter_frames = 0
                print(f"[Endpointer] LOUD ROOM detected (floor {floor_feat:.0f} RMS after denoise, "
                      f"burstiness {self._noise_burstiness():.2f}, chatter {self.babble_ratio:.0%}). "
                      f"Stricter onset + faster endpointing active.")
        else:
            self._loud_exit_frames = self._loud_exit_frames + 1 if wants_calm else 0
            if self._loud_exit_frames >= int(5.0 / self.frame_sec):  # 5s
                self.is_loud = False
                self._loud_exit_frames = 0
                print(f"[Endpointer] Room is calm again (floor {floor_feat:.0f} RMS). Normal endpointing restored.")

    def begin_turn(self, holdoff_sec: Optional[float] = None):
        """Prepares endpointer for a new turn.
        Any holdoff period immediately discards arriving frames to block startup pops or speaker echo.
        """
        now = time.monotonic()
        self.turn_started_at = now
        duration = float(holdoff_sec) if holdoff_sec is not None else float(self.cfg.get("startup_holdoff_sec", 0.45))
        self.holdoff_until = now + duration
        self.state = self.STATE_HOLDOFF if duration > 0.0 else self.STATE_WAITING

        preroll_len = max(1, int(float(self.cfg.get("preroll_sec", 0.5)) / self.frame_sec))
        if self.preroll.maxlen != preroll_len:
            self.preroll = deque(maxlen=preroll_len)
        self.preroll.clear()
        self.manual_buf.clear()
        self.onset_hist.clear()
        self.vad_hist5.clear()
        self.frames = []
        self.voiced_flags = []
        self.voiced_rms = []
        self.voiced_rms_raw = []
        self.rec_hist.clear()
        self.rec_hist_raw.clear()
        self.speaker_vals.clear()
        self.speaker_level = 0.0
        self.speaker_locked = False
        self.last_voiced_idx = 0
        self.last_dense_idx = 0
        self.voiced_count = 0
        self.recording_started_at = 0.0
        self.recording_loud = False
        self.is_manual_send = False
        self.done_reason = ""
        self.result_audio = None
        self.result_info = {}
        self.live_silence_sec = 0.0
        self._noise_gate = True

    # ----- main per-frame entry -----

    def snapshot_noise_psd(self) -> Optional[np.ndarray]:
        """Copy of the denoiser's current noise spectrum (taken just before speech, for the whole-utterance denoise)."""
        return None if self.denoiser.noise_psd is None else np.array(self.denoiser.noise_psd, copy=True)

    def feed(self, chunk: np.ndarray, monitor_only: bool = False, freeze_noise: bool = False) -> Optional[str]:
        """Feeds one 30ms (480-sample) int16 chunk into the endpointer.

        monitor_only=True keeps the room floor, the denoiser and the loud-room state up to date but never starts a
        recording (used while something else decides when to record, e.g. the raise-hand gate). With
        freeze_noise=True the frame is treated as speech: floor and noise profile are left untouched.
        Returns:
          "ONSET" - Speech onset detected; transitioning from WAITING to RECORDING.
          "ABORT" - The recording was steady background noise and was dropped; back to WAITING.
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

        if self.state not in (self.STATE_WAITING, self.STATE_RECORDING):
            return None

        self.denoiser.freeze_noise = bool(freeze_noise)
        raw_chunk = chunk[:self.frame_samples].astype(np.int16, copy=False)
        self.manual_buf.append(raw_chunk)

        # Feature extraction: bandpass, then (optionally) spectral denoise. The denoised band energy is what the
        # SNR decisions run on, so stationary noise no longer forces the speaker to shout.
        filt = bandpass_frame(
            raw_chunk,
            sample_rate=self.sample_rate,
            low_hz=float(self.cfg.get("low_cutoff_hz", 85.0)),
            high_hz=float(self.cfg.get("high_cutoff_hz", 4500.0)),
        )
        rms_raw = audio_rms(filt)
        if bool(self.cfg.get("denoise_enabled", True)):
            self.denoiser.set_max_attenuation(float(self.cfg.get("bg_suppress_db", 12.0)))
            clean = self.denoiser.process(filt.astype(np.float32), is_noise=self._noise_gate)
            feat = np.clip(clean, -32768.0, 32767.0).astype(np.int16)
        else:
            feat = filt
        rms = audio_rms(feat)
        self.live_rms = rms

        vad_speech = False
        if self.vad is not None:
            try:
                vad_speech = self.vad.is_speech(feat.tobytes(), self.sample_rate)
            except Exception:
                vad_speech = False
        self.live_vad = vad_speech

        # 2. State: WAITING (Floor estimation and sliding-window onset detection)
        if self.state == self.STATE_WAITING:
            if monitor_only and freeze_noise:
                return None  # the speaker is talking: do not let their voice into the floor or noise estimates
            self.preroll.append(raw_chunk)

            # Floor = median of the last ~4s of idle frames. Short vocal bursts cannot move a median, so no
            # admission gate is needed (the old gate could deadlock the floor in a loud hall).
            if self._warmup_frames_left > 0:
                if not self._warmup_started:
                    # First live frames: discard the (possibly stale) seed so the floor reflects this room
                    self._warmup_started = True
                    self.floor_win.clear()
                    self.floor_raw_win.clear()
                self._warmup_frames_left -= 1
            self.floor_win.append(rms)
            self.floor_raw_win.append(rms_raw)
            self.vad_long.append(vad_speech)
            floor_pct = float(np.clip(float(self.cfg.get("floor_percentile", 50)), 5.0, 90.0))
            floor = float(np.percentile(self.floor_win, floor_pct))
            floor_raw = float(np.percentile(self.floor_raw_win, 50))
            self.live_floor = floor
            self.live_floor_raw = floor_raw
            self._update_loud_state(floor, floor_raw)
            loud = self.is_loud
            if monitor_only:
                self._noise_gate = True
                return None

            onset_snr_db = float(self.cfg.get("onset_snr_db", 6.0)) + (float(self.cfg.get("loud_onset_boost_db", 4.0)) if loud else 0.0)
            min_onset_rms = float(self.cfg.get("min_onset_rms", 40.0))
            max_onset_rms = float(self.cfg.get("max_onset_rms", 1300.0))
            # Onset must beat the SNR over the median AND clear the noise's own bursts (90th percentile of recent idle
            # frames). Steady noise has p90 ~ 1.1 x median so this changes nothing there; chatter peaks at 2-2.5 x
            # median, which a plain "6 dB over the median" gate would trigger on.
            noise_p90 = float(np.percentile(self.floor_win, 90))
            burst_margin = float(self.cfg.get("onset_burst_margin", 1.25))
            onset_thr = float(np.clip(max(floor * (10.0 ** (onset_snr_db / 20.0)), burst_margin * noise_p90),
                                      min_onset_rms, max_onset_rms))
            self.live_onset_thr = onset_thr

            cont_snr_db = float(self.cfg.get("loud_continue_snr_db", 3.5)) if loud else float(self.cfg.get("continue_snr_db", 4.5))
            min_continue_rms = float(self.cfg.get("min_continue_rms", 20.0))
            self.live_cont_thr = max(floor * (10.0 ** (cont_snr_db / 20.0)), min_continue_rms)

            # Candidate frame: energy over the onset threshold AND VAD. Quiet rooms also accept a strong
            # energy-only frame (VAD can miss soft consonants); loud rooms never do (crowd noise is energetic).
            energy_ok = rms >= onset_thr
            cand = energy_ok and (vad_speech or (not loud and rms >= 1.8 * onset_thr))
            self.onset_hist.append(cand)
            self.vad_hist5.append(vad_speech)

            onset_req = int(self.cfg.get("loud_onset_required", 5)) if loud else int(self.cfg.get("onset_required", 4))
            onset_req = min(onset_req, self.onset_hist.maxlen)
            vad_ok = (not loud) or (self.vad is None) or (sum(self.vad_hist5) >= 3)
            self._noise_gate = not cand

            if self._warmup_frames_left > 0:
                return None  # still learning the room floor; never start recording on a stale estimate

            if sum(self.onset_hist) >= onset_req and vad_ok:
                # Transition to RECORDING!
                self.state = self.STATE_RECORDING
                self.recording_started_at = now
                self.recording_loud = loud
                self.frames = list(self.preroll)
                hist = list(self.onset_hist)
                if len(hist) >= len(self.frames):
                    self.voiced_flags = hist[-len(self.frames):]
                else:
                    self.voiced_flags = [False] * (len(self.frames) - len(hist)) + hist
                self.voiced_count = sum(hist)
                true_idx = [i for i, f in enumerate(self.voiced_flags) if f]
                self.last_voiced_idx = true_idx[-1] if true_idx else len(self.frames) - 1
                self.last_dense_idx = self.last_voiced_idx
                self.speaker_vals.clear()
                self.speaker_vals.append(rms)
                self.speaker_level = rms
                self.speaker_locked = False
                self.voiced_rms = [rms]
                self.voiced_rms_raw = [rms_raw]
                self.rec_hist.clear()
                self.rec_hist_raw.clear()
                self.rec_floor_start = floor
                # Snapshot the noise profile NOW, before the utterance can contaminate it, for the whole-utterance denoise
                self.utterance_noise_psd = None if self.denoiser.noise_psd is None else np.array(self.denoiser.noise_psd, copy=True)
                return "ONSET"

            return None

        # 3. State: RECORDING (voiced-density hangover endpointing with index trimming)
        if self.state == self.STATE_RECORDING:
            self.frames.append(raw_chunk)
            loud = self.recording_loud
            elapsed = now - self.recording_started_at

            floor = self.live_floor
            cont_snr_db = float(self.cfg.get("loud_continue_snr_db", 3.5)) if loud else float(self.cfg.get("continue_snr_db", 4.5))
            min_continue_rms = float(self.cfg.get("min_continue_rms", 20.0))
            snr_thr = max(floor * (10.0 ** (cont_snr_db / 20.0)), min_continue_rms)

            # Active speaker level: running median until it is locked (~1s in), then the 75th percentile of the
            # voiced frames seen so far. It is a property of the person talking, not of the surrounding noise.
            if self.speaker_locked:
                spk = self.speaker_level
            else:
                spk = float(np.median(self.speaker_vals)) if len(self.speaker_vals) >= 5 else rms
            speaker_ratio = float(self.cfg.get("loud_speaker_ratio", 0.45)) if loud else float(self.cfg.get("speaker_ratio", 0.32))
            cont_thr = max(snr_thr, speaker_ratio * spk)
            self.live_cont_thr = cont_thr

            bypass = 1.2 if loud else 1.6
            voiced = (rms >= cont_thr) and (vad_speech or (rms >= bypass * cont_thr))
            self._noise_gate = not voiced

            self.voiced_flags.append(voiced)
            idx = len(self.frames) - 1
            if voiced:
                self.last_voiced_idx = idx
                if sum(self.voiced_flags[-8:]) >= 3:
                    self.last_dense_idx = idx
                self.voiced_count += 1
                self.voiced_rms.append(rms)
                self.voiced_rms_raw.append(rms_raw)
                self.speaker_vals.append(rms)
                if self.speaker_locked and rms > self.speaker_level:
                    self.speaker_level += 0.02 * (rms - self.speaker_level)  # follows a speaker who gets louder
            else:
                # Unvoiced frames keep the floor estimate current while recording
                self.floor_win.append(rms)
                self.floor_raw_win.append(rms_raw)
                floor_pct = float(np.clip(float(self.cfg.get("floor_percentile", 50)), 5.0, 90.0))
                self.live_floor = float(np.percentile(self.floor_win, floor_pct))
                self.live_floor_raw = float(np.percentile(self.floor_raw_win, 50))
            self._update_loud_state(self.live_floor, self.live_floor_raw)
            if not self.speaker_locked and elapsed >= 1.0 and len(self.speaker_vals) >= 8:
                self.speaker_level = float(np.percentile(self.speaker_vals, 75))
                self.speaker_locked = True

            # Noise-abort: if for ~2s even the quietest fifth of the recording stays above the continue threshold,
            # the envelope is flat (speech always dips between words) and the level is far above the floor this
            # recording started against, then the room just got louder. Without this the old design stayed
            # "recording" until the hard cap, because the floor is frozen while recording and the noise looks voiced.
            self.rec_hist.append(rms)
            self.rec_hist_raw.append(rms_raw)
            if len(self.rec_hist) == self.rec_hist.maxlen and elapsed >= 2.0:
                hist = np.asarray(self.rec_hist, dtype=np.float64)
                h_p20 = float(np.percentile(hist, 20))
                h_p75 = float(np.percentile(hist, 75))
                if h_p20 >= cont_thr and h_p20 >= 0.5 * h_p75 and h_p20 >= 2.0 * max(self.rec_floor_start, 1.0):
                    return self._abort_recording_as_noise()

            silence_frames = len(self.frames) - 1 - self.last_voiced_idx
            self.live_silence_sec = silence_frames * self.frame_sec

            end_silence_sec = float(self.cfg.get("loud_end_silence_sec", 0.70)) if loud else float(self.cfg.get("end_silence_sec", 0.80))
            max_record_sec = float(self.cfg.get("loud_max_record_sec", 7.0)) if loud else float(self.cfg.get("max_record_sec", 9.0))
            window = max(6, int(round(end_silence_sec / self.frame_sec)))

            # Voiced-density hangover: the full end-of-speech silence is measured from the last DENSE voiced run
            # (>=3 voiced frames in the trailing 8), not from the last single voiced frame. A stray noise frame
            # therefore can no longer reset the silence timer, while a normal pause is never cut shorter.
            dense_silence_frames = len(self.frames) - 1 - self.last_dense_idx
            ended = dense_silence_frames >= window

            if ended:
                self._finalize(reason="silence", is_manual=False)
                return "END"
            if elapsed >= max_record_sec:
                self._finalize(reason="max_record", is_manual=False)
                return "END"

            return None

        return None

    def _abort_recording_as_noise(self) -> str:
        """Drops a recording that turned out to be steady background noise, folds its frames into the floor
        estimate (so the thresholds catch up with the new room level at once) and resumes waiting. Nothing is
        sent to Whisper. Returns the "ABORT" event."""
        for v in self.rec_hist_raw:
            self.floor_raw_win.append(float(v))
        self.live_floor_raw = float(np.percentile(self.floor_raw_win, 50))
        # The denoised-domain frames from this recording were measured against a noise profile that no longer
        # matches the room (that is why it looked like speech), so they are not reused. Restart the denoiser's
        # profile and the floor warm-up instead; the floor re-learns from fresh frames within ~0.6s.
        self.denoiser.set_noise_psd(None)
        self.floor_win.clear()
        self._warmup_started = False
        self._warmup_frames_left = max(self._warmup_frames_left, int(0.6 / self.frame_sec))
        print(f"[Endpointer] ABORT: recording was steady background noise (floor {self.rec_floor_start:.0f} -> "
              f"raw {self.live_floor_raw:.0f} RMS). Re-learning the room, still listening.")
        self.state = self.STATE_WAITING
        self.frames = []
        self.voiced_flags = []
        self.voiced_rms = []
        self.voiced_rms_raw = []
        self.speaker_vals.clear()
        self.speaker_locked = False
        self.speaker_level = 0.0
        self.last_voiced_idx = 0
        self.last_dense_idx = 0
        self.voiced_count = 0
        self.recording_started_at = 0.0
        self.recording_loud = False
        self.onset_hist.clear()
        self.vad_hist5.clear()
        self.preroll.clear()
        self.rec_hist.clear()
        self.rec_hist_raw.clear()
        self._noise_gate = True
        self.live_silence_sec = 0.0
        return "ABORT"

    def force_send(self):
        """Immediately dispatches recorded audio (0ms override on Send button or Enter)."""
        if self.state != self.STATE_RECORDING and len(self.manual_buf) > 0:
            self.frames = list(self.manual_buf)
            self.voiced_flags = [True] * len(self.frames)
            self.recording_started_at = time.monotonic() - (len(self.frames) * self.frame_sec)
            self.last_voiced_idx = len(self.frames) - 1
            self.voiced_count = len(self.frames)

        self._finalize(reason="manual_send", is_manual=True)

    def _last_dense_voiced_idx(self) -> int:
        """Index of the last frame inside a dense run of voiced frames (>=3 of the trailing 8). Ignores isolated
        trailing noise frames when trimming the tail. Manual sends have no dense tracking and use the last frame."""
        if self.is_manual_send:
            return self.last_voiced_idx
        return max(self.last_dense_idx, 0)

    def _finalize(self, reason: str, is_manual: bool):
        """Finalizes audio buffer and performs strict acceptance validation."""
        self.state = self.STATE_DONE
        self.done_reason = reason
        self.is_manual_send = is_manual

        if not self.frames:
            self.result_audio = None
            self.result_info = {"accepted": False, "reason": "empty_frames"}
            return

        # Tail trimming by index (keeps tail_pad_frames so final words are never clipped). Always applied for
        # automatic endings, including max_record, so trailing noise never reaches Whisper.
        tail_pad = int(self.cfg.get("tail_pad_frames", 7))
        if not is_manual:
            trim_idx = min(len(self.frames), self._last_dense_voiced_idx() + 1 + tail_pad)
            trimmed_frames = self.frames[:trim_idx]
        else:
            trimmed_frames = self.frames

        audio = np.concatenate(trimmed_frames)
        dur = audio.size / float(self.sample_rate)
        p90_rms = float(np.percentile(self.voiced_rms, 90)) if self.voiced_rms else audio_rms(audio)

        # Validation (Bypass validation on manual send). Relative to the room floor instead of fixed constants.
        accepted = True
        reject_reason = ""
        min_voiced_frames = int(self.cfg.get("min_voiced_frames", 6))
        min_onset_rms = float(self.cfg.get("min_onset_rms", 40.0))

        if not is_manual:
            floor_ratio = 2.0 if self.recording_loud else 1.5
            effective_min_speech_gate = max(min_onset_rms, self.live_floor * floor_ratio)
            if self.voiced_count < min_voiced_frames:
                accepted = False
                reject_reason = f"voiced_frames_too_low({self.voiced_count}<{min_voiced_frames})"
            elif p90_rms < effective_min_speech_gate:
                accepted = False
                reject_reason = f"p90_rms_too_low({p90_rms:.1f}<{effective_min_speech_gate:.1f})"

        if accepted and not is_manual and len(self.voiced_rms_raw) >= 12 and p90_rms >= 2.5 * max(self.live_floor, 1.0):
            p90_raw = float(np.percentile(self.voiced_rms_raw, 90))
            if p90_raw > 0.0:
                self.speech_ref = p90_raw if self.speech_ref <= 0.0 else 0.7 * self.speech_ref + 0.3 * p90_raw
                self.speech_ref = float(np.clip(self.speech_ref, 50.0, 20000.0))

        self.result_audio = audio if accepted else None
        self.result_info = {
            "accepted": accepted,
            "reason": reject_reason if not accepted else reason,
            "duration": round(dur, 2),
            "voiced_frames": self.voiced_count,
            "p90_rms": round(p90_rms, 1),
            "floor_rms": round(self.live_floor, 1),
            "floor_raw_rms": round(self.live_floor_raw, 1),
            "onset_thr": round(self.live_onset_thr, 1),
            "loud": bool(self.recording_loud),
            "speech_ref": round(self.speech_ref, 1),
            "is_manual": is_manual
        }

        # Structured diagnostic log
        status_tag = "ACCEPT" if accepted else f"REJECT({reject_reason})"
        print(
            f"[Endpointer] {status_tag} | reason={reason} dur={dur:.2f}s "
            f"voiced={self.voiced_count} p90={p90_rms:.1f} floor={self.live_floor:.1f}"
            f"{' LOUD' if self.recording_loud else ''}"
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
            "is_loud": self.is_loud,
            "noise_dbfs": self.noise_dbfs,
            "babble_ratio": self.babble_ratio,
        }
