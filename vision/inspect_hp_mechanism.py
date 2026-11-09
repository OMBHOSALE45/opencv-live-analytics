"""
Visualize HP bar pixels on damaged (TG row 1) vs healthy (TG row 2 and DG rows).
"""
import cv2
import numpy as np

# Load TG screen (Row 1 damaged ~75%, Row 2 healthy)
tg = cv2.imread("G:/opencv-live-analytics/recordings/snapshots/squad_tg_screen.jpg")
h, w = tg.shape[:2]
hdr_h = int(h * 0.24)
rost = tg[hdr_h:, :]
rh, rw = rost.shape[:2]
row_h = rh / 4.0

r1 = rost[int(0*row_h):int(1*row_h), :]
r2 = rost[int(1*row_h):int(2*row_h), :]

# Let's inspect the entire card background of r1 vs r2:
# In Free Fire:
# What makes row 1 look damaged?
# Let's look at the color:
# Let's check HSV or BGR of r1 vs r2:
b1, g1, r1_c = cv2.split(r1)
b2, g2, r2_c = cv2.split(r2)

print(f"Row 1 (damaged) BGR means: B={b1.mean():.1f}, G={g1.mean():.1f}, R={r1_c.mean():.1f}")
print(f"Row 2 (healthy) BGR means: B={b2.mean():.1f}, G={g2.mean():.1f}, R={r2_c.mean():.1f}")

# Look at the horizontal transition in Row 1:
# In Row 1, where does the light card background change to dark grass background?
row1_gray = cv2.cvtColor(r1, cv2.COLOR_BGR2GRAY)
# Let's print the mean of the top half (y=10..30) and bottom half (y=30..50) across X in steps of 10:
print("\nRow 1 brightness across X (y=15..45):")
for x in range(0, rw, 20):
    val = row1_gray[15:45, x:x+20].mean()
    print(f"  x={x:3d}..{x+20:3d}: {val:.1f}")

print("\nRow 2 brightness across X (y=15..45):")
row2_gray = cv2.cvtColor(r2, cv2.COLOR_BGR2GRAY)
for x in range(0, rw, 20):
    val = row2_gray[15:45, x:x+20].mean()
    print(f"  x={x:3d}..{x+20:3d}: {val:.1f}")

