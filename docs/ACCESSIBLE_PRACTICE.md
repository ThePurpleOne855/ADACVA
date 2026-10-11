# Voice-first practice with measured feedback

The app opens on the **ADA Coach** tab with speech on. ADA greets you, asks
"What would you like to practice today?", reads the catalog and listens for the
answer. A blind learner can load a piece, hear it, play it through and get
measured feedback without the mouse, loading files or a sighted helper.

```sh
uv sync --locked --all-extras
uv run ada-piano voice-setup      # once: natural offline voice (about 60 MB)
uv run --locked --all-extras python -m ada_piano note-reader
```

## Voice

ADA picks the best voice automatically:

1. **OpenAI voice** when an API key is set (most natural; API charges apply).
2. **Natural (offline)** — Piper neural voice, free and private, after
   `ada-piano voice-setup`. Set `ADA_PIPER_VOICE=/path/to/model.onnx` to use
   another [Piper voice](https://huggingface.co/rhasspy/piper-voices).
3. System voice (`espeak-ng`, macOS `say`, Windows speech), then on-screen text.

Change it any time with the **Voice** list in the ADA tab.

## Talking to ADA

Speech recognition runs offline (faster-whisper, part of the `voice` extra; the
first use downloads about 140 MB), or through OpenAI when an API key is set.
In the main app you don't press anything: ADA listens after it speaks, sends
what it heard, and listens again after answering. The app tests the
microphones once and uses one that carries sound, skipping loopback inputs left
by DroidCam and silent webcam mics. To force one, set `ADA_MIC_TARGET` to a
source name from `pactl list short sources`.

## Keys

| Key | Action |
| --- | --- |
| F1 | Talk to ADA (microphone), or focus the message box |
| F5 | Record a play-through of the loaded passage |
| F6 | "How did I do?" |
| F7 | Camera on/off (announces when it sees your hands) |
| Esc | Stop everything (MIDI stays connected) |
| F2 | Show/hide the PDF import tools (needs a sighted check) |

## Commands that work offline

Type them, or say them with "ADA …" in hands-free mode. These do not need an API
key and are handled locally, so they behave the same every time.

- "list pieces"
- "practice Für Elise" · "Für Elise middle, left hand" · "ode to joy"
- "play it for me" — reference sound through the MIDI output
- "replay" — hear your own last play-through
- "start camera" · "stop camera"
- "record" — then play; pause about four seconds when finished
- "how did I do" — spoken summary (with an API key, ADA explains it in more depth)
- "stop" · "help"

Any other question goes to the ADA coach, which can also load pieces, start a
recording of selected measures and read the measured report.

## ADA uses sound when it helps

With the piano's MIDI output connected, ADA decides on its own when hearing
something would help: it plays the approved measures (often slower), a few
notes, an interval or a chord, or replays your last play-through to contrast
it with the reference. There is no pop-up confirmation: ADA says what it is
about to play first, and "stop" or Esc cancels. It never plays while you are
playing or recording.

## Camera without DroidCam

The camera is optional (MIDI decides which notes were played). Say "start
camera" or press F7; the app chooses for you:

1. **A USB webcam** (simplest): plug it in. It is preferred over a built-in
   laptop camera. Virtual devices left by phone-webcam drivers ("Dummy video
   device", DroidCam) are ignored.
2. **A phone over Wi-Fi**, no driver needed: install any "IP camera" app that
   shows an address (Android: *IP Webcam*; iPhone: an MJPEG/RTSP camera app),
   keep the phone on the same Wi-Fi, and type the address it shows — e.g.
   `192.168.1.20:8080` — in the camera field, or start with
   `ADA_CAMERA=192.168.1.20:8080`. A bare address becomes
   `http://…/video`; enter the app's full URL if it uses another path
   (`rtsp://` works too).

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
6. Start the app: ADA greets you in the natural voice and lists the pieces.
7. Plug in a USB webcam, say "start camera": ADA names the webcam and says
   how many hands it sees. Repeat with a phone camera app's address.
8. Ask ADA "What does a C major chord sound like?" and "Can I hear what I
   played?": the Yamaha plays them after a spoken announcement.
