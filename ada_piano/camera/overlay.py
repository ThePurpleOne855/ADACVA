"""Finger joint overlay shared by the standalone and embedded camera views."""

import cv2

# Landmark order: base (MCP), middle (PIP), distal (DIP), tip.
# The thumb has an IP joint instead of separate PIP and DIP joints.
finger_joints = {
    "Thumb": (2, 3, 4),
    "Index": (5, 6, 7, 8),
    "Middle": (9, 10, 11, 12),
    "Ring": (13, 14, 15, 16),
    "Pinky": (17, 18, 19, 20),
}


def draw_hand(frame, hand):
    height, width = frame.shape[:2]
    points = [(int(point.x * width), int(point.y * height)) for point in hand]

    for finger_name, joints in finger_joints.items():
        # Include the distal joint so the line follows the finger's bend.
        for start, end in zip(joints, joints[1:]):
            cv2.line(frame, points[start], points[end], (220, 220, 220), 2)
        if len(joints) == 4:
            cv2.circle(frame, points[joints[2]], 4, (220, 220, 220), -1)

        markers = (
            (joints[0], "base", (255, 180, 0)),
            (joints[1], "IP" if finger_name == "Thumb" else "mid", (0, 180, 255)),
            (joints[-1], "tip", (0, 255, 0)),
        )
        for landmark_id, joint_name, color in markers:
            x, y = points[landmark_id]
            cv2.circle(frame, (x, y), 6, color, -1)
            label = f"{finger_name} {joint_name}"
            # Outline labels for contrast over light or dark backgrounds.
            for thickness, text_color in ((3, (0, 0, 0)), (1, color)):
                cv2.putText(
                    frame, label, (x + 8, y - 8), cv2.FONT_HERSHEY_SIMPLEX,
                    0.4, text_color, thickness, cv2.LINE_AA,
                )

