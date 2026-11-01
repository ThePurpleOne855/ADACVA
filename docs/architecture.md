# ADA Piano Teacher — architecture

Every check runs locally and gives the same answer every time. The keyboard, camera and tutor work
offline. The OpenAI coach is an optional layer that explains results the local engine has already
produced. It never decides whether a note was right.

```plantuml
@startuml
skinparam RectangleBackgroundColor #eef2fb
skinparam RectangleBorderColor #5b6b8c
skinparam RectangleFontColor #1f2937
skinparam ComponentBackgroundColor #eef2fb
skinparam ComponentBorderColor #5b6b8c
skinparam ComponentFontColor #1f2937
skinparam ClassBackgroundColor #eef2fb
skinparam ClassBorderColor #5b6b8c
skinparam ClassFontColor #1f2937
skinparam UsecaseBackgroundColor #eef2fb
skinparam UsecaseBorderColor #5b6b8c
skinparam UsecaseFontColor #1f2937
skinparam DatabaseBackgroundColor #eef2fb
skinparam DatabaseBorderColor #5b6b8c
skinparam DatabaseFontColor #1f2937
skinparam NodeBackgroundColor #eef2fb
skinparam NodeBorderColor #5b6b8c
skinparam NodeFontColor #1f2937
skinparam ActorBackgroundColor #eef2fb
skinparam ActorBorderColor #5b6b8c
skinparam ActorFontColor #1f2937
skinparam StateBackgroundColor #eef2fb
skinparam StateBorderColor #5b6b8c
skinparam StateFontColor #1f2937
skinparam ArtifactBackgroundColor #eef2fb
skinparam ArtifactBorderColor #5b6b8c
skinparam ArtifactFontColor #1f2937
skinparam CloudBackgroundColor #eef2fb
skinparam CloudBorderColor #5b6b8c
skinparam CloudFontColor #1f2937
skinparam FolderBackgroundColor #eef2fb
skinparam FolderBorderColor #5b6b8c
skinparam FolderFontColor #1f2937
skinparam PackageBackgroundColor #eef2fb
skinparam PackageBorderColor #5b6b8c
skinparam DefaultFontColor #1f2937
skinparam ArrowColor #5b6b8c
skinparam ArrowFontColor #1f2937
skinparam NoteBackgroundColor #dfe5fb
skinparam NoteBorderColor #5b6b8c
skinparam NoteFontColor #1f2937
skinparam stereotypeABackgroundColor #d9e3f4
skinparam stereotypeABorderColor #5b6b8c
skinparam stereotypeCBackgroundColor #d9e3f4
skinparam stereotypeCBorderColor #5b6b8c
skinparam stereotypeEBackgroundColor #d9e3f4
skinparam stereotypeEBorderColor #5b6b8c
skinparam stereotypeIBackgroundColor #d9e3f4
skinparam stereotypeIBorderColor #5b6b8c
title ADA Piano Teacher — component view

node "YPT-300 keyboard\n(USB MIDI via mioXC)" as kbd
node "Webcam" as cam_hw
node "Microphone" as mic
node "Speakers" as speakers
cloud "OpenAI API\n(optional)" as openai
component [Audiveris\n(PDF to MusicXML)] as audiveris

package "Entry" {
  component [cli\nada-piano command] as cli
}

package "Apps (Tk windows)" {
  component [note_reader\nNote Reader GUI] as nr
  component [agent\nvoice coach] as agent
  component [score_import\nPDF import + review] as si
  component [camera\nhand-tracking panel] as camera
}

package "Local engine (deterministic)" {
  component [ai_tutor\nperformance checks] as tutor
  component [music_sheet\nexercise model] as ms
  component [pieces\npre-checked pieces] as pieces
  component [sessions\nsession export] as sessions
}

package "Device adapters" {
  component [sound_sensor\nMIDI in] as sensor
  component [playback\nMIDI out] as playback
  component [voice\nespeak-ng / Piper TTS] as voice
}

database "Session files\n(local disk)" as files

cli --> nr : note-reader
cli --> camera : camera
cli --> sensor : midi-monitor

kbd --> sensor : MIDI notes
kbd --> nr : MIDI notes
playback --> kbd : reference playback
cam_hw --> camera : frames (MediaPipe)
mic --> agent : speech (faster-whisper)
voice --> speakers : spoken feedback

nr --> tutor
nr --> agent
nr --> camera
nr --> si
nr --> sessions
sessions --> files : atomic write

tutor --> sensor
tutor --> voice
agent --> tutor : reads results
agent --> voice
agent --> openai : coaching (optional)

si --> audiveris : PDF scores
si --> playback
pieces --> si

note right of ms
  shared exercise model:
  imported by note_reader, agent, ai_tutor,
  score_import, camera and cli
end note
@enduml
```

**How to read it:** arrows run from the importer to the thing it uses. This view leaves out
`music_sheet` imports (see the note) and a few back-references (`voice` → `agent`,
`playback` → `score_import`, `score_import` → `agent`) to keep the layout readable.

**Viewing:** open this file in the [docu.md Markdown Viewer](https://docu.md). GitHub shows the
source only. Use [`architecture.png`](architecture.png) there instead.

Regenerate the PNG after editing the diagram:

```bash
npx @markdown-viewer/documd docs/architecture.md --assets /tmp/figs --chrome /usr/bin/chromium
cp /tmp/figs/architecture-01-plantuml.png docs/architecture.png
```
