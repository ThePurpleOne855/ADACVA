"""Standalone preview; importing this module never opens a camera."""


def main():
    import cv2
    from threading import Event
    from ada_piano.camera.stream import camera_frames

    frames = camera_frames(0, Event())
    try:
        for frame in frames:
            cv2.imshow("Piano Hand Tracker", frame.bgr)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        frames.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
