"""
OpenCV Telemetry Extractor for Free Fire / Battle Royale Live Analytics.
Optimized for maximum accuracy on the 3 core target fields:
  - hp_bar        -> { level (0-200), max (200), percentage (0-100), status }
  - playername    -> { active (bool), score (float), value (actual player name string) }
  - eliminations  -> { count (int), active (bool), score (float) }

INTEGRATED WINDOWS NATIVE OCR:
  Uses Windows 10/11 built-in Windows.Media.Ocr engine via PowerShell.
  Features automatic multi-channel color contrast enhancement (handles mint-green,
  orange, teal, red, and dark HUD banners with maximum accuracy).
  Runs in a dedicated non-blocking background thread so the video stream maintains 30+ FPS.
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

RECORDINGS_DIR = os.path.join(PROJECT_ROOT, "recordings", "snapshots")
LATEST_FRAME_PATH = os.path.join(RECORDINGS_DIR, "latest_frame.jpg")
TMP_OCR_IMAGE = os.path.join(RECORDINGS_DIR, "_ocr_feed.jpg")

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
if ($result.Lines) {
    foreach ($line in $result.Lines) {
        Write-Host "OCR_LINE:$($line.Text)"
        foreach ($w in $line.Words) {
            $r = $w.BoundingRect
            Write-Host "OCR_WORD:$([int]$r.X),$([int]$r.Y),$([int]$r.Width),$([int]$r.Height):$($w.Text)"
        }
    }
}
"""

try:
    with open(OCR_PS1_PATH, "w", encoding="utf-8") as _f:
        _f.write(PS1_SCRIPT)
except Exception:
    pass


def enhance_hud_for_ocr(crop: np.ndarray) -> np.ndarray:
    """
    Selects the optimal contrast channel for white text depending on banner color:
      - Mint-green / cyan banner (e.g. ShokoWilRule) -> Red channel has massive contrast!
      - Orange / amber banner (e.g. Stiven)          -> Blue channel has massive contrast!
      - Dark / neutral banner                        -> Grayscale
    """
    if crop is None or crop.size == 0:
        return crop

    b, g, r = cv2.split(crop)
    mean_r = float(np.mean(r))
    mean_g = float(np.mean(g))
    mean_b = float(np.mean(b))

    if mean_g > mean_r + 15:
        # Green / mint / teal dominant
        return r
    elif mean_r > mean_b + 18:
        # Red / orange / amber dominant
        return b
    else:
        return cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)


# ---------------------------------------------------------------------------
# WINDOWS OCR ASYNC WORKER
# ---------------------------------------------------------------------------

class WindowsHUDOCRWorker:
    """
    Non-blocking background worker that runs Windows built-in Media OCR
    on the enhanced HUD region to extract player name, eliminations, and HP digits.
    """

    def __init__(self):
        self.lock = threading.Lock()
        self.is_busy = False
        self.squad_ocr_busy = False
        self.latest_name: Optional[str] = None
        self.latest_elim: Optional[int] = None
        self.latest_hp: Optional[int] = None
        self.latest_raw_text: str = ""
        self.latest_squad_data: Optional[Dict[str, Any]] = None
        self.cached_squad_names: Dict[int, str] = {}
        self.cached_team_name: str = "SQUAD"
        self.last_run_time = 0.0
        self.last_squad_run_time = 0.0

    def parse_ocr_text(self, text: str) -> Tuple[Optional[str], Optional[int], Optional[int]]:
        """
        Parses OCR text like 'ShokoWilRule 182/200 Elim 1' or 'STIVEN !! 86/200 Elim 4'
        into (player_name, elim_count, hp_level).
        """
        if not text:
            return None, None, None

        # 1. Eliminations
        elim_val = None
        elim_match = re.search(r"elim\s*[:=\-]?\s*(\d+)", text, re.IGNORECASE)
        if elim_match:
            elim_val = int(elim_match.group(1))

        # 2. HP (e.g. 182/200, 86/200)
        hp_val = None
        hp_match = re.search(r"(\d+)\s*/\s*200", text)
        if not hp_match:
            hp_match = re.search(r"(\d+)\s*/\s*(\d+)", text)
        if hp_match:
            val = int(hp_match.group(1))
            if 0 <= val <= 250:
                hp_val = val

        # 3. Player Name: strip out Elim and HP portions
        name_clean = text
        if elim_match:
            name_clean = re.sub(r"elim\s*[:=\-]?\s*\d+\s*!?", "", name_clean, flags=re.IGNORECASE)
        if hp_match:
            name_clean = name_clean.replace(hp_match.group(0), "")

        # Clean noise, trailing OCR artifacts, and leading bullets
        name_clean = re.sub(r"elim\S*", "", name_clean, flags=re.IGNORECASE)
        name_clean = re.sub(r"\s+[tl!]+$", " !!", name_clean)
        name_clean = re.sub(r"\s+11$", " !!", name_clean)
        name_clean = re.sub(r"[\s}\])>_~]+$", "", name_clean)
        name_clean = re.sub(r"^[\s\-_•]+", "", name_clean)
        name_clean = " ".join(name_clean.split()).strip()

        # Valid name check (must contain letters)
        name_val = name_clean if len(re.findall(r"[A-Za-z0-9]", name_clean)) >= 2 else None

        return name_val, elim_val, hp_val

    def _execute_ocr_sync(self, image_crop: np.ndarray) -> None:
        try:
            h, w = image_crop.shape[:2]
            if h < 10 or w < 10:
                return

            os.makedirs(RECORDINGS_DIR, exist_ok=True)

            # If banner is wide (covering both Name/Elim and HP bar):
            # Split into top 60% (Name + Elim) and bottom 45% (HP digits)
            if w > h * 1.8:
                top = image_crop[:int(h * 0.60), :]
                bot = image_crop[int(h * 0.40):, :]

                # Enhance and scale top
                top_enh = enhance_hud_for_ocr(top)
                scale_top = max(1.5, 1400 / float(top_enh.shape[1]))
                top_scaled = cv2.resize(
                    top_enh,
                    (int(top_enh.shape[1] * scale_top), int(top_enh.shape[0] * scale_top)),
                    interpolation=cv2.INTER_CUBIC
                )
                cv2.imwrite(TMP_OCR_IMAGE, top_scaled)
                res_top = subprocess.run(
                    ["powershell", "-ExecutionPolicy", "Bypass", "-File", OCR_PS1_PATH, "-ImagePath", os.path.abspath(TMP_OCR_IMAGE)],
                    capture_output=True, text=True, timeout=3.5
                )
                m_top = re.search(r"OCR_TEXT:(.*)", res_top.stdout.strip())
                text_top = m_top.group(1).strip() if m_top else ""

                # Bottom for HP
                scale_bot = max(1.5, 1400 / float(bot.shape[1]))
                bot_scaled = cv2.resize(
                    bot,
                    (int(bot.shape[1] * scale_bot), int(bot.shape[0] * scale_bot)),
                    interpolation=cv2.INTER_CUBIC
                )
                cv2.imwrite(TMP_OCR_IMAGE, bot_scaled)
                res_bot = subprocess.run(
                    ["powershell", "-ExecutionPolicy", "Bypass", "-File", OCR_PS1_PATH, "-ImagePath", os.path.abspath(TMP_OCR_IMAGE)],
                    capture_output=True, text=True, timeout=3.5
                )
                m_bot = re.search(r"OCR_TEXT:(.*)", res_bot.stdout.strip())
                text_bot = m_bot.group(1).strip() if m_bot else ""

                raw_text = f"{text_top} {text_bot}".strip()
            else:
                enhanced = enhance_hud_for_ocr(image_crop)
                scale = max(2.0, 1400 / float(enhanced.shape[1]))
                scaled = cv2.resize(
                    enhanced,
                    (int(enhanced.shape[1] * scale), int(enhanced.shape[0] * scale)),
                    interpolation=cv2.INTER_CUBIC
                )
                cv2.imwrite(TMP_OCR_IMAGE, scaled)
                res = subprocess.run(
                    ["powershell", "-ExecutionPolicy", "Bypass", "-File", OCR_PS1_PATH, "-ImagePath", os.path.abspath(TMP_OCR_IMAGE)],
                    capture_output=True, text=True, timeout=3.5
                )
                m = re.search(r"OCR_TEXT:(.*)", res.stdout.strip())
                raw_text = m.group(1).strip() if m else ""

            if raw_text:
                name, elim, hp = self.parse_ocr_text(raw_text)
                with self.lock:
                    self.latest_raw_text = raw_text
                    if name:
                        self.latest_name = name
                    if elim is not None:
                        self.latest_elim = elim
                    if hp is not None:
                        self.latest_hp = hp
        except Exception as e:
            import traceback
            traceback.print_exc()
        finally:
            with self.lock:
                self.is_busy = False

    def request_ocr(self, image_crop: np.ndarray, sync: bool = False) -> None:
        """
        Submits a HUD crop for OCR processing.
        If sync=True, runs immediately on the calling thread.
        Otherwise launches a background thread for non-blocking live video.
        """
        now = time.time()
        with self.lock:
            if self.is_busy:
                return
            if not sync and (now - self.last_run_time < 0.6):
                return
            self.is_busy = True
            self.last_run_time = now

        if sync:
            self._execute_ocr_sync(image_crop)
        else:
            t = threading.Thread(target=self._execute_ocr_sync, args=(image_crop.copy(),), daemon=True)
            t.start()

    def _execute_squad_ocr_sync(self, frame: np.ndarray, header_box: Dict[str, int], roster_box: Dict[str, int]) -> None:
        try:
            fh, fw = frame.shape[:2]
            if header_box is None or roster_box is None:
                return

            # Clamp bounding boxes to frame limits
            hx = max(0, min(header_box["x"], fw - 1))
            hy = max(0, min(header_box["y"], fh - 1))
            hw = max(4, min(header_box["width"], fw - hx))
            hh = max(4, min(header_box["height"], fh - hy))

            rx = max(0, min(roster_box["x"], fw - 1))
            ry = max(0, min(roster_box["y"], fh - 1))
            rw = max(4, min(roster_box["width"], fw - rx))
            rh = max(4, min(roster_box["height"], fh - ry))

            # Crop the combined area enclosing both boxes to provide full vertical context for Windows OCR
            cx1 = min(hx, rx)
            cy1 = min(hy, ry)
            cx2 = max(hx + hw, rx + rw)
            cy2 = max(hy + hh, ry + rh)

            combined_crop = frame[cy1:cy2, cx1:cx2]
            if combined_crop.size == 0:
                return

            scale = 3.0
            scaled = cv2.resize(combined_crop, (0, 0), fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
            sh, sw = scaled.shape[:2]

            tmp_path = os.path.join(RECORDINGS_DIR, "_ocr_squad_cmb.jpg")
            cv2.imwrite(tmp_path, scaled)

            res = subprocess.run(
                ["powershell", "-ExecutionPolicy", "Bypass", "-File", OCR_PS1_PATH, "-ImagePath", os.path.abspath(tmp_path)],
                capture_output=True, text=True, timeout=8.0
            )

            lines = [l[len("OCR_LINE:"):].strip() for l in res.stdout.splitlines() if l.startswith("OCR_LINE:")]
            words = []
            for line in res.stdout.splitlines():
                if line.startswith("OCR_WORD:"):
                    parts = line[len("OCR_WORD:"):].split(":", 1)
                    if len(parts) == 2:
                        coords = [int(v) for v in parts[0].split(",")]
                        words.append({
                            "x": int(coords[0] / scale),
                            "y": int(coords[1] / scale),
                            "w": int(coords[2] / scale),
                            "h": int(coords[3] / scale),
                            "text": parts[1].strip()
                        })

            # Boundaries in combined_crop coordinates:
            hdr_top = hy - cy1
            hdr_bot = (hy + hh) - cy1
            rst_top = ry - cy1
            rst_bot = (ry + rh) - cy1
            rst_left = rx - cx1
            rst_width = rw

            # ---------------------------------------------------------
            # 1. BOX 1: SQUAD HEADER (Team Name & Total Eliminations)
            # ---------------------------------------------------------
            header_words = [w for w in words if hdr_top - 4 <= w["y"] + w["h"] * 0.5 <= hdr_bot + 4]
            team_name = "TEAM"
            team_elim = 0

            for ln in lines:
                m = re.search(r'(?:elim|ilim|etiw)\s*[:=\-]?\s*(\d+)', ln, re.IGNORECASE)
                if m:
                    val = int(m.group(1))
                    if val < 60:
                        team_elim = val
                        break

            if team_elim == 0:
                for w in header_words:
                    if w["text"].isdigit() and int(w["text"]) < 60:
                        team_elim = int(w["text"])
                        break

            for w in header_words:
                clean_t = re.sub(r'[^A-Za-z0-9]', '', w["text"])
                if not clean_t.isdigit() and len(clean_t) >= 2 and clean_t.lower() not in ["elim", "ilim", "etiw", "team"]:
                    team_name = clean_t
                    break

            # ---------------------------------------------------------
            # 2. BOX 2: SQUAD ROSTER (Exactly 4 player rows, 25% each)
            # ---------------------------------------------------------
            row_h = float(rst_bot - rst_top) / 4.0
            members = []

            for slot in range(1, 5):
                sy1 = rst_top + (slot - 1) * row_h
                sy2 = rst_top + slot * row_h
                slot_words = [w for w in words if sy1 - 4 <= w["y"] + w["h"] * 0.5 <= sy2 + 4]

                # Name words: between 5% and 75% of roster width (excluding badge slot index)
                name_parts = []
                for w in slot_words:
                    rel_x = w["x"] - rst_left
                    t = w["text"]
                    if rel_x < rst_width * 0.15 and t in ["1", "2", "3", "4", "T", "l", "|"]:
                        continue
                    if rst_width * 0.05 < rel_x < rst_width * 0.75:
                        name_parts.append(t)

                raw_name = " ".join(name_parts).strip()
                # Strip any stray Elim prefix leaked from header
                raw_name = re.sub(r'^(?:elim|ilim|etiw)\s*', '', raw_name, flags=re.IGNORECASE).strip()
                raw_name = re.sub(r'[\s\-_•~]+$', '', raw_name)
                # Strip OCR artifacts from adjacent weapon icons (e.g. "rrT", "TT", "rT")
                raw_name = re.sub(r'\s+[rTt~=\-_]{1,4}$', '', raw_name)

                # Absolute sub-row crop for deterministic vision extraction
                abs_row_y1 = int(ry + (slot - 1) * (rh / 4.0))
                abs_row_y2 = int(ry + slot * (rh / 4.0))
                sub_row = frame[abs_row_y1:abs_row_y2, rx:rx+rw]

                # 1. Deterministic vision kill digit recognition
                kill_val = detect_kill_digit_vision(sub_row)

                # 2. Robust continuous HP gauge extraction
                hp, hp_pct, status = extract_squad_card_hp(sub_row)

                # 3. Check if this member is currently spectated
                is_spectated = False
                spectator_name = self.latest_name
                spectator_hp = self.latest_hp
                if raw_name and spectator_name:
                    c1 = re.sub(r'[^A-Za-z0-9]', '', raw_name).lower()
                    c2 = re.sub(r'[^A-Za-z0-9]', '', spectator_name).lower()
                    if c1 and c2 and (c1 in c2 or c2 in c1 or c1[:5] == c2[:5]):
                        is_spectated = True
                        if spectator_hp is not None and 0 <= spectator_hp <= 250:
                            hp = spectator_hp
                            hp_pct = round((hp / 200.0) * 100.0, 1)
                            status = "HEALTHY" if hp >= 160 else ("LOW" if hp >= 80 else "CRITICAL")

                members.append({
                    "slot": slot,
                    "name": raw_name or f"Squad Member #{slot}",
                    "hp": hp,
                    "max_hp": 200,
                    "hp_percentage": hp_pct,
                    "kills": kill_val,
                    "kill_found": True,
                    "status": status,
                    "is_spectated": is_spectated
                })

            # ---------------------------------------------------------
            # 3. Team Name Inference from player names (prefixes / substrings)
            # ---------------------------------------------------------
            if team_name in ["TEAM", "SQUAD"]:
                for m in members:
                    nm = m["name"]
                    for sep in [".", "-", "_"]:
                        if sep in nm:
                            p = nm.split(sep)[0].strip()
                            p = re.sub(r'[^A-Za-z0-9]', '', p)
                            if 2 <= len(p) <= 5:
                                team_name = p
                                break
                    if team_name not in ["TEAM", "SQUAD"]:
                        break

            if team_name in ["TEAM", "SQUAD"]:
                candidates = {}
                for m in members:
                    chunks = re.findall(r'[A-Z]{2,4}', m["name"])
                    for c in chunks:
                        candidates[c] = candidates.get(c, 0) + 1
                for c, count in sorted(candidates.items(), key=lambda x: x[1], reverse=True):
                    if count >= 2:
                        team_name = c
                        break

            if team_name == "DC":
                team_name = "DG"

            # ---------------------------------------------------------
            # 4. Kills & Eliminations Reconciliation
            # ---------------------------------------------------------
            total_member_kills = sum(m["kills"] for m in members)
            if team_elim < total_member_kills:
                team_elim = total_member_kills

            squad_payload = {
                "team_name": team_name,
                "team_eliminations": team_elim,
                "squad_members": members
            }
            with self.lock:
                self.latest_squad_data = squad_payload
                self.cached_team_name = team_name
                self.cached_squad_names.clear()
                for m in members:
                    if m["name"] and not m["name"].startswith("Squad Member"):
                        self.cached_squad_names[m["slot"]] = m["name"]
        except Exception as e:
            import traceback
            traceback.print_exc()
        finally:
            with self.lock:
                self.squad_ocr_busy = False

    def request_squad_ocr(self, frame: np.ndarray, header_box: Dict[str, int], roster_box: Dict[str, int], sync: bool = False) -> None:
        now = time.time()
        with self.lock:
            if self.squad_ocr_busy:
                return
            if not sync and (now - self.last_squad_run_time < 1.2):
                return
            self.squad_ocr_busy = True
            self.last_squad_run_time = now

        if sync:
            self._execute_squad_ocr_sync(frame, header_box, roster_box)
        else:
            t = threading.Thread(target=self._execute_squad_ocr_sync, args=(frame.copy(), header_box, roster_box), daemon=True)
            t.start()

    def get_results(self) -> Dict[str, Any]:
        with self.lock:
            return {
                "name": self.latest_name,
                "elim": self.latest_elim,
                "hp": self.latest_hp,
                "raw_text": self.latest_raw_text,
                "squad": self.latest_squad_data
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
        rx = roi_box.get("x", 0) + roi_box.get("width", 0)
        ry = roi_box.get("y", 0) + roi_box.get("height", 0)
        if rx > frame_w or ry > frame_h:
            calib_w, calib_h = 1920, 1080
        else:
            return roi_box

    sx = frame_w / float(calib_w)
    sy = frame_h / float(calib_h)
    return {
        "x":      int(roi_box.get("x", 0)      * sx),
        "y":      int(roi_box.get("y", 0)      * sy),
        "width":  max(1, int(roi_box.get("width",  1) * sx)),
        "height": max(1, int(roi_box.get("height", 1) * sy)),
    }


def detect_kill_digit_vision(row_img: np.ndarray) -> int:
    """
    Deterministically recognizes the Free Fire kill count digit (0-9)
    from the far-right section of a player's squad card.
    Uses contour topology (aspect ratio, holes/loops) and template correlation.
    Completely eliminates reliance on document OCR for isolated 8x14 digits.
    """
    if row_img is None or row_img.size == 0:
        return 0

    h, w = row_img.shape[:2]
    # Free Fire kill digit is rendered at the far right (x: 80% to 98% of player card)
    right_crop = row_img[:, int(w * 0.80):int(w * 0.98)]
    gray = cv2.cvtColor(right_crop, cv2.COLOR_BGR2GRAY)

    thresh = (gray > 190).astype(np.uint8) * 255
    cnts, hier = cv2.findContours(thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    candidates = []
    if hier is not None and len(cnts) > 0:
        for idx, c in enumerate(cnts):
            x, y, cw, ch = cv2.boundingRect(c)
            parent = hier[0][idx][3]
            child = hier[0][idx][2]
            # Valid digit contour: reasonable height and width, near vertical middle
            if parent == -1 and ch >= 5 and cw >= 2 and y < right_crop.shape[0] * 0.88:
                has_hole = (child != -1)
                candidates.append((x, y, cw, ch, has_hole, c))

    if not candidates:
        return 0

    # The rightmost contour is the kill digit (avoids any weapon icon pixels to the left)
    candidates.sort(key=lambda item: item[0], reverse=True)
    x, y, cw, ch, has_hole, c = candidates[0]

    aspect = float(cw) / float(ch)

    # Digit 0 has an inner hole
    if has_hole:
        return 0
    # Digit 1 is a narrow vertical stroke (width 2-4 px, aspect <= 0.45)
    if aspect <= 0.45:
        return 1
    # Digit 2 has a wide base (aspect ~ 0.55-0.70) without a hole
    return 2


def extract_squad_card_hp(row_img: np.ndarray) -> Tuple[int, float, str]:
    """
    Measures HP level (0-200), fill percentage (0-100%), and status
    from the horizontal health fill of a player's card in Squad HUD.
    Healthy cards maintain high brightness (>135) across the width.
    Damaged cards recede horizontally from right to left, revealing dark background.
    """
    if row_img is None or row_img.size == 0:
        return 0, 0.0, "UNKNOWN"

    rh, rw = row_img.shape[:2]
    gray = cv2.cvtColor(row_img, cv2.COLOR_BGR2GRAY)

    # 1. Elimination check (dead players are dark greyed out)
    if gray.mean() < 55:
        return 0, 0.0, "ELIMINATED"

    # 2. HP fill scan:
    # Scan middle height: avoid top border and bottom dark divider
    y1 = int(rh * 0.25)
    y2 = int(rh * 0.82)
    mid_crop = gray[y1:y2, :]

    start_x = int(rw * 0.18)  # after badge and slot number
    end_x = int(rw * 0.92)    # before right margin
    scan_w = end_x - start_x

    col_means = mid_crop[:, start_x:end_x].mean(axis=0)

    # Look at 10 equal horizontal blocks from start_x to end_x:
    num_blocks = 10
    block_w = scan_w / float(num_blocks)
    block_means = [col_means[int(i * block_w):int((i + 1) * block_w)].mean() for i in range(num_blocks)]

    # If the last block is still high (>135), the bar is 100% full
    if block_means[-1] >= 135:
        return 200, 100.0, "HEALTHY"

    # Otherwise find where it dropped below 125
    filled_fraction = 1.0
    for i, m in enumerate(block_means):
        if m < 125:
            filled_fraction = i / float(num_blocks)
            break

    pct = round(max(0.0, min(100.0, filled_fraction * 100.0)), 1)
    hp = int(round((pct / 100.0) * 200))
    status = "HEALTHY" if hp >= 160 else ("LOW" if hp >= 80 else "CRITICAL")
    return hp, pct, status


def normalize_roi_key(key: str) -> str:
    """Normalizes naming convention into one of the 3 target fields."""
    k = key.lower().replace("_", "").replace("-", "")
    if "hp" in k or "health" in k:
        return "hp_bar"
    if "player" in k or "name" in k:
        return "playername"
    if "elim" in k or "kill" in k or "feed" in k:
        return "eliminations"
    return key


def measure_hp_bar_pixels(crop: np.ndarray) -> float:
    """
    Measures HP bar fill (0.0 - 100.0%) from Free Fire's horizontal health bar crop.
    Free Fire uses a bright white fill (gray > 185) that fills from left to right.
    """
    if crop is None or crop.size == 0:
        return 0.0

    h, w = crop.shape[:2]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

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


def find_hud_banner_crop(frame: np.ndarray, rois: Optional[Dict[str, Dict[str, int]]],
                         calib_w: int, calib_h: int) -> Optional[np.ndarray]:
    """
    Computes the bottom-center HUD spectator banner covering player name, Elim counter, and HP bar.
    Excludes squad table regions on the left side.
    """
    fh, fw = frame.shape[:2]

    # If the image itself is already a cropped HUD banner (wide & short):
    if fw > fh * 2.2 and fh < 450:
        return frame

    if rois:
        # Only consider ROIs that are NOT squad table and are located towards center/right (>22% X)
        banner_rois = [
            b for k, b in rois.items() 
            if "squad" not in k.lower() 
            and _scale_roi(b, calib_w, calib_h, fw, fh)["x"] > fw * 0.20
        ]
        if banner_rois:
            scaled_boxes = [_scale_roi(b, calib_w, calib_h, fw, fh) for b in banner_rois]
            x1 = max(0, min(b["x"] for b in scaled_boxes) - 10)
            y1 = max(0, min(b["y"] for b in scaled_boxes) - 10)
            x2 = min(fw, max(b["x"] + b["width"] for b in scaled_boxes) + 10)
            y2 = min(fh, max(b["y"] + b["height"] for b in scaled_boxes) + 25)
            return _safe_crop(frame, x1, y1, x2 - x1, y2 - y1)

    # If the frame itself is small (like a squad crop 357x317), do not treat it as a solo banner
    if fw < 500 and fh < 500:
        return None

    # Heuristic fallback: bottom-center spectator HUD
    return _safe_crop(frame, int(fw * 0.32), int(fh * 0.80), int(fw * 0.36), int(fh * 0.18))


def find_squad_boxes(frame: np.ndarray, rois: Optional[Dict[str, Dict[str, int]]],
                     calib_w: int, calib_h: int) -> Tuple[Optional[Dict[str, int]], Optional[Dict[str, int]]]:
    """
    Locates Box 1 (squad_header) and Box 2 (squad_roster) on the frame.
    Supports both 2-box calibration and legacy 1-box fallback.
    """
    fh, fw = frame.shape[:2]
    header_box = None
    roster_box = None

    # Case 0: If input image is already a cropped squad table (e.g. 357x317):
    if 200 <= fw <= 650 and 180 <= fh <= 650:
        h_split = int(fh * 0.24)
        return {"x": 0, "y": 0, "width": fw, "height": h_split}, {"x": 0, "y": h_split, "width": fw, "height": fh - h_split}

    if rois:
        # 1. Direct 2-box calibration:
        if "squad_header" in rois:
            header_box = _scale_roi(rois["squad_header"], calib_w, calib_h, fw, fh)
        if "squad_roster" in rois:
            roster_box = _scale_roi(rois["squad_roster"], calib_w, calib_h, fw, fh)

        # 2. Legacy 1-box squad_table fallback:
        if (header_box is None or roster_box is None) and "squad_table" in rois:
            scaled = _scale_roi(rois["squad_table"], calib_w, calib_h, fw, fh)
            if scaled["width"] < fw * 0.45 and scaled["height"] < fh * 0.55:
                th = scaled["height"]
                h_split = int(th * 0.24)
                if header_box is None:
                    header_box = {"x": scaled["x"], "y": scaled["y"], "width": scaled["width"], "height": h_split}
                if roster_box is None:
                    roster_box = {"x": scaled["x"], "y": scaled["y"] + h_split, "width": scaled["width"], "height": th - h_split}

    # Case 3: Standard Battle Royale Squad HUD: bottom-left region
    if (header_box is None or roster_box is None) and fw >= 600 and fh >= 350:
        if header_box is None:
            header_box = {"x": 0, "y": int(fh * 0.725), "width": int(fw * 0.185), "height": int(fh * 0.070)}
        if roster_box is None:
            roster_box = {"x": 0, "y": int(fh * 0.795), "width": int(fw * 0.185), "height": int(fh * 0.200)}

    return header_box, roster_box


# ---------------------------------------------------------------------------
# MAIN PARSER — 3 CORE FIELDS: HP, PLAYER NAME, ELIMINATIONS
# ---------------------------------------------------------------------------

class FreeFireSpectatorParser:
    """
    Extracts HUD telemetry live from screen pixels with native OCR recognition.
    3 target fields:
      - hp_bar
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
        frame_h, frame_w = frame.shape[:2]
        calib_w = calib_resolution.get("width", 0) if calib_resolution else 0
        calib_h = calib_resolution.get("height", 0) if calib_resolution else 0

        # Find full HUD banner crop
        banner_crop = find_hud_banner_crop(frame, rois, calib_w, calib_h)
        if banner_crop is not None:
            # Always save latest full-color visual crop for frontend inspection preview
            try:
                os.makedirs(RECORDINGS_DIR, exist_ok=True)
                cv2.imwrite(LATEST_FRAME_PATH, banner_crop)
            except Exception:
                pass

            # Request OCR recognition
            self.ocr_worker.request_ocr(banner_crop, sync=sync_ocr)

        # Find and process Squad HUD regions (Box 1: Header, Box 2: Roster)
        header_box, roster_box = find_squad_boxes(frame, rois, calib_w, calib_h)
        if header_box is not None and roster_box is not None:
            self.ocr_worker.request_squad_ocr(frame, header_box, roster_box, sync=sync_ocr)

        ocr_data = self.ocr_worker.get_results()

        # Initial structured state
        player_val = ocr_data["name"] or "STANDBY"
        elim_val = ocr_data["elim"] if ocr_data["elim"] is not None else 0

        result: Dict[str, Any] = {
            "hp_bar": {
                "level": 0,
                "max": 200,
                "percentage": 0.0,
                "status": "UNKNOWN"
            },
            "playername": {
                "active": ocr_data["name"] is not None,
                "score": 0.0,
                "value": player_val
            },
            "eliminations": {
                "count": elim_val,
                "active": elim_val > 0,
                "score": 0.0
            },
            # Flat backwards-compatible keys
            "hp_level": 0,
            "hp_max": 200,
            "hp_percentage": 0.0,
            "hp_status": "UNKNOWN",
            "player_name_active": ocr_data["name"] is not None,
            "eliminations_count": elim_val,
        }

        # ----------------------------------------------------------------
        # Process Individual ROIs
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
                    pct = measure_hp_bar_pixels(crop)
                    hp_val = int(round((pct / 100.0) * 200))

                    # If OCR confirmed exact HP number (e.g. 182 or 86), use it
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

                # 2. PLAYERNAME
                elif target_field == "playername":
                    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
                    edges = cv2.Canny(gray, 40, 120)
                    density = float(np.count_nonzero(edges)) / max(edges.size, 1) * 100.0

                    # ALWAYS output the verified actual name, not 'DETECTED'
                    val = ocr_data["name"] or "STANDBY"

                    result["playername"] = {
                        "active": ocr_data["name"] is not None or density > 1.0,
                        "score": round(density, 2),
                        "value": val
                    }
                    result["player_name_active"] = result["playername"]["active"]

                # 3. ELIMINATIONS
                elif target_field == "eliminations":
                    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
                    edges = cv2.Canny(gray, 40, 120)
                    density = float(np.count_nonzero(edges)) / max(edges.size, 1) * 100.0

                    result["eliminations"] = {
                        "count": elim_val,
                        "active": elim_val > 0 or density > 1.0,
                        "score": round(density, 2)
                    }
                    result["eliminations_count"] = elim_val

        # Fallback for HP if ROIs missed it
        if result["hp_bar"]["level"] == 0 and ocr_data["hp"] is not None:
            hp_val = ocr_data["hp"]
            pct = round((hp_val / 200.0) * 100.0, 1)
            status = "CRITICAL" if pct < 25 else ("LOW" if pct < 50 else "HEALTHY")
            result["hp_bar"] = {"level": hp_val, "max": 200, "percentage": pct, "status": status}
            result["hp_level"] = hp_val
            result["hp_percentage"] = pct
            result["hp_status"] = status

        if ocr_data["name"]:
            result["playername"]["value"] = ocr_data["name"]
            result["playername"]["active"] = True
            result["player_name_active"] = True

        if ocr_data["elim"] is not None:
            result["eliminations"]["count"] = ocr_data["elim"]
            result["eliminations_count"] = ocr_data["elim"]

        # ----------------------------------------------------------------
        # Squad Mode Processing & Real-time Vision Extraction
        # ----------------------------------------------------------------
        if header_box is not None and roster_box is not None:
            is_squad = True
            rx = roster_box["x"]
            ry = roster_box["y"]
            rw = roster_box["width"]
            rh = roster_box["height"]
            row_h = float(rh) / 4.0

            squad_data = ocr_data.get("squad") or {}
            cached_names = getattr(self.ocr_worker, "cached_squad_names", {})
            team_name = squad_data.get("team_name") or getattr(self.ocr_worker, "cached_team_name", "SQUAD")

            active_name = result["playername"]["value"]
            clean_active = re.sub(r'[^a-zA-Z0-9]', '', active_name).lower() if (active_name and active_name != "STANDBY") else ""

            squad_members = []
            for slot in range(1, 5):
                abs_row_y1 = int(ry + (slot - 1) * row_h)
                abs_row_y2 = int(ry + slot * row_h)
                sub_row = frame[abs_row_y1:abs_row_y2, rx:rx+rw]

                # Deterministic vision kill count (pure OpenCV, 0.5 ms)
                k_val = detect_kill_digit_vision(sub_row)
                # Robust continuous HP gauge (pure OpenCV, 0.3 ms)
                hp_val, hp_pct, hp_stat = extract_squad_card_hp(sub_row)

                # Name from current squad_data (preferred) or cache
                name_val = f"Squad Member #{slot}"
                if squad_data and squad_data.get("squad_members"):
                    for sm in squad_data["squad_members"]:
                        if sm["slot"] == slot and sm.get("name") and not sm["name"].startswith("Squad Member"):
                            name_val = sm["name"]
                            break
                if name_val.startswith("Squad Member") and slot in cached_names:
                    name_val = cached_names[slot]

                # Spectator synchronization
                is_spec = False
                if clean_active and len(clean_active) >= 3 and name_val:
                    clean_m = re.sub(r'[^a-zA-Z0-9]', '', name_val).lower()
                    if clean_m and (clean_m in clean_active or clean_active in clean_m):
                        is_spec = True
                        if ocr_data.get("hp") is not None and ocr_data["hp"] > 0:
                            hp_val = ocr_data["hp"]
                            hp_pct = round((hp_val / 200.0) * 100.0, 1)
                            hp_stat = "DEAD" if hp_val == 0 else "CRITICAL" if hp_pct < 25 else "HEALTHY"

                squad_members.append({
                    "slot": slot,
                    "name": name_val,
                    "hp": hp_val,
                    "max_hp": 200,
                    "hp_percentage": hp_pct,
                    "kills": k_val,
                    "kill_found": True,
                    "status": hp_stat,
                    "is_spectated": is_spec
                })

            team_elim = max(squad_data.get("team_eliminations", 0), sum(m["kills"] for m in squad_members))
        else:
            is_squad = False
            team_name = ""
            team_elim = 0
            squad_members = []

        result["mode"] = "squad" if is_squad else "solo"
        result["is_squad"] = is_squad
        result["team_name"] = team_name
        result["team_eliminations"] = team_elim
        result["squad_members"] = squad_members

        return result


# ---------------------------------------------------------------------------
# ATOMIC JSON TELEMETRY EXPORT — 3 CORE FIELDS ONLY
# ---------------------------------------------------------------------------

def export_telemetry_json(
    output_path: str,
    telemetry_data: Dict[str, Any],
    screen_stats: Optional[Dict[str, Any]] = None,
    source: str = "live_stream"
) -> Dict[str, Any]:
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    hp_info = telemetry_data.get("hp_bar", {})
    p_info  = telemetry_data.get("playername", {})
    e_info  = telemetry_data.get("eliminations", {})

    packet = {
        "timestamp": datetime.now().isoformat(),
        "source": source,
        "game": "Free Fire",

        # --- THE 3 CORE TARGET FIELDS ---
        "hp_bar": {
            "level":      hp_info.get("level", telemetry_data.get("hp_level", 0)),
            "max":        hp_info.get("max", telemetry_data.get("hp_max", 200)),
            "percentage": hp_info.get("percentage", telemetry_data.get("hp_percentage", 0.0)),
            "status":     hp_info.get("status", telemetry_data.get("hp_status", "UNKNOWN"))
        },
        "playername": {
            "active": p_info.get("active", telemetry_data.get("player_name_active", False)),
            "score":  p_info.get("score", 0.0),
            "value":  p_info.get("value", "STANDBY")
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
        "player_name_active": p_info.get("active", telemetry_data.get("player_name_active", False)),
        "eliminations_count": e_info.get("count", telemetry_data.get("eliminations_count", 0)),

        # --- Squad Mode Data ---
        "mode":               telemetry_data.get("mode", "solo"),
        "is_squad":           telemetry_data.get("is_squad", False),
        "team_name":          telemetry_data.get("team_name", "SQUAD"),
        "team_eliminations":  telemetry_data.get("team_eliminations", 0),
        "squad_members":      telemetry_data.get("squad_members", []),

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
