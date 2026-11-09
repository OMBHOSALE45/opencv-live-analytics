"""
OpenCV Live Screen Analytics & HUD Capture System for Free Fire / Battle Royale.
High-performance screen capture, real-time computer vision telemetry extraction,
and live JSON export (hp_level, ep_level, player_visible, kill_feed_active, etc.).
Optimized for single-laptop setups, multi-monitor setups, and browser streaming.
"""

import os
import sys
import time
import json
import argparse
from datetime import datetime
from typing import Dict, Any, Tuple, Optional

import cv2
import numpy as np
import mss

# ---------------------------------------------------------
# CONSTANTS & PROJECT PATH RESOLUTION
# ---------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
VISION_DIR = os.path.join(PROJECT_ROOT, "vision")
EVENTS_DIR = os.path.join(PROJECT_ROOT, "events")
CONFIG_PATH = os.path.join(VISION_DIR, "roi_config.json")
RECORDINGS_DIR = os.path.join(PROJECT_ROOT, "recordings", "snapshots")
TELEMETRY_JSON_PATH = os.path.join(EVENTS_DIR, "live_telemetry.json")

# Ensure vision package can be imported
if VISION_DIR not in sys.path:
    sys.path.insert(0, VISION_DIR)

from telemetry_extractor import FreeFireSpectatorParser, export_telemetry_json

WINDOW_NAME = "OpenCV Live Analytics - Free Fire Telemetry"

# Target HUD regions configured for analysis (HP, Name, Elim, and Squad Table)
DEFAULT_ROI_NAMES = [
    "hp_bar",
    "playername",
    "eliminations",
    "squad_table"
]

# Color schemes (BGR)
COLOR_PALETTE = {
    "hp_bar": (70, 220, 70),        # Green
    "playername": (255, 180, 50),   # Cyan / Light Blue
    "eliminations": (60, 60, 240),  # Red / Coral
    "squad_table": (255, 200, 40),  # Sky blue / Gold
    "health_bar": (70, 220, 70),
    "player_name": (255, 180, 50),
    "kill_feed": (60, 60, 240),
    "default": (0, 255, 0),         # Green
    "bg_dark": (18, 18, 18),        # Dark slate
    "text_white": (245, 245, 245),
    "accent_yellow": (0, 220, 255),
    "accent_green": (70, 230, 70),
    "accent_orange": (0, 140, 255),
}


# ---------------------------------------------------------
# MSS SCREEN RECORDER INITIALIZATION
# ---------------------------------------------------------
def get_mss_instance():
    """Returns an MSS instance without deprecation warnings across versions."""
    sct_class = getattr(mss, "MSS", None)
    if sct_class is not None and callable(sct_class):
        return sct_class()
    return mss.mss()


# ---------------------------------------------------------
# DISPLAY SELECTION & MONITOR MANAGEMENT
# ---------------------------------------------------------
def list_available_monitors(sct) -> list:
    """
    Parses attached screens and adds smart split-screen options
    specifically designed for single-laptop setups.
    """
    displays = []
    
    # 1. Standard hardware displays from MSS
    for idx, mon in enumerate(sct.monitors):
        is_all_virtual = (idx == 0)
        is_primary = mon.get("is_primary", False) or (not is_all_virtual and mon.get("left") == 0 and mon.get("top") == 0)
        name = mon.get("name") or ("All Displays (Virtual Desktop)" if is_all_virtual else f"Display {idx}")
        
        displays.append({
            "index": idx,
            "name": name,
            "width": mon["width"],
            "height": mon["height"],
            "left": mon.get("left", 0),
            "top": mon.get("top", 0),
            "is_primary": is_primary,
            "is_virtual": is_all_virtual,
            "raw": mon,
            "tag": "PRIMARY" if is_primary else ("ALL SCREENS" if is_all_virtual else "")
        })

    # 2. Add smart half-screen regions for single laptop users (Win + Left / Win + Right)
    if len(sct.monitors) >= 2:
        prim = sct.monitors[1]
        w, h = prim["width"], prim["height"]
        l, t = prim.get("left", 0), prim.get("top", 0)
        half_w = w // 2

        # Left Half (e.g. Brave snapped to Left)
        displays.append({
            "index": len(displays),
            "name": "Left Half Screen (Win + Left)",
            "width": half_w,
            "height": h,
            "left": l,
            "top": t,
            "is_primary": False,
            "is_virtual": False,
            "raw": {"left": l, "top": t, "width": half_w, "height": h},
            "tag": "BRAVE ON LEFT"
        })

        # Right Half
        displays.append({
            "index": len(displays),
            "name": "Right Half Screen (Win + Right)",
            "width": half_w,
            "height": h,
            "left": l + half_w,
            "top": t,
            "is_primary": False,
            "is_virtual": False,
            "raw": {"left": l + half_w, "top": t, "width": half_w, "height": h},
            "tag": "BRAVE ON RIGHT"
        })

    return displays


def select_monitor(sct) -> Tuple[int, Dict[str, Any]]:
    """
    Robust interactive screen selector with single-laptop guidance.
    """
    displays = list_available_monitors(sct)
    
    print("\n" + "=" * 70)
    print("           OPENCV LIVE ANALYTICS - SCREEN SELECTOR")
    print("=" * 70)
    print(f"{'ID':<4} {'Name / Description':<32} {'Resolution':<12} {'Tag'}")
    print("-" * 70)
    
    default_id = 1
    for d in displays:
        tag_str = f"[{d['tag']}]" if d["tag"] else ""
        res_str = f"{d['width']}x{d['height']}"
        print(f"[{d['index']}]  {d['name'][:30]:<32} {res_str:<12} {tag_str}")
    
    print("-" * 70)
    print("SINGLE LAPTOP TIP:")
    print(" * Option [1]: Captures your entire laptop screen.")
    print(" * Option [2]: Captures only the LEFT HALF (Snap Brave with Win + Left Arrow).")
    print("-" * 70)
    
    while True:
        try:
            prompt = f"Select screen ID [0 - {len(displays) - 1}] (Default: {default_id}): "
            user_input = input(prompt).strip()
            
            if user_input == "":
                chosen_idx = default_id
            else:
                chosen_idx = int(user_input)
                
            if 0 <= chosen_idx < len(displays):
                chosen = displays[chosen_idx]
                print(f"[+] Selected: [{chosen['index']}] {chosen['name']} ({chosen['width']}x{chosen['height']})\n")
                return chosen["index"], chosen["raw"]
            else:
                print(f"[-] Invalid ID {chosen_idx}. Please select between 0 and {len(displays) - 1}.")
        except ValueError:
            print("[-] Please enter a valid number (or press ENTER for default).")
        except (KeyboardInterrupt, EOFError):
            print("\nExiting screen selection.")
            sys.exit(0)


# ---------------------------------------------------------
# HIGH-SPEED SCREEN CAPTURE & COUNTDOWN HELPER
# ---------------------------------------------------------
def capture_frame(sct, monitor_dict: Dict[str, Any]) -> np.ndarray:
    """
    High-speed frame grab using MSS raw buffer and fast BGRA -> BGR conversion.
    """
    screenshot = sct.grab(monitor_dict)
    raw_buffer = np.frombuffer(screenshot.raw, dtype=np.uint8)
    bgra = raw_buffer.reshape((screenshot.height, screenshot.width, 4))
    return cv2.cvtColor(bgra, cv2.COLOR_BGRA2BGR)


def countdown_capture(sct, monitor_dict: Dict[str, Any], seconds: int = 5) -> np.ndarray:
    """
    Gives a countdown so a single-laptop user can Alt+Tab to their
    Brave YouTube stream BEFORE the frame is captured.
    """
    print("\n" + "=" * 60)
    print(" [!] PREPARING SCREEN CAPTURE FOR CALIBRATION")
    print(f" --> Press [Alt + Tab] and switch to BRAVE (YouTube) NOW!")
    print(f" --> Make sure the YouTube video is visible on screen.")
    print("=" * 60)

    for sec in range(seconds, 0, -1):
        print(f"    Capturing screen in {sec}... (Switch to Brave now!)", flush=True)
        time.sleep(1.0)

    frame = capture_frame(sct, monitor_dict)
    print("    [+] SCREEN CAPTURED! Calibrating ROIs...\n")
    return frame


# ---------------------------------------------------------
# CONFIGURATION PERSISTENCE
# ---------------------------------------------------------
def load_config() -> Optional[Dict[str, Any]]:
    """Loads saved ROI configurations if present."""
    if os.path.isfile(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                config = json.load(f)
                if isinstance(config, dict) and "rois" in config:
                    return config
        except Exception as e:
            print(f"[!] Warning reading {CONFIG_PATH}: {e}")
    return None


def save_config(rois: Dict[str, Any], monitor_dict: Dict[str, Any]) -> None:
    """Saves configured ROIs to vision/roi_config.json."""
    os.makedirs(VISION_DIR, exist_ok=True)
    config = {
        "saved_at": datetime.now().isoformat(),
        "monitor": {
            "width": monitor_dict.get("width", 0),
            "height": monitor_dict.get("height", 0)
        },
        "rois": rois
    }
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)
    print(f"[+] Configuration saved successfully to: {CONFIG_PATH}")


# ---------------------------------------------------------
# INTERACTIVE HUD CALIBRATION
# ---------------------------------------------------------
def calibrate_rois(frame: np.ndarray, roi_names: list = None) -> Dict[str, Dict[str, int]]:
    """
    Interactive ROI selector using cv2.selectROI with safety bounds.
    Supports 1-box Squad Mode or Solo Spectator Mode.
    """
    frame_h, frame_w = frame.shape[:2]

    if roi_names is None:
        print("\n" + "=" * 60)
        print("          SELECT CALIBRATION TARGET MODE")
        print("=" * 60)
        print(" [1] SQUAD MODE (Recommended)")
        print("     -> Draw ONLY 1 SINGLE BOX around the bottom-left squad roster!")
        print("     -> Automatically extracts Team Name, Team Kills & all 4 Players")
        print(" [2] SOLO / SPECTATOR MODE")
        print("     -> Calibrate HP Bar, Player Name, and Eliminations (Center Banner)")
        print(" [3] CUSTOM / ALL REGIONS")
        print("=" * 60)

        try:
            mode_input = input("Enter mode [1 for Squad / 2 for Solo / 3 for All] (default=1): ").strip()
        except Exception:
            mode_input = "1"

        if mode_input == "2":
            roi_names = ["hp_bar", "playername", "eliminations"]
        elif mode_input == "3":
            roi_names = DEFAULT_ROI_NAMES
        else:
            # Squad mode: 2 distinct boxes as requested:
            # Box 1: squad_header (Team Name & Total Eliminations top banner)
            # Box 2: squad_roster (The 4 player cards ONLY)
            roi_names = ["squad_header", "squad_roster"]

    print("\n" + "=" * 55)
    print("           HUD REGION CALIBRATION")
    print("=" * 55)
    print("Instructions:")
    print(" - Drag with your mouse to draw the bounding box.")
    print(" - Press ENTER or SPACE to confirm.")
    print(" - Press ESC or 'c' to skip the current region.")
    print("-" * 55)

    rois = {}
    for name in roi_names:
        if name == "squad_header":
            prompt_hint = "BOX 1 - SQUAD HEADER: Drag box around Team Name & Total Kills (top banner)"
        elif name == "squad_roster":
            prompt_hint = "BOX 2 - SQUAD ROSTER: Drag box around ONLY the 4 player rows (1 to 4)"
        elif name == "squad_table":
            prompt_hint = "SQUAD TABLE: Drag box around entire squad roster"
        elif name == "hp_bar":
            prompt_hint = "HP BAR: Drag box around bottom-center health bar"
        elif name == "playername":
            prompt_hint = "PLAYER NAME: Drag box around spectator name banner"
        elif name == "eliminations":
            prompt_hint = "ELIMINATIONS: Drag box around spectator kill counter"
        else:
            prompt_hint = f"Region: {name}"

        win_title = f"{prompt_hint} (ESC to skip, ENTER to accept)"
        cv2.namedWindow(win_title, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(win_title, min(1280, frame_w), min(720, frame_h))

        roi = cv2.selectROI(win_title, frame, showCrosshair=True, fromCenter=False)
        cv2.destroyWindow(win_title)

        x, y, w, h = map(int, roi)
        if w > 4 and h > 4:
            x = max(0, min(x, frame_w - 1))
            y = max(0, min(y, frame_h - 1))
            w = max(4, min(w, frame_w - x))
            h = max(4, min(h, frame_h - y))
            rois[name] = {"x": x, "y": y, "width": w, "height": h}
            print(f" [+] Configured {name}: x={x}, y={y}, w={w}, h={h}")
        else:
            print(f" [-] Skipped {name}")

    return rois


# ---------------------------------------------------------
# REAL-TIME OPENCV SCREEN & ROI ANALYZER
# ---------------------------------------------------------
class ScreenAnalyzer:
    """Performs ultra-fast global telemetry on screen frames."""

    def __init__(self):
        self.prev_subsample: Optional[np.ndarray] = None
        self.prev_time = time.perf_counter()
        self.fps_smoothed = 0.0
        self.latency_ms = 0.0
        self.frame_count = 0
        self.alpha_fps = 0.15

    def analyze_global(self, frame: np.ndarray) -> Dict[str, Any]:
        now = time.perf_counter()
        delta = now - self.prev_time
        self.prev_time = now
        
        instant_fps = 1.0 / max(delta, 0.0001)
        if self.fps_smoothed == 0.0:
            self.fps_smoothed = instant_fps
        else:
            self.fps_smoothed = (self.alpha_fps * instant_fps) + ((1.0 - self.alpha_fps) * self.fps_smoothed)
            
        self.latency_ms = delta * 1000.0
        self.frame_count += 1

        h, w = frame.shape[:2]
        sample = frame[::8, ::8]
        sample_gray = sample[:, :, 0]

        mean_b, mean_g, mean_r = cv2.mean(sample)[:3]
        brightness = (mean_b + mean_g + mean_r) / 3.0

        if mean_r > mean_b + 15 and mean_r > mean_g:
            tone = "Warm"
        elif mean_b > mean_r + 15 and mean_b > mean_g:
            tone = "Cool"
        else:
            tone = "Neutral"

        motion_pct = 0.0
        if self.prev_subsample is not None and self.prev_subsample.shape == sample_gray.shape:
            diff = cv2.absdiff(sample_gray, self.prev_subsample)
            motion_pixels = np.count_nonzero(diff > 25)
            motion_pct = (motion_pixels / max(diff.size, 1)) * 100.0
            
        self.prev_subsample = sample_gray.copy()

        if motion_pct > 15.0:
            motion_status = "HIGH"
        elif motion_pct > 1.0:
            motion_status = "ACTIVE"
        else:
            motion_status = "STATIC"

        return {
            "fps": round(self.fps_smoothed, 1),
            "latency_ms": round(self.latency_ms, 1),
            "frame_w": w,
            "frame_h": h,
            "brightness": round(brightness, 1),
            "motion_pct": round(motion_pct, 1),
            "motion_status": motion_status,
            "tone": tone
        }


# ---------------------------------------------------------
# HUD OVERLAY & VISUAL TELEMETRY RENDERER
# ---------------------------------------------------------
class HUDOverlayRenderer:
    """Renders sleek, high-contrast analytics telemetry overlays on top of the live feed."""

    def __init__(self):
        self.hud_mode = 0  # 0: Full HUD, 1: Minimal HUD, 2: HUD Off
        self.hud_mode_names = ["FULL TELEMETRY", "MINIMAL", "OFF"]

    def toggle_mode(self) -> str:
        self.hud_mode = (self.hud_mode + 1) % 3
        return self.hud_mode_names[self.hud_mode]

    def render(
        self,
        frame: np.ndarray,
        global_stats: Dict[str, Any],
        telemetry_data: Dict[str, Any],
        rois: Dict[str, Dict[str, int]],
        monitor_idx: int
    ) -> np.ndarray:
        if self.hud_mode == 2:  # OFF
            return frame

        canvas = frame.copy()
        h, w = canvas.shape[:2]

        # 1. Draw ROIs with live telemetry badges (values read from actual pixels)
        for name, box in rois.items():
            x = max(0, min(int(box.get("x", 0)), w - 1))
            y = max(0, min(int(box.get("y", 0)), h - 1))
            rw = max(1, min(int(box.get("width", 0)), w - x))
            rh = max(1, min(int(box.get("height", 0)), h - y))

            clean_name = name.lower().replace("_", "").replace("-", "")
            color = COLOR_PALETTE.get(name, COLOR_PALETTE.get(clean_name, COLOR_PALETTE["default"]))
            

            # Get structured data with flat fallbacks
            hp_info = telemetry_data.get("hp_bar", {})
            p_info = telemetry_data.get("playername", {})
            e_info = telemetry_data.get("eliminations", {})

            if "hp" in clean_name or "health" in clean_name:
                lvl = hp_info.get("level", telemetry_data.get("hp_level", 0))
                pct = hp_info.get("percentage", telemetry_data.get("hp_percentage", 0.0))
                stat = hp_info.get("status", telemetry_data.get("hp_status", "UNKNOWN"))
                label_text = f"HP: {lvl}/200 ({pct:.0f}%) [{stat}]"
            elif "player" in clean_name or "name" in clean_name:
                val = p_info.get("value", "STANDBY")
                label_text = f"PLAYER: {val}"
            elif "elim" in clean_name or "kill" in clean_name or "feed" in clean_name:
                cnt = e_info.get("count", telemetry_data.get("eliminations_count", 0))
                e_act = e_info.get("active", False)
                label_text = f"ELIMINATIONS: {cnt} {'[ACTIVE]' if e_act else ''}"
            elif "squad" in clean_name:
                sq_cnt = len(telemetry_data.get("squad_members", []))
                team_name = telemetry_data.get("team_name", "SQUAD")
                team_kills = telemetry_data.get("team_eliminations", 0)
                label_text = f"SQUAD: {team_name} | KILLS: {team_kills} ({sq_cnt} PLAYERS)"
            else:
                label_text = name

            # Bounding box
            cv2.rectangle(canvas, (x, y), (x + rw, y + rh), color, 2)

            # Label badge
            (tw, th), _ = cv2.getTextSize(label_text, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
            badge_y1 = max(0, y - th - 8)
            badge_y2 = y
            badge_x1 = x
            badge_x2 = min(w, x + tw + 10)

            cv2.rectangle(canvas, (badge_x1, badge_y1), (badge_x2, badge_y2), color, -1)
            cv2.putText(
                canvas,
                label_text,
                (badge_x1 + 5, badge_y2 - 4),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (10, 10, 10),
                1,
                cv2.LINE_AA
            )

        # 2. Draw Top Telemetry Bar
        bar_h = 42 if self.hud_mode == 0 else 30
        header_slice = canvas[0:bar_h, 0:w]
        dark_bar = np.zeros_like(header_slice)
        cv2.addWeighted(dark_bar, 0.75, header_slice, 0.25, 0, header_slice)

        fps = global_stats["fps"]
        lat = global_stats["latency_ms"]
        fps_color = COLOR_PALETTE["accent_green"] if fps >= 25 else COLOR_PALETTE["accent_orange"]

        title_text = f"FEED #{monitor_idx} [{w}x{h}]"
        fps_text = f"FPS: {fps:.1f} ({lat:.1f}ms)"
        
        cv2.putText(canvas, title_text, (15, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, COLOR_PALETTE["text_white"], 1, cv2.LINE_AA)
        cv2.putText(canvas, fps_text, (240, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, fps_color, 2, cv2.LINE_AA)

        if self.hud_mode == 0:
            hp_info = telemetry_data.get("hp_bar", {})
            p_info = telemetry_data.get("playername", {})
            e_info = telemetry_data.get("eliminations", {})

            hp_num = hp_info.get("level", telemetry_data.get("hp_level", 0))
            hp_pct = hp_info.get("percentage", telemetry_data.get("hp_percentage", 0.0))
            p_val = p_info.get("value", "STANDBY")
            elim_num = e_info.get("count", telemetry_data.get("eliminations_count", 0))

            hp_str = f"HP: {hp_num}/200 ({hp_pct:.0f}%)"
            p_str = f"PLAYER: {p_val}"
            elim_str = f"ELIM: {elim_num}"

            cv2.putText(canvas, hp_str, (400, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, COLOR_PALETTE["accent_green"], 2, cv2.LINE_AA)
            cv2.putText(canvas, p_str, (620, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, COLOR_PALETTE["playername"], 2, cv2.LINE_AA)
            cv2.putText(canvas, elim_str, (880, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, COLOR_PALETTE["eliminations"], 2, cv2.LINE_AA)

            # Bottom status banner
            bot_h = 28
            bot_slice = canvas[h - bot_h:h, 0:w]
            bot_dark = np.zeros_like(bot_slice)
            cv2.addWeighted(bot_dark, 0.8, bot_slice, 0.2, 0, bot_slice)

            controls_text = "[Q] Quit  |  [R] Recalibrate ROIs  |  [T] Toggle HUD  |  [S] Save Snapshot  |  [C] Clear ROIs"
            cv2.putText(canvas, controls_text, (15, h - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1, cv2.LINE_AA)

        return canvas


# ---------------------------------------------------------
# MAIN REAL-TIME EXECUTION PIPELINE
# ---------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="OpenCV Free Fire Live Analytics")
    parser.add_argument("--image", "-i", type=str, default=None, help="Test static screenshot instead of live screen")
    parser.add_argument("--no-window", "--headless", action="store_true", help="Run in background without opening OpenCV preview window (ideal for fullscreen YouTube!)")
    args = parser.parse_args()

    print("\n" + "=" * 65)
    print("      OPENCV LIVE ANALYTICS & COMPUTER VISION ENGINE")
    print("=" * 65)

    sct = get_mss_instance()
    analyzer = ScreenAnalyzer()
    parser = FreeFireSpectatorParser()
    renderer = HUDOverlayRenderer()

    os.makedirs(EVENTS_DIR, exist_ok=True)
    os.makedirs(RECORDINGS_DIR, exist_ok=True)

    # 1. Screen / Image Selection
    is_static_image = False
    if args.image and os.path.isfile(args.image):
        print(f"[+] Running in Static Image Test Mode on: {args.image}")
        static_frame = cv2.imread(args.image)
        if static_frame is None:
            print(f"[-] Could not load image from {args.image}")
            return
        monitor_idx = 0
        monitor = {"width": static_frame.shape[1], "height": static_frame.shape[0]}
        is_static_image = True
    else:
        try:
            monitor_idx, monitor = select_monitor(sct)
        except Exception as e:
            print(f"[-] Monitor selection failed: {e}")
            return

    # 2. Configuration Management
    saved_config = load_config()
    rois = {}
    # calib_resolution: the monitor resolution at which ROIs were originally drawn.
    # Used to auto-scale ROIs to whatever frame size is being captured right now.
    calib_resolution = {"width": monitor.get("width", 0), "height": monitor.get("height", 0)}

    if saved_config and "rois" in saved_config:
        saved_rois = saved_config["rois"]
        # Load the saved calibration resolution (may differ from current capture monitor)
        if "monitor" in saved_config and saved_config["monitor"].get("width", 0) > 0:
            calib_resolution = saved_config["monitor"]
        print(f"[+] Loaded existing ROI configuration with {len(saved_rois)} region(s):")
        calib_w = calib_resolution.get("width", 0)
        calib_h = calib_resolution.get("height", 0)
        print(f"    (Calibrated at: {calib_w}x{calib_h} -> live frame: {monitor.get('width',0)}x{monitor.get('height',0)})")
        for r_name, r_box in saved_rois.items():
            print(f"    - {r_name}: {r_box['width']}x{r_box['height']} at ({r_box['x']}, {r_box['y']})")

        choice = input("\nUse saved ROIs? [Y/n] (or 'r' to recalibrate): ").strip().lower()
        if choice == "r":
            initial_frame = static_frame if is_static_image else countdown_capture(sct, monitor, seconds=5)
            rois = calibrate_rois(initial_frame)
            save_config(rois, monitor)
            calib_resolution = {"width": initial_frame.shape[1], "height": initial_frame.shape[0]}
        elif choice == "n":
            print("[*] Starting without saved ROIs. (Press 'R' during stream to calibrate).")
            rois = {}
        else:
            rois = saved_rois
    else:
        choice = input("\nNo saved ROI configuration found. Calibrate HUD regions now? [y/N]: ").strip().lower()
        if choice in ["y", "yes"]:
            initial_frame = static_frame if is_static_image else countdown_capture(sct, monitor, seconds=5)
            rois = calibrate_rois(initial_frame)
            save_config(rois, monitor)
            calib_resolution = {"width": initial_frame.shape[1], "height": initial_frame.shape[0]}
        else:
            print("[*] Starting with full screen analysis. Press 'R' anytime to calibrate ROIs.")

    # 3. Create Scalable Window (if not in headless mode)
    if not args.no_window:
        cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
        init_w = min(1280, monitor["width"])
        init_h = int(init_w * (monitor["height"] / max(monitor["width"], 1)))
        cv2.resizeWindow(WINDOW_NAME, init_w, init_h)

    print("\n" + "=" * 65)
    print("                    LIVE STREAM RUNNING")
    print("=" * 65)
    print(f"[+] Live telemetry JSON continuously exporting to: {TELEMETRY_JSON_PATH}")
    if args.no_window:
        print("[+] Headless mode enabled: Watching in fullscreen without popups! Press Ctrl+C to stop.")
    else:
        print("Controls:")
        print("  - Press 'Q' or ESC to exit cleanly")
        print("  - Press 'R' to recalibrate HUD regions")
        print("  - Press 'T' to toggle HUD telemetry modes")
        print("  - Press 'S' to save timestamped snapshot")
        print("  - Press 'C' to clear/reset all ROIs")
    print("=" * 65 + "\n")

    last_json_time = 0.0
    last_print_time = 0.0

    try:
        while True:
            # Capture frame
            if is_static_image:
                frame = static_frame.copy()
            else:
                frame = capture_frame(sct, monitor)

            if frame is None or frame.size == 0:
                time.sleep(0.01)
                continue

            # Run global screen analytics (FPS, motion, lighting)
            global_metrics = analyzer.analyze_global(frame)

            # Extract actual on-screen match telemetries (player_name, hp_level, events, alive)
            # calib_resolution enables auto-scaling of ROIs to the current frame size
            telemetry_data = parser.parse_frame(frame, rois, calib_resolution=calib_resolution, sync_ocr=is_static_image)

            # Export clean JSON telemetry throttled to ~10 Hz (every 100ms)
            now = time.time()
            if now - last_json_time >= 0.10:
                try:
                    export_telemetry_json(
                        output_path=TELEMETRY_JSON_PATH,
                        telemetry_data=telemetry_data,
                        screen_stats=global_metrics,
                        source="static_image" if is_static_image else f"screen_{monitor_idx}"
                    )
                except Exception:
                    pass  # Never let file lock contention disrupt the video stream
                last_json_time = now

            # If headless mode, print formatted match telemetry directly in terminal
            if args.no_window:
                if now - last_print_time >= 0.4:
                    hp_info = telemetry_data.get("hp_bar", {})
                    p_info  = telemetry_data.get("playername", {})
                    e_info  = telemetry_data.get("eliminations", {})

                    hp     = hp_info.get("level", telemetry_data.get("hp_level", 0))
                    hp_pct = hp_info.get("percentage", telemetry_data.get("hp_percentage", 0.0))
                    p_val  = p_info.get("value", "STANDBY")
                    elim   = e_info.get("count", telemetry_data.get("eliminations_count", 0))

                    if telemetry_data.get("is_squad"):
                        t_name = telemetry_data.get("team_name", "SQUAD")
                        t_elim = telemetry_data.get("team_eliminations", 0)
                        s_cnt = len(telemetry_data.get("squad_members", []))
                        print(
                            f"\r[SQUAD] {t_name} (TeamKills:{t_elim}) | Active:{p_val:<14} HP:{hp:3d}/200 | {s_cnt} Squad Members Active",
                            end="", flush=True
                        )
                    else:
                        print(
                            f"\r[LIVE] HP:{hp:3d}/200({hp_pct:.0f}%) | "
                            f"Player:{p_val:<16} | Elim:{elim:2d}",
                            end="", flush=True
                        )
                    last_print_time = now
                time.sleep(0.01)
                continue

            # Render visual HUD overlay
            display = renderer.render(frame, global_metrics, telemetry_data, rois, monitor_idx)

            # Display output
            cv2.imshow(WINDOW_NAME, display)

            # Check if user closed window with 'X'
            if cv2.getWindowProperty(WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
                print("\n[*] Window closed by user.")
                break

            # Handle interactive keys
            key = cv2.waitKey(1) & 0xFF

            if key in [ord("q"), ord("Q"), 27]:  # 'q' or ESC
                print("\n[*] Exit key pressed. Shutting down cleanly...")
                break

            elif key in [ord("r"), ord("R")]:
                print("\n[*] Recalibration requested...")
                new_frame = countdown_capture(sct, monitor, seconds=5)
                new_rois = calibrate_rois(new_frame)
                if new_rois:
                    rois.update(new_rois)
                    # Update calibration resolution to match the recalibration frame
                    calib_resolution = {"width": new_frame.shape[1], "height": new_frame.shape[0]}
                    save_config(rois, monitor)
                print("[*] Resuming live capture...")

            elif key in [ord("t"), ord("T")]:
                mode_name = renderer.toggle_mode()
                print(f"\n[*] HUD Mode switched to: {mode_name}")

            elif key in [ord("s"), ord("S")]:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                snap_path = os.path.join(RECORDINGS_DIR, f"snapshot_{timestamp}.jpg")
                cv2.imwrite(snap_path, display)
                print(f"\n[+] Saved snapshot: {snap_path}")

            elif key in [ord("c"), ord("C")]:
                rois = {}
                print("\n[*] Cleared active ROIs from memory.")

    except KeyboardInterrupt:
        print("\n\n[*] Interrupted via keyboard (Ctrl+C). Exiting...")
    except Exception as e:
        print(f"\n[!] Unexpected error in main capture loop: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("[*] Cleaning up OpenCV windows and resources...")
        cv2.destroyAllWindows()
        print("[+] Done. Exited cleanly.")


if __name__ == "__main__":
    main()
