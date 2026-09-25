"""Presentation and layout for the desktop workspace."""

import tkinter as tk
from tkinter import ttk

from .pdf import PAPER_SIZES


BG = "#eef2f3"
INK = "#182f3a"
MUTED = "#657984"
ACCENT = "#087e83"
PREVIEW = "#172b36"


class WorkspaceUI:
    def build_ui(self):
        self.configure(bg=BG)
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", font=("Segoe UI", 10), foreground=INK, background=BG)
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background="white")
        style.configure("TLabel", background=BG)
        style.configure("Card.TLabel", background="white")
        style.configure("Muted.TLabel", foreground=MUTED)
        style.configure("Hint.TLabel", background="white", foreground=MUTED, font=("Segoe UI", 9))
        style.configure("Title.TLabel", font=("Segoe UI", 21, "bold"))
        style.configure("Section.TLabel", background="white", font=("Segoe UI", 12, "bold"))
        style.configure("Eyebrow.TLabel", foreground=ACCENT, font=("Segoe UI", 9, "bold"))
        style.configure("Badge.TLabel", background="#dcefee", foreground=ACCENT, padding=(12, 6),
                        font=("Segoe UI", 9, "bold"))
        style.configure("TButton", background="white", bordercolor="#cedade", lightcolor="white",
                        darkcolor="white", padding=(10, 6), focuscolor=ACCENT, width=0)
        style.map("TButton", background=[("active", "#e3eeef"), ("disabled", "#edf1f2")],
                  foreground=[("disabled", "#98a5ab")])
        style.configure("Primary.TButton", background=ACCENT, foreground="white", bordercolor=ACCENT,
                        lightcolor=ACCENT, darkcolor=ACCENT, font=("Segoe UI", 10, "bold"))
        style.map("Primary.TButton", background=[("disabled", "#dbe7e8"), ("active", "#06666b")],
                  foreground=[("disabled", "#82999c"), ("!disabled", "white")],
                  bordercolor=[("disabled", "#dbe7e8")])
        style.configure("TEntry", padding=7, fieldbackground="white", bordercolor="#cedade",
                        lightcolor="white", darkcolor="white", insertcolor=INK)
        style.map("TEntry", bordercolor=[("focus", ACCENT)])
        style.configure("TCombobox", padding=6, arrowsize=13, bordercolor="#cedade")
        style.map("TCombobox", fieldbackground=[("readonly", "white")],
                  selectbackground=[("readonly", "white")], selectforeground=[("readonly", INK)])
        style.configure("TSpinbox", padding=6, bordercolor="#cedade", fieldbackground="white")
        style.configure("TCheckbutton", background="white", padding=(0, 4))
        style.map("TCheckbutton", background=[("active", "white")])
        style.configure("Mode.TRadiobutton", background="white", padding=(10, 8),
                        indicatorrelief="flat", font=("Segoe UI", 10, "bold"))
        style.map("Mode.TRadiobutton", background=[("selected", "#dcefee"), ("active", "#eef5f5")],
                  foreground=[("selected", ACCENT)])
        style.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(0, 0, 0, 10))
        style.configure("TNotebook.Tab", padding=(18, 8), background=BG, borderwidth=0,
                        font=("Segoe UI", 10, "bold"))
        style.map("TNotebook.Tab", background=[("selected", INK), ("active", "#dde7e9")],
                  foreground=[("selected", "white")], padding=[("selected", (18, 8))],
                  expand=[("selected", (0, 0, 0, 0))])
        style.configure("Horizontal.TProgressbar", background=ACCENT, troughcolor="#dce5e8",
                        borderwidth=0, lightcolor=ACCENT, darkcolor=ACCENT, thickness=4)
        style.configure("Horizontal.TScale", background="white", troughcolor="#dce5e8")

        outer = ttk.Frame(self, padding=(20, 14))
        outer.pack(fill="both", expand=True)
        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 12))
        self.action(header, "Open project…", self.open_project).pack(side="right", anchor="center", pady=10)
        ttk.Label(header, text="Video Sheet to PDF", style="Title.TLabel").pack(anchor="w", pady=(2, 0))

        source_card = ttk.Frame(outer, style="Card.TFrame", padding=(16, 12))
        source_card.pack(fill="x", pady=(0, 12))
        source_card.columnconfigure(0, weight=1)
        ttk.Label(source_card, text="VIDEO SOURCE", style="Hint.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 6))
        ttk.Label(source_card, text="YouTube link or local video", style="Hint.TLabel").grid(row=0, column=1, columnspan=2, sticky="e", pady=(0, 6))
        self.source_entry = ttk.Entry(source_card, textvariable=self.source)
        self.source_entry.grid(row=1, column=0, sticky="ew", padx=(0, 10))
        self.action(source_card, "Choose file…", self.choose_file).grid(row=1, column=1, padx=(0, 8))
        self.load_button = self.action(source_card, "Load video", self.load_video, primary=True)
        self.load_button.grid(row=1, column=2)
        self.source_entry.bind("<Return>", lambda event: self.load_button.invoke())

        footer = ttk.Frame(outer)
        footer.pack(side="bottom", fill="x", pady=(8, 0))
        footer.columnconfigure(1, weight=1)
        self.activity_label = ttk.Label(footer, text="READY", style="Eyebrow.TLabel", width=10)
        self.activity_label.grid(row=0, column=0, sticky="nw", pady=7)
        status_label = ttk.Label(footer, textvariable=self.status, style="Muted.TLabel", wraplength=760)
        status_label.grid(row=0, column=1, sticky="ew", padx=(8, 16), pady=7)
        status_label.bind("<Configure>", lambda e: status_label.configure(wraplength=max(100, e.width)))
        self.cancel_button = ttk.Button(footer, text="Cancel", command=self.cancel.set, state="disabled")
        self.cancel_button.grid(row=0, column=2, sticky="ne")
        self.progress = ttk.Progressbar(footer, maximum=1, orient="horizontal")
        self.progress.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(6, 0))

        self.tabs = ttk.Notebook(outer)
        self.tabs.pack(fill="both", expand=True)
        setup = ttk.Frame(self.tabs)
        review = ttk.Frame(self.tabs)
        self.tabs.add(setup, text="01   Score area")
        self.tabs.add(review, text="02   Review & export")
        self.tabs.bind("<<NotebookTabChanged>>", self.tab_changed)
        self.build_capture(setup)
        self.build_review(review)
        self.source_entry.focus_set()
        self.sync_controls()

    def build_capture(self, setup):
        setup.columnconfigure(1, weight=1)
        setup.rowconfigure(0, weight=1)
        sidebar = ttk.Frame(setup, style="Card.TFrame", padding=16, width=258)
        sidebar.grid(row=0, column=0, sticky="ns", padx=(0, 12))
        sidebar.columnconfigure(0, weight=1)
        ttk.Label(sidebar, text="Capture settings", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        mode_row = ttk.Frame(sidebar, style="Card.TFrame")
        mode_row.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        for mode in ("Automatic", "Manual"):
            ttk.Radiobutton(mode_row, text=mode, value=mode, variable=self.capture_mode,
                            style="Mode.TRadiobutton", command=self.change_capture_mode).pack(side="left", expand=True, fill="x")
        self.mode_hint = ttk.Label(sidebar, style="Hint.TLabel", wraplength=224,
                                  text="Drag on the preview to set the crop, then extract your score.")
        self.mode_hint.grid(row=3, column=0, sticky="w", pady=(10, 12))

        self.layout_row = ttk.Frame(sidebar, style="Card.TFrame")
        self.layout_row.grid(row=4, column=0, sticky="ew")
        ttk.Label(self.layout_row, text="Score layout", style="Card.TLabel").pack(anchor="w", pady=(0, 6))
        ttk.Combobox(self.layout_row, textvariable=self.mode, values=["auto", "bottom", "page"],
                     state="readonly", width=23).pack(fill="x")
        self.detect_button = self.action(self.layout_row, "Detect score area", self.detect_region)
        self.detect_button.pack(fill="x", pady=(8, 16))

        self.auto_options = ttk.Frame(sidebar, style="Card.TFrame")
        self.auto_options.grid(row=5, column=0, sticky="ew")
        self.action(self.auto_options, "Extraction settings…", self.extraction_settings).pack(fill="x")
        ttk.Label(self.auto_options, text="Sampling, sensitivity & time range", style="Hint.TLabel").pack(anchor="w", pady=(6, 0))
        sidebar.rowconfigure(6, weight=1)

        workspace = ttk.Frame(setup, style="Card.TFrame", padding=14)
        workspace.grid(row=0, column=1, sticky="nsew")
        workspace.columnconfigure(0, weight=1)
        workspace.rowconfigure(2, weight=1)
        toolbar = ttk.Frame(workspace, style="Card.TFrame")
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(toolbar, text="Video preview", style="Section.TLabel").pack(side="left")
        self.extract_button = self.action(toolbar, "Extract score lines", self.extract_video, primary=True)
        self.extract_button.pack(side="right")
        self.add_line_button = self.action(toolbar, "Add line", self.add_manual_line, primary=True)
        detail = ttk.Frame(workspace, style="Card.TFrame")
        detail.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        self.overlap_check = ttk.Checkbutton(detail, text="Remove overlapping lines when pages scroll", variable=self.remove_overlap)
        self.overlap_check.pack(side="left")
        self.count_label = ttk.Label(detail, textvariable=self.manual_count, style="Badge.TLabel")
        self.canvas = tk.Canvas(workspace, background=PREVIEW, highlightthickness=0, height=280, width=400, cursor="crosshair")
        self.canvas.grid(row=2, column=0, sticky="nsew")
        self.canvas.bind("<Configure>", lambda e: self.draw_preview())
        self.canvas.bind("<ButtonPress-1>", self.crop_start)
        self.canvas.bind("<B1-Motion>", self.crop_drag)
        self.canvas.bind("<ButtonRelease-1>", self.crop_end)
        self.drag_origin = None
        seek_row = ttk.Frame(workspace, style="Card.TFrame")
        seek_row.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        self.seek = ttk.Scale(seek_row, from_=0, to=300, variable=self.time)
        self.seek.pack(side="left", fill="x", expand=True)
        self.seek.bind("<ButtonPress-1>", self.begin_seek)
        self.seek.bind("<ButtonRelease-1>", self.end_seek)
        self.seek.bind("<KeyRelease>", lambda event: self.seek_video())
        self.time_label = ttk.Label(seek_row, text="00:00 / 00:00", style="Hint.TLabel", width=19, anchor="e")
        self.time_label.pack(side="left", padx=(12, 0))
        self.time.trace_add("write", lambda *_: self.update_time_label())
        controls = ttk.Frame(workspace, style="Card.TFrame")
        controls.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        self.show_frame_button = self.action(controls, "Show frame", self.show_frame)
        self.show_frame_button.pack(side="left")
        self.add_view_button = self.action(controls, "Add this view", self.manual_capture)
        self.add_view_button.pack(side="left", padx=(8, 0))
        ttk.Label(controls, text="Silent preview", style="Hint.TLabel").pack(side="right")
        self.playback_row = ttk.Frame(workspace, style="Card.TFrame")
        self.playback_row.grid(row=5, column=0, sticky="ew", pady=(10, 0))
        self.play_button = self.action(self.playback_row, "Play", self.toggle_playback)
        self.play_button.pack(side="left", padx=(0, 12))
        ttk.Label(self.playback_row, text="Speed", style="Card.TLabel").pack(side="left")
        speed_control = ttk.Combobox(self.playback_row, textvariable=self.speed,
                                    values=["0.5x", "1x", "1.5x", "2x"], width=6, state="readonly")
        speed_control.pack(side="left", padx=8)
        speed_control.bind("<<ComboboxSelected>>", lambda event: self.change_speed())
        self.action(self.playback_row, "Review lines →", lambda: self.tabs.select(1)).pack(side="right")
        self.playback_row.grid_remove()

    def build_review(self, review):
        review.columnconfigure(1, weight=1)
        review.rowconfigure(0, weight=1)
        list_card = ttk.Frame(review, style="Card.TFrame", padding=14)
        list_card.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        ttk.Label(list_card, text="Score lines", style="Section.TLabel").pack(anchor="w")
        self.line_summary = ttk.Label(list_card, text="No lines yet", style="Hint.TLabel")
        self.line_summary.pack(anchor="w", pady=(4, 12))
        list_frame = ttk.Frame(list_card, style="Card.TFrame")
        list_frame.pack(fill="both", expand=True)
        self.line_list = tk.Listbox(list_frame, width=29, height=6, font=("Segoe UI", 10),
                                   selectmode="extended", exportselection=False, activestyle="none",
                                   background="white", foreground=INK, relief="flat", borderwidth=0,
                                   highlightthickness=1, highlightbackground="#e1e8eb", highlightcolor=ACCENT,
                                   selectbackground="#dcefee", selectforeground="#075e63")
        scroll = ttk.Scrollbar(list_frame, command=self.line_list.yview)
        self.line_list.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.line_list.pack(fill="both", expand=True)
        self.line_list.bind("<<ListboxSelect>>", lambda e: self.show_line())
        ttk.Label(list_card, text="Ctrl / Shift + click to select multiple.", style="Hint.TLabel").pack(anchor="w", pady=(10, 0))

        right = ttk.Frame(review, style="Card.TFrame", padding=14)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)
        ttk.Label(right, text="Line preview", style="Section.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 12))
        self.line_canvas = tk.Canvas(right, background="#f5f7f8", width=300, height=140,
                                     highlightthickness=1, highlightbackground="#e1e8eb")
        self.line_canvas.grid(row=1, column=0, sticky="nsew")
        self.line_canvas.bind("<Configure>", lambda e: self.show_line())
        self.review_note = ttk.Label(right, text="Included lines are exported in list order.", style="Hint.TLabel", wraplength=600)
        self.review_note.grid(row=2, column=0, sticky="ew", pady=10)
        self.review_note.bind("<Configure>", lambda e: self.review_note.configure(wraplength=max(100, e.width)))
        buttons = ttk.Frame(right, style="Card.TFrame")
        buttons.grid(row=3, column=0, sticky="ew")
        self.review_buttons = []
        for label, command in [("Include / exclude", self.toggle_lines), ("Move up", lambda: self.move_line(-1)),
                               ("Move down", lambda: self.move_line(1)), ("Save project", self.save_project)]:
            button = self.action(buttons, label, command)
            button.pack(side="left", padx=(0, 6))
            self.review_buttons.append(button)

        export_card = ttk.Frame(review, style="Card.TFrame", padding=(16, 12))
        export_card.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        export_card.columnconfigure(0, weight=1)
        title_row = ttk.Frame(export_card, style="Card.TFrame")
        title_row.grid(row=1, column=0, sticky="ew")
        ttk.Label(title_row, text="PDF title", style="Card.TLabel").pack(side="left", padx=(0, 12))
        ttk.Entry(title_row, textvariable=self.score_title).pack(side="left", fill="x", expand=True)
        self.export_button = self.action(title_row, "Export PDF…", self.export, primary=True)
        self.export_button.pack(side="right", padx=(16, 0))
        fields = ttk.Frame(export_card, style="Card.TFrame")
        fields.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        for label, variable in [("Paper", self.paper), ("Line gap (mm)", self.gap),
                                ("Left margin (mm)", self.left_margin), ("Right margin (mm)", self.right_margin)]:
            ttk.Label(fields, text=label, style="Card.TLabel").pack(side="left", padx=(0, 7))
            if variable is self.paper:
                control = ttk.Combobox(fields, textvariable=variable, values=list(PAPER_SIZES), width=7, state="readonly")
            else:
                control = ttk.Spinbox(fields, textvariable=variable, from_=0, to=40,
                                      increment=.5 if variable is self.gap else 1, width=5)
            control.pack(side="left", padx=(0, 18))

    def extraction_settings(self):
        dialog = tk.Toplevel(self)
        dialog.title("Extraction settings")
        dialog.transient(self)
        dialog.resizable(False, False)
        body = ttk.Frame(dialog, style="Card.TFrame", padding=24)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Fine-tune extraction", style="Section.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        ttk.Label(body, text="Defaults work well for most videos.", style="Hint.TLabel").grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 16))
        for i, (label, variable) in enumerate([
            ("Sample every (s)", self.interval), ("Change threshold", self.threshold),
            ("Start (s)", self.start_time), ("End (s; blank = all)", self.end_time),
        ], start=2):
            ttk.Label(body, text=label, style="Card.TLabel").grid(row=i, column=0, sticky="w", padx=(0, 24), pady=6)
            ttk.Entry(body, textvariable=variable, width=12).grid(row=i, column=1, pady=6)
        ttk.Label(body, text="Smaller sample intervals catch shorter views.\nLower thresholds detect smaller notation changes.",
                  style="Hint.TLabel").grid(row=6, column=0, columnspan=2, sticky="w", pady=(12, 16))
        ttk.Button(body, text="Done", style="Primary.TButton", command=dialog.destroy).grid(row=7, column=1, sticky="e")
        dialog.bind("<Escape>", lambda event: dialog.destroy())
        dialog.update_idletasks()
        dialog.geometry(f"+{self.winfo_rootx()+(self.winfo_width()-dialog.winfo_width())//2}+{self.winfo_rooty()+(self.winfo_height()-dialog.winfo_height())//2}")
        dialog.grab_set()
        dialog.focus_set()

    def update_time_label(self):
        def clock(seconds):
            seconds = max(0, int(seconds))
            return f"{seconds // 60:02d}:{seconds % 60:02d}"
        # Keep tenths visible for precise manual captures, without rounding to 60.0.
        tenths = max(0, int(self.time.get() * 10))
        current = f"{tenths // 600:02d}:{tenths % 600 / 10:04.1f}"
        self.time_label.configure(text=f"{current} / {clock(self.video_duration)}")

    def empty_canvas(self, canvas, title, subtitle, dark=False):
        canvas.delete("all")
        w, h = canvas.winfo_width(), canvas.winfo_height()
        x, y = w / 2, h / 2
        color = "#74919d" if dark else "#a7bdc5"
        # A small staff motif keeps the empty workspace connected to notation.
        for i in range(5):
            canvas.create_line(x-34, y-68+i*6, x+34, y-68+i*6, fill=color)
        canvas.create_oval(x-5, y-54, x+5, y-47, fill=color, outline=color)
        canvas.create_line(x+5, y-50, x+5, y-76, fill=color, width=2)
        canvas.create_text(x, y-12, text=title, fill="#edf4f5" if dark else INK,
                           font=("Segoe UI", 16, "bold"), width=max(100, w-40))
        canvas.create_text(x, y+30, text=subtitle, fill="#9cb4be" if dark else MUTED,
                           font=("Segoe UI", 10), width=max(100, w-60), justify="center")

    def sync_controls(self):
        ready = not self.busy
        video = self.video is not None
        selected = self.line_list.curselection()
        lines = self.project.lines if self.project else []
        states = [(self.load_button, bool(self.source.get().strip())),
                  (self.detect_button, video), (self.extract_button, video),
                  (self.show_frame_button, video), (self.seek, video),
                  (self.play_button, self.player is not None),
                  (self.add_line_button, video and not self.awaiting_frame and not self.seek_dragging),
                  (self.add_view_button, video and self.project is not None),
                  (self.export_button, any(line.included for line in lines)),
                  (self.review_buttons[0], bool(selected)),
                  (self.review_buttons[1], len(selected) == 1 and selected[0] > 0),
                  (self.review_buttons[2], len(selected) == 1 and selected[0] < len(lines)-1),
                  (self.review_buttons[3], self.project is not None)]
        for widget, enabled in states:
            disabled = not (ready and enabled)
            if widget.instate(["disabled"]) != disabled:
                widget.state(["disabled" if disabled else "!disabled"])
        self.cancel_button.state(["!disabled" if self.busy else "disabled"])
        self.activity_label.configure(text="WORKING" if self.busy else "READY")
