"""
Inspect row kills
"""
import cv2

for i in range(1, 5):
    p = f"G:/opencv-live-analytics/recordings/snapshots/row{i}_kill.jpg"
    img = cv2.imread(p)
    if img is not None:
        print(f"row{i}_kill.jpg: shape {img.shape}")

