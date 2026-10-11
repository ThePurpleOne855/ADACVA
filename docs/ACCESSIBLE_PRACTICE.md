# Voice-first practice with measured feedback

The app opens on the **ADA Coach** tab with speech on. A blind learner can load
a piece, play it through and hear measured feedback without using the mouse,
loading files or asking someone to check a score.

```sh
uv run --locked --all-extras python -m ada_piano note-reader
```

On Linux, install `espeak-ng` for the offline voice (`sudo pacman -S espeak-ng`,
`sudo apt install espeak-ng`). Without it and without an OpenAI API key, ADA
falls back to on-screen text.

## Keys

| Key | Action |
| --- | --- |
| F1 | Talk to ADA (microphone), or focus the message box |
| F5 | Record a play-through of the loaded passage |
| F6 | "How did I do?" |
| Esc | Stop everything (MIDI stays connected) |
| F2 | Show/hide the PDF import tools (needs a sighted check) |

## Commands that work offline

Type them, or say them with "ADA …" in hands-free mode. These do not need an API
key and are handled locally, so they behave the same every time.

- "list pieces"
- "practice Für Elise" · "Für Elise middle, left hand" · "ode to joy"
- "play it for me" — reference sound through the MIDI output
- "record" — then play; pause about four seconds when finished
- "how did I do" — spoken summary (with an API key, ADA explains it in more depth)
- "stop" · "help"

Any other question goes to the ADA coach, which can also load pieces, start a
recording of selected measures and read the measured report.

## Checked pieces

`ada_piano/pieces/catalog.json` lists pieces that were verified note by note
before being added, so loading one needs no visual review:

- **Für Elise (easy arrangement)**, both/right/left hand — passages *theme*
  (m. 0–8), *middle* (m. 9–16), *ending* (m. 16–23), *whole* (repeats played once).
  Converted with Audiveris from `test_examples/fur_elise_piano.pdf` and checked
  against both pages.
- **Ode to Joy**, right hand — *first phrase*, *second phrase*, *whole*.

To add a piece: convert and check it with the import tools (F2), copy the
MusicXML into `ada_piano/pieces/`, and add an entry with its passages, hands and
a `verified` note. Only add pieces someone has checked against the source.

## What a play-through measures

A recording is not interrupted by corrections. When you stop, the notes are
aligned with the score using edit distance, so one mistake does not shift every
later comparison. The report contains, per measure:

- **wrong** (played X instead of Y), **missed** and **extra** notes;
- **early/late** attacks relative to a tempo fitted to *your own* playing
  (a steady slow performance is not "late"), plus the estimated BPM;
- **hesitations** — pauses well beyond the written gap;
- **short** — keys released before half the written length.

Stopping early is reported as "stopped in measure N", not as missed notes.
MIDI is timestamped when it arrives (rtmidi callback), not when the screen
updates.

Not judged: pedal, dynamics, articulation, fingering, or audible length
under the sustain pedal.

## Hardware checks still needed

1. Plug in the mioXC, start the app: ADA should say "The piano is connected."
   Unplug and replug: it should announce both and reconnect by itself.
2. Say or type "practice ode to joy", then "record", play it with one deliberate
   wrong note, and pause. The summary should name that measure.
3. Repeat on Für Elise theme with both hands, playing at a slow, steady tempo.
   No early/late notes should be reported.
4. "Play it for me" with the MIDI output selected: the Yamaha should play,
   then ADA says "Your turn."
5. With an API key, ask "What should I fix first?" after a play-through.
