# Standalone ADA chat and voice input

ADA can answer general piano questions without starting MIDI, camera, score
import, Audiveris or the deterministic tutor:

```sh
uv run --locked --extra agent python -m ada_piano.agent
```

Use the same uv command in Windows PowerShell:

```powershell
uv run --locked --extra agent python -m ada_piano.agent
```

The same controls are also available in the combined Note Reader's ADA Coach
tab. Score-specific actions require that host's reviewed, approved score and
the relevant MIDI hardware. Standalone chat cannot load, approve or play a
score. General learning advice is not evidence of what the learner played.

## Connect OpenAI

The panel shows whether a key is set and which model is selected. **API settings**
accepts a masked key and model for this session. Blank key means use
`OPENAI_API_KEY` from the app process environment. `ADA_OPENAI_MODEL` supplies
the initial model, defaulting to `gpt-4.1-mini`. Settings are kept in memory;
keys are never saved to a file or included in the transcript. The application
does not read Codex's credentials or automatically load a `.env` file.

For a persistent local key, store `OPENAI_API_KEY` in the Git-ignored `.env`
file and have uv load it explicitly (on Linux, restrict that file with
`chmod 600 .env`). Never paste a real key into tracked files or documentation.

```sh
uv run --locked --all-extras --env-file .env python -m ada_piano note-reader
```

For standalone chat, replace `ada_piano note-reader` with `ada_piano.agent`.
Replace a key shared in chat with a new key in the local `.env` file.

Press **Ask ADA** or Enter after typing into **Your message**. Sending a question
uses the OpenAI API and requires API account credit. A ChatGPT subscription does
not supply API credit. Errors distinguish missing/rejected keys, permissions,
unavailable models, quota, rate limits, connection failure and rejected request
formats without displaying secret-bearing API bodies. A rejected request format
may require a developer fix; the message does not assume the key is at fault.

No successful live API call has been verified by the offline automated tests.
To validate your account, enter your key and ask a simple general question such
as “How do I find middle C?” before trying score actions. Inspect the category
shown if it fails. The GUI stays responsive during requests.

## Microphone and activation

Windows uses installed English `System.Speech` dictation with the default
microphone; its recognition stays local. Linux uses PipeWire `pw-record`, or
ALSA `arecord`, and the existing OpenAI SDK to transcribe short audio clips with
`gpt-4o-mini-transcribe`. Linux listening sends audio to OpenAI and incurs API
charges. It starts only when you enable a microphone control. macOS retains text
chat and speech output; microphone recognition is not implemented there yet.

On Linux, choose **Speak responses** and **Hands-free: say “ADA …”** to converse.
Say “ADA, how do I find middle C?” and pause for about one second. Each recording
is capped at 12 seconds; silence and short clicks are discarded locally. The
energy gate is not a dedicated speech detector: use a quiet room and a headset.
In hands-free mode, recorded speech is transcribed before the ADA prefix is
checked, so background speech may be uploaded even if it does not trigger a reply.
Recordings are held in memory, not written to disk. Stop cancels recording and
pending transcription; cancelled requests may already have incurred charges.

PipeWire uses your default source unless `ADA_MIC_TARGET` names a source from
`wpctl status` / `wpctl inspect`. ALSA uses `default`, or `ADA_ALSA_DEVICE`.
Put these optional settings in `.env` and launch with `--env-file .env`.
Avoid choosing a loopback/monitor source when you intend to use a microphone.

- **Speak a question** listens for one utterance, for up to 12 seconds. Check
  the recognized text in the message box, then press **Ask ADA** to send it.
- **Hands-free: say “ADA …”** explicitly enables continuous listening. Say
  “ADA, how do I find middle C?” in one utterance. Only a question beginning
  with “ADA” or “Hey ADA” is automatically sent. Ordinary background speech is
  ignored by the chat dispatcher. This is a dictation-prefix filter, not a
  dedicated wake-word model; quiet surroundings and a headset help accuracy.
- “ADA stop” cancels the request and turns hands-free listening off. The Stop
  button also stops pending actions and speech. Voice Stop works while thinking
  and practicing, but microphone input pauses while ADA speaks or reference
  sound plays to avoid hearing itself. During those pauses use the Stop button.
- **Speak responses** enables OpenAI AI-generated speech (`gpt-4o-mini-tts`),
  initially using `marin` with a warm, patient-teacher style. Choose another voice
  from **Voice**, or choose **System (local)** for the original offline voice.
  Cloud speech uses the same session/API environment key as chat, sends reply
  text to OpenAI, and incurs a separate speech API charge. It is disabled by
  default. Chat still uses the Responses API; speech uses the Audio speech API,
  not a new chat or Realtime conversation. Windows recognition stays local;
  Linux recognition uses the transcription API.
  Typed chat remains
  usable when either microphone recognition or speech output is unavailable.

Low-confidence Windows results are discarded. The microphone starts only when enabled,
stops on Stop/window close, and has a visible status. Windows audio is not uploaded;
Linux audio is sent for transcription as described above. In hands-free mode the recognized question text is
sent through the usual coach request. The microphone subprocess does not inherit
`OPENAI_API_KEY`. Allow desktop microphone access in Windows yourself if needed,
select the correct default recording device, and install English speech
recognition if the local recognizer is missing. **Speak a question** retries a
failed microphone service explicitly.

Speech requests and WAV playback run outside Tk. Stop/window close cancels them,
discards stale speech and removes temporary WAV files. A cancelled API request
may already have incurred a charge. Replies over 4096 characters stay in text
instead of being truncated or triggering multiple paid speech requests.
Windows uses native WAV playback; macOS needs `afplay`, Linux uses `pw-play` or `aplay`.
No new Python dependency was added. Voice selection is session-only. Successful
cloud audio playback still requires a live API account and speakers.
The speech endpoint supplies raw PCM; ADA finalizes a mono 24kHz/16-bit WAV
locally so Windows playback does not depend on a streaming WAV header. Errors
identify API setup, speech generation/download, or native audio playback.
Implementation follows the [official OpenAI speech guide](https://developers.openai.com/api/docs/guides/text-to-speech).

## Verification

```sh
uv run --locked --all-extras python -m unittest ada_piano.agent.test_input -v
uv run --locked --all-extras python -m unittest ada_piano.agent.test_reliability -v
uv run --locked --all-extras python -m unittest ada_piano.agent.test_cloud_voice -v
uv run --locked --all-extras python -m unittest ada_piano.agent.test_linux_speech -v
uv run --locked --all-extras python -m unittest discover -s tests -q
```

The added tests are inside this module to keep edits within `ada_piano/agent/`.
GitHub CI runs these module tests explicitly alongside the main test suite.
Run the modules in separate processes: combining Tk input tests and worker-thread
tests can trigger a Tcl thread-cleanup crash on Linux. They exercise
fake recognition/model responses and real desktop Tk when available. Microphone
accuracy, speakers and a live API account still require a local trial.
