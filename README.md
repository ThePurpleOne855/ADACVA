# ADA Piano Teacher

**Status: working prototype.** ADA helps blind and low vision learners practice piano without relying on a printed score or visual keyboard cues. It loads a reviewed passage, listens to a MIDI keyboard, and gives spoken or on-screen feedback about what the learner played.

## What works now

| Area | Current behavior |
| --- | --- |
| Practice without hardware | A command-line demo runs a five-note exercise with simulated input. The desktop window also has a simulated MIDI display. |
| Practice with a MIDI piano | The desktop app shows played keys and supports guided note and chord practice. A free play-through reports wrong, missed, and extra notes by measure, plus timing, hesitations, and short key holds. Yamaha YPT-300 input has been confirmed. |
| Scores and reference sound | ADA includes checked passages from *Für Elise* and *Ode to Joy*. It can read MusicXML, review a selected passage, and send a fixed-tempo reference to a MIDI output. PDF import uses a separate Audiveris installation and requires manual review of its recognition result. |
| Voice and coaching | Common commands such as “practice Ode to Joy,” “record,” and “how did I do?” work without an API key. Optional OpenAI coaching can explain measured results and answer broader questions. Speech output and microphone input are available where their local dependencies or services are set up. |
| Camera | An optional camera preview tracks hand landmarks. It does not yet identify which piano key a finger presses. |

The software paths have automated checks. Live piano input has been confirmed on a YPT-300; audible output through its speakers, voice devices, PDF recognition quality, and screen-reader use with a learner still need hands-on validation.

## Try it

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then run the hardware-free text demo from the repository root:

```sh
uv run --locked python -m ada_piano demo
```

For the desktop app, use a graphical desktop with Tkinter and run:

```sh
uv run --locked --all-extras python -m ada_piano note-reader
```

The first run downloads Python dependencies. To practice on a piano, connect **piano MIDI OUT → interface MIDI IN → computer USB**, then select the MIDI input. Connect **interface MIDI OUT → piano MIDI IN** too if you want to hear reference playback through the piano. In the ADA Coach tab, type “practice Ode to Joy,” then “record”; play and pause for about four seconds to hear the report. F1 opens speech input or focuses the text box, F5 records, F6 requests results, and Esc stops.

An OpenAI API key is optional for local practice. For a natural offline speaking voice, run `uv run --locked --all-extras ada-piano voice-setup` once. See [voice-first practice](docs/ACCESSIBLE_PRACTICE.md) for microphone setup and the full keyboard controls.

## Current limits

- The camera sees hand joints but is not calibrated to piano keys; ADA cannot grade fingering or posture.
- Feedback covers MIDI pitches and selected timing measures. It does not grade pedal, dynamics, articulation, or sound recorded by a microphone.
- MusicXML support covers a subset of notation. PDF conversion depends on Audiveris, and recognized notes must be checked before practice.
- Guided attempts can be exported manually. Play-through reports stay in memory, and sessions are not restored when the app reopens.

## More detail

- [Voice-first practice and checked pieces](docs/ACCESSIBLE_PRACTICE.md)
- [PDF and MusicXML import](docs/SCORE_IMPORT.md) · [supported notation](docs/MUSICXML.md)
- [Camera setup and limits](docs/CAMERA.md)
- [Standalone ADA chat and voice setup](ada_piano/agent/USAGE.md)
