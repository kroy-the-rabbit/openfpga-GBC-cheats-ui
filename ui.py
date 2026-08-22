"""Tk front end: pick a card, a system, a game, tick cheats, send to the Pocket.

Three panes, left to right: systems on the card, games in the selected system,
cheats for the selected game. The tick state of the cheat list is exactly what
will be written, and what is already on the card starts ticked.

Each cheat also shows how the core makes it take effect, because the two ways
do not behave the same. A GameShark code is written into RAM once a frame, so
the value is really there; a Game Genie code overrides the CPU's read, which is
what a ROM patch needs. See docs/CHEATS.md.
"""
from __future__ import annotations

import os
import tkinter as tk
from tkinter import messagebox, ttk

import card as card_mod
import library
import model

TICK, UNTICK = "☑", "☐"


class App(ttk.Frame):
    def __init__(self, master: tk.Tk) -> None:
        super().__init__(master, padding=8)
        self.grid(sticky="nsew")
        master.columnconfigure(0, weight=1)
        master.rowconfigure(0, weight=1)

        self.card: card_mod.Card | None = None
        self.platforms: list[card_mod.Platform] = []
        self.games: list[card_mod.Game] = []
        self.view: model.GameView | None = None

        self._build()
        self.rescan()

    # ---------------------------------------------------------------- layout --
    def _build(self) -> None:
        self.columnconfigure(0, weight=1, minsize=170)
        self.columnconfigure(1, weight=3, minsize=280)
        self.columnconfigure(2, weight=5, minsize=380)
        self.rowconfigure(1, weight=1)

        top = ttk.Frame(self)
        top.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 8))
        top.columnconfigure(1, weight=1)
        ttk.Label(top, text="Pocket SD card:").grid(row=0, column=0, padx=(0, 6))
        self.card_label = ttk.Label(top, text="scanning...", foreground="#666")
        self.card_label.grid(row=0, column=1, sticky="w")
        ttk.Button(top, text="Rescan", command=self.rescan).grid(row=0, column=2)

        self.systems = self._tree(1, 0, ("count",), {"#0": "System", "count": "ROMs"},
                                  {"#0": 130, "count": 50})
        self.systems.bind("<<TreeviewSelect>>", self.on_system)

        self.gamelist = self._tree(1, 1, ("cheats",), {"#0": "Game", "cheats": "On"},
                                   {"#0": 240, "cheats": 40})
        self.gamelist.bind("<<TreeviewSelect>>", self.on_game)

        right = ttk.Frame(self)
        right.grid(row=1, column=2, sticky="nsew", padx=(8, 0))
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        src = ttk.Frame(right)
        src.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        src.columnconfigure(0, weight=1)
        self.source_label = ttk.Label(src, text="", foreground="#666")
        self.source_label.grid(row=0, column=0, sticky="w")
        self.source_btn = ttk.Button(src, text="Change source...",
                                     command=self.change_source, state="disabled")
        self.source_btn.grid(row=0, column=1)

        cols = ("desc", "how", "codes")
        self.cheats = ttk.Treeview(right, columns=cols, show="tree headings",
                                   selectmode="none")
        self.cheats.heading("#0", text="")
        self.cheats.heading("desc", text="Cheat")
        self.cheats.heading("how", text="Applied")
        self.cheats.heading("codes", text="Addresses")
        self.cheats.column("#0", width=34, stretch=False, anchor="center")
        self.cheats.column("desc", width=230)
        self.cheats.column("how", width=64, stretch=False, anchor="center")
        self.cheats.column("codes", width=160)
        self.cheats.grid(row=1, column=0, sticky="nsew")
        sb = ttk.Scrollbar(right, orient="vertical", command=self.cheats.yview)
        sb.grid(row=1, column=1, sticky="ns")
        self.cheats.configure(yscrollcommand=sb.set)
        self.cheats.tag_configure("extra", foreground="#0a6")
        self.cheats.tag_configure("dead", foreground="#999")
        self.cheats.bind("<Button-1>", self.on_click)

        ttk.Label(right, foreground="#666", text=(
            "Applied: written = the value is put into RAM each frame, so the "
            "game can still clamp it.  patched = the CPU's read is overridden."
        ), wraplength=520).grid(row=2, column=0, columnspan=2, sticky="w",
                                pady=(4, 0))

        bottom = ttk.Frame(right)
        bottom.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        bottom.columnconfigure(0, weight=1)
        self.status = ttk.Label(bottom, text="")
        self.status.grid(row=0, column=0, sticky="w")
        ttk.Button(bottom, text="None", width=6,
                   command=lambda: self.set_all(False)).grid(row=0, column=1, padx=2)
        ttk.Button(bottom, text="All", width=5,
                   command=lambda: self.set_all(True)).grid(row=0, column=2, padx=2)
        self.save_btn = ttk.Button(bottom, text="Send to Pocket", command=self.save,
                                   state="disabled")
        self.save_btn.grid(row=0, column=3, padx=(8, 0))

    def _tree(self, row: int, col: int, cols, heads, widths) -> ttk.Treeview:
        frame = ttk.Frame(self)
        frame.grid(row=row, column=col, sticky="nsew", padx=(0, 4))
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        t = ttk.Treeview(frame, columns=cols, show="tree headings")
        for k, v in heads.items():
            t.heading(k, text=v)
        for k, v in widths.items():
            t.column(k, width=v, stretch=(k == "#0"))
        t.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(frame, orient="vertical", command=t.yview)
        sb.grid(row=0, column=1, sticky="ns")
        t.configure(yscrollcommand=sb.set)
        return t

    # ----------------------------------------------------------------- cards --
    def rescan(self) -> None:
        # Repaint before doing any of it. Scanning is normally instant, but if
        # it ever is not, a window frozen mid-click is indistinguishable from a
        # crash, and the user has no idea it is working.
        self.card_label.config(text="scanning...", foreground="#666")
        self.status.config(text="", foreground="#000")
        self.update_idletasks()

        self.systems.delete(*self.systems.get_children())
        self.gamelist.delete(*self.gamelist.get_children())
        self.cheats.delete(*self.cheats.get_children())
        self.view = None
        self.save_btn.state(["disabled"])
        self.source_btn.state(["disabled"])
        self.source_label.config(text="")

        if not library.available():
            self.card_label.config(text="cheat database missing", foreground="#a00")
            self.status.config(text="Run tools/cheats/init-db.sh to fetch it")
            return

        cards = card_mod.find_cards()
        if not cards:
            self.card = None
            self.card_label.config(
                text="no Pocket card found (needs Cores/ and Platforms/)",
                foreground="#a00")
            self.status.config(text="Insert the card and press Rescan")
            return

        self.card = cards[0]
        extra = f"  (+{len(cards) - 1} more)" if len(cards) > 1 else ""
        self.card_label.config(text=f"{self.card.root}  [{self.card.label}]{extra}",
                               foreground="#060")
        self.platforms = self.card.platforms()
        for i, p in enumerate(self.platforms):
            self.systems.insert("", "end", iid=str(i), text=p.name,
                                values=(len(p.games),))
        self.status.config(text=f"{sum(len(p.games) for p in self.platforms)} ROMs")
        if self.platforms:
            self.systems.selection_set("0")

    # ----------------------------------------------------------------- panes --
    def on_system(self, _evt=None) -> None:
        sel = self.systems.selection()
        if not sel:
            return
        plat = self.platforms[int(sel[0])]
        self.games = plat.games
        self.gamelist.delete(*self.gamelist.get_children())
        self.cheats.delete(*self.cheats.get_children())
        self.view = None
        self.save_btn.state(["disabled"])
        self.source_btn.state(["disabled"])
        self.source_label.config(text="")
        self.status.config(text=f"reading {len(self.games)} games...")
        self.update_idletasks()
        for i, g in enumerate(self.games):
            n = len(model.writer.load_installed(g.cht_path))
            self.gamelist.insert("", "end", iid=str(i), text=g.name,
                                 values=(n if n else "",))
        self.status.config(text=f"{len(self.games)} games")

    def on_game(self, _evt=None) -> None:
        sel = self.gamelist.selection()
        if not sel:
            return
        game = self.games[int(sel[0])]
        self.status.config(text="loading...")
        self.update_idletasks()
        try:
            self.view = model.load(game)
        except Exception as e:                                # noqa: BLE001
            messagebox.showerror("Cheats", f"Could not read cheats:\n{e}")
            self.status.config(text="")
            return
        self.refresh_cheats()
        self.source_btn.state(["!disabled"])
        self.save_btn.state(["!disabled"])

    def refresh_cheats(self) -> None:
        v = self.view
        self.cheats.delete(*self.cheats.get_children())
        if v is None:
            return
        self.source_label.config(
            text=("source: " + os.path.basename(v.source)) if v.source
            else "no matching cheat file found")
        for i, e in enumerate(v.entries):
            tags = []
            if not e.in_library:
                tags.append("extra")
            if e.placeholder:
                tags.append("dead")
            desc = e.desc + ("   (already installed)" if not e.in_library else "")
            self.cheats.insert("", "end", iid=str(i),
                               text=TICK if e.enabled else UNTICK,
                               values=(desc, e.applied,
                                       e.summary or "no usable code"),
                               tags=tuple(tags))
        self.update_status()

    def update_status(self) -> None:
        v = self.view
        if v is None:
            return
        codes = sum(len(e.group.codes) for e in v.enabled)
        written, patched = v.applied_counts
        msg = f"{len(v.enabled)} of {len(v.entries)} on, {codes} codes"
        if written or patched:
            msg += f" ({written} written, {patched} patched)"
        problems = v.problems
        if problems:
            msg += "   " + "; ".join(problems)
        self.status.config(text=msg, foreground="#a00" if problems else "#000")

    # --------------------------------------------------------------- editing --
    def on_click(self, event) -> None:
        if self.view is None:
            return
        row = self.cheats.identify_row(event.y)
        if not row:
            return
        entry = self.view.entries[int(row)]
        if entry.placeholder:
            self.status.config(
                text="that cheat has no usable code (a XX-style modifier)",
                foreground="#a00")
            return
        entry.enabled = not entry.enabled
        self.cheats.item(row, text=TICK if entry.enabled else UNTICK)
        self.update_status()

    def set_all(self, on: bool) -> None:
        if self.view is None:
            return
        for e in self.view.entries:
            if not e.placeholder:
                e.enabled = on
        self.refresh_cheats()

    def change_source(self) -> None:
        if self.view is None:
            return
        Chooser(self, self.view)

    def save(self) -> None:
        v = self.view
        if v is None:
            return
        problems = v.problems
        if problems and not messagebox.askyesno(
                "Cheats", "\n".join(problems) + "\n\nWrite anyway?"):
            return
        try:
            cheats, codes = v.save()
            if self.card:
                self.card.sync()
        except Exception as e:                                # noqa: BLE001
            messagebox.showerror("Cheats", f"Could not write:\n{e}")
            return
        sel = self.gamelist.selection()
        if sel:
            self.gamelist.item(sel[0], values=(cheats if cheats else "",))
        self.status.config(
            text=f"wrote {cheats} cheats / {codes} codes to the card",
            foreground="#060")


class Chooser(tk.Toplevel):
    """Pick which cheat file a game uses, and remember it."""

    def __init__(self, app: App, view: model.GameView) -> None:
        super().__init__(app)
        self.app, self.view = app, view
        self.title("Cheat source")
        self.transient(app)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        ttk.Label(self, text=view.game.name, padding=8).grid(row=0, column=0,
                                                             sticky="w")
        self.list = tk.Listbox(self, width=78, height=12)
        self.list.grid(row=1, column=0, sticky="nsew", padx=8)
        for c in view.alternates:
            self.list.insert("end", f"{c.score:.2f}  {os.path.basename(c.path)}")
        if view.alternates:
            self.list.selection_set(0)

        row = ttk.Frame(self, padding=8)
        row.grid(row=2, column=0, sticky="ew")
        ttk.Button(row, text="Use this", command=self.choose).pack(side="right")
        ttk.Button(row, text="Cancel", command=self.destroy).pack(side="right", padx=4)

    def choose(self) -> None:
        sel = self.list.curselection()
        if not sel:
            return
        path = self.view.alternates[sel[0]].path
        model.pin(self.view.game, path)
        self.app.view = model.load(self.view.game, source=path)
        self.app.refresh_cheats()
        self.destroy()


def main() -> int:
    root = tk.Tk()
    root.title("Pocket Cheats")
    root.geometry("1080x620")
    App(root)
    root.mainloop()
    return 0
