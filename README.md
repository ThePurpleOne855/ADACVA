# ADA Piano Teacher

Accessible Piano Learning Assistant: a Python hackathon prototype for blind and visually impaired learners.

## Camera work in progress

The runnable camera tracker and its overhead-mount plan are in [docs/CAMERA.md](docs/CAMERA.md).
It detects and overlays two hands from a USB webcam, or from a still image.
Key calibration, key-press attribution, and MIDI integration are next steps.

## Start here (2 minutes once dependencies are available)

The simulated demo needs Python 3.11+ and no third-party packages, piano, camera, or API key:

```sh
python -m ada_piano demo
```

Use `python3` if your system does not have a `python` command. The demo plays simulated MIDI numbers `60, 61, 62, 64, 65, 67`: C, an intentionally wrong C sharp, then D, E, F, G. The tutor corrects the mistake and finishes the exercise. This is text output; enable local speech after installing its dependencies.

## Set up dependencies (5–10 minutes)

1. Create a local environment: `python -m venv .venv`.
2. Activate it: macOS/Linux `source .venv/bin/activate`; Windows PowerShell `.venv\Scripts\Activate.ps1`.
3. Install: `python -m pip install -e ".[hardware]"`.
4. Run checks: `python -m unittest discover -s tests -v`.
5. Try speech: `python -m ada_piano demo --speak`.

Optional groups let you install one input at a time: `.[camera]`, `.[midi]`, or `.[speech]`. The base application has no external runtime dependencies. Python 3.11 or 3.12 is a conservative starting choice for future computer-vision additions; native package availability depends on your operating system and Python version.

| Dependency | Purpose |
| --- | --- |
| OpenCV + MediaPipe | Capture webcam frames and track hand landmarks |
| Mido + python-rtmidi | Receive key events through a USB-to-MIDI interface |
| pyttsx3 | Speak feedback locally using a system voice |
| Python standard library | Exercises, tutor logic, CLI, tests |

On Linux, speech requires a system speech engine such as eSpeak NG; MIDI needs an available ALSA sequencer. A headless container may have neither. On Windows/macOS, speech uses the installed system voice. Camera and MIDI also require OS device access and permissions. Missing devices or dependencies produce an error rather than silently pretending the test succeeded.

## Understand the four modules

| Module | What works now | Later |
| --- | --- | --- |
| `ada_piano/camera` | Independent capture check; separate two-hand landmark tracker | Keyboard calibration and MIDI-aligned fingering |
| `ada_piano/music_sheet` | Validated JSON exercise → ordered MIDI notes | MusicXML import; scanned score recognition is stretch work |
| `ada_piano/sound_sensor` | Simulated notes, real MIDI input, independent monitor | Optional microphone input and pitch estimation |
| `ada_piano/ai_tutor` | Compare the next note, correct higher/lower, optional speech | Hand-position context and AI-generated explanations |

Music Sheet supplies the expected notes. Sound sensor supplies played notes. Tutor compares them, advances only on a correct note, and sends text or speech feedback. Camera is deliberately tested separately before it contributes hand-position observations.

The current tutor is rule based, not an AI model. It evaluates single notes in sequence, not timing, chords, fingering, or posture. MIDI captures note events, not audio. The separate camera tracker detects hands but does not yet associate them with keys or notes. Speech currently blocks while each prompt is spoken: use slow, one-note-at-a-time practice. Continuous real-time feedback needs a bounded speech queue and handling for notes received during speech.

## Test each part separately

```sh
python -m ada_piano sheet
python -m ada_piano camera --seconds 5
python -m ada_piano midi-ports
python -m ada_piano midi-monitor --port "EXACT INPUT NAME"
python -m ada_piano practice --port "EXACT INPUT NAME" --speak
```

The camera command prints its result without requiring a visual window. Add `--preview` for a sighted setup helper; use `--index 1` for another webcam. Press Control C to stop monitoring or practice. CLI text works with a terminal screen reader; screen-reader usability still needs testing with a learner.

## Connect the Yamaha YPT-300

Use a USB-to-MIDI interface with 5-pin DIN connectors. Connect the keyboard's **MIDI OUT** to the interface's **MIDI IN**, and USB to the computer. Follow the interface manufacturer's labeling and driver instructions. The return MIDI cable is unnecessary for receiving played notes. MIDI does not send piano audio to the computer; the keyboard can continue making its own sound.

No separate digital audio workstation is required for this prototype: Mido and python-rtmidi are the MIDI software. A device driver may still be required for your interface. List the ports before opening practice mode.

## Change the exercise

Copy `ada_piano/exercises/five_notes.json`, edit its title and notes, then run:

```sh
python -m ada_piano demo --exercise my_exercise.json --notes 60 62 64
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
