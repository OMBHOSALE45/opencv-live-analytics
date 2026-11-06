"""
OpenCV Telemetry Extractor for Free Fire / Battle Royale Live Analytics.
Reads ACTUAL on-screen data from calibrated ROIs and HUD elements in every live frame.
NO hardcoded seed data. Every value is derived from the pixels captured.

Target Fields:
  - hp_bar        -> { level (0-200), max (200), percentage (0-100), status }
  - ep_bar        -> { level (0-200), max (200), percentage (0-100), status }
  - playername    -> { active (bool), score (float), value (str) }
  - eliminations  -> { count (int), active (bool), score (float) }

INTEGRATED WINDOWS NATIVE OCR:
  Uses Windows 10/11 built-in Windows.Media.Ocr engine via PowerShell (zero external dependencies).
  Runs in a dedicated non-blocking background thread so the video stream maintains 30+ FPS.
  Extracts:
    - Exact Player Name string (e.g. "STIVEN !!")
    - Exact Eliminations number (e.g. 4)
    - Exact HP reading (e.g. 86 / 200)
"""

import os
import sys
import json
import time
import re
import subprocess
import threading
from datetime import datetime
from typing import Dict, Any, Optional, Tuple

import cv2
import numpy as np

VISION_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(VISION_DIR)
OCR_PS1_PATH = os.path.join(VISION_DIR, "win_ocr.ps1")
TMP_OCR_IMAGE = os.path.join(PROJECT_ROOT, "recordings", "snapshots", "_ocr_feed.jpg")

# Ensure PowerShell OCR script exists
PS1_SCRIPT = """param([string]$ImagePath)

Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
Function AwaitTask($WinRtTask, $ResultType) {
    $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    $netTask.Result
}

[Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime] | Out-Null
[Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType = WindowsRuntime] | Out-Null
[Windows.Storage.Streams.InMemoryRandomAccessStream, Windows.Storage.Streams, ContentType = WindowsRuntime] | Out-Null

$bytes = [System.IO.File]::ReadAllBytes((Resolve-Path $ImagePath).Path)
$stream = [Windows.Storage.Streams.InMemoryRandomAccessStream]::new()
$writer = [Windows.Storage.Streams.DataWriter]::new($stream)
$writer.WriteBytes($bytes)
$null = AwaitTask ($writer.StoreAsync()) ([System.UInt32])
$null = AwaitTask ($writer.FlushAsync()) ([System.Boolean])
$stream.Seek(0)

$decoder = AwaitTask ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap = AwaitTask ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])

$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
if (-not $engine) {
    $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new('en-US'))
}
$result = AwaitTask ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])

Write-Host "OCR_TEXT:$($result.Text)"
"""

try:
    with open(OCR_PS1_PATH, "w", encoding="utf-8") as _f:
        _f.write(PS1_SCRIPT)
except Exception:
    pass


# ---------------------------------------------------------------------------
# WINDOWS OCR ASYNC WORKER
# ---------------------------------------------------------------------------

class WindowsHUDOCRWorker:
    """
    Non-blocking background worker that runs Windows built-in Media OCR
    on the HUD region to extract player name, eliminations, and HP digits.
    """

    def __init__(self):
        self.lock = threading.Lock()
        self.is_busy = False
        self.latest_name: Optional[str] = None
        self.latest_elim: Optional[int] = None
        self.latest_hp: Optional[int] = None
        self.latest_raw_text: str = ""
        self.last_run_time = 0.0

    def parse_ocr_text(self, text: str) -> Tuple[Optional[str], Optional[int], Optional[int]]:
        """
        Parses OCR text like "STIVEN !! 86/200 Elim 4" into (name, elim, hp).
        """
        if not text:
            return None, None, None

        # 1. Eliminations
        elim_val = None
        elim_match = re.search(r"elim\s*[:=\-]?\s*(\d+)", text, re.IGNORECASE)
        if elim_match:
            elim_val = int(elim_match.group(1))

        # 2. HP (e.g. 86/200)
        hp_val = None
        hp_match = re.search(r"(\d+)\s*/\s*200", text)
        if not hp_match:
            hp_match = re.search(r"(\d+)\s*/\s*(\d+)", text)
        if hp_match:
            val = int(hp_match.group(1))
            if 0 <= val <= 250:
                hp_val = val

        # 3. Player Name: strip out Elim and HP parts
        name_clean = text
        if elim_match:
            name_clean = re.sub(r"elim\s*[:=\-]?\s*\d+\s*!?", "", name_clean, flags=re.IGNORECASE)
        if hp_match:
            name_clean = name_clean.replace(hp_match.group(0), "")

        # Clean trailing noise/punctuation; Free Fire often has 'STIVEN !!' where '!!' is OCR'd as 't' or '!'
        name_clean = re.sub(r"elim\S*", "", name_clean, flags=re.IGNORECASE)
        name_clean = re.sub(r"\s+[tl!]+$", " !!", name_clean)
        name_clean = " ".join(name_clean.split()).strip()

        # If name has at least 2 alphanumeric chars, keep it
        name_val = name_clean if len(re.findall(r"\w", name_clean)) >= 2 else None

        return name_val, elim_val, hp_val

    def _execute_ocr_sync(self, image_crop: np.ndarray) -> None:
        try:
            h, w = image_crop.shape[:2]
            if h < 10 or w < 10:
                return

            # Scale 4x for optimal OCR accuracy on small HUD text
            scaled = cv2.resize(image_crop, (w * 4, h * 4), interpolation=cv2.INTER_CUBIC)
            os.makedirs(os.path.dirname(TMP_OCR_IMAGE), exist_ok=True)
            cv2.imwrite(TMP_OCR_IMAGE, scaled)

            res = subprocess.run(
                ["powershell", "-ExecutionPolicy", "Bypass", "-File", OCR_PS1_PATH, "-ImagePath", os.path.abspath(TMP_OCR_IMAGE)],
                capture_output=True,
                text=True,
                timeout=3.0
            )

            out = res.stdout.strip()
            match = re.search(r"OCR_TEXT:(.*)", out)
            if match:
                raw_text = match.group(1).strip()
                name, elim, hp = self.parse_ocr_text(raw_text)
                with self.lock:
                    self.latest_raw_text = raw_text
                    if name:
                        self.latest_name = name
                    if elim is not None:
                        self.latest_elim = elim
                    if hp is not None:
                        self.latest_hp = hp
        except Exception:
            pass
        finally:
            with self.lock:
                self.is_busy = False

    def request_ocr(self, image_crop: np.ndarray, sync: bool = False) -> None:
        """
        Submits an image crop for OCR processing.
        If sync=True, runs immediately on the calling thread (for static tests).
        Otherwise launches a daemon thread (for real-time live capture).
        """
        now = time.time()
        with self.lock:
            if self.is_busy:
                return
            if not sync and (now - self.last_run_time < 0.8):
                return
            self.is_busy = True
            self.last_run_time = now

        if sync:
            self._execute_ocr_sync(image_crop)
        else:
            t = threading.Thread(target=self._execute_ocr_sync, args=(image_crop.copy(),), daemon=True)
            t.start()

    def get_results(self) -> Dict[str, Any]:
        with self.lock:
            return {
                "name": self.latest_name,
                "elim": self.latest_elim,
                "hp": self.latest_hp,
                "raw_text": self.latest_raw_text
            }


# Global singleton OCR worker
_ocr_worker = WindowsHUDOCRWorker()


# ---------------------------------------------------------------------------
# CORE VISION PRIMITIVES
# ---------------------------------------------------------------------------

def _safe_crop(frame: np.ndarray, x: int, y: int, w: int, h: int) -> Optional[np.ndarray]:
    """Safe sub-region crop with boundary clamping."""
    fh, fw = frame.shape[:2]
    x1 = max(0, min(int(x), fw - 1))
    y1 = max(0, min(int(y), fh - 1))
    x2 = max(x1 + 1, min(int(x + w), fw))
    y2 = max(y1 + 1, min(int(y + h), fh))
    crop = frame[y1:y2, x1:x2]
    return crop if crop.size > 0 else None


def _scale_roi(roi_box: Dict[str, int], calib_w: int, calib_h: int,
               frame_w: int, frame_h: int) -> Dict[str, int]:
    """Scales an ROI from calibration dimensions to current frame dimensions."""
    if calib_w <= 0 or calib_h <= 0:
        return roi_box
    sx = frame_w / calib_w
    sy = frame_h / calib_h
    return {
        "x":      int(roi_box.get("x", 0)      * sx),
        "y":      int(roi_box.get("y", 0)      * sy),
        "width":  max(1, int(roi_box.get("width",  1) * sx)),
        "height": max(1, int(roi_box.get("height", 1) * sy)),
    }


def normalize_roi_key(key: str) -> str:
    """Normalizes any naming convention into one of the 4 target fields."""
    k = key.lower().replace("_", "").replace("-", "")
    if "hp" in k or "health" in k:
        return "hp_bar"
    if "ep" in k:
        return "ep_bar"
    if "player" in k or "name" in k:
        return "playername"
    if "elim" in k or "kill" in k or "feed" in k:
        return "eliminations"
    return key


def measure_hp_bar_pixels(crop: np.ndarray) -> float:
    """
    Measures HP bar fill (0.0 - 100.0%) from Free Fire's horizontal health bar crop.
    Free Fire uses a bright white/grey fill (gray > 190) that fills from left to right.
    """
    if crop is None or crop.size == 0:
        return 0.0

    h, w = crop.shape[:2]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

    # Threshold for the bright white HP fill
    bright = gray > 185
    min_rows = max(1, h // 4)
    col_filled = np.sum(bright, axis=0) >= min_rows

    if not np.any(col_filled):
        return 0.0

    filled_indices = np.where(col_filled)[0]
    left_bound = int(filled_indices[0])

    last_fill_col = left_bound
    gap = 0
    for i in range(left_bound, w):
        if col_filled[i]:
            last_fill_col = i
            gap = 0
        else:
            gap += 1
            if gap >= 6:
                break

    pct = ((last_fill_col + 1) / float(w)) * 100.0
    return round(min(100.0, max(0.0, pct)), 1)


def measure_ep_bar_pixels(crop: np.ndarray) -> float:
    """
    Measures EP bar fill (0.0 - 100.0%) from Free Fire's yellow/amber EP bar crop.
    Strictly checks for saturated yellow/amber hues (HSV H: 18-38, Sat > 100, Val > 100).
    """
    if crop is None or crop.size == 0:
        return 0.0

    h, w = crop.shape[:2]
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)

    yellow_mask = (
        (hsv[:, :, 0] >= 18) & (hsv[:, :, 0] <= 38) &
        (hsv[:, :, 1] > 100) & (hsv[:, :, 2] > 100)
    )

    min_rows = max(2, h // 3)
    col_filled = np.sum(yellow_mask, axis=0) >= min_rows

    # Require at least 5 columns of solid yellow
    if np.sum(col_filled) < 5:
        return 0.0

    filled_indices = np.where(col_filled)[0]
    left_bound = int(filled_indices[0])

    last_fill_col = left_bound
    gap = 0
    for i in range(left_bound, w):
        if col_filled[i]:
            last_fill_col = i
            gap = 0
        else:
            gap += 1
            if gap >= 6:
                break

    pct = ((last_fill_col + 1) / float(w)) * 100.0
    return round(min(100.0, max(0.0, pct)), 1)


def find_hud_banner_crop(frame: np.ndarray, rois: Optional[Dict[str, Dict[str, int]]],
                         calib_w: int, calib_h: int) -> Optional[np.ndarray]:
    """
    Finds the complete HUD banner (which contains player name, Elim X, and HP bar).
    1. If ROIs are available, computes their union with small padding.
    2. Fallback: scans the bottom-center region (35-65% width, 80-98% height).
    """
    fh, fw = frame.shape[:2]

    if rois:
        scaled_boxes = [_scale_roi(b, calib_w, calib_h, fw, fh) for b in rois.values()]
        x1 = max(0, min(b["x"] for b in scaled_boxes) - 10)
        y1 = max(0, min(b["y"] for b in scaled_boxes) - 10)
        x2 = min(fw, max(b["x"] + b["width"] for b in scaled_boxes) + 10)
        y2 = min(fh, max(b["y"] + b["height"] for b in scaled_boxes) + 25)
        return _safe_crop(frame, x1, y1, x2 - x1, y2 - y1)

    # Heuristic fallback: Free Fire bottom HUD
    return _safe_crop(frame, int(fw * 0.32), int(fh * 0.80), int(fw * 0.36), int(fh * 0.18))


# ---------------------------------------------------------------------------
# MAIN PARSER — 4 TARGET FIELDS WITH HYBRID PIXEL + NATIVE OCR
# ---------------------------------------------------------------------------

class FreeFireSpectatorParser:
    """
    Extracts HUD telemetry live from screen pixels with native OCR recognition.
    Target fields:
      - hp_bar
      - ep_bar
      - playername
      - eliminations
    """

    def __init__(self):
        self.ocr_worker = _ocr_worker

    def parse_frame(
        self,
        frame: np.ndarray,
        rois: Optional[Dict[str, Dict[str, int]]] = None,
        calib_resolution: Optional[Dict[str, int]] = None,
        sync_ocr: bool = False
    ) -> Dict[str, Any]:
        """
        Parses live frame and extracts: hp_bar, ep_bar, playername, eliminations.
        """
        frame_h, frame_w = frame.shape[:2]
        calib_w = calib_resolution.get("width", 0) if calib_resolution else 0
        calib_h = calib_resolution.get("height", 0) if calib_resolution else 0

        # Trigger background OCR on the HUD banner
        banner_crop = find_hud_banner_crop(frame, rois, calib_w, calib_h)
        if banner_crop is not None:
            self.ocr_worker.request_ocr(banner_crop, sync=sync_ocr)

        ocr_data = self.ocr_worker.get_results()

        # Defaults
        result: Dict[str, Any] = {
            "hp_bar": {
                "level": 0,
                "max": 200,
                "percentage": 0.0,
                "status": "UNKNOWN"
            },
            "ep_bar": {
                "level": 0,
                "max": 200,
                "percentage": 0.0,
                "status": "UNKNOWN"
            },
            "playername": {
                "active": False,
                "score": 0.0,
                "value": ocr_data["name"] or "IDLE"
            },
            "eliminations": {
                "count": ocr_data["elim"] if ocr_data["elim"] is not None else 0,
                "active": False,
                "score": 0.0
            },
            # Flat backwards-compatible keys
            "hp_level": 0,
            "hp_max": 200,
            "hp_percentage": 0.0,
            "hp_status": "UNKNOWN",
            "ep_level": 0,
            "ep_max": 200,
            "ep_percentage": 0.0,
            "ep_status": "UNKNOWN",
            "player_name_active": False,
            "eliminations_count": ocr_data["elim"] if ocr_data["elim"] is not None else 0,
        }

        # ----------------------------------------------------------------
        # STEP 1: Process Individual ROIs
        # ----------------------------------------------------------------
        if rois:
            for raw_name, roi_box in rois.items():
                target_field = normalize_roi_key(raw_name)
                scaled = _scale_roi(roi_box, calib_w, calib_h, frame_w, frame_h)
                crop = _safe_crop(frame, scaled["x"], scaled["y"], scaled["width"], scaled["height"])
                if crop is None:
                    continue

                # 1. HP BAR
                if target_field == "hp_bar":
                    # Pixel fill measurement
                    pct = measure_hp_bar_pixels(crop)
                    hp_val = int(round((pct / 100.0) * 200))

                    # If OCR confirmed the exact HP number (e.g. 86), use it
                    if ocr_data["hp"] is not None:
                        hp_val = ocr_data["hp"]
                        pct = round((hp_val / 200.0) * 100.0, 1)

                    status = (
                        "DEAD" if hp_val == 0 else
                        "CRITICAL" if pct < 25 else
                        "LOW" if pct < 50 else
                        "HEALTHY"
                    )
                    result["hp_bar"] = {
                        "level": hp_val,
                        "max": 200,
                        "percentage": pct,
                        "status": status
                    }
                    result["hp_level"] = hp_val
                    result["hp_percentage"] = pct
                    result["hp_status"] = status

                # 2. EP BAR
                elif target_field == "ep_bar":
                    pct = measure_ep_bar_pixels(crop)
                    ep_val = int(round((pct / 100.0) * 200))
                    status = (
                        "EMPTY" if ep_val == 0 else
                        "FULL" if pct > 90 else
                        "NORMAL"
                    )
                    result["ep_bar"] = {
                        "level": ep_val,
                        "max": 200,
                        "percentage": pct,
                        "status": status
                    }
                    result["ep_level"] = ep_val
                    result["ep_percentage"] = pct
                    result["ep_status"] = status

                # 3. PLAYERNAME
                elif target_field == "playername":
                    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
                    edges = cv2.Canny(gray, 40, 120)
                    density = float(np.count_nonzero(edges)) / max(edges.size, 1) * 100.0
                    is_active = density > 1.2
                    p_name = ocr_data["name"] or ("DETECTED" if is_active else "IDLE")

                    result["playername"] = {
                        "active": is_active,
                        "score": round(density, 2),
                        "value": p_name
                    }
                    result["player_name_active"] = is_active

                # 4. ELIMINATIONS
                elif target_field == "eliminations":
                    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
                    edges = cv2.Canny(gray, 40, 120)
                    density = float(np.count_nonzero(edges)) / max(edges.size, 1) * 100.0
                    is_active = density > 1.0

                    elim_cnt = ocr_data["elim"] if ocr_data["elim"] is not None else 0

                    result["eliminations"] = {
                        "count": elim_cnt,
                        "active": is_active,
                        "score": round(density, 2)
                    }
                    result["eliminations_count"] = elim_cnt

        # ----------------------------------------------------------------
        # STEP 2: Fallback when no ROIs or bar level is 0
        # ----------------------------------------------------------------
        if not rois or result["hp_bar"]["level"] == 0:
            if ocr_data["hp"] is not None:
                hp_val = ocr_data["hp"]
                pct = round((hp_val / 200.0) * 100.0, 1)
                status = "CRITICAL" if pct < 25 else ("LOW" if pct < 50 else "HEALTHY")
                result["hp_bar"] = {"level": hp_val, "max": 200, "percentage": pct, "status": status}
                result["hp_level"] = hp_val
                result["hp_percentage"] = pct
                result["hp_status"] = status

        if ocr_data["name"] and result["playername"]["value"] in ["IDLE", "DETECTED"]:
            result["playername"]["value"] = ocr_data["name"]
            result["playername"]["active"] = True
            result["player_name_active"] = True

        if ocr_data["elim"] is not None:
            result["eliminations"]["count"] = ocr_data["elim"]
            result["eliminations_count"] = ocr_data["elim"]

        return result


# ---------------------------------------------------------------------------
# ATOMIC JSON TELEMETRY EXPORT
# ---------------------------------------------------------------------------

def export_telemetry_json(
    output_path: str,
    telemetry_data: Dict[str, Any],
    screen_stats: Optional[Dict[str, Any]] = None,
    source: str = "live_stream"
) -> Dict[str, Any]:
    """Writes live telemetry to JSON."""
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    hp_info = telemetry_data.get("hp_bar", {})
    ep_info = telemetry_data.get("ep_bar", {})
    p_info  = telemetry_data.get("playername", {})
    e_info  = telemetry_data.get("eliminations", {})

    packet = {
        "timestamp": datetime.now().isoformat(),
        "source": source,
        "game": "Free Fire",

        # --- THE 4 TARGET FIELDS ---
        "hp_bar": {
            "level":      hp_info.get("level", telemetry_data.get("hp_level", 0)),
            "max":        hp_info.get("max", telemetry_data.get("hp_max", 200)),
            "percentage": hp_info.get("percentage", telemetry_data.get("hp_percentage", 0.0)),
            "status":     hp_info.get("status", telemetry_data.get("hp_status", "UNKNOWN"))
        },
        "ep_bar": {
            "level":      ep_info.get("level", telemetry_data.get("ep_level", 0)),
            "max":        ep_info.get("max", telemetry_data.get("ep_max", 200)),
            "percentage": ep_info.get("percentage", telemetry_data.get("ep_percentage", 0.0)),
            "status":     ep_info.get("status", telemetry_data.get("ep_status", "UNKNOWN"))
        },
        "playername": {
            "active": p_info.get("active", telemetry_data.get("player_name_active", False)),
            "score":  p_info.get("score", 0.0),
            "value":  p_info.get("value", "IDLE")
        },
        "eliminations": {
            "count":  e_info.get("count", telemetry_data.get("eliminations_count", 0)),
            "active": e_info.get("active", False),
            "score":  e_info.get("score", 0.0)
        },

        # --- Flat Aliases ---
        "hp_level":           hp_info.get("level", telemetry_data.get("hp_level", 0)),
        "hp_max":             hp_info.get("max", telemetry_data.get("hp_max", 200)),
        "hp_percentage":      hp_info.get("percentage", telemetry_data.get("hp_percentage", 0.0)),
        "hp_status":          hp_info.get("status", telemetry_data.get("hp_status", "UNKNOWN")),
        "ep_level":           ep_info.get("level", telemetry_data.get("ep_level", 0)),
        "ep_max":             ep_info.get("max", telemetry_data.get("ep_max", 200)),
        "ep_percentage":      ep_info.get("percentage", telemetry_data.get("ep_percentage", 0.0)),
        "ep_status":          ep_info.get("status", telemetry_data.get("ep_status", "UNKNOWN")),
        "player_name_active": p_info.get("active", telemetry_data.get("player_name_active", False)),
        "eliminations_count": e_info.get("count", telemetry_data.get("eliminations_count", 0)),

        # --- Diagnostics ---
        "screen_stats": screen_stats or {}
    }

    payload = json.dumps(packet, indent=4)

    for attempt in range(3):
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(payload)
            break
        except (PermissionError, OSError):
            if attempt < 2:
                time.sleep(0.015)

    return packet
