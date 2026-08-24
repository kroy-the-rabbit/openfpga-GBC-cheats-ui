# SPDX-License-Identifier: GPL-3.0-or-later
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
import carts
import cheatfile
import db
import library
import meter
import model
import version
import work
import writer

TICK, UNTICK = "☑", "☐"
CARTS = "carts"        # iid of the Cartridges row in the systems pane
GROUP = "sys:"         # iid prefix of a system heading in the cartridge pane


class App(ttk.Frame):
    def __init__(self, master: tk.Tk) -> None:
        super().__init__(master, padding=8)
        self.grid(sticky="nsew")
        master.columnconfigure(0, weight=1)
        master.rowconfigure(0, weight=1)

        self.card: card_mod.Card | None = None
        self.platforms: list[card_mod.Platform] = []
        self.platform: card_mod.Platform | None = None
        self.worker = work.Worker(master)
        # The database fetch gets its own runner: it takes about a minute, and
        # card reads must not queue behind it.
        self.dbjob = work.Job(master)
        self.remote: dict | None = None       # upstream's version, once known
        self.dbjob_kind = ""                  # "check" or "update", for Stop
        self.games: list[card_mod.Game] = []
        self.view: model.GameView | None = None

        self._build()
        self.rescan()
        self.check_db()

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
        self.rescan_btn = ttk.Button(top, text="Rescan", command=self.rescan)
        self.rescan_btn.grid(row=0, column=2)
        self.eject_btn = ttk.Button(top, text="Eject", width=7,
                                    command=self.eject, state="disabled")
        self.eject_btn.grid(row=0, column=3, padx=(4, 0))

        self.systems = self._tree(1, 0, ("count",), {"#0": "System", "count": "ROMs"},
                                  {"#0": 130, "count": 50})
        self.systems.bind("<<TreeviewSelect>>", self.on_system)

        mid = ttk.Frame(self)
        mid.grid(row=1, column=1, sticky="nsew", padx=(0, 4))
        mid.columnconfigure(0, weight=1)
        mid.rowconfigure(0, weight=1)
        self.gamelist = self._tree_in(mid, ("cheats",),
                                      {"#0": "Game", "cheats": "On"},
                                      {"#0": 240, "cheats": 40})
        self.gamelist.bind("<<TreeviewSelect>>", self.on_game)

        cartbar = ttk.Frame(mid)
        cartbar.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        self.add_btn = ttk.Button(cartbar, text="Add cartridge...", width=16,
                                  command=self.add_cart, state="disabled")
        self.add_btn.pack(side="left")
        self.del_btn = ttk.Button(cartbar, text="Remove", width=9,
                                  command=self.remove_cart, state="disabled")
        self.del_btn.pack(side="left", padx=4)
        self.move_btn = ttk.Button(cartbar, text="Move", width=13,
                                   command=self.move_cart, state="disabled")
        self.move_btn.pack(side="left")

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
        self.meter = meter.Meter(bottom, writer.MAX_CODES)
        self.meter_platform = ""
        self.meter.grid(row=0, column=0, sticky="w")
        self.status = ttk.Label(bottom, text="")
        self.status.grid(row=1, column=0, columnspan=4, sticky="w", pady=(4, 0))
        ttk.Button(bottom, text="None", width=6,
                   command=lambda: self.set_all(False)).grid(row=0, column=1, padx=2)
        ttk.Button(bottom, text="All", width=5,
                   command=lambda: self.set_all(True)).grid(row=0, column=2, padx=2)
        self.save_btn = ttk.Button(bottom, text="Send to Pocket", command=self.save,
                                   state="disabled")
        self.save_btn.grid(row=0, column=3, padx=(8, 0))

        self._build_dbbar()

    def _build_dbbar(self) -> None:
        """Which cheat database is in use, how old it is, and updating it."""
        bar = ttk.Frame(self)
        bar.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        bar.columnconfigure(0, weight=1)
        self.db_label = ttk.Label(bar, text="cheat database: checking...",
                                  foreground="#666")
        self.db_label.grid(row=0, column=0, sticky="w")
        self.db_bar = ttk.Progressbar(bar, length=180, mode="determinate")
        self.db_btn = ttk.Button(bar, text="Update", width=8,
                                 command=self.update_db)
        self.db_btn.grid(row=0, column=2, padx=(6, 0))

    def _tree(self, row: int, col: int, cols, heads, widths) -> ttk.Treeview:
        frame = ttk.Frame(self)
        frame.grid(row=row, column=col, sticky="nsew", padx=(0, 4))
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        return self._tree_in(frame, cols, heads, widths)

    def _tree_in(self, frame, cols, heads, widths) -> ttk.Treeview:
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
        """Find the card and read its games. The reading happens off-thread."""
        self.systems.delete(*self.systems.get_children())
        self.gamelist.delete(*self.gamelist.get_children())
        self.cheats.delete(*self.cheats.get_children())
        self.view = None
        self.platforms = []
        self.save_btn.state(["disabled"])
        self.source_btn.state(["disabled"])
        self.source_label.config(text="")

        self.eject_btn.state(["disabled"])
        self.card_label.config(text="scanning...", foreground="#666")
        self.status.config(text="reading the card", foreground="#000")
        self.rescan_btn.state(["disabled"])
        self.worker.submit(self._scan, self._scanned, "scan")

    @staticmethod
    def _scan():
        """Worker thread: no widgets touched here."""
        cards = card_mod.find_cards()
        if not cards:
            return None
        return cards, cards[0].platforms()

    def _scanned(self, result, err) -> None:
        self.rescan_btn.state(["!disabled"])
        if err is not None:
            self.card_label.config(text="could not read the card", foreground="#a00")
            self.status.config(text=str(err), foreground="#a00")
            return
        if result is None:
            self.card = None
            self.card_label.config(
                text="no Pocket card found (needs Cores/ and Platforms/)",
                foreground="#a00")
            self.status.config(text="Insert the card and press Rescan")
            return

        cards, platforms = result
        self.card = cards[0]
        self.eject_btn.state(["!disabled"])
        self.platforms = platforms
        extra = f"  (+{len(cards) - 1} more)" if len(cards) > 1 else ""
        self.card_label.config(text=f"{self.card.root}  [{self.card.label}]{extra}",
                               foreground="#060")
        for i, p in enumerate(self.platforms):
            self.systems.insert("", "end", iid=str(i), text=p.name,
                                values=(len(p.games),))
        # Cartridges are not files on the card, so they are listed separately.
        self.systems.insert("", "end", iid=CARTS, text="Cartridges",
                            values=(len(carts.all()),))
        self.status.config(text=f"{sum(len(p.games) for p in self.platforms)} ROMs")
        if self.platforms:
            self.systems.selection_set("0")

    def eject(self) -> None:
        """Flush and unmount, so the card can be pulled without losing a write.

        Writing to the card already syncs, but a sync is not an unmount: the
        filesystem is still mounted and the kernel may still have metadata to
        write back. This is the same eject the desktop does.
        """
        if self.card is None:
            return
        card = self.card
        self.eject_btn.state(["disabled"])
        self.rescan_btn.state(["disabled"])
        self.status.config(text="unmounting...", foreground="#000")
        self.worker.submit(card.unmount, self._ejected, "eject")

    def _ejected(self, message, err) -> None:
        self.rescan_btn.state(["!disabled"])
        if err is not None:
            # Almost always a file still open on the card, and the tool's own
            # message names what. Nothing is forced: that is the failure this
            # whole app exists to avoid.
            self.eject_btn.state(["!disabled"])
            self.status.config(text=f"could not eject: {err}", foreground="#a00")
            messagebox.showwarning("Eject", f"The card was not unmounted.\n\n{err}")
            return
        self.card = None
        self.platforms = []
        self.platform = None
        self.games = []
        self.view = None
        self.systems.delete(*self.systems.get_children())
        self.gamelist.delete(*self.gamelist.get_children())
        self.cheats.delete(*self.cheats.get_children())
        for b in (self.save_btn, self.source_btn, self.del_btn, self.add_btn,
                  self.move_btn):
            b.state(["disabled"])
        self.source_label.config(text="")
        self.meter.set(0)
        self.card_label.config(text="card unmounted, safe to remove",
                               foreground="#060")
        self.status.config(text=str(message), foreground="#060")

    # -------------------------------------------------------------- database --
    def check_db(self) -> None:
        """Ask upstream what is current, without downloading anything.

        Two API calls. It runs at startup and again after an update, and a
        failure is not worth a dialog: being offline is not an error, it just
        means the comparison cannot be made.
        """
        self.refresh_db_label()
        if self.dbjob.busy():
            return
        self.dbjob_kind = "check"
        self.dbjob.start(lambda report, cancelled: db.remote_state(timeout=10),
                         None, self._db_checked)

    def _db_checked(self, remote, err) -> None:
        self.dbjob_kind = ""
        if err is None:
            self.remote = remote
        self.refresh_db_label(
            note="" if err is None else "  (could not reach upstream)")

    def refresh_db_label(self, note: str = "") -> None:
        local = db.local_state()
        text = db.describe(local, self.remote) + note
        stale = self.remote is not None and not db.up_to_date(local, self.remote)
        self.db_label.config(
            text=text, foreground="#a00" if local is None else
            ("#960" if stale else "#666"))

    def update_db(self) -> None:
        """Check first, then fetch only if there is something to fetch.

        The check doubles as the retry for a failed startup check, which is why
        there is no separate button for it.
        """
        if self.dbjob_kind == "update":
            self.dbjob.cancel()
            self.status.config(text="stopping the update...", foreground="#000")
            return
        if self.dbjob.busy():
            # The startup check is two API calls and nearly done; nothing is
            # gained by cancelling it and it is not what Stop means.
            self.status.config(text="still checking, try again in a moment",
                               foreground="#000")
            return

        def body(report, cancelled):
            report(0, 0, "asking upstream what is current")
            remote = db.remote_state()
            if db.up_to_date(db.local_state(), remote):
                return ("current", remote)
            return ("fetched", db.fetch(progress=report, cancelled=cancelled),
                    remote)

        if not self.dbjob.start(body, self._db_progress, self._db_done):
            return
        self.dbjob_kind = "update"
        self.db_btn.config(text="Stop")
        self.db_bar.grid(row=0, column=1, padx=(8, 0))
        self.db_bar.config(value=0, maximum=100)

    def _db_progress(self, done: int, total: int, message: str) -> None:
        if total:
            self.db_bar.config(mode="determinate", maximum=total, value=done)
            self.db_label.config(text=f"{message}  {done}/{total}",
                                 foreground="#666")
        else:
            self.db_bar.config(mode="indeterminate", value=0)
            self.db_label.config(text=message, foreground="#666")

    def _db_done(self, result, err) -> None:
        self.dbjob_kind = ""
        self.db_btn.config(text="Update")
        self.db_bar.grid_remove()
        if isinstance(err, db.Cancelled):
            self.status.config(text="update stopped, the database is unchanged",
                               foreground="#000")
            self.refresh_db_label()
            return
        if err is not None:
            self.refresh_db_label(note="  (update failed)")
            self.status.config(text=f"could not update: {err}", foreground="#a00")
            messagebox.showerror("Cheat database",
                                 f"The database was not updated.\n\n{err}\n\n"
                                 "Whatever was there before is untouched.")
            return

        if result[0] == "current":
            self.remote = result[1]
            self.refresh_db_label()
            self.status.config(text="cheat database is already up to date",
                               foreground="#060")
            return

        _, state, remote = result
        self.remote = remote
        # The index is built from the files that were just replaced.
        library.refresh()
        self.refresh_db_label()
        self.status.config(
            text=f"cheat database updated: {state['files']} files, "
                 f"{db.day(state['date'])}", foreground="#060")
        if self.view is not None:
            self.on_game()

    # ----------------------------------------------------------------- panes --
    def on_system(self, _evt=None) -> None:
        sel = self.systems.selection()
        if not sel:
            return
        self.add_btn.state(["!disabled"] if sel[0] == CARTS else ["disabled"])
        self.del_btn.state(["disabled"])
        self.move_btn.state(["disabled"])
        if sel[0] == CARTS:
            # Retire any platform read still in flight. show_carts() fills the
            # game pane synchronously, so a result arriving after it would
            # otherwise repaint the pane with that platform's ROMs while
            # self.games still held the cartridges: every row then indexed the
            # wrong object, and Remove silently did nothing.
            self.platform = None
            self.show_carts()
            return
        plat = self.platforms[int(sel[0])]
        self.games = plat.games
        self.platform = plat
        self.gamelist.delete(*self.gamelist.get_children())
        self.cheats.delete(*self.cheats.get_children())
        self.view = None
        self.save_btn.state(["disabled"])
        self.source_btn.state(["disabled"])
        self.source_label.config(text="")
        self.status.config(text=f"reading {len(self.games)} games...")
        self.worker.submit(lambda: self._counts(plat), self._listed, "list")

    @staticmethod
    def _counts(plat):
        """Worker thread: how many cheats each game has installed.

        Only the games that really have a file are opened. The rest are known
        to have none from the directory listing alone, so they cost nothing.
        """
        return plat, [len(model.writer.load_installed(g.cht_path, plat.id))
                      if plat.has_cheats(g) else 0 for g in plat.games]

    def _listed(self, result, err) -> None:
        if err is not None:
            self.status.config(text=f"could not read the card: {err}",
                               foreground="#a00")
            return
        plat, counts = result
        if plat is not self.platform:        # the user moved on while we read
            return
        self.gamelist.delete(*self.gamelist.get_children())
        self.move_btn.state(["disabled"])
        for i, (g, n) in enumerate(zip(plat.games, counts)):
            self.gamelist.insert("", "end", iid=str(i), text=g.name,
                                 values=(n if n else "",))
        self.status.config(text=f"{len(plat.games)} games, "
                                f"{len(plat.cheat_files)} with cheats",
                           foreground="#000")

    def platform_name(self, pid: str) -> str:
        """What the card calls a system, falling back to the bare id.

        The systems pane already shows these names, and a cartridge filed
        under one should say the same thing rather than a second name for it.
        """
        for p in self.platforms:
            if p.id == pid:
                return p.name
        return pid.upper()

    def show_carts(self) -> None:
        """The cartridges you have listed, filed under the system each is for.

        Rows keep indexing self.games, so the group rows get an iid that is
        not a number and selected_game() rejects them for free.
        """
        root = self.card.root if self.card else ""
        self.games = carts.all(root)
        self.gamelist.delete(*self.gamelist.get_children())
        self.cheats.delete(*self.cheats.get_children())
        self.view = None
        self.save_btn.state(["disabled"])
        self.source_btn.state(["disabled"])
        self.del_btn.state(["disabled"])
        self.move_btn.state(["disabled"])
        self.source_label.config(text="")

        for pid, positions in carts.grouped(self.games):
            gid = GROUP + pid
            self.gamelist.insert(
                "", "end", iid=gid, open=True,
                text=f"{self.platform_name(pid)}  ({len(positions)})",
                tags=("group",))
            for i in positions:
                c = self.games[i]
                n = len(model.writer.load_installed(c.cht_path, c.platform))
                self.gamelist.insert(gid, "end", iid=str(i), text=c.name,
                                     values=(n if n else "",))
        self.status.config(
            text=f"{len(self.games)} cartridges" if self.games else
                 "no cartridges listed yet, press Add", foreground="#000")

    def add_cart(self) -> None:
        """Name it and say which system it is for.

        The system used to be assumed to be Game Boy Color, which was right
        often enough to be quietly wrong the rest of the time: it decides
        which directory the cheat file goes in on the card.
        """
        # If a group row is selected, that system is the obvious default.
        sel = self.gamelist.selection()
        preset = carts.DEFAULT_PLATFORM
        if sel and sel[0].startswith(GROUP):
            preset = sel[0][len(GROUP):]
        elif isinstance(self.selected_game(), carts.Cartridge):
            preset = self.selected_game().platform

        result = CartDialog(self, preset, self.platform_name).result
        if result is None:
            return
        name, plat = result
        if not carts.add(name, plat):
            messagebox.showinfo("Cartridges", f"{name} is already listed.")
            return
        self.after_cart_change(name)

    def after_cart_change(self, select: str | None = None) -> None:
        """Redraw the pane and put the selection back on a named cartridge."""
        self.systems.item(CARTS, values=(len(carts.all()),))
        self.show_carts()
        if select is None:
            return
        for i, c in enumerate(self.games):
            if c.name == select:
                self.gamelist.see(str(i))
                self.gamelist.selection_set(str(i))
                break

    def move_cart(self) -> None:
        """File the selected cartridge under the other system."""
        cart = self.selected_game()
        if not isinstance(cart, carts.Cartridge):
            return
        other = self.other_platform(cart.platform)
        if not messagebox.askyesno(
                "Cartridges",
                f"File {cart.name} under {self.platform_name(other)}?\n\n"
                "The cheat file goes in that system's folder from now on. "
                "Any file already written under "
                f"{self.platform_name(cart.platform)} is left where it is."):
            return
        carts.set_platform(cart.name, other)
        self.after_cart_change(cart.name)

    @staticmethod
    def other_platform(pid: str) -> str:
        """There are two, so moving is a flip rather than a choice."""
        return next(p for p in carts.PLATFORMS if p != pid)

    def remove_cart(self) -> None:
        cart = self.selected_game()
        if not isinstance(cart, carts.Cartridge):
            return
        if not messagebox.askyesno(
                "Cartridges",
                f"Remove {cart.name} from the list?\n\n"
                "The cheat file already on the card is left alone."):
            return
        carts.remove(cart.name)
        self.after_cart_change()

    def selected_game(self):
        """The object for the selected row, or None if there is no live one.

        The pane and self.games are filled from two places, one of them a
        worker callback, so a row index is checked rather than trusted.
        """
        sel = self.gamelist.selection()
        if not sel:
            return None
        try:
            idx = int(sel[0])
        except ValueError:
            return None
        return self.games[idx] if 0 <= idx < len(self.games) else None

    def on_game(self, _evt=None) -> None:
        game = self.selected_game()
        if game is None:
            # A system heading, or nothing. Neither is something to act on.
            self.del_btn.state(["disabled"])
            self.move_btn.state(["disabled"])
            return
        is_cart = isinstance(game, carts.Cartridge)
        self.del_btn.state(["!disabled"] if is_cart else ["disabled"])
        self.move_btn.state(["!disabled"] if is_cart else ["disabled"])
        if is_cart:
            self.move_btn.config(
                text="Move to " + self.platform_name(
                    self.other_platform(game.platform)))
        self.status.config(text="loading...", foreground="#000")
        self.worker.submit(lambda: model.load(game), self._loaded, "load")

    def _loaded(self, view, err) -> None:
        if isinstance(err, library.MissingDatabase):
            # Not worth a dialog. This is the state a freshly downloaded build
            # starts in, it is not a failure, and the fix is one button away.
            self.status.config(
                text="no cheat database yet: press Update, at the bottom",
                foreground="#a00")
            return
        if err is not None:
            messagebox.showerror("Cheats", f"Could not read cheats:\n{err}")
            self.status.config(text="")
            return
        self.view = view
        self.refresh_cheats()
        self.source_btn.state(["!disabled"])
        self.save_btn.state(["!disabled"])

    def retune_meter(self, platform: str) -> None:
        """The code store is the core's, so its size follows the system."""
        if platform == self.meter_platform:
            return
        self.meter_platform = platform
        got = cheatfile.limits(platform)
        self.meter.set_limit(got[1] if got else None)

    def refresh_cheats(self) -> None:
        v = self.view
        self.cheats.delete(*self.cheats.get_children())
        if v is None:
            self.meter.set(0)
            return
        if v.source:
            marks = []
            if library.is_local(v.source):
                marks.append("yours")
            if v.pinned:
                # otherwise a remembered choice silently beats a file you just
                # wrote, and there is nothing on screen to say why
                marks.append("pinned")
            mark = ("  (" + ", ".join(marks) + ")") if marks else ""
            label = "source: " + os.path.basename(v.source) + mark
        else:
            label = "no matching cheat file found"
        self.source_label.config(text=label)
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
            self.meter.set(0)
            return
        self.retune_meter(v.platform)
        codes = sum(len(e.group.codes) for e in v.enabled)
        self.meter.set(codes)
        written, patched = v.applied_counts
        msg = f"{len(v.enabled)} of {len(v.entries)} cheats on"
        if written or patched:
            msg += f" ({written} written, {patched} patched)"
        elif not cheatfile.decoded(v.platform):
            msg += "   codes carried as written; this core does not read them yet"
        problems = list(v.problems)
        # On a cartridge you cannot check the revision, and the two kinds of
        # code fail differently when it is wrong: a Game Genie patch carries a
        # compare byte and simply never fires, while a GameShark code is a real
        # write to an address that may hold something else entirely.
        if isinstance(v.game, carts.Cartridge) and written:
            problems.append(f"{written} written codes: unverifiable on a cartridge")
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
        def write():
            result = v.save()
            if self.card:
                self.card.sync()      # can take seconds on a slow card
            return result

        self.save_btn.state(["disabled"])
        self.status.config(text="writing to the card...", foreground="#000")
        self.worker.submit(write, self._saved, "save")

    def _saved(self, result, err) -> None:
        self.save_btn.state(["!disabled"])
        if err is not None:
            messagebox.showerror("Cheats", f"Could not write:\n{err}")
            self.status.config(text="")
            return
        cheats, codes = result
        sel = self.gamelist.selection()
        if sel:
            self.gamelist.item(sel[0], values=(cheats if cheats else "",))
        self.status.config(
            text=f"wrote {cheats} cheats / {codes} codes to the card",
            foreground="#060")


class CartDialog(tk.Toplevel):
    """Name a cartridge and say which system it is for.

    Its own window rather than simpledialog.askstring, because the system is
    not optional detail: it decides which folder on the card the cheat file
    goes in, and the core's file browser opens on that folder.
    """

    def __init__(self, app, preset: str, name_of) -> None:
        super().__init__(app)
        self.result: tuple[str, str] | None = None
        self.title("Add cartridge")
        self.transient(app)
        self.resizable(False, False)
        self.columnconfigure(0, weight=1)

        body = ttk.Frame(self, padding=10)
        body.grid(row=0, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)

        ttk.Label(body, justify="left", text=(
            "Name it exactly as the ROM is named, including the region and\n"
            "revision tags. That name is the whole of the matching:\n\n"
            "    Legend of Zelda, The - Link's Awakening DX (USA, Europe) (Rev 2)"
        )).grid(row=0, column=0, sticky="w")

        self.entry = ttk.Entry(body, width=64)
        self.entry.grid(row=1, column=0, sticky="ew", pady=(8, 10))

        systems = ttk.LabelFrame(body, text="System", padding=6)
        systems.grid(row=2, column=0, sticky="ew")
        self.platform = tk.StringVar(value=preset)
        for i, pid in enumerate(carts.PLATFORMS):
            ttk.Radiobutton(systems, text=name_of(pid), value=pid,
                            variable=self.platform).grid(row=0, column=i,
                                                         padx=(0, 12), sticky="w")
        ttk.Label(body, foreground="#666", wraplength=440, justify="left", text=(
            "This decides which folder the cheat file goes in on the card. "
            "Get it wrong and the core's Load Cheats browser will not be "
            "looking where the file is."
        )).grid(row=3, column=0, sticky="w", pady=(8, 0))

        row = ttk.Frame(body)
        row.grid(row=4, column=0, sticky="e", pady=(12, 0))
        ttk.Button(row, text="Cancel", command=self.destroy).pack(side="right",
                                                                  padx=(6, 0))
        ttk.Button(row, text="Add", command=self.ok).pack(side="right")

        self.bind("<Return>", lambda _e: self.ok())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.entry.focus_set()
        self.grab_set()
        self.wait_window(self)

    def ok(self) -> None:
        name = self.entry.get().strip()
        if not name:
            self.entry.focus_set()
            return
        self.result = (name, self.platform.get())
        self.destroy()


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
            mark = "* " if c.local else "  "
            self.list.insert("end",
                             f"{mark}{c.score:.2f}  {os.path.basename(c.path)}")
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
    root.title(version.title())
    root.geometry("1080x620")
    App(root)
    root.mainloop()
    return 0
