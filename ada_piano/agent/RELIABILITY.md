# Agent request reliability

Each request captures the approved review, local score activity version,
playback status and the attempt whose summary was supplied to the model.
Local score Stop, practice, selection changes and observed independent playback
status changes invalidate stale requests. Invalidation discards agent actions
and speech without stopping a newer local practice session. The explicit ADA
Stop button still stops practice and playback.

Reference playback actions wait on the worker thread, not Tk. Their tool result
is completed only after the application observes playback finishing. Failure,
decline or cancellation prevents a later practice action in the same request.
The next user request may try again. Feedback is attached only to the attempt
supplied as evidence, never an unrelated newer attempt.

## Verification

Run both commands (the second is the existing full suite):

```sh
uv run --locked --all-extras python -m unittest ada_piano.agent.test_reliability -v
uv run --locked --all-extras python -m unittest discover -s tests -q
```

The regressions are colocated here to keep every change within `ada_piano/agent/`.
The existing test discovery command does not automatically collect them.
Tests use fake playback, voice and model responses; physical MIDI output,
speaker behavior and live model responses still require manual validation.

## Scope and remaining limitations

No changes to camera, tutor, score import, MIDI, playback or voice modules.
Mistake episode counting, exact measure/tie boundaries, timestamp receipt,
attempt persistence hardening and speech-engine recovery remain separate work.

Playback exposes status but no execution identifier or control-generation
counter. Status polling cannot distinguish a complete stop/restart cycle that
happens between polls, or a Stop sound click while playback is still idle during
an announcement. Use ADA Stop to cancel an announced reference before it starts.
Eliminating these gaps requires a playback-module contract change, outside this
PR. A finished status means the MIDI scheduler finished, not proof that the
physical piano produced audible sound.
