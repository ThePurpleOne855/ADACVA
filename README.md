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

An OpenAI API key is optional. Enter it in **API settings** under Tools (F3), or set `OPENAI_API_KEY` in the app's environment. Cloud coaching, speech, and transcription can incur API charges when used. For natural offline speech, run `uv run --locked --all-extras ada-piano voice-setup` once. Say “use natural offline voice” or “use system voice” to select local speech. F1 starts/retries conversation; Escape stops practice, sound, and calibration.

## Project limitations

### Accessibility and hardware

This is a prototype. Screen-reader compatibility and independent use by blind learners are not yet validated. Real camera calibration, microphone interruption while the piano/speakers are sounding, audible MIDI output, and Audiveris recognition need hardware trials. Automated checks use fake devices and synthetic observations; passing them does not establish hardware or accessibility readiness. CI targets Linux and Windows with Python 3.11 and 3.12; desktop GUI checks require Tk and a display.

### Score import and reference playback

PDF recognition requires a separate Audiveris installation; installing Python dependencies does not install it. Recognized music must be checked against a trusted source and explicitly approved before practice. The preview is a note/rest table, not rendered sheet music, and corrections require an external score editor. Direct photo import is not implemented. Original imports and conversion diagnostics remain in the working directory's `scores/` folder, including after failure or cancellation.

Only partwise MusicXML is supported, with one selected instrument part at a time. Written-order mode plays repeat signs and alternate endings once in printed order; it does not expand them. Transposing parts, playback jumps, measure repeats, and microtonal pitches are rejected. XML documents are limited to 16 MiB.

References use a single fixed tempo and do not interpret score tempo changes, pedal, dynamics, or fingering. Playback is limited to 4,096 notes and five minutes at the selected tempo. Overlapping notes of the same pitch/channel are rejected. A completed playback status means MIDI scheduling finished; it does not confirm audible piano output. Use the main **Stop** button or Escape to cancel an announced reference before it starts.

### Performance feedback

Guided practice checks note/chord attacks, not written rhythm. Play-through timing is measured against the learner's fitted tempo. MIDI captures key presses and releases, not piano audio; key-held duration is not audible duration under sustain. ADA does not grade pedal, dynamics, articulation, fingering, or posture.

Play-through comparison accepts at most 600 expected notes. A take retains at most 1,200 played notes; additional note attacks are not recorded. Detailed problem reports cover at most 16 measures and five examples per category per measure. A take ends after about four seconds without MIDI activity once all keys are released, so a long pause can end it before the piece is finished. Use short passages for practice.

### Camera setup and observations

The camera adds fingertip proximity evidence, not proof of which finger pressed a key or whether technique is correct. It requires visible hands and a fixed camera and piano. To calibrate, say “start camera,” then “calibrate hands” for the right hand or “calibrate left hand.” Keep only that hand visible and use the same index finger to press three separated white keys spanning at least an octave, holding still for half a second and releasing between keys. Then press two separated black keys spanning at least seven semitones, or say “finish calibration” for white keys only.

Only keys between each color's calibration anchors and near its fitted contact line are covered; this is not a full perspective model of the keyboard. Missing, stale, occluded, ambiguous, and out-of-range observations remain unknown. Camera timestamps reflect host acquisition; network-camera buffering is not compensated. Moving the camera or piano requires recalibration; physical movement is not detected automatically. Stopping, switching, or losing the camera clears calibration, and calibration is not restored after restart.

Hand analysis covers at most 1,200 MIDI attacks and retains at most 24 detailed associations per take. Practice sessions do not save camera frames or raw landmarks. The separate standalone tracker can export landmarks when explicitly requested. Its MediaPipe model, `hand_landmarker.task`, is included in the repository; use `python -m ada_piano.camera --model /path/to/hand_landmarker.task` to select another copy.

### Voice, AI, and saved sessions

Microphone recognition is implemented on Linux and Windows, not macOS. Linux requires PipeWire `pw-record` or ALSA `arecord`, plus local faster-whisper or an API key for cloud transcription. Windows requires an installed English System.Speech recognizer. Offline voices and recognition models need initial downloads. Speech commands do not provide acoustic echo cancellation, and “ADA stop” depends on recognition latency; Escape provides an immediate keyboard stop. Say “stop listening” to disable the microphone.

With an API key configured, Linux microphone clips may be sent for transcription before the wake prefix is checked, including background speech that does not trigger a reply. Cloud speech sends reply text, and coaching sends approved score context and measured summaries. Cancelled requests may already have incurred charges. AI advice is not independent evidence of what the learner played; core practice and local commands work without AI after local dependencies and models are installed.

Sessions save as local JSON, but there is no session browser or automatic resume after reopening. “Replay” uses the latest play-through still in memory. Default export locations are:

| Platform | Session folder |
| --- | --- |
| Linux | `$XDG_DATA_HOME/ada-piano/sessions`, defaulting to `~/.local/share/ada-piano/sessions` |
| Windows | `%LOCALAPPDATA%/ada-piano/sessions` |
| macOS | `~/Library/Application Support/ada-piano/sessions` |
