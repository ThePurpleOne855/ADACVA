"""Switch cameras only after the previous capture worker releases its resources."""

from ada_piano.camera.source import parse_camera_source


class CameraController:
    def __init__(self, worker):
        self.worker = worker
        self.pending = None
        self.active = None

    def start(self, source):
        source = parse_camera_source(source)
        if self.worker.running:
            if source == self.active and self.pending is None:
                return
            self.pending = source
            self.worker.stop()
        else:
            self.pending = None
            self.worker.start(source)
            self.active = source

    def snapshot(self):
        if self.pending is not None:
            if self.worker.running:
                return None, f"Switching to camera {self.pending}… waiting for the previous camera to stop."
            source, self.pending = self.pending, None
            self.worker.start(source)
            self.active = source
        frame, status = self.worker.snapshot()
        if self.active is not None:
            status = f"Camera {self.active}: {status}"
        return frame, status

    def stop(self):
        self.pending = None
        self.worker.stop()

    def close(self):
        self.pending = None
        self.worker.close()
