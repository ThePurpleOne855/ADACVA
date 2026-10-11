# PDF → MusicXML → review → practice

## Open the workflow

From the project root:

```sh
uv run --locked --extra camera --extra midi python -m ada_piano note-reader
```

Choose the top-level **Scores · import & practice** tab. Use the **Piano & Camera**
tab to configure the MIDI input, reference output/tempo, and camera.

1. Click **Choose PDF / MusicXML**. Files stay on your computer. Existing
   `.musicxml`, `.xml`, and `.mxl` files bypass recognition.
2. For a PDF, Audiveris runs in the background. The moving progress indicator
   and elapsed time show activity, not an invented completion percentage.
   **Cancel conversion** stops the converter and retains its diagnostics.
3. Choose an **Available score**, part, staff/voice, and measure range. Blank
   staff/voice means all. From/to are inclusive measure positions, starting at 1,
   rather than printed score labels. The initial range is at most four measures.
4. Click **Preview passage**. Compare the note/rest table with **Open source**.
   Tick the review checkbox and click **Approve & load**. Correct recognition
   errors in Audiveris or another score editor and reimport the corrected
   MusicXML; this app does not yet edit or render notation.
5. Choose **Play approved passage**, or connect the live piano input and choose
   **Start practice**. Text feedback is also visible in **Piano & Camera**.

Changing the passage or importing another file clears the loaded approval and
stops its reference playback. Playback is never started by importing a file.
Reference events and simulated Demo notes are not graded as learner input.
Starting another reference pauses practice; explicitly start a new practice
attempt after listening. Disconnecting MIDI stops practice.

To play an entire score part, click **Whole piece** after loading MusicXML. This
previews all measures, staves and voices of the selected part (both piano hands).
Check the preview, **Approve & load**, then **Play approved selection**. Other
instrument parts are not combined. Unsupported notation still blocks import;
the current playback limits remain 4096 notes and five minutes at the chosen tempo.

**Play written measures once** is enabled by default: repeat signs and alternate
endings do not block preview, and every selected measure is practiced once in
printed order. This does not expand repeats or choose between alternate endings.
The setting is saved with the approved passage; changing it clears approval.
Preview is a note/rest table, not a rendered sheet-music image. XML and compressed
MXL reading use Python's standard library, with no additional dependency.

## Audiveris installation

Audiveris is a separate desktop/Java application, not a Python dependency.
Follow its [official installation instructions](https://audiveris.github.io/audiveris/_pages/tutorials/install/binaries/)
for your platform. The app automatically checks for a native launcher and then
the installed Audiveris Flatpak. No executable field needs to be filled in.
Use **Advanced converter settings** only if you need a custom Audiveris launcher.
Score files are rejected there; choose them with **Choose PDF / MusicXML** on
the main screen. Use a launcher script for custom Java options.

For Arch Linux with Flatpak, install the officially documented Flatpak app:

```sh
flatpak install flathub org.audiveris.audiveris
```

Restart our app; automatic converter detection is the default. The Flatpak is
detected automatically and receives access only to the current import folder,
which may be outside its default Documents/Pictures permissions. Choose the PDF
again to retry conversion. The older `scripts/audiveris-flatpak` launcher remains
available for manual use but is no longer required.
`uv sync` does not install Audiveris. Preview stays disabled until readable
MusicXML is available; **Diagnostics** explains installation/conversion failures.

The application invokes this documented argument sequence without a shell:

```text
audiveris -batch -transcribe -export -save -output OUTPUT_FOLDER -- SOURCE.pdf
```

See the [Audiveris CLI reference](https://audiveris.github.io/audiveris/_pages/guides/advanced/cli/).
The converter may produce multiple MusicXML files; choose the desired one in
**Available score**. A successful exit without readable MusicXML is treated as a
failure. Conversion has a 30-minute timeout. Cancellation targets the process
group on POSIX and the launcher/child process tree on Windows.

## Saved files and reuse

Each import gets a unique folder in the repository's ignored `scores/` directory:

```text
scores/DATE-TIME-ID/
  source.pdf                 # or source.musicxml / source.xml / source.mxl
  command.json               # PDF conversion arguments
  conversion.log             # complete converter stdout/stderr
  output/                    # Audiveris OMR project and MusicXML exports
  import.json                # original path, state, outputs, elapsed time
  reviewed-exercise.json     # most recently approved passage in this import
```

The source and converter output are retained even after failure or cancellation.
**Diagnostics** shows the latest 32 KiB of the log; the full log remains on disk.
To reuse a score after restarting, choose its MusicXML from the saved output
folder and review the desired passage again. The GUI displays the save location.

`reviewed-exercise.json` is structured agent context, not the simple JSON exercise
format accepted by the CLI. It records the score hash, selection, exact fractional
beat positions, note durations, rests, staff/voice, and approval time. The import
record's `reviewed: false` describes the raw recognition output; approval applies
only to the saved passage, not automatically to the entire score.

## Programmatic use

```python
from pathlib import Path
from ada_piano.score_import.review import ReviewedScore, playback_notes
from ada_piano.ai_tutor import Tutor

review = ReviewedScore(
    Path("song.mxl"), part="P1", staff="1", start_measure=1, end_measure=4,
)
# Present review.exercise to the user. Call approve only after their review.
review.approve()
context = review.context()             # JSON-compatible input for a future agent
tutor = Tutor(review.exercise)         # existing pitch/chord tutor
notes = playback_notes(review.exercise, tempo=90)
# Existing ReferencePlayer.play_notes(notes, port_name=..., tempo=90) sends MIDI.
```

The GUI uses the same objects and exposes `window.score.agent_context()` only
after loading an approved passage. There is no cloud upload or language-model
call. Agent integration here means a reusable data boundary, not an autonomous
agent making music decisions.

## Current limits and verification

The review is an accessible text table, not an engraved score viewer. GUI practice
provides text feedback; the existing CLI retains its optional speech feature.
The MusicXML parser's [supported features and limits](MUSICXML.md) still apply.
Unsupported notation prevents preview with an explicit error. Tempo changes,
pedal, dynamics, and fingering are not interpreted; the GUI states this before
approval. References use the selected fixed BPM and preserve note onsets, chord
durations, ties, and internal rests. Trailing silence is not scheduled after the
last note release. Same-onset unisons become one MIDI key; overlapping retriggers
of the same pitch are rejected rather than guessed. References remain limited
to 4096 notes and five minutes. Practice grades pitch/chord attacks, not rhythm.

Automated tests cover a real child-process conversion fixture, cancellation,
timeouts, failure logs, MusicXML copying, approval/hash checks, and the
conversion → reviewed score → MIDI playback → tutor path. The fixture does not
measure Audiveris recognition accuracy. Desktop tests cover approval and practice
controls but skip when no display is available. The installed Audiveris 5.11 Flatpak is now detected in the development
environment, but launching it there fails because its application data directory
is read-only. Real conversion and hardware/desktop validation must run locally.
