"""Read Linux camera names without opening devices; use numbered choices elsewhere."""

import os
from pathlib import Path
import re

from ada_piano.camera.source import parse_camera_source

VIRTUAL = re.compile(r"dummy|loopback|droidcam|obs virtual", re.I)
BUILT_IN = re.compile(r"integrated|built-?in|internal|facetime|front|rear", re.I)


def camera_choices(device_root=Path("/sys/class/video4linux")):
    choices = {}
    for device in device_root.glob("video*"):
        suffix = device.name.removeprefix("video")
        if not suffix.isdigit():
            continue
        index = int(suffix)
        try:
            name = (device / "name").read_text().strip()
        except OSError:
            name = "Camera"
        try:
            # Each webcam also exposes metadata nodes (index 1+) that cannot capture video.
            if (device / "index").read_text().strip() not in ("", "0"):
                continue
        except OSError:
            pass
        choices[index] = f"{name or 'Camera'} (camera {index})"
    # OpenCV does not expose portable device names. Keep manual choices available
    # on other platforms and when no Linux devices are visible yet.
    if not choices:
        choices = {index: f"Camera {index}" for index in range(5)}
    return {label: index for index, label in sorted(choices.items())}


def best_camera(device_root=Path("/sys/class/video4linux"), environ=os.environ):
    """Pick the simplest working source: ADA_CAMERA, then an external USB webcam, then built-in.

    Virtual devices left by phone-webcam drivers (v4l2loopback "Dummy video device",
    DroidCam) are skipped because they show nothing unless that app is running.
    Returns (source, spoken description).
    """
    configured = environ.get("ADA_CAMERA", "").strip()
    if configured:
        return parse_camera_source(configured), "the camera set in ADA_CAMERA"
    real = [(label, index) for label, index in camera_choices(device_root).items() if not VIRTUAL.search(label)]
    external = [(label, index) for label, index in real if not BUILT_IN.search(label)]
    if external or real:
        label, index = (external or real)[0]
        return index, label.rsplit(" (camera", 1)[0]
    return 0, "camera 0"
