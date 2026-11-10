"""Frameless Tk window with custom controls, no window-procedure subclassing."""
import sys
import tkinter as tk


class WindowChrome:
    radius, header_height, controls_width = 26, 34, 140

    def __init__(self, root, on_close):
        self.root, self.on_close = root, on_close
        self.hwnd, self.native, self.maximized = None, False, False
        self.drag_widgets, self.drag_rects = [], []
        self.maximize_button = None
        self._sync_id = self._region_key = self._gesture = self._normal_rect = None
        root.overrideredirect(True)
        for sequence, callback in (('<Configure>', self._configured), ('<Map>', self._configured),
                ('<Destroy>', self._destroyed), ('<ButtonPress-1>', self._press),
                ('<B1-Motion>', self._move), ('<ButtonRelease-1>', self._release),
                ('<Double-Button-1>', self._double_click), ('<Motion>', self._cursor),
                ('<Alt-F4>', self._close_event)):
            root.bind(sequence, callback, add='+')
        root.after_idle(self._install)

    def add_drag_zone(self, widget):
        self.drag_widgets.append(widget)

    def _close_event(self, event):
        self.on_close()
        return 'break'

    def _install(self):
        if sys.platform != 'win32':
            return
        import ctypes as c
        from ctypes import wintypes as w
        self.c, self.w = c, w
        self.user, self.gdi = c.WinDLL('user32', use_last_error=True), c.WinDLL('gdi32', use_last_error=True)
        self.user.GetAncestor.argtypes, self.user.GetAncestor.restype = (w.HWND, w.UINT), w.HWND
        self.user.GetWindowLongPtrW.argtypes, self.user.GetWindowLongPtrW.restype = (w.HWND, c.c_int), c.c_ssize_t
        self.user.SetWindowLongPtrW.argtypes, self.user.SetWindowLongPtrW.restype = (w.HWND, c.c_int, c.c_ssize_t), c.c_ssize_t
        self.user.GetWindowRect.argtypes = (w.HWND, c.POINTER(w.RECT))
        self.user.SetWindowPos.argtypes = (w.HWND, w.HWND, c.c_int, c.c_int, c.c_int, c.c_int, w.UINT)
        self.user.SetWindowRgn.argtypes = (w.HWND, w.HRGN, w.BOOL)
        self.user.IsWindow.argtypes = (w.HWND,)
        self.user.IsIconic.argtypes = (w.HWND,)
        self.user.ShowWindow.argtypes = (w.HWND, c.c_int)
        self.user.MonitorFromWindow.argtypes, self.user.MonitorFromWindow.restype = (w.HWND, w.DWORD), w.HANDLE
        self.user.GetMonitorInfoW.argtypes = (w.HANDLE, c.c_void_p)
        self.gdi.CreateRoundRectRgn.argtypes, self.gdi.CreateRoundRectRgn.restype = (c.c_int,)*6, w.HRGN
        self.gdi.DeleteObject.argtypes = (w.HGDIOBJ,)
        self.native = True
        self._sync()

    def _current_handle(self):
        # Tk owns its wrapper lifecycle. Reapply taskbar/rounding only when
        # that wrapper changes; never retain a window-procedure callback.
        client = self.root.winfo_id()
        current = self.user.GetAncestor(client, 2)
        if current == client or self.user.GetWindowLongPtrW(current, -16) & 0x40000000:
            # Before the first Map, Tk's client can still be unparented.
            # Clipping that temporary 1x1 client would hide every child widget
            # even after the real wrapper is created. Wait for its Map event.
            return None
        if current != self.hwnd:
            self.hwnd, self._region_key = current, None
            extended = self.user.GetWindowLongPtrW(current, -20)
            self.user.SetWindowLongPtrW(current, -20, (extended & ~0x80) | 0x40000)
        return current

    def _rect(self):
        hwnd = self._current_handle() if self.native else None
        if hwnd:
            rect = self.w.RECT()
            self.user.GetWindowRect(hwnd, self.c.byref(rect))
            return rect.left, rect.top, rect.right, rect.bottom
        x, y = self.root.winfo_x(), self.root.winfo_y()
        return x, y, x+self.root.winfo_width(), y+self.root.winfo_height()

    def _place(self, rect):
        left, top, right, bottom = map(int, rect)
        hwnd = self._current_handle() if self.native else None
        if hwnd:
            self.user.SetWindowPos(hwnd, None, left, top, right-left, bottom-top, 0x0014)
        else:
            self.root.geometry(f'{right-left}x{bottom-top}{left:+d}{top:+d}')

    def hit_test(self, screen_x, screen_y):
        left, top, right, bottom = self._rect()
        x, y, width, height = screen_x-left, screen_y-top, right-left, bottom-top
        if 5 <= y < self.header_height and width-self.controls_width <= x < width-8:
            return 1
        if not self.maximized:
            if x < 24 and y < 24:
                return 13
            if x >= width-24 and y < 24:
                return 14
            if x < 24 and y >= height-24:
                return 16
            if x >= width-24 and y >= height-24:
                return 17
            if x < 7:
                return 10
            if x >= width-7:
                return 11
            if y < 7:
                return 12
            if y >= height-7:
                return 15
        if y < self.header_height and x < width-self.controls_width:
            return 2
        if any(a <= screen_x < c and b <= screen_y < d for a, b, c, d in self.drag_rects):
            return 2
        return 1

    def _press(self, event):
        mode = self.hit_test(event.x_root, event.y_root)
        if mode == 2 or mode >= 10:
            self._gesture = (mode, event.x_root, event.y_root, self._rect())
            self.root.grab_set()
            return 'break'

    def _move(self, event):
        if self._gesture is None:
            return
        mode, x, y, rect = self._gesture
        dx, dy = event.x_root-x, event.y_root-y
        left, top, right, bottom = rect
        if mode == 2:
            if self.maximized:
                fraction = (x-left)/max(1, right-left)
                self.toggle_maximize()
                left, top, right, bottom = self._rect()
                x = left+int((right-left)*fraction)
                dx, dy = event.x_root-x, event.y_root-top-18
                self._gesture = (mode, event.x_root, event.y_root, (left+dx, top+dy, right+dx, bottom+dy))
            self._place((left+dx, top+dy, right+dx, bottom+dy))
        else:
            minimum_w, minimum_h = self.root.minsize()
            if mode in (10, 13, 16):
                left = min(left+dx, right-minimum_w)
            if mode in (11, 14, 17):
                right = max(right+dx, left+minimum_w)
            if mode in (12, 13, 14):
                top = min(top+dy, bottom-minimum_h)
            if mode in (15, 16, 17):
                bottom = max(bottom+dy, top+minimum_h)
            self._place((left, top, right, bottom))
        return 'break'

    def _release(self, event):
        if self._gesture is not None:
            self._gesture = None
            self.root.grab_release()
            return 'break'

    def _double_click(self, event):
        if self.hit_test(event.x_root, event.y_root) == 2:
            self._release(event)
            self.toggle_maximize()
            return 'break'

    def _cursor(self, event):
        if self._gesture is None:
            mode = self.hit_test(event.x_root, event.y_root)
            cursor = {10:'sb_h_double_arrow', 11:'sb_h_double_arrow', 12:'sb_v_double_arrow',
                      15:'sb_v_double_arrow', 13:'size_nw_se', 17:'size_nw_se',
                      14:'size_ne_sw', 16:'size_ne_sw'}.get(mode, '')
            self.root.configure(cursor=cursor)

    def _configured(self, event):
        if event.widget == self.root and self._sync_id is None:
            self._sync_id = self.root.after_idle(self._sync)

    def _sync(self):
        self._sync_id = None
        if self.native:
            hwnd = self._current_handle()
            if hwnd and self.user.IsWindow(hwnd) and not self.user.IsIconic(hwnd):
                left, top, right, bottom = self._rect()
                key = (hwnd, right-left, bottom-top, self.maximized)
                if key != self._region_key:
                    self._region_key = key
                    if self.maximized:
                        self.user.SetWindowRgn(hwnd, None, True)
                    else:
                        r = self.radius*2
                        region = self.gdi.CreateRoundRectRgn(0, 0, right-left+1, bottom-top+1, r, r)
                        if region and not self.user.SetWindowRgn(hwnd, region, True):
                            self.gdi.DeleteObject(region)
        if self.maximize_button:
            self.maximize_button.configure(symbol='restore' if self.maximized else 'maximize')
        self.drag_rects = [(widget.winfo_rootx(), widget.winfo_rooty(),
                            widget.winfo_rootx()+widget.winfo_width(), widget.winfo_rooty()+widget.winfo_height())
                           for widget in self.drag_widgets if widget.winfo_ismapped()]

    def _work_area(self):
        if self.native:
            class Monitor(self.c.Structure):
                _fields_ = [('size', self.w.DWORD), ('monitor', self.w.RECT), ('work', self.w.RECT), ('flags', self.w.DWORD)]
            info = Monitor()
            info.size = self.c.sizeof(info)
            monitor = self.user.MonitorFromWindow(self._current_handle(), 2)
            if self.user.GetMonitorInfoW(monitor, self.c.byref(info)):
                return info.work.left, info.work.top, info.work.right, info.work.bottom
        return 0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight()

    def minimize(self):
        if self.native:
            self.user.ShowWindow(self._current_handle(), 6)
        else:
            self.root.overrideredirect(False)
            self.root.iconify()

    def toggle_maximize(self):
        if self.maximized:
            self.maximized = False
            if self._normal_rect:
                self._place(self._normal_rect)
        else:
            self._normal_rect = self._rect()
            self.maximized = True
            self._place(self._work_area())
        self._sync()

    def restore(self):
        if self.native:
            self.user.ShowWindow(self._current_handle(), 9)
        else:
            self.root.deiconify()
            self.root.overrideredirect(True)
        self._sync()

    def _destroyed(self, event):
        if event.widget == self.root:
            if self._sync_id is not None:
                try:
                    self.root.after_cancel(self._sync_id)
                except tk.TclError:
                    pass
            self.native = False
