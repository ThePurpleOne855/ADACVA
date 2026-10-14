# ADA Piano Teacher

**ADA helps blind and low vision learners practice piano through conversation.** Printed scores and visual keyboard cues make independent practice difficult. ADA connects a reviewed score, your MIDI piano, audible examples, and spoken feedback so you can choose music, play, and find the next thing to practice without using a mouse.

**Status: integrated desktop prototype.** Voice controls, MIDI practice, optional calibrated hand observations, AI coaching, and local session exports are connected. It still needs trials with blind learners and real hardware before it can be called a finished accessible product.

## A practice session

1. **Choose music:** load a checked passage from *Für Elise* or *Ode to Joy*, or import and review a MusicXML score. PDF conversion is available through Audiveris.
2. **Listen:** play the passage on a connected MIDI instrument at a chosen fixed tempo, or hear individual notes and short sequences.
3. **Play:** use guided practice for immediate note and chord feedback, or record an uninterrupted play-through.
4. **Review:** after a play-through, hear or read a measure-by-measure report, replay your performance, and ask the optional ADA Coach what to work on next.

MIDI tells ADA which keys were played. After spoken calibration, an optional camera can associate nearby fingertips with MIDI attacks. Those observations are estimates, not proof of which finger pressed a key or a judgment of correct technique.

## What works today

### Music and practice

| Feature | Current behavior |
| --- | --- |
| Checked music | The built-in catalog has passages from *Für Elise* (both, right, or left hand) and *Ode to Joy* (right hand). These can be loaded by name without reviewing a file first. |
| Import and review | Read `.musicxml`, `.xml`, and `.mxl`; select a part, staff, voice, and measure range; hear notes and rests; explicitly approve a passage before use. Audiveris can convert PDFs. Spoken review is available, but recognition still needs checking against a trusted source; corrections happen in an external score editor. |
| MIDI reader and reference | A virtual keyboard shows held notes, velocity, channel, sustain, and key-hold duration. Select a MIDI output to play a note, sequence, or approved passage; outgoing reference notes are kept separate from learner input. |
| Guided practice | The local tutor waits for the expected note or chord and gives immediate pitch feedback. It works without an API key and does not grade written rhythm. |
| Play-through report | ADA records MIDI without interrupting the learner, then reports wrong, missed, and extra notes by measure. It also estimates the learner's tempo and flags early or late attacks, hesitations, and short key holds. |

### Interaction and supporting tools

| Feature | Current behavior |
| --- | --- |
| Voice controls and simple screen | A quiet ethereal background, Talk/Stop/Tools buttons, message field, and selectable transcript. Voice commands handle practice, device selection, tempo, passage/hand selection, calibration, import review, saving, and quitting. F1 talks, F3 toggles tools, and Esc stops. During speech or playing, say “ADA stop.” Local commands do not need OpenAI. |
| Speech | Piper offers an offline voice after one-time setup, with system speech or on-screen text as fallbacks. Linux can recognize speech locally with faster-whisper or through OpenAI; Windows uses local System.Speech. Microphone recognition is not implemented on macOS. |
| Optional AI coach | With an OpenAI API key, ADA explains measured playing and calibrated hand observations, answers questions, and requests bounded practice or playback actions. It receives approved score context and summaries, never camera images. MIDI supplies the performance facts; missing or ambiguous hand evidence stays unknown. |
| Camera and sessions | Spoken white/black key calibration joins timestamped landmarks to MIDI attacks in a fixed key range. Completed guided and play-through sessions save automatically as local JSON, including hand evidence and subsequent coaching feedback. Camera frames are not saved. A separate tracker supports still images and landmark exports. |
| Independent tools | Command-line modes cover simulated practice, score reading, MIDI port listing and monitoring, live practice, and camera checks. These let each part be tried without the full desktop workflow. |

## Try it

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and run the text demo from the repository root. It needs no piano, camera, or API key:

```sh
uv run --locked python -m ada_piano demo
```

For the full desktop window, use a graphical desktop with Tkinter:

```sh
uv run --locked --all-extras python -m ada_piano note-reader
```

The first run downloads Python dependencies. Connect **piano MIDI OUT → interface MIDI IN → computer USB** to read your playing. For audible reference through the piano, also connect **interface MIDI OUT → piano MIDI IN** and select the MIDI output in the app. Say or type “practice Ode to Joy,” then “record”; play and pause for about four seconds to hear the report. The desktop **Demo** button shows simulated MIDI activity but is not graded as a learner performance.

An OpenAI API key is optional. Cloud coaching, speech, and transcription can incur API charges when used. For natural offline speech, run `uv run --locked --all-extras ada-piano voice-setup` once. The [voice-first guide](docs/ACCESSIBLE_PRACTICE.md) covers microphones, shortcuts, and the checked pieces.

## Current status and limits

- **Software:** automated tests cover local commands, practice, GUI integration, camera/MIDI association, and session writes with fake devices. CI targets Linux and Windows with Python 3.11 and 3.12; GUI checks require Tk and a display.
- **Accessibility and hardware:** this is voice operated, with native keyboard/text fallbacks. Screen-reader compatibility and independent use by blind learners are not yet validated. Real camera calibration, recognition while the piano/speakers are sounding, MIDI output, and Audiveris conversion need hardware trials. Microphone recognition is available on Linux and Windows, not macOS.
- **Feedback:** MIDI captures key presses, not recorded piano audio. ADA does not grade pedal, dynamics, articulation, fingering, or posture. Timing feedback is relative to the learner's fitted tempo, not a complete interpretation of score tempo changes.
- **Scores and camera:** supported notation is limited. Hand analysis requires a fixed camera, visible hands, and calibration; black keys need separate anchors. Stale, occluded, ambiguous, and out-of-range evidence is rejected. Moving the camera or piano requires recalibration; physical movement is not detected automatically.
- **Sessions:** local JSON exports persist, but there is no session browser or automatic resume after reopening. On Linux they are under `$XDG_DATA_HOME/ada-piano/sessions` (default `~/.local/share/ada-piano/sessions`); see the guide for other platforms.

## Detailed guides

- [Voice-first practice](docs/ACCESSIBLE_PRACTICE.md)
- [PDF and MusicXML import](docs/SCORE_IMPORT.md) and [supported notation](docs/MUSICXML.md)
- [Camera setup and calibration](docs/CAMERA.md)
- [Standalone ADA chat and voice setup](ada_piano/agent/USAGE.md)
