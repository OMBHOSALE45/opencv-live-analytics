"""
Static Screen HUD Telemetry Tester.
Processes Free Fire screenshots or live stream frames, extracts real in-game
metrics (Player Name, HP, Eliminations, Squad Roster), and exports clean JSON data.
"""

import os
import sys
import argparse
import time
import cv2
import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
CAPTURE_DIR = os.path.join(PROJECT_ROOT, "capture")
EVENTS_DIR = os.path.join(PROJECT_ROOT, "events")
RECORDINGS_DIR = os.path.join(PROJECT_ROOT, "recordings", "snapshots")
CONFIG_PATH = os.path.join(SCRIPT_DIR, "roi_config.json")
OUTPUT_JSON_PATH = os.path.join(EVENTS_DIR, "live_telemetry.json")

sys.path.insert(0, SCRIPT_DIR)
sys.path.insert(0, CAPTURE_DIR)

from telemetry_extractor import FreeFireSpectatorParser, export_telemetry_json
import live_capture as lc


def parse_args():
    parser = argparse.ArgumentParser(description="Test HUD telemetry on a static screen or image.")
    parser.add_argument(
        "--image", "-i",
        type=str,
        default=None,
        help="Path to screenshot image (e.g., screenshot.png). If omitted, defaults to uploaded screenshot."
    )
    parser.add_argument(
        "--no-window",
        action="store_true",
        help="Do not open OpenCV GUI window."
    )
    return parser.parse_args()


def main():
    args = parse_args()
    os.makedirs(EVENTS_DIR, exist_ok=True)
    os.makedirs(RECORDINGS_DIR, exist_ok=True)

    print("\n" + "=" * 68)
    print("      OPENCV FREE FIRE IN-GAME TELEMETRY EXTRACTOR")
    print("=" * 68)

    # 1. Acquire Image
    uploaded_default = os.path.join(RECORDINGS_DIR, "uploaded_test_screen.jpg")
    image_path = args.image or (uploaded_default if os.path.isfile(uploaded_default) else None)

    if image_path and os.path.isfile(image_path):
        print(f"[+] Processing image: {image_path}")
        frame = cv2.imread(image_path)
        source_name = os.path.basename(image_path)
    else:
        print("[*] No image file provided. Grabbing a static frame from your screen...")
        sct = lc.get_mss_instance()
        _, monitor = lc.select_monitor(sct)
        frame = lc.countdown_capture(sct, monitor, seconds=5)
        source_name = "screen_snapshot"

    h, w = frame.shape[:2]
    print(f"[+] Frame Resolution: {w}x{h}")

    # 2. Extract Real On-Screen Match Data (Computer Vision Analysis)
    print("[*] Running computer vision feature extraction...")
    cfg = lc.load_config()
    rois = cfg.get("rois", {}) if cfg else {}
    calib_res = cfg.get("monitor", {}) if cfg else {}

    parser = FreeFireSpectatorParser()
    data = parser.parse_frame(frame, rois, calib_resolution=calib_res, sync_ocr=True)

    # Global scene lighting & stats
    mean_b, mean_g, mean_r = cv2.mean(frame)[:3]
    screen_stats = {
        "width": w,
        "height": h,
        "mean_brightness": round((mean_b + mean_g + mean_r) / 3.0, 1),
        "mode": "static_screen_analysis"
    }

    # 3. Export Clean JSON
    packet = export_telemetry_json(
        output_path=OUTPUT_JSON_PATH,
        telemetry_data=data,
        screen_stats=screen_stats,
        source=source_name
    )

    hp_info = data.get("hp_bar", {})
    p_info = data.get("playername", {})
    e_info = data.get("eliminations", {})

    hp_lvl = hp_info.get("level", 0)
    hp_pct = hp_info.get("percentage", 0.0)
    hp_stat = hp_info.get("status", "UNKNOWN")

    p_val = p_info.get("value", "STANDBY")
    p_act = p_info.get("active", False)

    e_cnt = e_info.get("count", 0)
    e_act = e_info.get("active", False)

    # 4. Print Actual Game Data
    print("\n" + "+" + "-" * 62 + "+")
    print("|                  EXTRACTED FREE FIRE MATCH DATA              |")
    print("+" + "-" * 62 + "+")
    print(f"|  HP BAR:               {hp_lvl:3d} / 200 ({hp_pct:.0f}%) [{hp_stat:<12}] |")
    print(f"|  PLAYERNAME:           {p_val:<22} [{'ACTIVE' if p_act else 'IDLE':<8}] |")
    print(f"|  ELIMINATIONS:         {e_cnt:2d} Kills{' ' * 16} [{'ACTIVE' if e_act else 'IDLE':<8}] |")
    print("+" + "-" * 62 + "+")

    if data.get("is_squad"):
        team_name = data.get("team_name", "SQUAD")
        team_kills = data.get("team_eliminations", 0)
        print("\n" + "+" + "=" * 62 + "+")
        print(f"|      SQUAD MODE ROSTER — TEAM: {team_name:<10} (TEAM KILLS: {team_kills})     |")
        print("+" + "=" * 62 + "+")
        for m in data.get("squad_members", []):
            spec_tag = " [SPECTATING]" if m.get("is_spectated") else ""
            print(f"| Slot #{m['slot']}: {m['name']:<18} | HP: {m['hp']:3d}/200 ({m['hp_percentage']:.0f}%) | Kills: {m['kills']:2d}{spec_tag:<14} |")
        print("+" + "=" * 62 + "+")
    print(f"\n[+] Exported Clean JSON Data to: {OUTPUT_JSON_PATH}")

    # 5. Render HUD Overlay Badges with Actual Values
    annotated = frame.copy()

    p_badge = f"PLAYER: {p_val} | ELIM: {e_cnt}"
    cv2.rectangle(annotated, (int(w * 0.33), h - 90), (int(w * 0.67), h - 62), (30, 140, 255), -1)
    cv2.putText(annotated, p_badge, (int(w * 0.34), h - 70), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (10, 10, 10), 2, cv2.LINE_AA)

    hp_badge = f"HP: {hp_lvl}/200 ({hp_pct:.0f}%) [{hp_stat}]"
    hp_color = (60, 220, 60) if hp_lvl >= 100 else (40, 60, 240)
    cv2.rectangle(annotated, (int(w * 0.33), h - 55), (int(w * 0.60), h - 28), hp_color, -1)
    cv2.putText(annotated, hp_badge, (int(w * 0.34), h - 36), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2, cv2.LINE_AA)

    preview_path = os.path.join(RECORDINGS_DIR, "match_telemetry_annotated.jpg")
    cv2.imwrite(preview_path, annotated)
    print(f"[+] Saved visual preview to: {preview_path}")

    if not args.no_window:
        try:
            win_title = "Free Fire Live Telemetry - Press ANY KEY to close"
            cv2.namedWindow(win_title, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(win_title, min(1280, w), min(720, h))
            cv2.imshow(win_title, annotated)
            print("Press any key in the OpenCV window to exit...")
            cv2.waitKey(0)
            cv2.destroyAllWindows()
        except Exception:
            pass


if __name__ == "__main__":
    main()

