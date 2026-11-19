"""
Topological & High-Precision Kill Digit Extractor for Free Fire HUD.
Handles active players (bright white) and eliminated players (dimmed 50% opacity).
Filters out edge-cut artifacts from skull icons, table lines, or eye indicators.
"""

import cv2
import numpy as np


def extract_digit_from_row(crop: np.ndarray) -> int:
    """
    Extracts individual kill count from a player_kills row crop.
    Immune to skull icons on left and spectated eye icons on right.
    """
    if crop is None or crop.size == 0:
        return 0

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if len(crop.shape) == 3 else crop
    ch_h, ch_w = gray.shape[:2]
    max_val = np.max(gray)
    if max_val < 50:
        return 0

    # Adaptive binarization based on peak brightness (works for alive and eliminated players)
    th_val = max(55, int(max_val * 0.65))
    _, th = cv2.threshold(gray, th_val, 255, cv2.THRESH_BINARY)

    # Zero out top/bottom border lines
    th[0:2, :] = 0
    th[-2:, :] = 0

    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(th)

    digit_glyphs = []
    for lbl in range(1, num_labels):
        x, y, cw, ch, area = stats[lbl]
        # Ignore edge-bleed cuts from skull icon touching left edge (x <= 1)
        # and eye icon border cuts touching right edge (x + cw >= ch_w - 1)
        if x <= 1 or (x + cw) >= (ch_w - 1):
            continue

        # A digit in Free Fire has height between 10 and 20, width between 3 and 12, area >= 22
        if 10 <= ch <= 20 and 3 <= cw <= 12 and area >= 22:
            digit_glyphs.append((x, th[y:y+ch, x:x+cw]))

    if not digit_glyphs:
        return 0

    # Sort left to right (supports multi-digit counts like 10, 15 kills)
    digit_glyphs.sort(key=lambda g: g[0])
    val = 0
    for x, glyph in digit_glyphs:
        d = classify_single_digit(glyph)
        val = val * 10 + d

    return val


def classify_single_digit(glyph: np.ndarray) -> int:
    """Classifies a single normalized glyph into digit 0-9."""
    h, w = glyph.shape
    if w <= 0 or h <= 0:
        return 0

    # Thin vertical stroke -> 1
    aspect = float(w) / float(h)
    if aspect < 0.42:
        return 1

    padded = cv2.copyMakeBorder(glyph, 1, 1, 1, 1, cv2.BORDER_CONSTANT, value=0)
    contours, hierarchy = cv2.findContours(padded, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    num_holes = 0
    if hierarchy is not None:
        holes = [idx for idx, h_elem in enumerate(hierarchy[0]) if h_elem[3] == 0]
        num_holes = len(holes)

    if num_holes == 2:
        return 8

    if num_holes == 1:
        # 0, 4, 6, 9
        M = cv2.moments(contours[holes[0]])
        if M["m00"] > 0:
            cy = M["m01"] / M["m00"]
            norm_cy = cy / float(padded.shape[0])
            if 0.35 <= norm_cy <= 0.65:
                return 0
            elif norm_cy > 0.65:
                return 6
            else:
                return 4 if aspect > 0.60 else 9
        return 0

    # 0 holes: 2, 3, 5, 7
    # Digit 2 has a wide, solid horizontal base bar at the bottom
    bot_row = glyph[-2:, :]
    bot_fill_ratio = np.mean(bot_row > 0)

    # Digit 7 has a wide horizontal bar at the top, but NOT at the bottom
    top_row = glyph[:2, :]
    top_fill_ratio = np.mean(top_row > 0)

    # Middle profile
    mid_y1 = int(h * 0.35)
    mid_y2 = int(h * 0.65)
    mid_left = glyph[mid_y1:mid_y2, :w//2]
    mid_right = glyph[mid_y1:mid_y2, w//2:]

    if bot_fill_ratio >= 0.55:
        # Solid base bar -> 2
        return 2
    elif top_fill_ratio >= 0.55 and bot_fill_ratio < 0.35:
        # Solid top bar, thin bottom tip -> 7
        return 7
    elif np.mean(mid_left > 0) < 0.20 and np.mean(mid_right > 0) > 0.35:
        # Open on left, filled on right -> 3
        return 3
    else:
        # Top-left filled, bottom-left open -> 5
        return 5
