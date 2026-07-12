"""Minty Cat Pomodoro — a cozy, standalone study timer.

Run with Python on Windows.  It only uses the standard library.
The app saves notes, tasks, and timer preferences in a JSON file beside itself.
On Windows, a small cat-like WAV sound is generated automatically and played at
the end of each focus/break block.  Other platforms fall back to a bell.
"""

from __future__ import annotations

import json
import math
import platform
import struct
import tkinter as tk
import wave
from pathlib import Path
from tkinter import messagebox, ttk


APP_DIR = Path(__file__).resolve().parent
DATA_FILE = APP_DIR / "minty_cat_pomodoro_data.json"
MEOW_FILE = APP_DIR / "minty_meow.wav"
PURR_FILE = APP_DIR / "minty_purr.wav"
MRRP_FILE = APP_DIR / "minty_mrrp.wav"
TRILL_FILE = APP_DIR / "minty_happy_trill.wav"

# Dark, cozy charcoal and maroon palette.  The old variable names are kept so
# the rest of the example remains easy to follow.
COLORS = {
    "deep": "#171317", "forest": "#8E3F5B", "mint": "#5C525D",
    "pale": "#242025", "cream": "#332C34", "ink": "#FFF8F9",
    "rose": "#D67687", "sun": "#F0C980", "sky": "#B7B0C9",
    "line": "#746670", "muted": "#E5D9DE",
}


class SoundPlayer:
    """Generate and play small, friendly synthetic cat-like notification sounds.

    Keeping the sound generator in the program avoids requiring an external WAV
    download. It is not a recording of a real cat; it is a gentle sound effect.
    """

    def __init__(self) -> None:
        self._create_sounds_if_missing()

    @staticmethod
    def _write_wave(path: Path, samples: list[int], sample_rate: int = 22050) -> None:
        with wave.open(str(path), "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)  # signed 16-bit samples
            audio.setframerate(sample_rate)
            audio.writeframes(b"".join(struct.pack("<h", sample) for sample in samples))

    def _create_sounds_if_missing(self) -> None:
        sample_rate = 22050
        if not MEOW_FILE.exists():
            # Two softly sliding tones plus a fade envelope create a meow-ish cue.
            samples = []
            duration = 0.95
            for index in range(int(sample_rate * duration)):
                t = index / sample_rate
                progress = t / duration
                frequency = 620 - 350 * progress + 35 * math.sin(2 * math.pi * 3 * t)
                envelope = min(1, t / .08, (duration - t) / .20)
                value = envelope * (math.sin(2 * math.pi * frequency * t) + .34 * math.sin(4 * math.pi * frequency * t))
                samples.append(int(11000 * value))
            self._write_wave(MEOW_FILE, samples, sample_rate)
        if not PURR_FILE.exists():
            samples = []
            duration = 1.2
            for index in range(int(sample_rate * duration)):
                t = index / sample_rate
                envelope = min(1, t / .12, (duration - t) / .15)
                purr_pulse = .55 + .45 * math.sin(2 * math.pi * 25 * t)
                value = envelope * purr_pulse * (math.sin(2 * math.pi * 95 * t) + .25 * math.sin(2 * math.pi * 190 * t))
                samples.append(int(9000 * value))
            self._write_wave(PURR_FILE, samples, sample_rate)
        if not MRRP_FILE.exists():
            # A brief low-to-high "mrrp" sound, like a small greeting.
            samples = []
            duration = 0.50
            for index in range(int(sample_rate * duration)):
                t = index / sample_rate
                progress = t / duration
                frequency = 290 + 310 * progress
                envelope = min(1, t / .04, (duration - t) / .12)
                value = envelope * (math.sin(2 * math.pi * frequency * t) + .22 * math.sin(4 * math.pi * frequency * t))
                samples.append(int(10500 * value))
            self._write_wave(MRRP_FILE, samples, sample_rate)
        if not TRILL_FILE.exists():
            # A light warbling trill formed by gently moving the pitch.
            samples = []
            duration = 0.72
            for index in range(int(sample_rate * duration)):
                t = index / sample_rate
                frequency = 510 + 90 * math.sin(2 * math.pi * 19 * t)
                envelope = min(1, t / .05, (duration - t) / .15)
                value = envelope * (math.sin(2 * math.pi * frequency * t) + .18 * math.sin(4 * math.pi * frequency * t))
                samples.append(int(9500 * value))
            self._write_wave(TRILL_FILE, samples, sample_rate)

    def play(self, sound: str) -> None:
        """Play asynchronously so sound never freezes the Tkinter interface."""
        if platform.system() == "Windows":
            try:
                import winsound
                sound_files = {
                    "Meow": MEOW_FILE,
                    "Purr": PURR_FILE,
                    "Mrrp": MRRP_FILE,
                    "Happy trill": TRILL_FILE,
                }
                file = sound_files.get(sound, MEOW_FILE)
                winsound.PlaySound(str(file), winsound.SND_FILENAME | winsound.SND_ASYNC)
                return
            except (ImportError, RuntimeError):
                pass
        # A portable fallback for non-Windows computers.
        try:
            self.root.bell()  # type: ignore[attr-defined]
        except AttributeError:
            pass


class DataStore:
    """Simple local persistence for the user’s tasks, note, and preferences."""

    defaults = {
        "work": 25, "break": 5, "cycles": 4, "sound": "Meow",
        "tasks": [], "notes": "",
    }

    def __init__(self, path: Path) -> None:
        self.path = path
        self.data = self.defaults.copy()
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                self.data.update(loaded)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            pass  # First run or unreadable data: use clean defaults.

    def save(self) -> None:
        self.path.write_text(json.dumps(self.data, indent=2), encoding="utf-8")


class MintyCatPomodoro(tk.Tk):
    """Owns the timer logic, interface, task list, notes, and sound events."""

    def __init__(self) -> None:
        super().__init__()
        self.store = DataStore(DATA_FILE)
        self.sound = SoundPlayer()
        # Give the fallback bell function access to this root window.
        self.sound.root = self

        self.title("Kylle's Study Corner · Maroon Cat Pomodoro")
        self.geometry("1110x735")
        self.minsize(950, 635)
        self.configure(bg=COLORS["pale"])

        self.running = False
        self.is_break = False
        self.completed_cycles = 0
        self.remaining_seconds = int(self.store.data["work"]) * 60
        self.timer_job: str | None = None

        self.work_var = tk.StringVar(value=str(self.store.data["work"]))
        self.break_var = tk.StringVar(value=str(self.store.data["break"]))
        self.cycles_var = tk.StringVar(value=str(self.store.data["cycles"]))
        self.sound_var = tk.StringVar(value=str(self.store.data["sound"]))
        self.task_var = tk.StringVar()

        self._configure_styles()
        self._build_ui()
        self._refresh_tasks()
        self._refresh_timer_display()
        self.protocol("WM_DELETE_WINDOW", self._close)

    # --------------------------- GUI design ---------------------------
    def _configure_styles(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background=COLORS["pale"])
        style.configure("Panel.TFrame", background=COLORS["cream"], bordercolor=COLORS["line"], borderwidth=1, relief="raised")
        style.configure("TLabel", background=COLORS["cream"], foreground=COLORS["ink"], font=("Segoe UI", 10))
        style.configure("Title.TLabel", background=COLORS["pale"], foreground=COLORS["deep"], font=("Georgia", 25, "bold"))
        style.configure("Subtitle.TLabel", background=COLORS["pale"], foreground=COLORS["muted"], font=("Segoe UI", 10, "italic"))
        style.configure("PanelTitle.TLabel", background=COLORS["cream"], foreground=COLORS["forest"], font=("Georgia", 13, "bold"))
        style.configure("Mint.TButton", background=COLORS["forest"], foreground="white", font=("Segoe UI", 10, "bold"), padding=(10, 7))
        style.map("Mint.TButton", background=[("active", COLORS["deep"])])
        style.configure("Soft.TButton", background=COLORS["mint"], foreground=COLORS["ink"], font=("Segoe UI", 10, "bold"), padding=(10, 7))
        style.map("Soft.TButton", background=[("active", COLORS["sky"])])
        style.configure("Rose.TButton", background=COLORS["rose"], foreground=COLORS["ink"], font=("Segoe UI", 10, "bold"), padding=(10, 7))
        style.configure("TEntry", fieldbackground="#221E23", foreground=COLORS["ink"], insertcolor=COLORS["ink"], padding=5)
        style.configure("TCombobox", fieldbackground="#221E23", background=COLORS["mint"], foreground=COLORS["ink"], padding=5)
        style.configure("TSpinbox", fieldbackground="#221E23", foreground=COLORS["ink"], padding=5)

    def _panel(self, parent: ttk.Frame, col: int, padding: tuple[int, int]) -> ttk.Frame:
        panel = ttk.Frame(parent, style="Panel.TFrame", padding=17)
        panel.grid(row=0, column=col, sticky="nsew", padx=padding)
        return panel

    def _build_ui(self) -> None:
        header = ttk.Frame(self)
        header.pack(fill="x", padx=29, pady=(20, 11))
        title_area = ttk.Frame(header)
        title_area.pack(side="left", fill="x", expand=True)
        ttk.Label(title_area, text="Maroon Cat Pomodoro  ฅ^•ﻌ•^ฅ", style="Title.TLabel").pack(anchor="w")
        ttk.Label(title_area, text="Kylle's Study Corner · a quiet place for focus, notes, and tiny victories.", style="Subtitle.TLabel").pack(anchor="w")
        self._draw_cat(header).pack(side="right", padx=(12, 2))

        main = ttk.Frame(self)
        main.pack(fill="both", expand=True, padx=29, pady=(0, 25))
        main.columnconfigure(0, weight=0, minsize=250)
        main.columnconfigure(1, weight=1, minsize=380)
        main.columnconfigure(2, weight=1, minsize=280)
        main.rowconfigure(0, weight=1)
        self._build_settings(self._panel(main, 0, (0, 13)))
        self._build_timer(self._panel(main, 1, (0, 13)))
        self._build_workspace(self._panel(main, 2, (0, 0)))

    def _draw_cat(self, parent: ttk.Frame) -> tk.Canvas:
        """Draw a tiny original sleepy cat using Canvas shapes—no image file needed."""
        cat = tk.Canvas(parent, width=122, height=76, bg=COLORS["pale"], highlightthickness=0)
        fur, shade, blush = "#B78C9B", "#744353", "#D88493"
        # Curled body and head
        cat.create_oval(38, 29, 113, 69, fill=fur, outline=shade, width=2)
        cat.create_oval(16, 16, 70, 60, fill=fur, outline=shade, width=2)
        # Ears
        cat.create_polygon(22, 26, 27, 5, 40, 21, fill=fur, outline=shade, width=2)
        cat.create_polygon(51, 20, 65, 5, 67, 30, fill=fur, outline=shade, width=2)
        # Sleepy face and curled tail
        cat.create_arc(28, 33, 42, 42, start=180, extent=180, style="arc", outline=COLORS["deep"], width=2)
        cat.create_arc(47, 33, 61, 42, start=180, extent=180, style="arc", outline=COLORS["deep"], width=2)
        cat.create_oval(36, 43, 40, 46, fill=COLORS["deep"], outline="")
        cat.create_arc(69, 38, 113, 69, start=260, extent=210, style="arc", outline=shade, width=5)
        cat.create_oval(25, 43, 31, 47, fill=blush, outline="")
        cat.create_oval(55, 43, 61, 47, fill=blush, outline="")
        return cat

    def _build_settings(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Your cozy setup", style="PanelTitle.TLabel").pack(anchor="w")
        for text, variable, low, high in [
            ("Focus minutes", self.work_var, 5, 90),
            ("Break minutes", self.break_var, 1, 30),
            ("Pomodoro cycles", self.cycles_var, 1, 12),
        ]:
            ttk.Label(parent, text=text).pack(anchor="w", pady=(13, 3))
            spin = ttk.Spinbox(parent, from_=low, to=high, textvariable=variable, width=12)
            spin.pack(anchor="w")
        ttk.Label(parent, text="Finish sound").pack(anchor="w", pady=(13, 3))
        ttk.Combobox(parent, textvariable=self.sound_var, values=["Meow", "Purr", "Mrrp", "Happy trill"], state="readonly", width=12).pack(anchor="w")
        ttk.Button(parent, text="Save settings", style="Soft.TButton", command=self._save_settings).pack(fill="x", pady=(13, 0))

        tk.Label(parent, text="Tip: use a short break to stand, sip water, and gently reset your eyes.", justify="left",
                 wraplength=210, bg=COLORS["mint"], fg=COLORS["deep"], font=("Segoe UI", 9), padx=10, pady=9).pack(fill="x", pady=(22, 0))
        ttk.Button(parent, text="Test cat sound", style="Soft.TButton", command=lambda: self.sound.play(self.sound_var.get())).pack(fill="x", pady=(10, 0))

    def _build_timer(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Focus timer", style="PanelTitle.TLabel").pack(anchor="w")
        # The timer uses its own almost-black "night clock" panel so the
        # large white numerals remain readable at a glance.
        self.mode_label = tk.Label(parent, text="FOCUS", bg=COLORS["forest"], fg=COLORS["ink"], font=("Segoe UI", 9, "bold"), padx=10, pady=4)
        self.mode_label.pack(anchor="w", pady=(10, 1))
        clock_panel = tk.Frame(parent, bg=COLORS["deep"], highlightbackground=COLORS["rose"], highlightthickness=2)
        clock_panel.pack(fill="x", pady=(5, 0))
        self.clock_label = tk.Label(clock_panel, text="25:00", bg=COLORS["deep"], fg="#FFFFFF", font=("Georgia", 58, "bold"))
        self.clock_label.pack(pady=(9, 0))
        self.cycle_label = tk.Label(clock_panel, text="", bg=COLORS["deep"], fg="#F4DDE4", font=("Segoe UI", 11, "bold"))
        self.cycle_label.pack(pady=(0, 11))

        buttons = ttk.Frame(parent, style="Panel.TFrame")
        buttons.pack(fill="x")
        self.start_button = ttk.Button(buttons, text="Start focus", style="Mint.TButton", command=self._toggle_timer)
        self.start_button.pack(side="left", expand=True, fill="x", padx=(0, 4))
        ttk.Button(buttons, text="Reset", style="Rose.TButton", command=self._reset_timer).pack(side="left", padx=(4, 0))

        self.status_label = tk.Label(parent, text="Press Start when you are ready. Your cat is cheering quietly.",
                                     justify="center", wraplength=320, bg=COLORS["cream"], fg=COLORS["ink"], font=("Segoe UI", 10, "bold"))
        self.status_label.pack(fill="x", pady=(24, 0))

    def _build_workspace(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Study desk", style="PanelTitle.TLabel").pack(anchor="w")
        ttk.Label(parent, text="Quick task list").pack(anchor="w", pady=(11, 3))
        entry_row = ttk.Frame(parent, style="Panel.TFrame")
        entry_row.pack(fill="x")
        task_entry = ttk.Entry(entry_row, textvariable=self.task_var)
        task_entry.pack(side="left", expand=True, fill="x", padx=(0, 6))
        task_entry.bind("<Return>", lambda _event: self._add_task())
        ttk.Button(entry_row, text="Add", style="Mint.TButton", command=self._add_task).pack(side="left")

        list_row = ttk.Frame(parent, style="Panel.TFrame")
        list_row.pack(fill="both", expand=True, pady=(8, 5))
        self.task_list = tk.Listbox(list_row, height=8, bg="#221E23", fg=COLORS["ink"], selectbackground=COLORS["forest"],
                                    selectforeground=COLORS["deep"], relief="flat", activestyle="none", font=("Segoe UI", 10), exportselection=False)
        self.task_list.pack(side="left", fill="both", expand=True)
        self.task_list.bind("<Double-Button-1>", lambda _event: self._toggle_task_done())
        scrollbar = ttk.Scrollbar(list_row, orient="vertical", command=self.task_list.yview)
        scrollbar.pack(side="right", fill="y")
        self.task_list.configure(yscrollcommand=scrollbar.set)
        task_buttons = ttk.Frame(parent, style="Panel.TFrame")
        task_buttons.pack(fill="x")
        ttk.Button(task_buttons, text="Mark done / undo", style="Soft.TButton", command=self._toggle_task_done).pack(side="left", expand=True, fill="x", padx=(0, 3))
        ttk.Button(task_buttons, text="Remove", style="Rose.TButton", command=self._remove_task).pack(side="left", padx=(3, 0))

        ttk.Label(parent, text="Notes to future me").pack(anchor="w", pady=(12, 3))
        self.notes = tk.Text(parent, height=7, wrap="word", bg="#221E23", fg=COLORS["ink"], insertbackground=COLORS["ink"], relief="flat", font=("Segoe UI", 10), padx=8, pady=7)
        self.notes.pack(fill="both", expand=True)
        self.notes.insert("1.0", self.store.data.get("notes", ""))
        self.notes.bind("<FocusOut>", lambda _event: self._save_notes())

    # --------------------------- Timer logic --------------------------
    def _read_settings(self) -> tuple[int, int, int] | None:
        """Validate the three editable timer inputs before using them."""
        try:
            work, rest, cycles = int(self.work_var.get()), int(self.break_var.get()), int(self.cycles_var.get())
            if not (5 <= work <= 90 and 1 <= rest <= 30 and 1 <= cycles <= 12):
                raise ValueError
            return work, rest, cycles
        except ValueError:
            messagebox.showerror("Check your settings", "Focus: 5–90 min · Break: 1–30 min · Cycles: 1–12", parent=self)
            return None

    def _save_settings(self) -> None:
        values = self._read_settings()
        if values is None:
            return
        work, rest, cycles = values
        self.store.data.update({"work": work, "break": rest, "cycles": cycles, "sound": self.sound_var.get()})
        self.store.save()
        if not self.running:
            self.is_break = False
            self.remaining_seconds = work * 60
            self._refresh_timer_display()
        self.status_label.configure(text="Settings saved. Your next focus block is ready when you are.")

    def _toggle_timer(self) -> None:
        """Start or pause the timer. Tkinter's `after` updates it every second."""
        self.running = not self.running
        if self.running:
            self.start_button.configure(text="Pause")
            self.status_label.configure(text="One small task at a time. You’ve got this.")
            self._tick()
        else:
            if self.timer_job is not None:
                self.after_cancel(self.timer_job)
                self.timer_job = None
            self.start_button.configure(text="Resume")
            self.status_label.configure(text="Paused. Take your time—focus does not have to be rushed.")

    def _tick(self) -> None:
        if not self.running:
            return
        self._refresh_timer_display()
        if self.remaining_seconds <= 0:
            self._finish_block()
            # A new block starts at its full displayed time. If the whole set
            # is complete, do not queue another callback.
            if not self.running:
                return
        else:
            self.remaining_seconds -= 1
        self.timer_job = self.after(1000, self._tick)

    def _finish_block(self) -> None:
        """Switch focus ↔ break, or finish a whole set of Pomodoro cycles."""
        self.sound.play(self.sound_var.get())
        work, rest, cycles = self._read_settings() or (25, 5, 4)
        if not self.is_break:
            self.completed_cycles += 1
            if self.completed_cycles >= cycles:
                self.running = False
                self.is_break = False
                self.remaining_seconds = work * 60
                self.start_button.configure(text="Start a new set")
                self.status_label.configure(text="Your Pomodoro set is complete! Stretch, hydrate, and accept a tiny imaginary cat high-five. 🐾")
                messagebox.showinfo("Set complete!", "You finished your planned focus cycles. Great work! 🐾", parent=self)
                return
            self.is_break = True
            self.remaining_seconds = rest * 60
            self.status_label.configure(text="Focus block complete! Enjoy your little break.")
            messagebox.showinfo("Break time 🐱", "Focus block complete. Your cat says: take a gentle break!", parent=self)
        else:
            self.is_break = False
            self.remaining_seconds = work * 60
            self.status_label.configure(text="Break complete. A fresh focus block is beginning.")
            messagebox.showinfo("Back to focus", "Break complete—welcome back to your study desk.", parent=self)
        self._refresh_timer_display()

    def _refresh_timer_display(self) -> None:
        minutes, seconds = divmod(max(0, self.remaining_seconds), 60)
        self.clock_label.configure(text=f"{minutes:02d}:{seconds:02d}")
        # Use the last saved valid value during display refreshes; this avoids
        # showing validation pop-ups every second while someone edits a field.
        total_cycles = int(self.store.data.get("cycles", 4))
        self.mode_label.configure(text="BREAK" if self.is_break else "FOCUS")
        current = min(self.completed_cycles + 1, total_cycles)
        self.cycle_label.configure(text=f"Cycle {current} of {total_cycles}")

    def _reset_timer(self) -> None:
        if self.timer_job is not None:
            self.after_cancel(self.timer_job)
        self.timer_job = None
        self.running = False
        self.is_break = False
        self.completed_cycles = 0
        values = self._read_settings()
        self.remaining_seconds = (values[0] if values else 25) * 60
        self.start_button.configure(text="Start focus")
        self.status_label.configure(text="Timer reset. A calm new start is waiting for you.")
        self._refresh_timer_display()

    # ------------------------ Task-list management --------------------
    def _add_task(self) -> None:
        text = self.task_var.get().strip()
        if not text:
            return
        self.store.data["tasks"].append({"text": text, "done": False})
        self.task_var.set("")
        self.store.save()
        self._refresh_tasks()

    def _selected_index(self) -> int | None:
        selection = self.task_list.curselection()
        return selection[0] if selection else None

    def _toggle_task_done(self) -> None:
        index = self._selected_index()
        if index is None:
            return
        task = self.store.data["tasks"][index]
        task["done"] = not task["done"]
        self.store.save()
        self._refresh_tasks(index)

    def _remove_task(self) -> None:
        index = self._selected_index()
        if index is None:
            return
        self.store.data["tasks"].pop(index)
        self.store.save()
        self._refresh_tasks()

    def _refresh_tasks(self, select_index: int | None = None) -> None:
        self.task_list.delete(0, "end")
        for task in self.store.data.get("tasks", []):
            prefix = "✓ " if task.get("done") else "☐ "
            self.task_list.insert("end", prefix + task.get("text", ""))
        if select_index is not None and select_index < self.task_list.size():
            self.task_list.selection_set(select_index)

    def _save_notes(self) -> None:
        self.store.data["notes"] = self.notes.get("1.0", "end-1c")
        self.store.save()

    def _close(self) -> None:
        self._save_notes()
        if self.timer_job is not None:
            self.after_cancel(self.timer_job)
        self.destroy()


if __name__ == "__main__":
    MintyCatPomodoro().mainloop()
