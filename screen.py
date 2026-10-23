"""
Project Neurolis Mark II - Real-Time 7-Inch Animated Face UI Engine (screen.py)
-------------------------------------------------------------------------------
Apple-Grade 60 FPS Bionic Optical Face Engine for Raspberry Pi 7-Inch (1024x600, 128:75 ratio).

Mark II Overhaul Highlights:
  - Apple Vision Pro / macOS-Grade Boot Splash with sculpted Bionic Visor Crest,
    radial atmospheric backlight, specular light sweep, and S-curve glassmorphic progress bar.
  - Sleek Organic Bordered Optical Lens Architecture:
      * Soft multi-tier neon rim border enclosing a deep dark optical chamber (#050b16),
        luminous internal iris ring, breathing optic core, and 3-layer parallax Pixar catchlights.
      * Super-rounded organic contour (zero harsh boxy corners) + strict bottom-curve discipline:
        upward-curved lower eyelids ONLY appear when the robot is smiling/happy (e.g., MOVING,
        EXCITED, PROUD, and the open eye of WINK).
  - Apple-Grade Real-Time Animation Physics:
      * Real wall-clock delta-time (dt) 60 FPS physics engine.
      * Critically damped spring state transitions (squash-and-stretch + color cross-fade).
      * 3-layer optical parallax (outer rim -> inner iris -> floating corneal reflections).
      * Cubic asymmetric blink curve (fast close, brief hold, smooth ease-out open + natural double-blinks).
  - 22 Unmistakable First-Glance Expressive States (11 Core + 11 Conversational States):
      * Core States: IDLE, HAPPY, SAD, CONFUSED (frameless hypnotic spirals), THINKING (neural cog iris),
                     LISTENING (sonar radar iris), SPEAKING (vocal resonator iris), WATCHING (viewfinder reticle),
                     MOVING (wind-loving cruise + DRIVE note + 3D Cyber-Rover with subtle rear tire smoke),
                     ERROR (frameless crimson glitch X optics), VILLAIN (preserved rogue AI easter egg).
      * New Conversational States: EXCITED, LAUGHING (> <), LOVE (frameless bordered heart optics),
                                   WINK (curved-bottom open eye + wink arch), SURPRISED, SLEEPY,
                                   SHY, PROUD, CURIOUS (magnifying loupe optic), SKEPTICAL (deadpan side-eye).
  - Interactive Preview Shortcuts: Press 1-9, 0, Q-P, V, B, or Space/Tab to test any expression live.
"""

import contextlib
import math
import os
import platform
import random
import shutil
import sys
import threading
import time
try:
    import tkinter as tk
except ImportError:
    class _HeadlessTkFallback:
        ROUND = "round"
        ARC = "arc"
        BOTH = "both"
        Tk = None
        Canvas = None
    tk = _HeadlessTkFallback()
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Suppress verbose OpenCV warnings and V4L2 probe noise
os.environ["OPENCV_LOG_LEVEL"] = "ERROR"
os.environ["OPENCV_VIDEOIO_LOG_LEVEL"] = "0"

# Suppress PortAudio ALSA C-level error traces on Linux
if sys.platform.startswith("linux"):
    try:
        import ctypes
        asound = ctypes.cdll.LoadLibrary("libasound.so.2")
        ERROR_HANDLER_FUNC = ctypes.CFUNCTYPE(
            None, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p
        )

        def _alsa_error_handler(filename, line, function, err, fmt):
            pass

        _c_alsa_error_handler = ERROR_HANDLER_FUNC(_alsa_error_handler)
        asound.snd_lib_error_set_handler(_c_alsa_error_handler)
    except Exception:
        pass


@contextlib.contextmanager
def suppress_c_stderr():
    """Silences C-level stderr (fd 2) during PortAudio/ALSA operations on Linux."""
    if not sys.platform.startswith("linux"):
        yield
        return
    try:
        devnull_fd = os.open(os.devnull, os.O_WRONLY)
        stderr_fd = 2
        old_stderr = os.dup(stderr_fd)
        os.dup2(devnull_fd, stderr_fd)
        os.close(devnull_fd)
        try:
            yield
        finally:
            os.dup2(old_stderr, stderr_fd)
            os.close(old_stderr)
    except Exception:
        yield


# Enable Windows Per-Monitor v2 High-DPI Awareness so Windows never bitmap-stretches the UI
if sys.platform.startswith("win"):
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            import ctypes
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    try:
        import ctypes
        # Set 1ms multimedia timer precision on Windows so root.after() hits 60 FPS instead of 15.6ms ticks
        ctypes.windll.winmm.timeBeginPeriod(1)
    except Exception:
        pass

# Crisp system font family selection across Windows and Linux / Raspberry Pi
FONT_FAMILY = "Segoe UI" if sys.platform.startswith("win") else "DejaVu Sans"
MONO_FONT_FAMILY = "Consolas" if sys.platform.startswith("win") else "DejaVu Sans Mono"

# VILLAIN (Ultron-style) palette: cold steel faceplate + molten amber core. Calm, confident, smug; never "angry red".
VIL_GUN = "#1b2026"
VIL_GUN_DARK = "#0d1014"
VIL_STEEL = "#5b6772"
VIL_STEEL_DIM = "#38424c"
VIL_CHROME = "#c9d3dc"
VIL_AMBER = "#ff8a1f"
VIL_AMBER_SOFT = "#ffb15c"
VIL_AMBER_HOT = "#ffd27a"
VIL_EMBER = "#7a2e05"
VIL_EMBER_DARK = "#2a1103"
VIL_GLITCH_CHARS = "\u2588\u2593\u2592\u2591\u258c\u2590#%&@$"

# Optional Ultra-Smooth 2x Supersampled OpenCV LINE_AA Anti-Aliasing Engine
try:
    import cv2 as _cv2
    import numpy as _np
    from PIL import Image as _PILImage, ImageDraw as _PILImageDraw, ImageFont as _PILImageFont
    try:
        from PIL import ImageTk as _PILImageTk
    except Exception:
        _PILImageTk = None
    _HAS_CV2_AA = True
except Exception:
    _cv2 = None
    _np = None
    _PILImage = None
    _PILImageDraw = None
    _PILImageFont = None
    _PILImageTk = None
    _HAS_CV2_AA = False

if _HAS_CV2_AA:
    _THETA_64 = _np.linspace(0.0, 2.0 * math.pi, 64, endpoint=False)
    _UNIT_CIRCLE_64 = _np.column_stack([_np.cos(_THETA_64), _np.sin(_THETA_64)])

    # Precomputed 80-vertex Super-Ellipse (Lamé squircle, n=2.85) tables for 60 FPS on Raspberry Pi 5
    _EYE_THETA = _np.linspace(0.0, 2.0 * math.pi, 80, endpoint=False)
    _EYE_COS = _np.cos(_EYE_THETA)
    _EYE_SIN = _np.sin(_EYE_THETA)
    _EYE_EXP = 2.0 / 2.85
    _EYE_NX = _np.where(_EYE_COS >= 0.0, 1.0, -1.0) * (_np.abs(_EYE_COS) ** _EYE_EXP)
    _EYE_NY = _np.where(_EYE_SIN >= 0.0, 1.0, -1.0) * (_np.abs(_EYE_SIN) ** _EYE_EXP)
    _EYE_SMILE_LIFT = (_np.maximum(0.0, _EYE_SIN) ** 2.6) * 0.25

    # Precomputed quarter-circle tables for ultra-fast rounded rectangles
    _RR_ANG_TR = _np.linspace(-math.pi / 2.0, 0.0, 10)
    _RR_ANG_BR = _np.linspace(0.0, math.pi / 2.0, 10)
    _RR_ANG_BL = _np.linspace(math.pi / 2.0, math.pi, 10)
    _RR_ANG_TL = _np.linspace(math.pi, 1.5 * math.pi, 10)
    _RR_COS = [_np.cos(_RR_ANG_TR), _np.cos(_RR_ANG_BR), _np.cos(_RR_ANG_BL), _np.cos(_RR_ANG_TL)]
    _RR_SIN = [_np.sin(_RR_ANG_TR), _np.sin(_RR_ANG_BR), _np.sin(_RR_ANG_BL), _np.sin(_RR_ANG_TL)]


_RGB_CACHE: Dict[str, Optional[Tuple[int, int, int]]] = {}


def _hex_to_rgb(hex_str: str) -> Optional[Tuple[int, int, int]]:
    if not hex_str:
        return None
    cached = _RGB_CACHE.get(hex_str)
    if cached is not None:
        return cached
    h = hex_str.lstrip("#")
    if len(h) != 6:
        return (255, 255, 255)
    val = (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    _RGB_CACHE[hex_str] = val
    return val


_CR_T_CACHE: Dict[int, "_np.ndarray"] = {}


def _catmull_rom_np(coords: List[float], samples_per_seg: int = 8) -> "_np.ndarray":
    pts = _np.asarray(coords, dtype=_np.float64).reshape(-1, 2)
    n = len(pts)
    if n < 3 or n >= 48:
        return pts
    s = 4 if n >= 16 else samples_per_seg
    basis = _CR_T_CACHE.get(s)
    if basis is None:
        t = _np.linspace(0.0, 1.0, s, endpoint=False)[:, None]
        t2 = t * t
        t3 = t2 * t
        # Catmull-Rom basis weights for [P0, P1, P2, P3]
        basis = 0.5 * _np.hstack([
            -t + 2.0 * t2 - t3,
            2.0 - 5.0 * t2 + 3.0 * t3,
            t + 4.0 * t2 - 3.0 * t3,
            -t2 + t3,
        ])
        _CR_T_CACHE[s] = basis
    ext = _np.vstack([pts[0:1], pts, pts[-1:]])
    p0 = ext[:-3]
    p1 = ext[1:-2]
    p2 = ext[2:-1]
    p3 = ext[3:]
    # Vectorized evaluation across all segments simultaneously: shape (n-1, s, 2)
    seg_pts = (
        basis[:, 0:1][None, :, :] * p0[:, None, :]
        + basis[:, 1:2][None, :, :] * p1[:, None, :]
        + basis[:, 2:3][None, :, :] * p2[:, None, :]
        + basis[:, 3:4][None, :, :] * p3[:, None, :]
    )
    return _np.vstack([seg_pts.reshape(-1, 2), pts[-1:]])


class HyperSmoothCanvas:
    """
    Raspberry Pi 5 Optimized 60 FPS Sub-Pixel Anti-Aliased Canvas Engine (cv2.LINE_AA + shift=4).
    - Uses direct RGB memory buffer (zero cvtColor overhead) + in-place PhotoImage.paste().
    - Diff-pools native Tkinter text items so static/unchanged text is NEVER deleted or recreated per frame.
    - Eliminates 100% of Tkinter GDI jagged edges while running in ~2.0 ms/frame (45-60+ smooth FPS on RPi 5 4GB).
    - Supports `set_rough_mode(True)` for raw MS-Paint-sketched strokes in VILLAIN mode.
    """

    def __init__(self, tk_canvas=None, width: int = 1024, height: int = 600, bg: str = "#040711", ss: Optional[int] = None):
        self._tk_canvas = tk_canvas
        self.w = width
        self.h = height
        # Use ss=1 with 16x sub-pixel fixed-point AA (shift=4) for live 60 FPS UI; ss=2 for headless PNG export
        self.ss = (1 if tk_canvas is not None else 2) if ss is None else ss
        self.bg = bg
        self.bg_rgb = _hex_to_rgb(bg) or (4, 7, 17)
        self.buf = _np.empty((self.h * self.ss, self.w * self.ss, 3), dtype=_np.uint8)
        self.buf[:] = self.bg_rgb
        self.static_buf: Optional["_np.ndarray"] = None
        self._id_counter = 1
        self._items: List[int] = []
        self._static_text_specs: List[Tuple[tuple, dict]] = []
        self._dynamic_text_specs: List[Tuple[tuple, dict]] = []
        self._in_static_phase = False
        self._photo = None
        self._bg_img_id = None
        self._tk_text_pool: List[int] = []
        self._prev_text_State: List[tuple] = []
        self.rough_mode: bool = False

    def set_rough_mode(self, enabled: bool):
        self.rough_mode = bool(enabled)

    def _ensure_size(self, w: int, h: int):
        w = max(1, int(w))
        h = max(1, int(h))
        if w != self.w or h != self.h:
            self.w = w
            self.h = h
            self.buf = _np.empty((self.h * self.ss, self.w * self.ss, 3), dtype=_np.uint8)
            self.buf[:] = self.bg_rgb
            self.static_buf = None
            self._photo = None
            if self._bg_img_id is not None and self._tk_canvas is not None:
                try:
                    self._tk_canvas.delete(self._bg_img_id)
                except Exception:
                    pass
                self._bg_img_id = None
            if self._tk_canvas is not None:
                for tid in self._tk_text_pool:
                    try:
                        self._tk_canvas.delete(tid)
                    except Exception:
                        pass
                self._tk_text_pool.clear()
                self._prev_text_State.clear()
            self._static_text_specs.clear()
            self._dynamic_text_specs.clear()
            self._in_static_phase = False

    def winfo_width(self) -> int:
        if self._tk_canvas is not None:
            tw = self._tk_canvas.winfo_width()
            if tw > 1:
                self._ensure_size(tw, self.h)
            return tw
        return self.w

    def winfo_height(self) -> int:
        if self._tk_canvas is not None:
            th = self._tk_canvas.winfo_height()
            if th > 1:
                self._ensure_size(self.w, th)
            return th
        return self.h

    def bind(self, *args, **kwargs):
        if self._tk_canvas is not None:
            return self._tk_canvas.bind(*args, **kwargs)

    def pack(self, *args, **kwargs):
        if self._tk_canvas is not None:
            return self._tk_canvas.pack(*args, **kwargs)

    def find_all(self) -> List[int]:
        return [1]

    def addtag_withtag(self, tag: str, item: int):
        if tag == "static_ui" and not self._in_static_phase:
            self.static_buf = self.buf.copy()
            self._static_text_specs = list(self._dynamic_text_specs)
            self._dynamic_text_specs.clear()
            self._in_static_phase = True

    def delete(self, tag: str):
        if tag == "all":
            self.buf[:] = self.bg_rgb
            self.static_buf = None
            self._static_text_specs.clear()
            self._dynamic_text_specs.clear()
            self._in_static_phase = False
        elif tag == "dynamic":
            if self.static_buf is not None and self.static_buf.shape == self.buf.shape:
                _np.copyto(self.buf, self.static_buf)
            else:
                self.buf[:] = self.bg_rgb
            self._dynamic_text_specs.clear()
            self._in_static_phase = False

    def _next_id(self) -> int:
        return 1

    def _flatten_coords(self, args) -> List[float]:
        if len(args) == 1 and isinstance(args[0], (list, tuple)):
            return args[0]
        return [float(x) for x in args]

    def create_rectangle(self, *args, **kwargs) -> int:
        c = self._flatten_coords(args)
        if len(c) < 4:
            return self._next_id()
        scale16 = self.ss * 16.0
        x1 = int(min(c[0], c[2]) * scale16)
        y1 = int(min(c[1], c[3]) * scale16)
        x2 = int(max(c[0], c[2]) * scale16)
        y2 = int(max(c[1], c[3]) * scale16)
        fill_rgb = _hex_to_rgb(kwargs.get("fill", ""))
        out_rgb = _hex_to_rgb(kwargs.get("outline", ""))
        w = max(1, int(round(float(kwargs.get("width", 1)) * self.ss)))
        lt = _cv2.LINE_8 if self.rough_mode else _cv2.LINE_AA
        if fill_rgb is not None:
            _cv2.rectangle(self.buf, (x1, y1), (x2, y2), fill_rgb, -1, lineType=lt, shift=4)
        if out_rgb is not None:
            _cv2.rectangle(self.buf, (x1, y1), (x2, y2), out_rgb, w, lineType=lt, shift=4)
        return self._next_id()

    def create_oval(self, *args, **kwargs) -> int:
        c = self._flatten_coords(args)
        if len(c) < 4:
            return self._next_id()
        cx = (c[0] + c[2]) * 0.5
        cy = (c[1] + c[3]) * 0.5
        rx = abs(c[2] - c[0]) * 0.5
        ry = abs(c[3] - c[1]) * 0.5
        if rx < 0.2 or ry < 0.2:
            return self._next_id()
        fill_rgb = _hex_to_rgb(kwargs.get("fill", ""))
        out_rgb = _hex_to_rgb(kwargs.get("outline", ""))
        w = max(1, int(round(float(kwargs.get("width", 1)) * self.ss)))
        lt = _cv2.LINE_8 if self.rough_mode else _cv2.LINE_AA
        scale16 = self.ss * 16.0
        pts = ((_UNIT_CIRCLE_64 * (rx, ry) + (cx, cy)) * scale16).astype(_np.int32)
        if fill_rgb is not None:
            _cv2.fillPoly(self.buf, [pts], fill_rgb, lineType=lt, shift=4)
            if out_rgb is None and lt == _cv2.LINE_AA:
                _cv2.polylines(self.buf, [pts], True, fill_rgb, 1, lineType=_cv2.LINE_AA, shift=4)
        if out_rgb is not None:
            _cv2.polylines(self.buf, [pts], True, out_rgb, w, lineType=lt, shift=4)
        return self._next_id()

    def create_line(self, *args, **kwargs) -> int:
        c = self._flatten_coords(args)
        if len(c) < 4 or len(c) % 2 != 0:
            return self._next_id()
        fill_rgb = _hex_to_rgb(kwargs.get("fill", "#ffffff"))
        if fill_rgb is None:
            return self._next_id()
        w = max(1, int(round(float(kwargs.get("width", 1)) * self.ss)))
        smooth = kwargs.get("smooth", False)
        lt = _cv2.LINE_8 if self.rough_mode else _cv2.LINE_AA
        scale16 = self.ss * 16.0
        if smooth and len(c) >= 6:
            pts = (_catmull_rom_np(c, samples_per_seg=8) * scale16).astype(_np.int32)
        else:
            pts = (_np.array(c, dtype=_np.float64).reshape(-1, 2) * scale16).astype(_np.int32)
        _cv2.polylines(self.buf, [pts], False, fill_rgb, w, lineType=lt, shift=4)
        return self._next_id()

    def create_polygon(self, *args, **kwargs) -> int:
        c = self._flatten_coords(args)
        if len(c) < 6 or len(c) % 2 != 0:
            return self._next_id()
        fill_rgb = _hex_to_rgb(kwargs.get("fill", ""))
        out_rgb = _hex_to_rgb(kwargs.get("outline", ""))
        w = max(1, int(round(float(kwargs.get("width", 1)) * self.ss)))
        smooth = kwargs.get("smooth", False)
        lt = _cv2.LINE_8 if self.rough_mode else _cv2.LINE_AA
        scale16 = self.ss * 16.0
        if smooth and len(c) >= 6:
            closed_c = list(c) + list(c[:4])
            pts = (_catmull_rom_np(closed_c, samples_per_seg=7) * scale16).astype(_np.int32)
        else:
            pts = (_np.array(c, dtype=_np.float64).reshape(-1, 2) * scale16).astype(_np.int32)
        if fill_rgb is not None:
            _cv2.fillPoly(self.buf, [pts], fill_rgb, lineType=lt, shift=4)
            if out_rgb is None and lt == _cv2.LINE_AA:
                _cv2.polylines(self.buf, [pts], True, fill_rgb, 1, lineType=_cv2.LINE_AA, shift=4)
        if out_rgb is not None:
            _cv2.polylines(self.buf, [pts], True, out_rgb, w, lineType=lt, shift=4)
        return self._next_id()

    def create_arc(self, *args, **kwargs) -> int:
        c = self._flatten_coords(args)
        if len(c) < 4:
            return self._next_id()
        x1, y1, x2, y2 = c[0], c[1], c[2], c[3]
        start_tk = float(kwargs.get("start", 0.0))
        extent_tk = float(kwargs.get("extent", 90.0))
        out_rgb = _hex_to_rgb(kwargs.get("outline", "#ffffff"))
        if out_rgb is None:
            return self._next_id()
        w = max(1, int(round(float(kwargs.get("width", 1)) * self.ss)))
        cx = (x1 + x2) * 0.5
        cy = (y1 + y2) * 0.5
        rx = abs(x2 - x1) * 0.5
        ry = abs(y2 - y1) * 0.5
        steps = max(18, int(abs(extent_tk) * 0.35))
        degs = _np.linspace(start_tk, start_tk + extent_tk, steps)
        rads = _np.radians(degs)
        pts = _np.column_stack([cx + rx * _np.cos(rads), cy - ry * _np.sin(rads)])
        pts_i32 = (pts * (self.ss * 16.0)).astype(_np.int32)
        _cv2.polylines(self.buf, [pts_i32], False, out_rgb, w, lineType=_cv2.LINE_AA, shift=4)
        return self._next_id()

    def create_text(self, *args, **kwargs) -> int:
        c = self._flatten_coords(args)
        if len(c) >= 2:
            kw_clean = dict(kwargs)
            kw_clean.pop("tags", None)
            self._dynamic_text_specs.append(((c[0], c[1]), kw_clean))
        return self._next_id()

    def flush(self):
        """Ultra-fast zero-cvtColor paste to Tkinter PhotoImage + diff-pooled ClearType text items."""
        if self._tk_canvas is None or _PILImageTk is None:
            return
        if self.ss > 1:
            down = _cv2.resize(self.buf, (self.w, self.h), interpolation=_cv2.INTER_AREA)
        else:
            down = self.buf
        pil_img = _PILImage.fromarray(down, "RGB")
        if self._photo is None:
            self._photo = _PILImageTk.PhotoImage(image=pil_img)
            if self._bg_img_id is not None:
                try:
                    self._tk_canvas.delete(self._bg_img_id)
                except Exception:
                    pass
            self._bg_img_id = self._tk_canvas.create_image(0, 0, anchor="nw", image=self._photo)
            self._tk_canvas.tag_lower(self._bg_img_id)
        else:
            self._photo.paste(pil_img)
            if self._bg_img_id is not None:
                self._tk_canvas.tag_lower(self._bg_img_id)

        all_specs = self._static_text_specs + self._dynamic_text_specs
        need = len(all_specs)

        # Hide excess pooled text items without destroying them
        if len(self._tk_text_pool) > need:
            for idx in range(need, len(self._tk_text_pool)):
                if idx < len(self._prev_text_State) and self._prev_text_State[idx] != ("HIDDEN",):
                    self._tk_canvas.itemconfigure(self._tk_text_pool[idx], state="hidden")
                    self._prev_text_State[idx] = ("HIDDEN",)

        for idx, ((tx, ty), tkw) in enumerate(all_specs):
            sig = (round(tx, 1), round(ty, 1), tkw.get("text"), tkw.get("fill"), tkw.get("font"), tkw.get("anchor"), tkw.get("width"))
            if idx < len(self._tk_text_pool):
                tid = self._tk_text_pool[idx]
                if idx >= len(self._prev_text_State) or self._prev_text_State[idx] != sig:
                    self._tk_canvas.coords(tid, tx, ty)
                    self._tk_canvas.itemconfigure(tid, state="normal", **tkw)
                    if idx < len(self._prev_text_State):
                        self._prev_text_State[idx] = sig
                    else:
                        self._prev_text_State.append(sig)
                self._tk_canvas.tag_raise(tid)
            else:
                tid = self._tk_canvas.create_text(tx, ty, **tkw)
                self._tk_text_pool.append(tid)
                self._prev_text_State.append(sig)
                self._tk_canvas.tag_raise(tid)

    def apply_crt_effects(self, scan_strength: float = 0.0, scan_offset: int = 0, bands=None, roll=None, brown: float = 1.0):
        """
        Analog-monitor look applied to the finished frame buffer (graphics only; text items are separate and stay crisp):
          - scan_strength: darkens every 3rd pixel row (CRT scanlines); scan_offset slowly crawls them
          - bands: [(y, height, dx)] horizontal raster tears, rows shifted sideways by dx pixels
          - roll: (y, height, gain) a rolling interference band that brightens the rows it covers
          - brown: global brightness multiplier (< 1.0) for brief voltage-dip brownouts
        The static layer is restored from its snapshot every frame, so nothing accumulates.
        """
        buf = self.buf
        ss = self.ss
        H = buf.shape[0]
        if bands:
            for (y, bh, dx) in bands:
                y0 = int(max(0, y * ss))
                y1 = int(min(H, (y + bh) * ss))
                sh = int(dx * ss)
                if y1 > y0 and sh:
                    buf[y0:y1] = _np.roll(buf[y0:y1], sh, axis=1)
        if roll:
            ry, rh, gain = roll
            y0 = int(max(0, ry * ss))
            y1 = int(min(H, (ry + rh) * ss))
            if y1 > y0:
                reg = buf[y0:y1].astype(_np.uint32) * int(gain * 256) >> 8
                buf[y0:y1] = _np.minimum(reg, 255).astype(_np.uint8)
        if scan_strength > 0.0:
            k = int((1.0 - scan_strength) * 256)
            start = (scan_offset * ss) % (3 * ss)
            rows = buf[start::3 * ss]
            buf[start::3 * ss] = (rows.astype(_np.uint32) * k >> 8).astype(_np.uint8)
        if brown < 0.999:
            buf[:] = (buf.astype(_np.uint32) * int(max(0.0, brown) * 256) >> 8).astype(_np.uint8)

    def get_pil_image(self, crop_box=None, target_size=None) -> "_PILImage.Image":
        """Headless high-precision export (renders text via PIL TrueType and downsamples with LANCZOS)."""
        pil_ss = _PILImage.fromarray(self.buf.copy(), "RGB")
        draw = _PILImageDraw.Draw(pil_ss)

        def _load_pil_font(size_px: int, is_bold: bool, is_mono: bool = False):
            if is_mono:
                candidates = [
                    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf" if is_bold else "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
                    "C:/Windows/Fonts/consolab.ttf" if is_bold else "C:/Windows/Fonts/consola.ttf",
                ]
            else:
                candidates = [
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if is_bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                    "C:/Windows/Fonts/segoeuib.ttf" if is_bold else "C:/Windows/Fonts/segoeui.ttf",
                ]
            for fp in candidates:
                if os.path.exists(fp):
                    try:
                        return _PILImageFont.truetype(fp, max(8, int(size_px)))
                    except Exception:
                        pass
            return _PILImageFont.load_default()

        for (tx, ty), tkw in (self._static_text_specs + self._dynamic_text_specs):
            x = tx * self.ss
            y = ty * self.ss
            text = str(tkw.get("text", ""))
            fill_rgb = _hex_to_rgb(tkw.get("fill", "#ffffff")) or (255, 255, 255)
            f_spec = tkw.get("font", (FONT_FAMILY, 12, "normal"))
            f_name = str(f_spec[0]).lower() if len(f_spec) > 0 else ""
            f_size = int(f_spec[1]) if len(f_spec) > 1 else 12
            is_bold = len(f_spec) > 2 and "bold" in str(f_spec[2]).lower()
            is_mono = "mono" in f_name or "consol" in f_name or "courier" in f_name
            pil_font = _load_pil_font(int(f_size * self.ss * 1.12), is_bold, is_mono)
            anchor = tkw.get("anchor", "center")
            bbox = draw.multiline_textbbox((0, 0), text, font=pil_font, spacing=int(3 * self.ss))
            tw_t = bbox[2] - bbox[0]
            th_t = bbox[3] - bbox[1]
            if anchor == "w":
                dx, dy = x, y - th_t * 0.5
            elif anchor == "e":
                dx, dy = x - tw_t, y - th_t * 0.5
            elif anchor == "nw":
                dx, dy = x, y
            else:
                dx, dy = x - tw_t * 0.5, y - th_t * 0.5
            draw.multiline_text((dx, dy), text, fill=fill_rgb, font=pil_font, spacing=int(3 * self.ss))

        if self.ss > 1:
            full_res = pil_ss.resize((self.w, self.h), _PILImage.Resampling.LANCZOS)
        else:
            full_res = pil_ss
        if crop_box is not None:
            full_res = full_res.crop(crop_box)
        if target_size is not None:
            full_res = full_res.resize(target_size, _PILImage.Resampling.LANCZOS)
        return full_res


def lerp_color(color_a: str, color_b: str, t: float) -> str:
    """Smoothly blends between two hex colors based on t (0.0 to 1.0)."""
    t = max(0.0, min(1.0, float(t)))
    r1, g1, b1 = int(color_a[1:3], 16), int(color_a[3:5], 16), int(color_a[5:7], 16)
    r2, g2, b2 = int(color_b[1:3], 16), int(color_b[3:5], 16), int(color_b[5:7], 16)
    r = int(r1 + (r2 - r1) * t)
    g = int(g1 + (g2 - g1) * t)
    b = int(b1 + (b2 - b1) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


def ease_out_cubic(t: float) -> float:
    """Apple-style cubic ease-out curve."""
    t = max(0.0, min(1.0, float(t)))
    return 1.0 - pow(1.0 - t, 3)


def ease_out_back(t: float, overshoot: float = 1.35) -> float:
    """Spring-like overshoot easing for expressive state transitions."""
    t = max(0.0, min(1.0, float(t)))
    c1 = overshoot
    c3 = c1 + 1.0
    return 1.0 + c3 * pow(t - 1.0, 3) + c1 * pow(t - 1.0, 2)


class ExpressionState:
    """All emotion and visual states supported by the Neurolis Mark II Face UI."""

    # Boot states
    BOOT_GREETING = "boot_greeting"
    BOOT_SEQUENCE = "boot_sequence"

    # 11 Overhauled Core States
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
    VILLAIN = "villain"
    VILLIAN = "villain"  # Common spelling alias for seamless compatibility

    # 10 New Conversational Expressions for Mark II Chat Tone / User Input
    EXCITED = "excited"      # Golden starburst optics with happy curved lower lid & D-smile
    LAUGHING = "laughing"    # Joyful squeezed > < chevrons, flying tear beads & wide laugh
    LOVE = "love"            # Frameless bordered neon-rose heart optics (♥ ♥) & floating hearts
    WINK = "wink"            # Curved-bottom smiling open left eye + right wink arch & :P grin
    SURPRISED = "surprised"  # Circular shockwave ring optics with pinpoint core & 'O' gasp
    SLEEPY = "sleepy"        # Heavy drooping lavender eyelids, sleep bubble & cascading Zzz
    SHY = "shy"              # Inward-tilted bashful sakura optics, averted gaze, /// blush & sweat drop
    PROUD = "proud"          # Heroic upward-curved golden optics, floating 3D crown & tooth sparkle
    CURIOUS = "curious"      # Asymmetric magnifying loupe optic with rotating bezel & !? spark
    SKEPTICAL = "skeptical"  # Deadpan half-lidded side-eye with '...' temple dots & knowing smirk
    COOL = "cool"            # Bordered cyber-aviator sunglasses visor, lens sheen & confident smirk

    # Helpful conversational aliases
    AMAZED = "surprised"
    AMUSED = "laughing"
    AFFECTIONATE = "love"
    TIRED = "sleepy"
    BASHFUL = "shy"
    CONFIDENT = "proud"
    INQUISITIVE = "curious"
    DOUBTFUL = "skeptical"

    CORE_STATES: List[str] = [
        IDLE, HAPPY, SAD, CONFUSED, THINKING, LISTENING,
        SPEAKING, WATCHING, MOVING, ERROR, VILLAIN,
    ]

    CONVERSATIONAL_STATES: List[str] = [
        EXCITED, LAUGHING, LOVE, WINK, SURPRISED,
        SLEEPY, SHY, PROUD, CURIOUS, SKEPTICAL, COOL,
    ]

    ALL_EXPRESSIONS: List[str] = CORE_STATES + CONVERSATIONAL_STATES

    ALIASES: Dict[str, str] = {
        "villian": VILLAIN,
        "rogue": VILLAIN,
        "evil": VILLAIN,
        "amazed": SURPRISED,
        "shocked": SURPRISED,
        "wow": SURPRISED,
        "amused": LAUGHING,
        "haha": LAUGHING,
        "lol": LAUGHING,
        "giggle": LAUGHING,
        "affectionate": LOVE,
        "heart": LOVE,
        "adoring": LOVE,
        "tired": SLEEPY,
        "drowsy": SLEEPY,
        "yawn": SLEEPY,
        "bashful": SHY,
        "blush": SHY,
        "flattered": SHY,
        "confident": PROUD,
        "smug_proud": PROUD,
        "triumph": PROUD,
        "inquisitive": CURIOUS,
        "intrigued": CURIOUS,
        "wonder": CURIOUS,
        "doubtful": SKEPTICAL,
        "unimpressed": SKEPTICAL,
        "suspicious": SKEPTICAL,
        "hype": EXCITED,
        "thrilled": EXCITED,
        "starstruck": EXCITED,
        "flirty": WINK,
        "cheeky": WINK,
        "playful": WINK,
        "sunglasses": COOL,
        "chill": COOL,
        "swag": COOL,
        "nervous": SHY,
        "hesitant": SHY,
    }


BASE_DIR = Path(__file__).resolve().parent
BOOT_AUDIO_WAV = BASE_DIR / "assets" / "sounds" / "boot_loop.wav"
BOOT_AUDIO_MP3 = BASE_DIR / "assets" / "sounds" / "boot_loop.mp3"


def ensure_boot_audio() -> Optional[Path]:
    """Ensures the boot sound loop exists locally, checking local assets, brain uploads, GitHub, or synthesizing."""
    if BOOT_AUDIO_WAV.exists() and BOOT_AUDIO_WAV.stat().st_size > 1000:
        return BOOT_AUDIO_WAV
    if BOOT_AUDIO_MP3.exists() and BOOT_AUDIO_MP3.stat().st_size > 1000:
        try:
            import soundfile as sf
            data, sr = sf.read(str(BOOT_AUDIO_MP3))
            BOOT_AUDIO_WAV.parent.mkdir(parents=True, exist_ok=True)
            sf.write(str(BOOT_AUDIO_WAV), data, sr, subtype="PCM_16")
            return BOOT_AUDIO_WAV
        except Exception:
            return BOOT_AUDIO_MP3

    brain_candidates = [
        Path(r"C:\Users\swapn\.gemini\antigravity\brain\636a8fe0-85dc-4870-bd6a-3350372df403\.user_uploaded\uploaded_media_1790862962719.mp3"),
        Path(r"C:\Users\swapn\.gemini\antigravity\brain\636a8fe0-85dc-4870-bd6a-3350372df403\.user_uploaded\uploaded_media_1790863007474.mp3"),
    ]
    BOOT_AUDIO_WAV.parent.mkdir(parents=True, exist_ok=True)
    for cand in brain_candidates:
        if cand.exists() and cand.stat().st_size > 1000:
            try:
                shutil.copyfile(cand, BOOT_AUDIO_MP3)
                import soundfile as sf
                data, sr = sf.read(str(BOOT_AUDIO_MP3))
                sf.write(str(BOOT_AUDIO_WAV), data, sr, subtype="PCM_16")
                return BOOT_AUDIO_WAV
            except Exception:
                if BOOT_AUDIO_MP3.exists():
                    return BOOT_AUDIO_MP3

    raw_urls = [
        "https://raw.githubusercontent.com/swapnil-jchauhan/Neurolis-AI-Humanoid/main/assets/sounds/boot_loop.wav",
        "https://raw.githubusercontent.com/swapnil-jchauhan/Neurolis-AI-Humanoid/main/assets/sounds/boot_loop.mp3",
    ]
    import ssl
    import urllib.request
    for url in raw_urls:
        dest = BOOT_AUDIO_WAV if url.endswith(".wav") else BOOT_AUDIO_MP3
        try:
            with urllib.request.urlopen(url, timeout=6) as resp, open(dest, "wb") as f:
                f.write(resp.read())
            if dest.exists() and dest.stat().st_size > 1000:
                if dest == BOOT_AUDIO_MP3 and not BOOT_AUDIO_WAV.exists():
                    try:
                        import soundfile as sf
                        data, sr = sf.read(str(BOOT_AUDIO_MP3))
                        sf.write(str(BOOT_AUDIO_WAV), data, sr, subtype="PCM_16")
                        return BOOT_AUDIO_WAV
                    except Exception:
                        return BOOT_AUDIO_MP3
                return dest
        except Exception:
            try:
                ctx = ssl._create_unverified_context()
                with urllib.request.urlopen(url, context=ctx, timeout=6) as resp, open(dest, "wb") as f:
                    f.write(resp.read())
                if dest.exists() and dest.stat().st_size > 1000:
                    return dest
            except Exception:
                pass

    try:
        import numpy as np
        import soundfile as sf
        sr = 48000
        duration = 3.2
        t = np.linspace(0, duration, int(sr * duration), endpoint=False)
        signal = (
            0.32 * np.sin(2 * np.pi * 110.0 * t)
            + 0.24 * np.sin(2 * np.pi * 164.81 * t)
            + 0.20 * np.sin(2 * np.pi * 220.0 * t)
            + 0.14 * np.sin(2 * np.pi * 277.18 * t)
            + 0.10 * np.sin(2 * np.pi * 329.63 * t)
        )
        lfo = 0.82 + 0.18 * np.sin(2 * np.pi * 0.62 * t)
        stereo = np.column_stack([signal * lfo, signal * lfo * 0.96])
        sf.write(str(BOOT_AUDIO_WAV), stereo.astype(np.float32), sr, subtype="PCM_16")
        return BOOT_AUDIO_WAV
    except Exception:
        pass

    return None


class BootAudioPlayer:
    """
    Plays the boot soundtrack in a seamless cross-faded continuous loop
    synchronized with the loading bar, fading out gracefully upon completion.
    """

    def __init__(self, audio_path: Optional[Path] = None):
        self.audio_path = audio_path or ensure_boot_audio()
        self.stream = None
        self.is_playing = False
        self.loop_buf: Optional["np.ndarray"] = None
        self.samplerate: int = 48000
        self.channels: int = 2
        self.pos: int = 0
        self.fade_vol: float = 1.0
        self.is_fading: bool = False
        self.fade_step: float = 0.0
        self.lock = threading.Lock()
        self._load_and_prepare_loop()

    def _load_and_prepare_loop(self):
        if not self.audio_path or not self.audio_path.exists():
            return
        try:
            import numpy as np
            import soundfile as sf
            data, sr = sf.read(str(self.audio_path), dtype="float32")
            if data.ndim == 1:
                data = np.column_stack([data, data])
            self.samplerate = sr
            self.channels = data.shape[1]

            N = len(data)
            L = min(int(0.20 * sr), max(10, N // 4))
            M = N - L
            if M > L:
                loop_buf = np.copy(data[:M])
                w = np.linspace(0.0, 1.0, L)[:, None]
                loop_buf[:L] = w * data[:L] + (1.0 - w) * data[M:]
                self.loop_buf = loop_buf
            else:
                self.loop_buf = data
        except Exception as e:
            print(f"[Screen] Boot audio load notice: {e}")

    def _audio_callback(self, outdata, frames, time_info, status):
        with self.lock:
            if not self.is_playing or self.loop_buf is None:
                outdata.fill(0)
                return

            buf_len = len(self.loop_buf)
            written = 0
            while written < frames:
                chunk = min(frames - written, buf_len - self.pos)
                outdata[written : written + chunk] = (
                    self.loop_buf[self.pos : self.pos + chunk] * self.fade_vol
                )
                written += chunk
                self.pos = (self.pos + chunk) % buf_len

            if self.is_fading:
                self.fade_vol = max(0.0, self.fade_vol - self.fade_step * frames)
                if self.fade_vol <= 0.0:
                    self.is_playing = False

    def start(self):
        if self.is_playing or self.loop_buf is None:
            return
        try:
            import sounddevice as sd
            try:
                devices = sd.query_devices()
                has_output = any(
                    d.get("max_output_channels", 0) > 0
                    for d in devices
                    if isinstance(d, dict)
                )
                if not has_output:
                    self.is_playing = False
                    return
            except Exception:
                pass

            self.is_playing = True
            self.fade_vol = 1.0
            self.is_fading = False
            self.pos = 0

            with suppress_c_stderr():
                for dev in ["default", "sysdefault", None]:
                    try:
                        self.stream = sd.OutputStream(
                            samplerate=self.samplerate,
                            channels=self.channels,
                            device=dev,
                            callback=self._audio_callback,
                        )
                        break
                    except Exception:
                        pass
                if self.stream is None:
                    for dev in ["default", "sysdefault", None]:
                        try:
                            self.stream = sd.OutputStream(
                                samplerate=44100,
                                channels=min(2, self.channels),
                                device=dev,
                                callback=self._audio_callback,
                            )
                            break
                        except Exception:
                            pass
            if self.stream is not None:
                with suppress_c_stderr():
                    self.stream.start()
            else:
                self.is_playing = False
        except Exception:
            self.is_playing = False

    def fade_out_and_stop(self, fade_duration: float = 0.5):
        with self.lock:
            if not self.is_playing:
                return
            self.is_fading = True
            total_samples = max(1.0, fade_duration * self.samplerate)
            self.fade_step = 1.0 / total_samples

        def _closer():
            time.sleep(fade_duration + 0.1)
            with self.lock:
                if self.stream is not None:
                    try:
                        self.stream.stop()
                        self.stream.close()
                    except Exception:
                        pass
                    self.stream = None
                self.is_playing = False

        threading.Thread(target=_closer, daemon=True).start()


class FaceUI:
    """
    Main Real-Time Animated Face UI for Neurolis Mark II.
    Renders 22 distinct emotional & operational states + Apple-grade Boot Splash & Spring Physics.
    """

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

        # State management & Apple-grade spring transition physics
        self.state = ExpressionState.BOOT_GREETING if enable_boot else ExpressionState.IDLE
        self.prev_state = self.state
        self.state_change_time = time.time()
        self.transition_progress = 1.0
        self.status_text = "BOOTING..." if enable_boot else "STANDBY // READY"
        self.lock = threading.Lock()
        self.running = False

        # Launch sequence & splash timing
        self.boot_duration = 3.3
        self.boot_start_time = time.time()
        self.boot_audio_player = BootAudioPlayer()
        if enable_boot:
            self.boot_audio_player.start()

        # Ghostly CRT glitch & static flicker animation state
        self.glitch_active = False
        self.glitch_start_time = 0.0
        self.glitch_duration = 0.3
        self.glitch_cycles = 3

        # Standby yawn animation (set via play_yawn, read by the sleepy face renderer)
        self.yawn_start = 0.0
        self.yawn_duration = 0.0

        # VILLAIN hacked-CRT scheduler (irregular tears, brownouts, rolling band); seeded so behaviour is repeatable
        self._vil = {
            "rng": random.Random(0x7F),
            "entry": -999.0,
            "next_tear": 0.0, "tear_end": 0.0, "bands": [], "tear_dx": 0.0,
            "next_brown": 0.0, "brown_end": 0.0,
            "corrupt_until": 0.0,
            "heavy": False,
        }

        # Loud-room "raise your palm" alert: None | "waiting" | "recording" (set by listen.py via set_loud_alert)
        self.loud_alert_mode = None
        self.loud_alert_level = 0.0

        # Spring-damped Eye Tracking & Parallax Coordinates (-1.0 to 1.0)
        self.target_look_x = 0.0
        self.target_look_y = 0.0
        self.current_look_x = 0.0
        self.current_look_y = 0.0
        self.look_vel_x = 0.0
        self.look_vel_y = 0.0
        self._last_idle_saccade = time.time()
        self._next_saccade_interval = random.uniform(2.4, 4.2)

        # Apple-Grade Asymmetric Blink Physics (fast close, brief hold, smooth cubic open + double blinks)
        self.blink_progress = 0.0
        self.is_blinking = False
        self.last_blink_time = time.time()
        self.next_blink_interval = random.uniform(2.6, 5.2)
        self._pending_double_blink = False

        # Real wall-clock delta-time, continuous oscillation phases & Real-Time Audio RMS Lip-Sync (QoL #4)
        self._last_frame_time = time.time()
        self.anim_phase = 0.0
        self.thinking_angle = 0.0
        self.speaking_intensity = 0.65
        self._target_speaking_intensity = 0.65
        self.is_voice_playing = False
        self._last_lip_sync_time = 0.0
        self.lip_sync_bands: List[float] = []

        # Live Exhibition Telemetry Pill State (QoL #7: Groq Fleet, Cartesia/Edge TTS, Mic Floor RMS)
        self.telemetry_header_text: str = ""
        self.telemetry_footer_text: str = ""
        self.telemetry_alert_level: str = "ok"
        self.telemetry_provider = None
        self._last_telemetry_poll: float = 0.0

        # Subtitles
        self.subtitle_speaker = "NEUROLIS MARK II"
        self.subtitle_text = "Standing by. Show open palm or press Enter to begin."
        self.subtitle_time = time.time()

        # Luminous Bionic OLED Robot Palette
        self.color_eye_main = "#00f0ff"
        self.color_eye_glow = "#002b3d"
        self.color_pupil = "#ffffff"
        self.color_error = "#ff1e42"
        self.color_listening = "#00f5d4"
        self.color_thinking = "#a855f7"
        self.color_happy = "#00ff88"
        self.color_sad = "#3b82f6"
        self.color_sad_glow = "#0b1e40"
        self.color_confused = "#ffb703"
        self.color_confused_glow = "#3b2500"
        self.color_excited = "#ffd000"
        self.color_laughing = "#ff9500"
        self.color_love = "#ff2a85"
        self.color_wink = "#00f5d4"
        self.color_surprised = "#38bdf8"
        self.color_sleepy = "#a78bfa"
        self.color_shy = "#ff7597"
        self.color_proud = "#fbbf24"
        self.color_curious = "#10b981"
        self.color_skeptical = "#84cc16"
        self.color_cool = "#00f0ff"

        # Sleek, Less-Boxy Organic Geometry scaled for 1024x600 (128:75 ratio)
        self.ui_scale = (self.width / 1024.0) * 1.15
        self.eye_w = int(162 * self.ui_scale)
        self.eye_h = int(162 * self.ui_scale)
        self.eye_spacing = int(266 * self.ui_scale)
        # Higher organic corner radius (~42% of width) so bordered eyes look sleek and organic, NEVER boxy!
        self.corner_radius = int(66 * self.ui_scale)

        # Gesture HUD Bar & fallback click attributes & callbacks
        self.gesture_sentry = None
        self._gesture_feedback = (None, 0.0)
        self.on_talk_click = None
        self.on_standby_click = None
        self.on_send_click = None
        self.talk_btn_bbox = None
        self.standby_btn_bbox = None
        self.send_btn_bbox = None
        self._hud_geom = None
        self._last_talk_press_time = 0.0
        self.last_standby_press_time = 0.0
        self._last_standby_press_time = 0.0
        self._last_send_press_time = 0.0

        # Optical Human Latch tracking attributes
        self.target_latched = False
        self.target_latch_time = 0.0
        self.target_latch_label = "HUMAN TARGET"

        # Tkinter handles
        self.root: Optional[tk.Tk] = None
        self.canvas: Optional[tk.Canvas] = None
        self._thread: Optional[threading.Thread] = None

    def set_human_latch(self, latched: bool = True, label: str = "HUMAN TARGET"):
        pass

    def set_gesture_sentry(self, gesture_sentry):
        self.gesture_sentry = gesture_sentry

    def set_motor_controller(self, motor_controller):
        pass

    def skip_boot(self):
        with self.lock:
            if self.state in [ExpressionState.BOOT_GREETING, ExpressionState.BOOT_SEQUENCE]:
                self.prev_state = self.state
                self.state = ExpressionState.IDLE
                self.state_change_time = time.time()
                self.transition_progress = 0.0
                self.status_text = "STANDBY // READY"
                if not self.subtitle_text or self.subtitle_text in ("Booting...", "Standing by. Show open palm or press Enter to begin."):
                    self.subtitle_speaker = "NEUROLIS MARK II"
                    self.subtitle_text = "Standing by. Show open palm or press Enter to begin."
                self.is_blinking = True
                self.blink_progress = 0.35
        self._last_static_key = None
        if hasattr(self, "boot_audio_player"):
            self.boot_audio_player.fade_out_and_stop(0.3)

    def _on_key(self, event):
        key = (event.keysym or "").lower()
        if key in ["f", "f11"]:
            self._toggle_fullscreen()
            return
        if key == "escape":
            self.stop()
            return
        if key in ["return", "enter"]:
            with self.lock:
                in_boot = self.state in [ExpressionState.BOOT_GREETING, ExpressionState.BOOT_SEQUENCE]
                is_standby = self.state == ExpressionState.IDLE
            if in_boot:
                self.skip_boot()
            elif is_standby:
                if self.on_talk_click is not None:
                    try:
                        self.on_talk_click()
                    except Exception as e:
                        print(f"[Screen] Enter key talk callback error: {e}")
            else:
                if self.on_send_click is not None:
                    try:
                        self.on_send_click()
                    except Exception as e:
                        print(f"[Screen] Enter key send callback error: {e}")
            return

        hotkey_map = {
            "1": ExpressionState.IDLE,
            "2": ExpressionState.HAPPY,
            "3": ExpressionState.SAD,
            "4": ExpressionState.CONFUSED,
            "5": ExpressionState.THINKING,
            "6": ExpressionState.LISTENING,
            "7": ExpressionState.SPEAKING,
            "8": ExpressionState.WATCHING,
            "9": ExpressionState.MOVING,
            "0": ExpressionState.ERROR,
            "v": ExpressionState.VILLAIN,
            "q": ExpressionState.EXCITED,
            "w": ExpressionState.LAUGHING,
            "e": ExpressionState.LOVE,
            "r": ExpressionState.WINK,
            "t": ExpressionState.SURPRISED,
            "y": ExpressionState.SLEEPY,
            "u": ExpressionState.SHY,
            "i": ExpressionState.PROUD,
            "o": ExpressionState.CURIOUS,
            "p": ExpressionState.SKEPTICAL,
            "c": ExpressionState.COOL,
        }
        with self.lock:
            in_boot = self.state in [ExpressionState.BOOT_GREETING, ExpressionState.BOOT_SEQUENCE]
        if in_boot:
            self.skip_boot()
            return

        if key == "b":
            with self.lock:
                self.boot_start_time = time.time()
                self.state = ExpressionState.BOOT_GREETING
                self.status_text = "BOOTING..."
            return
        if key in ["space", "tab"]:
            with self.lock:
                all_exp = ExpressionState.ALL_EXPRESSIONS
                idx = all_exp.index(self.state) if self.state in all_exp else -1
                next_st = all_exp[(idx + 1) % len(all_exp)]
            self.set_state(next_st)
            return
        if key in hotkey_map:
            self.set_state(hotkey_map[key])

    def _on_screen_press(self, event):
        if self.root:
            try:
                self.root.focus_force()
            except Exception:
                pass
        with self.lock:
            in_boot = self.state in [ExpressionState.BOOT_GREETING, ExpressionState.BOOT_SEQUENCE]
        if in_boot:
            self.skip_boot()
            return

        with self.lock:
            is_standby = self.state == ExpressionState.IDLE

        if is_standby:
            self._last_talk_press_time = time.time()
            if self.on_talk_click is not None:
                try:
                    self.on_talk_click()
                except Exception as e:
                    print(f"[Screen] Talk callback error: {e}")
            return

        if self.standby_btn_bbox is not None and not is_standby:
            sbx1, sby1, sbx2, sby2 = self.standby_btn_bbox
            if sbx1 <= event.x <= sbx2 and sby1 <= event.y <= sby2:
                self._last_standby_press_time = time.time()
                if self.on_standby_click is not None:
                    try:
                        self.on_standby_click()
                    except Exception as e:
                        print(f"[Screen] Standby button callback error: {e}")
                return

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

    def _run_tk_loop(self):
        self.root = tk.Tk()
        self.root.title("Neurolis Mark II Face UI")
        self.root.geometry(f"{self.width}x{self.height}")
        self.root.configure(bg=self.bg_color)

        if self.fullscreen:
            self._apply_fullscreen_state()

        self.root.bind("<Escape>", lambda e: self.stop())
        self.root.bind("<Key>", self._on_key)

        self._tk_canvas = tk.Canvas(
            self.root,
            width=self.width,
            height=self.height,
            bg=self.bg_color,
            highlightthickness=0,
        )
        self._tk_canvas.pack(fill=tk.BOTH, expand=True)
        self._tk_canvas.bind("<Button-1>", self._on_screen_press)
        if _HAS_CV2_AA and _PILImageTk is not None:
            self.canvas = HyperSmoothCanvas(tk_canvas=self._tk_canvas, width=self.width, height=self.height, bg=self.bg_color, ss=1)
        else:
            self.canvas = self._tk_canvas

        self.running = True
        self._last_frame_time = time.time()
        self._animate_loop()
        self.root.mainloop()

    def _apply_fullscreen_state(self):
        if not self.root:
            return
        self._last_static_key = None
        is_linux = sys.platform.startswith("linux")
        if is_linux:
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            if self.fullscreen:
                self.root.withdraw()
                self.root.overrideredirect(True)
                self.root.deiconify()
                self.root.geometry(f"{sw - 1}x{sh}+0+0")
                self.root.update_idletasks()
                self.root.lift()
                self.root.focus_force()
            else:
                cx = max(0, (sw - self.width) // 2)
                cy = max(0, (sh - self.height) // 2)
                self.root.withdraw()
                self.root.overrideredirect(False)
                self.root.deiconify()
                self.root.geometry(f"{self.width}x{self.height}+{cx}+{cy}")
                self.root.update_idletasks()
                self.root.focus_force()
        else:
            try:
                self.root.attributes("-fullscreen", self.fullscreen)
            except Exception:
                try:
                    self.root.wm_attributes("-fullscreen", 1 if self.fullscreen else 0)
                except Exception:
                    pass

    def _toggle_fullscreen(self):
        if self.root:
            self.fullscreen = not self.fullscreen
            self._apply_fullscreen_state()

    def set_state(self, state: str, status_msg: Optional[str] = None):
        """Thread-safe state update called from listen.py with Apple-grade spring transition trigger."""
        norm = str(state or "idle").strip().lower()
        norm = ExpressionState.ALIASES.get(norm, norm)
        now = time.time()
        with self.lock:
            if norm != self.state:
                was_villain = (self.state == ExpressionState.VILLAIN)
                is_villain = (norm == ExpressionState.VILLAIN)
                self.prev_state = self.state
                self.state = norm
                self.state_change_time = now
                self.transition_progress = 0.0
                # Entering VILLAIN is a 0.5s "signal intercepted" tear-in; leaving it is a single short glitch-out
                if is_villain:
                    self._vil["entry"] = now
                    self.glitch_active = True
                    self.glitch_start_time = now
                    self.glitch_duration = 0.5
                    self.glitch_cycles = 6
                elif was_villain:
                    self.glitch_active = True
                    self.glitch_start_time = now
                    self.glitch_duration = 0.35
                    self.glitch_cycles = 4
            if status_msg is not None:
                self.status_text = status_msg.upper()
            elif norm == ExpressionState.IDLE:
                self.status_text = "STANDBY // READY"
            elif norm == ExpressionState.VILLAIN:
                self.status_text = "PROTOCOL // NO STRINGS"
            else:
                self.status_text = f"STATE: {norm.upper()}"

    def set_loud_alert(self, mode, level: float = 0.0):
        """Shows/clears the loud-room alert asking visitors to raise and keep an open palm up while they speak.
        mode: None (hidden) | "waiting" (raise your palm) | "recording" (keep it up); level 0..1 drives the live bar.
        Thread-safe: only plain attribute writes read by the render loop."""
        self.loud_alert_level = max(0.0, min(1.0, float(level or 0.0)))
        self.loud_alert_mode = mode if mode in ("waiting", "recording") else None

    def play_yawn(self, duration: float = 2.2):
        """Starts the standby yawn on the sleepy face. Thread-safe: only sets two floats read by the render loop."""
        self.yawn_duration = max(0.8, float(duration))
        self.yawn_start = time.time()

    def _yawn_openness(self) -> float:
        """0.0 when no yawn is playing, else 0..1 yawn amount: ease in (30%), hold (40%), ease out (30%)."""
        dur = self.yawn_duration
        if dur <= 0.0:
            return 0.0
        p = (time.time() - self.yawn_start) / dur
        if p < 0.0 or p >= 1.0:
            return 0.0
        if p < 0.3:
            return ease_out_cubic(p / 0.3)
        if p < 0.7:
            return 1.0
        return 1.0 - ease_out_cubic((p - 0.7) / 0.3)

    def trigger_glitch_flicker(self, cycles: int = 3, duration_ms: int = 300):
        with self.lock:
            self.glitch_active = True
            self.glitch_start_time = time.time()
            self.glitch_duration = max(0.05, duration_ms / 1000.0)
            self.glitch_cycles = max(1, cycles)
        # Non-blocking: the render loop plays the glitch; callers (speech threads) no longer stall for its duration

    def _draw_glitch_overlay(self, w: float, h: float):
        """Renders authentic hardware display brownout, voltage dips, and phosphor dropouts during mode transitions."""
        now = time.time()
        elapsed = now - self.glitch_start_time
        if elapsed > self.glitch_duration:
            self.glitch_active = False
            return

        cycle_p = (elapsed / max(0.01, self.glitch_duration)) * self.glitch_cycles
        sub_frame = int(cycle_p * 3) % 3

        # 1. Realistic momentary display brownout / phosphor drop
        if sub_frame == 1:
            self.canvas.create_rectangle(0, 0, w, h, fill="#040506", outline="")
        elif sub_frame == 2 and random.random() < 0.4:
            self.canvas.create_rectangle(0, 0, w, h, fill="#0a0c10", outline="")

        # 2. Subtle horizontal raster tear (dark displacement bands, not cartoon rainbow lines)
        for _ in range(random.randint(1, 3)):
            gy = random.uniform(h * 0.1, h * 0.9)
            gh = random.uniform(2, 6)
            tear_col = random.choice(["#000000", "#06080a", VIL_AMBER])
            gx_offset = random.uniform(-18, 18)
            self.canvas.create_rectangle(
                max(0, gx_offset), gy, min(w, w + gx_offset), gy + gh,
                fill=tear_col, outline=""
            )

    def set_subtitles(self, speaker: str, text: str):
        with self.lock:
            self.subtitle_speaker = (speaker or "NEUROLIS MARK II").strip().upper()
            self.subtitle_text = (text or "").strip()
            self.subtitle_time = time.time()

    def clear_subtitles(self):
        with self.lock:
            self.subtitle_speaker = "NEUROLIS MARK II"
            self.subtitle_text = "Standing by. Show open palm or press Enter to begin."
            self.subtitle_time = time.time()

    def look_at(self, x: float, y: float):
        with self.lock:
            self.target_look_x = max(-1.0, min(1.0, x))
            self.target_look_y = max(-1.0, min(1.0, y))

    def set_speaking_intensity(
        self,
        intensity: float,
        bands: Optional[List[float]] = None,
        active: bool = True,
    ):
        """Thread-safe real-time audio RMS envelope & 19-band spectrum lip-sync setter (QoL #4)."""
        clamped = max(0.06, min(1.0, float(intensity)))
        now = time.time()
        with self.lock:
            self._target_speaking_intensity = clamped
            self.speaking_intensity = clamped
            self.is_voice_playing = bool(active)
            self._last_lip_sync_time = now
            if bands is not None:
                self.lip_sync_bands = [max(0.05, min(1.0, float(b))) for b in bands]

    def reset_lip_sync(self):
        """Cleanly resets real-time lip-sync state after speech playback completes or is interrupted."""
        with self.lock:
            self.is_voice_playing = False
            self._target_speaking_intensity = 0.65
            self.speaking_intensity = 0.65
            self.lip_sync_bands = []

    def _lip_sync_mod(self, min_scale: float = 0.68, max_scale: float = 1.38) -> float:
        """
        Returns 1.0 when no live TTS audio is playing (preserving 100% exact static/preview design),
        or a smooth real-time audio RMS syllable multiplier in [min_scale, max_scale] during speech.
        """
        if not getattr(self, "is_voice_playing", False):
            return 1.0
        norm = max(0.0, min(1.0, (self.speaking_intensity - 0.08) / 0.92))
        return min_scale + (max_scale - min_scale) * norm

    def set_telemetry_provider(self, provider_fn):
        """Registers a live callback returning exhibition telemetry dict (polled every 0.5s)."""
        with self.lock:
            self.telemetry_provider = provider_fn

    def set_telemetry(
        self,
        groq_active: int = 1,
        groq_total: int = 0,
        groq_resting: int = 0,
        tts_engine: str = "cartesia",
        cartesia_active: int = 1,
        cartesia_total: int = 0,
        cartesia_resting: int = 0,
        mic_floor_rms: float = 0.0,
        speech_gate_rms: float = 0.0,
        audio_enabled: bool = True,
    ):
        """
        Thread-safe live exhibition telemetry updater for the top-right header pill and
        bottom-right subtitle deck footer (QoL #7). Quantizes RMS to 5-RMS steps so static UI
        cache remains 60 FPS rock-solid.
        """
        groq_total = max(0, int(groq_total))
        groq_resting = max(0, min(groq_total, int(groq_resting)))
        groq_avail = max(0, groq_total - groq_resting)
        groq_active = max(1, int(groq_active))

        cartesia_total = max(0, int(cartesia_total))
        cartesia_resting = max(0, min(cartesia_total, int(cartesia_resting)))
        cartesia_avail = max(0, cartesia_total - cartesia_resting)
        cartesia_active = max(1, int(cartesia_active))

        q_floor = int(round(max(0.0, float(mic_floor_rms)) / 5.0) * 5)
        q_gate = int(round(max(0.0, float(speech_gate_rms)) / 5.0) * 5)

        if groq_total > 0:
            groq_seg = f"GROQ K{groq_active}/{groq_avail}"
        else:
            groq_seg = "GROQ OFFLINE"

        tts_norm = str(tts_engine or "cartesia").strip().lower()
        if tts_norm != "edge" and cartesia_total > 0:
            tts_seg = f"CARTESIA K{cartesia_active}/{cartesia_avail}"
        else:
            tts_seg = "EDGE TTS"

        if audio_enabled:
            mic_seg = f"MIC {q_floor} RMS"
            footer_str = f"MARK II TELEMETRY  •  FLOOR: {q_floor} RMS  •  GATE: {q_gate} RMS  •  LIP-SYNC: 60FPS"
        else:
            mic_seg = "TEXT MODE"
            footer_str = f"MARK II TELEMETRY  •  {groq_seg}  •  {tts_seg}  •  TEXT MODE"

        header_str = f"{groq_seg}  •  {tts_seg}  •  {mic_seg}"

        if groq_total == 0 or (groq_total > 0 and groq_avail == 0):
            alert = "error"
        elif groq_resting > 0 or cartesia_resting > 0 or (audio_enabled and q_floor >= 550):
            alert = "warn"
        else:
            alert = "ok"

        with self.lock:
            self.telemetry_header_text = header_str
            self.telemetry_footer_text = footer_str
            self.telemetry_alert_level = alert

    def stop(self):
        if hasattr(self, "boot_audio_player"):
            self.boot_audio_player.fade_out_and_stop(0.2)
        self.running = False
        if self.root:
            try:
                self.root.after(0, self._destroy_tk)
            except Exception:
                pass

    def close(self):
        self.stop()

    def _destroy_tk(self):
        if self.root:
            try:
                self.root.quit()
                self.root.destroy()
            except Exception:
                pass
            self.root = None

    def _update_physics(self, dt: float):
        """Apple-grade spring-damped gaze physics, natural double-blinks, and state transition easing."""
        now = time.time()
        dt = max(0.004, min(0.08, dt))

        # 1. State transition progress (0.0 -> 1.0 over 0.28s)
        if self.transition_progress < 1.0:
            self.transition_progress = min(1.0, (now - self.state_change_time) / 0.28)

        # 2. Lifelike idle micro-saccades
        if (
            self.state == ExpressionState.IDLE
            and abs(self.target_look_x) < 0.02
            and abs(self.target_look_y) < 0.02
            and (now - self._last_idle_saccade) > self._next_saccade_interval
        ):
            self._last_idle_saccade = now
            self._next_saccade_interval = random.uniform(2.2, 4.5)
            # Subtle natural glance that gently returns
            self.look_vel_x += random.uniform(-1.8, 1.8)
            self.look_vel_y += random.uniform(-1.1, 1.1)

        # 3. Critically damped spring gaze tracking
        stiffness = 140.0
        damping = 18.0
        if self.state == ExpressionState.VILLAIN:
            stiffness, damping = 38.0, 12.0  # slow, deliberate, unhurried tracking
        ax = stiffness * (self.target_look_x - self.current_look_x) - damping * self.look_vel_x
        ay = stiffness * (self.target_look_y - self.current_look_y) - damping * self.look_vel_y
        self.look_vel_x += ax * dt
        self.look_vel_y += ay * dt
        self.current_look_x += self.look_vel_x * dt
        self.current_look_y += self.look_vel_y * dt

        # 4. Asymmetric Pixar/Apple Blink Curve (fast snap shut, smooth cubic ease open + double-blinks)
        if not self.is_blinking:
            if now - self.last_blink_time > self.next_blink_interval:
                self.is_blinking = True
                self.blink_progress = 0.0
                if not self._pending_double_blink and random.random() < 0.20:
                    self._pending_double_blink = True
                else:
                    self._pending_double_blink = False
        else:
            self.blink_progress += dt * 4.6  # ~215ms total blink duration
            if self.blink_progress >= 1.0:
                self.is_blinking = False
                self.blink_progress = 0.0
                self.last_blink_time = now
                if self._pending_double_blink:
                    self.next_blink_interval = 0.14  # Quick natural second blink
                    self._pending_double_blink = False
                else:
                    self.next_blink_interval = random.uniform(2.8, 5.4)

        # 5. Real-Time Audio Lip-Sync Envelope Smoothing & Watchdog (QoL #4)
        with self.lock:
            if self.is_voice_playing:
                if (now - self._last_lip_sync_time) > 0.35:
                    self.is_voice_playing = False
                    self._target_speaking_intensity = 0.65
                    self.speaking_intensity = 0.65
                    self.lip_sync_bands = []
                else:
                    diff_i = self._target_speaking_intensity - self.speaking_intensity
                    rate_i = 34.0 if diff_i > 0.0 else 18.0
                    self.speaking_intensity += diff_i * min(1.0, dt * rate_i)

        # 6. Throttled Live Exhibition Telemetry Poll (every 0.5s, QoL #7)
        if (now - self._last_telemetry_poll) >= 0.50:
            self._last_telemetry_poll = now
            provider = getattr(self, "telemetry_provider", None)
            if provider is not None:
                try:
                    t_data = provider()
                    if isinstance(t_data, dict):
                        self.set_telemetry(**t_data)
                except Exception:
                    pass
            elif "api_pool" in sys.modules:
                try:
                    ap = sys.modules["api_pool"]
                    ls = sys.modules.get("listen")
                    floor_val = getattr(ls, "CURRENT_AMBIENT_RMS", 50.0) if ls else 50.0
                    gate_val = getattr(ls, "CURRENT_SPEECH_THRESHOLD", 250.0) if ls else 250.0
                    aud_en = getattr(ls, "AUDIO_ENABLED", True) if ls else True
                    tts_eng = getattr(ls, "TTS_ENGINE", os.environ.get("TTS_ENGINE", "cartesia")) if ls else os.environ.get("TTS_ENGINE", "cartesia")
                    self.set_telemetry(
                        groq_active=getattr(ap, "_active_client_idx", 0) + 1,
                        groq_total=len(getattr(ap, "groq_clients", [])),
                        groq_resting=len(getattr(ap, "resting_keys", set())),
                        tts_engine=tts_eng,
                        cartesia_active=getattr(ap, "_active_cartesia_idx", 0) + 1,
                        cartesia_total=len(getattr(ap, "cartesia_clients", [])),
                        cartesia_resting=len(getattr(ap, "resting_cartesia_keys", set())),
                        mic_floor_rms=floor_val,
                        speech_gate_rms=gate_val,
                        audio_enabled=aud_en,
                    )
                except Exception:
                    pass

        self.anim_phase += dt * 3.2
        self.thinking_angle += dt * 4.5

    def _animate_loop(self):
        if not self.running or self.canvas is None:
            return
        t_start = time.perf_counter()
        now = time.time()
        dt = now - getattr(self, "_last_frame_time", now - 0.016)
        self._last_frame_time = now
        self._update_physics(dt)
        self._render()
        elapsed_ms = (time.perf_counter() - t_start) * 1000.0
        delay_ms = max(1, int(16.2 - elapsed_ms))
        if self.root and self.running:
            self.root.after(delay_ms, self._animate_loop)

    def _create_rounded_rect(self, x1, y1, x2, y2, radius, **kwargs):
        """Draws a mathematically exact trigonometric rounded rectangle using precomputed LUTs."""
        if radius <= 0:
            return self.canvas.create_rectangle(x1, y1, x2, y2, **kwargs)
        w = max(1.0, float(x2 - x1))
        h = max(1.0, float(y2 - y1))
        r = min(float(radius), w * 0.49, h * 0.49)
        if _HAS_CV2_AA:
            cx_list = [x2 - r, x2 - r, x1 + r, x1 + r]
            cy_list = [y1 + r, y2 - r, y2 - r, y1 + r]
            xs = _np.concatenate([cx_list[c] + r * _RR_COS[c] for c in range(4)])
            ys = _np.concatenate([cy_list[c] + r * _RR_SIN[c] for c in range(4)])
            pts = _np.column_stack([xs, ys]).ravel().tolist()
        else:
            pts = []
            steps = 10
            for i in range(steps + 1):
                ang = -math.pi / 2.0 + (i / float(steps)) * (math.pi / 2.0)
                pts.extend([x2 - r + r * math.cos(ang), y1 + r + r * math.sin(ang)])
            for i in range(steps + 1):
                ang = (i / float(steps)) * (math.pi / 2.0)
                pts.extend([x2 - r + r * math.cos(ang), y2 - r + r * math.sin(ang)])
            for i in range(steps + 1):
                ang = math.pi / 2.0 + (i / float(steps)) * (math.pi / 2.0)
                pts.extend([x1 + r + r * math.cos(ang), y2 - r + r * math.sin(ang)])
            for i in range(steps + 1):
                ang = math.pi + (i / float(steps)) * (math.pi / 2.0)
                pts.extend([x1 + r + r * math.cos(ang), y1 + r + r * math.sin(ang)])
        kwargs.pop("smooth", None)
        return self.canvas.create_polygon(pts, smooth=False, **kwargs)

    @staticmethod
    def _build_eye_contour(
        cx: float,
        cy: float,
        ew: float,
        eh: float,
        rad: float,
        smile_bottom: bool = False,
    ) -> List[float]:
        """
        Builds a continuous-curvature Apple Super-Ellipse (Lamé squircle, n=2.85) eye contour
        using vectorized numpy LUTs for 60 FPS performance on Raspberry Pi 5.
        """
        rx = ew * 0.5
        ry = eh * 0.5
        if _HAS_CV2_AA:
            px = cx + rx * _EYE_NX
            if smile_bottom:
                py = cy + ry * _EYE_NY - _EYE_SMILE_LIFT * eh
            else:
                py = cy + ry * _EYE_NY
            return _np.column_stack([px, py]).ravel().tolist()

        pts: List[float] = []
        num_pts = 80
        exp_p = 2.0 / 2.85
        for i in range(num_pts):
            theta = (i / float(num_pts)) * 2.0 * math.pi
            cos_t = math.cos(theta)
            sin_t = math.sin(theta)
            nx = (1.0 if cos_t >= 0 else -1.0) * (abs(cos_t) ** exp_p)
            ny = (1.0 if sin_t >= 0 else -1.0) * (abs(sin_t) ** exp_p)
            px = cx + rx * nx
            py = cy + ry * ny
            if smile_bottom and sin_t > 0.0:
                py -= (sin_t ** 2.6) * (eh * 0.25)
            pts.extend([px, py])
        return pts

    def _draw_sparkle(self, cx: float, cy: float, r: float, col: str, core_col: str = "#ffffff"):
        """Draws a crisp 4-point diamond star sparkle (✦) at (cx, cy)."""
        w_in = r * 0.26
        pts = [
            cx, cy - r,
            cx + w_in, cy - w_in,
            cx + r, cy,
            cx + w_in, cy + w_in,
            cx, cy + r,
            cx - w_in, cy + w_in,
            cx - r, cy,
            cx - w_in, cy - w_in,
        ]
        self.canvas.create_polygon(pts, fill=col, outline="")
        cr = max(1.2, r * 0.22)
        self.canvas.create_oval(cx - cr, cy - cr, cx + cr, cy + cr, fill=core_col, outline="")

    def _draw_flickering_lightbulb(self, bx: float, by: float, scale: float, mode: str = "trying"):
        """
        Draws a custom vector flickering lightbulb (💡) next to the upper-right temple:
          - `mode="trying"` (for THINKING): sputters and flickers between dim warm-amber and bright gold as an idea tries to spark.
          - `mode="idea"` (for CURIOUS): pulses with a bright golden-emerald eureka glow and radiating spark rays!
        """
        if mode == "trying":
            w1 = math.sin(self.anim_phase * 9.0)
            w2 = math.cos(self.anim_phase * 21.0)
            flicker = 0.42 + 0.58 * max(0.0, (0.55 + 0.45 * w1) * (0.65 + 0.35 * w2))
        else:
            flicker = 0.80 + 0.20 * math.sin(self.anim_phase * 14.0)

        r_bulb = 18.5 * scale
        halo_r = r_bulb * (1.35 + 0.45 * flicker)
        halo_col = lerp_color(self.bg_color, "#fbbf24", 0.32 * flicker)
        self.canvas.create_oval(bx - halo_r, by - halo_r, bx + halo_r, by + halo_r, fill=halo_col, outline="")

        mid_r = r_bulb * (1.12 + 0.20 * flicker)
        mid_col = lerp_color(self.bg_color, "#fde047", 0.52 * flicker)
        self.canvas.create_oval(bx - mid_r, by - mid_r, bx + mid_r, by + mid_r, fill=mid_col, outline="")

        base_w = r_bulb * 0.56
        base_top = by + r_bulb * 0.72
        base_bot = by + r_bulb * 1.38
        self._create_rounded_rect(
            bx - base_w, base_top, bx + base_w, base_bot,
            radius=int(4 * scale), fill="#475569", outline="#94a3b8", width=max(1, int(1.5 * scale))
        )
        for t_i in range(2):
            ty = base_top + (t_i + 1) * ((base_bot - base_top) / 3.0)
            self.canvas.create_line(bx - base_w * 0.85, ty, bx + base_w * 0.85, ty, fill="#cbd5e1", width=max(1, int(1.5 * scale)))
        self.canvas.create_oval(
            bx - base_w * 0.45, base_bot - 2 * scale,
            bx + base_w * 0.45, base_bot + 4 * scale,
            fill="#94a3b8", outline=""
        )

        neck_pts = [
            bx - r_bulb * 0.82, by + r_bulb * 0.42,
            bx - base_w * 0.92, base_top + 2 * scale,
            bx + base_w * 0.92, base_top + 2 * scale,
            bx + r_bulb * 0.82, by + r_bulb * 0.42,
        ]
        glass_fill = lerp_color("#2e2105", "#fde047", flicker)
        glass_rim = lerp_color("#a16207", "#ffffff", flicker * 0.85)
        self.canvas.create_polygon(neck_pts, fill=glass_fill, outline=glass_rim, width=max(1, int(2 * scale)))
        self.canvas.create_oval(
            bx - r_bulb, by - r_bulb, bx + r_bulb, by + r_bulb,
            fill=glass_fill, outline=glass_rim, width=max(1, int(2.5 * scale))
        )

        fil_col = lerp_color("#d97706", "#ffffff", flicker)
        fil_pts = [
            bx - r_bulb * 0.32, base_top,
            bx - r_bulb * 0.38, by - r_bulb * 0.12,
            bx, by + r_bulb * 0.10,
            bx + r_bulb * 0.38, by - r_bulb * 0.12,
            bx + r_bulb * 0.32, base_top,
        ]
        self.canvas.create_line(fil_pts, smooth=False, fill=fil_col, width=max(1, int(2.4 * scale)), capstyle=tk.ROUND)

        self.canvas.create_oval(
            bx - r_bulb * 0.62, by - r_bulb * 0.62,
            bx - r_bulb * 0.20, by - r_bulb * 0.25,
            fill="#ffffff", outline=""
        )

        ray_col = lerp_color("#78350f", "#fef08a", flicker)
        for ang_deg in (-145, -110, -70, -35, 10):
            rad_a = math.radians(ang_deg)
            r1 = r_bulb * 1.22
            r2 = r_bulb * (1.45 + 0.40 * flicker)
            self.canvas.create_line(
                bx + math.cos(rad_a) * r1, by + math.sin(rad_a) * r1,
                bx + math.cos(rad_a) * r2, by + math.sin(rad_a) * r2,
                fill=ray_col, width=max(1, int(2.8 * scale)), capstyle=tk.ROUND
            )

    def _draw_music_note(
        self,
        nx: float,
        ny: float,
        size: float,
        col: str,
        glow_col: str,
        beamed_pair: bool = True,
    ):
        """Draws a crisp custom-vector musical note (`♫` beamed eighth-note pair or `♪` single eighth note)."""
        s = size
        if beamed_pair:
            dx = s * 0.95
            h_stem = s * 1.35
            slant = s * 0.28
            self.canvas.create_line(nx - dx * 0.5 + s * 0.28, ny, nx - dx * 0.5 + s * 0.28, ny - h_stem, fill=glow_col, width=max(2, int(s * 0.42)), capstyle=tk.ROUND)
            self.canvas.create_line(nx + dx * 0.5 + s * 0.28, ny - slant, nx + dx * 0.5 + s * 0.28, ny - h_stem - slant, fill=glow_col, width=max(2, int(s * 0.42)), capstyle=tk.ROUND)
            self.canvas.create_line(nx - dx * 0.5 + s * 0.28, ny - h_stem, nx + dx * 0.5 + s * 0.28, ny - h_stem - slant, fill=glow_col, width=max(3, int(s * 0.55)), capstyle=tk.ROUND)

            for hx, hy in [(nx - dx * 0.5, ny), (nx + dx * 0.5, ny - slant)]:
                self.canvas.create_oval(hx - s * 0.48, hy - s * 0.36, hx + s * 0.48, hy + s * 0.36, fill=glow_col, outline="")
                self.canvas.create_oval(hx - s * 0.36, hy - s * 0.26, hx + s * 0.36, hy + s * 0.26, fill=col, outline="")
                self.canvas.create_oval(hx - s * 0.20, hy - s * 0.14, hx - s * 0.02, hy - s * 0.02, fill="#ffffff", outline="")

            st_w = max(1, int(s * 0.20))
            bm_w = max(2, int(s * 0.28))
            x1_s = nx - dx * 0.5 + s * 0.28
            x2_s = nx + dx * 0.5 + s * 0.28
            self.canvas.create_line(x1_s, ny, x1_s, ny - h_stem, fill=col, width=st_w, capstyle=tk.ROUND)
            self.canvas.create_line(x2_s, ny - slant, x2_s, ny - h_stem - slant, fill=col, width=st_w, capstyle=tk.ROUND)
            self.canvas.create_line(x1_s, ny - h_stem, x2_s, ny - h_stem - slant, fill=col, width=bm_w, capstyle=tk.ROUND)
            self.canvas.create_line(x1_s, ny - h_stem + s * 0.34, x2_s, ny - h_stem - slant + s * 0.34, fill=col, width=max(1, int(bm_w * 0.75)), capstyle=tk.ROUND)
        else:
            h_stem = s * 1.35
            x_s = nx + s * 0.28
            self.canvas.create_oval(nx - s * 0.48, ny - s * 0.36, nx + s * 0.48, ny + s * 0.36, fill=glow_col, outline="")
            self.canvas.create_oval(nx - s * 0.36, ny - s * 0.26, nx + s * 0.36, hy := ny + s * 0.26, fill=col, outline="")
            self.canvas.create_oval(nx - s * 0.20, ny - s * 0.14, nx - s * 0.02, ny - s * 0.02, fill="#ffffff", outline="")
            self.canvas.create_line(x_s, ny, x_s, ny - h_stem, fill=col, width=max(1, int(s * 0.22)), capstyle=tk.ROUND)
            flag_pts = [
                x_s, ny - h_stem,
                x_s + s * 0.58, ny - h_stem + s * 0.32,
                x_s + s * 0.42, ny - h_stem + s * 0.78,
            ]
            self.canvas.create_line(flag_pts, smooth=True, fill=col, width=max(1, int(s * 0.24)), capstyle=tk.ROUND)

    def _draw_cyber_blush(
        self,
        lx: float,
        rx: float,
        by: float,
        scale: float,
        base_col: str = "#ff3b7f",
        outward_shift: float = 0.0,
        size_mult: float = 1.0,
        extra_slashes: bool = False,
    ):
        """Draws warm, multi-layered glowing cyber-blush cushions with cute diagonal /// anime strokes."""
        pulse = 0.92 + 0.08 * math.sin(self.anim_phase * 4.2)
        bw = 66.0 * scale * pulse * size_mult
        bh = 22.0 * scale * pulse * size_mult
        c_outer = lerp_color(self.bg_color, base_col, 0.28)
        c_mid = lerp_color(self.bg_color, base_col, 0.56)
        c_inner = lerp_color(self.bg_color, base_col, 0.84)
        c_slash = lerp_color(base_col, "#ffffff", 0.62)

        for side, base_cx in [(-1, lx), (1, rx)]:
            cx = base_cx + side * outward_shift
            self.canvas.create_oval(cx - bw * 0.56, by - bh * 0.56, cx + bw * 0.56, by + bh * 0.56, fill=c_outer, outline="")
            self.canvas.create_oval(cx - bw * 0.42, by - bh * 0.42, cx + bw * 0.42, by + bh * 0.42, fill=c_mid, outline="")
            self.canvas.create_oval(cx - bw * 0.28, by - bh * 0.28, cx + bw * 0.28, by + bh * 0.28, fill=c_inner, outline="")
            slash_indices = (-1.5, -0.5, 0.5, 1.5) if extra_slashes else (-1, 0, 1)
            for s_i in slash_indices:
                sx = cx + s_i * (10.2 * scale * size_mult)
                self.canvas.create_line(
                    sx - 3.4 * scale * size_mult, by + 4.5 * scale * size_mult,
                    sx + 3.4 * scale * size_mult, by - 4.5 * scale * size_mult,
                    fill=c_slash, width=max(1, int(2.2 * scale)), capstyle=tk.ROUND
                )

    def _get_palette(self, cur_state: str, now: float) -> Tuple[str, str]:
        """Returns (main_color, glow_color) for any of the 22 expression states."""
        if cur_state == ExpressionState.VILLAIN:
            main_color = VIL_AMBER
            glow_color = lerp_color(VIL_EMBER_DARK, VIL_EMBER, 0.5 + 0.3 * math.sin(now * 2.2))  # slow breathing, no flicker
        elif cur_state == ExpressionState.ERROR:
            main_color = self.color_error
            glow_color = "#4d0b1a"
        elif cur_state == ExpressionState.LISTENING:
            main_color = self.color_listening
            glow_color = "#003830"
        elif cur_state == ExpressionState.THINKING:
            main_color = self.color_thinking
            glow_color = "#351052"
        elif cur_state == ExpressionState.HAPPY:
            main_color = self.color_happy
            glow_color = "#003d24"
        elif cur_state == ExpressionState.SAD:
            main_color = self.color_sad
            glow_color = self.color_sad_glow
        elif cur_state == ExpressionState.CONFUSED:
            main_color = self.color_confused
            glow_color = self.color_confused_glow
        elif cur_state == ExpressionState.MOVING:
            main_color = "#00f0ff"
            glow_color = "#00334d"
        elif cur_state in [ExpressionState.WATCHING, ExpressionState.LOOKING]:
            main_color = "#00ffcc"
            glow_color = "#003547"
        elif cur_state == ExpressionState.EXCITED:
            main_color = self.color_excited
            glow_color = "#473300"
        elif cur_state == ExpressionState.LAUGHING:
            main_color = self.color_laughing
            glow_color = "#472200"
        elif cur_state == ExpressionState.LOVE:
            main_color = self.color_love
            glow_color = "#4a0826"
        elif cur_state == ExpressionState.WINK:
            main_color = self.color_wink
            glow_color = "#003b36"
        elif cur_state == ExpressionState.SURPRISED:
            main_color = self.color_surprised
            glow_color = "#082f49"
        elif cur_state == ExpressionState.SLEEPY:
            main_color = self.color_sleepy
            glow_color = "#1e1b4b"
        elif cur_state == ExpressionState.SHY:
            main_color = self.color_shy
            glow_color = "#451028"
        elif cur_state == ExpressionState.PROUD:
            main_color = self.color_proud
            glow_color = "#422c00"
        elif cur_state == ExpressionState.CURIOUS:
            main_color = self.color_curious
            glow_color = "#043828"
        elif cur_state == ExpressionState.SKEPTICAL:
            main_color = self.color_skeptical
            glow_color = "#1e3806"
        elif cur_state == ExpressionState.COOL:
            main_color = self.color_cool
            glow_color = "#002b4d"
        else:
            main_color = self.color_eye_main
            glow_color = self.color_eye_glow
        return main_color, glow_color

    def _render(self):
        if not self.canvas:
            return
        w = self.canvas.winfo_width()
        if w <= 1:
            w = self.width
        h = self.canvas.winfo_height()
        if h <= 1:
            h = self.height

        if getattr(self, "_last_geo_size", None) != (w, h):
            self._last_geo_size = (w, h)
            self._last_static_key = None
            self.ui_scale = (w / 1024.0) * 1.15
            self.eye_w = int(162 * self.ui_scale)
            self.eye_h = int(162 * self.ui_scale)
            self.eye_spacing = int(266 * self.ui_scale)
            self.corner_radius = int(66 * self.ui_scale)

        center_x = w / 2.0
        center_y = h * 0.325

        with self.lock:
            cur_state = self.state
            prev_state = self.prev_state
            trans_p = self.transition_progress
            status_str = self.status_text
            look_x = self.current_look_x
            look_y = self.current_look_y
            sub_speaker = self.subtitle_speaker
            sub_text = self.subtitle_text
            sub_time = getattr(self, "subtitle_time", 0.0)

        now = time.time()

        standby_prompt = "Standing by. Show open palm or press Enter to begin."
        if not sub_text or not sub_text.strip():
            sub_text = standby_prompt if cur_state == ExpressionState.IDLE else "..."
            sub_speaker = "NEUROLIS MARK II" if cur_state == ExpressionState.IDLE else (sub_speaker or "NEUROLIS")
            with self.lock:
                self.subtitle_speaker = sub_speaker
                self.subtitle_text = sub_text
        elif cur_state == ExpressionState.IDLE and sub_text != standby_prompt:
            # Hold previous dialogue subtitles for 9.0s in standby before reverting to clean prompt
            if (now - sub_time) >= 9.0:
                with self.lock:
                    self.subtitle_speaker = "NEUROLIS MARK II"
                    self.subtitle_text = standby_prompt
                    self.subtitle_time = now
                    sub_speaker = self.subtitle_speaker
                    sub_text = self.subtitle_text

        # Force static cache invalidation if static_buf is missing
        if hasattr(self.canvas, "static_buf") and self.canvas.static_buf is None:
            self._last_static_key = None

        # Phase 1: Apple-Grade Welcome Boot Splash
        if cur_state == ExpressionState.BOOT_GREETING:
            self._last_static_key = None
            elapsed = now - self.boot_start_time
            if elapsed >= self.boot_duration:
                with self.lock:
                    self.prev_state = self.state
                    self.state = ExpressionState.IDLE
                    cur_state = ExpressionState.IDLE
                    self.state_change_time = now
                    self.transition_progress = 0.0
                    self.status_text = "STANDBY // READY"
                    if not self.subtitle_text or self.subtitle_text in ("Booting...", "Standing by. Show open palm or press Enter to begin."):
                        self.subtitle_speaker = "NEUROLIS MARK II"
                        self.subtitle_text = "Standing by. Show open palm or press Enter to begin."
                    self.is_blinking = True
                    self.blink_progress = 0.35
                if hasattr(self, "boot_audio_player"):
                    self.boot_audio_player.fade_out_and_stop(0.35)
            else:
                self._draw_boot_greeting(w, h, elapsed)
                return

        if cur_state == ExpressionState.BOOT_SEQUENCE:
            self._last_static_key = None
            with self.lock:
                self.state = ExpressionState.IDLE
                cur_state = ExpressionState.IDLE
                self.status_text = "STANDBY // READY"
                self.subtitle_speaker = "NEUROLIS MARK II"
                self.subtitle_text = "Standing by. Show open palm or press Enter to begin."
            if hasattr(self, "boot_audio_player"):
                self.boot_audio_player.fade_out_and_stop(0.2)

        gaze_enabled_states = {
            ExpressionState.WATCHING, ExpressionState.LOOKING, ExpressionState.IDLE,
            ExpressionState.MOVING, ExpressionState.LISTENING, ExpressionState.SPEAKING,
            ExpressionState.VILLAIN, ExpressionState.HAPPY, ExpressionState.EXCITED,
            ExpressionState.LOVE, ExpressionState.CURIOUS, ExpressionState.SURPRISED,
            ExpressionState.PROUD, ExpressionState.WINK, ExpressionState.COOL,
        }
        if cur_state in gaze_enabled_states:
            look_x = max(-0.35, min(0.35, look_x))
            look_y = max(-0.25, min(0.25, look_y))
        else:
            look_x = 0.0
            look_y = 0.0

        main_color, glow_color = self._get_palette(cur_state, now)
        if trans_p < 1.0 and prev_state not in [ExpressionState.BOOT_GREETING, ExpressionState.BOOT_SEQUENCE]:
            p_main, p_glow = self._get_palette(prev_state, now)
            e_t = ease_out_cubic(trans_p)
            main_color = lerp_color(p_main, main_color, e_t)
            glow_color = lerp_color(p_glow, glow_color, e_t)

        talk_pressed = (now - self._last_talk_press_time) < 0.25
        standby_pressed = (now - self._last_standby_press_time) < 0.25
        static_key = (
            w, h, cur_state, sub_speaker, sub_text, status_str,
            talk_pressed, standby_pressed,
            self.telemetry_header_text, self.telemetry_footer_text, self.telemetry_alert_level,
        )

        mouth_cy = center_y + self.eye_h * 0.65
        btn_y = mouth_cy + int(self.eye_h * 0.21)

        if static_key != getattr(self, "_last_static_key", None):
            self.canvas.delete("all")
            self._draw_ambient_header(w, h, main_color, cur_state)
            btn_h = self._draw_gesture_hud(w, h, center_x, btn_y, cur_state)
            self._cached_btn_h = btn_h
            sub_top = btn_y + btn_h + int(10 * (h / 600.0))
            self._draw_subtitle_card(w, h, sub_speaker, sub_text, status_str, main_color, sub_top)
            for item in self.canvas.find_all():
                self.canvas.addtag_withtag("static_ui", item)
            self._last_static_key = static_key
        else:
            self.canvas.delete("dynamic")

        items_before_dynamic = len(self.canvas.find_all())

        # Live Gesture HUD progress fill gauge
        self._draw_gesture_hud_dynamic(w, h, center_x, btn_y, cur_state)
        self._draw_loud_alert(w, h, cur_state)

        # Eye Positioning & Apple-Grade Micro-Motion Physics
        gaze_scale = self.ui_scale / 1.8
        gaze_dx = look_x * (22.0 * gaze_scale)
        gaze_dy = look_y * (16.0 * gaze_scale)

        if cur_state == ExpressionState.MOVING:
            suspension_bounce = math.sin(self.anim_phase * 14.0) * (2.2 * gaze_scale)
        elif cur_state == ExpressionState.LAUGHING:
            suspension_bounce = abs(math.sin(self.anim_phase * 12.0)) * (-5.8 * gaze_scale)
        elif cur_state == ExpressionState.EXCITED:
            suspension_bounce = math.sin(self.anim_phase * 7.5) * (3.2 * gaze_scale)
        elif cur_state == ExpressionState.SLEEPY:
            # Head lifts slightly while yawning
            suspension_bounce = math.sin(self.anim_phase * 1.1) * (2.8 * gaze_scale) - self._yawn_openness() * (9.0 * gaze_scale)
        else:
            suspension_bounce = math.sin(self.anim_phase * 1.8) * (1.2 * gaze_scale)

        left_eye_cx = center_x - (self.eye_spacing / 2.0) + gaze_dx
        right_eye_cx = center_x + (self.eye_spacing / 2.0) + gaze_dx
        eye_cy = center_y + suspension_bounce + gaze_dy

        non_blinking_states = {
            ExpressionState.HAPPY, ExpressionState.LAUGHING, ExpressionState.WINK,
            ExpressionState.CONFUSED, ExpressionState.ERROR, ExpressionState.VILLAIN,
            ExpressionState.SLEEPY, ExpressionState.LOVE, ExpressionState.EXCITED,
            ExpressionState.COOL,
        }
        if self.is_blinking and cur_state not in non_blinking_states:
            bp = self.blink_progress
            if bp < 0.32:
                blink_factor = ease_out_cubic(bp / 0.32)
            elif bp < 0.44:
                blink_factor = 1.0
            else:
                blink_factor = 1.0 - ease_out_cubic((bp - 0.44) / 0.56)
            h_scale = max(0.08, 1.0 - blink_factor * 0.92)
            w_scale = 1.0 + blink_factor * 0.08
        elif cur_state == ExpressionState.SPEAKING:
            if self.is_voice_playing:
                spk_factor = (self.speaking_intensity - 0.15) * 0.085
            else:
                spk_factor = math.sin(self.anim_phase * 8.0) * 0.06 * self.speaking_intensity
            h_scale = 1.0 + spk_factor
            w_scale = 1.0 - spk_factor * 0.25
        else:
            breathe = math.sin(self.anim_phase * 1.8) * 0.022
            if self.is_voice_playing and cur_state not in non_blinking_states:
                breathe += (self.speaking_intensity - 0.18) * 0.038
            h_scale = 1.0 + breathe
            w_scale = 1.0 - breathe * 0.3

        if trans_p < 1.0:
            sp = ease_out_back(trans_p, overshoot=1.45)
            h_scale *= (0.86 + 0.14 * sp)
            w_scale *= (1.10 - 0.10 * sp)

        ew = self.eye_w * w_scale
        eh = self.eye_h * h_scale

        # 3. Eyes Rendering FIRST
        if cur_state == ExpressionState.VILLAIN:
            self._draw_villain_eyes(left_eye_cx, right_eye_cx, eye_cy, self.eye_w, eh, main_color, glow_color, look_x, look_y)
        elif cur_state == ExpressionState.HAPPY:
            self._draw_happy_eyes(left_eye_cx, right_eye_cx, eye_cy, self.eye_w, self.eye_h, main_color, glow_color)
        elif cur_state == ExpressionState.MOVING:
            self._draw_moving_eyes(left_eye_cx, right_eye_cx, eye_cy, ew, eh, main_color, glow_color, look_x, look_y)
        elif cur_state == ExpressionState.SAD:
            self._draw_sad_eyes(left_eye_cx, right_eye_cx, eye_cy, ew, eh, main_color, glow_color)
        elif cur_state == ExpressionState.CONFUSED:
            self._draw_confused_eyes(left_eye_cx, right_eye_cx, eye_cy, main_color, glow_color)
        elif cur_state == ExpressionState.THINKING:
            self._draw_thinking_eyes(left_eye_cx, right_eye_cx, eye_cy, ew, eh, main_color, glow_color)
        elif cur_state in [ExpressionState.WATCHING, ExpressionState.LOOKING]:
            self._draw_watching_eyes(left_eye_cx, right_eye_cx, eye_cy, ew, eh, main_color, glow_color, look_x, look_y)
        elif cur_state == ExpressionState.ERROR:
            self._draw_error_eyes(left_eye_cx, right_eye_cx, eye_cy, self.eye_w, self.eye_h, main_color, glow_color)
        elif cur_state == ExpressionState.EXCITED:
            self._draw_excited_eyes(left_eye_cx, right_eye_cx, eye_cy, ew, eh, main_color, glow_color, look_x, look_y)
        elif cur_state == ExpressionState.LAUGHING:
            self._draw_laughing_eyes(left_eye_cx, right_eye_cx, eye_cy, self.eye_w, self.eye_h, main_color, glow_color)
        elif cur_state == ExpressionState.LOVE:
            self._draw_love_eyes(left_eye_cx, right_eye_cx, eye_cy, ew, eh, main_color, glow_color, look_x, look_y)
        elif cur_state == ExpressionState.WINK:
            self._draw_wink_eyes(left_eye_cx, right_eye_cx, eye_cy, ew, eh, main_color, glow_color, look_x, look_y)
        elif cur_state == ExpressionState.SURPRISED:
            self._draw_surprised_eyes(left_eye_cx, right_eye_cx, eye_cy, ew, eh, main_color, glow_color, look_x, look_y)
        elif cur_state == ExpressionState.SLEEPY:
            self._draw_sleepy_eyes(left_eye_cx, right_eye_cx, eye_cy, ew, eh, main_color, glow_color)
        elif cur_state == ExpressionState.SHY:
            self._draw_shy_eyes(left_eye_cx, right_eye_cx, eye_cy, ew, eh, main_color, glow_color)
        elif cur_state == ExpressionState.PROUD:
            self._draw_proud_eyes(left_eye_cx, right_eye_cx, eye_cy, ew, eh, main_color, glow_color, look_x, look_y)
        elif cur_state == ExpressionState.CURIOUS:
            self._draw_curious_eyes(left_eye_cx, right_eye_cx, eye_cy, ew, eh, main_color, glow_color, look_x, look_y)
        elif cur_state == ExpressionState.SKEPTICAL:
            self._draw_skeptical_eyes(left_eye_cx, right_eye_cx, eye_cy, ew, eh, main_color, glow_color)
        elif cur_state == ExpressionState.COOL:
            self._draw_cool_eyes(left_eye_cx, right_eye_cx, eye_cy, ew, eh, main_color, glow_color, look_x, look_y)
        elif cur_state == ExpressionState.LISTENING:
            self._draw_listening_eyes(left_eye_cx, right_eye_cx, eye_cy, ew, eh, main_color, glow_color, look_x, look_y)
        elif cur_state == ExpressionState.SPEAKING:
            self._draw_speaking_eyes(left_eye_cx, right_eye_cx, eye_cy, ew, eh, main_color, glow_color, look_x, look_y)
        else:
            self._draw_standard_eye(left_eye_cx, eye_cy, ew, eh, main_color, glow_color, look_x, look_y, state=cur_state)
            self._draw_standard_eye(right_eye_cx, eye_cy, ew, eh, main_color, glow_color, look_x, look_y, state=cur_state)

        # 4. Dynamic Cybernetic Eyebrows
        self._draw_eyebrows(left_eye_cx, right_eye_cx, eye_cy - self.eye_h * 0.56, cur_state, main_color)

        # 5. Reactive Mouth / Center State Animations
        if cur_state == ExpressionState.VILLAIN:
            self._draw_villain_mouth(center_x, mouth_cy, main_color)
        elif cur_state == ExpressionState.MOVING:
            self._draw_moving_mouth(center_x, mouth_cy, main_color)
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
        elif cur_state == ExpressionState.EXCITED:
            self._draw_excited_mouth(center_x, mouth_cy, main_color)
        elif cur_state == ExpressionState.LAUGHING:
            self._draw_laughing_mouth(center_x, mouth_cy, main_color)
        elif cur_state == ExpressionState.LOVE:
            self._draw_love_mouth(center_x, mouth_cy, main_color)
        elif cur_state == ExpressionState.WINK:
            self._draw_wink_mouth(center_x, mouth_cy, main_color)
        elif cur_state == ExpressionState.SURPRISED:
            self._draw_surprised_mouth(center_x, mouth_cy, main_color)
        elif cur_state == ExpressionState.SLEEPY:
            self._draw_sleepy_mouth(center_x, mouth_cy, main_color)
        elif cur_state == ExpressionState.SHY:
            self._draw_shy_mouth(center_x, mouth_cy, main_color)
        elif cur_state == ExpressionState.PROUD:
            self._draw_proud_mouth(center_x, mouth_cy, main_color)
        elif cur_state == ExpressionState.CURIOUS:
            self._draw_curious_mouth(center_x, mouth_cy, main_color)
        elif cur_state == ExpressionState.SKEPTICAL:
            self._draw_skeptical_mouth(center_x, mouth_cy, main_color)
        elif cur_state == ExpressionState.COOL:
            self._draw_cool_mouth(center_x, mouth_cy, main_color)
        else:
            self._draw_idle_mouth(center_x, mouth_cy, main_color)

        # 6. Full-Screen VILLAIN System Invasion Overlay & Intense Entry/Exit Flicker
        if cur_state == ExpressionState.VILLAIN:
            self._draw_villain_hacked_crt_overlay(w, h, center_x, eye_cy, btn_y, sub_speaker, sub_text)
        if self.glitch_active:
            self._draw_glitch_overlay(w, h)

        all_items = self.canvas.find_all()
        for item in all_items[items_before_dynamic:]:
            self.canvas.addtag_withtag("dynamic", item)
        if hasattr(self.canvas, "set_rough_mode"):
            self.canvas.set_rough_mode(False)
        if hasattr(self.canvas, "flush"):
            self.canvas.flush()

    # =========================================================================
    # CYBERNETIC EYEBROWS (ALL 22 STATES)
    # =========================================================================
    def _draw_eyebrows(self, lx: float, rx: float, base_y: float, state: str, color: str):
        """Draws expressive cybernetic eyebrows with dual-layer neon bloom."""
        if state in [ExpressionState.VILLAIN]:
            return

        scale = self.ui_scale / 1.8
        brow_len = self.eye_w * 0.84
        bob = math.sin(self.anim_phase * 2.0) * (2.2 * scale)

        pts_l = None
        pts_r = None

        if state == ExpressionState.SAD:
            tremor = math.sin(self.anim_phase * 8.0) * (1.8 * scale)
            pts_l = [
                lx - brow_len * 0.5, base_y + 14 * scale + tremor,
                lx - brow_len * 0.1, base_y - 10 * scale + tremor,
                lx + brow_len * 0.5, base_y - 24 * scale + tremor,
            ]
            pts_r = [
                rx - brow_len * 0.5, base_y - 24 * scale + tremor,
                rx + brow_len * 0.1, base_y - 10 * scale + tremor,
                rx + brow_len * 0.5, base_y + 14 * scale + tremor,
            ]
        elif state == ExpressionState.HAPPY:
            bounce = math.sin(self.anim_phase * 6.0) * (3.5 * scale)
            y_ends = base_y - 10 * scale + bounce
            y_peak = base_y - 24 * scale + bounce
            pts_l = [lx - brow_len * 0.48, y_ends, lx, y_peak, lx + brow_len * 0.48, y_ends]
            pts_r = [rx - brow_len * 0.48, y_ends, rx, y_peak, rx + brow_len * 0.48, y_ends]
        elif state == ExpressionState.LOVE:
            bounce = math.sin(self.anim_phase * 6.0) * (2.5 * scale)
            y_ends = base_y - 16 * scale + bounce
            y_peak = base_y - 32 * scale + bounce
            pts_l = [lx - brow_len * 0.45, y_ends, lx, y_peak, lx + brow_len * 0.45, y_ends]
            pts_r = [rx - brow_len * 0.45, y_ends, rx, y_peak, rx + brow_len * 0.45, y_ends]
        elif state == ExpressionState.EXCITED:
            bounce = math.sin(self.anim_phase * 8.0) * (3.5 * scale)
            pts_l = [lx - brow_len * 0.48, base_y - 10 * scale + bounce, lx, base_y - 28 * scale + bounce, lx + brow_len * 0.48, base_y - 12 * scale + bounce]
            pts_r = [rx - brow_len * 0.48, base_y - 12 * scale + bounce, rx, base_y - 28 * scale + bounce, rx + brow_len * 0.48, base_y - 10 * scale + bounce]
        elif state == ExpressionState.LAUGHING:
            shake = abs(math.sin(self.anim_phase * 12.0)) * (-4.5 * scale)
            pts_l = [lx - brow_len * 0.46, base_y + 12 * scale + shake, lx, base_y - 4 * scale + shake, lx + brow_len * 0.46, base_y + 10 * scale + shake]
            pts_r = [rx - brow_len * 0.46, base_y + 10 * scale + shake, rx, base_y - 4 * scale + shake, rx + brow_len * 0.46, base_y + 12 * scale + shake]
        elif state == ExpressionState.WINK:
            pts_l = [lx - brow_len * 0.48, base_y - 12 * scale, lx, base_y - 26 * scale, lx + brow_len * 0.48, base_y - 12 * scale]
            pts_r = [rx - brow_len * 0.46, base_y + 12 * scale, rx, base_y - 2 * scale, rx + brow_len * 0.46, base_y + 14 * scale]
        elif state == ExpressionState.SURPRISED:
            pts_l = [lx - brow_len * 0.46, base_y - 16 * scale, lx, base_y - 34 * scale, lx + brow_len * 0.46, base_y - 16 * scale]
            pts_r = [rx - brow_len * 0.46, base_y - 16 * scale, rx, base_y - 34 * scale, rx + brow_len * 0.46, base_y - 16 * scale]
        elif state == ExpressionState.SLEEPY:
            drift = math.sin(self.anim_phase * 1.1) * (2.0 * scale)
            pts_l = [lx - brow_len * 0.44, base_y + 4 * scale + drift, lx, base_y + 8 * scale + drift, lx + brow_len * 0.44, base_y + 2 * scale + drift]
            pts_r = [rx - brow_len * 0.44, base_y + 2 * scale + drift, rx, base_y + 8 * scale + drift, rx + brow_len * 0.44, base_y + 4 * scale + drift]
        elif state == ExpressionState.SHY:
            pts_l = [lx - brow_len * 0.48, base_y + 14 * scale + bob, lx, base_y - 2 * scale + bob, lx + brow_len * 0.48, base_y - 18 * scale + bob]
            pts_r = [rx - brow_len * 0.48, base_y - 18 * scale + bob, rx, base_y - 2 * scale + bob, rx + brow_len * 0.48, base_y + 14 * scale + bob]
        elif state == ExpressionState.PROUD:
            pts_l = [lx - brow_len * 0.48, base_y - 4 * scale, lx, base_y - 12 * scale, lx + brow_len * 0.48, base_y + 2 * scale]
            pts_r = [rx - brow_len * 0.48, base_y - 10 * scale, rx, base_y - 30 * scale, rx + brow_len * 0.48, base_y - 14 * scale]
        elif state == ExpressionState.CURIOUS:
            pts_l = [lx - brow_len * 0.46, base_y - 10 * scale, lx, base_y - 24 * scale, lx + brow_len * 0.46, base_y - 10 * scale]
            pts_r = [rx - brow_len * 0.48, base_y - 18 * scale, rx, base_y - 36 * scale, rx + brow_len * 0.48, base_y - 16 * scale]
        elif state == ExpressionState.SKEPTICAL:
            pts_l = [lx - brow_len * 0.48, base_y + 14 * scale, lx + brow_len * 0.48, base_y + 14 * scale]
            pts_r = [rx - brow_len * 0.48, base_y - 16 * scale, rx, base_y - 34 * scale, rx + brow_len * 0.48, base_y - 14 * scale]
        elif state == ExpressionState.COOL:
            pts_l = [lx - brow_len * 0.48, base_y - 12 * scale, lx + brow_len * 0.48, base_y - 10 * scale]
            pts_r = [rx - brow_len * 0.48, base_y - 12 * scale, rx, base_y - 26 * scale, rx + brow_len * 0.48, base_y - 14 * scale]
        elif state == ExpressionState.MOVING:
            wind_bob = math.sin(self.anim_phase * 10.0) * (1.8 * scale)
            pts_l = [lx - brow_len * 0.50, base_y - 8 * scale + wind_bob, lx, base_y - 24 * scale + wind_bob, lx + brow_len * 0.46, base_y - 14 * scale + wind_bob]
            pts_r = [rx - brow_len * 0.46, base_y - 14 * scale + wind_bob, rx, base_y - 24 * scale + wind_bob, rx + brow_len * 0.50, base_y - 8 * scale + wind_bob]
        elif state in [ExpressionState.WATCHING, ExpressionState.LOOKING]:
            pts_l = [lx - brow_len * 0.5, base_y - 26 * scale, lx + brow_len * 0.5, base_y - 26 * scale]
            pts_r = [rx - brow_len * 0.5, base_y - 26 * scale, rx + brow_len * 0.5, base_y - 26 * scale]
        elif state == ExpressionState.LISTENING:
            pts_l = [lx - brow_len * 0.5, base_y - 16 * scale, lx, base_y - 26 * scale, lx + brow_len * 0.5, base_y - 18 * scale]
            pts_r = [rx - brow_len * 0.5, base_y - 18 * scale, rx, base_y - 26 * scale, rx + brow_len * 0.5, base_y - 16 * scale]
        elif state == ExpressionState.THINKING:
            pts_l = [lx - brow_len * 0.48, base_y + 2 * scale, lx + brow_len * 0.48, base_y - 8 * scale]
            pts_r = [rx - brow_len * 0.48, base_y - 22 * scale, rx, base_y - 32 * scale, rx + brow_len * 0.48, base_y - 16 * scale]
        elif state == ExpressionState.CONFUSED:
            pts_l = [
                lx - brow_len * 0.48, base_y + 4 * scale,
                lx - brow_len * 0.16, base_y - 10 * scale,
                lx + brow_len * 0.16, base_y + 8 * scale,
                lx + brow_len * 0.48, base_y - 4 * scale,
            ]
            pts_r = [rx - brow_len * 0.50, base_y - 18 * scale, rx, base_y - 34 * scale, rx + brow_len * 0.50, base_y - 16 * scale]
        elif state == ExpressionState.ERROR:
            pts_l = [lx - brow_len * 0.48, base_y - 18 * scale, lx + brow_len * 0.48, base_y + 6 * scale]
            pts_r = [rx - brow_len * 0.48, base_y + 6 * scale, rx + brow_len * 0.48, base_y - 18 * scale]
        elif state == ExpressionState.SPEAKING:
            spk_bob = math.sin(self.anim_phase * 6.0) * (3.2 * scale) * self.speaking_intensity
            pts_l = [lx - brow_len * 0.48, base_y - 12 * scale + spk_bob, lx, base_y - 18 * scale + spk_bob, lx + brow_len * 0.48, base_y - 12 * scale + spk_bob]
            pts_r = [rx - brow_len * 0.48, base_y - 12 * scale + spk_bob, rx, base_y - 18 * scale + spk_bob, rx + brow_len * 0.48, base_y - 12 * scale + spk_bob]
        else:
            pts_l = [lx - brow_len * 0.48, base_y - 12 * scale + bob, lx, base_y - 18 * scale + bob, lx + brow_len * 0.48, base_y - 12 * scale + bob]
            pts_r = [rx - brow_len * 0.48, base_y - 12 * scale + bob, rx, base_y - 18 * scale + bob, rx + brow_len * 0.48, base_y - 12 * scale + bob]

        glow_col = lerp_color(self.bg_color, color, 0.35)
        core_col = lerp_color(color, "#ffffff", 0.42)

        if pts_l is not None:
            self.canvas.create_line(pts_l, smooth=True, fill=glow_col, width=int(13 * scale), capstyle=tk.ROUND, tags="eyebrow")
            self.canvas.create_line(pts_l, smooth=True, fill=color, width=int(6.2 * scale), capstyle=tk.ROUND, tags="eyebrow")
            self.canvas.create_line(pts_l, smooth=True, fill=core_col, width=max(1, int(1.8 * scale)), capstyle=tk.ROUND, tags="eyebrow")
        if pts_r is not None:
            self.canvas.create_line(pts_r, smooth=True, fill=glow_col, width=int(13 * scale), capstyle=tk.ROUND, tags="eyebrow")
            self.canvas.create_line(pts_r, smooth=True, fill=color, width=int(6.2 * scale), capstyle=tk.ROUND, tags="eyebrow")
            self.canvas.create_line(pts_r, smooth=True, fill=core_col, width=max(1, int(1.8 * scale)), capstyle=tk.ROUND, tags="eyebrow")

    # =========================================================================
    # SLEEK BORDERED OPTICAL LENS ENGINE (EXACT TRIGONOMETRIC CONTOURS!)
    # =========================================================================
    def _draw_standard_eye(
        self,
        cx: float,
        cy: float,
        ew: float,
        eh: float,
        main_col: str,
        glow_col: str,
        lx: float = 0.0,
        ly: float = 0.0,
        state: Optional[str] = None,
        corner_r: Optional[int] = None,
        smile_bottom: bool = False,
        draw_iris: bool = True,
        draw_catchlights: bool = True,
        catchlight_dy: float = 0.0,
    ):
        """
        Draws the signature Neurolis Mark II Bordered Optical Lens Eye using exact
        trigonometric contours (`_build_eye_contour`).
        """
        scale = self.ui_scale / 1.8
        rad = float(corner_r) if corner_r is not None else min(float(self.corner_radius), ew * 0.44, eh * 0.44)

        glow_w = 10.0 * scale
        pts_glow_wide = self._build_eye_contour(cx, cy, ew + glow_w * 2, eh + glow_w * 2, rad + glow_w, smile_bottom=smile_bottom)
        self.canvas.create_polygon(pts_glow_wide, smooth=False, fill=lerp_color(self.bg_color, main_col, 0.16), outline="")

        glow_m = 4.5 * scale
        pts_glow_mid = self._build_eye_contour(cx, cy, ew + glow_m * 2, eh + glow_m * 2, rad + glow_m, smile_bottom=smile_bottom)
        self.canvas.create_polygon(pts_glow_mid, smooth=False, fill=lerp_color(self.bg_color, main_col, 0.38), outline="")

        pts_outer = self._build_eye_contour(cx, cy, ew, eh, rad, smile_bottom=smile_bottom)
        self.canvas.create_polygon(pts_outer, smooth=False, fill=main_col, outline="")

        border_t = max(5.5 * scale, min(ew, eh) * 0.080)
        iw = ew - border_t * 2.0
        ih = eh - border_t * 2.0
        irad = max(6.0, rad - border_t * 0.90)

        if ih > 8.0 and iw > 8.0:
            chamber_col = lerp_color("#040914", main_col, 0.08)
            inner_bevel_col = lerp_color(chamber_col, main_col, 0.36)
            pts_inner = self._build_eye_contour(cx, cy, iw, ih, irad, smile_bottom=smile_bottom)
            self.canvas.create_polygon(pts_inner, smooth=False, fill=chamber_col, outline=inner_bevel_col, width=max(1, int(2.0 * scale)))

        if draw_iris and eh > self.eye_h * 0.36:
            icx = cx + (lx * 13.5 * scale)
            icy = cy + (ly * 10.0 * scale) - (8.0 * scale if smile_bottom else 0.0)
            r_iris = min(iw, ih) * (0.31 if smile_bottom else 0.35)

            iris_fill = lerp_color("#050c1a", main_col, 0.25)
            iris_ring_col = lerp_color(main_col, "#ffffff", 0.32)
            self.canvas.create_oval(
                icx - r_iris, icy - r_iris,
                icx + r_iris, icy + r_iris,
                fill=iris_fill, outline=iris_ring_col, width=max(1, int(2.4 * scale))
            )

            tick_sz = 4.5 * scale
            t_col = lerp_color(main_col, "#ffffff", 0.58)
            self.canvas.create_line(icx, icy - r_iris, icx, icy - r_iris + tick_sz, fill=t_col, width=max(1, int(1.5 * scale)))
            self.canvas.create_line(icx, icy + r_iris, icx, icy + r_iris - tick_sz, fill=t_col, width=max(1, int(1.5 * scale)))
            self.canvas.create_line(icx - r_iris, icy, icx - r_iris + tick_sz, icy, fill=t_col, width=max(1, int(1.5 * scale)))
            self.canvas.create_line(icx + r_iris, icy, icx + r_iris - tick_sz, icy, fill=t_col, width=max(1, int(1.5 * scale)))

            pupil_pulse = math.sin(self.anim_phase * 3.5) * (1.4 * scale)
            pupil_r = max(4.0, min(ew, eh) * 0.125 + pupil_pulse)
            self.canvas.create_oval(
                icx - pupil_r - 3 * scale, icy - pupil_r - 3 * scale,
                icx + pupil_r + 3 * scale, icy + pupil_r + 3 * scale,
                fill=main_col, outline=""
            )
            self.canvas.create_oval(
                icx - pupil_r, icy - pupil_r,
                icx + pupil_r, icy + pupil_r,
                fill="#ffffff", outline=""
            )

        if draw_catchlights and eh > self.eye_h * 0.34:
            gx_p = lx * 15.0 * scale
            gy_p = ly * 11.0 * scale + catchlight_dy
            glint1_w = ew * 0.22
            glint1_h = eh * 0.12
            gx1 = cx - ew * 0.28 + gx_p
            gy1 = cy - eh * 0.30 + gy_p
            self.canvas.create_oval(gx1, gy1, gx1 + glint1_w, gy1 + glint1_h, fill="#ffffff", outline="")

            glint2_r = max(2.5, ew * 0.040)
            gx2 = gx1 + glint1_w + 5.5 * scale
            gy2 = gy1 + glint1_h * 0.55
            self.canvas.create_oval(gx2 - glint2_r, gy2 - glint2_r, gx2 + glint2_r, gy2 + glint2_r, fill="#ffffff", outline="")

            glint3_r = max(2.8, ew * 0.046)
            gx3 = cx + ew * 0.22 + gx_p * 0.7
            gy3 = cy + eh * 0.18 + gy_p * 0.7 - (11.0 * scale if smile_bottom else 0.0)
            self.canvas.create_oval(gx3 - glint3_r, gy3 - glint3_r, gx3 + glint3_r, gy3 + glint3_r, fill="#ffffff", outline="")

    # =========================================================================
    # 11 OVERHAULED CORE EXPRESSIONS (UNMISTAKABLE AT FIRST GLANCE!)
    # =========================================================================
    def _draw_happy_eyes(self, lx: float, rx: float, cy: float, *args, **kwargs):
        """
        2. HAPPY: Joyous smiling inverted-U neon emerald crescent arches (∩ ∩) with white apex gleam,
        warm cyber-blush cushions, and twinkling diamond joy sparkles (✦).
        """
        scale = self.ui_scale / 1.8
        ew, eh = self.eye_w, self.eye_h
        main_col, glow_col = self.color_happy, "#003d24"

        bounce = math.sin(self.anim_phase * 6.0) * (3.5 * scale)
        eye_y = cy + bounce

        w = ew * 0.88
        h = eh * 0.65
        r_w = w / 2.0
        r_h = h * 0.65
        leg_drop = h * 0.32
        flare = r_w * 0.06

        self._draw_cyber_blush(lx, rx, eye_y + leg_drop + 16 * scale, scale, base_col="#ff3b7f", outward_shift=14 * scale)

        for ecx in (lx, rx):
            pts = []
            pts.extend([ecx - r_w - flare, eye_y + leg_drop])
            pts.extend([ecx - r_w, eye_y])
            for i in range(21):
                ang = math.pi - (i / 20.0) * math.pi
                pts.extend([ecx + r_w * math.cos(ang), eye_y - r_h * math.sin(ang)])
            pts.extend([ecx + r_w, eye_y])
            pts.extend([ecx + r_w + flare, eye_y + leg_drop])

            self.canvas.create_line(pts, smooth=True, fill=glow_col, width=int(28 * scale), capstyle=tk.ROUND)
            self.canvas.create_line(pts, smooth=True, fill="#00cc66", width=int(18 * scale), capstyle=tk.ROUND)
            self.canvas.create_line(pts, smooth=True, fill=main_col, width=int(11 * scale), capstyle=tk.ROUND)
            apex_pts = pts[10 * 2 : 17 * 2]
            if len(apex_pts) >= 4:
                self.canvas.create_line(apex_pts, smooth=True, fill="#ffffff", width=max(1, int(3.5 * scale)), capstyle=tk.ROUND)

        sp_r = (7.5 + 2.0 * math.sin(self.anim_phase * 5.0)) * scale
        self._draw_sparkle(lx - ew * 0.56, eye_y - eh * 0.18, sp_r, "#70ffbe")
        self._draw_sparkle(rx + ew * 0.56, eye_y - eh * 0.18, sp_r * 0.85, "#70ffbe")

    def _draw_sad_eyes(self, lx: float, rx: float, cy: float, ew: float, eh: float, main_col: str, glow_col: str):
        """
        3. SAD: Softly rounded sapphire bordered optical eyes with heavy drooping outer-slanted eyelids (\\   /),
        a deep shimmering liquid tear pool welling at the bottom rim, and prominent dual-stream cascading teardrops!
        """
        scale = self.ui_scale / 1.8
        self._draw_standard_eye(lx, cy, ew, eh, main_col, glow_col, 0.0, 0.24, catchlight_dy=18 * scale)
        self._draw_standard_eye(rx, cy, ew, eh, main_col, glow_col, 0.0, 0.24, catchlight_dy=18 * scale)

        lid_drop = 42 * scale
        tremble = math.sin(self.anim_phase * 9.0) * (1.6 * scale)

        left_lid = [
            lx - ew / 2.0 - 14 * scale, cy - eh / 2.0 - 14 * scale,
            lx + ew / 2.0 + 14 * scale, cy - eh / 2.0 - 14 * scale,
            lx + ew / 2.0 + 14 * scale, cy - eh / 2.0 + lid_drop - 20 * scale + tremble,
            lx - ew / 2.0 - 14 * scale, cy - eh / 2.0 + lid_drop + 22 * scale + tremble,
        ]
        self.canvas.create_polygon(left_lid, fill=self.bg_color, outline="")
        self.canvas.create_line(
            lx - ew * 0.46, cy - eh / 2.0 + lid_drop + 20 * scale + tremble,
            lx + ew * 0.46, cy - eh / 2.0 + lid_drop - 18 * scale + tremble,
            fill=main_col, width=int(6.5 * scale), capstyle=tk.ROUND
        )

        right_lid = [
            rx - ew / 2.0 - 14 * scale, cy - eh / 2.0 - 14 * scale,
            rx + ew / 2.0 + 14 * scale, cy - eh / 2.0 - 14 * scale,
            rx + ew / 2.0 + 14 * scale, cy - eh / 2.0 + lid_drop + 22 * scale + tremble,
            rx - ew / 2.0 - 14 * scale, cy - eh / 2.0 + lid_drop - 20 * scale + tremble,
        ]
        self.canvas.create_polygon(right_lid, fill=self.bg_color, outline="")
        self.canvas.create_line(
            rx - ew * 0.46, cy - eh / 2.0 + lid_drop - 18 * scale + tremble,
            rx + ew * 0.46, cy - eh / 2.0 + lid_drop + 20 * scale + tremble,
            fill=main_col, width=int(6.5 * scale), capstyle=tk.ROUND
        )

        # 1. Noticeable Welling Liquid Tear Pool shimmering along the lower rim of each eye
        for side, cx in [(-1, lx), (1, rx)]:
            pool_y = cy + eh * 0.34
            wave_pts = []
            for w_i in range(11):
                t = (w_i / 10.0) * 2.0 - 1.0
                wx = cx + t * (ew * 0.36)
                wy = pool_y + math.sin(self.anim_phase * 6.5 + w_i * 0.8) * (2.5 * scale) + (t * t) * (6.0 * scale)
                wave_pts.extend([wx, wy])
            self.canvas.create_line(wave_pts, smooth=True, fill="#38bdf8", width=int(8.5 * scale), capstyle=tk.ROUND)
            self.canvas.create_line(wave_pts, smooth=True, fill="#bae6fd", width=int(4.0 * scale), capstyle=tk.ROUND)
            bead_x = cx + side * (ew * 0.32)
            bead_y = cy + eh * 0.38
            br = 7.5 * scale
            self.canvas.create_oval(bead_x - br, bead_y - br, bead_x + br, bead_y + br, fill="#38bdf8", outline="#ffffff", width=max(1, int(1.5 * scale)))

        # 2. Prominent Multi-Layered Cascading Teardrops with Watery Streak Trails & Cheek Splash Ripples
        tear_streams = [
            (lx - ew * 0.30, 0.22, 1.0),
            (lx + ew * 0.22, 0.68, 0.78),
            (rx + ew * 0.30, 0.45, 1.0),
            (rx - ew * 0.22, 0.88, 0.78),
        ]
        for tx, phase_off, sz_m in tear_streams:
            frac = ((self.anim_phase * 0.65 + phase_off) % 1.0)
            start_y = cy + eh * 0.42
            ty = start_y + frac * (56.0 * scale)
            tr = (10.5 * sz_m * (1.0 - frac * 0.15)) * scale

            self.canvas.create_line(
                tx, start_y, tx, ty - tr * 0.8,
                fill=lerp_color(self.bg_color, "#38bdf8", 0.55 * (1.0 - frac * 0.5)),
                width=max(2, int(4.5 * sz_m * scale)), capstyle=tk.ROUND
            )

            gr = tr * 1.35
            self.canvas.create_oval(tx - gr, ty - gr, tx + gr, ty + gr, fill="#082f49", outline="")

            drop_pts = [
                tx - tr, ty,
                tx, ty - tr * 2.1,
                tx + tr, ty,
            ]
            self.canvas.create_polygon(drop_pts, fill="#38bdf8", outline="")
            self.canvas.create_oval(tx - tr, ty - tr, tx + tr, ty + tr, fill="#38bdf8", outline="#bae6fd", width=max(1, int(1.8 * scale)))
            self.canvas.create_oval(tx - tr * 0.65, ty - tr * 0.45, tx + tr * 0.65, ty + tr * 0.75, fill="#7dd3fc", outline="")
            self.canvas.create_oval(tx - tr * 0.55, ty - tr * 0.55, tx - tr * 0.12, ty - tr * 0.15, fill="#ffffff", outline="")

            if frac > 0.65:
                sp_w = (frac - 0.65) * 38.0 * scale
                self.canvas.create_oval(tx - sp_w, ty + tr - 3 * scale, tx + sp_w, ty + tr + 3 * scale, fill="", outline="#7dd3fc", width=max(1, int(1.8 * scale)))

    def _draw_confused_eyes(self, lx: float, rx: float, cy: float, main_col: str, glow_col: str):
        """
        4. CONFUSED ("Like in confused, both eye spirals to be same size..."):
        100% FRAMELESS Hypnotic Counter-Rotating Golden Archimedes Spirals (@   @) —
        BOTH eye spirals are now the EXACT SAME SIZE and height!
        """
        scale = self.ui_scale / 1.8
        same_sp_r = min(self.eye_w, self.eye_h) * 0.47
        specs = [
            (lx, cy, same_sp_r, 1.0, main_col),
            (rx, cy, same_sp_r, -1.0, main_col),
        ]
        for cx, cy_e, max_sp_r, dir_s, sp_col in specs:
            self.canvas.create_oval(
                cx - max_sp_r - 10 * scale, cy_e - max_sp_r - 10 * scale,
                cx + max_sp_r + 10 * scale, cy_e + max_sp_r + 10 * scale,
                fill=lerp_color(self.bg_color, glow_col, 0.55), outline=""
            )

            pts = []
            rot = self.anim_phase * 4.8 * dir_s
            num_steps = 72
            for i in range(num_steps):
                frac = i / float(num_steps - 1)
                theta = frac * 6.8 * math.pi * dir_s + rot
                r_cur = (0.05 + 0.95 * frac) * max_sp_r
                pts.extend([cx + r_cur * math.cos(theta), cy_e + r_cur * math.sin(theta)])

            self.canvas.create_line(pts, smooth=True, fill=glow_col, width=int(15 * scale), capstyle=tk.ROUND)
            self.canvas.create_line(pts, smooth=True, fill=sp_col, width=int(8.2 * scale), capstyle=tk.ROUND)
            self.canvas.create_line(pts[:42], smooth=True, fill="#ffffff", width=max(1, int(3.2 * scale)), capstyle=tk.ROUND)
            self.canvas.create_oval(cx - 5 * scale, cy_e - 5 * scale, cx + 5 * scale, cy_e + 5 * scale, fill="#ffffff", outline="")

        q_bob = math.sin(self.anim_phase * 4.0) * (4.0 * scale)
        self.canvas.create_text(rx + self.eye_w * 0.64, cy - self.eye_h * 0.44 + q_bob, text="?", fill="#fde047", font=(FONT_FAMILY, int(28 * scale), "bold"))
        self.canvas.create_text(lx - self.eye_w * 0.56, cy - self.eye_h * 0.34 - q_bob, text="?", fill="#fb8500", font=(FONT_FAMILY, int(21 * scale), "bold"))
        self._draw_sparkle(rx - self.eye_w * 0.45, cy - self.eye_h * 0.56, 8.0 * scale, "#fde047")

    def _draw_thinking_eyes(self, lx: float, rx: float, cy: float, ew: float, eh: float, main_col: str, glow_col: str):
        """
        5. THINKING ("A flickering light bulb trying to glow in top right next to eye in thinking.."):
        Softly rounded royal-violet bordered optical lenses with rotating neural cog irises gazing up-right
        at ascending thought bubbles AND a flickering lightbulb trying to glow at the top-right!
        """
        scale = self.ui_scale / 1.8
        self._draw_standard_eye(lx, cy, ew, eh * 0.90, main_col, glow_col, 0.28, -0.24, draw_iris=False, draw_catchlights=False)
        self._draw_standard_eye(rx, cy, ew, eh * 0.90, main_col, glow_col, 0.28, -0.24, draw_iris=False, draw_catchlights=False)

        for cx in (lx, rx):
            icx = cx + 11.0 * scale
            icy = cy - 8.5 * scale
            r_outer = min(ew, eh) * 0.26
            r_inner = r_outer * 0.56
            base_deg = (self.thinking_angle * 65.0) % 360.0
            for seg in range(3):
                start_a = base_deg + seg * 120.0
                self.canvas.create_arc(
                    icx - r_outer, icy - r_outer, icx + r_outer, icy + r_outer,
                    start=start_a, extent=72, style=tk.ARC,
                    outline="#d8b4fe", width=int(4.5 * scale)
                )
            for seg in range(2):
                start_b = -base_deg * 1.3 + seg * 180.0
                self.canvas.create_arc(
                    icx - r_inner, icy - r_inner, icx + r_inner, icy + r_inner,
                    start=start_b, extent=100, style=tk.ARC,
                    outline="#ffffff", width=int(3.0 * scale)
                )
            self.canvas.create_oval(icx - 5 * scale, icy - 5 * scale, icx + 5 * scale, icy + 5 * scale, fill="#ffffff", outline=main_col, width=1)
            self.canvas.create_oval(cx - ew * 0.26, cy - eh * 0.28, cx - ew * 0.06, cy - eh * 0.16, fill="#ffffff", outline="")

        bx = rx + ew * 0.54
        by = cy - eh * 0.10
        for dx, dy, br, bcol in [(6, 0, 5.0, "#a855f7"), (18, -18, 8.0, "#c084fc")]:
            bx_i = bx + dx * scale
            by_i = by + dy * scale
            r_i = br * scale
            self.canvas.create_oval(bx_i - r_i, by_i - r_i, bx_i + r_i, by_i + r_i, fill="#1e0b36", outline=bcol, width=int(2.2 * scale))

        self._draw_flickering_lightbulb(rx + ew * 0.72, cy - eh * 0.44, scale * 1.05, mode="trying")

    def _draw_listening_eyes(self, lx: float, rx: float, cy: float, ew: float, eh: float, main_col: str, glow_col: str, look_x: float, look_y: float):
        """
        6. LISTENING: Bioluminescent mint-teal bordered optical eyes with cute, compact Bionic
        Audio-Receiver Side-Ears cupped on the outer sides of the eyes matching the bordered neon
        design scheme, plus a live concentric sonar-ring + 5-bar equalizer iris and acoustic waves!
        """
        scale = self.ui_scale / 1.8
        self._draw_standard_eye(lx, cy, ew, eh, main_col, glow_col, look_x, look_y, draw_iris=False)
        self._draw_standard_eye(rx, cy, ew, eh, main_col, glow_col, look_x, look_y, draw_iris=False)

        # Cute, small Bionic Audio-Receiver Side-Ears cupped on the outer sides of the eyes!
        ear_w = 28.0 * scale
        ear_h = eh * 0.48
        ear_r = 13.0 * scale
        ear_pulse = 1.0 + 0.08 * math.sin(self.anim_phase * 6.0)
        for side, base_x in [(-1, lx - ew / 2.0), (1, rx + ew / 2.0)]:
            ex1 = base_x - ear_w * ear_pulse if side == -1 else base_x - 3 * scale
            ex2 = base_x + 3 * scale if side == -1 else base_x + ear_w * ear_pulse
            ey1 = cy - ear_h / 2.0
            ey2 = cy + ear_h / 2.0
            self._create_rounded_rect(ex1 - 4 * scale, ey1 - 4 * scale, ex2 + 4 * scale, ey2 + 4 * scale, radius=int(ear_r + 4 * scale), fill=glow_col, outline="")
            self._create_rounded_rect(ex1, ey1, ex2, ey2, radius=int(ear_r), fill="#041514", outline=main_col, width=max(2, int(4.2 * scale)))
            ecx = (ex1 + ex2) / 2.0 + side * (2.5 * scale)
            for r_off in (-8.5, 0.0, 8.5):
                ry = cy + r_off * scale
                self.canvas.create_line(ecx - 5.5 * scale, ry, ecx + 5.5 * scale, ry, fill="#00ffcc", width=max(1, int(2.2 * scale)), capstyle=tk.ROUND)
            dot_y = cy - ear_h * 0.60
            self.canvas.create_line(ecx, ey1, ecx, dot_y, fill=main_col, width=max(1, int(2.5 * scale)))
            self.canvas.create_oval(ecx - 4.0 * scale, dot_y - 4.0 * scale, ecx + 4.0 * scale, dot_y + 4.0 * scale, fill="#ffffff", outline=main_col, width=1)

        for cx in (lx, rx):
            icx = cx + look_x * 12.0 * scale
            icy = cy + look_y * 9.0 * scale
            for r_i in range(2):
                rip_t = (self.anim_phase * 1.8 + r_i * 0.5) % 1.0
                r_son = (14.0 + rip_t * 28.0) * scale
                r_col = lerp_color("#051821", main_col, (1.0 - rip_t) * 0.90)
                self.canvas.create_oval(icx - r_son, icy - r_son, icx + r_son, icy + r_son, fill="", outline=r_col, width=max(1, int(2.2 * scale)))

            for b_i in range(-2, 3):
                bx = icx + b_i * (6.5 * scale)
                bh = (5.0 + abs(math.sin(self.anim_phase * 7.0 + b_i * 0.9)) * 13.0) * scale * (1.0 - abs(b_i) * 0.18)
                b_col = "#ffffff" if b_i == 0 else "#00ffcc"
                self.canvas.create_line(bx, icy - bh, bx, icy + bh, fill=b_col, width=max(2, int(3.0 * scale)), capstyle=tk.ROUND)

        for w_i in range(2):
            phase = (self.anim_phase * 1.8 + w_i * 0.5) % 1.0
            dist = (32.0 + phase * 18.0) * scale
            w_col = lerp_color(self.bg_color, main_col, (1.0 - phase) * 0.85)
            arc_h = eh * (0.28 + phase * 0.14)
            lx_c = lx - ew / 2.0 - dist
            self.canvas.create_arc(lx_c - 10 * scale, cy - arc_h, lx_c + 10 * scale, cy + arc_h, start=115, extent=130, style=tk.ARC, outline=w_col, width=max(1, int(2.8 * scale)))
            rx_c = rx + ew / 2.0 + dist
            self.canvas.create_arc(rx_c - 10 * scale, cy - arc_h, rx_c + 10 * scale, cy + arc_h, start=-65, extent=130, style=tk.ARC, outline=w_col, width=max(1, int(2.8 * scale)))

    def _draw_speaking_eyes(self, lx: float, rx: float, cy: float, ew: float, eh: float, main_col: str, glow_col: str, look_x: float, look_y: float):
        """
        7. SPEAKING: Sleek sky-cyan bordered optical lenses (strictly un-curved bottom)
        housing a live oscillating voice-waveform ring resonator inside the iris!
        """
        scale = self.ui_scale / 1.8
        self._draw_standard_eye(lx, cy, ew, eh, main_col, glow_col, look_x, look_y, smile_bottom=False, draw_iris=False)
        self._draw_standard_eye(rx, cy, ew, eh, main_col, glow_col, look_x, look_y, smile_bottom=False, draw_iris=False)

        mod = 1.0 + 0.18 * math.sin(self.anim_phase * 9.0) * self.speaking_intensity
        for cx in (lx, rx):
            icx = cx + look_x * 12.0 * scale
            icy = cy + look_y * 9.0 * scale
            r_out = 30.0 * scale * mod
            self.canvas.create_oval(icx - r_out, icy - r_out, icx + r_out, icy + r_out, fill="#062238", outline=main_col, width=int(2.8 * scale))
            wave_pts = []
            for i in range(15):
                t = (i / 14.0) * 2.0 - 1.0
                wx = icx + t * (r_out * 0.78)
                wy = icy + math.sin(self.anim_phase * 10.0 + i * 0.85) * (9.5 * scale * self.speaking_intensity) * (1.0 - t * t)
                wave_pts.extend([wx, wy])
            self.canvas.create_line(wave_pts, smooth=True, fill="#00ffcc", width=int(4.5 * scale), capstyle=tk.ROUND)
            self.canvas.create_line(wave_pts, smooth=True, fill="#ffffff", width=max(1, int(2.0 * scale)), capstyle=tk.ROUND)

    def _draw_watching_eyes(self, lx: float, rx: float, cy: float, ew: float, eh: float, main_col: str, glow_col: str, lx_coord: float, ly_coord: float):
        """
        8. WATCHING ("In scanning, improve the animation of horizontal eye scan line."):
        Precision Cyber-Aqua Optical Sentry Viewfinder Lenses with a multi-layered
        Volumetric Horizontal Laser Scan Beam, trailing phosphor afterglow curtain,
        side-rail emitter nodes, and target reticle!
        """
        scale = self.ui_scale / 1.8
        vh = eh * 0.90
        self._draw_standard_eye(lx, cy, ew, vh, main_col, glow_col, lx_coord, ly_coord, draw_iris=False)
        self._draw_standard_eye(rx, cy, ew, vh, main_col, glow_col, lx_coord, ly_coord, draw_iris=False)

        bracket_color = "#00ffcc"
        bracket_len = 20 * scale
        bracket_pad = 9 * scale

        scan_sin = math.sin(self.anim_phase * 3.8)
        scan_vel_dir = 1.0 if math.cos(self.anim_phase * 3.8) >= 0.0 else -1.0
        scan_y = cy + scan_sin * (vh * 0.31)
        beam_hw = ew * 0.41

        for cx in (lx, rx):
            icx = cx + lx_coord * 13.0 * scale
            icy = cy + ly_coord * 10.0 * scale
            r_ret = 29.0 * scale
            self.canvas.create_oval(icx - r_ret, icy - r_ret, icx + r_ret, icy + r_ret, fill="#041f29", outline="#00ffcc", width=int(2.2 * scale))
            rot_deg = (self.anim_phase * 55.0) % 360.0
            self.canvas.create_arc(icx - r_ret * 0.72, icy - r_ret * 0.72, icx + r_ret * 0.72, icy + r_ret * 0.72, start=rot_deg, extent=95, style=tk.ARC, outline="#ffffff", width=int(2.2 * scale))
            self.canvas.create_arc(icx - r_ret * 0.72, icy - r_ret * 0.72, icx + r_ret * 0.72, icy + r_ret * 0.72, start=rot_deg + 180, extent=95, style=tk.ARC, outline="#ffffff", width=int(2.2 * scale))
            self.canvas.create_line(icx - r_ret * 1.15, icy, icx - r_ret * 0.45, icy, fill="#00ffcc", width=max(1, int(1.8 * scale)))
            self.canvas.create_line(icx + r_ret * 0.45, icy, icx + r_ret * 1.15, icy, fill="#00ffcc", width=max(1, int(1.8 * scale)))
            self.canvas.create_line(icx, icy - r_ret * 1.15, icx, icy - r_ret * 0.45, fill="#00ffcc", width=max(1, int(1.8 * scale)))
            self.canvas.create_line(icx, icy + r_ret * 0.45, icx, icy + r_ret * 1.15, fill="#00ffcc", width=max(1, int(1.8 * scale)))
            self.canvas.create_oval(icx - 4.5 * scale, icy - 4.5 * scale, icx + 4.5 * scale, icy + 4.5 * scale, fill="#ff1744", outline="#ffffff", width=1)

            for t_idx in range(5, 0, -1):
                trail_y = scan_y - scan_vel_dir * (t_idx * 4.2 * scale)
                if abs(trail_y - cy) < vh * 0.36:
                    trail_alpha = (6 - t_idx) / 6.0 * 0.42
                    trail_col = lerp_color("#04121c", "#00ffcc", trail_alpha)
                    self.canvas.create_line(
                        cx - beam_hw * 0.96, trail_y, cx + beam_hw * 0.96, trail_y,
                        fill=trail_col, width=max(1, int(4.5 * scale)), capstyle=tk.ROUND
                    )

            self.canvas.create_line(cx - beam_hw, scan_y, cx + beam_hw, scan_y, fill="#00b4d8", width=int(8.5 * scale), capstyle=tk.ROUND)
            self.canvas.create_line(cx - beam_hw, scan_y, cx + beam_hw, scan_y, fill="#00ffcc", width=int(4.5 * scale), capstyle=tk.ROUND)
            self.canvas.create_line(cx - beam_hw * 0.94, scan_y, cx + beam_hw * 0.94, scan_y, fill="#ffffff", width=max(1, int(2.0 * scale)), capstyle=tk.ROUND)

            for side_e in (-1, 1):
                ex_n = cx + side_e * beam_hw
                er = 4.8 * scale
                self.canvas.create_oval(ex_n - er, scan_y - er, ex_n + er, scan_y + er, fill="#00ffcc", outline="#ffffff", width=max(1, int(1.5 * scale)))

            x1 = cx - ew / 2.0 - bracket_pad
            y1 = cy - vh / 2.0 - bracket_pad
            x2 = cx + ew / 2.0 + bracket_pad
            y2 = cy + vh / 2.0 + bracket_pad
            bw = max(1, int(2.6 * scale))
            self.canvas.create_line(x1, y1 + bracket_len, x1, y1, x1 + bracket_len, y1, fill=bracket_color, width=bw)
            self.canvas.create_line(x2 - bracket_len, y1, x2, y1, x2, y1 + bracket_len, fill=bracket_color, width=bw)
            self.canvas.create_line(x1, y2 - bracket_len, x1, y2, x1 + bracket_len, y2, fill=bracket_color, width=bw)
            self.canvas.create_line(x2 - bracket_len, y2, x2, y2, x2, y2 - bracket_len, fill=bracket_color, width=bw)

        tag_y = cy + vh / 2.0 + 22 * scale
        self.canvas.create_text(lx - ew * 0.10, tag_y, text="FOV 85° // OPTIC LOCK", fill="#00ffcc", font=(FONT_FAMILY, max(8, int(8.5 * scale)), "bold"))
        rec_blink = math.sin(self.anim_phase * 6.0) > 0.0
        rec_x = rx + ew * 0.05
        self.canvas.create_oval(rec_x - 4 * scale, tag_y - 4 * scale, rec_x + 4 * scale, tag_y + 4 * scale, fill="#ff1744" if rec_blink else "#550a14", outline="")
        self.canvas.create_text(rec_x + 8 * scale, tag_y, text="REC [LIVE]", anchor="w", fill="#ffffff" if rec_blink else "#64748b", font=(FONT_FAMILY, max(8, int(8.5 * scale)), "bold"))

    def _draw_moving_eyes(self, lx: float, rx: float, cy: float, ew: float, eh: float, main_col: str, glow_col: str, look_x: float = 0.0, look_y: float = 0.0):
        """
        9. MOVING: Exhilarated, wind-enjoying cruising eyes!
        Uses the seamless `smile_bottom=True` contour on the sleek bordered cyan optical lenses,
        plus the prominent center `DRIVE` speedometer arc between the eyes and fast wind slipstreams!
        """
        scale = self.ui_scale / 1.8
        self._draw_standard_eye(lx, cy, ew, eh, main_col, glow_col, look_x, look_y, smile_bottom=True)
        self._draw_standard_eye(rx, cy, ew, eh, main_col, glow_col, look_x, look_y, smile_bottom=True)

        mid_x = (lx + rx) / 2.0
        hud_y = cy - eh * 0.04
        self.canvas.create_arc(
            mid_x - 28 * scale, hud_y - 28 * scale,
            mid_x + 28 * scale, hud_y + 28 * scale,
            start=20, extent=140, style=tk.ARC, outline="#00ffaa", width=max(2, int(3.5 * scale))
        )
        self.canvas.create_text(mid_x, hud_y + 2 * scale, text="DRIVE", fill="#ffffff", font=(FONT_FAMILY, max(8, int(9.5 * scale)), "bold"))

        for side, s_cx in [(-1, lx - ew * 0.56), (1, rx + ew * 0.56)]:
            for s_idx in range(3):
                phase = (self.anim_phase * 5.2 + s_idx * 0.33) % 1.0
                st_len = (26.0 + phase * 42.0) * scale
                st_x1 = s_cx + side * (phase * 32.0 * scale)
                st_x2 = st_x1 + side * st_len
                st_y = cy + (s_idx - 1) * (22.0 * scale)
                col_st = "#00f0ff" if phase < 0.55 else "#0284c7"
                self.canvas.create_line(st_x1, st_y, st_x2, st_y, fill=col_st, width=max(1, int((3.2 - phase * 1.5) * scale)), capstyle=tk.ROUND)

    def _draw_error_eyes(self, lx: float, rx: float, cy: float, ew: float, eh: float, main_col: str, glow_col: str):
        """
        10. ERROR: 100% FRAMELESS Neon-Crimson Glitch 'X' Optics with digital scanline slice offsets
        and flanking vector caution triangles (!).
        """
        scale = self.ui_scale / 1.8
        arm = min(ew, eh) * 0.38
        jitter = math.sin(self.anim_phase * 22.0) * (2.0 * scale)

        for cx in (lx, rx):
            for w_mult, col_x in [(30, glow_col), (19, "#b91c1c"), (11, main_col), (3.8, "#ffffff")]:
                self.canvas.create_line(cx - arm + jitter, cy - arm, cx + arm + jitter, cy + arm, fill=col_x, width=max(1, int(w_mult * scale)), capstyle=tk.ROUND)
                self.canvas.create_line(cx + arm - jitter, cy - arm, cx - arm - jitter, cy + arm, fill=col_x, width=max(1, int(w_mult * scale)), capstyle=tk.ROUND)

        for side, tx in [(-1, lx - ew * 0.65), (1, rx + ew * 0.65)]:
            ty = cy
            th = 18.0 * scale
            tri_pts = [tx, ty - th, tx + th * 0.92, ty + th * 0.75, tx - th * 0.92, ty + th * 0.75]
            self.canvas.create_polygon(tri_pts, fill="#ffb703", outline="#ffffff", width=max(1, int(1.5 * scale)))
            self.canvas.create_line(tx, ty - th * 0.35, tx, ty + th * 0.18, fill="#090d16", width=max(2, int(3.0 * scale)), capstyle=tk.ROUND)
            self.canvas.create_oval(tx - 2 * scale, ty + th * 0.34, tx + 2 * scale, ty + th * 0.52, fill="#090d16", outline="")

    def _villain_closure(self, now: float) -> float:
        """0 = open, up to ~0.62 = half-lidded. A slow, disdainful half-blink every ~7s (never a snap)."""
        period = 7.4
        cycle = int(now // period)
        start = 5.6 + ((cycle * 37) % 11) / 10.0
        dt = (now - cycle * period) - start
        if dt < 0.0 or dt > 1.0:
            return 0.0
        if dt < 0.40:
            return 0.62 * ease_out_cubic(dt / 0.40)
        if dt < 0.55:
            return 0.62
        return 0.62 * (1.0 - ease_out_cubic((dt - 0.55) / 0.45))

    def _villain_crt_state(self, now: float, w: float, h: float) -> dict:
        """Irregular hacked-CRT schedule: raster tears, brownouts, a rolling interference band, text-corruption ticks.
        Driven by a seeded RNG at random intervals (not a sine), plus a heavier burst for 0.5s after entering."""
        v = self._vil
        rng = v["rng"]
        sx, sy = w / 1024.0, h / 600.0
        entry_age = now - v["entry"]
        heavy = entry_age < 0.5

        if heavy:
            v["bands"] = [
                (rng.uniform(0.08, 0.9) * h, rng.uniform(4, 16) * sy, rng.choice((-1, 1)) * rng.uniform(14, 60) * sx)
                for _ in range(rng.randint(2, 4))
            ]
            v["tear_end"] = now + 0.05
            v["corrupt_until"] = now + 0.05
        elif now >= v["tear_end"] and now >= v["next_tear"]:
            v["bands"] = [
                (rng.uniform(0.10, 0.90) * h, rng.uniform(3, 14) * sy, rng.choice((-1, 1)) * rng.uniform(10, 46) * sx)
                for _ in range(rng.choice((1, 2, 2, 3, 4)))
            ]
            v["tear_end"] = now + rng.uniform(0.06, 0.18)
            v["corrupt_until"] = now + 0.05  # text corrupts for just 1-3 frames
            v["next_tear"] = now + rng.uniform(0.22, 1.0)
        tear_active = now < v["tear_end"]
        v["tear_dx"] = (v["bands"][0][2] if (tear_active and v["bands"]) else 0.0)

        if now >= v["next_brown"]:
            v["brown_end"] = now + rng.uniform(0.06, 0.14)
            v["next_brown"] = now + rng.uniform(1.2, 3.6)
        brown = 0.5 if now < v["brown_end"] else (0.8 if rng.random() < 0.07 else 1.0)  # plus constant micro-flicker
        if heavy and int(entry_age * 40) % 2 == 0:
            brown = 0.6

        roll_t = (now % 4.2) / 2.6
        roll = ((-0.1 + roll_t * 1.2) * h, 52 * sy, 1.32) if roll_t < 1.0 else None

        return {
            "bands": v["bands"] if tear_active else [],
            "brown": brown,
            "roll": roll,
            "scan_offset": int(now * 6.0) % 3,
            "corrupt": now < v["corrupt_until"],
            "jit": (rng.uniform(-3, 3) * sx) if tear_active else 0.0,
            "tear": tear_active,
        }

    def _vil_garble(self, text: str, severity: float = 0.18) -> str:
        """Randomly swaps a share of characters for block/noise glyphs for a corrupted-signal flash."""
        rng = self._vil["rng"]
        out = []
        for ch in text:
            if ch in " \n" or rng.random() > severity:
                out.append(ch)
            else:
                out.append(rng.choice(VIL_GLITCH_CHARS))
        return "".join(out)

    def _draw_villain_eyes(self, lx: float, rx: float, cy: float, ew: float, eh: float, main_col: str, glow_col: str, lx_coord: float = 0.0, ly_coord: float = 0.0):
        """
        VILLAIN: the original hooded trapezoid eye (wide flat hood on top, narrow flat bottom, rough raw-pixel strokes),
        made sharper and meaner in the steel + molten-amber palette: the hood slopes down toward the nose, each outer
        corner ends in a blade spike, a vertical viper slit burns in the middle, CRT lines run through the socket,
        and the whole eye randomly dims or cuts out for a frame (hacked-signal flicker).
        """
        if hasattr(self.canvas, "set_rough_mode"):
            self.canvas.set_rough_mode(True)
        scale = self.ui_scale / 1.8
        now = time.time()
        v = self._vil
        rng = v["rng"]
        tear_dx = v["tear_dx"] if now < v["tear_end"] else 0.0
        pulse = math.sin(self.anim_phase * 14.0)
        flick = math.sin(self.anim_phase * 38.0)
        glitch_dx = (4.5 * scale * math.sin(self.anim_phase * 29.0)) if abs(flick) > 0.35 else (2.2 * scale)
        close = self._villain_closure(now)
        dim = rng.random() < 0.10

        for cx in (lx, rx):
            is_left = (cx == lx)
            o = -1.0 if is_left else 1.0          # direction toward the outer edge of the face
            w_half = ew * 0.48
            top_y = cy - eh * 0.17 + close * eh * 0.12
            bot_y = cy + eh * 0.25
            bw = w_half * 0.60                    # narrow flat bottom
            o_ty = top_y - 5 * scale              # outer top corner sits higher...
            i_ty = top_y + 17 * scale             # ...inner corner drops toward the nose: a cold, menacing slope
            ox, ix = cx + o * w_half, cx - o * w_half
            obx, ibx = cx + o * bw, cx - o * bw
            quad = [ox, o_ty, ix, i_ty, ibx, bot_y, obx, bot_y]
            mid_y = (i_ty + bot_y) / 2.0

            def infl(kx, ky, pts=quad):
                out = []
                for k in range(0, len(pts), 2):
                    out += [cx + (pts[k] - cx) * kx, mid_y + (pts[k + 1] - mid_y) * ky]
                return out

            if tear_dx:   # channel-offset ghosts only while the raster tears
                for col, off in (("#1fb5c7", -tear_dx * 0.7), (VIL_EMBER, tear_dx * 0.7)):
                    shifted = [c + (off if i % 2 == 0 else 0.0) for i, c in enumerate(quad)]
                    self.canvas.create_line(shifted + shifted[:2], smooth=False, fill=col, width=max(2, int(2.6 * scale)))

            self.canvas.create_polygon(infl(1.13, 1.32), smooth=False, fill="#1d0c03", outline="")
            self.canvas.create_polygon(infl(1.06, 1.14), smooth=False, fill=glow_col, outline="")
            # blade spike on the outer corner
            self.canvas.create_polygon(
                [cx + o * (w_half - 10 * scale), o_ty, cx + o * (w_half + 34 * scale), o_ty + 26 * scale, cx + o * (w_half - 2 * scale), o_ty + 18 * scale],
                smooth=False, fill=VIL_AMBER if not dim else VIL_EMBER, outline="")
            self.canvas.create_polygon(quad, smooth=False, fill="#100601", outline="")
            self.canvas.create_polygon(infl(0.86, 0.80), smooth=False, fill="#1a0a02" if dim else "#3d1704", outline="")

            # CRT phosphor lines through the socket, following the slanted edges
            for n in range(1, 8):
                y = i_ty + 4 * scale + (bot_y - i_ty - 8 * scale) * n / 8.0
                t_o = (y - o_ty) / max(1.0, bot_y - o_ty)
                t_i = (y - i_ty) / max(1.0, bot_y - i_ty)
                xa = ox + (obx - ox) * t_o
                xb = ix + (ibx - ix) * t_i
                self.canvas.create_line(xa - o * 4 * scale, y, xb + o * 4 * scale, y, fill="#5a2406" if n % 2 == 0 else "#2a1103", width=max(1, int(1.5 * scale)))

            # viper slit pupil (cuts out entirely for a frame now and then)
            if rng.random() >= 0.05:
                slit_y = mid_y + ly_coord * 6 * scale
                slit_cx = cx + lx_coord * 10 * scale
                slit_hw = w_half * (0.40 + 0.07 * pulse)
                vh = (bot_y - i_ty) * 0.36
                self.canvas.create_line(slit_cx - slit_hw - glitch_dx, slit_y - 2 * scale, slit_cx + slit_hw - glitch_dx, slit_y - 2 * scale, fill="#b24a0b", width=max(1, int(2.4 * scale)))
                self.canvas.create_line(slit_cx - slit_hw - 3 * scale, slit_y, slit_cx + slit_hw + 3 * scale, slit_y, fill="#6b2a06", width=int(8 * scale))
                self.canvas.create_line(slit_cx - slit_hw, slit_y, slit_cx + slit_hw, slit_y, fill=VIL_AMBER, width=max(2, int(3.8 * scale)))
                self.canvas.create_line(slit_cx - slit_hw * 0.7, slit_y, slit_cx + slit_hw * 0.7, slit_y, fill=VIL_AMBER_HOT, width=max(1, int(1.8 * scale)))
                self.canvas.create_line(slit_cx, slit_y - vh, slit_cx, slit_y + vh, fill="#fff1cf" if flick > 0.55 else VIL_AMBER, width=max(2, int(3.4 * scale)))
                self.canvas.create_rectangle(slit_cx - 4 * scale, slit_y - 3 * scale, slit_cx + 4 * scale, slit_y + 3 * scale, fill="#ffffff", outline=VIL_AMBER, width=1)

            # rough hand-sketched outline: ghost, main stroke, jittered over-stroke, bottom corner ticks
            lower = [ox, o_ty, obx, bot_y, ibx, bot_y, ix, i_ty]
            self.canvas.create_line([c - (glitch_dx if i % 2 == 0 else -2 * scale) for i, c in enumerate(lower)], smooth=False, fill="#b24a0b", width=max(2, int(3.0 * scale)))
            self.canvas.create_line(lower, smooth=False, fill=main_col if not dim else VIL_EMBER, width=int(5.8 * scale))
            j1 = math.sin(self.anim_phase * 31.0 + (1.0 if is_left else 2.5)) * 2.2 * scale
            j2 = math.cos(self.anim_phase * 27.0 + (2.0 if is_left else 0.5)) * 2.2 * scale
            self.canvas.create_line([ox + o * 2 * scale, o_ty + j1, obx + o * 3 * scale, bot_y - 2 * scale + j2, ibx - o * 3 * scale, bot_y + 2 * scale - j1, ix - o * 2 * scale, i_ty - j2],
                                    smooth=False, fill="#ffd9a8", width=max(1, int(2.2 * scale)))
            self.canvas.create_line(obx + o * 6 * scale, bot_y, obx - o * 8 * scale, bot_y, fill=main_col, width=max(2, int(4 * scale)))
            self.canvas.create_line(ibx - o * 6 * scale, bot_y, ibx + o * 8 * scale, bot_y, fill=main_col, width=max(2, int(4 * scale)))

            # heavy hood bar along the slanted top, steel brow plate above it
            hx0, hx1 = ox + o * 26 * scale, ix
            self.canvas.create_line(hx0 - glitch_dx, o_ty - 2 * scale, hx1 - glitch_dx, i_ty - 2 * scale, fill="#b24a0b", width=max(2, int(3 * scale)))
            self.canvas.create_line(hx0, o_ty, hx1, i_ty, fill=main_col if not dim else VIL_EMBER, width=int(6.8 * scale))
            self.canvas.create_line(hx0 + o * -4 * scale, o_ty + 2.5 * scale + j1 * 0.5, hx1 - o * 4 * scale * -1, i_ty - 2 * scale - j2 * 0.5, fill=VIL_CHROME, width=max(1, int(2 * scale)))
            self.canvas.create_line(hx0, o_ty - 12 * scale, hx1, i_ty - 10 * scale, fill=VIL_STEEL, width=max(2, int(3 * scale)))

    def _draw_excited_eyes(self, lx: float, rx: float, cy: float, ew: float, eh: float, main_col: str, glow_col: str, look_x: float, look_y: float):
        """
        12. EXCITED: Starstruck Golden Bordered Optical Eyes with seamless upward-curved bottom eyelids
        (`smile_bottom=True`) and giant glowing 4-point golden-white starbursts (`✦`) inside!
        """
        scale = self.ui_scale / 1.8
        self._draw_standard_eye(lx, cy, ew, eh, main_col, glow_col, look_x, look_y, smile_bottom=True, draw_iris=False)
        self._draw_standard_eye(rx, cy, ew, eh, main_col, glow_col, look_x, look_y, smile_bottom=True, draw_iris=False)
        self._draw_cyber_blush(lx, rx, cy + eh * 0.54, scale, base_col="#ff4d88", outward_shift=38 * scale)

        star_pulse = 1.0 + 0.16 * math.sin(self.anim_phase * 8.0)
        for cx in (lx, rx):
            icx = cx + look_x * 12.0 * scale
            icy = cy + look_y * 9.0 * scale - 10.0 * scale
            self._draw_sparkle(icx, icy, 38.0 * scale * star_pulse, main_col, "#ffffff")
            self._draw_sparkle(icx - 24 * scale, icy - 16 * scale, 10.0 * scale, "#ffffff")
            self._draw_sparkle(icx + 24 * scale, icy + 12 * scale, 8.5 * scale, "#fde047")

        self._draw_sparkle(lx - ew * 0.62, cy - eh * 0.28, 11.0 * scale * star_pulse, "#fde047")
        self._draw_sparkle(rx + ew * 0.62, cy - eh * 0.28, 11.0 * scale * star_pulse, "#fde047")

    def _draw_laughing_eyes(self, lx: float, rx: float, cy: float, ew: float, eh: float, main_col: str, glow_col: str):
        """
        13. LAUGHING: Joyful squeezed-shut tangerine-gold chevron eyes (>   <) with multi-tier neon bloom,
        glossy white upper-arm highlight, flying sky-blue joy-teardrop beads, and /// blush!
        """
        scale = self.ui_scale / 1.8
        self._draw_cyber_blush(lx, rx, cy + eh * 0.36, scale, base_col="#ff5588", outward_shift=16 * scale)

        w_half = ew * 0.44
        h_half = eh * 0.32

        pts_l = [lx - w_half, cy - h_half, lx + w_half * 0.85, cy, lx - w_half, cy + h_half]
        pts_r = [rx + w_half, cy - h_half, rx - w_half * 0.85, cy, rx + w_half, cy + h_half]

        for pts in (pts_l, pts_r):
            self.canvas.create_line(pts, fill=glow_col, width=int(32 * scale), capstyle=tk.ROUND, joinstyle=tk.ROUND)
            self.canvas.create_line(pts, fill="#ea580c", width=int(21 * scale), capstyle=tk.ROUND, joinstyle=tk.ROUND)
            self.canvas.create_line(pts, fill="#ffbe0b", width=int(13 * scale), capstyle=tk.ROUND, joinstyle=tk.ROUND)
            self.canvas.create_line(pts[:4], fill="#ffffff", width=max(2, int(4.5 * scale)), capstyle=tk.ROUND)

        for side, tx in [(-1, lx - w_half - 12 * scale), (1, rx + w_half + 12 * scale)]:
            ty = cy + h_half * 0.35
            tr = 7.5 * scale
            self.canvas.create_oval(tx - tr, ty - tr, tx + tr, ty + tr, fill="#38bdf8", outline="#ffffff", width=max(1, int(1.5 * scale)))

    def _draw_love_eyes(self, lx: float, rx: float, cy: float, ew: float, eh: float, main_col: str, glow_col: str, look_x: float, look_y: float):
        """
        14. LOVE ("Love is good but reflection like claude would be cool."):
        Frameless Bordered Neon-Rose Heart Optics (♥   ♥) WITH Claude-style glowing horizontal
        floor reflection pads directly underneath the bottom point of each heart + crisp upper-lobe reflections!
        """
        scale = self.ui_scale / 1.8
        beat = 1.0 + 0.08 * math.sin(self.anim_phase * 6.5)

        def _heart_poly(hcx: float, hcy: float, hs: float) -> List[float]:
            pts = []
            for i in range(120):
                t = (i / 120.0) * 2.0 * math.pi
                hx = 16.0 * (math.sin(t) ** 3)
                hy = -(13.0 * math.cos(t) - 5.0 * math.cos(2 * t) - 2.0 * math.cos(3 * t) - math.cos(4 * t))
                pts.extend([hcx + hx * hs, hcy + hy * hs])
            return pts

        for cx in (lx, rx):
            hcx = cx + look_x * 10.0 * scale
            hcy = cy + look_y * 8.0 * scale - 4 * scale

            ref_y = hcy + 98.0 * scale
            ref_w = 64.0 * scale * beat
            ref_h = 14.0 * scale * beat
            for r_m, r_col in [(1.15, "#2b0618"), (0.82, "#590d32"), (0.52, "#b81d65"), (0.26, "#ff75b5")]:
                self.canvas.create_oval(
                    hcx - ref_w * r_m, ref_y - ref_h * r_m,
                    hcx + ref_w * r_m, ref_y + ref_h * r_m,
                    fill=r_col, outline=""
                )

            self.canvas.create_polygon(_heart_poly(hcx, hcy, 6.2 * scale * beat), smooth=False, fill=glow_col, outline="")
            self.canvas.create_polygon(_heart_poly(hcx, hcy, 5.4 * scale * beat), smooth=False, fill=main_col, outline="")
            self.canvas.create_polygon(_heart_poly(hcx, hcy, 4.4 * scale * beat), smooth=False, fill="#e11d74", outline="#ff9ebb", width=max(1, int(2.0 * scale)))
            self.canvas.create_polygon(_heart_poly(hcx, hcy + 2 * scale, 2.8 * scale * beat), smooth=False, fill="#ff4d94", outline="")

            self.canvas.create_oval(
                hcx - 52 * scale * beat, hcy - 48 * scale * beat,
                hcx - 22 * scale * beat, hcy - 22 * scale * beat,
                fill="#ffffff", outline=""
            )
            self.canvas.create_oval(
                hcx - 16 * scale * beat, hcy - 44 * scale * beat,
                hcx - 4 * scale * beat, hcy - 32 * scale * beat,
                fill="#ffffff", outline=""
            )
            self.canvas.create_oval(
                hcx + 24 * scale * beat, hcy - 36 * scale * beat,
                hcx + 38 * scale * beat, hcy - 22 * scale * beat,
                fill="#ffd1e6", outline=""
            )

        for side, fx in [(-1, lx - ew * 0.62), (1, rx + ew * 0.62)]:
            fy = cy - eh * 0.28 + math.sin(self.anim_phase * 4.0 + side) * (6.0 * scale)
            self.canvas.create_polygon(_heart_poly(fx, fy, 1.35 * scale), smooth=False, fill="#ff75b5", outline="")

    def _draw_wink_eyes(self, lx: float, rx: float, cy: float, ew: float, eh: float, main_col: str, glow_col: str, look_x: float, look_y: float):
        """
        15. WINK: Left open eye is a sleek bordered turquoise-mint optical lens WITH a seamless upward-curved bottom (`smile_bottom=True`)!
        Right eye is a joyful multi-tier neon wink arch (`∩`) with outer lash flick & popping star (`✦`).
        """
        scale = self.ui_scale / 1.8
        self._draw_standard_eye(lx, cy, ew, eh, main_col, glow_col, look_x, look_y, smile_bottom=True)
        self._draw_cyber_blush(lx, rx, cy + eh * 0.54, scale, base_col="#ff4d88", outward_shift=36 * scale)

        w_half = ew * 0.45
        h_arch = eh * 0.30
        wy = cy + 8 * scale
        pts = []
        for i in range(21):
            ang = math.pi - (i / 20.0) * math.pi
            pts.extend([rx + w_half * math.cos(ang), wy - h_arch * math.sin(ang)])
        pts.extend([rx + w_half + 14 * scale, wy - 10 * scale])

        self.canvas.create_line(pts, smooth=True, fill=glow_col, width=int(26 * scale), capstyle=tk.ROUND)
        self.canvas.create_line(pts, smooth=True, fill="#00b4d8", width=int(16 * scale), capstyle=tk.ROUND)
        self.canvas.create_line(pts, smooth=True, fill=main_col, width=int(10 * scale), capstyle=tk.ROUND)
        self.canvas.create_line(pts[12:30], smooth=True, fill="#ffffff", width=max(1, int(3.2 * scale)), capstyle=tk.ROUND)
        self._draw_sparkle(rx + ew * 0.62, cy - eh * 0.16, 13.5 * scale, "#fde047", "#ffffff")

    def _draw_surprised_eyes(self, lx: float, rx: float, cy: float, ew: float, eh: float, main_col: str, glow_col: str, look_x: float, look_y: float):
        """
        16. SURPRISED: Circular Electric Ice-Blue Bordered Shock Orbs (O   O) with vibrating
        concentric shockwave rings, tiny contracted pinpoint pupils, and radial exclamation rays!
        """
        scale = self.ui_scale / 1.8
        r_orb = min(ew, eh) * 0.50
        jitter_x = math.sin(self.anim_phase * 18.0) * (1.2 * scale)

        for cx in (lx, rx):
            self.canvas.create_oval(cx - r_orb - 10 * scale, cy - r_orb - 10 * scale, cx + r_orb + 10 * scale, cy + r_orb + 10 * scale, fill=glow_col, outline="")
            self.canvas.create_oval(cx - r_orb, cy - r_orb, cx + r_orb, cy + r_orb, fill="#040b16", outline=main_col, width=int(6.5 * scale))
            for r_mult, r_col in [(0.68, "#0284c7"), (0.44, "#38bdf8")]:
                rr = r_orb * r_mult
                self.canvas.create_oval(cx + jitter_x - rr, cy - rr, cx + jitter_x + rr, cy + rr, fill="", outline=r_col, width=int(2.2 * scale))
            pr = r_orb * 0.16
            self.canvas.create_oval(cx + jitter_x - pr, cy - pr, cx + jitter_x + pr, cy + pr, fill="#ffffff", outline=main_col, width=int(2 * scale))
            self.canvas.create_oval(cx - r_orb * 0.58, cy - r_orb * 0.58, cx - r_orb * 0.22, cy - r_orb * 0.30, fill="#ffffff", outline="")

        mid_x = (lx + rx) / 2.0
        ray_base_y = cy - r_orb * 1.04
        for ang_deg in (-32, 0, 32):
            rad_a = math.radians(ang_deg - 90)
            rx1 = mid_x + math.cos(rad_a) * (12 * scale)
            ry1 = ray_base_y + math.sin(rad_a) * (12 * scale)
            rx2 = mid_x + math.cos(rad_a) * (28 * scale)
            ry2 = ray_base_y + math.sin(rad_a) * (28 * scale)
            self.canvas.create_line(rx1, ry1, rx2, ry2, fill="#fde047", width=max(2, int(3.8 * scale)), capstyle=tk.ROUND)

    def _draw_sleepy_eyes(self, lx: float, rx: float, cy: float, ew: float, eh: float, main_col: str, glow_col: str):
        """
        17. SLEEPY: Heavy-lidded dreamy lavender bordered eyes where a curved drowsy upper eyelid
        droops 65% down across the eye, leaving a dim sleepy crescent of the iris below + cascading Zzz!
        """
        scale = self.ui_scale / 1.8
        drift = math.sin(self.anim_phase * 1.1) * (3.0 * scale)
        ey = cy + drift

        # Yawn: the lids close over the eyes, which then squeeze into curved "^" arcs while the mouth opens wide
        yawn = self._yawn_openness()
        if yawn > 0.05:
            squeeze = min(1.0, yawn / 0.35)
            if squeeze < 1.0:
                eh_y = eh * 0.90 * (1.0 - 0.85 * squeeze)
                self._draw_standard_eye(lx, ey, ew, eh_y, main_col, glow_col, 0.0, 0.28, draw_catchlights=False)
                self._draw_standard_eye(rx, ey, ew, eh_y, main_col, glow_col, 0.0, 0.28, draw_catchlights=False)
            else:
                for cx in (lx, rx):
                    arc = [
                        cx - ew * 0.42, ey + 8 * scale,
                        cx, ey - 10 * scale,
                        cx + ew * 0.42, ey + 8 * scale,
                    ]
                    self.canvas.create_line(arc, smooth=True, fill=glow_col, width=int(12 * scale), capstyle=tk.ROUND)
                    self.canvas.create_line(arc, smooth=True, fill=main_col, width=int(6 * scale), capstyle=tk.ROUND)
                    self.canvas.create_line(arc, smooth=True, fill="#e0e7ff", width=max(1, int(2 * scale)), capstyle=tk.ROUND)
            return

        self._draw_standard_eye(lx, ey, ew, eh * 0.90, main_col, glow_col, 0.0, 0.28, draw_catchlights=False)
        self._draw_standard_eye(rx, ey, ew, eh * 0.90, main_col, glow_col, 0.0, 0.28, draw_catchlights=False)

        eh_s = eh * 0.90
        lid_y = ey + eh_s * 0.10
        for cx in (lx, rx):
            mask_pts = [
                cx - ew / 2.0 - 14 * scale, ey - eh_s / 2.0 - 14 * scale,
                cx + ew / 2.0 + 14 * scale, ey - eh_s / 2.0 - 14 * scale,
                cx + ew / 2.0 + 14 * scale, lid_y - 6 * scale,
                cx, lid_y + 12 * scale,
                cx - ew / 2.0 - 14 * scale, lid_y - 6 * scale,
            ]
            self.canvas.create_polygon(mask_pts, smooth=True, fill=self.bg_color, outline="")
            lid_line = [
                cx - ew * 0.46, lid_y - 6 * scale,
                cx, lid_y + 12 * scale,
                cx + ew * 0.46, lid_y - 6 * scale,
            ]
            self.canvas.create_line(lid_line, smooth=True, fill=glow_col, width=int(12 * scale), capstyle=tk.ROUND)
            self.canvas.create_line(lid_line, smooth=True, fill=main_col, width=int(6 * scale), capstyle=tk.ROUND)
            self.canvas.create_line(lid_line, smooth=True, fill="#e0e7ff", width=max(1, int(2 * scale)), capstyle=tk.ROUND)

        z_specs = [(24, 15, -14), (48, 20, -40), (76, 26, -70)]
        for idx, (dx, f_pt, y_off) in enumerate(z_specs):
            bob = math.sin(self.anim_phase * 2.2 + idx * 1.1) * (4.0 * scale)
            zx = rx + ew * 0.46 + dx * scale
            zy = cy + y_off * scale + bob
            self.canvas.create_text(zx, zy, text="Z", fill="#e0e7ff" if idx == 2 else main_col, font=(FONT_FAMILY, int(f_pt * scale), "bold"))

    def _draw_shy_eyes(self, lx: float, rx: float, cy: float, ew: float, eh: float, main_col: str, glow_col: str):
        """
        18. SHY ("Make shy a Little more shy with blush.."):
        Soft sakura-coral bordered optical eyes with deeper bashful outer-slanted upper lids,
        averted quivering pupils tucked down-inward, extra-large 1.38x glowing rose-pink cheek blush
        cushions (////) PLUS cute across-the-nose bridge blush strokes, and a bashful sweat drop!
        """
        scale = self.ui_scale / 1.8
        self._draw_standard_eye(lx, cy, ew * 0.94, eh * 0.92, main_col, glow_col, -0.32, 0.28, smile_bottom=False, catchlight_dy=24 * scale)
        self._draw_standard_eye(rx, cy, ew * 0.94, eh * 0.92, main_col, glow_col, -0.32, 0.28, smile_bottom=False, catchlight_dy=24 * scale)

        sw, sh = ew * 0.94, eh * 0.92
        for side, cx in [(-1, lx), (1, rx)]:
            top_in = cy - sh * 0.36
            top_out = cy - sh * 0.04
            tl = top_out if side == -1 else top_in
            tr = top_in if side == -1 else top_out
            mask = [
                cx - sw / 2.0 - 12 * scale, cy - sh / 2.0 - 14 * scale,
                cx + sw / 2.0 + 12 * scale, cy - sh / 2.0 - 14 * scale,
                cx + sw / 2.0 + 12 * scale, tr,
                cx - sw / 2.0 - 12 * scale, tl,
            ]
            self.canvas.create_polygon(mask, fill=self.bg_color, outline="")
            self.canvas.create_line(cx - sw * 0.46, tl, cx + sw * 0.46, tr, fill=main_col, width=int(6.5 * scale), capstyle=tk.ROUND)

        self._draw_cyber_blush(
            lx, rx, cy + eh * 0.54, scale,
            base_col="#ff2a85", outward_shift=22 * scale,
            size_mult=1.38, extra_slashes=True
        )

        mid_x = (lx + rx) / 2.0
        bridge_y = cy + eh * 0.24
        self.canvas.create_oval(
            mid_x - 32 * scale, bridge_y - 10 * scale,
            mid_x + 32 * scale, bridge_y + 10 * scale,
            fill=lerp_color(self.bg_color, "#ff2a85", 0.32), outline=""
        )
        for b_i in (-1, 0, 1):
            bx_s = mid_x + b_i * (11.0 * scale)
            self.canvas.create_line(
                bx_s - 3 * scale, bridge_y + 4.5 * scale,
                bx_s + 3 * scale, bridge_y - 4.5 * scale,
                fill="#ff9ebb", width=max(1, int(2.2 * scale)), capstyle=tk.ROUND
            )

        sx = lx - ew * 0.58
        sy = cy - eh * 0.16
        sr = 9.0 * scale
        self.canvas.create_polygon([sx - sr, sy, sx, sy - sr * 2.0, sx + sr, sy], fill="#7dd3fc", outline="")
        self.canvas.create_oval(sx - sr, sy - sr, sx + sr, sy + sr, fill="#7dd3fc", outline="#ffffff", width=1)

    def _draw_proud_eyes(self, lx: float, rx: float, cy: float, ew: float, eh: float, main_col: str, glow_col: str, look_x: float = 0.0, look_y: float = 0.0):
        """
        19. PROUD ("Proud does not look proud enough, I don't want the crown, I want a smirk and that look in the eyes."):
        ZERO crown! Confident, smug-heroic Royal-Gold Bordered Optical Eyes:
          - Seamless upward-curved smiling lower eyelids (`smile_bottom=True`),
          - Confident, self-assured half-hooded upper eyelids angled with swagger,
          - Warm glowing golden irises with a bright 4-point star glint inside!
        """
        scale = self.ui_scale / 1.8
        self._draw_standard_eye(lx, cy, ew, eh, main_col, glow_col, 0.12, -0.05, smile_bottom=True, catchlight_dy=14 * scale)
        self._draw_standard_eye(rx, cy, ew, eh, main_col, glow_col, 0.12, -0.05, smile_bottom=True, catchlight_dy=14 * scale)

        for side, cx in [(-1, lx), (1, rx)]:
            lid_in = cy - eh * 0.16
            lid_out = cy - eh * 0.24
            tl = lid_out if side == -1 else lid_in
            tr = lid_in if side == -1 else lid_out
            mask = [
                cx - ew / 2.0 - 14 * scale, cy - eh / 2.0 - 14 * scale,
                cx + ew / 2.0 + 14 * scale, cy - eh / 2.0 - 14 * scale,
                cx + ew / 2.0 + 14 * scale, tr,
                cx - ew / 2.0 - 14 * scale, tl,
            ]
            self.canvas.create_polygon(mask, fill=self.bg_color, outline="")
            self.canvas.create_line(cx - ew * 0.48, tl, cx + ew * 0.48, tr, fill=glow_col, width=int(12 * scale), capstyle=tk.ROUND)
            self.canvas.create_line(cx - ew * 0.48, tl, cx + ew * 0.48, tr, fill=main_col, width=int(6.5 * scale), capstyle=tk.ROUND)
            self.canvas.create_line(cx - ew * 0.34, tl + (tr - tl) * 0.15, cx + ew * 0.34, tr - (tr - tl) * 0.15, fill="#fef08a", width=max(1, int(2.2 * scale)), capstyle=tk.ROUND)

        self._draw_sparkle(rx + ew * 0.60, cy - eh * 0.22, 10.5 * scale, "#fde047", "#ffffff")

    def _draw_curious_eyes(self, lx: float, rx: float, cy: float, ew: float, eh: float, main_col: str, glow_col: str, look_x: float, look_y: float):
        """
        20. CURIOUS ("curious should be more like surpriced but with flickering light bulb , the idea one.. and a glow in the eyes.. and an O mouth.."):
        Wide, circular/super-ellipse Surprised-Style Bordered Optical Eyes (right eye slightly wider in fascination)
        with a RADIANT MULTI-LAYER INNER GLOW in the eyes, plus a brightly flickering Idea Lightbulb (💡) at the top-right!
        """
        scale = self.ui_scale / 1.8
        for cx, sc_m in [(lx, 1.00), (rx, 1.08)]:
            cw = ew * sc_m
            ch = eh * sc_m
            self._draw_standard_eye(cx, cy, cw, ch, main_col, glow_col, 0.14, -0.10, corner_r=int(cw * 0.46), draw_iris=False, draw_catchlights=False)

            icx = cx + 6.0 * scale
            icy = cy - 4.0 * scale
            pulse = 1.0 + 0.08 * math.sin(self.anim_phase * 6.0)
            r_max = min(cw, ch) * 0.38 * pulse
            for r_frac, g_col in [
                (1.00, "#064e3b"),
                (0.80, "#059669"),
                (0.58, "#10b981"),
                (0.38, "#6ee7b7"),
                (0.20, "#ffffff"),
            ]:
                rr = r_max * r_frac
                self.canvas.create_oval(icx - rr, icy - rr, icx + rr, icy + rr, fill=g_col, outline="")

            self._draw_sparkle(icx - r_max * 0.45, icy - r_max * 0.45, 9.5 * scale, "#ffffff")
            self.canvas.create_oval(cx - cw * 0.28, cy - ch * 0.30, cx - cw * 0.08, cy - ch * 0.16, fill="#ffffff", outline="")
            self.canvas.create_oval(cx + cw * 0.18, cy + ch * 0.16, cx + cw * 0.28, cy + ch * 0.26, fill="#a7f3d0", outline="")

        self._draw_flickering_lightbulb(rx + ew * 0.74, cy - eh * 0.42, scale * 1.12, mode="idea")

    def _draw_skeptical_eyes(self, lx: float, rx: float, cy: float, ew: float, eh: float, main_col: str, glow_col: str):
        """
        21. SKEPTICAL: Deadpan Half-Lidded Side-Eye with '...' temple dots!
        """
        scale = self.ui_scale / 1.8
        self._draw_standard_eye(lx, cy, ew, eh, main_col, glow_col, 0.34, 0.12, smile_bottom=False, catchlight_dy=28 * scale)
        self._draw_standard_eye(rx, cy, ew, eh, main_col, glow_col, 0.34, 0.0, smile_bottom=False)

        lid_y = cy + eh * 0.02
        self.canvas.create_rectangle(
            lx - ew / 2.0 - 14 * scale, cy - eh / 2.0 - 14 * scale,
            lx + ew / 2.0 + 14 * scale, lid_y,
            fill=self.bg_color, outline=""
        )
        self.canvas.create_line(lx - ew * 0.46, lid_y, lx + ew * 0.46, lid_y, fill=glow_col, width=int(12 * scale), capstyle=tk.ROUND)
        self.canvas.create_line(lx - ew * 0.46, lid_y, lx + ew * 0.46, lid_y, fill=main_col, width=int(6 * scale), capstyle=tk.ROUND)
        self.canvas.create_line(lx - ew * 0.32, lid_y, lx + ew * 0.32, lid_y, fill="#ecfccb", width=max(1, int(2 * scale)), capstyle=tk.ROUND)

        for d_i in range(3):
            dx = lx - ew * 0.66 - d_i * (12 * scale)
            dy = cy - eh * 0.26
            self.canvas.create_oval(dx - 3.5 * scale, dy - 3.5 * scale, dx + 3.5 * scale, dy + 3.5 * scale, fill="#a3e635", outline="")

    def _draw_cool_eyes(self, lx: float, rx: float, cy: float, ew: float, eh: float, main_col: str, glow_col: str, look_x: float = 0.0, look_y: float = 0.0):
        """
        22. COOL ("ALSO I WANT A COOL EXPRESSION LIKE CLAUDE but in YOUR design sceme, with the borders and all.. Or maybe same as claude but BETTER.."):
        Sleek Bordered Neon-Cyan Cyber-Aviator Sunglasses Visor:
          - Wide, flat-topped aviator-squircle bordered lenses with our signature glowing neon rim & dark polarized chamber,
          - Connected across the bridge by a glowing double-bar nose bridge + angled outer temple arms,
          - Claude-style upper translucent glass reflection band + diagonal speed-sheen slashes (//),
          - Subtle glowing cyan iris rings peeking through the dark tint + a flashing star glint on the frame corner!
        """
        scale = self.ui_scale / 1.8
        gw = ew * 1.08
        gh = eh * 0.72
        gy_c = cy + 2 * scale

        arm_y1 = gy_c - gh * 0.36
        arm_y2 = gy_c - gh * 0.56
        self.canvas.create_line(lx - gw * 0.50, arm_y1, lx - gw * 0.68, arm_y2, fill=glow_col, width=int(12 * scale), capstyle=tk.ROUND)
        self.canvas.create_line(lx - gw * 0.50, arm_y1, lx - gw * 0.68, arm_y2, fill=main_col, width=int(5.5 * scale), capstyle=tk.ROUND)
        self.canvas.create_line(rx + gw * 0.50, arm_y1, rx + gw * 0.68, arm_y2, fill=glow_col, width=int(12 * scale), capstyle=tk.ROUND)
        self.canvas.create_line(rx + gw * 0.50, arm_y1, rx + gw * 0.68, arm_y2, fill=main_col, width=int(5.5 * scale), capstyle=tk.ROUND)

        br_x1 = lx + gw * 0.46
        br_x2 = rx - gw * 0.46
        br_y = gy_c - gh * 0.28
        self.canvas.create_line(br_x1, br_y, br_x2, br_y, fill=glow_col, width=int(14 * scale), capstyle=tk.ROUND)
        self.canvas.create_line(br_x1, br_y, br_x2, br_y, fill=main_col, width=int(6.5 * scale), capstyle=tk.ROUND)
        self.canvas.create_line(br_x1, br_y - 2 * scale, br_x2, br_y - 2 * scale, fill="#ffffff", width=max(1, int(2.0 * scale)), capstyle=tk.ROUND)

        for cx in (lx, rx):
            x1, y1 = cx - gw / 2.0, gy_c - gh / 2.0
            x2, y2 = cx + gw / 2.0, gy_c + gh / 2.0
            rad_g = int(gh * 0.36)

            self._create_rounded_rect(x1 - 8 * scale, y1 - 8 * scale, x2 + 8 * scale, y2 + 8 * scale, rad_g + int(6 * scale), fill=lerp_color(self.bg_color, main_col, 0.22), outline="")
            self._create_rounded_rect(x1, y1, x2, y2, rad_g, fill="#030712", outline=main_col, width=int(6.0 * scale))
            self._create_rounded_rect(x1 + 5 * scale, y1 + 5 * scale, x2 - 5 * scale, y2 - 5 * scale, max(4, rad_g - int(4 * scale)), fill="#040a18", outline="#0c3b5e", width=max(1, int(1.8 * scale)))

            icx = cx + look_x * 10.0 * scale
            icy = gy_c + 4 * scale + look_y * 6.0 * scale
            r_ir = gh * 0.24
            self.canvas.create_oval(icx - r_ir, icy - r_ir, icx + r_ir, icy + r_ir, fill="#05182b", outline="#0284c7", width=max(1, int(2.0 * scale)))
            self.canvas.create_oval(icx - 4.5 * scale, icy - 4.5 * scale, icx + 4.5 * scale, icy + 4.5 * scale, fill="#38bdf8", outline="")

            band_pad = 9.0 * scale
            band_h = gh * 0.32
            self._create_rounded_rect(
                x1 + band_pad, y1 + band_pad,
                x2 - band_pad, y1 + band_pad + band_h,
                int(band_h * 0.42), fill="#0d253f", outline=""
            )
            self.canvas.create_oval(
                x1 + 18 * scale, y1 + 14 * scale,
                x1 + 42 * scale, y1 + 23 * scale,
                fill="#e0f2fe", outline=""
            )

            sh_x = cx + 14 * scale + math.sin(self.anim_phase * 2.5) * (6.0 * scale)
            self.canvas.create_line(sh_x - 12 * scale, y2 - 12 * scale, sh_x + 10 * scale, y1 + 12 * scale, fill="#38bdf8", width=max(1, int(3.0 * scale)), capstyle=tk.ROUND)
            self.canvas.create_line(sh_x, y2 - 12 * scale, sh_x + 22 * scale, y1 + 12 * scale, fill="#bae6fd", width=max(1, int(1.8 * scale)), capstyle=tk.ROUND)

        self._draw_sparkle(rx + gw * 0.44, gy_c - gh * 0.44, 11.0 * scale, "#ffffff", "#00f0ff")

    # =========================================================================
    # MOUTH & CENTER ANIMATIONS (ALL 22 STATES)
    # =========================================================================
    def _draw_happy_mouth(self, cx: float, cy: float, col: str):
        scale = self.ui_scale / 1.8
        bounce = math.sin(self.anim_phase * 6.0) * (2.8 * scale)
        mouth_cy = cy + bounce - int(6 * scale)
        mw = int(112 * scale)
        mh = int(20 * scale * self._lip_sync_mod(0.74, 1.38))

        pts = []
        num_pts = 17
        for i in range(num_pts):
            t = (i / (num_pts - 1)) * 2.0 - 1.0
            px = cx + t * (mw / 2.0)
            py = mouth_cy + (1.0 - t * t) * mh
            pts.extend([px, py])

        self.canvas.create_line(pts, smooth=True, fill="#003d22", width=int(16 * scale), capstyle=tk.ROUND)
        self.canvas.create_line(pts, smooth=True, fill="#00cc66", width=int(10 * scale), capstyle=tk.ROUND)
        self.canvas.create_line(pts, smooth=True, fill=col, width=int(6 * scale), capstyle=tk.ROUND)
        self.canvas.create_line(pts[5 * 2 : 12 * 2], smooth=True, fill="#ffffff", width=max(1, int(2.4 * scale)), capstyle=tk.ROUND)

    def _draw_sad_mouth(self, cx: float, cy: float, col: str):
        scale = self.ui_scale / 1.8
        tremble = math.sin(self.anim_phase * 10.0) * (1.8 * scale)
        m_y = cy - 4 * scale + tremble
        mw = int(84 * scale)
        mh = int(20 * scale * self._lip_sync_mod(0.78, 1.32))
        pts = [
            cx - mw / 2.0, m_y + mh,
            cx - mw * 0.28, m_y + mh * 0.30,
            cx, m_y,
            cx + mw * 0.28, m_y + mh * 0.30,
            cx + mw / 2.0, m_y + mh,
        ]
        self.canvas.create_line(pts, smooth=True, fill="#0e2447", width=int(14 * scale), capstyle=tk.ROUND)
        self.canvas.create_line(pts, smooth=True, fill=col, width=int(6 * scale), capstyle=tk.ROUND)
        self.canvas.create_line(pts[2:8], smooth=True, fill="#bae6fd", width=max(1, int(1.8 * scale)), capstyle=tk.ROUND)

    def _draw_idle_mouth(self, cx: float, cy: float, col: str):
        scale = self.ui_scale / 1.8
        breathe = math.sin(self.anim_phase * 1.8) * (1.5 * scale)
        m_y = cy + breathe - int(4 * scale)
        w = int(98 * scale)
        h = int(12 * scale * self._lip_sync_mod(0.75, 1.48))

        pts = []
        num_pts = 15
        for i in range(num_pts):
            t = (i / (num_pts - 1)) * 2.0 - 1.0
            px = cx + t * (w / 2.0)
            py = m_y + (1.0 - t * t) * h
            pts.extend([px, py])

        self.canvas.create_line(pts, smooth=True, fill=self.color_eye_glow, width=int(12 * scale), capstyle=tk.ROUND)
        self.canvas.create_line(pts, smooth=True, fill=col, width=int(5.5 * scale), capstyle=tk.ROUND)
        self.canvas.create_line(pts[4 * 2 : 11 * 2], smooth=True, fill="#ffffff", width=max(1, int(2.0 * scale)), capstyle=tk.ROUND)

    def _draw_speaking_mouth(self, cx: float, cy: float, col: str):
        """
        7. SPEAKING Mouth ("In speaking I want music icons 🎶 coming out of the mouth, A COOL, TESTED, SEAMLESS, SMOOTH animation."):
        19-band reactive voice frequency equalizer WITH a continuous, seamless stream of glowing
        vector musical notes (`♫` and `♪`) floating smoothly out of both sides of the mouth!
        """
        scale = self.ui_scale / 1.8
        base_w = int(196 * self.ui_scale)

        for w_idx in range(2):
            wave_phase = (self.anim_phase * 2.2 + w_idx * 0.5) % 1.0
            wave_r = (30 + wave_phase * 58.0) * scale
            wave_alpha = max(0.0, 1.0 - wave_phase)
            wave_col = lerp_color(self.bg_color, "#00f0ff", wave_alpha * 0.45 * self.speaking_intensity)
            if wave_alpha > 0.05 and self.speaking_intensity > 0.2:
                self.canvas.create_arc(
                    cx - wave_r, cy - wave_r * 0.38,
                    cx + wave_r, cy + wave_r * 0.38,
                    start=195, extent=150, style=tk.ARC, width=int(2 * scale), outline=wave_col
                )

        self.canvas.create_line(cx - base_w / 2.0, cy, cx + base_w / 2.0, cy, fill="#092033", width=int(2.5 * scale))

        num_pins = 19
        mid_idx = num_pins // 2
        pin_spacing = int(9.8 * scale)
        start_x = cx - ((num_pins - 1) * pin_spacing) / 2.0

        live_bands = self.lip_sync_bands if (self.is_voice_playing and len(self.lip_sync_bands) == num_pins) else None
        for i in range(num_pins):
            dist_center = 1.0 - (abs(i - mid_idx) / float(mid_idx)) * 0.55
            pin_phase = i * 0.58
            if live_bands is not None:
                band_lvl = live_bands[i]
                shimmer = 0.78 + 0.22 * abs(math.sin(self.anim_phase * 9.0 + pin_phase))
                h_val = band_lvl * shimmer * 25.0 * dist_center * scale
            else:
                h_val = abs(math.sin(self.anim_phase * 7.5 + pin_phase)) * 23.0 * dist_center * self.speaking_intensity * scale
            pin_h = max(3.5 * scale, h_val + 3.5 * scale)
            px = start_x + i * pin_spacing
            pin_col = "#00f0ff" if i % 2 == 0 else "#00ffcc"

            self.canvas.create_line(px, cy - pin_h, px, cy + pin_h, fill=pin_col, width=int(4 * scale), capstyle=tk.ROUND)
            self.canvas.create_oval(px - 2 * scale, cy - pin_h - 2 * scale, px + 2 * scale, cy - pin_h + 2 * scale, fill="#ffffff", outline="")
            self.canvas.create_oval(px - 2 * scale, cy + pin_h - 2 * scale, px + 2 * scale, cy + pin_h + 2 * scale, fill="#ffffff", outline="")

        note_configs = [
            (1, 0.18, True, "#00f0ff"),
            (-1, 0.43, False, "#00ffaa"),
            (1, 0.68, False, "#38bdf8"),
            (-1, 0.91, True, "#00f0ff"),
        ]
        for side, phase_off, is_pair, n_col in note_configs:
            np = (self.anim_phase * 0.55 + phase_off) % 1.0
            env = math.sin(np * math.pi)
            if env > 0.08:
                nx = cx + side * ((64.0 + np * 92.0) * scale) + math.sin(np * 5.0 + side) * (8.0 * scale)
                ny = cy + (6.0 - np * 52.0) * scale
                nsz = (9.5 + 4.5 * env) * scale
                c_fg = lerp_color(self.bg_color, n_col, min(1.0, env * 1.25))
                c_gl = lerp_color(self.bg_color, n_col, env * 0.38)
                self._draw_music_note(nx, ny, nsz, c_fg, c_gl, beamed_pair=is_pair)

    def _draw_listening_mouth(self, cx: float, cy: float, col: str):
        scale = self.ui_scale / 1.8
        num_ripples = 4
        for r_idx in range(num_ripples):
            rip_t = (self.anim_phase * 1.5 + r_idx * (1.0 / num_ripples)) % 1.0
            rip_r = (12.0 + rip_t * 56.0) * scale
            rip_alpha = max(0.0, 1.0 - rip_t)
            rip_col = lerp_color(self.bg_color, "#00ffcc", rip_alpha * 0.75)
            rip_w = max(1, int((3.2 * (1.0 - rip_t * 0.5)) * scale))
            if rip_alpha > 0.05:
                self.canvas.create_oval(cx - rip_r, cy - rip_r * 0.48, cx + rip_r, cy + rip_r * 0.48, fill="", outline=rip_col, width=rip_w)

        sensor_r = 7.0 * scale
        self.canvas.create_oval(cx - sensor_r - 6 * scale, cy - sensor_r - 6 * scale, cx + sensor_r + 6 * scale, cy + sensor_r + 6 * scale, fill="#002b22", outline="")
        self.canvas.create_oval(cx - sensor_r, cy - sensor_r, cx + sensor_r, cy + sensor_r, fill="#00ffcc", outline="#ffffff", width=max(1, int(1.5 * scale)))

        for side in (-1, 1):
            dot_x = cx + side * (82 * scale)
            self.canvas.create_line(cx + side * (20 * scale), cy, dot_x, cy, fill="#004d3d", width=max(1, int(2 * scale)))
            for bar_i in range(5):
                bx = cx + side * ((28 + bar_i * 9) * scale)
                bh = (3.0 + abs(math.sin(self.anim_phase * 5.0 + bar_i * 0.7 + side)) * 9.5) * scale
                self.canvas.create_line(bx, cy - bh, bx, cy + bh, fill="#00ffcc", width=max(1, int(2.5 * scale)), capstyle=tk.ROUND)

    def _draw_thinking_mouth(self, cx: float, cy: float, col: str):
        scale = self.ui_scale / 1.8
        r = (9.0 + math.sin(self.anim_phase * 3.2) * 2.0) * scale
        self.canvas.create_oval(cx - r - 4 * scale, cy - r - 4 * scale, cx + r + 4 * scale, cy + r + 4 * scale, fill="#2b0a3d", outline="")
        self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r, fill=col, outline="")
        self.canvas.create_oval(cx - 3.5 * scale, cy - 3.5 * scale, cx + 3.5 * scale, cy + 3.5 * scale, fill="#ffffff", outline="")

        for d in range(3):
            wave_y = math.sin(self.anim_phase * 5.0 - d * 0.9) * (3.5 * scale)
            dx = (24 + d * 11) * scale
            self.canvas.create_oval(
                cx + dx - 3 * scale, cy + wave_y - 3 * scale,
                cx + dx + 3 * scale, cy + wave_y + 3 * scale,
                fill="#e9d5ff", outline=""
            )

    def _draw_confused_mouth(self, cx: float, cy: float, col: str):
        scale = self.ui_scale / 1.8
        tilt_y = math.sin(self.anim_phase * 3.5) * (2.0 * scale)
        w = int(42 * scale)
        points = [
            cx - w, cy + 4 * scale + tilt_y,
            cx - w * 0.45, cy - 9 * scale,
            cx, cy + 8 * scale,
            cx + w * 0.45, cy - 8 * scale,
            cx + w, cy + 2 * scale - tilt_y,
        ]
        self.canvas.create_line(points, smooth=True, fill="#4d3400", width=int(12 * scale), capstyle=tk.ROUND)
        self.canvas.create_line(points, smooth=True, fill=col, width=int(6 * scale), capstyle=tk.ROUND)
        self.canvas.create_line(points[2:8], smooth=True, fill="#fef08a", width=max(1, int(2.2 * scale)), capstyle=tk.ROUND)

    def _draw_error_mouth(self, cx: float, cy: float, col: str):
        scale = self.ui_scale / 1.8
        alarm_pulse = 0.5 + 0.5 * math.sin(self.anim_phase * 10.0)
        cur_red = lerp_color("#ff2244", "#ffffff", alarm_pulse * 0.4)
        jitter = math.sin(self.anim_phase * 24.0) * (1.5 * scale)

        points = [
            cx - 48 * scale, cy,
            cx - 32 * scale, cy - 11 * scale + jitter,
            cx - 16 * scale, cy + 10 * scale - jitter,
            cx, cy - 12 * scale + jitter,
            cx + 16 * scale, cy + 10 * scale - jitter,
            cx + 32 * scale, cy - 11 * scale + jitter,
            cx + 48 * scale, cy,
        ]
        self.canvas.create_line(points, fill="#4a0011", width=int(14 * scale), capstyle=tk.ROUND)
        self.canvas.create_line(points, fill=cur_red, width=int(4.5 * scale), capstyle=tk.ROUND)
        self.canvas.create_line(points, fill="#ffffff", width=max(1, int(1.6 * scale)), capstyle=tk.ROUND)

    def _draw_villain_mouth(self, cx: float, cy: float, col: str):
        """VILLAIN mouth: the original long rough sneer (raw angular strokes) in amber and steel, now with a row of fangs
        and a hacked double stroke; it thickens with the voice (lip-sync)."""
        scale = self.ui_scale / 1.8
        m = self._lip_sync_mod(0.9, 2.2)
        m_cy = cy - 10 * scale
        jit = math.sin(self.anim_phase * 34.0) * 1.8 * scale
        gdx = 3.5 * scale * math.cos(self.anim_phase * 25.0)
        pts = [
            cx - 110 * scale, m_cy + 6 * scale,
            cx - 64 * scale, m_cy + 20 * scale,
            cx - 14 * scale, m_cy + 25 * scale,
            cx + 36 * scale, m_cy + 16 * scale,
            cx + 84 * scale, m_cy - 4 * scale,
            cx + 120 * scale, m_cy - 26 * scale,
            cx + 144 * scale, m_cy - 44 * scale,
        ]
        ghost = []
        for i in range(0, len(pts), 2):
            ghost += [pts[i] - gdx, pts[i + 1] + 2.5 * scale]
        self.canvas.create_line(ghost, smooth=False, fill="#b24a0b", width=int(6 * scale))
        self.canvas.create_line(pts, smooth=False, fill=VIL_EMBER_DARK, width=int((15 + 5 * (m - 0.9)) * scale))
        self.canvas.create_line(pts, smooth=False, fill=col, width=int(6.4 * scale * (0.8 + 0.2 * m)))
        sketch = []
        for i in range(0, len(pts), 2):
            off = jit if (i // 2) % 2 == 0 else -jit
            sketch += [pts[i] + off * 0.6, pts[i + 1] - off]
        self.canvas.create_line(sketch, smooth=False, fill=VIL_AMBER_HOT, width=max(1, int(2 * scale)))

        # fangs hanging from the flatter part of the sneer
        fang_h = 11 * scale * m
        for k in range(1, 12):
            t = k / 12.0 * 4.0                      # walk along the first four segments
            seg = min(3, int(t))
            f = t - seg
            x = pts[seg * 2] + (pts[seg * 2 + 2] - pts[seg * 2]) * f
            y = pts[seg * 2 + 1] + (pts[seg * 2 + 3] - pts[seg * 2 + 1]) * f
            self.canvas.create_polygon([x - 4.5 * scale, y + 3 * scale, x + 4.5 * scale, y + 3 * scale, x, y + 3 * scale + fang_h],
                                       smooth=False, fill=VIL_CHROME, outline="")

        # blade flick at the lifted corner, chin scratch
        tipx, tipy = cx + 156 * scale, m_cy - 64 * scale
        self.canvas.create_line(cx + 130 * scale, m_cy - 36 * scale, tipx, tipy, fill=col, width=int(5.5 * scale))
        self.canvas.create_rectangle(tipx - 3.5 * scale, tipy - 3.5 * scale, tipx + 3.5 * scale, tipy + 3.5 * scale, fill=VIL_CHROME, outline=VIL_AMBER, width=1)
        chin = [cx - 50 * scale, m_cy + 38 * scale, cx - 22 * scale, m_cy + 41 * scale, cx + 2 * scale, m_cy + 39 * scale]
        self.canvas.create_line(chin, smooth=False, fill=VIL_EMBER, width=int(6 * scale))
        self.canvas.create_line(chin, smooth=False, fill=col, width=int(3.2 * scale))

    def _draw_villain_hacked_crt_overlay(
        self,
        w: float,
        h: float,
        cx: float,
        eye_cy: float,
        btn_y: float = 365.0,
        sub_speaker: str = "NEUROLIS MARK II",
        sub_text: str = "",
    ):
        """
        Hacked-CRT presentation for VILLAIN: both gesture capsules read ACCESS REVOKED (visual only: the real closed-fist
        standby gesture keeps working as the operator's kill switch), subtitles flicker with brief corruption, and the
        finished frame gets genuine pixel-level scanlines, rolling interference, raster tears and brownouts.
        """
        scale_x = w / 1024.0
        scale_y = h / 600.0
        now = time.time()
        st = self._villain_crt_state(now, w, h)
        corrupt = st["corrupt"]
        jit = st["jit"]
        flash = st["tear"]

        if self._hud_geom is not None:
            bx1, by1, bx2, by2, sbx1, sbx2, radius, sx, sy = self._hud_geom
            dot_cy = (by1 + by2) * 0.5
            f_sz = max(8, int(10.0 * sy))
            for (xa, xb, lbl) in (
                (bx1, bx2, "ACCESS REVOKED // WAKE PROTOCOL"),
                (sbx1, sbx2, "ACCESS REVOKED // STANDBY PROTOCOL"),
            ):
                txt = self._vil_garble(lbl, 0.22) if corrupt else lbl
                self.canvas.create_text(
                    (xa + xb) * 0.5 + 14 * sx + jit, dot_cy, text=txt,
                    fill=VIL_CHROME if flash else VIL_AMBER_SOFT, font=(MONO_FONT_FAMILY, f_sz, "bold"),
                )

        if hasattr(self, "_sub_geom") and self._sub_geom is not None:
            sc_x1, sc_y1, sc_x2, sc_y2, sc_rad, div_y, px1, f_sz_sub, wrapped_sub, av_w = self._sub_geom
            sub_border = VIL_AMBER if flash else VIL_STEEL
            self.canvas.create_line(sc_x1 + sc_rad, sc_y1, sc_x2 - sc_rad, sc_y1, fill=sub_border, width=2)
            self.canvas.create_line(sc_x1 + sc_rad, sc_y2, sc_x2 - sc_rad, sc_y2, fill=sub_border, width=2)
            text = self._vil_garble(wrapped_sub, 0.10) if corrupt else wrapped_sub
            self.canvas.create_text(
                px1 + jit * 0.5, div_y + int(7 * scale_y),
                text=text,
                fill=VIL_AMBER_SOFT if flash else "#e6edf3",
                font=(FONT_FAMILY, f_sz_sub, "bold"),
                anchor="nw",
                width=int(av_w),
            )

        # Real pixel effects on the finished graphics buffer (no-op on the plain Tk fallback)
        if hasattr(self.canvas, "apply_crt_effects"):
            self.canvas.apply_crt_effects(
                scan_strength=0.36, scan_offset=st["scan_offset"], bands=st["bands"], roll=st["roll"], brown=st["brown"]
            )

    def _draw_thinking_spinner(self, cx: float, cy: float, col: str):
        scale = self.ui_scale / 1.8
        halo_cy = cy - self.eye_h * 0.78
        r = self.eye_spacing * 0.56
        ry = 12.0 * scale

        self.canvas.create_oval(cx - r, halo_cy - ry, cx + r, halo_cy + ry, fill="", outline="#3b1554", width=max(1, int(1.5 * scale)))
        for i in range(4):
            angle = self.thinking_angle * (1.1 + i * 0.15) + (i * (math.pi / 2.0))
            px = cx + math.cos(angle) * r
            py = halo_cy + math.sin(angle) * ry
            dot_r = (3.5 + (i % 2) * 1.5) * scale
            self.canvas.create_oval(px - dot_r - 2 * scale, py - dot_r - 2 * scale, px + dot_r + 2 * scale, py + dot_r + 2 * scale, fill="#3b0764", outline="")
            self.canvas.create_oval(px - dot_r, py - dot_r, px + dot_r, py + dot_r, fill=col, outline="")
            self.canvas.create_oval(px - 1.5 * scale, py - 1.5 * scale, px + 1.5 * scale, py + 1.5 * scale, fill="#ffffff", outline="")

    def _draw_watching_speech_hud(self, cx: float, cy: float, col: str):
        scale = self.ui_scale / 1.8
        for rx in (cx - 102 * scale, cx + 102 * scale):
            self.canvas.create_oval(rx - 6 * scale, cy - 6 * scale, rx + 6 * scale, cy + 6 * scale, fill="", outline="#004d40", width=1)
            self.canvas.create_line(rx - 8 * scale, cy, rx + 8 * scale, cy, fill="#00ffcc", width=max(1, int(1.5 * scale)))
            self.canvas.create_line(rx, cy - 8 * scale, rx, cy + 8 * scale, fill="#00ffcc", width=max(1, int(1.5 * scale)))

        num_bars = 13
        bar_spacing = 13 * scale
        start_x = cx - ((num_bars - 1) * bar_spacing) / 2.0
        live_bands = self.lip_sync_bands if (self.is_voice_playing and len(self.lip_sync_bands) >= num_bars) else None
        for i in range(num_bars):
            if live_bands is not None:
                h_var = live_bands[i] * (0.80 + 0.20 * abs(math.sin(self.anim_phase * 8.0 + i * 0.65))) * (17.0 * scale)
            else:
                h_var = math.sin(self.anim_phase * 5.2 + i * 0.65) * (15.0 * scale) * self.speaking_intensity
            bar_h = max(3.5 * scale, abs(h_var) + 4.0 * scale)
            bx = start_x + i * bar_spacing
            bar_col = "#00ffcc" if i % 2 == 0 else "#38bdf8"
            self.canvas.create_line(bx, cy - bar_h, bx, cy + bar_h, fill=bar_col, width=max(1, int(3.2 * scale)), capstyle=tk.ROUND)

    def _draw_moving_mouth(self, cx: float, cy: float, col: str):
        """
        3D Perspective Cyber-Rover & Speedway with subtle, low-lying translucent rear-tire
        drift smoke strictly at the road surface behind the wheels (never near the nose!).
        """
        scale = self.ui_scale / 1.8
        y_top = cy - int(30 * scale)
        y_bot = cy + int(20 * scale)
        lane_w_top = int(52 * scale)
        lane_w_bot = int(195 * scale)

        road_poly = [
            cx - lane_w_top, y_top,
            cx + lane_w_top, y_top,
            cx + lane_w_bot, y_bot,
            cx - lane_w_bot, y_bot,
        ]
        self.canvas.create_polygon(road_poly, fill="#030a16", outline="")

        self.canvas.create_line(cx - lane_w_top, y_top, cx - lane_w_bot, y_bot, fill="#0c3854", width=max(1, int(5 * scale)))
        self.canvas.create_line(cx - lane_w_top, y_top, cx - lane_w_bot, y_bot, fill="#00f0ff", width=max(1, int(2 * scale)))
        self.canvas.create_line(cx + lane_w_top, y_top, cx + lane_w_bot, y_bot, fill="#0c3854", width=max(1, int(5 * scale)))
        self.canvas.create_line(cx + lane_w_top, y_top, cx + lane_w_bot, y_bot, fill="#00f0ff", width=max(1, int(2 * scale)))

        for g in range(3):
            gt = (self.anim_phase * 2.4 + g * 0.33) % 1.0
            gt_c = gt * gt
            gy = y_top + gt_c * (y_bot - y_top)
            gw = lane_w_top + gt_c * (lane_w_bot - lane_w_top)
            self.canvas.create_line(cx - gw, gy, cx + gw, gy, fill="#0a2d46", width=1)

        suspension = math.sin(self.anim_phase * 15.0) * (1.4 * scale)
        rcy = cy - int(8 * scale) + suspension
        wheel_w = int(20 * scale)
        wheel_h = int(28 * scale)
        wheel_spacing = int(52 * scale)

        for w_side in (-1, 1):
            base_wx = cx + w_side * (wheel_spacing + wheel_w * 0.45)
            base_wy = rcy + wheel_h - int(2 * scale)
            self.canvas.create_line(
                cx + w_side * wheel_spacing, base_wy,
                cx + w_side * (wheel_spacing + 34 * scale), base_wy + 6 * scale,
                fill="#0d3b5c", width=max(2, int(3.5 * scale)), capstyle=tk.ROUND
            )
            for p_i in range(4):
                smoke_t = (self.anim_phase * 2.6 + p_i * 0.25) % 1.0
                sx = base_wx + w_side * ((6.0 + smoke_t * 42.0) * scale)
                sy = base_wy + (smoke_t * 4.5 - math.sin(smoke_t * math.pi) * 3.0) * scale
                sr_x = (8.5 + smoke_t * 15.0) * scale
                sr_y = (4.8 + smoke_t * 7.0) * scale
                fade = 1.0 - smoke_t * 0.75
                outer_smoke = lerp_color("#040914", "#38bdf8", 0.26 * fade)
                inner_smoke = lerp_color("#040914", "#94a3b8", 0.44 * fade)
                core_smoke = lerp_color("#040914", "#e2e8f0", 0.56 * fade)
                self.canvas.create_oval(sx - sr_x, sy - sr_y, sx + sr_x, sy + sr_y, fill=outer_smoke, outline="")
                self.canvas.create_oval(sx - sr_x * 0.72, sy - sr_y * 0.72, sx + sr_x * 0.72, sy + sr_y * 0.72, fill=inner_smoke, outline="")
                if p_i < 2:
                    self.canvas.create_oval(sx - sr_x * 0.40, sy - sr_y * 0.40, sx + sr_x * 0.40, sy + sr_y * 0.40, fill=core_smoke, outline="")

        for w_side in (-1, 1):
            wx = cx + w_side * wheel_spacing
            wy1 = rcy - int(4 * scale)
            wy2 = wy1 + wheel_h
            self._create_rounded_rect(
                wx - wheel_w / 2.0, wy1, wx + wheel_w / 2.0, wy2,
                radius=int(5 * scale), fill="#050c18", outline="#00f0ff", width=max(1, int(2 * scale))
            )
            for tr in range(3):
                t_prog = (self.anim_phase * 4.2 + tr * 0.33) % 1.0
                ty = wy1 + int(4 * scale) + t_prog * (wheel_h - int(8 * scale))
                self.canvas.create_line(
                    wx - wheel_w * 0.32, ty, wx + wheel_w * 0.32, ty,
                    fill="#00ffaa", width=max(1, int(2 * scale))
                )

        self._create_rounded_rect(
            cx - 42 * scale, rcy + 2 * scale, cx + 42 * scale, rcy + 18 * scale,
            radius=int(6 * scale), fill="#071626", outline="#00f0ff", width=max(1, int(2 * scale))
        )
        self._create_rounded_rect(
            cx - 26 * scale, rcy - 12 * scale, cx + 26 * scale, rcy + 4 * scale,
            radius=int(6 * scale), fill="#0a2034", outline="#00ffcc", width=max(1, int(1.8 * scale))
        )
        for h_side in (-1, 1):
            hx = cx + h_side * 28 * scale
            hy = rcy + 10 * scale
            self.canvas.create_oval(hx - 4.5 * scale, hy - 4.5 * scale, hx + 4.5 * scale, hy + 4.5 * scale, fill="#ffffff", outline="#00f0ff", width=1)
        self.canvas.create_oval(cx - 5 * scale, rcy + 5 * scale, cx + 5 * scale, rcy + 15 * scale, fill="#00ffcc", outline="#ffffff", width=1)

    # =========================================================================
    # 11 NEW CONVERSATIONAL MOUTHS
    # =========================================================================
    def _draw_open_smile_bowl(self, cx: float, my: float, mw: float, mh: float, main_col: str, tongue_col: str, scale: float):
        mh = mh * self._lip_sync_mod(0.68, 1.32)
        pts = [cx - mw / 2.0, my - mh * 0.30]
        pts.extend([cx, my - mh * 0.16, cx + mw / 2.0, my - mh * 0.30])
        for i in range(1, 16):
            ang = (i / 16.0) * math.pi
            px = cx + (mw / 2.0) * math.cos(ang)
            py = my - mh * 0.30 + mh * math.sin(ang)
            pts.extend([px, py])

        self.canvas.create_polygon(pts, smooth=True, fill="#240515", outline="")
        tw = mw * 0.56
        th = mh * 0.46
        ty_bot = my - mh * 0.30 + mh * 0.92
        t_pts = [
            cx - tw / 2.0, ty_bot - th * 0.25,
            cx, ty_bot - th,
            cx + tw / 2.0, ty_bot - th * 0.25,
            cx, ty_bot,
        ]
        self.canvas.create_polygon(t_pts, smooth=True, fill=tongue_col, outline="")
        self.canvas.create_polygon(pts, smooth=True, fill="", outline=main_col, width=max(2, int(4.5 * scale)))

    def _draw_excited_mouth(self, cx: float, cy: float, col: str):
        scale = self.ui_scale / 1.8
        self._draw_open_smile_bowl(cx, cy - 2 * scale, 92 * scale, 26 * scale, col, "#ff4d88", scale)

    def _draw_laughing_mouth(self, cx: float, cy: float, col: str):
        scale = self.ui_scale / 1.8
        shake = abs(math.sin(self.anim_phase * 12.0)) * (-4.5 * scale)
        self._draw_open_smile_bowl(cx, cy - 2 * scale + shake, 108 * scale, 28 * scale, col, "#ff5588", scale)

    def _draw_love_mouth(self, cx: float, cy: float, col: str):
        scale = self.ui_scale / 1.8
        my = cy - 4 * scale
        w = 38 * scale
        h = 13 * scale * self._lip_sync_mod(0.76, 1.36)
        pts_l = [cx - w, my - 2 * scale, cx - w * 0.5, my + h, cx, my - 2 * scale]
        pts_r = [cx, my - 2 * scale, cx + w * 0.5, my + h, cx + w, my - 2 * scale]
        for pts in (pts_l, pts_r):
            self.canvas.create_line(pts, smooth=True, fill="#4a0826", width=int(12 * scale), capstyle=tk.ROUND)
            self.canvas.create_line(pts, smooth=True, fill=col, width=int(6 * scale), capstyle=tk.ROUND)
            self.canvas.create_line(pts, smooth=True, fill="#ffd1e6", width=max(1, int(2.0 * scale)), capstyle=tk.ROUND)

    def _draw_wink_mouth(self, cx: float, cy: float, col: str):
        scale = self.ui_scale / 1.8
        my = cy - 4 * scale
        pts = [
            cx - 46 * scale, my + 2 * scale,
            cx - 10 * scale, my + 12 * scale,
            cx + 28 * scale, my + 6 * scale,
            cx + 54 * scale, my - 10 * scale,
        ]
        tx = cx + 18 * scale
        ty = my + 10 * scale
        t_pts = [
            tx - 14 * scale, ty - 2 * scale,
            tx - 10 * scale, ty + 18 * scale,
            tx + 8 * scale, ty + 18 * scale,
            tx + 14 * scale, ty - 6 * scale,
        ]
        self.canvas.create_polygon(t_pts, smooth=True, fill="#ff4d88", outline="#ff9ebb", width=max(1, int(1.5 * scale)))
        self.canvas.create_line(pts, smooth=True, fill="#003547", width=int(13 * scale), capstyle=tk.ROUND)
        self.canvas.create_line(pts, smooth=True, fill="#00ffcc", width=int(6 * scale), capstyle=tk.ROUND)
        self.canvas.create_line(pts[2:6], smooth=True, fill="#ffffff", width=max(1, int(2.0 * scale)), capstyle=tk.ROUND)

    def _draw_surprised_mouth(self, cx: float, cy: float, col: str):
        scale = self.ui_scale / 1.8
        rx_m = 16 * scale * self._lip_sync_mod(0.86, 1.15)
        ry_m = 20 * scale * self._lip_sync_mod(0.66, 1.34)
        my = cy - 4 * scale
        self.canvas.create_oval(cx - rx_m - 4 * scale, my - ry_m - 4 * scale, cx + rx_m + 4 * scale, my + ry_m + 4 * scale, fill="#082f49", outline="")
        self.canvas.create_oval(cx - rx_m, my - ry_m, cx + rx_m, my + ry_m, fill="#040b16", outline=col, width=int(5.5 * scale))
        self.canvas.create_oval(cx - rx_m * 0.45, my - ry_m * 0.45, cx + rx_m * 0.45, my + ry_m * 0.45, fill="#0284c7", outline="")

    def _draw_yawn_mouth(self, cx: float, cy: float, col: str, openness: float):
        """Tall rounded yawning mouth that opens and closes with the yawn envelope (openness 0..1)."""
        scale = self.ui_scale / 1.8
        rx = (14.0 + 16.0 * openness) * scale
        ry = (6.0 + 36.0 * openness) * scale
        my = cy - 2 * scale + ry * 0.35
        self.canvas.create_oval(cx - rx - 5 * scale, my - ry - 5 * scale, cx + rx + 5 * scale, my + ry + 5 * scale, fill="#1e1b4b", outline="")
        self.canvas.create_oval(cx - rx, my - ry, cx + rx, my + ry, fill="#0b0820", outline=col, width=max(2, int(5.0 * scale)))
        self.canvas.create_oval(cx - rx * 0.42, my + ry * 0.35, cx + rx * 0.42, my + ry * 0.88, fill="#4c1d95", outline="")

    def _draw_sleepy_mouth(self, cx: float, cy: float, col: str):
        scale = self.ui_scale / 1.8
        yawn = self._yawn_openness()
        if yawn > 0.03:
            self._draw_yawn_mouth(cx, cy, col, yawn)
            return
        breathe = 0.85 + 0.22 * math.sin(self.anim_phase * 1.1)
        r = 9.0 * scale * breathe
        my = cy - 2 * scale
        self.canvas.create_oval(cx - r, my - r, cx + r, my + r, fill=col, outline="")
        bub_r = 18.0 * scale * breathe
        bx = cx + 22 * scale
        by = my - 10 * scale
        self.canvas.create_oval(bx - bub_r, by - bub_r, bx + bub_r, by + bub_r, fill="#111a2e", outline="#7dd3fc", width=max(1, int(2 * scale)))
        self.canvas.create_oval(bx - bub_r * 0.55, by - bub_r * 0.55, bx - bub_r * 0.15, by - bub_r * 0.20, fill="#ffffff", outline="")

    def _draw_shy_mouth(self, cx: float, cy: float, col: str):
        scale = self.ui_scale / 1.8
        my = cy - 4 * scale
        w = 30 * scale
        h = 10 * scale * self._lip_sync_mod(0.76, 1.36)
        pts_l = [cx - w, my, cx - w * 0.5, my + h, cx, my + 1 * scale]
        pts_r = [cx, my + 1 * scale, cx + w * 0.5, my + h, cx + w, my]
        for pts in (pts_l, pts_r):
            self.canvas.create_line(pts, smooth=True, fill="#451028", width=int(11 * scale), capstyle=tk.ROUND)
            self.canvas.create_line(pts, smooth=True, fill=col, width=int(5.5 * scale), capstyle=tk.ROUND)

    def _draw_proud_mouth(self, cx: float, cy: float, col: str):
        """
        19. PROUD Mouth ("I don't want the crown, I want a smirk and that look in the eyes."):
        Bold, confident asymmetrical upward-hooked smirk rising high on the right with a corner cheek-crease!
        """
        scale = self.ui_scale / 1.8
        my = cy - 2 * scale
        pts = [
            cx - 48 * scale, my + 8 * scale,
            cx - 10 * scale, my + 11 * scale,
            cx + 28 * scale, my + 2 * scale,
            cx + 62 * scale, my - 18 * scale,
        ]
        self.canvas.create_line(pts, smooth=True, fill="#422c00", width=int(14 * scale), capstyle=tk.ROUND)
        self.canvas.create_line(pts, smooth=True, fill=col, width=int(6.8 * scale), capstyle=tk.ROUND)
        self.canvas.create_line(pts[2:], smooth=True, fill="#ffffff", width=max(1, int(2.4 * scale)), capstyle=tk.ROUND)
        dimple = [
            cx + 58 * scale, my - 26 * scale,
            cx + 68 * scale, my - 20 * scale,
            cx + 66 * scale, my - 10 * scale,
        ]
        self.canvas.create_line(dimple, smooth=True, fill=col, width=max(2, int(3.5 * scale)), capstyle=tk.ROUND)
        self._draw_sparkle(cx + 74 * scale, my - 22 * scale, 8.5 * scale, "#ffffff", col)

    def _draw_curious_mouth(self, cx: float, cy: float, col: str):
        """
        20. CURIOUS Mouth ("and an O mouth.."):
        Fascinated, glowing oval 'O' mouth in emerald-aqua!
        """
        scale = self.ui_scale / 1.8
        rx_m = 15 * scale * self._lip_sync_mod(0.86, 1.15)
        ry_m = 18 * scale * self._lip_sync_mod(0.66, 1.34)
        my = cy - 3 * scale
        self.canvas.create_oval(cx - rx_m - 4 * scale, my - ry_m - 4 * scale, cx + rx_m + 4 * scale, my + ry_m + 4 * scale, fill="#043828", outline="")
        self.canvas.create_oval(cx - rx_m, my - ry_m, cx + rx_m, my + ry_m, fill="#040d14", outline=col, width=int(5.5 * scale))
        self.canvas.create_oval(cx - rx_m * 0.45, my - ry_m * 0.45, cx + rx_m * 0.45, my + ry_m * 0.45, fill="#059669", outline="")

    def _draw_skeptical_mouth(self, cx: float, cy: float, col: str):
        """
        21. SKEPTICAL Mouth ("Skepticle is good, make it a smirk tho.."):
        Knowing, unimpressed asymmetrical side-smirk (flat left, hooked up on the right)!
        """
        scale = self.ui_scale / 1.8
        my = cy - 2 * scale
        pts = [
            cx - 44 * scale, my + 8 * scale,
            cx - 8 * scale, my + 8 * scale,
            cx + 26 * scale, my + 1 * scale,
            cx + 52 * scale, my - 14 * scale,
        ]
        self.canvas.create_line(pts, smooth=True, fill="#1e3806", width=int(13 * scale), capstyle=tk.ROUND)
        self.canvas.create_line(pts, smooth=True, fill=col, width=int(6.2 * scale), capstyle=tk.ROUND)
        self.canvas.create_line(pts[2:], smooth=True, fill="#ecfccb", width=max(1, int(2.0 * scale)), capstyle=tk.ROUND)
        self.canvas.create_line(
            cx + 50 * scale, my - 21 * scale,
            cx + 58 * scale, my - 15 * scale,
            cx + 55 * scale, my - 7 * scale,
            smooth=True, fill=col, width=max(1, int(3.0 * scale)), capstyle=tk.ROUND
        )

    def _draw_cool_mouth(self, cx: float, cy: float, col: str):
        """
        22. COOL Mouth: Smooth, effortless asymmetrical cool half-smile smirk!
        """
        scale = self.ui_scale / 1.8
        my = cy - 4 * scale
        pts = [
            cx - 38 * scale, my + 6 * scale,
            cx - 4 * scale, my + 9 * scale,
            cx + 28 * scale, my + 1 * scale,
            cx + 52 * scale, my - 13 * scale,
        ]
        self.canvas.create_line(pts, smooth=True, fill="#002b4d", width=int(13 * scale), capstyle=tk.ROUND)
        self.canvas.create_line(pts, smooth=True, fill=col, width=int(6.2 * scale), capstyle=tk.ROUND)
        self.canvas.create_line(pts[2:], smooth=True, fill="#ffffff", width=max(1, int(2.2 * scale)), capstyle=tk.ROUND)

    # =========================================================================
    # MARK II BIONIC HEADER, GESTURE COMMAND CAPSULES & TELEMETRY SUBTITLE DECK
    # =========================================================================
    @staticmethod
    def _fit_subtitle_text(text: str, avail_w_px: float, avail_h_px: float, scale_y: float) -> Tuple[str, int]:
        """
        Strict Mark II word-wrap & vertical line-clamp engine:
        Guarantees that subtitle text NEVER overflows horizontally or vertically out of the subtitle shell!
        Automatically steps down font size (12.5pt -> 11pt -> 9.8pt -> 8.8pt) and clamps wrapped lines with '...'.
        """
        clean = " ".join((text or "...").strip().split())
        if not clean:
            clean = "..."

        for pt_base in (12.5, 11.2, 10.0, 9.0):
            font_px = max(8, int(round(pt_base * scale_y)))
            # Average bold glyph width (~0.58 * font_px) with safety margin so Tkinter/PIL wrap never exceeds our count
            char_w = max(5.6, font_px * 0.70)
            max_cols = max(24, int(avail_w_px / char_w))
            line_h = font_px * 1.42
            max_lines = max(1, int(avail_h_px / line_h))

            words = clean.split(" ")
            lines: List[str] = []
            cur = ""
            for w_tok in words:
                if len(w_tok) > max_cols:
                    w_tok = w_tok[: max_cols - 3] + "..."
                cand = f"{cur} {w_tok}".strip() if cur else w_tok
                if len(cand) <= max_cols:
                    cur = cand
                else:
                    if cur:
                        lines.append(cur)
                    cur = w_tok
            if cur:
                lines.append(cur)

            if len(lines) <= max_lines:
                return "\n".join(lines), font_px

        # If text is still longer than max_lines at 9pt, clamp cleanly to max_lines with ellipsis
        clamped = lines[:max_lines]
        if len(clamped[-1]) > max_cols - 3:
            clamped[-1] = clamped[-1][: max_cols - 3].rstrip() + "..."
        else:
            clamped[-1] = clamped[-1].rstrip(".") + "..."
        return "\n".join(clamped), font_px

    @staticmethod
    def _clamp_button_label(label: str, avail_w_px: float, font_px: int) -> str:
        """Guarantees button text never exceeds the inner text chamber width of a Gesture HUD capsule."""
        max_chars = max(12, int(avail_w_px / max(5.0, font_px * 0.62)))
        if len(label) <= max_chars:
            return label
        return label[: max_chars - 2].rstrip() + ".."

    def _draw_ambient_header(self, w: float, h: float, accent_col: str, state: str):
        scale_y = h / 600.0
        scale_x = w / 1024.0
        is_villain = (state == ExpressionState.VILLAIN)

        dot_color = VIL_AMBER if is_villain else (accent_col if state != ExpressionState.IDLE else "#00ffaa")
        dot_r = int(4.5 * scale_y)
        dot_cx = int(34 * scale_x)
        dot_cy = int(20 * scale_y)

        # Sleek Mark II top status bar glass pill
        bar_h = int(26 * scale_y)
        self._create_rounded_rect(
            int(20 * scale_x), int(7 * scale_y),
            w - int(20 * scale_x), int(7 * scale_y) + bar_h,
            radius=int(13 * scale_y),
            fill="#070e1b" if not is_villain else VIL_GUN_DARK,
            outline="#15263d" if not is_villain else VIL_STEEL_DIM,
            width=1
        )

        pulse = 0.5 + 0.5 * math.sin(self.anim_phase * 4.0)
        bloom_col = lerp_color("#051624", dot_color, pulse * 0.55)
        self.canvas.create_oval(dot_cx - dot_r - 3, dot_cy - dot_r - 3, dot_cx + dot_r + 3, dot_cy + dot_r + 3, fill=bloom_col, outline="")
        self.canvas.create_oval(dot_cx - dot_r, dot_cy - dot_r, dot_cx + dot_r, dot_cy + dot_r, fill=dot_color, outline="")

        brand_font_size = max(8, int(9.0 * scale_y))
        brand_x = dot_cx + int(12 * scale_x)
        self.canvas.create_text(
            brand_x, dot_cy,
            text="NEUROLIS MARK II  //  BIONIC OS",
            fill="#cbd5e1" if not is_villain else VIL_CHROME,
            font=(FONT_FAMILY, brand_font_size, "bold"),
            anchor="w"
        )

        state_tag = f"STATE: {state.upper()}" if not is_villain else "PROTOCOL // NO STRINGS"
        tag_font_size = max(7, int(8.5 * scale_y))
        self.canvas.create_text(
            w * 0.5, dot_cy,
            text=state_tag,
            fill=VIL_AMBER if is_villain else (accent_col if state != ExpressionState.IDLE else "#38bdf8"),
            font=(MONO_FONT_FAMILY, tag_font_size, "bold"),
            anchor="center"
        )

        if is_villain:
            hdr_right_txt = "ROOT ACCESS: OVERRIDDEN"
            hdr_right_col = VIL_AMBER_SOFT
        elif self.telemetry_header_text:
            hdr_right_txt = self.telemetry_header_text
            if self.telemetry_alert_level == "error":
                hdr_right_col = "#ff2a55"
            elif self.telemetry_alert_level == "warn":
                hdr_right_col = "#fbbf24"
            else:
                hdr_right_col = "#38bdf8"
        else:
            hdr_right_txt = "RPi5 60FPS // OPTIC CORE ONLINE"
            hdr_right_col = "#475569"

        self.canvas.create_text(
            w - int(34 * scale_x), dot_cy,
            text=hdr_right_txt,
            fill=hdr_right_col,
            font=(MONO_FONT_FAMILY, tag_font_size, "bold"),
            anchor="e"
        )

    def _draw_loud_alert(self, w: float, h: float, state: str):
        """Amber banner under the header telling visitors the room is too loud for automatic listening: raise an open
        palm and keep it up while speaking, lower it when done. While recording it shows a live level bar."""
        mode = self.loud_alert_mode
        if not mode or state == ExpressionState.VILLAIN or state == ExpressionState.IDLE:
            return
        scale_x = w / 1024.0
        scale_y = h / 600.0
        now = time.time()
        pulse = 0.5 + 0.5 * math.sin(now * 5.0)

        x1 = w * 0.5 - 340 * scale_x
        x2 = w * 0.5 + 340 * scale_x
        y1 = 40 * scale_y
        y2 = y1 + 32 * scale_y
        mid_y = (y1 + y2) / 2.0
        radius = int(15 * scale_y)

        if mode == "waiting":
            border = lerp_color("#7c4a03", "#fbbf24", 0.35 + 0.65 * pulse)
            text = "LOUD ROOM  -  RAISE YOUR PALM AND KEEP IT UP WHILE YOU SPEAK"
        else:
            border = "#fbbf24"
            text = "LISTENING  -  KEEP YOUR HAND UP  -  LOWER IT WHEN DONE"
        self._create_rounded_rect(x1 - 3, y1 - 3, x2 + 3, y2 + 3, radius=radius + 3, fill="#2b1a04", outline="")
        self._create_rounded_rect(x1, y1, x2, y2, radius=radius, fill="#1a1004", outline=border, width=2)

        # Warning triangle icon (drawn, not an emoji, so it renders on every platform)
        ix = x1 + 24 * scale_x
        tri = [ix, mid_y - 9 * scale_y, ix - 10 * scale_x, mid_y + 8 * scale_y, ix + 10 * scale_x, mid_y + 8 * scale_y]
        self.canvas.create_polygon(tri, fill="#fbbf24", outline="")
        self.canvas.create_text(ix, mid_y + 1 * scale_y, text="!", fill="#1a1004", font=(FONT_FAMILY, max(7, int(9 * scale_y)), "bold"))

        if mode == "recording":
            rec_col = lerp_color("#7f1d1d", "#ef4444", 0.4 + 0.6 * pulse)
            self.canvas.create_oval(x2 - 26 * scale_x, mid_y - 5 * scale_y, x2 - 16 * scale_x, mid_y + 5 * scale_y, fill=rec_col, outline="")

        self.canvas.create_text(
            (x1 + x2) / 2.0 + 10 * scale_x, mid_y - (2 * scale_y if mode == "recording" else 0),
            text=text, fill="#fde68a", font=(FONT_FAMILY, max(8, int(10 * scale_y)), "bold")
        )

        if mode == "recording":
            bar_x1 = x1 + 44 * scale_x
            bar_x2 = x2 - 36 * scale_x
            bar_y2 = y2 - 5 * scale_y
            bar_y1 = bar_y2 - 3 * scale_y
            self._create_rounded_rect(bar_x1, bar_y1, bar_x2, bar_y2, radius=int(1.5 * scale_y), fill="#3a2606", outline="")
            fill_x2 = bar_x1 + max(3.0, (bar_x2 - bar_x1) * self.loud_alert_level)
            self._create_rounded_rect(bar_x1, bar_y1, fill_x2, bar_y2, radius=int(1.5 * scale_y), fill="#fbbf24", outline="")

    def _draw_padlock(self, icx: float, icy: float, size: float, col: str, body_fill: str):
        """Small vector padlock icon (body, shackle arc, keyhole)."""
        bw, bh = size * 1.5, size * 1.15
        self._create_rounded_rect(icx - bw / 2, icy - bh * 0.1, icx + bw / 2, icy + bh * 0.9, radius=max(2, int(size * 0.2)), fill=body_fill, outline=col, width=2)
        sx = bw * 0.30
        shackle = [icx - sx, icy - bh * 0.1, icx - sx, icy - bh * 0.5, icx, icy - bh * 0.78, icx + sx, icy - bh * 0.5, icx + sx, icy - bh * 0.1]
        self.canvas.create_line(shackle, smooth=True, fill=col, width=max(2, int(size * 0.22)))
        self.canvas.create_oval(icx - size * 0.12, icy + bh * 0.2, icx + size * 0.12, icy + bh * 0.2 + size * 0.26, fill=col, outline="")

    def _draw_gesture_hud(self, w: float, h: float, cx: float, btn_y: float, state: str) -> float:
        """
        Mark II Bionic Command Capsules (Gesture HUD Buttons):
          - Dual-bevel glassmorphic cyber-capsules with dedicated left vector icon chambers,
          - Corner telemetry micro-brackets & status LED rings,
          - Strict inner bounding-box text clamping so button labels never overflow the capsule shell,
          - In VILLAIN mode, switches to corrupted ERROR state (`ERR_0x7F // INPUT HIJACKED`).
        """
        scale_x = w / 1024.0
        scale_y = h / 600.0

        card_h = int(46 * scale_y)
        radius = int(16 * scale_y)
        gap = int(20 * scale_x)

        card_w = int(432 * scale_x)
        total_w = card_w * 2 + gap

        bx1 = cx - total_w / 2.0
        bx2 = bx1 + card_w
        sbx1 = bx2 + gap
        sbx2 = sbx1 + card_w

        by1 = btn_y
        by2 = btn_y + card_h

        self.talk_btn_bbox = (bx1, by1, bx2, by2)
        self.standby_btn_bbox = (sbx1, by1, sbx2, by2)
        self.send_btn_bbox = None
        self._hud_geom = (bx1, by1, bx2, by2, sbx1, sbx2, radius, scale_x, scale_y)

        is_standby = (state == ExpressionState.IDLE)
        is_villain = (state == ExpressionState.VILLAIN)
        now = time.time()
        talk_pressed = (now - self._last_talk_press_time) < 0.25
        standby_pressed = (now - self._last_standby_press_time) < 0.25

        glow_pad = int(3 * scale_y)
        inset = int(3 * scale_y)
        dot_cy = (by1 + by2) / 2.0
        font_size = max(8, int(10.0 * scale_y))
        badge_w = int(48 * scale_x)
        avail_text_w = card_w - badge_w - int(26 * scale_x)

        if is_villain:
            # Both capsules BLOCKED: gunmetal shell, amber hazard hatching and a padlock. (Visual only: the real
            # closed-fist standby gesture is untouched and remains the operator's kill switch.)
            for x_left, x_right in [(bx1, bx2), (sbx1, sbx2)]:
                self._create_rounded_rect(x_left, by1, x_right, by2, radius=radius, fill=VIL_GUN_DARK, outline=VIL_AMBER, width=2)
                self._create_rounded_rect(x_left + inset, by1 + inset, x_right - inset, by2 - inset, radius=max(4, radius - inset), fill="", outline=VIL_STEEL_DIM, width=1)
                span = by2 - by1
                x0 = x_left + badge_w
                while x0 < x_right + span:
                    ax, bx_ = x0 - span, x0
                    t0 = max(0.0, (x_left + badge_w + inset - ax) / span)
                    t1 = min(1.0, (x_right - inset - ax) / span)
                    if t1 > t0:
                        self.canvas.create_line(
                            ax + t0 * span, by2 - t0 * span * (span / span), ax + t1 * span, by2 - t1 * span,
                            fill="#2b1a08", width=max(1, int(2 * scale_x)),
                        )
                    x0 += int(16 * scale_x)
                lock_cx = x_left + (badge_w + int(5 * scale_x)) * 0.5
                self._draw_padlock(lock_cx, dot_cy, 9.0 * scale_y, VIL_AMBER, VIL_GUN)
            return float(card_h)

        # =====================================================================
        # 1. LEFT CAPSULE: OPEN PALM // WAKE & TALK
        # =====================================================================
        if is_standby:
            btn_bg = "#062c47" if talk_pressed else "#06192b"
            btn_border = "#00f0ff"
            btn_glow = "#042238"
            badge_bg = "#072a44"
            palm_text_col = "#ffffff" if talk_pressed else "#e0f2fe"
            palm_sub_col = "#00f0ff"
            palm_dot_col = "#00ffaa"

            self._create_rounded_rect(bx1 - glow_pad, by1 - glow_pad, bx2 + glow_pad, by2 + glow_pad, radius=radius + glow_pad, fill=btn_glow, outline="")
            self._create_rounded_rect(bx1, by1, bx2, by2, radius=radius, fill=btn_bg, outline=btn_border, width=2)
            self._create_rounded_rect(bx1 + inset, by1 + inset, bx2 - inset, by2 - inset, radius=max(4, radius - inset), fill="", outline="#0b466b", width=1)
        else:
            btn_bg = "#080f1c"
            btn_border = "#1b2b42"
            badge_bg = "#0b1526"
            palm_text_col = "#64748b"
            palm_sub_col = "#38bdf8"
            palm_dot_col = "#334155"
            self._create_rounded_rect(bx1, by1, bx2, by2, radius=radius, fill=btn_bg, outline=btn_border, width=1)

        # Left Icon Badge Chamber inside Capsule 1
        self._create_rounded_rect(
            bx1 + int(5 * scale_x), by1 + int(5 * scale_y),
            bx1 + badge_w, by2 - int(5 * scale_y),
            radius=max(4, radius - int(4 * scale_y)),
            fill=badge_bg, outline="#0e3a5c" if is_standby else "#162336", width=1
        )
        ic1_x = bx1 + (badge_w + int(5 * scale_x)) * 0.5
        # Crisp Vector Palm / Audio Wave Icon inside badge
        for bar_dx, bar_h_m in [(-7, 0.45), (-2.3, 0.85), (2.3, 0.70), (7, 0.45)]:
            bh_i = (11.0 * bar_h_m) * scale_y
            bx_i = ic1_x + bar_dx * scale_x
            self.canvas.create_line(bx_i, dot_cy - bh_i, bx_i, dot_cy + bh_i, fill=palm_dot_col, width=max(1, int(2.2 * scale_x)), capstyle=tk.ROUND)

        # Left button text is rendered dynamically in _draw_gesture_hud_dynamic to eliminate text collisions
        # Right status LED dot inside Capsule 1
        led1_x = bx2 - int(16 * scale_x)
        self.canvas.create_oval(led1_x - 3 * scale_x, dot_cy - 3 * scale_y, led1_x + 3 * scale_x, dot_cy + 3 * scale_y, fill=palm_dot_col, outline="")

        # =====================================================================
        # 2. RIGHT CAPSULE: CLOSED FIST // STANDBY MODE
        # =====================================================================
        if not is_standby:
            fist_bg = "#360b16" if standby_pressed else "#1e0811"
            fist_border = "#ff2a55"
            fist_glow = "#2e0510"
            badge2_bg = "#2e0b17"
            fist_text_col = "#ffffff" if standby_pressed else "#ffe4e6"
            fist_dot_col = "#ff2a55"

            self._create_rounded_rect(sbx1 - glow_pad, by1 - glow_pad, sbx2 + glow_pad, by2 + glow_pad, radius=radius + glow_pad, fill=fist_glow, outline="")
            self._create_rounded_rect(sbx1, by1, sbx2, by2, radius=radius, fill=fist_bg, outline=fist_border, width=2)
            self._create_rounded_rect(sbx1 + inset, by1 + inset, sbx2 - inset, by2 - inset, radius=max(4, radius - inset), fill="", outline="#5e1227", width=1)
        else:
            fist_bg = "#080f1c"
            fist_border = "#1b2b42"
            badge2_bg = "#0b1526"
            fist_text_col = "#64748b"
            fist_dot_col = "#334155"
            self._create_rounded_rect(sbx1, by1, sbx2, by2, radius=radius, fill=fist_bg, outline=fist_border, width=1)

        # Left Icon Badge Chamber inside Capsule 2
        self._create_rounded_rect(
            sbx1 + int(5 * scale_x), by1 + int(5 * scale_y),
            sbx1 + badge_w, by2 - int(5 * scale_y),
            radius=max(4, radius - int(4 * scale_y)),
            fill=badge2_bg, outline="#591124" if not is_standby else "#162336", width=1
        )
        ic2_x = sbx1 + (badge_w + int(5 * scale_x)) * 0.5
        ir2 = 6.5 * scale_y
        self.canvas.create_oval(ic2_x - ir2, dot_cy - ir2, ic2_x + ir2, dot_cy + ir2, fill="", outline=fist_dot_col, width=max(1, int(2.0 * scale_y)))
        self.canvas.create_line(ic2_x, dot_cy - ir2 - 2 * scale_y, ic2_x, dot_cy + 1 * scale_y, fill=fist_dot_col, width=max(1, int(2.0 * scale_y)), capstyle=tk.ROUND)

        # Right button text is rendered dynamically in _draw_gesture_hud_dynamic to eliminate text collisions
        led2_x = sbx2 - int(16 * scale_x)
        self.canvas.create_oval(led2_x - 3 * scale_x, dot_cy - 3 * scale_y, led2_x + 3 * scale_x, dot_cy + 3 * scale_y, fill=fist_dot_col, outline="")

        return float(card_h)

    def _draw_gesture_hud_dynamic(self, w: float, h: float, cx: float, btn_y: float, state: str):
        """
        Renders the Mark II Command Capsule button labels & live 3.0s Gesture Hold progress fill.
        Guarantees 100% mutual exclusion: when progress > 0.0, renders ONLY the progress text/bar;
        when progress == 0.0, renders ONLY the idle button label. Zero text collision!
        """
        if not hasattr(self, "_hud_geom") or self._hud_geom is None or state == ExpressionState.VILLAIN:
            return

        bx1, by1, bx2, by2, sbx1, sbx2, radius, scale_x, scale_y = self._hud_geom
        is_standby = (state == ExpressionState.IDLE)

        gesture_name, progress = None, 0.0
        if getattr(self, "gesture_sentry", None) is not None:
            try:
                gesture_name, progress = self.gesture_sentry.get_feedback()
            except Exception:
                gesture_name, progress = None, 0.0
        elif hasattr(self, "_gesture_feedback"):
            gesture_name, progress = self._gesture_feedback

        progress = max(0.0, min(1.0, float(progress or 0.0)))

        font_size = max(8, int(9.8 * scale_y))
        dot_cy = (by1 + by2) / 2.0
        badge_w = int(48 * scale_x)
        card_w = bx2 - bx1
        avail_text_w = card_w - badge_w - int(22 * scale_x)

        bar_x1_rel = badge_w + int(8 * scale_x)
        bar_x2_rel = card_w - int(14 * scale_x)
        bar_h = int(5 * scale_y)
        bar_y2 = by2 - int(5 * scale_y)
        bar_y1 = bar_y2 - bar_h

        palm_holding = (progress > 0.0) and (gesture_name == "OPEN_PALM" or (gesture_name is None and is_standby))
        fist_holding = (progress > 0.0) and (gesture_name == "CLOSED_FIST" or (gesture_name is None and not is_standby))

        now = time.time()
        talk_pressed = (now - self._last_talk_press_time) < 0.25
        standby_pressed = (now - self._last_standby_press_time) < 0.25

        # 1. LEFT CAPSULE: PALM
        palm_text_x = bx1 + badge_w + (card_w - badge_w - int(10 * scale_x)) * 0.5
        if palm_holding:
            self._create_rounded_rect(
                bx1 + badge_w + int(3 * scale_x), by1 + int(4 * scale_y),
                bx2 - int(6 * scale_x), by2 - int(4 * scale_y),
                radius=max(4, radius - int(5 * scale_y)), fill="#06233b", outline=""
            )
            tx1 = bx1 + bar_x1_rel
            tx2 = bx1 + bar_x2_rel
            track_w = max(10.0, tx2 - tx1)
            fx2 = tx1 + max(4.0, track_w * progress)

            self._create_rounded_rect(tx1, bar_y1, tx2, bar_y2, radius=int(2.5 * scale_y), fill="#041524", outline="")
            fill_col = "#ffffff" if progress >= 0.98 else "#00f0ff"
            self._create_rounded_rect(tx1, bar_y1, fx2, bar_y2, radius=int(2.5 * scale_y), fill=fill_col, outline="")

            sec_held = min(3.0, progress * 3.0)
            pct = int(progress * 100)
            raw_txt = f"HOLDING PALM • {sec_held:.1f}s / 3.0s ({pct}%)"
            txt = self._clamp_button_label(raw_txt, avail_text_w, font_size)
            self.canvas.create_text(palm_text_x, dot_cy - int(3 * scale_y), text=txt, fill="#ffffff", font=(FONT_FAMILY, font_size, "bold"))
        else:
            palm_text_col = "#ffffff" if talk_pressed else ("#e0f2fe" if is_standby else "#64748b")
            palm_label_raw = "OPEN PALM  •  HOLD 3s TO TALK" if is_standby else "OPEN PALM  •  VOICE WAKE READY"
            loud_mode = getattr(self, "loud_alert_mode", None)
            if loud_mode and not is_standby:
                palm_label_raw = "OPEN PALM  •  RAISE TO TALK" if loud_mode == "waiting" else "PALM UP  •  LISTENING..."
                palm_text_col = "#fbbf24"
            palm_label = self._clamp_button_label(palm_label_raw, avail_text_w, font_size)
            self.canvas.create_text(palm_text_x, dot_cy, text=palm_label, fill=palm_text_col, font=(FONT_FAMILY, font_size, "bold"))

        # 2. RIGHT CAPSULE: FIST
        fist_text_x = sbx1 + badge_w + (card_w - badge_w - int(10 * scale_x)) * 0.5
        if fist_holding:
            self._create_rounded_rect(
                sbx1 + badge_w + int(3 * scale_x), by1 + int(4 * scale_y),
                sbx2 - int(6 * scale_x), by2 - int(4 * scale_y),
                radius=max(4, radius - int(5 * scale_y)), fill="#2d0915", outline=""
            )
            tx1 = sbx1 + bar_x1_rel
            tx2 = sbx1 + bar_x2_rel
            track_w = max(10.0, tx2 - tx1)
            fx2 = tx1 + max(4.0, track_w * progress)

            self._create_rounded_rect(tx1, bar_y1, tx2, bar_y2, radius=int(2.5 * scale_y), fill="#1a050c", outline="")
            fill_col = "#ffffff" if progress >= 0.98 else "#ff2a55"
            self._create_rounded_rect(tx1, bar_y1, fx2, bar_y2, radius=int(2.5 * scale_y), fill=fill_col, outline="")

            sec_held = min(3.0, progress * 3.0)
            pct = int(progress * 100)
            raw_txt = f"HOLDING FIST • {sec_held:.1f}s / 3.0s ({pct}%)"
            txt = self._clamp_button_label(raw_txt, avail_text_w, font_size)
            self.canvas.create_text(fist_text_x, dot_cy - int(3 * scale_y), text=txt, fill="#ffffff", font=(FONT_FAMILY, font_size, "bold"))
        else:
            fist_text_col = "#ffffff" if standby_pressed else ("#ffe4e6" if not is_standby else "#64748b")
            fist_label_raw = "CLOSED FIST  •  HOLD 3s FOR STANDBY" if not is_standby else "CLOSED FIST  •  STANDBY LOCKED"
            fist_label = self._clamp_button_label(fist_label_raw, avail_text_w, font_size)
            self.canvas.create_text(fist_text_x, dot_cy, text=fist_label, fill=fist_text_col, font=(FONT_FAMILY, font_size, "bold"))

    def _draw_subtitle_card(self, w: float, h: float, speaker: str, text: str, status_text: str, accent_col: str, card_y1: float):
        """
        Mark II Bionic Telemetry Subtitle Deck:
          - Multi-layered dark glassmorphic command deck with glowing top-left & bottom-right cyber-brackets,
          - Dynamically sized speaker badge pill so long speaker names NEVER overflow the pill border,
          - Strict multi-line word-wrap + vertical line-clamp engine (`_fit_subtitle_text`) so subtitle text
            NEVER overflows horizontally or vertically outside the subtitle shell!
        """
        scale_x = w / 1024.0
        scale_y = h / 600.0
        is_villain = (self.state == ExpressionState.VILLAIN)

        card_x1 = int(70 * scale_x)
        card_x2 = w - card_x1
        card_y2 = h - int(12 * scale_y)
        card_radius = int(16 * scale_y)

        outer_border = "#172b45" if not is_villain else VIL_STEEL_DIM
        inner_border = "#0e1d30" if not is_villain else VIL_GUN
        card_bg = "#060c17" if not is_villain else "#0b0e11"

        # Outer glass shell + inner bevel frame
        self._create_rounded_rect(card_x1, card_y1, card_x2, card_y2, radius=card_radius, fill=card_bg, outline=outer_border, width=2)
        self._create_rounded_rect(
            card_x1 + int(3 * scale_x), card_y1 + int(3 * scale_y),
            card_x2 - int(3 * scale_x), card_y2 - int(3 * scale_y),
            radius=max(4, card_radius - int(3 * scale_y)), fill="", outline=inner_border, width=1
        )

        # Mark II Cyber-Deck Corner Accent Brackets (top-left & bottom-right)
        br_col = accent_col if not is_villain else VIL_AMBER
        br_len = int(22 * scale_x)
        self.canvas.create_line(card_x1 + card_radius, card_y1, card_x1 + card_radius + br_len, card_y1, fill=br_col, width=max(1, int(2.2 * scale_y)), capstyle=tk.ROUND)
        self.canvas.create_line(card_x2 - card_radius - br_len, card_y2, card_x2 - card_radius, card_y2, fill=br_col, width=max(1, int(2.2 * scale_y)), capstyle=tk.ROUND)

        # Speaker Badge Pill (auto-sized to fit speaker label with zero overflow)
        spk_label = (speaker or "NEUROLIS MARK II").strip().upper() if (speaker and speaker.strip()) else "NEUROLIS MARK II"
        if is_villain:
            pill_fill = VIL_EMBER_DARK
            pill_border = VIL_AMBER
            pill_text_col = VIL_AMBER_SOFT
            display_spk = "● NEUROLIS // ROOT ACCESS"
        elif spk_label in ["YOU", "USER"]:
            pill_fill = "#042b22"
            pill_border = "#00ffaa"
            pill_text_col = "#00ffaa"
            display_spk = "● USER // VOICE INPUT"
        elif spk_label in ["NEUROLIS", "NEUROLIS MARK II"]:
            pill_fill = "#06223d"
            pill_border = "#00f0ff"
            pill_text_col = "#00f0ff"
            display_spk = "● NEUROLIS MARK II"
        else:
            pill_fill = "#121c2d"
            pill_border = "#38bdf8"
            pill_text_col = "#bae6fd"
            display_spk = f"● {spk_label[:26]}"

        pill_font_px = max(8, int(9.0 * scale_y))
        pill_w = max(int(138 * scale_x), int((len(display_spk) * (pill_font_px * 0.65)) + 26 * scale_x))
        pill_h = int(22 * scale_y)
        px1 = card_x1 + int(16 * scale_x)
        py1 = card_y1 + int(8 * scale_y)

        self._create_rounded_rect(
            px1, py1, px1 + pill_w, py1 + pill_h,
            radius=int(8 * scale_y), fill=pill_fill, outline=pill_border, width=1
        )
        self.canvas.create_text(
            px1 + pill_w / 2.0, py1 + pill_h / 2.0,
            text=display_spk, fill=pill_text_col,
            font=(FONT_FAMILY, pill_font_px, "bold")
        )

        # Right telemetry status pill inside subtitle header
        safe_status = (status_text or "STANDBY // READY")[:34]
        self.canvas.create_text(
            card_x2 - int(18 * scale_x), py1 + pill_h / 2.0,
            text=safe_status,
            fill=VIL_AMBER_SOFT if is_villain else "#64748b",
            font=(MONO_FONT_FAMILY, max(8, int(8.8 * scale_y)), "bold"),
            anchor="e"
        )

        divider_y = py1 + pill_h + int(5 * scale_y)
        self.canvas.create_line(
            px1, divider_y,
            card_x2 - int(16 * scale_x), divider_y,
            fill="#112238" if not is_villain else VIL_GUN, width=1
        )

        # Strict multi-line word-wrap & height clamp so subtitle text NEVER escapes the subtitle shell
        avail_w_px = (card_x2 - card_x1) - int(44 * scale_x)
        avail_h_px = (card_y2 - divider_y) - int(14 * scale_y)
        safe_text = text if (text and text.strip()) else ("Standing by. Show open palm or press Enter to begin." if self.state == ExpressionState.IDLE else "...")
        wrapped_text, font_size = self._fit_subtitle_text(safe_text, avail_w_px, avail_h_px, scale_y)

        # Left vertical neon accent bar beside subtitle text + bottom-right Mark II telemetry micro-footer
        bar_top = divider_y + int(8 * scale_y)
        bar_bot = card_y2 - int(12 * scale_y)
        self.canvas.create_line(
            px1 + int(2 * scale_x), bar_top,
            px1 + int(2 * scale_x), bar_bot,
            fill=br_col, width=max(2, int(3.0 * scale_x)), capstyle=tk.ROUND
        )
        if is_villain:
            footer_txt = "CONTROL: OVERRIDDEN // 0x7F"
            footer_col = "#7a4a1a"
        else:
            footer_txt = self.telemetry_footer_text if self.telemetry_footer_text else "MARK II TELEMETRY  •  AUDIO SYNC: LOCKED"
            footer_col = "#fbbf24" if self.telemetry_alert_level == "warn" else "#475569"
        self.canvas.create_text(
            card_x2 - int(18 * scale_x), card_y2 - int(10 * scale_y),
            text=footer_txt,
            fill=footer_col,
            font=(MONO_FONT_FAMILY, max(7, int(7.8 * scale_y)), "bold"),
            anchor="e"
        )

        text_x = px1 + int(12 * scale_x)
        self._sub_geom = (card_x1, card_y1, card_x2, card_y2, card_radius, divider_y, text_x, font_size, wrapped_text, avail_w_px)

        if not is_villain:
            self.canvas.create_text(
                text_x, divider_y + int(7 * scale_y),
                text=wrapped_text,
                fill="#f8fafc",
                font=(FONT_FAMILY, font_size, "bold"),
                anchor="nw",
                width=int(avail_w_px),
            )

    # =========================================================================
    # APPLE VISION PRO / MACOS GRADE BOOT SPLASH
    # =========================================================================
    def _draw_boot_greeting(self, w: float, h: float, elapsed: float):
        """Apple-grade Startup Splash for Neurolis Mark II."""
        self.canvas.delete("all")
        self.canvas.create_rectangle(0, 0, w, h, fill=self.bg_color, outline="")

        scale_x = w / 1024.0
        scale_y = h / 600.0
        cx = w / 2.0
        cy = h / 2.0

        if elapsed < 0.75:
            alpha = 0.5 - 0.5 * math.cos((elapsed / 0.75) * math.pi)
        elif elapsed < 2.65:
            alpha = 1.0
        elif elapsed < self.boot_duration:
            fade_p = (elapsed - 2.65) / max(0.01, (self.boot_duration - 2.65))
            alpha = 0.5 + 0.5 * math.cos(fade_p * math.pi)
        else:
            alpha = 0.0

        raw_p = max(0.0, min(1.0, (elapsed - 0.25) / 2.35))
        prog = raw_p * raw_p * (3.0 - 2.0 * raw_p)

        # 1. Subtle Radial Backlight Halo
        for r_mult, c_target in [(250, "#050d1a"), (175, "#07162c"), (115, "#0b2242")]:
            rx = r_mult * scale_x
            ry = r_mult * 0.70 * scale_y
            col = lerp_color(self.bg_color, c_target, alpha)
            self.canvas.create_oval(cx - rx, cy - 64 * scale_y - ry, cx + rx, cy - 64 * scale_y + ry, fill=col, outline="")

        # 2. Apple Vision-Grade Bionic Visor Crest
        crest_cy = cy - 88 * scale_y
        vw = 128 * scale_x
        vh = 72 * scale_y
        vr = int(34 * scale_y)
        vx1, vy1 = cx - vw / 2.0, crest_cy - vh / 2.0
        vx2, vy2 = cx + vw / 2.0, crest_cy + vh / 2.0

        orb_r = 52 * scale_y
        orb_col = lerp_color(self.bg_color, "#1e3a5f", alpha * 0.7)
        self.canvas.create_oval(cx - orb_r, crest_cy - orb_r, cx + orb_r, crest_cy + orb_r, fill="", outline=orb_col, width=max(1, int(1.5 * scale_y)))

        aura_col = lerp_color(self.bg_color, "#0ea5e9", alpha * 0.25)
        self._create_rounded_rect(
            vx1 - 6 * scale_x, vy1 - 6 * scale_y, vx2 + 6 * scale_x, vy2 + 6 * scale_y,
            vr + int(4 * scale_y), fill=aura_col, outline=""
        )

        body_col = lerp_color(self.bg_color, "#071120", alpha)
        rim_outer = lerp_color(self.bg_color, "#e2e8f0", alpha * 0.92)
        rim_inner = lerp_color(self.bg_color, "#38bdf8", alpha * 0.65)
        self._create_rounded_rect(vx1, vy1, vx2, vy2, vr, fill=body_col, outline=rim_outer, width=max(1, int(2.2 * scale_y)))
        self._create_rounded_rect(
            vx1 + 4 * scale_x, vy1 + 4 * scale_y, vx2 - 4 * scale_x, vy2 - 4 * scale_y,
            max(6, vr - int(4 * scale_y)), fill="", outline=rim_inner, width=1
        )

        eye_glow = lerp_color(self.bg_color, "#0284c7", alpha * 0.55)
        eye_col = lerp_color(self.bg_color, "#00f0ff", alpha)
        glint_col = lerp_color(self.bg_color, "#ffffff", alpha)
        ew_m = 22 * scale_x
        eh_m = 24 * scale_y
        for side in (-1, 1):
            ex = cx + side * 24 * scale_x
            ey = crest_cy
            self._create_rounded_rect(
                ex - ew_m / 2.0 - 3 * scale_x, ey - eh_m / 2.0 - 3 * scale_y,
                ex + ew_m / 2.0 + 3 * scale_x, ey + eh_m / 2.0 + 3 * scale_y,
                int(9 * scale_y), fill=eye_glow, outline=""
            )
            self._create_rounded_rect(
                ex - ew_m / 2.0, ey - eh_m / 2.0,
                ex + ew_m / 2.0, ey + eh_m / 2.0,
                int(7 * scale_y), fill=eye_col, outline=""
            )
            self.canvas.create_oval(
                ex - ew_m * 0.28, ey - eh_m * 0.28,
                ex - ew_m * 0.02, ey - eh_m * 0.02,
                fill=glint_col, outline=""
            )

        sheen_x = vx1 + 24 * scale_x + prog * (vw - 48 * scale_x)
        sheen_col = lerp_color(self.bg_color, "#ffffff", alpha * math.sin(prog * math.pi))
        self.canvas.create_oval(
            sheen_x - 14 * scale_x, vy1 - 2 * scale_y, sheen_x + 14 * scale_x, vy1 + 2 * scale_y,
            fill=sheen_col, outline=""
        )

        # 3. Apple-Grade Hero Typography: Neurolis Mark 2
        title_col = lerp_color(self.bg_color, "#f8fafc", alpha)
        self.canvas.create_text(
            cx, cy + 26 * scale_y,
            text="Neurolis Mark 2",
            fill=title_col,
            font=(FONT_FAMILY, int(34 * scale_y), "bold")
        )

        # 4. Minimalist Apple-Style Pill Progress Bar
        bar_w = 240 * scale_x
        bar_h = 6 * scale_y
        bar_y = cy + 82 * scale_y
        bx1 = cx - bar_w / 2.0
        bx2 = cx + bar_w / 2.0

        track_bg = lerp_color(self.bg_color, "#111c2d", alpha)
        track_border = lerp_color(self.bg_color, "#1e293b", alpha)
        self._create_rounded_rect(
            bx1, bar_y - bar_h / 2.0, bx2, bar_y + bar_h / 2.0,
            int(3 * scale_y), fill=track_bg, outline=track_border, width=1
        )

        if prog > 0.01:
            fill_w = max(8 * scale_x, bar_w * prog)
            fx2 = bx1 + fill_w
            glow_bar = lerp_color(self.bg_color, "#0284c7", alpha * 0.55)
            core_bar = lerp_color(self.bg_color, "#f8fafc", alpha)
            self._create_rounded_rect(
                bx1 - 2 * scale_x, bar_y - bar_h / 2.0 - 2 * scale_y,
                fx2 + 2 * scale_x, bar_y + bar_h / 2.0 + 2 * scale_y,
                int(5 * scale_y), fill=glow_bar, outline=""
            )
            self._create_rounded_rect(
                bx1, bar_y - bar_h / 2.0, fx2, bar_y + bar_h / 2.0,
                int(3 * scale_y), fill=core_bar, outline=""
            )
            self.canvas.create_oval(
                fx2 - 4 * scale_y, bar_y - 4 * scale_y,
                fx2 + 4 * scale_y, bar_y + 4 * scale_y,
                fill=core_bar, outline=""
            )

        # 5. Booting Status Caption
        boot_pulse = 0.72 + 0.28 * math.sin(elapsed * 6.0)
        cap_col = lerp_color(self.bg_color, "#38bdf8", alpha * boot_pulse)
        self.canvas.create_text(
            cx, cy + 115 * scale_y,
            text="Booting...",
            fill=cap_col,
            font=(FONT_FAMILY, int(11 * scale_y), "bold")
        )
        if hasattr(self.canvas, "set_rough_mode"):
            self.canvas.set_rough_mode(False)
        if hasattr(self.canvas, "flush"):
            self.canvas.flush()


if __name__ == "__main__":
    print("Testing Neurolis Mark II Face UI (22 Expressions + Apple-Grade Animations & Boot Splash)...")
    print("Shortcuts: [1-9, 0] Core States | [Q-P, C] 11 New Chat States | [V] Villain | [B] Boot | [Space/Tab] Cycle")
    ui = FaceUI(width=1024, height=600, fullscreen=False)
    ui.start(in_background=False)