from __future__ import annotations

import os
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import cv2
from PIL import Image, ImageTk

from .extract import Extraction, ScoreLine, extract
from .manual import append_line, new_manual_project
from .pdf import export_pdf
from .playback import VideoPlayer
from .ui import WorkspaceUI
from .video import Cancelled, download, metadata, preview
from .vision import Region, auto_region, clean_score, split_systems


ROOT = Path(__file__).resolve().parent.parent


class App(WorkspaceUI, tk.Tk):
    def __init__(self):
        if os.name == "nt":
            import ctypes
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except (AttributeError, OSError):
                pass
        super().__init__()
        self.title("Video Sheet to PDF")
        self.geometry("1240x860")
        self.minsize(1080, 760)
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.busy = False
        self.video = None
        self.project = None
        self.automatic_project = None
        self.manual_project = None
        self.player = None
        self.video_duration = 0
        self.frame_time = 0
        self.seek_dragging = False
        self.resume_after_seek = False
        self.awaiting_frame = False
        self.playback_ended = False
        self.frame = None
        self.region = Region()
        self.preview_photo = None
        self.line_photo = None
        self.source = tk.StringVar()
        self.score_title = tk.StringVar(value="Sheet music")
        self.mode = tk.StringVar(value="auto")
        self.capture_mode = tk.StringVar(value="Automatic")
        self.last_capture_mode = "Automatic"
        self.speed = tk.StringVar(value="1x")
        self.manual_count = tk.StringVar(value="0 lines added")
        self.time = tk.DoubleVar(value=0)
        self.interval = tk.StringVar(value="0.5")
        self.threshold = tk.StringVar(value="0.035")
        self.start_time = tk.StringVar(value="0")
        self.end_time = tk.StringVar(value="")
        self.paper = tk.StringVar(value="A4")
        self.gap = tk.StringVar(value="0")
        self.left_margin = tk.StringVar(value="3")
        self.right_margin = tk.StringVar(value="3")
        self.remove_overlap = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value="Paste a YouTube link or choose a video, then click Load video.")
        self.build_ui()
        self.after(100, self.poll)
        self.protocol("WM_DELETE_WINDOW", self.close)

    def action(self, parent, label, callback, primary=False):
        def guarded():
            if self.busy:
                self.status.set("Please wait for the current operation, or click Cancel.")
                return
            try:
                callback()
            except Exception as exc:
                messagebox.showerror("Video Sheet to PDF", str(exc))
        return ttk.Button(parent, text=label, command=guarded,
                          style="Primary.TButton" if primary else "TButton")

    def worker(self, task, callback):
        self.pause_playback()
        self.busy = True
        self.cancel.clear()
        self.status.set("Working…")
        self.sync_controls()
        self.progress["value"] = 0
        def run():
            try:
                result = task()
                self.events.put(("done", callback, result))
            except Exception as exc:
                self.events.put(("error", str(exc), isinstance(exc, Cancelled) or self.cancel.is_set()))
        threading.Thread(target=run, daemon=True).start()

    def report(self, text, fraction):
        self.events.put(("progress", text, fraction))

    def poll(self):
        try:
            while True:
                event, a, b = self.events.get_nowait()
                if event == "progress":
                    self.status.set(a)
                    if b is not None:
                        self.progress["value"] = b
                elif event == "done":
                    self.busy = False
                    self.progress["value"] = 1
                    try:
                        a(b)
                    except Exception as exc:
                        messagebox.showerror("Video Sheet to PDF", str(exc))
                else:
                    self.busy = False
                    self.progress["value"] = 0
                    self.status.set("Cancelled." if b else a)
                    if not b:
                        messagebox.showerror("Could not complete operation", a)
        except queue.Empty:
            pass
        self.consume_playback()
        self.sync_controls()
        self.after(33, self.poll)

    def change_capture_mode(self):
        if self.busy:
            self.capture_mode.set(self.last_capture_mode)
            self.status.set("Wait for the current operation, or click Cancel, before switching modes.")
            return
        self.pause_playback()
        self.last_capture_mode = self.capture_mode.get()
        manual = self.capture_mode.get() == "Manual"
        for widget in (self.layout_row, self.auto_options):
            widget.grid_remove() if manual else widget.grid()
        for widget in (self.overlap_check, self.extract_button, self.add_view_button):
            widget.pack_forget()
        if manual:
            self.mode_hint.configure(text="Drag around one score line. Play the video and click Add line to capture it.")
            self.count_label.pack(side="left")
            self.add_line_button.pack(side="right")
            self.playback_row.grid()
            self.project = self.manual_project
            if self.player and self.manual_project is None:
                self.time.set(0)
                self.seek_video()
            self.status.set("Manual mode: drag a rectangle around one line, press Play, and click Add line whenever you want to capture it.")
        else:
            self.mode_hint.configure(text="Drag on the preview to set the crop, then extract your score.")
            self.count_label.pack_forget()
            self.add_line_button.pack_forget()
            self.playback_row.grid_remove()
            self.overlap_check.pack(side="left")
            self.extract_button.pack(side="right")
            self.add_view_button.pack(side="left", padx=(8, 0))
            self.project = self.automatic_project
            self.status.set("Automatic mode: check the score crop, then click Extract score lines.")
        self.refresh_lines()

    def tab_changed(self, event=None):
        if self.tabs.select() and self.tabs.index("current") == 1:
            self.pause_playback()

    def pause_playback(self):
        if self.player:
            self.player.pause()
        self.play_button.configure(text="Play")

    def close_player(self):
        if self.player:
            self.player.close()
            self.player = None
        self.play_button.configure(text="Play")
        self.awaiting_frame = self.seek_dragging = False

    def toggle_playback(self):
        if not self.player:
            raise ValueError("Load a video first.")
        if self.player.playing:
            self.pause_playback()
        else:
            if self.awaiting_frame:
                return
            self.player.play(0 if self.playback_ended else self.frame_time)
            self.playback_ended = False
            self.play_button.configure(text="Pause")

    def change_speed(self):
        if self.player:
            self.player.set_speed(float(self.speed.get().rstrip("x")))

    def consume_playback(self):
        if not self.player or self.seek_dragging:
            return
        packet = self.player.take_frame()
        if packet is None:
            return
        if packet.error:
            self.close_player()
            self.status.set(packet.error)
            messagebox.showerror("Video playback", packet.error)
            return
        self.frame, self.frame_time = packet.image, packet.seconds
        self.time.set(packet.seconds)
        self.awaiting_frame = False
        self.playback_ended = packet.ended
        self.play_button.configure(text="Pause" if self.player.playing else "Play")
        self.draw_preview()

    def begin_seek(self, event=None):
        self.seek_dragging = True
        self.resume_after_seek = bool(self.player and self.player.playing)
        self.pause_playback()

    def end_seek(self, event=None):
        self.seek_dragging = False
        self.seek_video(resume=self.resume_after_seek)

    def seek_video(self, resume=False):
        if not self.player or self.busy:
            return
        self.awaiting_frame = True
        self.playback_ended = False
        self.player.seek(self.time.get())
        if resume:
            self.player.play()
        self.play_button.configure(text="Pause" if self.player.playing else "Play")

    def choose_file(self):
        path = filedialog.askopenfilename(filetypes=[("Videos", "*.mp4 *.mkv *.webm *.mov *.avi"), ("All files", "*.*")])
        if path:
            self.source.set(path)

    def load_video(self):
        source = self.source.get().strip()
        if not source:
            raise ValueError("Enter a YouTube link or choose a local video first.")
        manual = self.capture_mode.get() == "Manual"
        def task():
            path, title = download(source, ROOT/"output"/"cache", self.report, self.cancel)
            _, _, duration = metadata(path)
            seconds = 0 if manual else min(20, duration*.1)
            return path, title, duration, seconds, preview(path, seconds)
        def loaded(result):
            self.close_player()
            self.video, title, duration, seconds, self.frame = result
            self.video_duration = duration
            self.loaded_source = source
            self.score_title.set(title)
            self.seek.configure(to=max(0, duration-.1))
            self.time.set(seconds)
            self.frame_time = seconds
            self.project = None
            self.manual_project = self.automatic_project = None
            self.manual_count.set("0 lines added")
            self.refresh_lines()
            self.region = auto_region(self.frame, self.mode.get())
            self.draw_preview()
            self.player = VideoPlayer(self.video, duration, seconds)
            self.change_speed()
            self.playback_ended = False
            if self.capture_mode.get() == "Manual":
                self.status.set("Video loaded. Drag a rectangle around one line, press Play, then click Add line for each capture.")
            else:
                self.status.set("Video loaded. Check the green crop; drag to adjust it, then extract.")
        self.worker(task, loaded)

    def show_frame(self):
        if not self.video:
            raise ValueError("Load a video first.")
        self.pause_playback()
        self.seek_video()

    def detect_region(self):
        if self.frame is not None:
            self.region = auto_region(self.frame, self.mode.get())
            self.draw_preview()

    def draw_preview(self):
        if self.frame is None:
            self.empty_canvas(self.canvas, "Start with a video",
                              "Paste a YouTube link or choose a local file above.\nYour score preview will appear here.", dark=True)
            return
        image = Image.fromarray(cv2.cvtColor(self.frame, cv2.COLOR_BGR2RGB))
        cw, ch = max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height())
        image.thumbnail((cw, ch), Image.Resampling.LANCZOS)
        self.preview_photo = ImageTk.PhotoImage(image)
        self.offset = ((cw-image.width)/2, (ch-image.height)/2)
        self.display_size = image.size
        self.canvas.delete("all")
        x, y = self.offset
        self.canvas.create_image(x, y, anchor="nw", image=self.preview_photo)
        r = self.region
        self.canvas.create_rectangle(x+r.left*image.width, y+r.top*image.height,
                                     x+r.right*image.width, y+r.bottom*image.height,
                                     outline="#36ef9b", width=3, tags="crop")

    def normalized_point(self, event):
        x, y = self.offset
        w, h = self.display_size
        return min(1, max(0, (event.x-x)/w)), min(1, max(0, (event.y-y)/h))

    def crop_start(self, event):
        if self.frame is not None and not self.busy:
            self.pause_playback()
            self.drag_origin = self.normalized_point(event)

    def crop_drag(self, event):
        if self.drag_origin is None:
            return
        x0, y0 = self.drag_origin
        x1, y1 = self.normalized_point(event)
        if abs(x0-x1) > .01 and abs(y0-y1) > .01:
            self.region = Region(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
            self.draw_preview()

    def crop_end(self, event):
        self.crop_drag(event)
        self.drag_origin = None

    def extract_video(self):
        if not self.video:
            raise ValueError("Load a video first.")
        interval, threshold = float(self.interval.get()), float(self.threshold.get())
        start = float(self.start_time.get())
        end = float(self.end_time.get()) if self.end_time.get().strip() else None
        title, region, video = self.score_title.get(), self.region, self.video
        remove_overlap = self.remove_overlap.get()
        def done(project):
            self.project = project
            self.automatic_project = project
            self.refresh_lines()
            self.tabs.select(1)
            self.status.set(f"Extracted {len(project.lines)} lines. Review them, then export a PDF.")
        self.worker(lambda: extract(video, ROOT/"output", title, self.loaded_source, region,
                                   interval=interval, threshold=threshold, start=start, end=end,
                                   progress=self.report, cancel=self.cancel, remove_overlap=remove_overlap), done)

    def refresh_lines(self, selection=0):
        self.line_list.delete(0, "end")
        self.review_note.configure(text="Select a line to inspect it. Included lines are exported in list order.")
        if self.project:
            for i, line in enumerate(self.project.lines):
                origin = f"view {line.view}" if line.view else "manual"
                self.line_list.insert("end", f"{'✓' if line.included else '—'}  {i+1:03d}   ·   {line.time//60:.0f}:{line.time%60:04.1f}   ·   {origin}")
                self.line_list.itemconfigure(i, background="#f2f6f7" if i % 2 == 0 else "white",
                                             foreground="#182f3a" if line.included else "#87979f")
            if self.project.warnings:
                self.review_note.configure(text="\n".join(self.project.warnings))
            if self.project.lines:
                self.line_list.selection_set(min(selection, len(self.project.lines)-1))
        lines = self.project.lines if self.project else []
        included = sum(line.included for line in lines)
        self.line_summary.configure(text=f"{len(lines)} lines · {included} included" if lines else "No lines yet")
        self.show_line()

    def show_line(self):
        self.line_canvas.delete("all")
        selected = self.line_list.curselection()
        if not selected or not self.project:
            self.empty_canvas(self.line_canvas, "Your score starts here",
                              "Capture lines in Score area or open a saved project.\nSelect a line to inspect it before exporting.")
            return
        line = self.project.lines[selected[0]]
        with Image.open(self.project.directory/line.path) as original:
            image = original.convert("RGB")
        image.thumbnail((max(1, self.line_canvas.winfo_width()-20), max(1, self.line_canvas.winfo_height()-20)), Image.Resampling.LANCZOS)
        self.line_photo = ImageTk.PhotoImage(image)
        self.line_canvas.create_image(self.line_canvas.winfo_width()/2,
                                      self.line_canvas.winfo_height()/2, image=self.line_photo)

    def toggle_lines(self):
        selected = self.line_list.curselection()
        if self.project and selected:
            for index in selected:
                line = self.project.lines[index]
                line.included = not line.included
            self.refresh_lines(selected[0])
            self.project.save()

    def move_line(self, direction):
        selected = self.line_list.curselection()
        if self.project and len(selected) == 1:
            i = selected[0]
            j = i+direction
            if 0 <= j < len(self.project.lines):
                self.project.lines[i], self.project.lines[j] = self.project.lines[j], self.project.lines[i]
                self.refresh_lines(j)
                self.project.save()

    def manual_capture(self):
        if not self.project or self.frame is None:
            raise ValueError("Extract the video first, then use Add this view to insert any missing lines.")
        strips = split_systems(clean_score(self.region.crop(self.frame)))
        if not strips:
            raise ValueError("No staff lines found in the current crop.")
        import uuid
        position = self.line_list.curselection()
        at = position[0]+1 if position else len(self.project.lines)
        for i, strip in enumerate(strips):
            name = "manual_"+uuid.uuid4().hex[:10]+".png"
            Image.fromarray(strip).save(self.project.directory/name)
            self.project.lines.insert(at+i, ScoreLine(name, self.frame_time, 0))
        self.project.save()
        self.refresh_lines(at)
        self.tabs.select(1)
        self.status.set(f"Inserted {len(strips)} lines after the selected line.")

    def add_manual_line(self):
        if not self.video or self.frame is None:
            raise ValueError("Load a video first, then drag a rectangle around one score line.")
        if self.awaiting_frame or self.seek_dragging:
            self.status.set("Wait for the selected frame to appear before adding a line.")
            return
        if self.manual_project is None:
            self.manual_project = new_manual_project(ROOT/"output", self.score_title.get(),
                                                     self.loaded_source, self.region)
        project = self.manual_project
        project.title = self.score_title.get()
        append_line(project, self.frame, self.region, self.frame_time)
        self.project = project
        count = len(project.lines)
        self.manual_count.set(f"{count} {'line' if count == 1 else 'lines'} added")
        self.refresh_lines(count-1)
        self.status.set(f"Added line {count} at {self.frame_time:.1f}s. Keep adding lines, or open Review & export when ready.")

    def save_project(self):
        if self.project:
            self.project.title = self.score_title.get()
            self.project.save()
            self.status.set(f"Saved {self.project.directory / 'project.json'}")

    def open_project(self):
        filename = filedialog.askopenfilename(initialdir=ROOT/"output", filetypes=[("Score project", "project.json"), ("JSON", "*.json")])
        if filename:
            self.close_player()
            self.project = Extraction.load(filename)
            self.automatic_project = self.project
            self.manual_project = None
            self.capture_mode.set("Automatic")
            self.change_capture_mode()
            self.score_title.set(self.project.title)
            self.video = None
            self.frame = None
            self.video_duration = 0
            self.time.set(0)
            self.draw_preview()
            self.refresh_lines()
            self.tabs.select(1)
            self.status.set("Saved project opened. Review and export when ready.")

    def export(self):
        if not self.project:
            raise ValueError("Add lines in Manual mode, extract a video, or open a saved project first.")
        self.pause_playback()
        import re
        name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", self.score_title.get())[:100].strip(". ") or "sheet-music"
        filename = filedialog.asksaveasfilename(initialdir=ROOT/"output", initialfile=name+".pdf", defaultextension=".pdf", filetypes=[("PDF", "*.pdf")])
        if filename:
            self.project.title = self.score_title.get()
            self.project.save()
            project, paper, gap = self.project, self.paper.get(), float(self.gap.get())
            left_margin, right_margin = float(self.left_margin.get()), float(self.right_margin.get())
            def done(pages):
                self.status.set(f"Saved {pages} pages: {filename}")
                if hasattr(os, "startfile"):
                    os.startfile(filename)
            self.worker(lambda: export_pdf(project, filename, paper=paper, gap_mm=gap,
                                          left_margin_mm=left_margin, right_margin_mm=right_margin), done)

    def close(self):
        self.cancel.set()
        self.close_player()
        self.destroy()


def main():
    App().mainloop()
