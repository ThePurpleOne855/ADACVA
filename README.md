# ADA Piano Teacher

**ADA is an accessible piano practice prototype for blind and low vision learners.** Printed scores and visual keyboard cues make independent practice difficult, and a learner playing alone gets little specific feedback. ADA brings a reviewed score, MIDI keyboard input, audible examples, and spoken or text feedback into one practice window. An optional camera is being developed for future hand guidance.

## A practice session

1. **Choose music:** load a checked passage from *Für Elise* or *Ode to Joy*, or import and review a MusicXML score. PDF conversion is available through Audiveris.
2. **Listen:** play the passage on a connected MIDI instrument at a chosen fixed tempo, or hear individual notes and short sequences.
3. **Play:** use guided practice for immediate note and chord feedback, or record an uninterrupted play-through.
4. **Review:** after a play-through, hear or read a measure-by-measure report, replay your performance, and ask the optional ADA Coach what to work on next.

MIDI tells ADA which keys were played. The camera can show hand landmarks alongside practice, but it does not currently identify which finger pressed a key.

## What works today

### Music and practice

| Feature | Current behavior |
| --- | --- |
| Checked music | The built-in catalog has passages from *Für Elise* (both, right, or left hand) and *Ode to Joy* (right hand). These can be loaded by name without reviewing a file first. |
| Import and review | Read `.musicxml`, `.xml`, and `.mxl`; select a part, staff, voice, and measure range; preview notes and rests; approve a passage before playback or practice. A separate Audiveris installation can convert PDFs, retaining its output and diagnostics. New imports need manual review; the import controls currently need a sighted check. |
| MIDI reader and reference | A virtual keyboard shows held notes, velocity, channel, sustain, and key-hold duration. Select a MIDI output to play a note, sequence, or approved passage; outgoing reference notes are kept separate from learner input. |
| Guided practice | The local tutor waits for the expected note or chord and gives immediate pitch feedback. It works without an API key and does not grade written rhythm. |
| Play-through report | ADA records MIDI without interrupting the learner, then reports wrong, missed, and extra notes by measure. It also estimates the learner's tempo and flags early or late attacks, hesitations, and short key holds. |

### Interaction and supporting tools

| Feature | Current behavior |
| --- | --- |
| Voice-first controls | The app opens on ADA Coach. Type or say commands such as “practice Ode to Joy,” “play it for me,” “record,” “replay,” and “how did I do?” Local commands and feedback work without OpenAI. F1 talks or focuses the message box; F5 records, F6 gives results, F7 toggles the camera, and Esc stops. |
| Speech | Piper offers an offline voice after one-time setup, with system speech or on-screen text as fallbacks. Linux can recognize speech locally with faster-whisper or through OpenAI; Windows uses local System.Speech. Microphone recognition is not implemented on macOS. |
| Optional AI coach | With an OpenAI API key, ADA can answer piano questions, explain measured results, and request bounded actions on checked or approved music. It sends approved score context and local summaries, not raw camera data. The local MIDI evaluator supplies the performance facts. |
| Camera | The combined window can preview a webcam or compatible phone camera and mark hand joints. A separate tracker can inspect a still image or save timestamped landmarks. Camera data is not used to grade playing. |
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

- **Software:** automated checks cover the core flows on Linux and Windows with Python 3.11 and 3.12. Live Yamaha YPT-300 MIDI input has been confirmed.
- **Real-world checks:** audible output through the Yamaha speakers, microphone and speech devices, and real Audiveris PDF conversion still need local validation. Screen-reader use needs testing with a learner.
- **Feedback:** MIDI captures key presses, not recorded piano audio. ADA does not grade pedal, dynamics, articulation, fingering, or posture. Timing feedback is relative to the learner's fitted tempo, not a complete interpretation of score tempo changes.
- **Scores and camera:** MusicXML support is intentionally limited, and recognition errors must be corrected outside ADA. The camera is not calibrated to the keys, so finger-to-key guidance remains future work.
- **Sessions:** guided attempts can be exported manually as JSON. Play-through reports remain in memory; practice sessions are not restored after reopening the app.

## Detailed guides

- [Voice-first practice](docs/ACCESSIBLE_PRACTICE.md)
- [PDF and MusicXML import](docs/SCORE_IMPORT.md) and [supported notation](docs/MUSICXML.md)
- [Camera setup and planned calibration](docs/CAMERA.md)
- [Standalone ADA chat and voice setup](ada_piano/agent/USAGE.md)
