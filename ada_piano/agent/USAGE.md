# Standalone ADA chat and voice input

ADA can answer general piano questions without starting MIDI, camera, score
import, Audiveris or the deterministic tutor:

```sh
uv run --extra agent python -m ada_piano.agent
```

From an already installed Windows virtual environment:

```powershell
.\.venv\Scripts\python.exe -m ada_piano.agent
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
microphone. There are no new Python packages and no audio-upload service.
Other operating systems retain text chat and existing speech output; native
microphone recognition is not implemented there yet.

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
  not a new chat or Realtime conversation. The microphone stays local.
  Typed chat remains
  usable when either microphone recognition or speech output is unavailable.

Low-confidence results are discarded. The microphone starts only when enabled,
stops on Stop/window close, and has a visible status. Audio is not saved or sent
to OpenAI by this service. In hands-free mode the recognized question text is
sent through the usual coach request. The microphone subprocess does not inherit
`OPENAI_API_KEY`. Allow desktop microphone access in Windows yourself if needed,
select the correct default recording device, and install English speech
recognition if the local recognizer is missing. **Speak a question** retries a
failed microphone service explicitly.

Speech requests and WAV playback run outside Tk. Stop/window close cancels them,
discards stale speech and removes temporary WAV files. A cancelled API request
may already have incurred a charge. Replies over 4096 characters stay in text
instead of being truncated or triggering multiple paid speech requests.
Windows uses native WAV playback; macOS needs `afplay`, Linux needs `aplay`.
No new Python dependency was added. Voice selection is session-only. Successful
cloud audio playback still requires a live API account and speakers.
The speech endpoint supplies raw PCM; ADA finalizes a mono 24kHz/16-bit WAV
locally so Windows playback does not depend on a streaming WAV header. Errors
identify API setup, speech generation/download, or native audio playback.
Implementation follows the [official OpenAI speech guide](https://developers.openai.com/api/docs/guides/text-to-speech).

## Verification

```sh
python -m unittest ada_piano.agent.test_input ada_piano.agent.test_reliability ada_piano.agent.test_cloud_voice -v
python -m unittest discover -s tests -q
```

The added tests are inside this module to keep edits within `ada_piano/agent/`.
Existing GitHub test discovery does not automatically run them. They exercise
fake recognition/model responses and real desktop Tk when available. Microphone
accuracy, speakers and a live API account still require a local trial.
