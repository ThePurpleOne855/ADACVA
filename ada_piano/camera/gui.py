"""Embedded Tk preview. All Tk calls stay on the main thread."""

import tkinter as tk
from tkinter import ttk

from ada_piano.camera.stream import CameraWorker
from ada_piano.camera.source import parse_camera_source


class CameraPanel(ttk.LabelFrame):
    def __init__(self, parent, worker=None):
        super().__init__(parent, text="Camera · hand tracking", padding=12)
        self.worker = worker if worker is not None else CameraWorker()
        self._photo = None
        self._closed = False
        self._notice = None
        self.source = tk.StringVar(value="0")
        self.status = tk.StringVar(value="Camera off. MIDI works independently.")
        controls = ttk.Frame(self)
        controls.pack(fill="x")
        ttk.Label(controls, text="Camera source:").pack(side="left")
        self.source_field = ttk.Combobox(controls, width=16, textvariable=self.source,
                                        values=("0", "1", "2", "/dev/video2"))
        self.source_field.pack(side="left", padx=6)
        self.start_button = ttk.Button(controls, text="Start camera", command=self.start)
        self.start_button.pack(side="left", padx=4)
        ttk.Button(controls, text="Stop camera", command=self.stop).pack(side="left")
        self.preview = ttk.Label(self, text="Start camera to see your hands.", anchor="center")
        self.preview.pack(fill="both", expand=True, pady=12)
        ttk.Label(self, textvariable=self.status, wraplength=410).pack(anchor="w")
        ttk.Label(self, text="Blue: base knuckles · Orange: middle joints\n"
                  "Green: fingertips · White: finger segments\n"
                  "Preview is unmirrored. Tracking does not grade fingering.",
                  wraplength=410).pack(anchor="w", pady=(8, 0))
        self._timer = self.after(50, self._tick)

    def start(self):
        try:
            self.worker.start(parse_camera_source(self.source.get()))
        except Exception as exc:
            self._notice = f"Camera error: {exc}"
            self.status.set(self._notice)
            return
        self._notice = None
        self.status.set("Starting camera…")

    def stop(self):
        self._notice = None
        self.worker.stop()
        self._clear_preview()

    def _clear_preview(self):
        self.preview.configure(image="", text="Camera off.")
        self._photo = None

    def _tick(self):
        try:
            frame, status = self.worker.snapshot()
            self.status.set(self._notice or status)
            self.start_button.configure(state="disabled" if self.worker.running else "normal")
            if frame is not None:
                self._photo = tk.PhotoImage(master=self, data=frame.ppm, format="PPM")
                self.preview.configure(image=self._photo, text="")
            elif not self.worker.running:
                self._clear_preview()
        except Exception as exc:
            self.worker.stop()
            self._clear_preview()
            self._notice = f"Camera preview error: {exc}"
            self.status.set(self._notice)
        finally:
            if not self._closed:
                self._timer = self.after(50, self._tick)

    def close(self):
        self._closed = True
        self.after_cancel(self._timer)
        self.worker.close()
