# Import existing sheet music

Export a score as MusicXML (`.musicxml`, `.xml`, or compressed `.mxl`), then:

```powershell
python -m ada_piano sheet --exercise song.musicxml
python -m ada_piano demo --exercise ada_piano/exercises/five_notes.musicxml --notes 60 62 64 65 67
python -m ada_piano practice --exercise song.mxl --part P1 --staff 1 --voice 1 --port "YOUR MIDI INPUT" --speak
```

Use `sheet` first to inspect the imported sequence. Multi-part scores require
`--part` with the score's part ID; the error lists available IDs and names.
For piano scores, `--staff 1 --voice 1` may select a melody, but voice numbering
is determined by the score exporter. Staff selection does not infer a hand.

This first importer provides **untimed, single-note pitch practice**. Rests and
durations are not graded. Tied continuations do not require another key press.
Sharps and flats come from MusicXML's explicit pitch/alter, not its display
accidental or key signature. Existing JSON exercises remain supported.

Supported: partwise scores, title, integer MIDI pitches, rests, ties, selection
of one part/staff/voice, XML namespaces and compressed rootfile containers.
Rejected: chords in the selected line, grace/cue/unpitched notes, microtones,
repeats/endings/playback jumps, transposition, octave shifts, and timewise scores.
Export an unfolded concert-pitch monophonic line for these cases. This is not
a complete MusicXML schema validator. PDF, photos and scanned scores require
score recognition, which is not implemented.

XML is parsed locally without fetching external DTDs or extracting ZIP members
to disk. Entity declarations and documents over 16 MiB are rejected.

Next milestones: timed events and rests, simultaneous chords, repeat expansion,
and accessible selection of score parts/measures.

Reference: [W3C MusicXML pitch and tie semantics](https://www.w3.org/2021/06/musicxml40/tutorial/midi-compatible-part/).
