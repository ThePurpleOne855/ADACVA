# ADA Piano Teacher

The **Scores · import & practice** tab supports local PDF conversion through
Audiveris, MusicXML review, approved-passage playback, and live pitch/chord
practice. See the [PDF import workflow](docs/SCORE_IMPORT.md) for setup and the
[MusicXML guide](docs/MUSICXML.md) for supported notation and limits.

Accessible Piano Learning Assistant: a Python hackathon prototype for blind and visually impaired learners.

## ADA AI Coach

The language model does not determine which notes were played. MIDI and the
deterministic evaluator provide performance facts; ADA uses those facts for
coaching and practice decisions. Local pitch/chord practice works offline and
does not require an OpenAI account. The optional coach uses the OpenAI Responses
API with a small allowlisted tool surface; it is not an autonomous teacher.

```sh
uv sync --locked --all-extras
# Set OPENAI_API_KEY securely in your shell or secret manager; never commit it.
export ADA_OPENAI_MODEL=gpt-4.1-mini
uv run --locked --all-extras python -m ada_piano note-reader
```

On PowerShell use `$env:ADA_OPENAI_MODEL = 'gpt-4.1-mini'`; supply
`OPENAI_API_KEY` privately through your environment. Missing credentials or SDK,
network failures, and model errors leave MIDI and local practice available.
API use requires a funded API account separately from a ChatGPT subscription.

1. In **Scores · import & practice**, load, review and approve a short passage.
2. Connect MIDI input and practice it. Attempts record structured pitch/chord
   results in memory, including repeats and measured chord attack spread.
3. In **ADA Coach**, type “What should I work on?” and press **Ask ADA** or Enter.
4. Ask to hear a specific approved measure. Confirm the playback request,
   select a MIDI output in Audible reference, and keep the Yamaha audible.
   ADA can queue targeted practice after the reference finishes.

**Speak responses** is off by default. Speech runs in a cancellable background
worker: Linux uses `espeak-ng`, macOS `say`, Windows PowerShell/System.Speech.
No Python TTS package is needed; the `speech` extra remains a compatibility
alias. Missing or failed speech falls back to visible text. Reference playback
waits for its announcement; practice waits for “Your turn.” **Stop** cancels
pending coach actions, speech and reference sound without disconnecting MIDI.

**Save latest attempt** exports JSON through a background writer. Attempts are
not automatically persisted; reopening the app does not restore a practice
session. Exported attempts include approved score identity, passage, monotonic
times, results, summary and coaching history, but not raw camera/MIDI streams.
Only sanitized approved score context and deterministic summaries are sent to
OpenAI, together with your question and at most three recent exchanges. Local
file paths and raw video/landmarks are excluded. Responses use `store=False`;
your API account's data policies still apply.

Limitations: guided pitch/chord attacks only, not rhythm grading, pedal grading
or inferred fingering. MIDI timing currently reflects GUI polling. Calibrated
camera/finger-to-key evidence is unavailable. Model prose can still be wrong;
the local evaluator remains authoritative. Tool actions are validated locally,
cannot approve scores or load files, and cannot send arbitrary MIDI. Physical
speech, Yamaha output and a live API request require local validation. No
microphone or always-listening functionality is included.

## Automated checks

GitHub Actions runs the tests on pull requests and pushes to `main`, using
Python 3.11 and 3.12 on Windows and Linux. It also checks installation, the CLI,
and the packaged exercise files. Only the core package is installed; physical
camera, MIDI and speech-device checks still need local testing. Before merging,
check that all four jobs in the PR's Checks tab are green. Requiring these
checks before merge is a separate repository branch-protection setting.

## Start here (2 minutes once dependencies are available)

### Combined camera and piano window

From the repository root, run:

```sh
uv run --locked --extra camera --extra midi python -m ada_piano note-reader
```

The MIDI reader, virtual keyboard, and audible-reference controls appear on the left;
the hand-tracking camera preview appears on the right. Drag the divider to resize
the panels. Select the MIDI input, choose a **Camera source**, and click
**Start camera**. To switch between the built-in and external camera while
tracking, choose the other source in the dropdown. The app releases the previous
camera before opening the selected one; MIDI input and playback keep running.
**Stop camera** also cancels a pending switch.

The source field is editable and defaults to `0`. You can also type `2`,
`/dev/video2`, or another OpenCV-compatible string and click **Switch camera**
(or **Start camera** when stopped).

After plugging in a USB camera, click **Refresh cameras**. On Linux, the dropdown
shows device names supplied by the operating system (with their camera numbers).
On other systems, or when no devices are listed, it offers numbered camera
choices. Camera 0 is often the built-in camera, but numbering and device type
are not guaranteed: use the preview to identify each. Listed Linux devices may
include additional endpoints that cannot capture video; select another source
if opening one fails. Refreshing the list does not open cameras or interrupt
the current stream. Refresh also preserves a manually entered source.

The camera marks base knuckles in blue, middle joints in orange, and fingertips
in green, with text labels and connected finger segments. The thumb's middle
joint is labeled IP. The camera starts only when requested and needs the root
`hand_landmarker.task` model file. **Stop camera** leaves MIDI input and playback
running. Closing the window stops camera capture and MIDI playback. Camera
capture and inference run in a background thread, retaining only the latest
preview so a slow camera does not block the MIDI controls. A camera failure is
shown in its panel without disconnecting the piano.

Inference and preview are unmirrored, preserving the camera's left-to-right
view (mount it so physical low notes appear on the left). Each processed
`CameraFrame` retains `captured_at_ns`, sampled from `time.monotonic_ns()`
immediately after `read()`, plus immutable normalized `hand_landmarks` (x/y/z)
in that same unmirrored image coordinate system. Divide nanoseconds by 1e9 to
compare with MIDI's monotonic seconds. This is host acquisition time, not the
sensor's exposure time; driver/phone buffering can add latency. MediaPipe uses
a separate strictly increasing millisecond timestamp derived from acquisition
time. Camera observations are not proof of a key press: MIDI remains authoritative
for actual note events. No keyboard calibration or fingering grading is added.

### Using an iPhone as the camera

ADACVA does not communicate directly with iOS. First expose the iPhone to the
operating system as a webcam, for example through DroidCam/V4L2 on Linux.
ADACVA then opens the resulting `/dev/videoN` source through OpenCV; it does
not implement DroidCam, WebRTC, RTSP servers, or custom phone networking.

Find the device and run the existing capture-only check:

```sh
v4l2-ctl --list-devices
uv run --locked --extra camera python -m ada_piano camera --source /dev/video2 --seconds 10 --preview
```

For MediaPipe tracking, run the combined window and enter `/dev/video2` in
**Camera source**, then click **Start camera**:

```sh
uv run --locked --extra camera --extra midi python -m ada_piano note-reader
```

Integer sources still work: `camera --source 0` is the default, and `--index 0`
remains a compatibility alias. Do not combine `--index` and `--source`.
OpenCV-compatible string/URL sources can also be entered, but their actual
support depends on the installed OpenCV backend. The iPhone's ultrawide camera,
if available through the webcam software, may help fit the full Yamaha YPT-300
keyboard. Phone/device permissions, lens selection, latency, field of view and
left-to-right orientation need physical validation. Camera geometry and key
calibration are future work; landmarks do not establish which key was pressed.

For a local integration check (about 2 minutes):

1. Start the camera and move your fingers; check the knuckle and fingertip markers.
2. Play a piano key; check that the virtual keyboard updates alongside the video.
3. Use **Audible reference** to play a short sequence; check that the preview continues.
4. Select the external camera, then switch back; MIDI should remain connected.
5. Close the window; confirm the camera is released and playback stops.

Without a MIDI interface, add `--demo` to simulate input while testing the real
camera. This integration shares a window; it does not yet map fingers to piano
keys or grade fingering. Native camera drivers may delay shutdown while a
capture call finishes; the GUI does not wait indefinitely on a stalled driver.

### Command-line demo

After installing [uv](https://docs.astral.sh/uv/getting-started/installation/), run the simulated demo. It needs no piano, camera, or API key:

```sh
uv run --locked python -m ada_piano demo
```

uv manages Python and the local `.venv` automatically; no environment activation is needed. The first run needs network access to resolve packages and install the project. The demo plays simulated MIDI numbers `60, 61, 62, 64, 65, 67`: C, an intentionally wrong C sharp, then D, E, F, G. The tutor corrects the mistake and finishes the exercise. This is text output; enable local speech after installing its dependencies.

## Set up dependencies (5–10 minutes)

1. Check uv is available: `uv --version`.
2. Install camera, MIDI, and AI coach dependencies: `uv sync --locked --all-extras`.
3. Run checks: `uv run python -m unittest discover -s tests -v`.
4. Try speech: `uv run --extra speech python -m ada_piano demo --speak`.

Use `uv sync` for the base project, or select individual extras with `uv sync --extra camera`, `uv sync --extra midi`, or `uv sync --extra speech`. The base application has no external runtime dependencies. `.python-version` selects Python 3.12 for development; the package still supports Python 3.11+. uv can download the selected interpreter if needed. Native dependencies still require validation on the demo operating system.

The `hardware` extra combines `camera`, `midi`, and `speech`, so each Python dependency is declared only once. Add `--extra agent` for the AI coach, or use `--all-extras` for everything. The `speech` extra remains available for compatibility but installs no Python packages; speech uses native system commands. To launch with all features, run `uv run --locked --all-extras python -m ada_piano note-reader`.

### Dependency workflow

Use uv exclusively for Python installation, dependency management, application commands, and tests, locally and in CI. `pyproject.toml` remains the dependency source, and setuptools remains the build backend invoked by uv. Do not install packages with pip or maintain a separate virtual environment. See the [uv project guide](https://docs.astral.sh/uv/guides/projects/).

- Add a dependency with `uv add PACKAGE`; use `uv add --optional camera PACKAGE` for an optional camera dependency.
- Generate or refresh the lockfile with `uv lock`. Commit `uv.lock` alongside dependency changes.
- Once the lockfile exists, reproduce the hardware environment with `uv sync --locked --extra hardware`.
- Upgrade one dependency deliberately with `uv lock --upgrade-package PACKAGE`.

`uv.lock` is committed. Use `--locked` to keep installations consistent with it; a first installation still needs network access unless the packages are cached.

After the initial setup, run an offline core demo with `uv run --offline --no-sync python -m ada_piano demo`. This uses the existing uv environment without changing dependencies; it does not verify hardware devices.

| Dependency | Purpose |
| --- | --- |
| OpenCV | Capture webcam frames |
| MediaPipe | Hand landmark detection (included in camera and hardware extras; integration in progress) |
| Mido + python-rtmidi | Receive key events through a USB-to-MIDI interface |
| OpenAI SDK (`agent` extra) | Optional AI coach |
| Native system speech | Speak feedback locally without a Python speech dependency |
| Python standard library | Exercises, tutor logic, CLI, tests |

On Linux, speech requires a system speech engine such as eSpeak NG; MIDI needs an available ALSA sequencer. A headless container may have neither. On Windows/macOS, speech uses the installed system voice. Camera and MIDI also require OS device access and permissions. Missing devices or dependencies produce an error rather than silently pretending the test succeeded.

Audiveris for PDF recognition, DroidCam and its loopback driver for a phone webcam, and the Linux speech engine are separate system installations; uv does not install them.

Linux voice input uses `pw-record` (PipeWire) or `arecord` (`alsa-utils`) and OpenAI transcription. Spoken replies use `pw-play` or `aplay`; no additional audio Python package is required. If PipeWire tools are already installed, no system installation is needed for cloud voice. The optional local voice uses `espeak-ng`. For ALSA/local speech on Arch Linux, use `sudo pacman -S --needed alsa-utils espeak-ng`; on Debian/Ubuntu, use `sudo apt install alsa-utils espeak-ng`. Python dependencies use uv only.

To talk with ADA on Linux, launch `uv run --locked --all-extras --env-file .env python -m ada_piano.agent`, enable **Speak responses** and **Hands-free: say “ADA …”**, then say “ADA, how do I find middle C?” and pause. Linux listening uploads short audio clips to OpenAI for transcription and incurs API charges. Set `ADA_MIC_TARGET` in `.env` to a PipeWire source name if the default input is wrong; ALSA users can set `ADA_ALSA_DEVICE` instead. See [voice setup](ada_piano/agent/USAGE.md).

## Note Reader GUI (2–5 minutes)

Start the independent Note Reader test panel:

```sh
uv run --locked --extra midi python -m ada_piano note-reader
```

1. Connect the YPT-300 **MIDI OUT** to the USB interface's **MIDI IN**, then plug the interface into your computer.
2. The app connects automatically when there is one input other than **Midi Through**. Otherwise click **Refresh inputs**, select the USB interface, and click **Connect**. The mioXC is preferred in the selector; its name appears instead of “Yamaha.” **Midi Through** is a software routing port, not the keyboard.
3. Play individual notes and chords. A labeled **61-key virtual piano** lights held keys green and marks the last played note with a blue outline. The panel also shows note names, MIDI numbers, velocity, channels (1–16), sustain status, and the last 500 note events. The displayed range starts at C2–C7 and shifts for transposed notes outside that range.
4. Release the keys and confirm the held-key list clears. Both `note_off` and zero-velocity `note_on` messages count as releases. Sustain is separate: held keys represent physical presses, not sustained sound.
5. Click **Disconnect / Stop** or close the window to release the MIDI port. After unplugging/reconnecting, click **Refresh inputs** and **Connect** again.

For a hardware-free test, click **Demo**, or launch directly with:

```sh
uv run --locked python -m ada_piano note-reader --demo
```

Demo simulates a C4–E4–G4 chord, both release formats, and sustain. It does not play audio or verify your cable. **Clear log** clears event history only; reconnecting or restarting Demo resets the session count. The window uses Tkinter; on Arch Linux, install `tk` if Tkinter is missing (`sudo pacman -S tk`). A graphical desktop is required. If Linux reports that the ALSA sequencer is unavailable, verify that `/dev/snd/seq` exists on the host and that the app has device access; containers may not expose MIDI devices.

The **Duration (s)** column shows how long each key was held on its **OFF** row, to three decimal places. Timing is tracked separately per note and MIDI channel, from press to release, and does not include sustain-pedal time. ON rows and releases without a recorded press show `—`. Clearing the log preserves timing for held keys; disconnecting or resetting clears it. A repeated press on the same note/channel restarts its timer. Measurements use the app's monotonic clock and are approximate at the GUI's 20 ms polling interval.

The reusable `ada_piano.note_reader.NoteReader` uses Mido's explicit RtMidi backend and nonblocking polling. It is independent of the existing tutor and sound sensor API. Automated tests cover MIDI state and desktop GUI behavior; a separate virtual-port test verified real RtMidi events reaching the virtual keyboard. Live input from the YPT-300 through the mioXC was confirmed by the user on 2026-10-10. Screen-reader usability still requires testing with a learner.

### Connected but no keys light up

The **MIDI activity** line distinguishes an open USB interface from received note data. After five seconds without any note presses, it displays a connection checklist. Its message count includes non-note messages delivered by Mido (for example pedal and clock messages); the RtMidi backend filters active sensing.

1. Confirm the listening input is **mioXC**, not **Midi Through**. Connect keyboard **MIDI OUT** to interface **MIDI IN**. Keep USB connected: the mioXC requires USB power and does not act as a passive MIDI cable with USB unplugged.
2. On the YPT-300, set **PC mode to OFF** and **Local Control ON** if you want to hear the piano's own speakers. **PC1 disables Keyboard Out**; PC mode OFF enables it. PC2 also enables Keyboard Out but disables local sound. Local sound alone does not prove MIDI transmission. See the [Yamaha manual, pages 59–60](https://data.yamaha.com/download/files/2091886).
3. Play several keys and watch the message count. If it stays at zero, the app has not received MIDI data: check the cable, piano power, and PC mode. **Demo** tests the visual keyboard independently of that connection.

### Audible reference (1 minute)

1. Keep USB connected. Connect **mioXC MIDI OUT → Yamaha MIDI IN** and make the Yamaha speaker volume audible. The opposite cable direction is used for reading your playing.
2. Open the **Audible reference** tab in Note Reader. Choose the mioXC under **MIDI output** (use **Refresh outputs** after reconnecting).
3. Enter `C4` and click **Play note**, or click a key on the virtual keyboard. Notes also accept MIDI numbers such as `60`, sharps (`F#4`), and flats (`Bb3`). Each click plays one note for the selected beat duration; stop the current reference before starting another.
4. Enter a space- or comma-separated sequence such as `C4 D4 E4 F4 G4` and click **Play sequence**. Adjust tempo, beats per note, velocity, and MIDI channel as needed.
5. Use **Stop sound** to interrupt playback. Closing the window or choosing **Disconnect / Stop** also stops the output worker and releases playback notes.

Blue-filled keys are reference notes; green keys are notes received from your keyboard. Outgoing reference events appear in the log with **Source = Reference** and do not directly update the input note count. Real input continues to be read and is never automatically echoed to output. The offline **Demo** remains simulated; use the reference controls for actual sound. The engine selects General MIDI program 0 (piano) and turns sustain off on the chosen channels for reference playback. A completion message confirms MIDI was sent, not that speakers produced audible sound.

### Reusable playback API for AI and score modules

`ada_piano.playback.ReferencePlayer` runs without Tkinter and accepts a validated, JSON-compatible request. A future AI adapter can choose a reviewed passage and submit its note plan; the application supplies the output port. Example:

```python
from ada_piano.playback import ReferencePlayer

player = ReferencePlayer()
print(player.list_ports())  # Select the exact Yamaha interface output.
player.play_request(
    {
        "tempo": 90,
        "notes": [
            {"note": 60, "start_beat": 0, "duration_beats": 1},
            {"note": 64, "start_beat": 1, "duration_beats": 1},
            {"note": 67, "start_beat": 2, "duration_beats": 2},
        ],
    },
    port_name="EXACT OUTPUT NAME",
)
# Returns immediately. Keep your application running while the worker plays.
# Read player.status and drain_events() from your UI/controller loop.
# player.stop() cancels; player.close() releases resources on application exit.
```

Typed callers can use `play_notes([PlaybackNote(...)], port_name=..., tempo=...)`. `start_beat` and `duration_beats` use quarter-note beats; equal starts create chords, gaps create rests. Channels are 1–16 and default to 1; velocity defaults to 70. Requests allow only note plans and tempo, not arbitrary MIDI/SysEx. Validation rejects invalid pitches, nonfinite timing, overlapping identical pitch/channel pairs, more than 4096 notes, or references longer than five minutes. Tempo is 20–300 BPM. A second request during playback is rejected until the first stops or finishes.

Playback uses a separate worker and monotonic deadlines. Its bounded event buffer includes actual send timestamps, releases, and `source="reference"`; `status` reports completion, cancellation, or failure. On output failure, cleanup attempts releases before closing the port; a disconnected cable cannot deliver those releases to the instrument. Stop/error handling does not depend on an AI response.

Reviewed MusicXML passages now feed the playback adapter and pitch/chord tutor
from the **Scores** tab. References preserve chords, note durations, ties, and
internal rests at the selected fixed tempo. Score tempo changes, pedal, dynamics,
and fingering are not interpreted. Reference playback pauses practice; start a
new attempt after listening. The approved passage is available as structured
JSON for future agents; no language-model integration is enabled.

## Understand the modules

| Module | What works now | Later |
| --- | --- | --- |
| `ada_piano/camera` | Generic OpenCV sources, capture check, threaded unmirrored MediaPipe preview, timestamped landmarks | Keyboard calibration and finger-to-key mapping |
| `ada_piano/music_sheet` | JSON/MusicXML → timed attack groups, chords, rests; measure selection | Repeat expansion and additional notation |
| `ada_piano/score_import` | Local Audiveris conversion worker, saved outputs/logs, passage review, approval, tutor/agent context | Real Audiveris trial; notation editing and rendering |
| `ada_piano/sound_sensor` | Simulated notes, real MIDI input, independent monitor | Optional microphone input and pitch estimation |
| `ada_piano/note_reader` | Independent MIDI GUI, virtual keyboard, velocity/channel, sustain, simulated demo; live YPT-300 input confirmed | Accessibility validation |
| `ada_piano/playback` | Audible reference GUI, reviewed-score adapter, validated MIDI note plans, fixed tempo, cancellation | AI adapter, score tempo changes and pedal phrasing |
| `ada_piano/ai_tutor` | Single-note/chord practice, held-key matching, optional speech | Rhythm grading, hand-position context |

Music Sheet supplies the expected notes. Sound sensor supplies played notes. Tutor compares them, advances only on a correct note, and sends text or speech feedback. Camera is deliberately tested separately before it contributes hand-position observations.

The local tutor is rule based. It evaluates pitches and chord attacks, not rhythmic accuracy, fingering, or posture. MIDI captures key presses and releases, not audio. Chord notes must be held together and pressed within 150 ms by default (`--chord-window-ms` changes this). This is a simultaneity tolerance, not tempo grading. Camera landmarks are not calibrated fingering evidence. System speech is queued outside capture and GUI threads; hardware and speech latency still require validation.

## Test each part separately

```sh
uv run --locked python -m ada_piano sheet
uv run --locked --extra camera python -m ada_piano camera --seconds 5
uv run --locked --extra midi python -m ada_piano midi-ports
uv run --locked --extra midi python -m ada_piano midi-monitor --port "EXACT INPUT NAME"
uv run --locked --extra hardware python -m ada_piano practice --port "EXACT INPUT NAME" --speak
```

The camera command prints its result without requiring a visual window. Add `--preview` for a sighted setup helper; use `--source 1` (or legacy `--index 1`) for another webcam. Press Control C to stop monitoring or practice. CLI text works with a terminal screen reader; screen-reader usability still needs testing with a learner.

## Connect the Yamaha YPT-300

Use a USB-to-MIDI interface with 5-pin DIN connectors. Connect the keyboard's **MIDI OUT** to the interface's **MIDI IN**, and USB to the computer. Follow the interface manufacturer's labeling and driver instructions. The return MIDI cable is unnecessary for receiving played notes. MIDI does not send piano audio to the computer; the keyboard can continue making its own sound.

No separate digital audio workstation is required for this prototype: Mido and python-rtmidi are the MIDI software. A device driver may still be required for your interface. List the ports before opening practice mode.

## Change the exercise

Copy `ada_piano/exercises/five_notes.json`, edit its title and notes, then run:

```sh
uv run --locked python -m ada_piano demo --exercise my_exercise.json --notes 60 62 64
```

Each note is an integer from 0–127; this project names MIDI 60 as C4 (middle C). At least one note is required. Sharps are spelled out in feedback for speech.

For chords, use a nested list such as `"notes": [[60, 64, 67], [62, 65, 69]]`.
Try the included example without hardware:

```sh
uv run --locked --all-extras python -m ada_piano demo --exercise ada_piano/exercises/two_chords.json --chords 60+64+67 62+65+69
```

See [PLAN.md](PLAN.md) for the delivery order and acceptance checks.

## References

- [Yamaha YPT-300 / PSR-E303 manual](https://data.yamaha.com/download/files/2091886): computer and MIDI connection.
- [Mido RtMidi backend](https://mido.readthedocs.io/en/stable/backends/rtmidi.html): MIDI input setup.
- [OpenCV camera capture](https://docs.opencv.org/4.x/dd/d43/tutorial_py_video_display.html): capture and cleanup.
- [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling): optional bounded coaching tools.
- [MediaPipe Python setup](https://developers.google.com/edge/mediapipe/solutions/setup_python): future hand-tracking dependency.
# ADACVA
