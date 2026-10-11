"""Legacy CLI feedback over nonblocking system speech."""

from ada_piano.voice import VoiceService


class Feedback:
    def __init__(self, speak: bool = False):
        self.engine = VoiceService() if speak else None
        self._last = None
        if self.engine is not None and not self.engine.available:
            print(self.engine.status, flush=True)

    def say(self, text: str):
        print(text, flush=True)
        if self.engine is not None:
            self._last = self.engine.say(text)

    def close(self):
        if self.engine is not None:
            if self._last is not None:
                self._last.wait(timeout=5)
            self.engine.close()
