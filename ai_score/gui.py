"""Two isolated desktop editions; credentials never leave process memory or provider request."""
import hashlib
import json
import os
import queue
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, messagebox

from .providers import Client, PROVIDERS, RATES, login_status
from .pipeline import extract, reformat


class App:
    def __init__(self, root, edition):
        self.root, self.edition = root, edition
        self.messages = queue.Queue()
        self.cancel = threading.Event()
        self.busy = False
        self.pdf = None
        self.project = None
        self.client = None
        self.started = None
        root.title('AI Score — '+('Personal · Codex' if edition == 'personal' else 'API edition'))
        root.geometry(f"{min(1060, root.winfo_screenwidth()-80)}x{min(940, root.winfo_screenheight()-100)}")
        root.minsize(820, 690)
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('.', font=('Segoe UI', 10))
        style.configure('Title.TLabel', font=('Segoe UI Semibold', 22))
        style.configure('Accent.TButton', font=('Segoe UI Semibold', 11), padding=8)
        self.source = tk.StringVar()
        self.instrument = tk.StringVar(value='bass')
        self.bars = tk.IntVar(value=4)
        self.provider = tk.StringVar(value='Codex' if edition == 'personal' else 'OpenAI')
        self.model = tk.StringVar(value=PROVIDERS[self.provider.get()]['model'])
        self.key = tk.StringVar()
        self.interval = tk.DoubleVar(value=2.)
        self.frames = tk.IntVar(value=6)
        self.budget = tk.DoubleVar(value=2.)
        self.requests = tk.IntVar(value=100)
        self.full_frames = tk.BooleanVar(value=True)
        self.draft = tk.BooleanVar(value=True)
        home = Path(os.environ.get('LOCALAPPDATA', str(Path.home())))/'AI Score'/edition
        self.output = tk.StringVar(value=str(home/'jobs'))
        self.status = tk.StringVar(value='Ready. Choose a video, instrument, and page layout.')
        self.usage = tk.StringVar(value='No AI requests made.')
        viewport = tk.Canvas(root, highlightthickness=0)
        scrollbar = ttk.Scrollbar(root, orient='vertical', command=viewport.yview)
        scrollbar.pack(side='right', fill='y')
        viewport.pack(side='left', fill='both', expand=True)
        viewport.configure(yscrollcommand=scrollbar.set)
        outer = ttk.Frame(viewport, padding=20)
        window = viewport.create_window((0, 0), window=outer, anchor='nw')
        outer.bind('<Configure>', lambda e: viewport.configure(scrollregion=viewport.bbox('all')))
        viewport.bind('<Configure>', lambda e: viewport.itemconfigure(window, width=e.width))
        root.bind('<MouseWheel>', lambda e: viewport.yview_scroll(int(-e.delta/120), 'units') if not isinstance(e.widget, (tk.Text, ttk.Spinbox, ttk.Combobox)) else None)
        outer.columnconfigure(1, weight=1)
        ttk.Label(outer, text='AI Score', style='Title.TLabel').grid(row=0, column=0, sticky='w')
        subtitle = ('Personal edition · uses your installed Codex CLI and ChatGPT allowance'
                    if edition == 'personal' else 'API edition · your key, your provider · billed separately')
        ttk.Label(outer, text=subtitle).grid(row=0, column=1, columnspan=2, sticky='w', padx=12)
        ttk.Label(outer, text='YouTube link / video').grid(row=1, column=0, sticky='w', pady=(18, 8))
        ttk.Entry(outer, textvariable=self.source).grid(row=1, column=1, sticky='ew', padx=12, pady=(18, 8))
        ttk.Button(outer, text='Choose video…', command=self.choose_video).grid(row=1, column=2, pady=(18, 8))
        options = ttk.Frame(outer)
        options.grid(row=2, column=0, columnspan=3, sticky='ew', pady=8)
        ttk.Label(options, text='Instrument').pack(side='left')
        ttk.Combobox(options, textvariable=self.instrument, values=['bass', 'guitar', 'drums', 'piano'], state='readonly', width=12).pack(side='left', padx=(8, 24))
        ttk.Label(options, text='Bars per line').pack(side='left')
        ttk.Spinbox(options, from_=1, to=8, textvariable=self.bars, width=5).pack(side='left', padx=8)
        provider_row = ttk.LabelFrame(outer, text='AI connection', padding=12)
        provider_row.grid(row=3, column=0, columnspan=3, sticky='ew', pady=8)
        provider_row.columnconfigure(3, weight=1)
        ttk.Label(provider_row, text='Provider').grid(row=0, column=0, sticky='w')
        provider_widget = ttk.Combobox(provider_row, textvariable=self.provider,
                                      values=['Codex'] if edition == 'personal' else ['OpenAI', 'DeepSeek', 'Anthropic'], state='readonly', width=13)
        provider_widget.grid(row=0, column=1, padx=8)
        provider_widget.bind('<<ComboboxSelected>>', self.change_provider)
        ttk.Label(provider_row, text='Model').grid(row=0, column=2)
        self.model_widget = ttk.Combobox(provider_row, textvariable=self.model, state='readonly')
        self.model_widget.grid(row=0, column=3, sticky='ew', padx=8)
        self.change_provider()
        if edition == 'personal':
            ttk.Button(provider_row, text='Check login', command=self.check_login).grid(row=0, column=4)
            ttk.Label(provider_row, text='Install Codex CLI separately and sign in with “codex login”. No API key is used here.').grid(row=1, column=0, columnspan=5, sticky='w', pady=(8, 0))
        else:
            ttk.Label(provider_row, text='API key').grid(row=1, column=0, pady=(10, 0))
            ttk.Entry(provider_row, textvariable=self.key, show='•').grid(row=1, column=1, columnspan=3, sticky='ew', padx=8, pady=(10, 0))
            ttk.Label(provider_row, text='Key stays in memory. Frames and instructions are sent to the chosen provider.').grid(row=2, column=0, columnspan=5, sticky='w', pady=(8, 0))
        ttk.Label(outer, text='Additional instructions · optional').grid(row=4, column=0, columnspan=3, sticky='w', pady=(10, 5))
        self.instructions = tk.Text(outer, height=5, wrap='word', font=('Segoe UI', 10), relief='solid', bd=1)
        self.instructions.grid(row=5, column=0, columnspan=3, sticky='ew')
        ttk.Label(outer, text='Example: Title “Ado | Bass TAB” on the first page only. No subtitle or footer. Combine rests 116–117 into one two-bar rest.', wraplength=820).grid(row=6, column=0, columnspan=3, sticky='w', pady=5)
        advanced = ttk.LabelFrame(outer, text='Quality and limits', padding=10)
        advanced.grid(row=7, column=0, columnspan=3, sticky='ew', pady=8)
        for col, (text, variable, lower, upper) in enumerate([
            ('Sample seconds', self.interval, .5, 5), ('Frames / request', self.frames, 3, 10),
            ('Max requests / run', self.requests, 1, 500), ('Spend guard USD', self.budget, .1, 100)]):
            ttk.Label(advanced, text=text).grid(row=0, column=col*2, padx=(0, 5))
            spin = ttk.Spinbox(advanced, from_=lower, to=upper, increment=.5 if variable is self.interval else 1,
                              textvariable=variable, width=6)
            spin.grid(row=0, column=col*2+1, padx=(0, 12))
            if edition == 'personal' and variable is self.budget:
                spin.configure(state='disabled')
        ttk.Checkbutton(advanced, text='Full frames: follow moving score areas (recommended)', variable=self.full_frames).grid(row=1, column=0, columnspan=4, sticky='w', pady=(8, 0))
        ttk.Checkbutton(advanced, text='Export draft if review issues remain', variable=self.draft).grid(row=1, column=4, columnspan=4, sticky='w', pady=(8, 0))
        ttk.Label(advanced, text='Spend guard is an estimate, not a billing cap. Dense music: use 1-second samples. Completed AI responses are cached.', wraplength=800).grid(row=2, column=0, columnspan=8, sticky='w', pady=(8, 0))
        ttk.Label(outer, text='Output folder').grid(row=8, column=0, sticky='w')
        ttk.Entry(outer, textvariable=self.output).grid(row=8, column=1, sticky='ew', padx=12)
        ttk.Button(outer, text='Choose folder…', command=self.choose_output).grid(row=8, column=2)
        actions = ttk.Frame(outer)
        actions.grid(row=9, column=0, columnspan=3, sticky='ew', pady=14)
        self.start_button = ttk.Button(actions, text='Transcribe / resume', style='Accent.TButton', command=self.start)
        self.start_button.pack(side='left')
        self.format_button = ttk.Button(actions, text='Reformat saved score…', command=self.start_format)
        self.format_button.pack(side='left', padx=10)
        self.stop_button = ttk.Button(actions, text='Cancel', command=self.cancel.set, state='disabled')
        self.stop_button.pack(side='left')
        self.pdf_button = ttk.Button(actions, text='Open PDF', command=self.open_pdf, state='disabled')
        self.pdf_button.pack(side='right')
        ttk.Label(outer, textvariable=self.status, wraplength=890).grid(row=10, column=0, columnspan=3, sticky='w')
        ttk.Label(outer, textvariable=self.usage, wraplength=890).grid(row=11, column=0, columnspan=3, sticky='w', pady=(5, 8))
        self.log_widget = tk.Text(outer, height=9, state='disabled', wrap='word', font=('Consolas', 9))
        self.log_widget.grid(row=12, column=0, columnspan=3, sticky='nsew')
        outer.rowconfigure(12, weight=1)
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.after(150, self.poll)

    def change_provider(self, *_):
        provider = self.provider.get()
        values = ['gpt-6-astra', 'gpt-6-sol', 'gpt-6-luna'] if provider in ('Codex', 'OpenAI') else [PROVIDERS[provider]['model']]
        self.model_widget.configure(values=values)
        self.model.set(PROVIDERS[provider]['model'])
        self.key.set('')

    def choose_video(self):
        path = filedialog.askopenfilename(filetypes=[('Video', '*.mp4 *.mkv *.webm *.mov *.avi'), ('All files', '*.*')])
        if path:
            self.source.set(path)

    def choose_output(self):
        path = filedialog.askdirectory()
        if path:
            self.output.set(path)

    def check_login(self):
        def worker():
            try:
                self.messages.put(('log', login_status()))
            except Exception as exc:
                self.messages.put(('log', str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def settings(self):
        values = dict(source=self.source.get().strip(), instrument=self.instrument.get(), bars_per_line=self.bars.get(),
                      instructions=self.instructions.get('1.0', 'end').strip(), interval=self.interval.get(),
                      frames_per_request=self.frames.get(), full_frames=self.full_frames.get(), draft=self.draft.get())
        if not 1 <= values['bars_per_line'] <= 8:
            raise ValueError('Choose 1–8 bars per line.')
        if not self.output.get().strip():
            raise ValueError('Choose an output folder.')
        if not 1 <= self.requests.get() <= 500 or self.budget.get() <= 0:
            raise ValueError('Request limit and spend guard must be positive.')
        identity = hashlib.sha256(json.dumps([values['source'], values['instrument'], values['interval'],
                                             values['frames_per_request'], values['full_frames']], sort_keys=True).encode()).hexdigest()[:12]
        folder = Path(self.output.get())/identity
        self.cancel = threading.Event()
        self.client = Client(self.provider.get(), self.model.get(), self.key.get(), folder/'responses',
                             self.cancel, lambda msg: self.messages.put(('log', msg)),
                             max_requests=self.requests.get(), budget=self.budget.get())
        return values, folder

    def start(self):
        if self.busy:
            return
        try:
            values, folder = self.settings()
            if not values['source']:
                raise ValueError('Paste a YouTube link or choose a video.')
        except Exception as exc:
            messagebox.showerror('Check settings', str(exc))
            return
        self.run(lambda: extract(self.client, job_folder=folder, **values))

    def start_format(self):
        if self.busy:
            return
        path = filedialog.askopenfilename(title='Open AI score project', filetypes=[('AI Score', '*.aiscore.json'), ('JSON', '*.json')])
        if not path:
            return
        try:
            values, _ = self.settings()
            self.client.folder = Path(path).parent/'responses'
            self.client.folder.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            messagebox.showerror('Check settings', str(exc))
            return
        self.run(lambda: reformat(self.client, path, values['instructions'], values['bars_per_line']))

    def run(self, action):
        self.busy = True
        self.started = time.monotonic()
        self.pdf = None
        self.pdf_button.configure(state='disabled')
        self.start_button.configure(state='disabled')
        self.format_button.configure(state='disabled')
        self.stop_button.configure(state='normal')
        def worker():
            try:
                self.messages.put(('done', action()))
            except Exception as exc:
                self.messages.put(('error', str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def append_log(self, message):
        self.log_widget.configure(state='normal')
        self.log_widget.insert('end', message+'\n')
        self.log_widget.see('end')
        self.log_widget.configure(state='disabled')

    def poll(self):
        try:
            while True:
                kind, value = self.messages.get_nowait()
                if kind == 'log':
                    self.status.set(value)
                    self.append_log(value)
                elif kind in ('done', 'error'):
                    self.busy = False
                    self.start_button.configure(state='normal')
                    self.format_button.configure(state='normal')
                    self.stop_button.configure(state='disabled')
                    if kind == 'error':
                        self.status.set('Stopped: '+value)
                        self.append_log('Stopped: '+value)
                    else:
                        self.project, self.pdf, score = value
                        issues = list(dict.fromkeys(score.get('review', [])+score['layout'].get('unsupported_requests', [])))
                        self.status.set(f"{'Draft ready' if issues else 'PDF ready'} · {len(score['bars'])} musical bars · {len(issues)} review notes" if self.pdf else 'Project saved. Review issues before exporting a PDF.')
                        self.append_log(f'Project: {self.project}')
                        self.append_log(f'PDF: {self.pdf}' if self.pdf else 'No PDF exported.')
                        for issue in issues:
                            self.append_log('Review: '+issue)
                        self.pdf_button.configure(state='normal' if self.pdf else 'disabled')
        except queue.Empty:
            pass
        if self.client:
            u = self.client.usage
            elapsed = int(time.monotonic()-self.started) if self.started and self.busy else getattr(self, 'elapsed', 0)
            self.elapsed = elapsed
            cost = 'Subscription allowance; no API billing' if u['subscription'] else f"Estimated ${u['estimated_usd']:.4f} · current run only"
            self.usage.set(f"{elapsed//60}:{elapsed%60:02d} · {u['requests']} requests · {u['cache_hits']} reused · input {u['input_tokens']:,} (cached {u['cached_input_tokens']:,}) · output {u['output_tokens']:,}\n{cost}")
        self.root.after(200, self.poll)

    def open_pdf(self):
        if self.pdf and Path(self.pdf).exists():
            os.startfile(str(self.pdf))

    def close(self):
        if self.busy:
            self.cancel.set()
            self.status.set('Cancelling. Close again after the current request has stopped.')
            return
        self.key.set('')
        self.root.destroy()


def main(edition):
    bundle = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent))
    node = bundle/'runtime'/'node.exe'
    if node.exists():
        os.environ['DRUMSCORE_NODE'] = str(node)
    if '--self-test' in sys.argv:
        from .selftest import run
        run(sys.argv[sys.argv.index('--self-test')+1])
        return
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    root = tk.Tk()
    App(root, edition)
    if '--smoke-test' in sys.argv:
        root.after(1500, root.destroy)
    root.mainloop()
