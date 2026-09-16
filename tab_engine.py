"""
tab_engine.py  —  Headless core logic for the Guitar Tab editor.

This module contains ZERO GUI code so it can be unit-tested in a headless
environment.  The Tkinter GUI (guitar_tab_app.py) is a thin layer on top.

Model: a character grid.  Each string is a list of single characters.
The classic ASCII tab look:

    e|--3---5-----|
    B|------------|
    G|------------|
    D|------------|
    A|------------|
    E|------------|

Techniques are simply characters placed in the grid, exactly how they appear
in real ASCII tabs (h p b r / \\ ~ x etc.), so exports are always faithful.
"""

from __future__ import annotations
import json
import copy

EMPTY = "-"

# ----------------------------------------------------------------------------
# Tunings  (index 0 = highest/thinnest string shown at the TOP of the tab)
# ----------------------------------------------------------------------------
TUNINGS: dict[str, list[str]] = {
    "Standard (E A D G B e)":      ["e", "B", "G", "D", "A", "E"],
    "Drop D (D A D G B e)":        ["e", "B", "G", "D", "A", "D"],
    "Half Step Down (Eb Ab Db Gb Bb eb)": ["eb", "Bb", "Gb", "Db", "Ab", "Eb"],
    "Full Step Down (D G C F A d)":["d", "A", "F", "C", "G", "D"],
    "Drop C (C G C F A d)":        ["d", "A", "F", "C", "G", "C"],
    "Open G (D G D G B d)":        ["d", "B", "G", "D", "G", "D"],
    "Open D (D A D F# A d)":       ["d", "A", "F#", "D", "A", "D"],
    "DADGAD (D A D G A d)":        ["d", "A", "G", "D", "A", "D"],
    "7-String (B E A D G B e)":    ["e", "B", "G", "D", "A", "E", "B"],
    "Bass 4 (E A D G)":            ["G", "D", "A", "E"],
}

# Technique symbols -> human readable (used for the legend / palette)
TECHNIQUES: dict[str, str] = {
    "h": "Hammer-on",
    "p": "Pull-off",
    "b": "Bend",
    "r": "Release",
    "/": "Slide up",
    "\\": "Slide down",
    "~": "Vibrato",
    "x": "Mute / dead note",
    "↑": "Volume Up",
    "↓": "Volumne Down"
}

VALID_CHARS = set("0123456789") | set(TECHNIQUES.keys()) | {EMPTY, "|", "(", ")", "*", "t"}


class TabModel:
    """A single song's tab: a grid of strings x columns plus a cursor."""

    def __init__(self, name: str = "Untitled",
                 tuning: str = "Standard (E A D G B e)",
                 length: int = 48):
        if tuning not in TUNINGS:
            tuning = "Standard (E A D G B e)"
        self.name = name
        self.tuning = tuning
        self.length = max(8, int(length))
        self.grid: list[list[str]] = [
            [EMPTY] * self.length for _ in TUNINGS[tuning]
        ]
        self.cur_string = 0     # 0 = top row (thinnest string)
        self.cur_col = 0
        # metadata
        self.artist = ""
        self.tempo = ""         # BPM (str or int)
        self.capo = 0           # capo fret (0 = none)
        # custom tuning + undo/redo
        self._custom_labels: list[str] | None = None
        self._undo: list[tuple] = []
        self._redo: list[tuple] = []

    # ---- convenience ----------------------------------------------------
    @property
    def labels(self) -> list[str]:
        if self.tuning == "Custom" and self._custom_labels:
            return self._custom_labels
        return TUNINGS.get(self.tuning, TUNINGS["Standard (E A D G B e)"])

    # ---- undo / redo ----------------------------------------------------
    def _snapshot(self) -> None:
        """Record current state so the next mutation can be undone."""
        self._undo.append((copy.deepcopy(self.grid), self.length,
                           self.cur_string, self.cur_col))
        if len(self._undo) > 300:
            self._undo.pop(0)
        self._redo.clear()

    def _restore(self, state) -> None:
        grid, length, cs, cc = state
        self.grid = grid
        self.length = length
        self.cur_string = cs
        self.cur_col = cc

    def undo(self) -> bool:
        if not self._undo:
            return False
        self._redo.append((copy.deepcopy(self.grid), self.length,
                           self.cur_string, self.cur_col))
        self._restore(self._undo.pop())
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append((copy.deepcopy(self.grid), self.length,
                           self.cur_string, self.cur_col))
        self._restore(self._redo.pop())
        return True

    @property
    def num_strings(self) -> int:
        return len(self.grid)

    def clamp_cursor(self) -> None:
        self.cur_string = max(0, min(self.cur_string, self.num_strings - 1))
        self.cur_col = max(0, min(self.cur_col, self.length - 1))

    # ---- editing --------------------------------------------------------
    def set_char(self, ch: str, _record: bool = True) -> bool:
        """Place a character at the cursor. Digits/techniques advance cursor."""
        if ch not in VALID_CHARS:
            return False
        if _record:
            self._snapshot()
        self.grid[self.cur_string][self.cur_col] = ch
        # auto-advance for note/technique entry so typing flows
        if ch != EMPTY and self.cur_col < self.length - 1:
            self.cur_col += 1
        return True

    def type_fret(self, number: str) -> bool:
        """Type a (possibly multi-digit) fret string like '12'."""
        digits = [d for d in str(number) if d.isdigit()]
        if not digits:
            return False
        self._snapshot()
        for d in digits:
            self.set_char(d, _record=False)
        return True

    def add_technique(self, sym: str, from_fret: str = "",
                      to_fret: str = "") -> bool:
        """Lay a combined phrase such as 7h9 / 7b9 / 12/14 at the cursor."""
        if sym not in TECHNIQUES:
            return False
        self._snapshot()
        for d in f"{from_fret}{sym}{to_fret}":
            if d in VALID_CHARS:
                self.set_char(d, _record=False)
        return True

    def backspace(self) -> None:
        self._snapshot()
        if self.cur_col > 0:
            self.cur_col -= 1
        self.grid[self.cur_string][self.cur_col] = EMPTY

    def clear_cell(self) -> None:
        self._snapshot()
        self.grid[self.cur_string][self.cur_col] = EMPTY

    def insert_column(self) -> None:
        self._snapshot()
        for row in self.grid:
            row.insert(self.cur_col, EMPTY)
        self.length += 1

    def delete_column(self) -> None:
        if self.length <= 1:
            return
        self._snapshot()
        for row in self.grid:
            del row[self.cur_col]
        self.length -= 1
        self.clamp_cursor()

    def insert_barline(self) -> None:
        self._snapshot()
        for r in range(self.num_strings):
            self.grid[r][self.cur_col] = "|"
        if self.cur_col < self.length - 1:
            self.cur_col += 1

    def extend(self, extra: int = 16) -> None:
        self._snapshot()
        for row in self.grid:
            row.extend([EMPTY] * extra)
        self.length += extra

    # ---- navigation -----------------------------------------------------
    def move(self, d_string: int, d_col: int) -> None:
        self.cur_string += d_string
        self.cur_col += d_col
        # auto-grow to the right when arrowing past the end
        if self.cur_col >= self.length:
            self.extend(8)
        self.clamp_cursor()

    def home(self) -> None:
        self.cur_col = 0

    def end(self) -> None:
        self.cur_col = self.length - 1

    # ---- tuning ---------------------------------------------------------
    def change_tuning(self, tuning: str) -> bool:
        """Change tuning; keeps existing note data, adjusts string count."""
        if tuning not in TUNINGS:
            return False
        new_labels = TUNINGS[tuning]
        new_n = len(new_labels)
        old_n = self.num_strings
        if new_n > old_n:
            for _ in range(new_n - old_n):
                self.grid.append([EMPTY] * self.length)
        elif new_n < old_n:
            self.grid = self.grid[:new_n]
        self.tuning = tuning
        self._custom_labels = None
        self.clamp_cursor()
        return True

    def set_custom_tuning(self, labels: list[str]) -> bool:
        """Define an arbitrary tuning (e.g. ['e','B','G','D','A','D#'])."""
        labels = [str(l).strip() for l in labels if str(l).strip()]
        if not labels:
            return False
        self._snapshot()
        new_n, old_n = len(labels), self.num_strings
        if new_n > old_n:
            for _ in range(new_n - old_n):
                self.grid.append([EMPTY] * self.length)
        elif new_n < old_n:
            self.grid = self.grid[:new_n]
        self.tuning = "Custom"
        self._custom_labels = labels
        self.clamp_cursor()
        return True

    # ---- rendering ------------------------------------------------------
    def render(self, wrap: int = 0, cursor: bool = False) -> str:
        """
        Render as ASCII text.
        wrap = 0 -> single long system; wrap > 0 -> break into systems.
        cursor -> insert a caret marker row (used only for on-screen preview).
        """
        labels = self.labels
        label_w = max(len(l) for l in labels)
        cols = self.length
        wrap = cols if wrap <= 0 else wrap

        systems = []
        start = 0
        while start < cols:
            end = min(start + wrap, cols)
            lines = []
            for r, lab in enumerate(labels):
                seg = "".join(self.grid[r][start:end])
                lines.append(f"{lab.rjust(label_w)}|{seg}|")
            systems.append("\n".join(lines))
            start = end
        return "\n\n".join(systems)

    def export_text(self, wrap: int = 48, header: bool = True) -> str:
        parts = []
        if header:
            parts.append(f"{self.name}")
            if self.artist:
                parts.append(f"Artist: {self.artist}")
            tuning_label = ("Custom (" + " ".join(self.labels) + ")"
                            if self.tuning == "Custom" else self.tuning)
            parts.append(f"Tuning: {tuning_label}")
            extra = []
            if self.tempo:
                extra.append(f"Tempo: {self.tempo} BPM")
            if self.capo:
                extra.append(f"Capo: fret {self.capo}")
            if extra:
                parts.append("   ".join(extra))
            parts.append("")
        parts.append(self.render(wrap=wrap))
        parts.append("")
        parts.append("Legend: h=hammer p=pull b=bend r=release "
                     "/=slide up \\=slide down ~=vibrato x=mute")
        return "\n".join(parts)

    # ---- serialisation --------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "tuning": self.tuning,
            "length": self.length,
            "grid": ["".join(row) for row in self.grid],
            "artist": self.artist,
            "tempo": self.tempo,
            "capo": self.capo,
            "custom_labels": self._custom_labels,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TabModel":
        m = cls(name=d.get("name", "Untitled"),
                tuning=d.get("tuning", "Standard (E A D G B e)"),
                length=d.get("length", 48))
        m.artist = d.get("artist", "")
        m.tempo = d.get("tempo", "")
        m.capo = d.get("capo", 0)
        m._custom_labels = d.get("custom_labels")
        grid = d.get("grid")
        if grid:
            m.grid = [list(row) for row in grid]
            m.length = max((len(r) for r in m.grid), default=m.length)
            # normalise all rows to equal length
            for row in m.grid:
                if len(row) < m.length:
                    row.extend([EMPTY] * (m.length - len(row)))
        m.clamp_cursor()
        return m


class Songbook:
    """A collection of songs, persisted as a single JSON file."""

    def __init__(self):
        self.songs: list[TabModel] = []
        self.current: int = -1

    def new_song(self, name: str = "Untitled",
                 tuning: str = "Standard (E A D G B e)") -> TabModel:
        song = TabModel(name=name, tuning=tuning)
        self.songs.append(song)
        self.current = len(self.songs) - 1
        return song

    def delete_song(self, index: int) -> None:
        if 0 <= index < len(self.songs):
            del self.songs[index]
            self.current = min(self.current, len(self.songs) - 1)

    def rename_song(self, index: int, name: str) -> None:
        if 0 <= index < len(self.songs):
            self.songs[index].name = name

    def get_current(self) -> TabModel | None:
        if 0 <= self.current < len(self.songs):
            return self.songs[self.current]
        return None

    def duplicate(self, index: int) -> None:
        if 0 <= index < len(self.songs):
            clone = copy.deepcopy(self.songs[index])
            clone.name += " (copy)"
            self.songs.insert(index + 1, clone)

    def move_song(self, src: int, dst: int) -> bool:
        """Reorder a song from position src to position dst."""
        n = len(self.songs)
        if not (0 <= src < n) or not (0 <= dst < n) or src == dst:
            return False
        song = self.songs.pop(src)
        self.songs.insert(dst, song)
        self.current = dst
        return True

    # ---- persistence ----------------------------------------------------
    def to_json(self) -> str:
        return json.dumps(
            {"version": 1, "songs": [s.to_dict() for s in self.songs],
             "current": self.current},
            indent=2,
        )

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.to_json())

    @classmethod
    def from_json(cls, text: str) -> "Songbook":
        book = cls()
        try:
            data = json.loads(text)
            songs = data.get("songs", []) if isinstance(data, dict) else []
            for s in songs:
                try:
                    book.songs.append(TabModel.from_dict(s))
                except Exception:
                    continue  # skip a single corrupt song, keep the rest
            book.current = data.get("current", 0) if isinstance(data, dict) else -1
        except Exception:
            # Completely unreadable file -> return an empty, usable songbook
            book.songs = []
            book.current = -1
        book.current = max(-1, min(book.current, len(book.songs) - 1))
        return book

    @classmethod
    def load(cls, path: str) -> "Songbook":
        with open(path, "r", encoding="utf-8") as f:
            return cls.from_json(f.read())
