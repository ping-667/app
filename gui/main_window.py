import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime


class MainWindow:
    def __init__(self, config, db):
        self.config = config
        self.db = db
        self.monitor = None

        self.root = tk.Tk()
        self.root.title('QQ群消息监控')
        self.root.geometry('1050x680')
        self.root.minsize(800, 500)
        self.root.protocol('WM_DELETE_WINDOW', self._on_close)

        self._build_ui()
        self._start_queue_poller()

    def set_monitor(self, monitor):
        self.monitor = monitor

    # ---- Build UI ----

    def _build_ui(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill='both', expand=True, padx=5, pady=5)

        self.history_tab = ttk.Frame(self.notebook)
        self.keywords_tab = ttk.Frame(self.notebook)
        self.settings_tab = ttk.Frame(self.notebook)

        self.notebook.add(self.history_tab, text='消息记录')
        self.notebook.add(self.keywords_tab, text='关键词管理')
        self.notebook.add(self.settings_tab, text='设置')

        self._build_history_tab()
        self._build_keywords_tab()
        self._build_settings_tab()

        self.status_bar = ttk.Label(
            self.root, text='监控状态: 未启动  |  按提示配置并开始监控',
            relief='sunken', padding=(8, 3),
        )
        self.status_bar.pack(side='bottom', fill='x')

    def _build_history_tab(self):
        search_frame = ttk.Frame(self.history_tab)
        search_frame.pack(fill='x', padx=5, pady=5)

        ttk.Label(search_frame, text='搜索:').pack(side='left')
        self.search_entry = ttk.Entry(search_frame, width=20)
        self.search_entry.pack(side='left', padx=5)
        self.search_entry.bind('<KeyRelease>', lambda e: self._refresh_history())

        ttk.Label(search_frame, text='发送者:').pack(side='left', padx=(15, 0))
        self.sender_filter = ttk.Combobox(search_frame, width=10, state='readonly')
        self.sender_filter.pack(side='left', padx=5)
        self.sender_filter.bind('<<ComboboxSelected>>', lambda e: self._refresh_history())

        ttk.Label(search_frame, text='关键词:').pack(side='left', padx=(15, 0))
        self.keyword_filter = ttk.Combobox(search_frame, width=10, state='readonly')
        self.keyword_filter.pack(side='left', padx=5)
        self.keyword_filter.bind('<<ComboboxSelected>>', lambda e: self._refresh_history())

        ttk.Button(search_frame, text='刷新', command=self._refresh_history).pack(
            side='left', padx=(15, 0))
        ttk.Button(search_frame, text='导出CSV', command=self._export_csv).pack(
            side='left', padx=5)

        columns = ('id', '检测时间', '发送者', '内容', '匹配关键词')
        self.tree = ttk.Treeview(self.history_tab, columns=columns,
                                 show='headings', selectmode='browse')
        self.tree.heading('id', text='ID')
        self.tree.column('id', width=40, stretch=False)
        self.tree.heading('检测时间', text='检测时间')
        self.tree.column('检测时间', width=150, stretch=False)
        self.tree.heading('发送者', text='发送者')
        self.tree.column('发送者', width=100, stretch=False)
        self.tree.heading('内容', text='内容')
        self.tree.column('内容', width=420)
        self.tree.heading('匹配关键词', text='匹配关键词')
        self.tree.column('匹配关键词', width=150)

        scrollbar = ttk.Scrollbar(self.history_tab, orient='vertical',
                                  command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

        self.tree.bind('<Double-1>', self._on_message_double_click)

        btn_frame = ttk.Frame(self.history_tab)
        btn_frame.pack(fill='x', padx=5, pady=5)
        ttk.Button(btn_frame, text='标记已读', command=self._mark_read).pack(
            side='left', padx=5)
        ttk.Button(btn_frame, text='删除选中', command=self._delete_selected).pack(
            side='left', padx=5)
        ttk.Button(btn_frame, text='清空所有记录', command=self._clear_all).pack(
            side='right', padx=5)

    def _build_keywords_tab(self):
        top = ttk.Frame(self.keywords_tab)
        top.pack(fill='x', padx=5, pady=5)

        ttk.Label(top, text='添加关键词:').pack(side='left')
        self.kw_entry = ttk.Entry(top, width=20)
        self.kw_entry.pack(side='left', padx=5)
        self.kw_entry.bind('<Return>', lambda e: self._add_keyword())
        ttk.Button(top, text='添加', command=self._add_keyword).pack(side='left')

        ttk.Label(top, text='匹配模式:').pack(side='left', padx=(20, 5))
        self.kw_mode = ttk.Combobox(top, values=['exact', 'regex'],
                                    state='readonly', width=8)
        self.kw_mode.set(self.config.get('keyword_mode', 'exact'))
        self.kw_mode.pack(side='left')
        self.kw_mode.bind('<<ComboboxSelected>>', self._on_mode_change)

        ttk.Button(top, text='恢复默认', command=self._reset_keywords).pack(
            side='right', padx=5)

        list_frame = ttk.Frame(self.keywords_tab)
        list_frame.pack(fill='both', expand=True, padx=5, pady=5)

        self.kw_listbox = tk.Listbox(list_frame, selectmode='extended',
                                     font=('Microsoft YaHei', 11))
        kw_scroll = ttk.Scrollbar(list_frame, orient='vertical',
                                  command=self.kw_listbox.yview)
        self.kw_listbox.configure(yscrollcommand=kw_scroll.set)
        self.kw_listbox.pack(side='left', fill='both', expand=True)
        kw_scroll.pack(side='right', fill='y')

        btn_frame = ttk.Frame(self.keywords_tab)
        btn_frame.pack(fill='x', padx=5, pady=5)
        ttk.Button(btn_frame, text='删除选中', command=self._delete_keywords).pack(
            side='left', padx=5)
        ttk.Button(btn_frame, text='清空全部', command=self._clear_keywords).pack(
            side='left', padx=5)

        ttk.Label(self.keywords_tab,
                  text='提示: 精确模式匹配子串(如"考试"匹配"考试时间")；'
                       '正则模式支持高级匹配(如"考试|考核")',
                  foreground='gray').pack(pady=(0, 5))

        self._refresh_keyword_list()

    def _build_settings_tab(self):
        pad = {'padx': 10, 'pady': 5, 'fill': 'x'}

        region_frame = ttk.LabelFrame(self.settings_tab, text='监控区域', padding=10)
        region_frame.pack(**pad)

        self.region_label = ttk.Label(
            region_frame,
            text=self._format_region_text(),
            font=('Consolas', 10),
        )
        self.region_label.pack(side='left', padx=(0, 10))

        ttk.Button(region_frame, text='框选区域',
                   command=self._select_region).pack(side='left', padx=5)
        ttk.Button(region_frame, text='预览区域截图',
                   command=self._preview_region).pack(side='left', padx=5)

        interval_frame = ttk.LabelFrame(self.settings_tab, text='监控参数', padding=10)
        interval_frame.pack(**pad)

        ttk.Label(interval_frame, text='检测间隔(秒):').pack(side='left')
        self.interval_var = tk.StringVar(
            value=str(self.config.get('interval_seconds', 5)))
        interval_spin = ttk.Spinbox(interval_frame, from_=1, to=60,
                                    textvariable=self.interval_var, width=5)
        interval_spin.pack(side='left', padx=5)
        self.interval_var.trace('w', lambda *a: self._on_interval_change())

        ttk.Label(interval_frame, text='群名称:').pack(side='left', padx=(20, 0))
        self.group_var = tk.StringVar(value=self.config.get('group_name', '默认'))
        group_entry = ttk.Entry(interval_frame, textvariable=self.group_var, width=12)
        group_entry.pack(side='left', padx=5)
        self.group_var.trace('w', lambda *a: self._on_group_change())

        option_frame = ttk.LabelFrame(self.settings_tab, text='选项', padding=10)
        option_frame.pack(**pad)

        self.notify_var = tk.BooleanVar(
            value=self.config.get('notification_enabled', True))
        ttk.Checkbutton(option_frame, text='启用桌面通知',
                        variable=self.notify_var,
                        command=self._on_notify_change).pack(anchor='w')

        self.autostart_var = tk.BooleanVar(
            value=self.config.get('monitoring_enabled', True))
        ttk.Checkbutton(option_frame, text='启动时自动开始监控',
                        variable=self.autostart_var,
                        command=self._on_autostart_change).pack(anchor='w')

        self.minimize_var = tk.BooleanVar(
            value=self.config.get('start_minimized', False))
        ttk.Checkbutton(option_frame, text='启动时最小化到托盘',
                        variable=self.minimize_var,
                        command=self._on_minimize_change).pack(anchor='w')

        self.screenshot_var = tk.BooleanVar(
            value=self.config.get('save_screenshots', False))
        ttk.Checkbutton(option_frame, text='保存匹配截图(占用较多磁盘)',
                        variable=self.screenshot_var,
                        command=self._on_screenshot_change).pack(anchor='w')

        ctrl_frame = ttk.Frame(self.settings_tab)
        ctrl_frame.pack(padx=10, pady=15, fill='x')

        self.start_btn = ttk.Button(ctrl_frame, text='▶ 开始监控',
                                    command=self._start_monitor)
        self.start_btn.pack(side='left', padx=5)

        self.stop_btn = ttk.Button(ctrl_frame, text='■ 停止监控',
                                   command=self._stop_monitor, state='disabled')
        self.stop_btn.pack(side='left', padx=5)

        self.status_text = ttk.Label(ctrl_frame, text='',
                                     font=('Microsoft YaHei', 9))
        self.status_text.pack(side='left', padx=20)

    # ---- History tab actions ----

    def _refresh_history(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        search = self.search_entry.get().strip()
        sender = self.sender_filter.get()
        keyword = self.keyword_filter.get()

        messages = self.db.query_messages(
            keyword=keyword if keyword else None,
            sender=sender if sender else None,
            limit=500,
        )

        for m in messages:
            content = m['content']
            if search and search.lower() not in content.lower():
                continue
            display_content = content[:80] + '...' if len(content) > 80 else content
            self.tree.insert('', 'end', values=(
                m['id'], m['detected_at'][:19], m['sender'],
                display_content, m['matched_keywords'],
            ))

        self._update_filters()

    def _update_filters(self):
        senders = self.db.get_unique_senders()
        self.sender_filter['values'] = [''] + senders
        keywords = self.db.get_unique_keywords()
        self.keyword_filter['values'] = [''] + keywords

    def _on_message_double_click(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        values = self.tree.item(sel[0], 'values')
        if not values:
            return
        msg_id = values[0]
        messages = self.db.query_messages(limit=1)
        msg = None
        for m in messages:
            if str(m['id']) == str(msg_id):
                msg = m
                break
        if not msg:
            return

        popup = tk.Toplevel(self.root)
        popup.title(f"消息详情 - {msg['sender']}")
        popup.geometry('550x350')
        popup.minsize(400, 250)

        info = f"发送者: {msg['sender']}\n"
        info += f"时间: {msg['detected_at']}\n"
        info += f"匹配关键词: {msg['matched_keywords']}\n"
        info += f"群组: {msg['group_name']}\n\n"
        info += '-' * 40 + '\n\n'

        ttk.Label(popup, text=info, font=('Microsoft YaHei', 10),
                  justify='left').pack(padx=15, pady=(15, 5), anchor='w')

        text_frame = ttk.Frame(popup)
        text_frame.pack(fill='both', expand=True, padx=15, pady=(0, 15))
        content_text = tk.Text(text_frame, wrap='word', font=('Microsoft YaHei', 10))
        content_scroll = ttk.Scrollbar(text_frame, orient='vertical',
                                       command=content_text.yview)
        content_text.configure(yscrollcommand=content_scroll.set)
        content_text.pack(side='left', fill='both', expand=True)
        content_scroll.pack(side='right', fill='y')
        content_text.insert('1.0', msg['content'])
        content_text.configure(state='disabled')

    def _mark_read(self):
        sel = self.tree.selection()
        if not sel:
            return
        msg_id = self.tree.item(sel[0], 'values')[0]
        self.db.mark_read(msg_id)

    def _delete_selected(self):
        sel = self.tree.selection()
        if not sel:
            return
        if messagebox.askyesno('确认', '确定要删除选中的消息吗？'):
            for item in sel:
                msg_id = self.tree.item(item, 'values')[0]
                self.db.delete_message(msg_id)
            self._refresh_history()

    def _clear_all(self):
        if messagebox.askyesno('确认', '确定要清空所有消息记录吗？此操作不可恢复。'):
            self.db.clear_all()
            self._refresh_history()

    def _export_csv(self):
        path = filedialog.asksaveasfilename(
            defaultextension='.csv',
            filetypes=[('CSV文件', '*.csv')],
            initialfile=f"QQ监控_{datetime.now().strftime('%Y%m%d')}.csv",
        )
        if path:
            self.db.export_csv(path)
            messagebox.showinfo('导出成功', f'已导出到:\n{path}')

    # ---- Keywords tab actions ----

    def _refresh_keyword_list(self):
        self.kw_listbox.delete(0, 'end')
        keywords = self.config.get('keywords', [])
        for kw in keywords:
            self.kw_listbox.insert('end', kw)

    def _add_keyword(self):
        text = self.kw_entry.get().strip()
        if not text:
            return
        keywords = self.config.get('keywords', [])
        if text in keywords:
            messagebox.showwarning('提示', '该关键词已存在')
            return
        keywords.append(text)
        self.config.set('keywords', keywords)
        self.config.save()
        self._refresh_keyword_list()
        self.kw_entry.delete(0, 'end')
        if self.monitor:
            self.monitor.detector.set_keywords(keywords)

    def _delete_keywords(self):
        sel = self.kw_listbox.curselection()
        if not sel:
            return
        keywords = self.config.get('keywords', [])
        to_remove = [self.kw_listbox.get(i) for i in sel]
        for kw in to_remove:
            if kw in keywords:
                keywords.remove(kw)
        self.config.set('keywords', keywords)
        self.config.save()
        self._refresh_keyword_list()
        if self.monitor:
            self.monitor.detector.set_keywords(keywords)

    def _clear_keywords(self):
        if messagebox.askyesno('确认', '确定要清空所有关键词吗？'):
            self.config.set('keywords', [])
            self.config.save()
            self._refresh_keyword_list()
            if self.monitor:
                self.monitor.detector.set_keywords([])

    def _reset_keywords(self):
        from config import DEFAULT_KEYWORDS
        self.config.set('keywords', DEFAULT_KEYWORDS)
        self.config.save()
        self._refresh_keyword_list()
        if self.monitor:
            self.monitor.detector.set_keywords(DEFAULT_KEYWORDS)

    def _on_mode_change(self, event):
        mode = self.kw_mode.get()
        self.config.set('keyword_mode', mode)
        self.config.save()
        if self.monitor:
            self.monitor.detector.keyword_mode = mode

    # ---- Settings tab actions ----

    def _format_region_text(self):
        r = self.config.get('region', {})
        return f"左:{r.get('left',0)} 上:{r.get('top',0)}\n宽:{r.get('width',800)} 高:{r.get('height',600)}"

    def _select_region(self):
        self.root.withdraw()
        self.root.after(300, self._do_select_region)

    def _do_select_region(self):
        from gui.region_selector import RegionSelector
        selector = RegionSelector()
        result = selector.select()
        if result:
            self.config.set('region', result)
            self.config.save()
            self.region_label.config(text=self._format_region_text())
        self.root.deiconify()

    def _preview_region(self):
        try:
            import mss
            from PIL import Image as PILImage
            region = self.config.get_region_dict()
            with mss.mss() as sct:
                img = sct.grab(region)
                pil_img = PILImage.frombytes('RGB', img.size, img.rgb)

            preview = tk.Toplevel(self.root)
            preview.title('区域预览 - 关闭此窗口返回')
            preview.geometry(f'{img.size[0]}x{img.size[1]}')
            from PIL import ImageTk
            photo = ImageTk.PhotoImage(pil_img)
            label = ttk.Label(preview, image=photo)
            label.image = photo
            label.pack()
        except Exception as e:
            messagebox.showerror('预览失败', f'无法截取该区域:\n{e}')

    def _on_interval_change(self):
        try:
            val = int(self.interval_var.get())
            if 1 <= val <= 60:
                self.config.set('interval_seconds', val)
                self.config.save()
        except ValueError:
            pass

    def _on_group_change(self):
        self.config.set('group_name', self.group_var.get())
        self.config.save()

    def _on_notify_change(self):
        self.config.set('notification_enabled', self.notify_var.get())
        self.config.save()

    def _on_autostart_change(self):
        self.config.set('monitoring_enabled', self.autostart_var.get())
        self.config.save()

    def _on_minimize_change(self):
        self.config.set('start_minimized', self.minimize_var.get())
        self.config.save()

    def _on_screenshot_change(self):
        self.config.set('save_screenshots', self.screenshot_var.get())
        self.config.save()

    # ---- Monitor control ----

    def _start_monitor(self):
        if not self.monitor:
            messagebox.showerror('错误', '监控引擎未初始化')
            return
        self.monitor.detector.set_keywords(self.config.get('keywords', []))
        self.monitor.detector.keyword_mode = self.config.get('keyword_mode', 'exact')
        self.monitor.start()
        self.start_btn.configure(state='disabled')
        self.stop_btn.configure(state='normal')
        self.status_text.config(text='● 监控运行中', foreground='green')
        self.status_bar.config(text='监控状态: 运行中  |  检测关键词并记录消息')

    def _stop_monitor(self):
        if self.monitor:
            self.monitor.stop()
        self.start_btn.configure(state='normal')
        self.stop_btn.configure(state='disabled')
        self.status_text.config(text='○ 监控已停止', foreground='gray')
        self.status_bar.config(text='监控状态: 已停止')

    # ---- Queue poller ----

    def _start_queue_poller(self):
        if self.monitor and not self.monitor.result_queue.empty():
            self._refresh_history()
        self.root.after(2000, self._start_queue_poller)

    # ---- Window management ----

    def toggle_visible(self):
        if self.root.state() == 'withdrawn' or self.root.state() == 'iconic':
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
        else:
            self.root.withdraw()

    def _on_close(self):
        self.root.withdraw()

    def show(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def run(self):
        self._refresh_history()
        self._update_filters()
        self.root.mainloop()
