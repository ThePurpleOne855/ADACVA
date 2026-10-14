# Score-guided piano learning: current delivery and historical plan

## Integrated prototype — 2026-10-13

The desktop now connects voice controls, a minimal practice screen, timestamped
MIDI comparison, spoken score review, calibrated fingertip proximity evidence,
optional AI coaching, and atomic local JSON session exports. MIDI is timestamped
on arrival; camera observations use host acquisition times. Calibration does not
establish correct fingering or posture. Exports do not contain raw camera frames
or landmarks, and there is no session browser or automatic resume.

The current scope and limits are in [README.md](README.md) and the
[voice guide](docs/ACCESSIBLE_PRACTICE.md). Remaining acceptance work is hardware
validation, microphone interruption while sound plays, imported-score checks,
screen-reader compatibility, and trials with blind learners.

**The sections below preserve the original design and dated handoffs. Their
estimates, future features, and status statements are historical, not the current
implementation contract.**

Target experience: import a PDF or MusicXML score, review the recognized music, play on the Yamaha YPT-300, record the performance, compare it with the score, and receive spoken/visual corrections. Camera observations will support guidance toward the intended keys and suggested fingering.

## Historical starting state

Live YPT-300 input through the mioXC is user-confirmed. Note Reader displays a virtual keyboard, velocity, channel, sustain, and note history. The duration column measures press to release. Automated tests cover the reader, desktop GUI, and audible-reference engine. Timing for input currently uses GUI polling timestamps and is approximate.

Music Sheet loads JSON and MusicXML (including compressed MXL), preserving timed attack groups, chords, rests, and ties with part/staff/voice and measure selection. The tutor supports held-key chord matching, but does not grade rhythm. The shared GUI tracks finger joints with camera selection, but the camera is not calibrated to piano keys or integrated with the tutor. The Scores tab now provides a local Audiveris conversion worker, retained sources/results/logs, passage review and approval, fixed-tempo MusicXML playback, and live pitch/chord practice. Audiveris recognition and the new desktop workflow still need local validation. Saved practice sessions, language-model feedback, and calibrated hand guidance remain to be implemented.

## ADA Coach update — 2026-10-11

First lightweight coaching layer: immutable TutorResult observations preserve
the legacy text API; in-memory AttemptRecorder tracks approved-score identity,
selection, monotonic timestamps, completion and feedback. Deterministic summaries
group repeated errors and measured chord spreads. Optional JSON export is run
off the UI thread. This deliberately uses one attempt.json, rather than the
future multi-sensor events.jsonl recorder described below.

The optional Responses client sends sanitized approved score context and attempt
summaries, never raw sensors. Five bounded tools read passage/summary, request
reference playback, start targeted practice and stop. Playback uses the existing
ReferencePlayer and safety limits. Application confirmation and spoken
announcement precede reference sound; targeted practice waits for completion.
The combined Tkinter window has an ADA Coach tab; requests and system TTS run
in background workers, with text fallback and cancellation. No database,
microphone, camera calibration or full rhythm grading is included.

Remaining: physical Yamaha/speech and live API validation, accessibility testing
with learners, independently timestamped MIDI capture, timed comparison,
cross-attempt improvement analysis and the richer multi-sensor session recorder.
Existing historical stage descriptions below are the broader roadmap, not a
claim that those stages have all been delivered.

## Implementation stages

Initial engineering estimates below assume sample scores and dependencies are available. Recognition corrections and learner testing may add time.

1. **Import and review scores (first implementation complete; local validation pending).** Accept `.musicxml`, `.xml`, and compressed `.mxl` directly. Convert PDFs using Audiveris in a background process with progress, cancellation, and diagnostic output. Keep the source and recognition output, and require review before using recognized music as the practice reference. The first implementation preserves pitch, beat position, duration, rests, ties, staff/voice and chords. Tempo changes, pedal, dynamics and fingering are explicitly not interpreted yet. Flag unsupported constructs rather than silently flattening them. Acceptance: convert one representative PDF, review it, and select a staff/part for practice.
2. **Record and compare playing (4–8 hours for a single-hand prototype).** Capture MIDI presses/releases, velocity, channels, pedals, and monotonic arrival times independently of GUI updates and speech. Save session data linked to the reviewed score, passage, practice mode, and tempo. Start with a guided mode that waits for the correct pitch. Add count-in and timed alignment that handles wrong, extra, missed, and repeated notes without shifting all later comparisons. Convert score beats into time using practice tempo and tempo changes; treat rests and ties explicitly. Acceptance: save/reload a short attempt containing a wrong note, retry, missed note, and long hold. Add chord alignment and tempo adaptation after this baseline.
3. **Feedback and correction (3–6 hours for an initial integration).** Immediate local checks produce cues such as “Play D4” or “Hold longer.” A language model receives structured comparison results to explain patterns and prioritize practice after a phrase or attempt. It must not invent notes, fingers, or errors. Queue speech without blocking capture and replace stale instructions. Save feedback and subsequent attempts so improvements can be evaluated. Acceptance: compare two attempts and explain the measured changes. Choose the AI provider/model during implementation; local feedback remains usable independently.
4. **Calibrated hand placement (1–3 days for a constrained prototype).** Refactor the camera script into a reusable module. With a stable view of hands and keys, calibrate key regions and pitch anchors, then map finger landmarks to them. Account for the mirrored preview so directions agree with the learner's physical left/right. Use explicit exercise fingering or reviewed suggestions: pitches alone do not specify one correct fingering, and MIDI does not identify fingers. Start with one hand and five keys. Pause directional guidance when tracking or calibration is uncertain. Acceptance: guide a learner to those target keys, verify resulting MIDI notes, and recover from camera movement or occlusion. Do not claim unvalidated posture/technique assessment.
5. **Integrate accessible practice (1–2 days plus learner testing).** Connect score selection, recording, comparison, camera observations, immediate cues, and end-of-attempt feedback using a shared session clock. Reject stale observations. Provide keyboard-operable controls, adjustable speech, a stop action, and camera/MIDI connection states. Acceptance: complete a reviewed passage, correct a mistake, replay recorded MIDI events, review feedback, and resume after a device disconnect.

## Data boundaries

| Data | Purpose |
| --- | --- |
| Reviewed score | Expected notes/chords, beat positions, durations, rests, tempo, staff/voice, optional fingering |
| Performance events | Actual MIDI presses/releases, velocity, channel, pedal state, arrival timestamps |
| Comparison results | Matched score events, extra/missed/wrong notes, timing differences, uncertainty |
| Camera observations | Calibrated key regions, hand/finger positions, timestamps, confidence |
| Feedback history | Instructions, supporting observations, and subsequent attempts |

“Record the performance” initially means saving MIDI/session data, not microphone audio or camera video. Key-held duration is different from audible duration under sustain. Audio/video recording can be added if requested.

## Shared session recorder

Keep the independently developed camera, MIDI, score, and feedback modules behind small event interfaces. Add a separate Session Recorder that subscribes to their events. For the first version, use one local folder per attempt with `session.json` metadata and an append-only `events.jsonl` stream. This avoids a database dependency while permitting later indexing or migration to SQLite.

Metadata includes a schema version, session ID, score identifier/hash, selected passage, tempo, calibration identifier, and start time. Each event includes its type, source module, sequence number, and time relative to a shared monotonic session clock. Timestamp MIDI on receipt and camera frames at acquisition where possible; preserve processing latency or estimated capture delay rather than treating inference completion time as the hand-position time. Use a queued writer so saving cannot block input, and explicitly record dropped observations or write failures.

Save raw MIDI events and derived key-held durations; camera landmarks with documented coordinate systems, hand/finger identity estimates and confidence; calibrated key associations; comparison results; and feedback. Finger-to-note associations are inferred and can be unknown when the camera is obscured. Initially save landmarks and derived observations, not continuous video. Retain the original events so scoring can be rerun without asking the learner to repeat an attempt.

Live corrections can use an in-memory time window. For AI analysis, assemble a phrase-level summary from the score alignment and synchronized observations, then retain the evidence used for each response. The language model does not need every camera frame. It can report hand movement only to the extent supported by calibrated, confident observations.

Acceptance: record a short session with MIDI and camera observations, reload it, align both streams to the same passage, and reproduce the original comparison. Initial recorder implementation estimate: 2–4 hours, with camera synchronization validation additional.

## Audible score demonstrations

Implemented foundation: `ReferencePlayer` now accepts typed note plans or JSON-compatible requests through `play_request()`, uses a cancellable output worker, and reports reference events separately. Note Reader provides output selection, clickable piano keys, single-note and sequence controls, tempo/velocity/channel settings, and Stop sound. The API and reviewed-MusicXML adapter support a fixed tempo with chord/rest scheduling; tempo-map and pedal-score adapters remain planned. Automated desktop tests and a real RtMidi virtual-port round trip verify the software path. Audible Yamaha output still requires user confirmation.

The reviewed-score adapter is implemented with tie durations and internal rests. Next, add support for tempo changes and pedal events. The future AI adapter may request a bounded passage and a slower tempo; the playback module validates the note plan and handles scheduling outside the language model and GUI thread.

Send playback through mioXC MIDI OUT to Yamaha MIDI IN while USB remains connected. This produces sound through the Yamaha; it does not physically move or illuminate its keys. Provide play, stop, tempo, and passage controls; stopping or failing must release all notes started by playback and any sustain enabled by playback. Tag outgoing events as demonstrations. Begin with alternating Listen and Your turn modes, exclude demonstration intervals from learner scoring, and do not enable automatic MIDI input-to-output echo.

Hardware acceptance remains open: confirm the learner hears three test notes with the now-working wiring/settings. The GUI sent C4–E4–G4 through mioXC and reported completion, but audible output has not been confirmed by the learner. Then demonstrate a reviewed five-note score and record the learner's response after the score adapter and recorder are implemented.

Playback support is documented in the [YPT-300 manual, page 59](https://data.yamaha.com/download/files/2091886) and the [Mido MIDI-file playback documentation](https://mido.github.io/mido/files/midi.html).

## First delivery

One reviewed, single-hand MusicXML exercise with five notes: show the expected key, record playing, identify a wrong pitch, prompt a retry, and save the attempt. This establishes a testable foundation before full-score timing and hand guidance.

The supplied two-page `ada_piano/note_reader/test_examples/fur_elise_piano.pdf` is available for an Audiveris conversion trial. Recognition has not been tested; select a short single-hand passage for the first exercise. Existing MusicXML can bypass recognition.

## Session handoff — 2026-10-10

Completed: per-note/channel held durations; clickable reference keys; output selection and single-note/sequence controls; a GUI-independent, validated playback API for future score/AI callers; cancellable scheduling, release cleanup, and separate reference event labels. Fixed black-key click targeting, sharp-label font compatibility, and automatic selection of software-only output ports. Tests cover timing resets, chords/rests, invalid requests, cancellation, output failures, unplugging, and GUI event separation.

Validation: all 49 automated tests passed, including desktop GUI tests. A real Mido/RtMidi virtual-port round trip verified note-on/off output. The physical mioXC send completed; speaker audibility remains unconfirmed. Input timing still uses GUI polling, and practice sessions are not yet persisted.

Next session, in priority order:

1. **Confirm audible output (1–2 minutes).** In Audible reference, select mioXC and play `C4 E4 G4`; confirm the Yamaha speakers sound all three notes.
2. **Trial PDF recognition (30–60 minutes, plus installation if needed).** Check/install Audiveris, convert the supplied PDF, retain diagnostics, and review a short passage against the source.
3. **Connect existing MusicXML import to playback (2–4 hours initially).** Use `Exercise.events` and per-tone durations, preserve chords/rests/ties, and add review controls for one short passage. MusicXML import and held-key chord practice arrived from GitHub main during integration; avoid duplicating them.
4. **Add session recording (2–4 hours initially).** Capture MIDI arrival timestamps independently of GUI polling, persist metadata/events, and mark Listen versus Your turn intervals before scoring attempts.
5. **Continue comparison, camera calibration, and AI integration.** Follow the stage estimates above; keep feedback grounded in recorded, aligned observations.

See the [Audiveris project](https://github.com/Audiveris/audiveris) and [CLI documentation](https://github.com/Audiveris/audiveris/wiki/CLI-Arguments) for the proposed PDF conversion component.

## Score workflow update — 2026-10-11

Implemented: PDF conversion subprocess with cancellation and retained diagnostics; direct MusicXML import; saved original/output files; part/staff/voice/measure selection; note/rest table; explicit review approval; fixed-tempo passage playback; pitch/chord practice against live MIDI; and structured approved-passage JSON for future agent use. Selection changes invalidate the loaded approval. No language-model calls or saved performance sessions were added.

The converter was tested through a real child-process fixture, including conversion failure, timeout, cancellation and the resulting score → playback → tutor path. This does not validate Audiveris recognition quality. Audiveris is not on the development environment's PATH, and a desktop display is unavailable. Next acceptance check: install/select Audiveris locally, convert the supplied PDF, review a short supported passage and test playback/practice. See [SCORE_IMPORT.md](docs/SCORE_IMPORT.md).
