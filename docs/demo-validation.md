# Laptop and Yamaha demo validation

Status: **physical validation pending**. Automated tests use fake MIDI, microphone,
speech, and camera devices. They do not establish audible output or microphone
reliability around a sounding piano. Allow 15–20 minutes for this check.

Use the same laptop, Yamaha, MIDI interface, output, and microphone for all runs.
Leave camera guidance off. Keep auto-finish disabled. Record the device names,
app commit, operating system, and date with the results below.

## Core sequence — repeat three consecutive times

1. Launch `uv run --locked --all-extras python -m ada_piano note-reader`.
   Confirm “Piano connected” and the intended MIDI output. If using the YPT-300,
   set PC mode to oFF (hold DEMO).
2. Say “ADA practice Ode to Joy,” then “ADA play it for me.” Confirm that the
   Yamaha is audible and that reference playback does not become a learner take.
3. Say “ADA record.” Play the first few notes, pause at least ten seconds with
   all keys released, then continue. Recording must remain active during the pause.
4. Say “ADA finish recording.” Confirm a spoken outcome, reached/total passage
   notes, pitch accuracy on the portion reached, and measured feedback. A partial
   take must not suggest advancing. Check that F6 produces the same result.
5. Say “ADA record” and retry the same passage. Finish it explicitly and hear
   the new measured report. Close and relaunch before the next run.

| Run | Reference audible | Pause safe | Voice finish works | Feedback factual | Retry works | Result |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Pending | Pending | Pending | Pending | Pending | Pending |
| 2 | Pending | Pending | Pending | Pending | Pending | Pending |
| 3 | Pending | Pending | Pending | Pending | Pending | Pending |

## Interruption and recovery checks

1. While the reference sounds, say “ADA stop.” Confirm silence. Repeat with
   Escape, including during the spoken announcement before reference playback.
2. While playing, say “ADA finish recording.” Confirm microphone recognition
   works with piano audio present and background sound does not trigger actions.
   Escape must remain an immediate fallback.
3. During a partial take, unplug the MIDI interface. Confirm the take is saved
   with a disconnected outcome and no success/advance message. Reconnect and
   confirm automatic connection recovery; recording must wait for a new “record.”
4. Finish an empty take and stop a correct but partial take. Confirm neither
   reuses an old result or describes the whole passage as successful.
5. Enable “auto finish after thirty seconds.” Confirm released-key silence
   finishes a partial take with an explicit timeout and stopped-early report.
   Say “disable auto finish” afterwards.

Record any failure with the spoken command, expected result, actual result, and
device state. After a fix, restart the three-run sequence. The demo baseline is
accepted only after three consecutive passing core runs and passing recovery checks.
