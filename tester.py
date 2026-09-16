"""
tester.py  —  INDEPENDENT, STRICT software tester for the Guitar Tab editor.

Philosophy: behave like a demanding QA engineer, not a rubber stamp. It tests
not only the stated requirements but the real-world quality bar a musician
expects from a usable tab editor. Uses getattr/hasattr so it degrades
gracefully (missing features simply FAIL rather than crash).

Prints a weighted score out of 10 and a machine-readable __SCORE__ line.
"""

import os
import json
import tempfile
import traceback

import tab_engine as E
from tab_engine import TabModel, Songbook

GUI_SRC = ""
if os.path.exists("guitar_tab_app.py"):
    with open("guitar_tab_app.py", encoding="utf-8") as f:
        GUI_SRC = f.read()

results = []


def check(cid, desc, weight, cond, note=""):
    try:
        ok = bool(cond)
    except Exception as ex:  # a check that raises == fail
        ok, note = False, f"exception: {ex}"
    results.append((cid, desc, weight, ok, note))


def safe(fn, default=False):
    try:
        return fn()
    except Exception:
        return default


def run():
    # ============================================================ REQUIRED
    # ---- R1 blank ASCII default
    m = TabModel()
    r = m.render()
    check("R1", "Blank ASCII tab by default", 1.0,
          ("-" in r) and all(len(set(len(l) for l in blk.splitlines())) == 1
                             for blk in r.split("\n\n")),
          "all rows equal width")
    check("R1b", "6 strings, labels e B G D A E", 0.5,
          m.num_strings == 6 and m.labels == ["e", "B", "G", "D", "A", "E"])

    # ---- R2 navigation (arrows + tab + mouse)
    m = TabModel()
    m.move(1, 0); m.move(0, 3); m.move(-1, -1)
    check("R2", "Arrow nav + bounds + auto-grow", 1.0,
          m.cur_string == 0 and m.cur_col == 2)
    check("R2-mouse", "Mouse click selection in GUI", 0.5,
          "on_canvas_click" in GUI_SRC and "<Button-1>" in GUI_SRC)
    check("R2-tab", "Tab key navigation bound", 0.5, "<Tab>" in GUI_SRC)

    # ---- R3 fret input, incl open string 0, high fret, and CHORD stacking
    m = TabModel()
    m.cur_string, m.cur_col = 5, 0; m.type_fret("12")
    m.cur_string, m.cur_col = 0, 0; m.type_fret("0")
    chord_ok = m.grid[5][0] == "1" and m.grid[5][1] == "2" and m.grid[0][0] == "0"
    check("R3", "Fret input incl open '0' and multi-digit '12'", 1.0, chord_ok)
    # chord = several strings share the SAME column and still align on export
    m = TabModel()
    for s in range(6):
        m.cur_string, m.cur_col = s, 4
        m.set_char("2" if s % 2 else "0")
    lines = m.render().splitlines()
    aligned = len(set(len(l) for l in lines)) == 1
    check("R3-chord", "Chord (stacked notes) stays column-aligned", 1.0, aligned)

    # ---- R4 tuning dropdown + CUSTOM tuning support
    m = TabModel()
    check("R4", "Change to Drop D via engine", 1.0,
          m.change_tuning("Drop D (D A D G B e)") and m.labels[-1] == "D")
    check("R4-dd", "Tuning dropdown in GUI", 0.5, "Combobox" in GUI_SRC)
    has_custom = hasattr(m, "set_custom_tuning")
    check("R4-custom", "Custom/user-defined tuning supported", 1.0,
          has_custom and safe(lambda: m.set_custom_tuning(["e","B","G","D","A","D#"]) and m.labels[-1] == "D#"))

    # ---- R5 multiple songs + REORDER
    book = Songbook()
    book.new_song("A"); book.new_song("B"); book.new_song("C")
    multi = len(book.songs) == 3
    can_reorder = hasattr(book, "move_song")
    reordered = safe(lambda: (book.move_song(2, 0), book.songs[0].name == "C")[1])
    check("R5", "Multiple songs stored", 1.0, multi)
    check("R5-reorder", "Reorder songs in the songbook", 1.0,
          can_reorder and reordered)
    book.duplicate(0); book.delete_song(0)
    check("R5-dupdel", "Duplicate & delete songs", 0.5, len(book.songs) == 3)

    # ---- R6 export: faithful, equal-width, copyable + wrapping
    m = TabModel(name="Riff"); m.cur_string = 5; m.type_fret("3")
    txt = m.export_text()
    exp_lines = [l for l in m.render(wrap=48).splitlines() if l]
    equal_w = len(set(len(l) for l in exp_lines)) == 1
    check("R6", "Export readable + equal-width rows", 1.0,
          "Riff" in txt and "|" in txt and equal_w)
    check("R6-copy", "Copy to clipboard in GUI", 0.5, "clipboard_append" in GUI_SRC)
    m2 = TabModel(length=120)
    check("R6-wrap", "Long tabs wrap into systems", 0.5,
          m2.render(wrap=48).count("\n\n") >= 1)

    # ---- R7 techniques: enter each, plus COMBINED forms 7h9 and 7b9
    techs = ["b", "r", "/", "\\", "~", "h", "p"]
    m = TabModel(); all_place = True
    for i, s in enumerate(techs):
        m.cur_string, m.cur_col = 0, i
        all_place = all_place and m.set_char(s) and m.grid[0][i] == s
    check("R7", "All required techniques enter-able", 1.5, all_place)
    # helper to lay a technique BETWEEN two frets (e.g. 7h9) is what players want
    has_helper = hasattr(m, "add_technique")
    combo = safe(lambda: _combo_ok(TabModel))
    check("R7-combo", "Helper lays combined notation like 7h9 / 7b9", 1.0,
          has_helper and combo)
    check("R7-palette", "Technique palette buttons in GUI", 0.5,
          "place_char" in GUI_SRC)

    # ========================================================= QUALITY BAR
    # ---- Undo / Redo  (essential for any editor)
    m = TabModel()
    has_undo = hasattr(m, "undo") and hasattr(m, "redo")
    undo_ok = safe(lambda: _undo_ok(TabModel))
    check("Q-undo", "Undo & redo edits", 2.0, has_undo and undo_ok)

    # ---- Song metadata (artist / tempo / capo) commonly expected
    m = TabModel()
    meta_ok = all(hasattr(m, a) for a in ("artist", "tempo", "capo"))
    meta_export = meta_ok and safe(lambda: _meta_export_ok(TabModel))
    check("Q-meta", "Song metadata (artist/tempo/capo) + in export", 1.0,
          meta_ok and meta_export)

    # ---- Robustness: corrupt / partial file must not crash the app
    graceful = safe(lambda: _load_corrupt_ok())
    check("Q-corrupt", "Loads corrupt songbook gracefully", 1.0, graceful)

    # ---- Persistence round-trip lossless
    book = Songbook(); book.new_song("X"); book.get_current().type_fret("7")
    tmp = tempfile.mktemp(suffix=".json"); book.save(tmp)
    rt = safe(lambda: Songbook.load(tmp).songs[0].to_dict() == book.songs[0].to_dict())
    os.path.exists(tmp) and os.remove(tmp)
    check("Q-roundtrip", "Save/load round-trip lossless", 1.0, rt)

    # ---- Editor niceties
    m = TabModel(); m.cur_col = 4; m.insert_barline()
    check("Q-bar", "Bar line across strings", 0.5,
          all(m.grid[r][4] == "|" for r in range(m.num_strings)))
    m = TabModel(); m.type_fret("9"); m.backspace()
    check("Q-bksp", "Backspace clears note", 0.5, m.grid[0][0] == "-")
    check("Q-badchar", "Rejects invalid characters", 0.5, m.set_char("Z") is False)
    check("Q-autosave", "Autosave on quit", 0.5, "AUTOSAVE" in GUI_SRC)
    check("Q-help", "In-app keyboard/technique help", 0.5, "show_help" in GUI_SRC)


# ---- helper scenarios -----------------------------------------------------
def _combo_ok(TabModel):
    m = TabModel(); m.cur_string, m.cur_col = 0, 0
    m.add_technique("h", "7", "9")           # expect 7 h 9 laid down in a row
    seg = "".join(m.grid[0][0:3])
    return seg == "7h9"


def _undo_ok(TabModel):
    m = TabModel(); m.cur_string, m.cur_col = 0, 0
    m.type_fret("5"); before = "".join(m.grid[0])
    m.undo(); after = "".join(m.grid[0])
    m.redo(); redone = "".join(m.grid[0])
    return before != after and redone == before


def _meta_export_ok(TabModel):
    m = TabModel(name="Song"); m.artist = "Hendrix"; m.tempo = 120; m.capo = 2
    t = m.export_text()
    return "Hendrix" in t and "120" in t and "2" in str(t)


def _load_corrupt_ok():
    tmp = tempfile.mktemp(suffix=".json")
    with open(tmp, "w") as f:
        f.write("{ this is : not valid json ][")
    try:
        Songbook.load(tmp)          # ideal: returns empty book, no raise
        ok = True
    except Exception:
        ok = False
    finally:
        os.path.exists(tmp) and os.remove(tmp)
    return ok


def main():
    try:
        run()
    except Exception:
        traceback.print_exc()

    total_w = sum(w for _, _, w, _, _ in results)
    got_w = sum(w for _, _, w, p, _ in results if p)
    score10 = round(got_w / total_w * 10, 2)

    print("=" * 72)
    print("GUITAR TAB EDITOR — INDEPENDENT SOFTWARE TESTER (STRICT)")
    print("=" * 72)
    for cid, desc, w, p, note in results:
        mark = "PASS" if p else "FAIL"
        extra = f"   -> {note}" if note else ""
        print(f"[{mark}] {cid:14} w={w:<4} {desc}{extra}")
    print("-" * 72)
    n_pass = sum(1 for *_x, p, _ in results if p)
    print(f"Checks passed: {n_pass}/{len(results)}   "
          f"Weighted {got_w:.2f}/{total_w:.2f}")
    print(f"SCORE: {score10} / 10")
    print("=" * 72)
    print(f"__SCORE__={score10}")
    return score10


if __name__ == "__main__":
    main()
