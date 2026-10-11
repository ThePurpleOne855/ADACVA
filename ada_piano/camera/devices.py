"""Read Linux camera names without opening devices; use numbered choices elsewhere."""

from pathlib import Path


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
        choices[index] = f"{name or 'Camera'} (camera {index})"
    # OpenCV does not expose portable device names. Keep manual choices available
    # on other platforms and when no Linux devices are visible yet.
    if not choices:
        choices = {index: f"Camera {index}" for index in range(5)}
    return {label: index for index, label in sorted(choices.items())}
