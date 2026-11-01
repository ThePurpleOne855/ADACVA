---
version: 1
slug: "ada-piano-note-reader-accessible-py"
primary_target: "ada_piano/note_reader/accessible.py"
related_targets: ["ada_piano/note_reader/gui.py"]
---

# Home screen (accessible view) and tools workspace

Scope: the desktop window's home view (ada_piano/note_reader/accessible.py) and the F3 tools workspace that shares its world. Visitor mode: Operate.

Audience and job: a low-vision piano learner reads this screen at arm's length from the keyboard, between phrases, while ADA speaks. Task: know what ADA is doing, what it just said, and how the last take went; then speak (F1), stop (Esc) or open tools (F3). Constraints: very large text, 7:1 contrast, few controls, every action also voice and keyboard; Tk on Linux has no Xft, so display text is drawn from a bundled face.

Unattended choice: the decision page went unanswered for 36 minutes on 2026-11-01, so the assigned direction was built; the user can still pick an alternate.

## Direction contract

THESIS: The home screen is a tactile sign plate: one matte plate, raised ivory letters readable from the piano bench, and each take embossed beneath as dots. It refuses the chat-app arrangement (header bar, message bubbles, input strip) the category ships.

OWN-WORLD: Flat matte charcoal-blue plate #15181F, no bevel and no faked relief; ivory ink #F2EFE6 in Atkinson Hyperlegible (Braille Institute), bold for state, regular for speech; slate #B9BFCD for secondary; faded #8A90A0 (5.6:1) for the previous take; one amber signal #FFB020 owns every live state and always travels with a word; dots are flat with smooth edges, filled for a correct note and a hollow ring for a missed one; one 24 px cell sets every space; "ADA" in real Grade 1 braille beside bold capitals.

STORY: The learner glances over, reads what ADA is doing and just said, sees the take measure by measure with the trouble spot ringed, and speaks or presses F1 to go on.

FIRST VIEWPORT: Top row: braille ADA and the word ADA, piano status at right. State line with amber lamp and word; a sentence under it only when it adds an instruction (recording, guided practice, a voice error). ADA's latest words alone, the largest reading text, filling all the room between the state and the takes (never less than three lines' worth); the words step down from 34 to 24 px to fit whole before any ellipsis; no history and no scrollbar on the plate (the full conversation lives in Tools > ADA Coach). In windows under 760 px tall the dot rows give way to one measured line under ADA's words (score and the measure to fix). Piece line. Embossed takes: last take faded above this take with smaller dots, one dot per note grouped by measure, the measure needing work ringed amber, score at right. Bottom: message box, Talk (F1, ivory primary), Stop (Esc), Tools (F3).

FORM: Braille embossed card rendered as a tactile sign plate, position 5 on the ordered list of seven; seed:2c22662f5db09373. Raises: hierarchy by size alone with live text size (type specimen); two hard rows to compare takes (cassette j-card); one cell unit (Crouwel grid); one accent owns live state (metro tiles); ring the measure that matters (event catalog).

TOOLS WORKSPACE: shares the palette, focus rings and spacing; tab labels and the main heading use the plate's type and follow the text size. Its other widgets stay in Tk's own bitmap face until the app runs on a Tk built with Xft; that remainder is recorded as outside this world's typography.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
