"""Minimal chat session for using ADA without score or hardware modules."""
from types import SimpleNamespace


class ChatSession:
    loaded = None
    tutor = None
    latest_attempt = None
    activity_version = 0

    def __init__(self):
        self.playback = SimpleNamespace(player=SimpleNamespace(
            status=SimpleNamespace(state="idle")))

    def stop(self):
        self.activity_version += 1

