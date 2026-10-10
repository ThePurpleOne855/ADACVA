# ADA Piano Teacher

MusicXML import is available for single-note pitch practice. See
[importing existing sheet music](docs/MUSICXML.md) for supported files and limits.

Accessible Piano Learning Assistant: a Python hackathon prototype for blind and visually impaired learners.

## Start here (2 minutes once dependencies are available)

After installing [uv](https://docs.astral.sh/uv/getting-started/installation/), run the simulated demo. It needs no piano, camera, or API key:

```sh
uv run python -m ada_piano demo
```

uv manages Python and the local `.venv` automatically; no environment activation is needed. The first run needs network access to resolve packages and install the project. The demo plays simulated MIDI numbers `60, 61, 62, 64, 65, 67`: C, an intentionally wrong C sharp, then D, E, F, G. The tutor corrects the mistake and finishes the exercise. This is text output; enable local speech after installing its dependencies.

## Set up dependencies (5–10 minutes)

1. Check uv is available: `uv --version`.
2. Install the hardware dependencies: `uv sync --extra hardware`.
3. Run checks: `uv run python -m unittest discover -s tests -v`.
4. Try speech: `uv run --extra speech python -m ada_piano demo --speak`.

Use `uv sync` for the base project, or select individual extras with `uv sync --extra camera`, `uv sync --extra midi`, or `uv sync --extra speech`. The base application has no external runtime dependencies. `.python-version` selects Python 3.12 for development; the package still supports Python 3.11+. uv can download the selected interpreter if needed. Native dependencies still require validation on the demo operating system.

### Dependency workflow

`pyproject.toml` remains the dependency source, and setuptools remains the build backend. uv manages installation, the virtual environment, and dependency locking. See the [uv project guide](https://docs.astral.sh/uv/guides/projects/).

- Add a dependency with `uv add PACKAGE`; use `uv add --optional camera PACKAGE` for an optional camera dependency.
- Generate or refresh the lockfile with `uv lock`. Commit `uv.lock` alongside dependency changes.
- Once the lockfile exists, reproduce the hardware environment with `uv sync --locked --extra hardware`.
- Upgrade one dependency deliberately with `uv lock --upgrade-package PACKAGE`.

**Current setup limitation:** this workspace cannot resolve `pypi.org`, so `uv.lock` could not be generated and a full sync has not been verified. Run `uv sync --extra hardware` on a network-connected computer to generate the lockfile and install dependencies. Do not use `--locked` until that lockfile exists.

For an offline core demo with Python already installed, `python -m ada_piano demo` still works directly from the repository. This bypasses uv dependency synchronization and does not verify hardware dependencies.

| Dependency | Purpose |
| --- | --- |
| OpenCV | Capture webcam frames |
| MediaPipe | Hand landmark detection (included in camera and hardware extras; integration in progress) |
| Mido + python-rtmidi | Receive key events through a USB-to-MIDI interface |
| pyttsx3 | Speak feedback locally using a system voice |
| Python standard library | Exercises, tutor logic, CLI, tests |

On Linux, speech requires a system speech engine such as eSpeak NG; MIDI needs an available ALSA sequencer. A headless container may have neither. On Windows/macOS, speech uses the installed system voice. Camera and MIDI also require OS device access and permissions. Missing devices or dependencies produce an error rather than silently pretending the test succeeded.

## Understand the four modules

| Module | What works now | Later |
| --- | --- | --- |
| `ada_piano/camera` | Independent timed webcam capture check, optional preview | MediaPipe hand landmarks, keyboard calibration |
| `ada_piano/music_sheet` | Validated JSON exercise → ordered MIDI notes | MusicXML import; scanned score recognition is stretch work |
| `ada_piano/sound_sensor` | Simulated notes, real MIDI input, independent monitor | Optional microphone input and pitch estimation |
| `ada_piano/ai_tutor` | Compare the next note, correct higher/lower, optional speech | Hand-position context and AI-generated explanations |

Music Sheet supplies the expected notes. Sound sensor supplies played notes. Tutor compares them, advances only on a correct note, and sends text or speech feedback. Camera is deliberately tested separately before it contributes hand-position observations.

The current tutor is rule based, not an AI model. It evaluates single notes in sequence, not timing, chords, fingering, or posture. MIDI captures note events, not audio. The camera check does not yet detect hands. Speech currently blocks while each prompt is spoken: use slow, one-note-at-a-time practice. Continuous real-time feedback needs a bounded speech queue and handling for notes received during speech.

## Test each part separately

```sh
uv run python -m ada_piano sheet
uv run --extra camera python -m ada_piano camera --seconds 5
uv run --extra midi python -m ada_piano midi-ports
uv run --extra midi python -m ada_piano midi-monitor --port "EXACT INPUT NAME"
uv run --extra hardware python -m ada_piano practice --port "EXACT INPUT NAME" --speak
```

The camera command prints its result without requiring a visual window. Add `--preview` for a sighted setup helper; use `--index 1` for another webcam. Press Control C to stop monitoring or practice. CLI text works with a terminal screen reader; screen-reader usability still needs testing with a learner.

## Connect the Yamaha YPT-300

Use a USB-to-MIDI interface with 5-pin DIN connectors. Connect the keyboard's **MIDI OUT** to the interface's **MIDI IN**, and USB to the computer. Follow the interface manufacturer's labeling and driver instructions. The return MIDI cable is unnecessary for receiving played notes. MIDI does not send piano audio to the computer; the keyboard can continue making its own sound.

No separate digital audio workstation is required for this prototype: Mido and python-rtmidi are the MIDI software. A device driver may still be required for your interface. List the ports before opening practice mode.

## Change the exercise

Copy `ada_piano/exercises/five_notes.json`, edit its title and notes, then run:

```sh
uv run python -m ada_piano demo --exercise my_exercise.json --notes 60 62 64
```

Each note is an integer from 0–127; this project names MIDI 60 as C4 (middle C). At least one note is required. Sharps are spelled out in feedback for speech.

See [PLAN.md](PLAN.md) for the delivery order and acceptance checks.

## References

- [Yamaha YPT-300 / PSR-E303 manual](https://data.yamaha.com/download/files/2091886): computer and MIDI connection.
- [Mido RtMidi backend](https://mido.readthedocs.io/en/stable/backends/rtmidi.html): MIDI input setup.
- [OpenCV camera capture](https://docs.opencv.org/4.x/dd/d43/tutorial_py_video_display.html): capture and cleanup.
- [pyttsx3 engine](https://pyttsx3.readthedocs.io/en/latest/engine.html): local speech.
- [MediaPipe Python setup](https://developers.google.com/edge/mediapipe/solutions/setup_python): future hand-tracking dependency.
# ADACVA
