"""Standalone region selector for the web-based version.

Usage: python select_region.py [port]

Opens a full-screen overlay. The user drags to select the QQ message area.
On confirm, saves the region to a temp file AND posts it to the Flask API.
"""

import json
import os
import sys
import tempfile
import tkinter as tk
import urllib.request

from utils import set_dpi_aware


class RegionSelector:
    """Full-screen tkinter overlay for selecting a screen region."""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("框选QQ消息区域")
        self.root.attributes("-fullscreen", True)
        self.root.attributes("-alpha", 0.3)
        self.root.attributes("-topmost", True)
        self.root.configure(bg="black")

        self.canvas = tk.Canvas(
            self.root, bg="black", highlightthickness=0, cursor="cross",
        )
        self.canvas.pack(fill="both", expand=True)

        self.start_x = self.start_y = None
        self.rect_id = None
        self.label_id = None
        self.result = None

        sw = self.root.winfo_screenwidth()
        self.canvas.create_text(
            sw // 2, 40,
            text="拖拽鼠标框选 QQ 群消息区域 | 按 Enter 确认 | 按 Esc 取消",
            fill="#FFD700", font=("Microsoft YaHei", 16, "bold"),
            anchor="n",
        )

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.root.bind("<Escape>", self._on_cancel)
        self.root.bind("<Return>", self._on_confirm)
        self.canvas.bind("<Double-Button-1>", self._on_confirm)

    def run(self):
        self.root.focus_force()
        self.root.lift()
        self.root.mainloop()
        return self.result

    def _on_press(self, event):
        self.start_x, self.start_y = event.x, event.y
        if self.rect_id:
            self.canvas.delete(self.rect_id)
        self.rect_id = self.canvas.create_rectangle(
            event.x, event.y, event.x, event.y,
            outline="#FF4444", width=4,
        )
        if self.label_id:
            self.canvas.delete(self.label_id)
        self.label_id = self.canvas.create_text(
            event.x + 100, event.y - 40,
            text="", fill="#00FF00", font=("Consolas", 13, "bold"),
            anchor="nw",
        )

    def _on_drag(self, event):
        if self.rect_id:
            self.canvas.coords(
                self.rect_id, self.start_x, self.start_y, event.x, event.y,
            )
        left = min(self.start_x, event.x)
        top = min(self.start_y, event.y)
        w = abs(event.x - self.start_x)
        h = abs(event.y - self.start_y)
        if self.label_id:
            self.canvas.coords(self.label_id, left, top - 40)
            self.canvas.itemconfig(
                self.label_id,
                text=f"X:{left}  Y:{top}   宽:{w}  高:{h}",
            )

    def _on_confirm(self, event=None):
        if self.start_x is not None and self.rect_id:
            coords = self.canvas.coords(self.rect_id)
            left = int(min(coords[0], coords[2]))
            top = int(min(coords[1], coords[3]))
            width = int(abs(coords[2] - coords[0]))
            height = int(abs(coords[3] - coords[1]))
            if width > 20 and height > 20:
                self.result = {
                    "left": left, "top": top,
                    "width": width, "height": height,
                }
        self.root.destroy()

    def _on_cancel(self, event):
        self.result = None
        self.root.destroy()


if __name__ == "__main__":
    set_dpi_aware()

    port = sys.argv[1] if len(sys.argv) > 1 else "5000"

    selector = RegionSelector()
    result = selector.run()

    if result:
        outfile = os.path.join(tempfile.gettempdir(), "qq_monitor_region.json")
        with open(outfile, "w", encoding="utf-8") as f:
            json.dump(result, f)

        try:
            data = json.dumps(result).encode("utf-8")
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/region/set",
                data=data,
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            pass
