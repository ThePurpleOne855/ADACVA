---
name: ADA Piano Teacher
description: A tactile sign plate for a low-vision piano learner, readable from the piano bench.
colors:
  plate: "#15181F"
  raised: "#1E222C"
  raised-hover: "#2A3040"
  edge: "#3A4152"
  ink: "#F2EFE6"
  slate: "#B9BFCD"
  amber: "#FFB020"
  faded: "#8A90A0"
  quiet: "#868CA0"
typography:
  display:
    fontFamily: "Atkinson Hyperlegible"
    fontSize: "50px"
    fontWeight: 700
    lineHeight: 1.22
  headline:
    fontFamily: "Atkinson Hyperlegible"
    fontSize: "40px"
    fontWeight: 700
    lineHeight: 1.22
  title:
    fontFamily: "Atkinson Hyperlegible"
    fontSize: "30px"
    fontWeight: 700
    lineHeight: 1.22
    letterSpacing: "6px"
  reading:
    fontFamily: "Atkinson Hyperlegible"
    fontSize: "34px"
    fontWeight: 400
    lineHeight: 1.22
  input:
    fontFamily: "Atkinson Hyperlegible"
    fontSize: "28px"
    fontWeight: 400
    lineHeight: 1.22
  button:
    fontFamily: "Atkinson Hyperlegible"
    fontSize: "26px"
    fontWeight: 700
    lineHeight: 1.22
  body:
    fontFamily: "Atkinson Hyperlegible"
    fontSize: "24px"
    fontWeight: 400
    lineHeight: 1.22
  label:
    fontFamily: "Atkinson Hyperlegible"
    fontSize: "22px"
    fontWeight: 400
    lineHeight: 1.22
  key:
    fontFamily: "Atkinson Hyperlegible"
    fontSize: "20px"
    fontWeight: 400
    lineHeight: 1.22
rounded:
  none: "0px"
  ring: "14px"
  dot: "9999px"
spacing:
  hair: "3px"
  sixth: "4px"
  quarter: "6px"
  third: "8px"
  half: "12px"
  cell: "24px"
  double: "48px"
components:
  button-primary:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.plate}"
    typography: "{typography.button}"
    rounded: "{rounded.none}"
    padding: "15px 26px"
  button-primary-hover:
    backgroundColor: "#FFFFFF"
    textColor: "{colors.plate}"
  button-secondary:
    backgroundColor: "{colors.raised}"
    textColor: "{colors.ink}"
    typography: "{typography.button}"
    rounded: "{rounded.none}"
    padding: "15px 26px"
  button-secondary-hover:
    backgroundColor: "{colors.raised-hover}"
    textColor: "{colors.ink}"
  message-box:
    backgroundColor: "{colors.raised}"
    textColor: "{colors.ink}"
    typography: "{typography.input}"
    rounded: "{rounded.none}"
    height: "66px"
    padding: "0 12px"
  take-dot:
    backgroundColor: "{colors.ink}"
    rounded: "{rounded.dot}"
    size: "28px"
  take-dot-previous:
    backgroundColor: "{colors.faded}"
    rounded: "{rounded.dot}"
  measure-ring:
    textColor: "{colors.amber}"
    rounded: "{rounded.ring}"
  tools-tab:
    backgroundColor: "{colors.raised}"
    textColor: "{colors.ink}"
    padding: "9px 18px"
  tools-tab-selected:
    backgroundColor: "{colors.plate}"
    textColor: "{colors.ink}"
---

# Design System: ADA Piano Teacher

## Overview

**Creative North Star: "The Tactile Sign Plate"**

The home screen is one matte plate seen from the piano bench: raised ivory letters, a braille mark, and each take embossed beneath as a row of dots. Hierarchy comes from size alone. There is no header bar, no message bubbles, no chrome; the plate states what ADA is doing, what it just said, and how the last take went, then offers three keyed buttons. It is deliberately sparse because the learner reads it at arm's length between phrases while ADA speaks the same thing aloud.

"Embossed" is a metaphor carried by form, not by rendering. The plate is flat, dots are flat discs with smooth edges, and nothing is bevelled, shadowed or faked into relief. One amber signal owns live state; everything else is ivory, slate or faded on charcoal-blue. Every measurement descends from one 24 px cell, and every size multiplies by the learner's chosen text scale.

The tools workspace (F3) is the same instrument opened up: same palette, same focus language, same spacing, with denser native widgets for setup and troubleshooting.

**Key Characteristics:**
- One flat matte plate, ivory ink, one amber live signal that always travels with a word.
- Atkinson Hyperlegible throughout the plate, drawn smooth from the bundled face.
- Size-only hierarchy, scaled live from 0.8 to 1.75.
- Takes shown as flat dots, one per note, grouped by measure; the measure to fix ringed amber.
- One 24 px cell sets every space.
- Every button names its key; focus is an ivory ring that is always visible.

## Colors

A near-monochrome night plate: charcoal-blue ground, warm ivory ink, cool slate for secondary text, and a single saturated amber held back for live state.

### Primary
- **Signal Amber** (amber): owns every live state and nothing else on the plate: the lamp and state word for Listening, Recording, Guided practice, Speaking, Thinking and Hearing you, and the ring around the measure that needs work. 9.6:1 on the plate.

### Neutral
- **Matte Plate** (plate): the ground of the home screen and the tools workspace; also the gap colour inside focus rings and the ink on the ivory primary button.
- **Raised Field** (raised): fills that hold input or action: the message box, secondary buttons, tools text areas, lists, entries and unselected tabs. Raised in name only; it is a tonal step, not a lift.
- **Raised Hover** (raised-hover): hover/active fill for raised buttons, tabs and scrollbars.
- **Edge** (edge): the resting border of the message box, the tools border colour, text selection and scrollbar thumbs.
- **Ivory Ink** (ink): primary text, ADA's words, the braille mark, current-take dots and score, the primary button fill, and every focus indicator. 15.3:1 on the plate.
- **Slate** (slate): secondary text: piano status, piece line, take labels, the sentence under the state word, placeholder, key hints on secondary buttons, the idle lamp ring, unselected tab text. 9.4:1 on the plate.
- **Faded** (faded): the previous take only (its dots and the not-reached dots of either take). 5.6:1; it is the comparison layer, never the only carrier of a reading.
- **Quiet** (quiet): disabled text in the tools workspace only.

Contrast figures are those stated in the source; a WCAG recomputation lands at or slightly above each.

### Named Rules
**The One Signal Rule.** Amber means "live now". It appears only for the six live states and the ringed measure, and it always sits beside a word (the state word, or the measure note under the take). Amber never decorates and never marks a setting.

**The Seven-to-One Rule.** Anything the learner must read is ivory or slate on the plate (at least 7:1). Faded is reserved for the previous take, which repeats information the current take already carries.

## Typography

**Display Font:** Atkinson Hyperlegible Bold (Braille Institute, SIL OFL; bundled with its licence)
**Body Font:** Atkinson Hyperlegible Regular
**Fallback:** Tk's default face, at roughly 60 percent of the nominal size, only when Pillow or the font files are missing.

**Character:** A legibility face with open, unambiguous letterforms (distinct 0/O, 1/l/I). Bold speaks state; regular speaks ADA. Tk on this Linux build has no Xft, so plate text is rasterised by Pillow and shown as images while widgets keep their real text for tests and copying.

### Hierarchy
All sizes below are at text scale 1.0; every one multiplies by the live scale (0.8, 0.9, 1.0, 1.15, 1.3, 1.5, 1.75), changed with Ctrl +/-, Ctrl 0, or by voice. Wrapped text uses a 1.22 line step.
- **Display** (bold, 50 px): the state word only (Listening, Recording, Ready...), amber when live, ivory otherwise.
- **Headline** (bold, 40 px): the current take's score ("29 / 30"). The previous take's score drops to 26 px in slate.
- **Reading** (regular, 34 px stepping down to 24 px): ADA's latest words, the largest reading text, filling their block.
- **Title** (bold, 30 px, 6 px tracking): the word ADA beside the braille mark; also the tools heading.
- **Input** (regular, 28 px): typed text in the message box; the placeholder is 26 px in slate.
- **Button** (bold, 26 px) with **Key** (regular, 20 px) on one baseline, 14 px apart.
- **Body** (regular, 24 px): the instruction sentence under the state, the piece line, and the measured note under the current take (26 px in the compact line).
- **Label** (regular, 22 px): piano status, "Last take" / "This take", the empty-takes prompt.
- **Tools tab** (bold, 20 px, ivory): tab labels in the tools workspace.

### Named Rules
**The Fill-Before-Clip Rule.** ADA's words take the largest size from 34 down to 24 px at which the whole message fits its block; only below 24 px does the last line end in an ellipsis. The measured note is never clipped.

**The Size-Is-Rank Rule.** Rank is expressed by size and weight, not by colour, boxes or rules. A new element finds its place on the ramp above.

## Layout

A single column on a plate inset by two cells left and right and one cell top and bottom (48 px / 24 px). Gaps between bands are a cell or half a cell (24 / 12 px); smaller spacing uses thirds, quarters and sixths of the cell (8 / 6 / 4 px). The packing order is priority: controls at the bottom, then the top row (braille mark + ADA at left, piano status at right), the state line (lamp + word), an optional instruction sentence, ADA's words, and the takes. The takes yield room before ADA's words do, and ADA's words never get less than three lines.

ADA's words are shown alone: no history and no scrollbar on the plate; the full conversation lives in Tools > ADA Coach.

**Compact windows.** When the home window is under 760 px tall (default 900 x 700, minimum 700 x 540) the dot rows are removed and a single measured line ("29 / 30 · Measure 2: ...") sits under ADA's words in slate. The tools workspace opens at 1400 x 850 with a 1100 x 760 minimum.

**The Takes Grid.** Dot spacing derives from one diameter (up to 28 px, never below 18 px, or 9 px in compact): 0.42 gap between dots, 0.38 ring padding, 0.9 between measures. When a take does not fit, whole measures wrap onto balanced lines (8 measures on two lines is 4 + 4); dots never shrink below the floor.

### Named Rules
**The One Cell Rule.** Every space is the 24 px cell or a simple fraction of it. Do not introduce a free-standing spacing value.

## Elevation & Depth

Flat by doctrine. There are no shadows, bevels, gradients or relief anywhere. Depth is a tonal step only: plate, then raised field, then raised-hover. "Embossed" takes are flat discs; the metaphor is in the dot grammar, not in lighting.

### Named Rules
**The No-Faked-Relief Rule.** If an element looks lifted, it is wrong. Use a tonal step or an outline instead.

## Shapes

Rectangles with square corners for every field and button; perfect circles for dots, the lamp and the braille mark; one rounded outline (14 px radius, 4 px stroke, amber) for the ringed measure. Shapes are drawn at 4x and downsampled so edges are smooth where Tk's own ovals are jagged.

## Components

### Buttons
Large, square, keyed.
- **Shape:** square corners, no border.
- **Primary (Talk to ADA):** ivory fill, plate-coloured bold label, key hint in a darker graphite (#4A4F5C, 7.1:1 on ivory). Hover turns pure white.
- **Secondary (Stop, Tools):** raised fill, ivory label, slate key hint; hover raised-hover.
- **Key hint:** every button carries its key (F1, Esc, F3) on the label's baseline. Without smooth type the label reads "Talk to ADA (F1)".
- **Focus:** a 3 px ivory ring separated from the button by a 3 px plate-coloured gap, so the ring reads on the ivory primary as well.

### Message box
- **Style:** raised field, square, 66 px tall (scaled), 3 px edge border.
- **Focus:** the border turns ivory. Typed text is drawn large (Input role) with a drawn caret that stays in view while typing past the edge.

### State line (signature)
A flat lamp beside the state word. Live: an amber disc and amber word. Idle: a hollow slate ring and ivory word. A sentence in slate appears under it only when it adds an instruction (Recording, Guided practice, a voice error, Ready), never in compact windows.

### Braille mark (signature)
"ADA" in real Grade 1 braille (dots 1 / 1-4-5 / 1), ivory flat dots, beside the word ADA in bold tracked capitals.

### Embossed takes (signature)
- **Dots:** one per expected note, grouped by measure. Filled disc = correct; hollow ring = wrong or missed; small disc (30 percent radius, faded) = not reached.
- **Two rows:** "Last take" above in faded at 74 percent of the dot size, "This take" below in ivory, score at right.
- **Ring:** the first measure needing work is ringed amber on the current take; the measured note sits under it in ivory.
- **Motion:** a new take presses in measure by measure, 70 ms per measure; a new take mid-animation restarts it.

### Tools workspace
- **Tabs:** raised, slate text when unselected; selected tab sits on the plate. Labels are drawn in the Tool tab role and follow the text size.
- **Native widgets:** buttons raised with an ivory focus border; entries, lists, text and tree views on raised fields; selection uses edge; scrollbars edge on plate.
- **Typography boundary:** apart from tab labels and the main heading, tools widgets render in Tk's bitmap face because this Tk build lacks Xft. That text is outside this world's typography until a Tk with Xft is available; it is not a model for new surfaces.

## Do's and Don'ts

### Do:
- **Do** derive every space from the 24 px cell.
- **Do** pair amber with a word, and use it only for the six live states and the ringed measure.
- **Do** scale every size with the learner's text scale.
- **Do** show each button's key on the button.
- **Do** keep an ivory focus ring with a plate-coloured gap on every focusable control.
- **Do** draw readable text from the bundled Atkinson Hyperlegible, keeping the widget's real text.

### Don't:
- **Don't** add shadows, bevels, gradients or faked relief; embossing is expressed by flat dots.
- **Don't** carry meaning by colour alone: missed is a ring, not a red dot; live is a word, not only a lamp.
- **Don't** add history, bubbles, header bars or scrollbars to the plate.
- **Don't** shrink take dots below the floor; wrap whole measures instead.
- **Don't** ellipsize ADA's words above 24 px.
- **Don't** use faded for anything the learner must read first.
