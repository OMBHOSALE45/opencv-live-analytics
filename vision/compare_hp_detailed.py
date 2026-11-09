"""
Analyze the exact visual difference when a player loses HP.
In squad_tg_screen.jpg: Player 1 has lost HP, Players 2, 3, 4 have full HP.
Let's compare Row 1 vs Row 2 in squad_tg_screen.jpg!
"""
import cv2
import numpy as np

img = cv2.imread("G:/opencv-live-analytics/recordings/snapshots/squad_tg_screen.jpg")
h, w = img.shape[:2]
header_h = int(h * 0.24)
roster = img[header_h:, :]
rh, rw = roster.shape[:2]
row_h = rh / 4.0

r1 = roster[int(0*row_h):int(1*row_h), :]
r2 = roster[int(1*row_h):int(2*row_h), :]

# Let's subtract row 2 from row 1, or inspect the differences:
cv2.imwrite("G:/opencv-live-analytics/recordings/snapshots/_r1_comp.png", r1)
cv2.imwrite("G:/opencv-live-analytics/recordings/snapshots/_r2_comp.png", r2)

print("Row 1 shape:", r1.shape)
print("Row 2 shape:", r2.shape)

# Let's inspect the columns of Row 1 vs Row 2 in detail:
# For each column x from 0 to rw:
g1 = cv2.cvtColor(r1, cv2.COLOR_BGR2GRAY)
g2 = cv2.cvtColor(r2, cv2.COLOR_BGR2GRAY)

print("\nMean brightness per column across 10-pixel slices:")
for x in range(0, rw, 20):
    m1 = g1[:, x:x+20].mean()
    m2 = g2[:, x:x+20].mean()
    print(f"  x={x:3d}..{x+20:3d}: Row1={m1:5.1f} | Row2={m2:5.1f} | Diff={m1-m2:+5.1f}")

