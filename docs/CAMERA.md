# Overhead camera: build and tracking plan

This branch supplies a first hand-landmark tracker. It does not yet identify piano
keys, detect a key press, or grade fingering. MIDI note-on events should remain
the source of truth for which notes actually sounded.

## Run the tracker

From the repository root, with Python 3.11 or 3.12:

```powershell
python -m venv .venv
. .\.venv\Scripts\Activate.ps1
python -m pip install -e '.[camera]'
New-Item -ItemType Directory -Path models -Force | Out-Null
Invoke-WebRequest -Uri 'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task' -OutFile 'models\hand_landmarker.task'
python -m ada_piano.camera --source 0 --jsonl hand-session.jsonl
```

Use `--source 1` if another camera occupies index 0. Press `q` to close the
preview. Use `--seconds 30 --no-preview` for a timed headless check. Test a
still frame with `--image photo.jpg --output annotated.jpg`. The tracker stores
normalized `x`, `y`, and `z` for all 21 hand landmarks and both handedness
labels. The JSON lines include `captured_monotonic_ns` so camera observations
can later be matched to MIDI events recorded on the same computer with
`time.monotonic_ns()`. The `timestamp_ms` field is the MediaPipe video timestamp
relative to the beginning of capture.

The model is downloaded separately, kept in ignored `models/`, and is not
uploaded with camera frames. It can be used offline after download. Avoid
recording bystanders; JSON output is optional.

## Mount to build

Use the webcam's existing folding monitor clip on a printed adapter plate.
Support that plate with a rigid overhead arm fixed to the keyboard stand or a
separate stable base behind the keyboard. A 2020 aluminum extrusion arm with
printed camera adapter and clamp parts is a practical first build: the metal
arm limits flex, while the printed parts fit the actual webcam and stand.
The first parametric adapter is in [mount/webcam_adapter.scad](../mount/webcam_adapter.scad).
It bolts to one extrusion slot with two M5 T-nuts and presents a vertical edge
for the webcam's own clip. Change the parameters after measuring the clip.
Print it flat with the base on the build plate, preferably in PETG with several
perimeters; verify screw length against the extrusion and use washers. The
printed adapter is not a complete overhead stand.
Keep the lens centered over the keys and pointed nearly straight down. Route
the USB cable along the arm with slack at the camera and strain relief at the
base. Keep fasteners, printed parts, and the cable out of the player's hands.
Do not rest the mount on playable keys.

Before final CAD, measure and photograph:

1. Webcam body width, depth, and height; folding clip opening and contact
   surfaces; whether its underside has a standard tripod socket.
2. Keyboard width, keybed depth, and the number of keys that must fit in one
   frame. Photograph the keyboard from above and from the side.
3. Available stand or desk attachment dimensions and the maximum usable height
   above the keys. Include the USB cable length and any obstacles.

Print a small test adapter before the full mount. Confirm the clip grips it,
the image stays steady while playing, and the webcam sees the intended key
range and both hands at the capture resolution. If it cannot see the full
keyboard with enough pixels per key, prioritize a two-octave training region
or use a second camera. Do not infer the webcam's field of view from its
appearance in a photo.

## Make the view musically useful

1. **Calibrate the keyboard.** Fix the mount, then record the four corners of
   the visible keybed and several black-key landmarks. Use a perspective
   transform to map image points into keyboard coordinates. Recalibrate after
   any mount movement. Offer keyboard controls and spoken prompts for setup.
2. **Locate fingers over keys.** Transform each fingertip into keyboard space,
   show the likely white or black key under it, and smooth short tracking gaps.
   Test with two hands, different skin tones, sleeves, and realistic lighting.
3. **Join camera and MIDI.** On each MIDI note-on, look at nearby camera frames
   and rank plausible fingers by proximity and recent downward motion. Report
   a finger assignment only when confidence is high; otherwise say unknown.
   Video alone cannot reliably prove a key was pressed when fingertips obscure
   the keys, and MediaPipe landmark depth is relative to the hand, not a
   calibrated distance to the key surface.
4. **Coach technique.** Compare the inferred finger to the exercise's intended
   fingering. Add hand crossings, reach, and wrist position only after the
   basic note/finger association is validated with recorded examples.

## Demo acceptance checks

- Both hands are tracked for a continuous 30-second scale exercise, with
  visible landmarks and an FPS report.
- The same fixed mount provides a stable keyboard calibration before and
  after playing; note which keys are outside the frame.
- For a small labeled recording, report how often a MIDI note-on is associated
  with the correct hand/finger and how often the system abstains. Choose a
  threshold from the data rather than promising perfect attribution.
- Feedback is spoken or screen-reader accessible; the preview is only a
  sighted setup aid.

Reference: [MediaPipe Hand Landmarker Python guide](https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker/python).
