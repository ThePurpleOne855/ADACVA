"""Load a saved OpenAI API key so learners never have to enter it.

The key lives in the user's config folder (never in the repository):
Linux/macOS ~/.config/ada-piano/openai_api_key, Windows %APPDATA%\\ada-piano\\openai_api_key.
An OPENAI_API_KEY already in the environment takes precedence.
"""
import os
from pathlib import Path
import sys


def key_file():
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "ada-piano" / "openai_api_key"


def load_api_key(path=None):
    """Put the saved key into OPENAI_API_KEY for this process; returns True if one is available."""
    if os.environ.get("OPENAI_API_KEY"):
        return True
    try:
        key = Path(path or key_file()).read_text(encoding="utf-8").strip()
    except OSError:
        return False
    if key:
        os.environ["OPENAI_API_KEY"] = key
    return bool(key)
