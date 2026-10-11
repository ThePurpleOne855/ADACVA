"""Find native or Flatpak Audiveris without requiring a manually entered command."""

import os
from pathlib import Path
import shutil
import subprocess

APP_ID = "org.audiveris.audiveris"


def _native():
    for name in ("audiveris", "Audiveris"):
        found = shutil.which(name)
        if found:
            return found
    candidates = [Path("/opt/audiveris/bin/Audiveris"),
                  Path("/Applications/Audiveris.app/Contents/MacOS/Audiveris")]
    if os.name == "nt":
        candidates.insert(0, Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Audiveris" / "Audiveris.exe")
    return next((str(path) for path in candidates if path.is_file() and os.access(path, os.X_OK)), None)


def audiveris_command(executable, import_folder):
    choice = executable.strip()
    automatic = choice.lower() in {"", "auto", "automatic", "audiveris"}
    if automatic:
        native = _native()
        if native:
            return [native]
    elif choice.lower() != "flatpak":
        if Path(choice).suffix.lower() in {".pdf", ".xml", ".mxl", ".musicxml"}:
            raise ValueError("This field is for the converter, not the score. Use auto here and Choose PDF / MusicXML for your document.")
        found = shutil.which(str(Path(choice).expanduser()))
        if found is None:
            raise RuntimeError(f"Cannot run Audiveris at {choice!r}. Use auto or choose its installed executable.")
        return [found]

    flatpak = shutil.which("flatpak")
    if flatpak:
        try:
            result = subprocess.run([flatpak, "info", APP_ID], stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL, timeout=5)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError(f"Could not check the Audiveris Flatpak installation: {exc}") from exc
        if result.returncode == 0:
            return [flatpak, "run", f"--filesystem={Path(import_folder).resolve()}", APP_ID]
    raise RuntimeError("Audiveris was not found. Install Audiveris or import MusicXML directly. "
                       "On Linux: flatpak install flathub org.audiveris.audiveris")
