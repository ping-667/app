import tkinter as tk
import json
import sys


class RegionSelector:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title('框选QQ消息区域 - 拖拽鼠标选择后按 Enter 确认')
        self.root.attributes('-fullscreen', True)
        self.root.attributes('-alpha', 0.3)
        self.root.attributes('-topmost', True)
        self.root.configure(bg='black')

        self.canvas = tk.Canvas(self.root, bg='black', highlightthickness=0,
                                cursor='cross')
        self.canvas.pack(fill='both', expand=True)

        self.start_x = self.start_y = None
        self.rect_id = None
        self.label_id = None
        self.result = None

        hint_id = self.canvas.create_text(
            self.root.winfo_screenwidth() // 2, 40,
            text='拖拽鼠标框选 QQ 聊天消息区域 | Enter 确认 | Esc 取消',
            fill='#FFD700', font=('Microsoft YaHei', 16, 'bold'),
            anchor='n',
        )

        self.canvas.bind('<ButtonPress-1>', self._on_press)
        self.canvas.bind('<B1-Motion>', self._on_drag)
        self.canvas.bind('<ButtonRelease-1>', self._on_release)
        self.root.bind('<Escape>', self._on_cancel)
        self.root.bind('<Return>', self._on_confirm)

    def run(self):
        self.root.mainloop()
        return self.result

    def _on_press(self, event):
        self.start_x, self.start_y = event.x, event.y
        if self.rect_id:
            self.canvas.delete(self.rect_id)
        self.rect_id = self.canvas.create_rectangle(
            event.x, event.y, event.x, event.y,
            outline='#FF4444', width=3, dash=(8, 4),
        )
        if self.label_id:
            self.canvas.delete(self.label_id)
        self.label_id = self.canvas.create_text(
            event.x + 80, event.y - 25,
            text='', fill='#FF4444', font=('Consolas', 12, 'bold'),
            anchor='nw',
        )

    def _on_drag(self, event):
        if self.rect_id:
            self.canvas.coords(self.rect_id, self.start_x, self.start_y,
                               event.x, event.y)
        left = min(self.start_x, event.x)
        top = min(self.start_y, event.y)
        w = abs(event.x - self.start_x)
        h = abs(event.y - self.start_y)
        if self.label_id:
            self.canvas.coords(self.label_id, left, top - 30)
            self.canvas.itemconfig(
                self.label_id,
                text=f'X:{left} Y:{top}  宽:{w} 高:{h}',
            )

    def _on_release(self, event):
        pass

    def _on_confirm(self, event):
        if self.start_x is not None and self.rect_id:
            coords = self.canvas.coords(self.rect_id)
            left = int(min(coords[0], coords[2]))
            top = int(min(coords[1], coords[3]))
            width = int(abs(coords[2] - coords[0]))
            height = int(abs(coords[3] - coords[1]))
            if width > 20 and height > 20:
                self.result = {'left': left, 'top': top, 'width': width, 'height': height}
        self.root.destroy()

    def _on_cancel(self, event):
        self.result = None
        self.root.destroy()


if __name__ == '__main__':
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    selector = RegionSelector()
    result = selector.run()
    if result:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print('null')
