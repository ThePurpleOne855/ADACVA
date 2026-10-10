# Hackathon delivery plan

Target demo: a learner hears the next note, plays it on the YPT-300, receives a correction if needed, and completes a five-note exercise. First prove camera and MIDI independently. Combine them only after both pass.

Estimates below are implementation time on the demo computer; obtaining the MIDI interface is additional time.

1. **Foundation — implemented; verify on demo laptop (10–15 minutes).** Four separate modules, dependency groups, a sample exercise, simulated demo, and core tests. Acceptance: `uv run python -m ada_piano demo` produces a wrong-note correction and finishes the exercise.
2. **Independent device checks (30–60 minutes).** Connect the USB-to-MIDI interface, list ports, verify five physical notes; check webcam frames and spoken output separately. Acceptance: expected MIDI numbers arrive, camera captures frames, and prompts are audible. Requires physical hardware.
3. **Spoken MIDI exercise (45–90 minutes).** Try `practice --port "..." --speak` with the learner. Add speech scheduling and stale-event handling before supporting continuous playing. Acceptance: slow five-note exercise, wrong-note retry, completion message, and keyboard-only stop all work. Test with the learner's screen reader.
4. **Camera hand tracking (2–3 hours).** Add MediaPipe Hand Landmarker and a local model asset, then calibrate hand landmarks against the keyboard. First report hand presence; only add directional guidance after calibration is verified. Acceptance: explain lost tracking and avoid confident guidance when tracking is uncertain. Keep this separate from note scoring until tested.
5. **Combine and rehearse (60–90 minutes).** Feed calibrated camera observations and MIDI events to the tutor. Rehearse one exercise, wrong notes, a disconnected device, and no hands detected. Keep the simulated demo available if hardware fails. Capture a backup recording with participant consent.

## Scope decisions

- Must deliver: keyboard-accessible workflow, MIDI note checks, audible short feedback, one exercise, and independent camera proof.
- Add only after the demo works: hand-position guidance and richer tutor explanations.
- Defer: microphone pitch recognition, scanned sheet music, chords, tempo grading, and custom model training.

## Open setup decisions

Demo operating system and whether “sound sensor” also means microphone input are awaiting confirmation. Current implementation assumes MIDI first. No cloud account or API key is needed.

## Foundation verification

Verified in this workspace using Python 3.14.7: four unit tests pass, the simulated exercise completes after a wrong-note correction, exercise text loads, and incomplete sessions retain the expected next note. A `.venv` was created.

Dependency management now uses uv, with Python 3.12 selected in `.python-version`. Creating `uv.lock` failed because this environment cannot resolve `pypi.org`. Run `uv sync --extra hardware` on a network-connected demo computer, then commit the generated `uv.lock`. Third-party packages and the Python 3.12 environment have not been verified here. Camera capture, physical MIDI, and spoken output still need hardware verification.
