# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Python 3.11+ desktop app built with Tkinter/ttk (Linux first; Windows voice input supported). On 2026-11-01 the user chose to keep Python for the redesign; a React Native rewrite and a web front end were offered and declined for now. The Platform field reads `web` only because the product schema has no desktop value: the app is a native Tk desktop window, so web-only checks (the HTML/CSS design detector) do not apply.

## Users

Blind and low-vision people learning piano at home on a MIDI keyboard (currently a Yamaha YPT-300 through an iConnectivity mioXC USB interface). ADA speaks everything, and the learner mostly talks to it. The person who reads the screen is the low-vision learner, up close (confirmed 2026-11-01).

## Product Purpose

ADA ("Ada") runs a complete practice loop without sighted help: choose a checked piece, hear a reference, record a play-through or practise note by note, get measured feedback (wrong, missed and extra notes, timing, by measure), ask the coach what to do next, and retry. Success means the learner practises independently and plays the passage more accurately than before.

## Positioning

Feedback comes from deterministic measurement of what the MIDI keyboard actually received, scored against an approved score. The AI coach (Meta Muse Spark or OpenAI) only explains that evidence; it never decides what was played. Optional camera analysis reports fingertip proximity with its uncertainty, never claims about correct fingering.

## Operating Context

A laptop beside the keyboard at home. Voice through the laptop microphone with an offline recogniser (faster-whisper) and offline natural voice (Piper); cloud speech and coaching are optional. Keyboard shortcuts: F1 talk, Escape stop, F3 tools, F5 record, F6 results, F7 camera. A tools workspace (piano keyboard view, MIDI input and output, reference playback, camera, score import, coach chat) serves setup and troubleshooting.

## Capabilities and Constraints

- Note and timing evaluation stays deterministic and local; AI is optional and explains only.
- The core works offline once local voice models are installed; missing hardware (camera, cloud keys) must never block practice.
- Tk exposes little to screen readers, so ADA speaks every status itself; the visual UI supports, never replaces, speech.
- Every action stays reachable by voice and keyboard. The automated suite (260+ tests, plus the agent module tests) drives the real Tk widgets.

## Brand Commitments

- Name: ADA; the voice introduces itself as "Ada".
- Volunteered by the user on 2026-10-13 (not yet confirmed as binding): "minimize the UI and keep it simple; a blind person does not need a UI, but let's make something like an ethereal background."

## Evidence on Hand

Checked catalog pieces (Für Elise, Ode to Joy) under `ada_piano/pieces`, README, and synthetic test fixtures. There are no user testimonials, studies or usage numbers; do not invent any.

## Product Principles

1. Evidence before advice: show and say what was measured before what the AI thinks.
2. Voice first, screen second: the screen mirrors what ADA says, in fewer words.
3. Legible and calm over clever: one thing at a time, nothing that needs fine vision.
4. Offline by default; cloud is an upgrade, never a dependency.
5. Practice never waits on optional hardware.

## Accessibility & Inclusion

The screen reader is a low-vision learner: very large text, strong contrast (aim for 7:1), very few controls on the home screen, generous spacing, an always-visible focus indicator, and no meaning carried by colour alone. Every visible action is also a voice command and a keyboard shortcut.
