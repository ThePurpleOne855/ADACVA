"""Independent webcam check; hand landmarks and key calibration come next."""

from time import monotonic


def check_camera(index: int = 0, seconds: float = 5, preview: bool = False) -> int:
    if seconds <= 0:
        raise ValueError("Camera duration must be greater than zero.")
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError('Camera dependencies missing. Run: uv sync --extra camera') from exc
    camera = cv2.VideoCapture(index)
    count = 0
    try:
        if not camera.isOpened():
            raise RuntimeError(f"Cannot open camera {index}. Check permissions, connection, or --index.")
        deadline = monotonic() + seconds
        while monotonic() < deadline:
            ok, frame = camera.read()
            if not ok:
                raise RuntimeError("Camera opened but a frame could not be read.")
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
