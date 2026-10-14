# Practice through voice

ADA opens a minimal practice screen with a static ethereal background, native
Talk/Stop/Tools buttons, a message field, and a selectable conversation transcript.
Speech and conversation are enabled by default. The detailed setup tabs are under
**Tools & settings** or F3. This is an integrated prototype; independent use by blind
learners and screen-reader compatibility still need real-world validation.

## Start a session

```sh
uv sync --locked --all-extras
uv run --locked --all-extras ada-piano voice-setup
uv run --locked --all-extras python -m ada_piano note-reader
```

Run voice-setup once for the natural offline voice. Connect piano MIDI OUT to
interface MIDI IN; for reference sound, connect interface MIDI OUT to piano MIDI IN.
A graphical desktop with Tk is required.

1. Say **“list MIDI inputs”**, then **“select MIDI input one”** if the piano did not
   connect automatically. Say **“list MIDI outputs”** and select one for reference sound.
2. Say **“practice Ode to Joy”** or **“Für Elise theme right hand.”**
3. Say **“play it for me”**, then **“record”** when ready. Pause four seconds after
   playing for a report, or say **“ADA stop.”**
4. Say **“how did I do,” “replay,”** or **“guided practice.”** Guided practice waits
   for the expected note or chord and speaks immediate corrections.
5. Say **“save session”** for a save confirmation, or **“quit.”** Completed takes
   are saved automatically, including when practice is stopped or the app closes.

## Voice and keyboard controls

At idle, speak directly after ADA finishes. During recording, guided practice,
reference sound, or ADA's speech, only a wake-prefixed stop command is accepted:
**“ADA stop.”** Other commands wait until you stop. This limits accidental actions
from piano sound or speech echo; it is not acoustic echo cancellation. A headset
can help, and interruption latency depends on the recognizer. Escape remains an
immediate keyboard stop.

Say **“stop listening”** to turn the microphone off. F1 retries/resumes conversation;
you can also type **“start listening.”** Spoken commands work without an AI key.
The standalone chat window retains its separate one-shot dictation behavior.

| Key | Action |
| --- | --- |
| F1 | Start/retry voice conversation; focus the message field if unavailable |
| F2 / F3 | Open import controls / toggle all tools |
| F5 / F6 | Record / ask for results |
| F7 / Escape | Toggle camera / stop practice, sound, and calibration |
| Tab / Shift+Tab / Enter | Move between native controls / submit a typed message |

### Practice and setup commands

| Purpose | Say |
| --- | --- |
| Discover and recover | “help,” “help settings,” “status,” “repeat,” “list pieces” |
| Music | “practice Für Elise,” “measures one to four,” “left hand,” “both hands,” “practice measure three” |
| Playback and practice | “play it for me,” “record,” “guided practice,” “replay,” “how did I do,” “tempo sixty,” “slower” |
| Devices | “list MIDI inputs,” “select MIDI input two,” “connect piano,” “disconnect piano,” “list MIDI outputs,” “select MIDI output one,” “list cameras,” “select camera one” |
| App and speech | “show tools,” “hide tools,” “save session,” “quit,” “list voices,” “use system voice,” “use natural offline voice,” “speech off,” “speech on,” “speech speed 0.85” |

Device numbers are one-based positions in the spoken list. Select by full name
if preferred. A tempo change applies to the next reference/take; stop current
practice first. Selecting measures uses printed measure labels within the current
approved passage. Reload a checked piece to expand beyond that selection.
Hand selection for checked pieces preserves selected measures. “Practice measure”
starts guided practice; “measures” only changes the selection.

### Speech setup

ADA chooses OpenAI speech when a key is configured, then Piper when installed,
then system speech or text. Use **“use system voice”** or **“use natural offline
voice”** to select local speech. Speaking-speed commands apply to cloud voices.
Cloud speech is AI generated; reply text is sent to OpenAI and charges may apply.

Linux recognition uses faster-whisper offline (first use downloads its model), or
OpenAI transcription when a key is set. It records using PipeWire `pw-record` or
ALSA `arecord`. Set `ADA_MIC_TARGET` or `ADA_ALSA_DEVICE` to override the recording
source. Windows uses an installed English System.Speech recognizer. Microphone
recognition is not implemented on macOS. Device permissions and installing speech
engines happen outside ADA. Unavailable microphones are announced when speech
output works, and the text field remains usable.

## Optional camera and MIDI hand observations

MIDI alone supports practice. Camera analysis adds conservative evidence of a
fingertip near a MIDI key; it does **not** establish which finger pressed the key,
correct fingering, posture, or technique. AI receives the same bounded evidence,
including unknown observations and its limitations.

1. Fix a camera above a small piano region, facing nearly straight down. Keep
   the piano and camera still. Say **“start camera.”** For a different device,
   say **“list cameras”** and **“select camera one.”** A phone-camera URL can be
   typed, for example `select camera http://192.168.1.20:8080/video`.
2. Say **“calibrate hands”** (right index finger) or **“calibrate left hand.”**
   Keep only that hand visible. Press three separated white keys spanning at
   least an octave, such as C4, G4, C5, with the same index finger near the fronts
   of the keys. Hold still for half a second and release before each next key.
   ADA speaks the captured note names or asks you to retry.
3. After white calibration, press two separated black keys spanning at least
   seven semitones, such as C sharp4 and A sharp4, with that index finger at a
   consistent depth on the black keys. Or say **“finish calibration”** to use
   white keys only; black-key observations will be unknown.
4. Record or use guided practice, then say **“hand report.”** With an AI key,
   you can ask what the camera observed. Both hands may be visible in practice;
   calibration establishes how the camera's hand labels map to your actual hands.
5. Recalibrate after moving the camera or piano. Stopping, switching, or losing
   the camera clears calibration. **“Reset calibration”** clears it manually.

Only keys between each row's calibration anchors are covered. Geometry is a
fitted line per key color, not a full perspective model. Fingers must remain near
those contact lines. Two nearby camera frames must surround a MIDI attack;
missing, delayed, unstable, ambiguous, or out-of-range evidence becomes unknown.
Network-camera buffering is not measured. Geometry and timing thresholds need
validation on real piano/camera recordings. Reports retain at most 24 detailed
associations and analyze at most 1,200 attacks per take; truncation is reported.
No camera images or raw landmarks are saved in practice sessions or sent to AI.
Calibration is not restored across restarts.

## Import and spoken review

Checked catalog pieces can be loaded without reviewing a file. For new music:

1. Place `.pdf`, `.musicxml`, `.xml`, or `.mxl` files in `scores/inbox` under the
   working directory, or set `ADA_SCORE_DIR`. Say **“list score files”**, then
   **“import score one.”** You can also type `import score /path/to/file.musicxml`.
2. Wait for the spoken import result. PDF recognition needs a separate Audiveris
   installation. **“Cancel import”** cancels conversion and retains diagnostics.
3. Say **“list score options.”** Choose an output or part with **“select score
   output one”** or **“select score part one.”** Use **“select score staff two”**,
   **“select score staff all”**, or **“select score voice one.”** Staff numbers
   are not assumed to mean right/left hand in arbitrary imported music.
4. Select **“measures one to four”** before approval. Here numbers are one-based
   measure positions. Say **“review passage”** and **“next measure”** to hear every
   note/rest, beat position, duration, staff, and voice. Long measures continue
   over several requests, eight rows at a time.
5. Check the recognized notes against a trusted accessible source or with a
   helper, then explicitly say **“approve passage.”** A spoken preview does not
   prove PDF recognition was correct. Correct errors in an external score editor
   and reimport. Approval is cleared when imported selection settings change.

The importer plays written measures once; it does not expand repeats or alternate
endings. See [supported notation](MUSICXML.md) and the [import guide](SCORE_IMPORT.md).

## Reports, AI, and local files

Play-through reports align MIDI with the score and summarize wrong, missed, and
extra notes, early/late attacks relative to a fitted tempo, hesitations, and short
key holds. Guided practice checks pitch/chord attacks, not written rhythm. MIDI
does not measure acoustic sustain, pedal technique, dynamics, or articulation.

The optional AI coach receives approved score context, measured summaries, and
calibrated hand summaries. General questions can use AI; device selection, file
import, approval, and other local controls do not depend on the model. Cloud
coaching, speech, and transcription may incur charges. With local speech and no
API key, core practice and controls work offline after dependencies/models are
installed.

Sessions are JSON exports with a unique ID, score/selection context, MIDI results,
hand summaries, and coaching feedback received for that session. Writes are atomic
and run outside the MIDI loop. A failed save is reported; a save failure on exit
keeps the window and latest session open for retry.

| Platform | Default session folder |
| --- | --- |
| Linux | `$XDG_DATA_HOME/ada-piano/sessions`, or `~/.local/share/ada-piano/sessions` |
| Windows | `%LOCALAPPDATA%/ada-piano/sessions` |
| macOS | `~/Library/Application Support/ada-piano/sessions` |

There is no session browser or automatic resumption. “Replay” uses the latest
play-through still in memory. Files stay local; camera frames and credentials are
not included. Calibration is deliberately discarded when camera geometry changes.

## Checks before independent use

Automated checks use fake devices and synthetic landmarks. Physical trials remain:

1. Complete a practice session with a blind learner, including recovery from a
   disconnected input and microphone failure, and check the target screen reader.
2. Confirm reference/replay sound, spoken feedback, and “ADA stop” with the actual
   microphone and speakers while the piano is sounding.
3. Calibrate white/black keys and compare observed fingers against labeled video
   under realistic lighting, occlusion, both hands, and camera movement.
4. Import a real PDF with Audiveris and review/approve it through voice.
5. Confirm the exported session matches the played take and survives restarting ADA.
