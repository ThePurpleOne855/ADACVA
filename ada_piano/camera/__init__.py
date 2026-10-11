"""Independent capture-only check; hand tracking runs in the camera panel."""

from time import monotonic

from ada_piano.camera.source import CameraSource, parse_camera_source


def check_camera(source: CameraSource = 0, seconds: float = 5, preview: bool = False) -> int:
    if seconds <= 0:
        raise ValueError("Camera duration must be greater than zero.")
    source = parse_camera_source(source)
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError('Camera dependencies missing. Run: uv sync --extra camera') from exc
    camera = cv2.VideoCapture(source)
    count = 0
    try:
        if not camera.isOpened():
            raise RuntimeError(f"Cannot open camera source {source}. Check permissions, connection, or --source.")
        deadline = monotonic() + seconds
        while monotonic() < deadline:
            ok, frame = camera.read()
            if not ok:
                raise RuntimeError(f"Camera source {source} opened but a frame could not be read.")
            count += 1
            if preview:
                cv2.imshow("ADA camera check - Q to close", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    finally:
        camera.release()
        if preview:
            cv2.destroyAllWindows()
    return count
