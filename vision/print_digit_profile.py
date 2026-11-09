"""
Print vertical profile of each digit.
"""
import cv2

for idx in range(1, 5):
    img = cv2.imread(f"G:/opencv-live-analytics/recordings/snapshots/_exact_k_{idx}.png")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # The digit is located at x=10..17, y=8..22
    digit_crop = gray[8:22, 10:18]
    print(f"\nRow {idx} digit crop (8x14):")
    for y in range(digit_crop.shape[0]):
        row_str = " ".join([f"{v:3d}" for v in digit_crop[y]])
        print(f"  y={y:2d}: {row_str}")

