from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import font as tkfont

from .models import HudViewModel


class BaseHud:
    def update(self, model: HudViewModel) -> None:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError


class NullHud(BaseHud):
    def update(self, model: HudViewModel) -> None:
        del model

    def close(self) -> None:
        return


class TkHudOverlay(BaseHud):
    def __init__(self) -> None:
        self._queue: "queue.Queue[HudViewModel | None]" = queue.Queue()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def update(self, model: HudViewModel) -> None:
        self._queue.put(model)

    def close(self) -> None:
        self._queue.put(None)
        self._thread.join(timeout=1.0)

    def _run(self) -> None:
        root = tk.Tk()
        root.withdraw()
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.attributes("-alpha", 0.94)
        root.configure(background="#111111")

        frame = tk.Frame(root, bg="#111111", padx=16, pady=14)
        frame.pack(fill=tk.BOTH, expand=True)

        title_font = tkfont.Font(family="Helvetica Neue", size=17, weight="bold")
        body_font = tkfont.Font(family="Helvetica Neue", size=12)
        mono_font = tkfont.Font(family="Menlo", size=11)

        title_var = tk.StringVar()
        subtitle_var = tk.StringVar()
        gesture_var = tk.StringVar()
        options_var = tk.StringVar()

        title_label = tk.Label(
            frame,
            textvariable=title_var,
            bg="#111111",
            fg="#F5F5F5",
            font=title_font,
            anchor="w",
        )
        title_label.pack(fill=tk.X)
        subtitle_label = tk.Label(
            frame,
            textvariable=subtitle_var,
            bg="#111111",
            fg="#D0D0D0",
            font=body_font,
            anchor="w",
            justify=tk.LEFT,
            wraplength=380,
        )
        subtitle_label.pack(fill=tk.X, pady=(6, 0))
        gesture_label = tk.Label(
            frame,
            textvariable=gesture_var,
            bg="#111111",
            fg="#7FDBCA",
            font=mono_font,
            anchor="w",
        )
        gesture_label.pack(fill=tk.X, pady=(8, 0))
        options_label = tk.Label(
            frame,
            textvariable=options_var,
            bg="#111111",
            fg="#F5F5F5",
            font=body_font,
            anchor="w",
            justify=tk.LEFT,
            wraplength=380,
        )
        options_label.pack(fill=tk.X, pady=(8, 0))

        def apply_model(model: HudViewModel | None) -> None:
            if model is None:
                root.destroy()
                return
            if not model.visible:
                root.withdraw()
                return
            title_var.set(model.title)
            subtitle_var.set(model.subtitle)
            gesture_var.set(f"gesture: {model.active_gesture or '-'}")
            if model.options:
                lines = []
                for idx, option in enumerate(model.options):
                    marker = ">" if idx == model.selection_index else " "
                    lines.append(f"{marker} {option}")
                options_var.set("\n".join(lines))
            else:
                options_var.set("")
            root.update_idletasks()
            width = 420
            height = max(110, 120 + 24 * min(len(model.options), 5))
            screen_w = root.winfo_screenwidth()
            root.geometry(f"{width}x{height}+{screen_w - width - 28}+28")
            root.deiconify()

        def pump() -> None:
            try:
                while True:
                    item = self._queue.get_nowait()
                    apply_model(item)
            except queue.Empty:
                pass
            root.after(50, pump)

        root.after(50, pump)
        root.mainloop()
