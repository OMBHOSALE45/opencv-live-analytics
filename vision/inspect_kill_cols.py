"""
Inspect columns inside the 28x28 kill boxes.
"""
import cv2

for idx in range(1, 5):
    img = cv2.imread(f"G:/opencv-live-analytics/recordings/snapshots/_exact_k_{idx}.png")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    # Print max brightness in each column x:
    col_max = [int(gray[:, x].max()) for x in range(w)]
    print(f"Row {idx} kill box col max (x=0..27): {col_max}")

