---
version: 1
slug: "ada-piano-note-reader-accessible-py"
primary_target: "ada_piano/note_reader/accessible.py"
related_targets: ["ada_piano/note_reader/gui.py"]
---

# Home screen with integrated tools (accessible view)

Scope: the desktop window's home screen (ada_piano/note_reader/accessible.py), which now carries the tools too: Practice, Piano, Pieces, Camera, and Voice & AI, one at a time. The F3 workspace stays only as an advanced fallback. Visitor mode: Operate.

Audience and job: a low-vision piano learner reads this screen at arm's length from the keyboard while ADA speaks. Task: know at a glance what is connected and what ADA is doing, practise, and change a setting without hunting through panels. Constraints: very large text, 7:1 contrast, only a few big buttons, one tool open at a time, every action also a voice command and a keyboard shortcut. Confirmed 2026-11-01: all four tool groups belong on the main screen; the voice coach must always be active, woken by the word "ADA".

## Direction contract

THESIS: The tactile sign plate becomes a building directory: a rail of five labelled doors, each with a lamp that says whether that room is ready, and the plate shows one room at a time. It refuses both the tabbed settings dialog and the everything-on-one-page dashboard.

OWN-WORLD: Unchanged from DESIGN.md: flat matte plate #15181F, raised #1E222C rail and buttons, ivory ink #F2EFE6 in Atkinson Hyperlegible, slate #B9BFCD secondary, faded #8A90A0 for the previous take, amber #FFB020 only for live states and always with a word; flat smooth dots; one 24 px cell sets every space.

STORY: The learner glances left and reads, top to bottom, which rooms are ready (piano connected, last key played; piece loaded; camera off; coach ready and listening for "ADA"), then reads the open room on the right. They say "ADA, ..." at any time, or press a rail key, and the room changes; Escape always returns to Practice.

FIRST VIEWPORT: Left rail, about 31 percent of the width: braille ADA and the word ADA at the top, then five buttons stacked, each a lamp, a 30 px label and a 21 px live status line (Practice, Piano, Pieces, Camera, Voice & AI); the open one is filled and outlined in ivory. Right: the open room. Practice shows the state line, ADA's latest words filling the room, the piece line, the takes, the message box, and Talk and Stop. Every other room shows its status in large type, a few big buttons, and the exact words to say for each action.

FORM: Status rail, position 5 on the ordered list of seven structures (tool keys, sign board, big tabs, spoken menu, status rail, command card, stacked sections); seed:f6884859f6396563. Kept from declined challengers: one complete state at a time, never a half-scrolled view (vertical feed); every tool always listed (tabbed manual); states stay visible instead of vanishing (ticket wallet).

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
