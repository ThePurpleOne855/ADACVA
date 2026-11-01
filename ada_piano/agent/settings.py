"""Load saved API keys so learners never have to enter them.

Keys live in the user's config folder (never in the repository):
Linux/macOS ~/.config/ada-piano/, Windows %APPDATA%\\ada-piano\\.
- openai_api_key: OpenAI voice, transcription and coaching. OPENAI_API_KEY takes precedence.
- meta_api_key: Meta Muse Spark coaching. MODEL_API_KEY (Meta's documented name) takes precedence.
"""
import os
from pathlib import Path
import sys

# Read at startup and kept out of os.environ, so helper processes never inherit it.
_meta_key = None


def key_file(name="openai_api_key"):
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "ada-piano" / name


def load_api_key(path=None):
    """Put the saved OpenAI key into OPENAI_API_KEY for this process; returns True if one is available.

    Without a path (app startup) this also reads a saved Meta Muse Spark key; see meta_api_key().
    """
    global _meta_key
    if path is None:
        try:
            _meta_key = key_file("meta_api_key").read_text(encoding="utf-8").strip() or None
        except OSError:
            _meta_key = None
    if os.environ.get("OPENAI_API_KEY"):
        return True
    try:
        key = Path(path or key_file()).read_text(encoding="utf-8").strip()
    except OSError:
        return False
    if key:
        os.environ["OPENAI_API_KEY"] = key
    return bool(key)


def meta_api_key():
    """The Meta Muse Spark key, or None."""
    return os.environ.get("MODEL_API_KEY") or _meta_key
