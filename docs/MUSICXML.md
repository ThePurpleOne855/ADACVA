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
Omit both selectors to combine all voices/staves in the chosen part. Attacks
at the same score position become one group, including notes across both staves.

## Practice a measure range

```powershell
python -m ada_piano sheet --exercise "C:/Users/X/Downloads/Moonlight Sonata - Ivory.mxl" --part P1 --staff 1 --voice 1 --start-measure 1 --end-measure 4
```

Both endpoints are inclusive **one-based positions in the selected part**, not
printed measure labels. Pickups, labels such as `X2`, and restarted numbering
still count as one measure each. Omit the start to begin at the first measure;
omit the end to continue to the end of the part. The exercise title reports both
the chosen positions and the original endpoint labels. These flags also work
with `demo` and `practice`; JSON does not support measure selection.

The range is read in written order. Unsupported features outside the
range do not block it. Repeat markings/endings inside it still do. Division
settings are inherited from earlier measures. Earlier transposition, octave
shifts or measure-repeat declarations are conservatively rejected because they
may affect the excerpt. A range starting inside a repeat ending is rejected.
Ranges cutting through a tie are rejected with instructions to extend the range.
Selecting a range does not implement repeat playback or rhythm grading.

The importer provides **single-note and chord pitch practice**. Onsets, per-note
durations and rests are preserved as exact fractions of quarter-note beats.
Rests and durations are not graded. Tied continuations extend the original note
duration and do not require another key press, including partial chord ties.
Sharps and flats come from MusicXML's explicit pitch/alter, not its display
accidental or key signature. Existing JSON exercises remain supported.

Supported: partwise scores, title, integer MIDI pitches, chords, multiple voices
and staves, rests, ties, selection of one part and optional staff/voice filters,
XML namespaces and compressed rootfile containers.
Rejected: grace/cue/unpitched notes, microtones,
repeats/endings/playback jumps, transposition, octave shifts, and timewise scores.
Export an unfolded concert-pitch score without these features. This is not
a complete MusicXML schema validator. PDF, photos and scanned scores require
score recognition, which is not implemented.

XML is parsed locally without fetching external DTDs or extracting ZIP members
to disk. Entity declarations and documents over 16 MiB are rejected.

## Chord practice

For both staves of the opening Moonlight excerpt:

```powershell
python -m ada_piano sheet --exercise "C:/Users/X/Downloads/Moonlight Sonata - Ivory.mxl" --part P1 --start-measure 1 --end-measure 4
python -m ada_piano practice --exercise "C:/Users/X/Downloads/Moonlight Sonata - Ivory.mxl" --part P1 --start-measure 1 --end-measure 4 --port "YOUR MIDI INPUT" --chord-window-ms 150
```

The tutor waits for all pitches in each attack group to be held. Notes must be
pressed within the configured window; a rolled chord outside it prompts a retry.
Repeated chord pitches need release and re-press. Extra held pitches block chord
exercises, except earlier score tones whose written durations extend into the
current attack. Such sustained notes are allowed, but holding their full duration
is not yet graded. Single-note-only exercises retain the earlier forgiving mode.
Same-pitch unisons across staves count as one physical key. Sustain pedal messages
are ignored: matching uses physically held keys, not sustained sound.

`Exercise.events` is the chord-aware sequence; each event has an onset, original
measure label and tones with pitch/duration/staff/voice. `Exercise.rests` preserves
rests; `Exercise.duration` includes trailing rests/forward movement. Onsets are
relative to the selected range. `Exercise.notes` remains a flattened compatibility
view and must not be used to infer chord boundaries. JSON chords receive unit
spacing/durations; they do not claim timing from a source score.

Next milestones: repeat expansion, rhythmic grading, and live MIDI validation.

Reference: [W3C MusicXML pitch and tie semantics](https://www.w3.org/2021/06/musicxml40/tutorial/midi-compatible-part/).
