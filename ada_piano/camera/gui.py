"""Embedded Tk preview. All Tk calls stay on the main thread."""

import tkinter as tk
from tkinter import ttk

from ada_piano.camera.stream import CameraWorker
from ada_piano.camera.controller import CameraController
from ada_piano.camera.devices import camera_choices


class CameraPanel(ttk.LabelFrame):
    def __init__(self, parent, worker=None):
        super().__init__(parent, text="Camera · hand tracking", padding=12)
        self.worker = worker if worker is not None else CameraWorker()
        self.controller = CameraController(self.worker)
        self._photo = None
        self._closed = False
        self._notice = None
        self.selection = tk.StringVar()
        self._choices = {}
        self.status = tk.StringVar(value="Camera off. MIDI works independently.")
        ttk.Label(self, text="Camera source:").pack(anchor="w")
        self.selector = ttk.Combobox(self, textvariable=self.selection, state="readonly")
        self.selector.pack(fill="x", pady=(4, 8))
        self.selector.bind("<<ComboboxSelected>>", self._selected)
        controls = ttk.Frame(self)
        controls.pack(fill="x")
        ttk.Button(controls, text="Refresh cameras", command=self.refresh).pack(side="left")
        self.start_button = ttk.Button(controls, text="Start camera", command=self.start)
        self.start_button.pack(side="left", padx=4)
        ttk.Button(controls, text="Stop camera", command=self.stop).pack(side="left")
        self.preview = ttk.Label(self, text="Start camera to see your hands.", anchor="center")
        self.preview.pack(fill="both", expand=True, pady=12)
        ttk.Label(self, textvariable=self.status, wraplength=410).pack(anchor="w")
        ttk.Label(self, text="Blue: base knuckles · Orange: middle joints\n"
                  "Green: fingertips · White: finger segments\n"
                  "Preview is mirrored. Tracking does not grade fingering.",
                  wraplength=410).pack(anchor="w", pady=(8, 0))
        self.refresh()
        self._timer = self.after(50, self._tick)

    def refresh(self):
        previous = self._choices.get(self.selection.get())
        self._choices = camera_choices()
        self.selector["values"] = tuple(self._choices)
        self.selection.set(next((label for label, index in self._choices.items() if index == previous),
                                next(iter(self._choices))))

    def _selected(self, event=None):
        if self.worker.running or self.controller.pending is not None:
            self.start()

    def start(self):
        try:
            index = self._choices.get(self.selection.get())
            if index is None:
                raise ValueError("Select a camera first.")
            self.controller.start(index)
        except Exception as exc:
            self._notice = f"Camera error: {exc}"
            self.status.set(self._notice)
            return
        self._notice = None
        self._clear_preview()
        self.status.set(f"Starting camera {index}…")

    def stop(self):
        self._notice = None
        self.controller.stop()
        self._clear_preview()

    def _clear_preview(self):
        self.preview.configure(image="", text="Camera off.")
        self._photo = None

    def _tick(self):
        try:
            frame, status = self.controller.snapshot()
            self.status.set(self._notice or status)
            self.start_button.configure(text="Switch camera" if self.worker.running else "Start camera")
            if frame is not None:
                self._photo = tk.PhotoImage(master=self, data=frame.ppm, format="PPM")
                self.preview.configure(image=self._photo, text="")
            elif not self.worker.running:
                self._clear_preview()
        except Exception as exc:
            self.controller.stop()
            self._clear_preview()
            self._notice = f"Camera preview error: {exc}"
            self.status.set(self._notice)
        finally:
            if not self._closed:
                self._timer = self.after(50, self._tick)

    def close(self):
        self._closed = True
        self.after_cancel(self._timer)
        self.controller.close()
