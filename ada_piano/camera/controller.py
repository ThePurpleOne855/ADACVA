"""Switch cameras only after the previous capture worker releases its resources."""


class CameraController:
    def __init__(self, worker):
        self.worker = worker
        self.pending = None
        self.active = None

    def start(self, index):
        if self.worker.running:
            if index == self.active and self.pending is None:
                return
            self.pending = index
            self.worker.stop()
        else:
            self.pending = None
            self.worker.start(index)
            self.active = index

    def snapshot(self):
        if self.pending is not None:
            if self.worker.running:
                return None, f"Switching to camera {self.pending}… waiting for the previous camera to stop."
            index, self.pending = self.pending, None
            self.worker.start(index)
            self.active = index
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
