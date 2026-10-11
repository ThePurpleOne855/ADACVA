"""Pre-checked practice pieces that can be loaded by name, without visual review.

Each catalog entry was compared note by note with its source before being added,
so loading one does not require the learner to inspect a preview table.
"""

from dataclasses import dataclass
import json
from pathlib import Path
import re
import unicodedata

from ada_piano.score_import.review import ReviewedScore

FOLDER = Path(__file__).parent


@dataclass(frozen=True)
class Piece:
    id: str
    title: str
    composer: str
    file: Path
    aliases: tuple[str, ...]
    part: str
    written_order: bool
    default_tempo: int
    hands: dict
    passages: dict
    verified: str

    def describe(self):
        return {"id": self.id, "title": self.title, "composer": self.composer,
                "hands": list(self.hands), "default_tempo": self.default_tempo,
                "passages": {name: spec[2] for name, spec in self.passages.items()}}


def _plain(text):
    text = unicodedata.normalize("NFKD", text.casefold())
    return re.sub(r"[^a-z0-9 ]+", " ", "".join(c for c in text if not unicodedata.combining(c))).strip()


def catalog(folder=FOLDER):
    data = json.loads((Path(folder) / "catalog.json").read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError("Unsupported piece catalog.")
    return [Piece(item["id"], item["title"], item["composer"], Path(folder) / item["file"],
                  tuple(item["aliases"]), item["part"], item["written_order"], item["default_tempo"],
                  dict(item["hands"]), dict(item["passages"]), item["verified"])
            for item in data["pieces"]]


def find(name, pieces=None):
    """Match an id, title or spoken alias such as "fur elise"; None if unclear."""
    pieces = catalog() if pieces is None else pieces
    wanted = _plain(name)
    if not wanted:
        return None
    for piece in pieces:
        if wanted in {piece.id, _plain(piece.id), _plain(piece.title)}:
            return piece
    padded = f" {wanted} "
    hits = [p for p in pieces if any(f" {_plain(a)} " in padded for a in p.aliases)]
    return hits[0] if len(hits) == 1 else None


def load(piece, passage="whole", hands=None):
    """Return an approved ReviewedScore for a catalog passage and hand."""
    if passage not in piece.passages:
        raise ValueError(f"{piece.title} has no passage {passage!r}. Choose: {', '.join(piece.passages)}.")
    hands = hands or next(iter(piece.hands))
    if hands not in piece.hands:
        raise ValueError(f"{piece.title} supports: {', '.join(piece.hands)} hand(s).")
    start, end, _ = piece.passages[passage]
    review = ReviewedScore(piece.file, part=piece.part, staff=piece.hands[hands], voice=None,
                           start_measure=start, end_measure=end, written_order=piece.written_order)
    review.approve()
    review.piece = {"id": piece.id, "passage": passage, "hands": hands, "verified": piece.verified}
    return review
