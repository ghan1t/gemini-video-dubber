from __future__ import annotations

import asyncio
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional, Union

from .jobs import DubJob, JobProgress, JobRunner
from .languages import SUPPORTED_LANGUAGES, code_for_display, display_for_code
from .settings import load_api_key


class GeminiVideoDubberApp:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Gemini Video Dubber")
        self.root.geometry("820x620")
        self.root.minsize(720, 540)

        self.events: queue.Queue[Union[JobProgress, tuple[str, str]]] = queue.Queue()
        self.runner: Optional[JobRunner] = None
        self.worker: Optional[threading.Thread] = None
        self.controls: list[tk.Widget] = []

        self.video_path = tk.StringVar()
        self.output_dir = tk.StringVar(value=str(Path.home() / "Desktop"))
        self.source_language = tk.StringVar(value=display_for_code("en"))
        self.target_language = tk.StringVar(value=display_for_code("es"))
        self.audio_start_offset = tk.StringVar(value="0.0")
        self.create_subtitles = tk.BooleanVar(value=True)
        self.keep_original_audio = tk.BooleanVar(value=True)
        self.api_key = tk.StringVar()
        self.status = tk.StringVar(value="Ready.")
        self.progress = tk.DoubleVar(value=0.0)
        self.start_button_text = tk.StringVar(value="Start")

        self._build_ui()
        self.root.after(100, self._drain_events)

    def run(self) -> None:
        self.root.mainloop()

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        frame = ttk.Frame(self.root, padding=16)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(9, weight=1)

        self._file_row(frame, 0, "Video file", self.video_path, self._choose_video)
        self._file_row(frame, 1, "Output folder", self.output_dir, self._choose_output_dir)

        displays = [language.display for language in SUPPORTED_LANGUAGES]
        ttk.Label(frame, text="Source language").grid(row=2, column=0, sticky="w", pady=6)
        source = ttk.Combobox(
            frame,
            textvariable=self.source_language,
            values=displays,
            state="readonly",
        )
        source.grid(row=2, column=1, sticky="ew", pady=6)
        self.controls.append(source)

        ttk.Label(frame, text="Target language").grid(row=3, column=0, sticky="w", pady=6)
        target = ttk.Combobox(
            frame,
            textvariable=self.target_language,
            values=displays,
            state="readonly",
        )
        target.grid(row=3, column=1, sticky="ew", pady=6)
        self.controls.append(target)

        ttk.Label(frame, text="Dub start offset (seconds)").grid(
            row=4,
            column=0,
            sticky="w",
            pady=6,
        )
        offset_entry = ttk.Entry(frame, textvariable=self.audio_start_offset, width=12)
        offset_entry.grid(row=4, column=1, sticky="w", pady=6)
        self.controls.append(offset_entry)

        subtitles = ttk.Checkbutton(
            frame,
            text="Create approximate subtitles",
            variable=self.create_subtitles,
        )
        subtitles.grid(row=5, column=1, sticky="w", pady=6)
        self.controls.append(subtitles)

        original_audio = ttk.Checkbutton(
            frame,
            text="Keep original audio track",
            variable=self.keep_original_audio,
            state="disabled",
        )
        original_audio.grid(row=6, column=1, sticky="w", pady=6)

        ttk.Label(frame, text="API key").grid(row=7, column=0, sticky="w", pady=6)
        api_entry = ttk.Entry(frame, textvariable=self.api_key, show="*", width=44)
        api_entry.grid(row=7, column=1, sticky="ew", pady=6)
        self.controls.append(api_entry)

        actions = ttk.Frame(frame)
        actions.grid(row=8, column=0, columnspan=3, sticky="ew", pady=(12, 8))
        actions.columnconfigure(1, weight=1)
        start = ttk.Button(
            actions,
            textvariable=self.start_button_text,
            command=self._start_or_cancel,
        )
        start.grid(row=0, column=0, sticky="w")
        ttk.Label(actions, textvariable=self.status).grid(row=0, column=1, sticky="w", padx=12)

        bar = ttk.Progressbar(frame, variable=self.progress, mode="determinate", maximum=100)
        bar.grid(row=9, column=0, columnspan=3, sticky="ew", pady=(0, 8))

        self.log = tk.Text(frame, height=16, wrap="word", state="disabled")
        self.log.grid(row=10, column=0, columnspan=3, sticky="nsew")
        scrollbar = ttk.Scrollbar(frame, command=self.log.yview)
        scrollbar.grid(row=10, column=3, sticky="ns")
        self.log.configure(yscrollcommand=scrollbar.set)

    def _file_row(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.StringVar,
        command: object,
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=6)
        entry = ttk.Entry(parent, textvariable=variable)
        entry.grid(row=row, column=1, sticky="ew", pady=6)
        button = ttk.Button(parent, text="Browse", command=command)
        button.grid(row=row, column=2, sticky="e", padx=(8, 0), pady=6)
        self.controls.extend([entry, button])

    def _choose_video(self) -> None:
        value = filedialog.askopenfilename(
            title="Select video",
            filetypes=[
                ("Video files", "*.mp4 *.mov *.mkv *.m4v *.avi *.webm"),
                ("All files", "*.*"),
            ],
        )
        if value:
            self.video_path.set(value)

    def _choose_output_dir(self) -> None:
        value = filedialog.askdirectory(title="Select output folder")
        if value:
            self.output_dir.set(value)

    def _start_or_cancel(self) -> None:
        if self.worker and self.worker.is_alive():
            if self.runner:
                self.runner.cancel()
            self._append_log("Cancellation requested.")
            return
        self._start_job()

    def _start_job(self) -> None:
        api_key = load_api_key(self.api_key.get())
        try:
            audio_start_offset = float(self.audio_start_offset.get().strip() or "0")
        except ValueError:
            messagebox.showerror(
                "Gemini Video Dubber",
                "Dub start offset must be a number of seconds, such as 0, -4.2, or 1.5.",
            )
            return
        job = DubJob(
            input_path=Path(self.video_path.get()).expanduser(),
            output_dir=Path(self.output_dir.get()).expanduser(),
            source_language_code=code_for_display(self.source_language.get()),
            target_language_code=code_for_display(self.target_language.get()),
            create_subtitles=self.create_subtitles.get(),
            api_key=api_key,
            audio_start_offset_seconds=audio_start_offset,
        )
        self.progress.set(0.0)
        self.status.set("Starting.")
        self.start_button_text.set("Cancel")
        self._set_controls_enabled(False)
        self._append_log("Starting job.")

        self.runner = JobRunner(self.events.put)
        self.worker = threading.Thread(
            target=self._run_worker,
            args=(self.runner, job),
            daemon=True,
        )
        self.worker.start()

    def _run_worker(self, runner: JobRunner, job: DubJob) -> None:
        try:
            asyncio.run(runner.run(job))
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

    def _drain_events(self) -> None:
        try:
            while True:
                event = self.events.get_nowait()
                if isinstance(event, JobProgress):
                    self._handle_progress(event)
                else:
                    self._append_log(event[1])
        except queue.Empty:
            pass
        if self.worker and not self.worker.is_alive() and self.start_button_text.get() == "Cancel":
            self.start_button_text.set("Start")
            self._set_controls_enabled(True)
            self.runner = None
        self.root.after(100, self._drain_events)

    def _handle_progress(self, event: JobProgress) -> None:
        if event.percent is not None:
            self.progress.set(max(0.0, min(100.0, event.percent)))
        self.status.set(event.phase.replace("_", " ").title())
        self._append_log(event.message)
        if event.phase == "failed":
            messagebox.showerror("Gemini Video Dubber", event.message)
        elif event.phase == "done":
            messagebox.showinfo("Gemini Video Dubber", event.message)

    def _append_log(self, message: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", f"{message}\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _set_controls_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for control in self.controls:
            if isinstance(control, ttk.Combobox):
                control.configure(state="readonly" if enabled else "disabled")
            else:
                control.configure(state=state)
