"""The tools workspace in the home screen's world: matte plate, ivory ink, clear focus.

Tk's own widgets keep their behaviour; only colours, spacing and focus change, so the
setup screens read as part of the same instrument as the tactile sign plate.
"""

from tkinter import ttk

from ada_piano.note_reader.accessible import EDGE, INK, PLATE, RAISED, RAISED_HOVER, SLATE

QUIET = "#868CA0"  # disabled text: 4.75:1 on raised fields, 5.3:1 on the plate
SELECTION = "#3A4152"


def style_tools(root):
    """Apply the plate palette to ttk and to classic Tk widgets created afterwards."""
    root.configure(background=PLATE)
    for pattern, value in (("*Text.background", RAISED), ("*Text.foreground", INK), ("*Text.insertBackground", INK),
                           ("*Text.selectBackground", SELECTION), ("*Text.highlightColor", INK),
                           ("*Text.highlightBackground", PLATE), ("*Listbox.background", RAISED),
                           ("*Listbox.foreground", INK), ("*Listbox.selectBackground", SELECTION),
                           ("*Listbox.selectForeground", INK), ("*Entry.background", RAISED),
                           ("*Entry.foreground", INK), ("*Entry.insertBackground", INK),
                           ("*Canvas.background", PLATE), ("*Canvas.highlightThickness", 0),
                           ("*Toplevel.background", PLATE), ("*Label.background", PLATE),
                           ("*Label.foreground", INK), ("*Frame.background", PLATE)):
        root.option_add(pattern, value)
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(".", background=PLATE, foreground=INK, fieldbackground=RAISED, bordercolor=EDGE,
                    lightcolor=RAISED, darkcolor=PLATE, troughcolor=PLATE, selectbackground=SELECTION,
                    selectforeground=INK, insertcolor=INK, focuscolor=INK, arrowcolor=INK)
    style.map(".", foreground=[("disabled", QUIET)])
    style.configure("TFrame", background=PLATE)
    style.configure("TLabel", background=PLATE, foreground=INK)
    style.configure("TNotebook", background=PLATE, borderwidth=0, tabmargins=(12, 10, 12, 0))
    style.configure("TNotebook.Tab", background=RAISED, foreground=SLATE, padding=(18, 9), borderwidth=0)
    style.map("TNotebook.Tab", background=[("selected", PLATE), ("active", RAISED_HOVER)],
              foreground=[("selected", INK), ("active", INK)])
    style.configure("TButton", background=RAISED, foreground=INK, padding=(14, 7), borderwidth=1, relief="flat")
    style.map("TButton", background=[("pressed", EDGE), ("active", RAISED_HOVER)],
              bordercolor=[("focus", INK)], lightcolor=[("focus", INK)], darkcolor=[("focus", INK)])
    for name in ("TEntry", "TCombobox", "TSpinbox"):
        style.configure(name, fieldbackground=RAISED, foreground=INK, insertcolor=INK, padding=6, arrowcolor=INK)
        style.map(name, fieldbackground=[("readonly", RAISED), ("disabled", PLATE)],
                  foreground=[("readonly", INK)], bordercolor=[("focus", INK)], lightcolor=[("focus", INK)])
    style.configure("TCheckbutton", background=PLATE, foreground=INK, indicatorbackground=RAISED,
                    indicatorforeground=INK)  # amber stays reserved for live states
    style.map("TCheckbutton", background=[("active", PLATE)], indicatorbackground=[("selected", RAISED)])
    style.configure("Treeview", background=RAISED, fieldbackground=RAISED, foreground=INK, rowheight=26,
                    borderwidth=0)
    style.map("Treeview", background=[("selected", SELECTION)], foreground=[("selected", INK)])
    style.configure("Treeview.Heading", background=PLATE, foreground=SLATE, relief="flat", padding=6)
    for name in ("TScrollbar", "Vertical.TScrollbar", "Horizontal.TScrollbar"):
        style.configure(name, background=EDGE, troughcolor=PLATE, arrowcolor=SLATE, bordercolor=PLATE,
                        lightcolor=EDGE, darkcolor=EDGE, gripcount=0, arrowsize=14)
        style.map(name, background=[("active", RAISED_HOVER), ("pressed", RAISED_HOVER)])
    style.configure("TPanedwindow", background=PLATE)
    style.configure("Sash", background=EDGE)
    return style
