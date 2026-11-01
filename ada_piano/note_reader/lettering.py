"""Smooth, large type for Tk, even where Tk itself cannot draw anti-aliased fonts.

Some Linux Pythons ship Tk without Xft, so every Tk font becomes one small bitmap
face at every size. Text a low-vision learner reads is therefore drawn by Pillow
from the bundled Atkinson Hyperlegible (Braille Institute of America, SIL Open Font
License, see assets/fonts/OFL.txt) and shown as a Tk image. Widgets keep their real
text for tests, copying and assistive tools. Without Pillow, Tk's own font is used.
"""

import base64
from functools import lru_cache
import io
from pathlib import Path

FONT_DIR = Path(__file__).resolve().parents[1] / "assets" / "fonts"
FACES = {"regular": "AtkinsonHyperlegible-Regular.ttf", "bold": "AtkinsonHyperlegible-Bold.ttf"}

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # the window still works with Tk's own fonts
    Image = ImageDraw = ImageFont = None


def available():
    return Image is not None and all((FONT_DIR / name).is_file() for name in FACES.values())


@lru_cache(maxsize=64)
def face(size, weight="regular"):
    return ImageFont.truetype(str(FONT_DIR / FACES[weight]), max(6, int(round(size))))


def measure(text, size, weight="regular", tracking=0):
    return face(size, weight).getlength(text) + tracking * max(0, len(text) - 1)


def wrap(text, size, width, weight="regular"):
    """Greedy word wrap measured with the real face; long words are kept whole."""
    lines = []
    for paragraph in text.splitlines() or [""]:
        line = ""
        for word in paragraph.split(" "):
            trial = f"{line} {word}" if line else word
            if line and measure(trial, size, weight) > width:
                lines.append(line)
                line = word
            else:
                line = trial
        lines.append(line)
    return lines


def _clip(lines, size, width, weight, max_lines):
    if not max_lines or len(lines) <= max_lines:
        return lines
    lines = lines[:max_lines]
    last = lines[-1]
    while last and width and measure(last + "…", size, weight) > width:
        last = last[:-1]
    lines[-1] = last.rstrip() + "…"
    return lines


@lru_cache(maxsize=256)
def png(text, size, color, weight="regular", width=None, max_lines=None, tracking=0, caret=None, leading=1.22):
    """PNG bytes of text in the bundled face on a transparent ground.

    width wraps to that many pixels; caret draws a text cursor before that character index.
    """
    font = face(size, weight)
    lines = wrap(text, size, width, weight) if width else (text.splitlines() or [""])
    lines = _clip(lines, size, width, weight, max_lines)
    ascent, descent = font.getmetrics()
    step = int(round(size * leading))
    widest = max((measure(line, size, weight, tracking) for line in lines), default=0)
    caret_width = max(2, int(round(size / 10)))
    image = Image.new("RGBA", (max(1, int(widest) + caret_width + 2), max(1, step * (len(lines) - 1) + ascent + descent)))
    draw = ImageDraw.Draw(image)
    for row, line in enumerate(lines):
        if tracking:
            x = 0.0
            for character in line:
                draw.text((x, row * step), character, font=font, fill=color)
                x += font.getlength(character) + tracking
        else:
            draw.text((0, row * step), line, font=font, fill=color)
    if caret is not None:
        x = int(measure(text[:caret], size, weight))
        draw.rectangle((x, 2, x + caret_width - 1, ascent + descent - 2), fill=color)
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


@lru_cache(maxsize=64)
def runs_png(parts, gap, padding=(0, 0)):
    """One baseline-aligned line from (text, size, color, weight) parts, gap pixels apart.

    padding adds transparent margins: Tk ignores padx/pady on buttons that show an image.
    """
    fonts = [face(size, weight) for _, size, _, weight in parts]
    ascent = max(font.getmetrics()[0] for font in fonts)
    descent = max(font.getmetrics()[1] for font in fonts)
    widths = [font.getlength(text) for (text, *_), font in zip(parts, fonts)]
    pad_x, pad_y = padding
    image = Image.new("RGBA", (max(1, int(sum(widths) + gap * (len(parts) - 1)) + 2 + pad_x * 2),
                               ascent + descent + pad_y * 2))
    draw = ImageDraw.Draw(image)
    x = float(pad_x)
    for (text, _, color, _), font, width in zip(parts, fonts, widths):
        draw.text((x, pad_y + ascent - font.getmetrics()[0]), text, font=font, fill=color)
        x += width + gap
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def _tk_photo(master, data):
    import tkinter as tk
    return tk.PhotoImage(master=master, data=base64.b64encode(data).decode("ascii"), format="png")


def photo(master, text, size, color, **style):
    """A Tk PhotoImage of the text; keep a reference to it while it is shown."""
    return _tk_photo(master, png(text, size, color, **style))


def photo_runs(master, parts, gap, padding=(0, 0)):
    return _tk_photo(master, runs_png(tuple(parts), gap, tuple(padding)))


@lru_cache(maxsize=128)
def shape_png(kind, width, height, color, line=0, radius=0):
    """Flat shapes with smooth edges (drawn 4x and scaled down): "dot", "ring" or "frame" (rounded outline)."""
    scale = 4
    w, h = max(1, int(round(width))), max(1, int(round(height)))
    image = Image.new("RGBA", (w * scale, h * scale))
    draw = ImageDraw.Draw(image)
    box = (0, 0, w * scale - 1, h * scale - 1)
    stroke = max(1, int(round(line * scale)))
    if kind == "dot":
        draw.ellipse(box, fill=color)
    elif kind == "ring":
        draw.ellipse(box, outline=color, width=stroke)
    else:
        draw.rounded_rectangle(box, radius=int(radius * scale), outline=color, width=stroke)
    buffer = io.BytesIO()
    image.resize((w, h), Image.Resampling.LANCZOS).save(buffer, "PNG")
    return buffer.getvalue()


def shape(master, kind, width, height, color, line=0, radius=0):
    return _tk_photo(master, shape_png(kind, round(width), round(height), color, round(line, 1), round(radius, 1)))


def _shape_image(kind, width, height, color, line=0, radius=0):
    return Image.open(io.BytesIO(shape_png(kind, round(width), round(height), color, round(line, 1),
                                           round(radius, 1)))).convert("RGBA")


@lru_cache(maxsize=256)
def card_png(title, subtitle, width, title_size, subtitle_size, title_color, subtitle_color,
             lamp=None, lamp_color=None, outline=None, padding=(16, 12)):
    """A fixed-width card: an optional lamp ("on" filled, "off" ring), a bold title and one subtitle line.

    outline draws a rounded frame (the selected state) in that colour. Transparent ground.
    """
    pad_x, pad_y = padding
    title_font, sub_font = face(title_size, "bold"), face(subtitle_size)
    lamp_size = round(title_size * 0.62) if lamp else 0
    text_x = pad_x + (lamp_size + round(title_size * 0.42) if lamp else 0)
    room = max(10, width - text_x - pad_x)
    title_lines = _clip(wrap(title, title_size, room, "bold"), title_size, room, "bold", 1)
    sub_lines = _clip(wrap(subtitle, subtitle_size, room), subtitle_size, room, "regular", 1) if subtitle else []
    t_ascent, t_descent = title_font.getmetrics()
    s_ascent, s_descent = sub_font.getmetrics()
    gap = round(subtitle_size * 0.25)
    height = pad_y * 2 + t_ascent + t_descent + ((gap + s_ascent + s_descent) if sub_lines else 0)
    image = Image.new("RGBA", (int(width), int(height)))
    if outline:
        line = max(3, round(title_size / 10))
        image.alpha_composite(_shape_image("frame", width, height, outline, line=line, radius=round(title_size * 0.4)))
    if lamp:
        top = pad_y + (t_ascent + t_descent - lamp_size) // 2
        ring = max(2.0, lamp_size / 6)
        image.alpha_composite(_shape_image("dot" if lamp == "on" else "ring", lamp_size, lamp_size, lamp_color,
                                           line=ring), (pad_x, top))
    draw = ImageDraw.Draw(image)
    draw.text((text_x, pad_y), title_lines[0], font=title_font, fill=title_color)
    if sub_lines:
        draw.text((text_x, pad_y + t_ascent + t_descent + gap), sub_lines[0], font=sub_font, fill=subtitle_color)
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def card(master, title, subtitle, width, title_size, subtitle_size, title_color, subtitle_color, **style):
    return _tk_photo(master, card_png(title, subtitle, int(width), round(title_size), round(subtitle_size),
                                      title_color, subtitle_color, **style))


def letter(widget, text, size, color, *, keep_text=True, fallback_size=None, **style):
    """Show text on a Label or Button as smooth type, keeping the widget's own text."""
    if available():
        image = photo(widget, text, size, color, **style)
        options = {"image": image, "compound": "none"}  # image shown, text kept
        if keep_text:
            options["text"] = text
        widget.configure(**options)
        widget._lettering = image  # Tk images vanish when Python drops the last reference
    else:
        options = {"font": ("", fallback_size or max(9, int(size * 0.6)), "bold" if style.get("weight") == "bold" else "normal")}
        if keep_text:
            options["text"] = text
        widget.configure(**options)
