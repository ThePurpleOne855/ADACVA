"""Optional local speech. Text always remains available to screen readers."""


class Feedback:
    def __init__(self, speak: bool = False):
        self.engine = None
        if speak:
            try:
                import pyttsx3
                self.engine = pyttsx3.init()
                self.engine.setProperty("rate", 165)
            except Exception as exc:
                raise RuntimeError(
                    'Speech unavailable. Install ".[speech]" and a system voice '
                    '(Linux: eSpeak NG), or omit --speak for text mode.'
                ) from exc

    def say(self, text: str):
        print(text, flush=True)
        if self.engine is not None:
            self.engine.say(text)
            self.engine.runAndWait()

    def close(self):
        if self.engine is not None:
            self.engine.stop()
