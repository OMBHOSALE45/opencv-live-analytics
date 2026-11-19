import os, sys
import cv2, json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from vision.telemetry_extractor import FreeFireSpectatorParser, export_telemetry_json

parser = FreeFireSpectatorParser()

print("==================================================")
print("TESTING 2-SELECTION PIPELINE ON TEAM KARAN (1024x465)")
print("==================================================")

img = cv2.imread('recordings/snapshots/karan_game_frame.jpg')

rois = {
    "player_names": {
        "x": 737,
        "y": 193,
        "width": 158,
        "height": 124
    },
    "player_kills": {
        "x": 930,
        "y": 193,
        "width": 25,
        "height": 124
    }
}

calib_res = {"width": 1024, "height": 465}

res = parser.parse_frame(img, rois=rois, calib_resolution=calib_res)
export_telemetry_json('events/live_telemetry.json', res)

print(f"\nTeam Name: {res['team_name']}")
print(f"Total Team Kills: {res['team_eliminations']}")
print("-" * 65)
for m in res['squad_members']:
    print(f"  Slot #{m['slot']}: {m['name']:<16} | HP: {m['hp']:3d}/200 ({m['hp_percentage']:5.1f}%) [{m['status']:<8}] | Kills: {m['kills']}")

# Verify exported JSON packet
with open('events/live_telemetry.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

print("\n[+] live_telemetry.json verified successfully!")
print(f"    Exported Team: {data.get('team_name')}")
print(f"    Exported Team Kills: {data.get('team_eliminations')}")
print(f"    Alive players count: {sum(1 for m in data['squad_members'] if m['status'] != 'DEAD')}/4")
