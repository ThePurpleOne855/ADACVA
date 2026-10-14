"""Quiet desktop surface for the spoken coach, with native keyboard fallbacks."""

import tkinter as tk
from tkinter import ttk


class AccessibleView(tk.Frame):
    """Present the coach without exposing the setup panels during practice."""

    BACKGROUND = "#0b0d1c"
    FOREGROUND = "#f5f3ff"
    MUTED = "#bdc5df"
    FOCUS = "#c2b8ff"

    def __init__(self, parent, *, submit, talk, stop, tools, status):
        super().__init__(parent, background=self.BACKGROUND)
        self._submit = submit
        self._closed = False
        self.status = status

        header = tk.Frame(self, background=self.BACKGROUND)
        tk.Label(header, text="ADA", background=self.BACKGROUND,
                 foreground=self.FOREGROUND, font=("", 21, "bold")).pack(side="left")
        tk.Label(header, text="P I A N O   C O M P A N I O N", background=self.BACKGROUND,
                 foreground=self.MUTED, font=("", 9)).pack(side="left", padx=18)

        self.background = tk.Canvas(self, background=self.BACKGROUND, height=180,
                                    borderwidth=0, highlightthickness=0, takefocus=False)
        self.background.bind("<Configure>", self._draw)

        panel = tk.Frame(self, background=self.BACKGROUND)
        tk.Label(panel, text="Your piano. Your pace.", background=self.BACKGROUND,
                 foreground=self.FOREGROUND, font=("", 25)).pack(anchor="w")
        tk.Label(panel, text="F1 to talk  ·  Escape to stop", background=self.BACKGROUND,
                 foreground=self.MUTED, font=("", 11)).pack(anchor="w", pady=(6, 12))
        self.status_label = tk.Label(panel, textvariable=status, anchor="w", justify="left",
                                     background=self.BACKGROUND, foreground=self.FOREGROUND,
                                     font=("", 11), wraplength=660)
        self.status_label.pack(fill="x", pady=(0, 14))

        tk.Label(panel, text="Your message", background=self.BACKGROUND,
                 foreground=self.MUTED, font=("", 10)).pack(anchor="w", pady=(0, 5))
        self.entry = tk.Entry(panel, name="message", background="#14192c",
                              foreground=self.FOREGROUND, insertbackground=self.FOREGROUND,
                              selectbackground="#6558a1", selectforeground="white",
                              relief="flat", highlightthickness=2,
                              highlightbackground="#414967", highlightcolor=self.FOCUS,
                              font=("", 13))
        self.entry.pack(fill="x", ipady=9)
        self.entry.bind("<Return>", self._send)
        controls = tk.Frame(panel, background=self.BACKGROUND)
        controls.pack(fill="x", pady=(12, 16))
        self.talk_button = self._button(controls, "Talk to ADA", talk, primary=True)
        self.talk_button.pack(side="left", padx=(0, 10))
        self.stop_button = self._button(controls, "Stop", stop)
        self.stop_button.pack(side="left", padx=(0, 10))
        self.tools_button = self._button(controls, "Tools & settings", tools)
        self.tools_button.pack(side="right")

        tk.Label(panel, text="Conversation", background=self.BACKGROUND,
                 foreground=self.MUTED, font=("", 10)).pack(anchor="w", pady=(0, 4))
        history = tk.Frame(panel, background=self.BACKGROUND)
        history.pack(fill="both", expand=True)
        self.transcript = tk.Text(history, name="conversation", height=3, wrap="word",
                                  state="disabled", takefocus=True, background=self.BACKGROUND,
                                  foreground=self.MUTED, insertbackground=self.FOREGROUND,
                                  selectbackground="#6558a1", selectforeground="white",
                                  relief="flat", borderwidth=0, highlightthickness=2,
                                  highlightbackground=self.BACKGROUND, highlightcolor=self.FOCUS,
                                  font=("", 11), padx=2, pady=4)
        scrollbar = ttk.Scrollbar(history, command=self.transcript.yview, takefocus=False)
        self.transcript.configure(yscrollcommand=scrollbar.set)
        self.transcript.tag_configure("speaker", foreground=self.FOREGROUND)
        scrollbar.pack(side="right", fill="y")
        self.transcript.pack(fill="both", expand=True)
        self.transcript.bind("<Tab>", self._next_control)
        self.transcript.bind("<Shift-Tab>", self._previous_control)
        self.transcript.bind("<ISO_Left_Tab>", self._previous_control)

        header.pack(fill="x", padx=36, pady=(22, 0))
        # Keep the controls visible when the window is reduced to its minimum size.
        panel.pack(side="bottom", fill="x", padx=36, pady=(8, 22))
        self.background.pack(fill="both", expand=True)
        panel.bind("<Configure>", lambda event: self.status_label.configure(wraplength=event.width))

    def _button(self, parent, label, command, *, primary=False):
        return tk.Button(parent, text=label, command=command, takefocus=True,
                         background=self.FOCUS if primary else "#20263d",
                         foreground="#13142a" if primary else self.FOREGROUND,
                         activebackground="#dfd8ff" if primary else "#384462",
                         activeforeground="#13142a" if primary else "white",
                         relief="flat", borderwidth=0, highlightthickness=2,
                         highlightbackground=self.BACKGROUND, highlightcolor="white",
                         font=("", 11), padx=16, pady=9, cursor="hand2")

    def _send(self, event=None):
        text = self.entry.get().strip()
        if text and not self._closed:
            self._submit(text)
            self.entry.delete(0, "end")
        return "break"

    def append(self, speaker, text):
        """Mirror a spoken turn in selectable, keyboard-readable native text."""
        if self._closed:
            return
        self.transcript.configure(state="normal")
        self.transcript.insert("end", f"{speaker}: ", "speaker")
        self.transcript.insert("end", f"{text}\n\n")
        if int(self.transcript.index("end-1c").split(".")[0]) > 300:
            self.transcript.delete("1.0", "100.0")
        self.transcript.see("end")
        self.transcript.configure(state="disabled")

    def focus_message(self):
        if not self._closed:
            self.entry.focus_set()

    @staticmethod
    def _next_control(event):
        event.widget.tk_focusNext().focus_set()
        return "break"

    @staticmethod
    def _previous_control(event):
        event.widget.tk_focusPrev().focus_set()
        return "break"

    def _draw(self, event):
        """Paint a static halo; resizing is the only work scheduled by the artwork."""
        canvas = self.background
        canvas.delete("all")
        width, height = event.width, event.height
        x, y = width * 0.58, height * 0.52
        radius = min(height * 0.38, 96)
        if radius < 8:
            return
        # The halo fades into the same solid color used behind native controls.
        for step in range(48):
            fraction = step / 47
            color = "#%02x%02x%02x" % (int(11 + fraction ** 2 * 23),
                                      int(13 + fraction ** 2 * 22),
                                      int(28 + fraction ** 2 * 51))
            horizontal, vertical = radius * (3.0 - 1.5 * fraction), radius * (1.2 - 0.4 * fraction)
            canvas.create_oval(x - horizontal, y - vertical, x + horizontal, y + vertical,
                               fill=color, outline="")
        for step in range(64):
            fraction = step / 63
            size = radius * (1 - fraction * 0.83)
            color = "#%02x%02x%02x" % (int(37 + fraction ** 0.65 * 170),
                                      int(46 + fraction ** 0.7 * 155),
                                      int(79 + fraction ** 0.6 * 165))
            canvas.create_oval(x - size, y - size, x + size, y + size, fill=color, outline="")
        canvas.create_arc(x - radius * 1.5, y - radius * 0.52,
                          x + radius * 1.5, y + radius * 0.52,
                          start=185, extent=175, style="arc", outline="#7782b6", width=1)
        canvas.create_arc(x - radius * 1.3, y - radius * 0.64,
                          x + radius * 1.3, y + radius * 0.64,
                          start=6, extent=151, style="arc", outline="#444e7a", width=1)

    def close(self):
        """Stop accepting transcript updates before the parent destroys the window."""
        self._closed = True
