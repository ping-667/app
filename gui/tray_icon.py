from PIL import Image, ImageDraw


def _make_icon_image():
    img = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([8, 4, 56, 52], fill='#2196F3')
    draw.ellipse([18, 14, 46, 42], fill='white')
    draw.rectangle([30, 28, 34, 44], fill='#2196F3', width=0)
    draw.ellipse([30, 42, 34, 50], fill='#2196F3')
    draw.line([24, 38, 18, 52], fill='white', width=3)
    draw.line([40, 38, 46, 52], fill='white', width=3)
    return img


class TrayIcon:
    def __init__(self, show_callback, start_callback, stop_callback, exit_callback):
        self.show_callback = show_callback
        self.start_callback = start_callback
        self.stop_callback = stop_callback
        self.exit_callback = exit_callback
        self._icon = None

    def run(self):
        import pystray
        self._icon = pystray.Icon(
            'QQMonitor',
            _make_icon_image(),
            'QQ群消息监控',
            menu=pystray.Menu(
                pystray.MenuItem('显示/隐藏主窗口', self._on_show, default=True),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem('开始监控', self._on_start),
                pystray.MenuItem('停止监控', self._on_stop),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem('退出', self._on_exit),
            ),
        )
        self._icon.run()

    def stop(self):
        if self._icon:
            self._icon.stop()

    def _on_show(self, icon, item):
        self.show_callback()

    def _on_start(self, icon, item):
        self.start_callback()

    def _on_stop(self, icon, item):
        self.stop_callback()

    def _on_exit(self, icon, item):
        self.stop_callback()
        self._icon.stop()
        self.exit_callback()
