"""
Crop and inspect the exact kill column for all 4 rows in squad_dg_elim5.jpg.
"""
import cv2

img = cv2.imread("G:/opencv-live-analytics/recordings/snapshots/squad_dg_elim5.jpg")
h, w = img.shape[:2]

# In 1024x575 image:
# Squad table is at x ≈ 0..190, y ≈ 460..572
# Roster rows:
# Row 1: y=460..488
# Row 2: y=488..516
# Row 3: y=516..544
# Row 4: y=544..572
# Kills are at x ≈ 165..185 (width ~20px)

for i, (y1, y2) in enumerate([(460, 488), (488, 516), (516, 544), (544, 572)]):
    kill_box = img[y1:y2, 160:188]
    cv2.imwrite(f"G:/opencv-live-analytics/recordings/snapshots/_exact_k_{i+1}.png", kill_box)
    print(f"Row {i+1} kill box: shape {kill_box.shape}")

