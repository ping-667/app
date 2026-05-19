import sys
import threading
import logging

from utils import set_dpi_aware, setup_logging


def check_dependencies():
    missing = []
    for mod in ("paddleocr", "mss", "plyer", "pystray"):
        try:
            __import__(mod.replace("-", "_"))
        except ImportError:
            missing.append(mod)
    if missing:
        print(f"缺少依赖: {', '.join(missing)}")
        print("请运行: pip install -r requirements.txt")
        sys.exit(1)


def main():
    set_dpi_aware()
    logger = setup_logging("qqmonitor")
    logger.info("QQ群消息监控 启动中...")

    check_dependencies()

    from config import Config
    from database import Database
    from ocr_engine import OCREngine
    from detector import Detector
    from monitor import Monitor
    from gui.main_window import MainWindow
    from gui.tray_icon import TrayIcon

    config = Config()
    config.load()
    logger.info("配置已加载")

    db = Database()
    logger.info("数据库已初始化")

    ocr = OCREngine()
    logger.info("OCR引擎已就绪")

    detector = Detector(
        keywords=config.get("keywords", []),
        keyword_mode=config.get("keyword_mode", "exact"),
    )

    monitor = Monitor(config, ocr, detector, db)

    main_win = MainWindow(config, db)
    main_win.set_monitor(monitor)

    def show_window():
        main_win.root.after(0, main_win.show)

    def exit_app():
        main_win.root.after(0, main_win.root.destroy)

    tray = TrayIcon(
        show_callback=show_window,
        start_callback=lambda: main_win.root.after(0, main_win._start_monitor),
        stop_callback=lambda: main_win.root.after(0, main_win._stop_monitor),
        exit_callback=exit_app,
    )

    if config.get("monitoring_enabled", False):
        main_win.root.after(500, main_win._start_monitor)

    tray_thread = threading.Thread(target=tray.run, daemon=True)
    tray_thread.start()
    logger.info("系统托盘已启动")

    if config.get("start_minimized", False):
        main_win.root.withdraw()
    else:
        main_win.show()

    try:
        main_win.run()
    finally:
        logger.info("正在退出...")
        monitor.stop()
        config.save()
        logger.info("已退出")


if __name__ == "__main__":
    main()
