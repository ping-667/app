import tkinter as tk


class RegionSelector:
    def __init__(self):
        self.root = tk.Toplevel()
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

        self.canvas.bind('<ButtonPress-1>', self._on_press)
        self.canvas.bind('<B1-Motion>', self._on_drag)
        self.canvas.bind('<ButtonRelease-1>', self._on_release)
        self.root.bind('<Escape>', self._on_cancel)
        self.root.bind('<Return>', self._on_confirm)

    def select(self):
        self.root.wait_window()
        return self.result

    def _on_press(self, event):
        self.start_x, self.start_y = event.x, event.y
        if self.rect_id:
            self.canvas.delete(self.rect_id)
        self.rect_id = self.canvas.create_rectangle(
            event.x, event.y, event.x, event.y,
            outline='#FF4444', width=2, dash=(5, 3),
        )
        if self.label_id:
            self.canvas.delete(self.label_id)
        self.label_id = self.canvas.create_text(
            event.x + 60, event.y - 15,
            text='', fill='#FF4444', font=('Microsoft YaHei', 11),
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
            self.canvas.coords(self.label_id, left, top - 20)
            self.canvas.itemconfig(
                self.label_id,
                text=f'{left},{top}  {w}x{h}',
            )

    def _on_release(self, event):
        left = min(self.start_x, event.x)
        top = min(self.start_y, event.y)
        w = abs(event.x - self.start_x)
        h = abs(event.y - self.start_y)
        if w > 20 and h > 20:
            self.result = {'left': left, 'top': top, 'width': w, 'height': h}
        self.root.destroy()

    def _on_cancel(self, event):
        self.result = None
        self.root.destroy()

    def _on_confirm(self, event):
        if self.start_x is not None:
            self._on_release(event)
        else:
            self.result = None
            self.root.destroy()
