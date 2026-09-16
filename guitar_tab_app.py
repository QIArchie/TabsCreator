"""
guitar_tab_app.py  —  Tkinter desktop GUI for the Guitar Tab editor.

Run with:  python guitar_tab_app.py
(Tkinter ships with the standard python.org installer on Windows & macOS.)

All logic lives in tab_engine.py; this file only draws the UI and forwards
keystrokes / button clicks to the engine.
"""

import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

from tab_engine import TabModel, Songbook, TUNINGS, TECHNIQUES, EMPTY

CELL_W = 16          # pixel width of one character cell
CELL_H = 22          # pixel height of one string row
PAD_X = 60           # left space for string labels
PAD_Y = 20
FONT = ("Courier New", 14)
AUTOSAVE = os.path.join(os.path.expanduser("~"), ".guitar_tabs.json")


class TabApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ASCII Guitar Tab Editor")
        self.geometry("1000x640")
        self.minsize(760, 480)

        self.book = Songbook()
        self._load_autosave()
        if self.book.get_current() is None:
            self.book.new_song("My First Song")

        self._build_menu()
        self._build_toolbar()
        self._build_body()
        self._bind_keys()
        self.refresh_song_list()
        self.redraw()

    # ------------------------------------------------------------------ UI
    def _build_menu(self):
        m = tk.Menu(self)
        filem = tk.Menu(m, tearoff=0)
        filem.add_command(label="New song", command=self.new_song, accelerator="Ctrl+N")
        filem.add_command(label="Save songbook", command=self.save_book, accelerator="Ctrl+S")
        filem.add_command(label="Open songbook…", command=self.open_book, accelerator="Ctrl+O")
        filem.add_separator()
        filem.add_command(label="Export current tab…", command=self.export_tab)
        filem.add_command(label="Copy current tab", command=self.copy_tab, accelerator="Ctrl+C")
        filem.add_separator()
        filem.add_command(label="Quit", command=self.on_quit)
        m.add_cascade(label="File", menu=filem)

        editm = tk.Menu(m, tearoff=0)
        editm.add_command(label="Undo", command=self.undo, accelerator="Ctrl+Z")
        editm.add_command(label="Redo", command=self.redo, accelerator="Ctrl+Y")
        editm.add_separator()
        editm.add_command(label="Song details (artist/tempo/capo)…",
                          command=self.edit_metadata)
        m.add_cascade(label="Edit", menu=editm)

        helpm = tk.Menu(m, tearoff=0)
        helpm.add_command(label="Keyboard & techniques", command=self.show_help)
        m.add_cascade(label="Help", menu=helpm)
        self.config(menu=m)

    def _build_toolbar(self):
        bar = ttk.Frame(self, padding=(8, 6))
        bar.pack(side=tk.TOP, fill=tk.X)

        ttk.Label(bar, text="Tuning:").pack(side=tk.LEFT)
        self.tuning_var = tk.StringVar(value=self.book.get_current().tuning)
        self.tuning_dd = ttk.Combobox(bar, textvariable=self.tuning_var,
                                      values=list(TUNINGS.keys()) + ["Custom…"],
                                      state="readonly", width=32)
        self.tuning_dd.pack(side=tk.LEFT, padx=(4, 12))
        self.tuning_dd.bind("<<ComboboxSelected>>", self.on_tuning_change)

        ttk.Button(bar, text="＋ Bar |", command=self.add_bar).pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text="Insert col", command=self.insert_col).pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text="Delete col", command=self.delete_col).pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text="Extend →", command=self.extend).pack(side=tk.LEFT, padx=2)

        # Technique palette buttons
        pal = ttk.Frame(bar)
        pal.pack(side=tk.RIGHT)
        ttk.Label(pal, text="Techniques:").pack(side=tk.LEFT, padx=(0, 4))
        for sym, name in TECHNIQUES.items():
            b = ttk.Button(pal, text=f"{name} ({sym})", width=14,
                           command=lambda s=sym: self.place_char(s))
            b.pack(side=tk.LEFT, padx=1)

    def _build_body(self):
        body = ttk.Frame(self)
        body.pack(fill=tk.BOTH, expand=True)

        # left: song list
        left = ttk.Frame(body, padding=6)
        left.pack(side=tk.LEFT, fill=tk.Y)
        ttk.Label(left, text="Songs").pack(anchor="w")
        self.song_list = tk.Listbox(left, width=24, exportselection=False)
        self.song_list.pack(fill=tk.Y, expand=True)
        self.song_list.bind("<<ListboxSelect>>", self.on_song_select)
        btns = ttk.Frame(left)
        btns.pack(fill=tk.X, pady=4)
        ttk.Button(btns, text="New", width=6, command=self.new_song).pack(side=tk.LEFT)
        ttk.Button(btns, text="Rename", width=7, command=self.rename_song).pack(side=tk.LEFT)
        ttk.Button(btns, text="Del", width=5, command=self.delete_song).pack(side=tk.LEFT)
        btns2 = ttk.Frame(left)
        btns2.pack(fill=tk.X)
        ttk.Button(btns2, text="↑ Up", width=8,
                   command=lambda: self.reorder(-1)).pack(side=tk.LEFT)
        ttk.Button(btns2, text="↓ Down", width=8,
                   command=lambda: self.reorder(1)).pack(side=tk.LEFT)
        ttk.Button(btns2, text="Dup", width=6,
                   command=self.duplicate_song).pack(side=tk.LEFT)

        # right: canvas editor
        right = ttk.Frame(body)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(right, bg="#fbfbf7", highlightthickness=0)
        hbar = ttk.Scrollbar(right, orient=tk.HORIZONTAL, command=self.canvas.xview)
        self.canvas.configure(xscrollcommand=hbar.set)
        hbar.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<Button-1>", self.on_canvas_click)

        self.status = ttk.Label(self, anchor="w", padding=(8, 2),
                                relief=tk.SUNKEN)
        self.status.pack(side=tk.BOTTOM, fill=tk.X)

    def _bind_keys(self):
        self.bind("<Up>", lambda e: self.nav(-1, 0))
        self.bind("<Down>", lambda e: self.nav(1, 0))
        self.bind("<Left>", lambda e: self.nav(0, -1))
        self.bind("<Right>", lambda e: self.nav(0, 1))
        self.bind("<Tab>", lambda e: (self.nav(0, 1), "break")[1])
        self.bind("<Home>", lambda e: (self.song().home(), self.redraw()))
        self.bind("<End>", lambda e: (self.song().end(), self.redraw()))
        self.bind("<BackSpace>", lambda e: (self.song().backspace(), self.redraw()))
        self.bind("<Delete>", lambda e: (self.song().clear_cell(), self.redraw()))
        self.bind("<space>", lambda e: (self.song().clear_cell(), self.nav(0, 1)))
        self.bind("<Key>", self.on_key)
        self.bind("<Control-n>", lambda e: self.new_song())
        self.bind("<Control-s>", lambda e: self.save_book())
        self.bind("<Control-o>", lambda e: self.open_book())
        self.bind("<Control-c>", lambda e: self.copy_tab())
        self.bind("<Control-z>", lambda e: self.undo())
        self.bind("<Control-y>", lambda e: self.redo())
        self.bind("<Control-Z>", lambda e: self.redo())  # Ctrl+Shift+Z

    # -------------------------------------------------------------- helpers
    def song(self) -> TabModel:
        return self.book.get_current()

    def nav(self, ds, dc):
        self.song().move(ds, dc)
        self.redraw()

    def place_char(self, ch):
        self.song().set_char(ch)
        self.redraw()

    def on_key(self, event):
        ch = event.char
        if not ch:
            return
        if ch.isdigit():
            self.song().set_char(ch)
            self.redraw()
        elif ch in TECHNIQUES:
            self.song().set_char(ch)
            self.redraw()
        elif ch == "|":
            self.add_bar()

    # --------------------------------------------------------------- drawing
    def redraw(self):
        c = self.canvas
        c.delete("all")
        song = self.song()
        labels = song.labels
        n = song.num_strings
        cols = song.length

        # string label + horizontal lines + characters
        for r, lab in enumerate(labels):
            y = PAD_Y + r * CELL_H
            c.create_text(PAD_X - 10, y, text=lab, font=FONT, anchor="e")
            for col in range(cols):
                x = PAD_X + col * CELL_W
                ch = song.grid[r][col]
                c.create_text(x, y, text=(ch if ch != EMPTY else "-"),
                              font=FONT, anchor="w",
                              fill="#111" if ch != EMPTY else "#c8c8c8")

        # cursor highlight
        cx = PAD_X + song.cur_col * CELL_W
        cy = PAD_Y + song.cur_string * CELL_H
        c.create_rectangle(cx - 2, cy - CELL_H // 2, cx + CELL_W - 2,
                           cy + CELL_H // 2, outline="#0a7", width=2)

        c.configure(scrollregion=(0, 0, PAD_X + cols * CELL_W + 40,
                                  PAD_Y + n * CELL_H + 20))
        self.status.config(
            text=f"  {song.name}   |   {song.tuning}   |   "
                 f"string {labels[song.cur_string]}  col {song.cur_col + 1}/{cols}"
                 f"   |   type digits for frets, h/p/b/r/~ // \\\\ for techniques")

    def on_canvas_click(self, event):
        song = self.song()
        col = round((self.canvas.canvasx(event.x) - PAD_X) / CELL_W)
        row = round((event.y - PAD_Y) / CELL_H)
        song.cur_col = max(0, min(col, song.length - 1))
        song.cur_string = max(0, min(row, song.num_strings - 1))
        self.canvas.focus_set()
        self.redraw()

    # --------------------------------------------------------------- actions
    def add_bar(self):
        self.song().insert_barline(); self.redraw()

    def insert_col(self):
        self.song().insert_column(); self.redraw()

    def delete_col(self):
        self.song().delete_column(); self.redraw()

    def extend(self):
        self.song().extend(16); self.redraw()

    def undo(self):
        self.song().undo(); self.redraw()

    def redo(self):
        self.song().redo(); self.redraw()

    def on_tuning_change(self, _evt=None):
        choice = self.tuning_var.get()
        if choice == "Custom…":
            spec = simpledialog.askstring(
                "Custom tuning",
                "Enter strings high→low, space separated (e.g. e B G D A D#):",
                parent=self)
            if spec:
                self.song().set_custom_tuning(spec.split())
            self.tuning_var.set(self.song().tuning if self.song().tuning != "Custom"
                                else "Custom…")
        else:
            self.song().change_tuning(choice)
        self.redraw()

    def edit_metadata(self):
        s = self.song()
        artist = simpledialog.askstring("Artist", "Artist:",
                                        initialvalue=s.artist, parent=self)
        if artist is not None:
            s.artist = artist
        tempo = simpledialog.askstring("Tempo", "Tempo (BPM):",
                                       initialvalue=str(s.tempo), parent=self)
        if tempo is not None:
            s.tempo = tempo
        capo = simpledialog.askinteger("Capo", "Capo fret (0 = none):",
                                       initialvalue=int(s.capo or 0), parent=self)
        if capo is not None:
            s.capo = capo
        self.redraw()

    def reorder(self, direction):
        cur = self.book.current
        if cur < 0:
            return
        if self.book.move_song(cur, cur + direction):
            self.refresh_song_list(); self.redraw()

    def duplicate_song(self):
        if self.book.current >= 0:
            self.book.duplicate(self.book.current)
            self.refresh_song_list()

    # ---- songs
    def refresh_song_list(self):
        self.song_list.delete(0, tk.END)
        for s in self.book.songs:
            self.song_list.insert(tk.END, s.name)
        if self.book.current >= 0:
            self.song_list.selection_clear(0, tk.END)
            self.song_list.selection_set(self.book.current)

    def on_song_select(self, _evt=None):
        sel = self.song_list.curselection()
        if sel:
            self.book.current = sel[0]
            self.tuning_var.set(self.song().tuning)
            self.redraw()

    def new_song(self):
        name = simpledialog.askstring("New song", "Song name:", parent=self)
        if name:
            self.book.new_song(name, self.tuning_var.get())
            self.refresh_song_list(); self.redraw()

    def rename_song(self):
        if self.book.current < 0:
            return
        name = simpledialog.askstring("Rename", "New name:",
                                      initialvalue=self.song().name, parent=self)
        if name:
            self.book.rename_song(self.book.current, name)
            self.refresh_song_list()

    def delete_song(self):
        if self.book.current < 0:
            return
        if messagebox.askyesno("Delete", f"Delete '{self.song().name}'?"):
            self.book.delete_song(self.book.current)
            if not self.book.songs:
                self.book.new_song("Untitled")
            self.refresh_song_list(); self.redraw()

    # ---- persistence / export
    def save_book(self):
        path = filedialog.asksaveasfilename(defaultextension=".json",
                                            filetypes=[("Tab songbook", "*.json")])
        if path:
            self.book.save(path)
            messagebox.showinfo("Saved", f"Saved {len(self.book.songs)} song(s).")

    def open_book(self):
        path = filedialog.askopenfilename(filetypes=[("Tab songbook", "*.json")])
        if path:
            self.book = Songbook.load(path)
            if not self.book.songs:
                self.book.new_song("Untitled")
            self.tuning_var.set(self.song().tuning)
            self.refresh_song_list(); self.redraw()

    def export_tab(self):
        path = filedialog.asksaveasfilename(defaultextension=".txt",
                                            filetypes=[("Text", "*.txt")])
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.song().export_text())
            messagebox.showinfo("Exported", "Tab exported as text.")

    def copy_tab(self):
        self.clipboard_clear()
        self.clipboard_append(self.song().export_text())
        self.status.config(text="  Copied tab to clipboard!")

    def show_help(self):
        msg = ("Navigation:  arrow keys / Tab / mouse click\n"
               "Frets:       type digits (0-24). Multi-digit auto-advances.\n"
               "Bar line:    | button or type '|'\n"
               "Backspace:   delete previous, Delete: clear cell\n\n"
               "Techniques (type the key or use palette):\n"
               + "\n".join(f"  {k}  {v}" for k, v in TECHNIQUES.items()))
        messagebox.showinfo("Help", msg)

    # ---- lifecycle
    def _load_autosave(self):
        if os.path.exists(AUTOSAVE):
            try:
                self.book = Songbook.load(AUTOSAVE)
            except Exception:
                pass

    def on_quit(self):
        try:
            self.book.save(AUTOSAVE)
        except Exception:
            pass
        self.destroy()


if __name__ == "__main__":
    app = TabApp()
    app.protocol("WM_DELETE_WINDOW", app.on_quit)
    app.mainloop()
