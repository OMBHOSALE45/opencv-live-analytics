"""
ASCII visualizer of the 4 kill boxes.
"""
import cv2

for idx in range(1, 5):
    img = cv2.imread(f"G:/opencv-live-analytics/recordings/snapshots/_exact_k_{idx}.png")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    print(f"\n{'='*30}\n  ROW {idx} KILL BOX (28x28)\n{'='*30}")
    # Threshold white text vs background
    # Free Fire text is bright white (>200) or has dark outline
    for y in range(0, 28, 2):
        row_str = ""
        for x in range(0, 28):
            val = gray[y, x]
            if val > 190:
                row_str += "#"
            elif val > 140:
                row_str += "."
            else:
                row_str += " "
        print(f"{y:2d}: {row_str}")

