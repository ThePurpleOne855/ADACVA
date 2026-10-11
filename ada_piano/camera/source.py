"""Normalize user input without restricting OpenCV's string sources."""

import re

CameraSource = int | str


def parse_camera_source(source: CameraSource) -> CameraSource:
    """Convert numeric entries to indices; pass paths/URLs through as strings."""
    if isinstance(source, bool) or not isinstance(source, (int, str)):
        raise ValueError("Camera source must be an integer index or a nonempty string.")
    if isinstance(source, str):
        source = source.strip()
        if not source:
            raise ValueError("Camera source cannot be empty.")
        if re.fullmatch(r"[+-]?[0-9]+", source):
            source = int(source)
    if isinstance(source, int) and source < 0:
        raise ValueError("Camera index must be zero or greater.")
    return source
