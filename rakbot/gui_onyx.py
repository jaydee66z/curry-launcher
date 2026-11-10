"""Static, lightweight Onyx widgets and layout. No image/UI dependencies."""
import math
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, ttk
from .mass import MAX_ACCOUNTS
from .gui_support import SORT_OPTIONS

BG = '#070707'
PANEL = '#0c0c0c'
FIELD = '#101010'
BORDER = '#272727'
TEXT = '#f1f1f1'
MUTED = '#a5a8af'


def rounded(canvas, x1, y1, x2, y2, radius, **options):
    radius = min(radius * 1.7, max(0, (x2 - x1) / 2), max(0, (y2 - y1) / 2))
    points = (x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius,
              x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2,
              x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1)
    return canvas.create_polygon(points, smooth=True, splinesteps=24, **options)


class Panel(tk.Canvas):
    def __init__(self, parent, *, fill=PANEL, border=BORDER, radius=16, padding=16, **kwargs):
        super().__init__(parent, bg=parent.cget('bg'), highlightthickness=0, bd=0, **kwargs)
        self.fill, self.border, self.radius, self.padding = fill, border, radius, padding
        self.body = tk.Frame(self, bg=fill, bd=0)
        self.window = self.create_window(padding, padding, window=self.body, anchor='nw')
        self.bind('<Configure>', self._resize)

    def _resize(self, event):
        self.delete('surface')
        rounded(self, 1, 1, event.width - 1, event.height - 1, self.radius,
                fill=self.fill, outline=self.border, width=1, tags='surface')
        self.tag_lower('surface')
        self.itemconfigure(self.window, width=max(1, event.width - self.padding * 2),
                           height=max(1, event.height - self.padding * 2))


def icon(canvas, name, x, y, size=22, color=MUTED):
    r = size / 2
    line = dict(fill=color, width=1.7, capstyle='round', joinstyle='round')
    if name == 'search':
        canvas.create_oval(x-r*.75, y-r*.85, x+r*.55, y+r*.45, outline=color, width=1.8)
        canvas.create_line(x+r*.35, y+r*.3, x+r, y+r, **line)
    elif name == 'server':
        for dy in (-r*.52, r*.52):
            rounded(canvas, x-r, y+dy-r*.36, x+r, y+dy+r*.36, 3,
                    fill='', outline=color, width=1.7)
            canvas.create_oval(x+r*.5, y+dy-1, x+r*.5+2, y+dy+1, fill=color, outline='')
    elif name == 'clock':
        canvas.create_oval(x-r, y-r, x+r, y+r, outline=color, width=1.8)
        canvas.create_line(x, y-r*.65, x, y, x+r*.5, y+r*.3, **line)
    elif name == 'star':
        points = []
        for i in range(10):
            a = -math.pi/2 + math.pi*i/5
            length = r if i % 2 == 0 else r*.45
            points.extend((x + math.cos(a)*length, y + math.sin(a)*length))
        canvas.create_polygon(points, fill='', outline=color, width=1.8, joinstyle='round')
    elif name == 'play':
        canvas.create_polygon(x-r*.5, y-r*.7, x+r*.65, y, x-r*.5, y+r*.7,
                              fill=color, outline=color, joinstyle='round')
    elif name == 'stop':
        rounded(canvas, x-r*.6, y-r*.6, x+r*.6, y+r*.6, 3, fill=color, outline=color)
    elif name == 'copy':
        rounded(canvas, x-r*.3, y-r*.9, x+r*.65, y+r*.5, 2, fill='', outline=color, width=1.4)
        rounded(canvas, x-r*.65, y-r*.5, x+r*.3, y+r*.9, 2, fill=canvas.cget('bg'), outline=color, width=1.4)
    elif name == 'folder':
        canvas.create_line(x-r, y-r*.5, x-r*.25, y-r*.5, x, y-r*.8, x+r, y-r*.8,
                           x+r, y+r*.65, x-r, y+r*.65, x-r, y-r*.5, **line)
    elif name == 'file':
        canvas.create_line(x-r*.7, y-r, x+r*.2, y-r, x+r*.7, y-r*.5, x+r*.7, y+r,
                           x-r*.7, y+r, x-r*.7, y-r, **line)
        canvas.create_line(x+r*.2, y-r, x+r*.2, y-r*.5, x+r*.7, y-r*.5, **line)
    elif name == 'trophy':
        canvas.create_line(x-r*.6, y-r*.8, x+r*.6, y-r*.8, x+r*.45, y+r*.1,
                           x, y+r*.5, x-r*.45, y+r*.1, x-r*.6, y-r*.8, **line)
        canvas.create_line(x, y+r*.5, x, y+r, x-r*.5, y+r, x+r*.5, y+r, **line)
        for sign in (-1, 1):
            canvas.create_line(x+sign*r*.6, y-r*.55, x+sign*r, y-r*.55,
                               x+sign*r*.9, y+r*.05, x+sign*r*.45, y+r*.2, **line)
    elif name == 'gear':
        points = []
        for i in range(32):
            angle = i*math.pi/16
            length = r if i % 4 in (1, 2) else r*.73
            points.extend((x+math.cos(angle)*length, y+math.sin(angle)*length))
        canvas.create_polygon(points, fill='', outline=color, width=1.4, joinstyle='round')
        canvas.create_oval(x-r*.32, y-r*.32, x+r*.32, y+r*.32, outline=color, width=1.6)
    elif name == 'minimize':
        canvas.create_line(x-r*.55, y+r*.2, x+r*.55, y+r*.2, **line)
    elif name == 'maximize':
        canvas.create_rectangle(x-r*.55, y-r*.55, x+r*.55, y+r*.55, outline=color, width=1.4)
    elif name == 'restore':
        canvas.create_line(x-r*.25, y-r*.7, x+r*.7, y-r*.7, x+r*.7, y+r*.25, **line)
        canvas.create_rectangle(x-r*.65, y-r*.25, x+r*.25, y+r*.65, outline=color, width=1.4)
    elif name == 'close':
        canvas.create_line(x-r*.55, y-r*.55, x+r*.55, y+r*.55, **line)
        canvas.create_line(x-r*.55, y+r*.55, x+r*.55, y-r*.55, **line)


class Button(tk.Canvas):
    def __init__(self, parent, *, text='', command=None, primary=False, selected=False,
                 symbol=None, end_symbol=None, align='center', height=42, width=120, radius=12,
                 border=True, font=('Segoe UI', 11), state='normal'):
        super().__init__(parent, bg=parent.cget('bg'), height=height, width=width,
                         highlightthickness=0, bd=0, takefocus=1, cursor='hand2')
        self.text, self.command, self.primary = text, command, primary
        self.symbol, self.align, self.radius = symbol, align, radius
        self.end_symbol = end_symbol
        self.selected, self.has_border, self.font = selected, border, font
        self.state, self.hovered = state, False
        self.bind('<Configure>', lambda e: self.draw())
        self.bind('<Enter>', lambda e: self._hover(True))
        self.bind('<Leave>', lambda e: self._hover(False))
        self.bind('<Button-1>', lambda e: self.focus_set())
        self.bind('<ButtonRelease-1>', self._release)
        self.bind('<Return>', lambda e: self.invoke())
        self.bind('<space>', lambda e: self.invoke())
        self.bind('<FocusIn>', lambda e: self.draw())
        self.bind('<FocusOut>', lambda e: self.draw())

    def _hover(self, active):
        self.hovered = active
        self.draw()

    def _release(self, event):
        if 0 <= event.x < self.winfo_width() and 0 <= event.y < self.winfo_height():
            self.invoke()

    def invoke(self):
        if self.state != 'disabled' and self.command:
            return self.command()

    def configure(self, cnf=None, **kwargs):
        options = dict(cnf or {}, **kwargs)
        for name in ('text', 'command', 'selected', 'state', 'symbol'):
            if name in options:
                setattr(self, name, options.pop(name))
        if options:
            super().configure(**options)
        if hasattr(self, 'primary'):
            self.draw()

    config = configure

    def cget(self, key):
        if key in ('text', 'state') and hasattr(self, key):
            return getattr(self, key)
        return super().cget(key)

    def draw(self):
        self.delete('all')
        w, h = self.winfo_width(), self.winfo_height()
        if self.primary:
            fill = '#eeeeee' if not self.hovered else '#ffffff'
            fg, edge = '#080808', '#eeeeee'
        else:
            fill = '#181818' if self.selected or self.hovered else '#101010'
            fg, edge = TEXT, '#303030' if self.selected else BORDER
            if not self.has_border and not self.selected and not self.hovered:
                fill = self.cget('bg')
                edge = fill
        if self.state == 'disabled':
            fill, fg, edge = ('#232323', '#858585', '#2b2b2b') if self.primary else ('#101010', '#66686d', '#202020')
        if self.focus_get() == self and self.state != 'disabled':
            edge = '#777777'
        if self.symbol == 'close' and self.hovered:
            fill, edge, fg = '#c42b1c', '#c42b1c', '#ffffff'
        rounded(self, 1, 1, w-1, h-1, self.radius, fill=fill, outline=edge, width=1)
        if self.align == 'left':
            tx, anchor = (54 if self.symbol else 16), 'w'
            if self.symbol:
                icon(self, self.symbol, 27, h/2, color=fg)
        elif self.symbol and not self.text:
            tx, anchor = w/2, 'center'
            icon(self, self.symbol, w/2, h/2, size=18, color=fg)
        else:
            from tkinter.font import Font
            length = Font(self, font=self.font).measure(self.text)
            tx, anchor = w/2 + (12 if self.symbol else 0), 'center'
            if self.symbol:
                icon(self, self.symbol, w/2-length/2-13, h/2, size=19, color=fg)
        self.create_text(tx, h/2, text=self.text, fill=fg, font=self.font, anchor=anchor)
        if self.end_symbol:
            icon(self, self.end_symbol, w-24, h/2, size=18, color=fg)


class AutoScrollbar(ttk.Scrollbar):
    def set(self, first, last):
        if float(first) <= 0 and float(last) >= 1:
            self.grid_remove()
        else:
            self.grid()
        super().set(first, last)


def label(parent, text='', *, variable=None, size=11, color=TEXT, bold=False, **kwargs):
    return tk.Label(parent, text=text, textvariable=variable, bg=parent.cget('bg'), fg=color,
                    font=('Segoe UI', size, 'bold' if bold else 'normal'), bd=0, **kwargs)


def build(app):
    root = app.root
    root.title('RAKBOT')
    root.geometry(f'{min(1500, root.winfo_screenwidth()-70)}x{min(930, root.winfo_screenheight()-100)}')
    root.minsize(1080, 780)
    root.configure(bg=BG)
    from .gui_window import WindowChrome
    app.chrome = WindowChrome(root, app.close)
    style = ttk.Style(root)
    style.theme_use('clam')
    style.configure('.', font=('Segoe UI', 11), foreground=TEXT, background=PANEL)
    style.configure('Onyx.Treeview', background=PANEL, fieldbackground=PANEL, foreground=TEXT,
                    rowheight=48, borderwidth=0, relief='flat', font=('Segoe UI', 13))
    style.layout('Onyx.Treeview', [('Treeview.treearea', {'sticky': 'nswe'})])
    style.configure('Onyx.Treeview.Heading', background='#131313', foreground=MUTED,
                    bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER,
                    relief='flat', padding=(16, 12), font=('Segoe UI', 12))
    style.map('Onyx.Treeview', background=[('selected', '#242424')], foreground=[('selected', '#ffffff')])
    style.map('Onyx.Treeview.Heading', background=[('active', '#1c1c1c')])
    for kind in ('TSpinbox', 'TCombobox', 'TEntry'):
        name = 'Onyx.' + kind
        style.configure(name, foreground=TEXT, fieldbackground=FIELD, background=FIELD,
                        arrowcolor=MUTED, bordercolor=FIELD, lightcolor=FIELD, darkcolor=FIELD,
                        borderwidth=0, padding=(5, 5), arrowsize=12, insertcolor=TEXT)
        style.map(name, fieldbackground=[('disabled', FIELD), ('readonly', FIELD)],
                  foreground=[('disabled', '#737373'), ('readonly', TEXT)],
                  background=[('active', '#191919')], bordercolor=[('focus', '#444444')])
    for direction in ('Vertical', 'Horizontal'):
        name = 'Onyx.' + direction + '.TScrollbar'
        style.configure(name, background='#303030', troughcolor=PANEL, borderwidth=0,
                        bordercolor=PANEL, lightcolor=PANEL, darkcolor=PANEL,
                        arrowcolor=PANEL, arrowsize=9, gripcount=0)
        style.map(name, background=[('active', '#444444'), ('pressed', '#555555')],
                  lightcolor=[('active', PANEL)], darkcolor=[('active', PANEL)])
        style.layout(name, [(direction+'.Scrollbar.trough', {'sticky': 'nswe', 'children': [
            (direction+'.Scrollbar.thumb', {'expand': '1', 'sticky': 'nswe'})]})])
    root.option_add('*TCombobox*Listbox.background', FIELD)
    root.option_add('*TCombobox*Listbox.foreground', TEXT)
    root.option_add('*TCombobox*Listbox.selectBackground', '#303030')

    shell = Panel(root, fill=BG, radius=26, padding=34)
    shell.pack(fill='both', expand=True)
    caption = tk.Frame(root, bg=BG, height=30)
    caption.place(relx=1, x=-16, y=5, anchor='ne')
    app.minimize_button = Button(caption, symbol='minimize', width=36, height=27,
                                 border=False, radius=8, command=app.chrome.minimize)
    app.maximize_button = Button(caption, symbol='maximize', width=36, height=27,
                                 border=False, radius=8, command=app.chrome.toggle_maximize)
    app.close_button = Button(caption, symbol='close', width=36, height=27,
                              border=False, radius=8, command=app.close)
    for button in (app.minimize_button, app.maximize_button, app.close_button):
        button.pack(side='left', padx=2)
    app.chrome.maximize_button = app.maximize_button
    sidebar = tk.Frame(shell.body, bg=BG, width=278)
    sidebar.pack(side='left', fill='y')
    sidebar.pack_propagate(False)
    tk.Frame(shell.body, bg=BORDER, width=1).pack(side='left', fill='y')
    side = tk.Frame(sidebar, bg=BG)
    side.pack(fill='both', expand=True, padx=22, pady=20)
    brand = tk.Frame(side, bg=BG, height=60)
    brand.pack(fill='x')
    brand.pack_propagate(False)
    app.chrome.add_drag_zone(brand)
    logo = label(brand, 'RAKBOT', size=24, bold=True)
    logo.pack(side='top', anchor='w')
    app.status_dot = tk.Canvas(brand, width=12, height=12, bg=BG, highlightthickness=0)
    app.status_dot.place(x=166, y=13)
    app.status_dot.create_oval(1, 1, 11, 11, fill='#626262', outline='', tags='dot')
    def state_changed(*_):
        color = '#22d45b' if app.status.get() == 'Funcionando' else '#eea84b' if '…' in app.status.get() else '#ed6464' if app.status.get() == 'Error' else '#626262'
        app.status_dot.itemconfigure('dot', fill=color)
    app.status.trace_add('write', state_changed)
    label(brand, 'Brainrot scanner', size=11, color=MUTED).pack(anchor='w')

    app.scanner_page = tk.Frame(shell.body, bg=BG)
    app.settings_page = tk.Frame(shell.body, bg=BG)
    def show(page):
        app.scanner_page.pack_forget()
        app.settings_page.pack_forget()
        (app.scanner_page if page == 'scanner' else app.settings_page).pack(
            side='left', fill='both', expand=True, padx=20, pady=20)
        app.nav_scanner.configure(selected=page == 'scanner')
        app.nav_settings.configure(selected=page == 'settings')
    app.show_page = show
    app.nav_scanner = Button(side, text='Scanner', symbol='search', selected=True, height=48,
                             align='left', command=lambda: show('scanner'), font=('Segoe UI Semibold', 12))
    app.nav_scanner.pack(fill='x', pady=(7, 4))
    app.nav_settings = Button(side, text='Ajustes', symbol='gear', align='left', border=False,
                              height=44, command=lambda: show('settings'), font=('Segoe UI', 12))
    app.nav_settings.pack(fill='x')
    tk.Frame(side, bg=BORDER, height=1).pack(fill='x', pady=(17, 14))

    actions = tk.Frame(side, bg=BG)
    actions.pack(side='bottom', fill='x')
    app.start_button = Button(actions, text='Iniciar', symbol='play', primary=True,
                              command=app.start, height=54, font=('Segoe UI Semibold', 12))
    app.start_button.pack(fill='x', pady=(0, 10))
    app.stop_button = Button(actions, text='Detener', symbol='stop', state='disabled',
                             command=app.stop, height=54, font=('Segoe UI Semibold', 11))
    app.stop_button.pack(fill='x')
    label(side, 'Parámetros del scanner', color=MUTED, size=11).pack(anchor='w', pady=(0, 9))
    numbers = tk.Frame(side, bg=BG)
    numbers.pack(fill='x')
    numbers.columnconfigure((0, 1), weight=1, uniform='numbers')
    for n, (title, variable) in enumerate((('Cuentas', app.accounts), ('Workers', app.workers),
                                          ('Grupos', app.groups), ('Cargas', app.inflight))):
        card = Panel(numbers, height=84, padding=9, radius=12)
        card.grid(row=n//2, column=n%2, sticky='ew', padx=(0 if n%2 == 0 else 5, 5 if n%2 == 0 else 0), pady=(0, 10))
        label(card.body, title, size=10, color=MUTED).pack(anchor='w', pady=(0, 4))
        field = Panel(card.body, fill=FIELD, radius=9, padding=3, height=36)
        field.pack(fill='x')
        if n < 2:
            entry = ttk.Spinbox(field.body, textvariable=variable, from_=1, to=MAX_ACCOUNTS if n == 0 else 9999,
                                width=4, style='Onyx.TSpinbox', font=('Segoe UI', 11))
        else:
            entry = ttk.Combobox(field.body, textvariable=variable, values=('Auto', '1', '2', '4', '8', '16', '30'),
                                 width=4, style='Onyx.TCombobox', font=('Segoe UI', 11))
        entry.pack(fill='both', expand=True)
        app.inputs.append(entry)
    label(side, 'Archivos', size=11, color=MUTED).pack(anchor='w', pady=(8, 9))
    for variable, kind in ((app.cookies, 'cookies'), (app.config, 'config')):
        button = Button(side, text=Path(variable.get()).name, symbol='file', end_symbol='folder', align='left', height=44,
                        command=lambda v=variable, k=kind: choose_file(app, v, k))
        button.pack(fill='x', pady=(0, 9))
        variable.trace_add('write', lambda *_, v=variable, b=button: b.configure(text=Path(v.get()).name or 'Elegir archivo'))
        app.inputs.append(button)

    main = app.scanner_page
    main.columnconfigure(0, weight=1)
    main.rowconfigure(3, weight=1, minsize=150)
    profiles=tk.Frame(main,bg=BG)
    profiles.grid(row=0,column=0,sticky='ew',pady=(0,8))
    app.profile_brainrot=Button(profiles,text='Brainrot',selected=True,width=150,height=42,
                                command=lambda:app.select_profile('brainrot'))
    app.profile_brainrot.pack(side='left',padx=(0,10))
    app.profile_eggs=Button(profiles,text='Steal An Egg',width=170,height=42,
                           command=lambda:app.select_profile('eggs'))
    app.profile_eggs.pack(side='left')
    app.profile_joiner=Button(profiles,text='Joiner',width=120,height=42,command=lambda:app.select_profile('joiner'))
    app.profile_joiner.pack(side='left',padx=(10,0))
    app.inputs.extend([app.profile_brainrot,app.profile_eggs,app.profile_joiner])
    stats = tk.Frame(main, bg=BG)
    app.stats_panel=stats
    stats.grid(row=1, column=0, sticky='ew', pady=(0, 16))
    for n, (title, variable, symbol) in enumerate((('Servidores', app.servers, 'server'),
            ('Tiempo', app.elapsed, 'clock'), ('Featured', app.featured, 'star'))):
        stats.columnconfigure(n, weight=1, uniform='stats')
        card = Panel(stats, height=106, radius=16, padding=16)
        card.grid(row=0, column=n, sticky='ew', padx=(0, 16 if n < 2 else 0))
        badge = tk.Canvas(card.body, width=64, height=70, bg=PANEL, bd=0, highlightthickness=0)
        badge.pack(side='left', padx=(0, 15))
        badge.create_oval(1, 3, 63, 65, fill='#1b1b1b', outline='')
        icon(badge, symbol, 32, 34, size=28, color='#b4b8c0')
        stack = tk.Frame(card.body, bg=PANEL)
        stack.pack(side='left', fill='both', expand=True)
        label(stack, title, variable=app.result_label if n==2 else None, size=12, color=MUTED).pack(anchor='w', pady=(1, 0))
        label(stack, variable=variable, size=28, bold=True).pack(anchor='w')
    best = Panel(main, height=62, padding=14, radius=15)
    app.best_panel=best
    best.grid(row=2, column=0, sticky='ew', pady=(0, 36))
    label(best.body,variable=app.cycle_label,size=10,color=MUTED).pack(side='right')
    badge = tk.Canvas(best.body, width=35, height=32, bg=PANEL, bd=0, highlightthickness=0)
    badge.pack(side='left', padx=(0, 12))
    icon(badge, 'trophy', 17, 15, size=23, color='#c5c8ce')
    label(best.body, 'Mejor:', color=MUTED, size=14).pack(side='left', padx=(0, 7))
    label(best.body, variable=app.best, bold=True, size=14).pack(side='left')
    app.joiner_target_panel=Panel(main,height=104,padding=12,radius=15)
    target=app.joiner_target_panel.body
    for column,(title,variable) in enumerate((('Place ID / enlace al juego',app.join_place),
            ('JobID (opcional)',app.join_server),('VIP link (en vez de Place ID)',app.join_vip))):
        target.columnconfigure(column,weight=1,uniform='target')
        label(target,title,size=9,color=MUTED).grid(row=0,column=column,sticky='w',padx=(0,8),pady=(0,3))
        entry=ttk.Entry(target,textvariable=variable,style='Onyx.TEntry',width=10)
        entry.grid(row=1,column=column,sticky='ew',padx=(0,8))
        app.inputs.append(entry)
    label(target,'JobID requiere Place ID. Todas las cuentas entran al mismo servidor; el reconnect es al mismo JobID.',
        size=8,color=MUTED).grid(row=2,column=0,columnspan=3,sticky='w',pady=(5,0))

    featured = Panel(main, radius=16, padding=18)
    featured.grid(row=3, column=0, sticky='nsew', pady=(0, 16))
    header = tk.Frame(featured.body, bg=PANEL)
    header.pack(fill='x', pady=(0, 17))
    controls=tk.Frame(header,bg=PANEL)
    app.result_controls=controls
    controls.pack(side='right',anchor='n')
    app.sort_menu=tk.Menu(root,tearoff=False,bg=FIELD,fg=TEXT,activebackground='#292929',
        activeforeground=TEXT,selectcolor=TEXT,bd=0,font=('Segoe UI',11))
    for title in SORT_OPTIONS:
        app.sort_menu.add_radiobutton(label=title,variable=app.sort_choice,value=title,command=app.set_sort)
    def show_sort():
        try:
            app.sort_menu.tk_popup(app.sort_button.winfo_rootx(),
                app.sort_button.winfo_rooty()+app.sort_button.winfo_height())
        finally:
            app.sort_menu.grab_release()
    app.sort_button=Button(controls,text='Sort by ▾',width=115,height=36,command=show_sort,font=('Segoe UI',10))
    app.sort_button.pack(side='left',padx=(0,8))
    app.clear_featured_button=Button(controls,text='Clear',width=75,height=36,command=app.clear_featured,font=('Segoe UI',10))
    app.clear_featured_button.pack(side='left')
    app.joiner_actions=tk.Frame(header,bg=PANEL)
    app.join_scope_box=ttk.Combobox(app.joiner_actions,textvariable=app.join_scope,values=('Todas las cuentas',),
        style='Onyx.TCombobox',state='readonly',width=14)
    app.join_scope_box.pack(side='left',padx=(0,8))
    Button(app.joiner_actions,text='Stop LoopTp',width=110,height=36,
        command=lambda:app.send_join_command('stoploop'),font=('Segoe UI',10)).pack(side='left')
    titles=tk.Frame(header,bg=PANEL)
    titles.pack(side='left',fill='x',expand=True)
    label(titles, variable=app.table_heading, size=22, bold=True).pack(anchor='w')
    label(titles, variable=app.table_subheading, color=MUTED, size=10,wraplength=420,justify='left').pack(anchor='w')
    footer = tk.Frame(featured.body, bg=PANEL)
    app.result_footer=footer
    footer.pack(side='bottom', fill='x', pady=(14, 0))
    label(footer, variable=app.page_label, color=MUTED, size=10).pack(side='left')
    Button(footer, text='Copiar JobID', symbol='copy', width=185, height=40,
           command=app.copy_job, font=('Segoe UI', 10)).pack(side='right', padx=(14, 0))
    pagination = tk.Frame(footer, bg=PANEL)
    app.pagination=pagination
    pagination.pack(side='right')
    app.previous = Button(pagination, text='‹', width=34, height=38, command=lambda: app.change_page(-1), font=('Segoe UI', 18))
    app.previous.pack(side='left', padx=3)
    app.page_buttons = []
    for i in range(5):
        button = Button(pagination, text=str(i+1), width=34, height=38, font=('Segoe UI', 10))
        button.pack(side='left', padx=3)
        app.page_buttons.append(button)
    app.next = Button(pagination, text='›', width=34, height=38, command=lambda: app.change_page(1), font=('Segoe UI', 18))
    app.next.pack(side='left', padx=3)
    app.joiner_command_bar=tk.Frame(featured.body,bg=PANEL)
    label(app.joiner_command_bar,'Comando',size=9,color=MUTED).pack(side='left',padx=(0,8))
    command=ttk.Entry(app.joiner_command_bar,textvariable=app.join_line,style='Onyx.TEntry')
    command.pack(side='left',fill='x',expand=True)
    command.bind('<Return>',lambda event:app.send_join_command())
    Button(app.joiner_command_bar,text='Enviar',width=100,height=34,command=app.send_join_command,
        font=('Segoe UI',10)).pack(side='right',padx=(8,0))
    table = Panel(featured.body, radius=10, padding=5)
    table.pack(fill='both', expand=True)
    table.body.rowconfigure(0, weight=1)
    table.body.columnconfigure(0, weight=1)
    columns = ('time', 'pet', 'generation', 'job', 'copy')
    app.tree = ttk.Treeview(table.body, columns=columns, show='headings', selectmode='browse',
                            height=5, style='Onyx.Treeview')
    for key, title, width, minimum, stretch in (('time', 'Tiempo', 120, 95, False),
            ('pet', 'Pet / mutación', 290, 180, True), ('generation', 'Income', 150, 100, False),
            ('job', 'JobID', 250, 140, True), ('copy', '', 34, 34, False)):
        app.tree.heading(key, text=title, anchor='w')
        app.tree.column(key, width=width, minwidth=minimum, stretch=stretch, anchor='w')
    app.tree.tag_configure('even', background='#0b0b0b')
    app.tree.tag_configure('odd', background='#0e0e0e')
    scroll = AutoScrollbar(table.body, orient='vertical', command=app.tree.yview, style='Onyx.Vertical.TScrollbar')
    horizontal = AutoScrollbar(table.body, orient='horizontal', command=app.tree.xview, style='Onyx.Horizontal.TScrollbar')
    app.tree.configure(yscrollcommand=scroll.set, xscrollcommand=horizontal.set)
    app.tree.grid(row=0, column=0, sticky='nsew')
    scroll.grid(row=0, column=1, sticky='ns')
    horizontal.grid(row=1, column=0, sticky='ew')
    def copy_cell(event):
        if app.active_profile=='joiner':
            return app.player_menu(event)
        row = app.tree.identify_row(event.y)
        if row and app.tree.identify_column(event.x) == f'#{len(app.tree["columns"])}':
            app.tree.selection_set(row)
            app.copy_job()
            return 'break'
    app.tree.bind('<Button-1>', copy_cell)
    app.tree.bind('<Button-3>',app.player_menu)
    app.player_actions=tk.Menu(root,tearoff=False,bg=FIELD,fg=TEXT,activebackground='#292929',
        activeforeground=TEXT,bd=0,font=('Segoe UI',11))
    app.empty_history = label(table.body, 'Aquí aparecerán los Featured encontrados', color='#686b72', size=11)
    app.empty_history.place(relx=.5, rely=.55, anchor='center')

    log_panel = Panel(main, height=132, radius=16, padding=12)
    log_panel.grid(row=4, column=0, sticky='ew')
    log_head = tk.Frame(log_panel.body, bg=PANEL)
    log_head.pack(fill='x', pady=(0, 8))
    label(log_head, 'Log', bold=True, size=11).pack(side='left')
    label(log_head, variable=app.account_status, color='#777b83', size=8).pack(side='left', padx=15)
    Button(log_head, text='Limpiar', command=app.clear_log, height=24, width=75,
           border=False, font=('Segoe UI', 9)).pack(side='right')
    app.logs_button=Button(log_head,text='Archivos de logs',command=app.open_logs,height=24,width=95,
        border=False,font=('Segoe UI',9))
    app.logs_button.pack(side='right',padx=(4,0))
    app.health_button=Button(log_head,text='Estados',command=app.show_health,height=24,width=70,
        border=False,font=('Segoe UI',9))
    app.health_button.pack(side='right',padx=(4,0))
    log_box = tk.Frame(log_panel.body, bg=PANEL)
    log_box.pack(fill='both', expand=True)
    log_box.columnconfigure(0, weight=1)
    log_box.rowconfigure(0, weight=1)
    app.log = tk.Text(log_box, bg=PANEL, fg='#a5abb5', insertbackground=TEXT,
                      relief='flat', bd=0, highlightthickness=0, padx=4, pady=0,
                      wrap='none', height=4, state='disabled', font=('Consolas', 10))
    log_scroll = AutoScrollbar(log_box, orient='vertical', command=app.log.yview, style='Onyx.Vertical.TScrollbar')
    log_horizontal = AutoScrollbar(log_box, orient='horizontal', command=app.log.xview, style='Onyx.Horizontal.TScrollbar')
    app.log.configure(yscrollcommand=log_scroll.set, xscrollcommand=log_horizontal.set)
    app.log.grid(row=0, column=0, sticky='nsew')
    log_scroll.grid(row=0, column=1, sticky='ns')
    log_horizontal.grid(row=1, column=0, sticky='ew')
    build_settings(app)
    show('scanner')


def choose_file(app, variable, kind):
    path = filedialog.askopenfilename(parent=app.root, title='Archivo de cuentas' if kind == 'cookies' else 'Configuración',
        initialdir=app.base, filetypes=[('Archivos de texto', '*.txt'), ('JSON', '*.json'), ('Todos los archivos', '*.*')])
    if path:
        variable.set(path)
        if kind == 'config':
            app.load_settings()


def build_settings(app):
    page = app.settings_page
    label(page, 'Ajustes', size=24, bold=True).pack(anchor='w', pady=(5, 5))
    label(page, 'Los parámetros de la izquierda se aplican en el próximo arranque.', color=MUTED).pack(anchor='w', pady=(0, 24))
    panel = Panel(page, height=390, padding=24)
    panel.pack(fill='x')
    for title, variable, kind in (('Archivo de cuentas', app.cookies, 'cookies'), ('Configuración / Featured', app.config, 'config')):
        label(panel.body, title, color=MUTED, size=10).pack(anchor='w', pady=(0, 8))
        line = tk.Frame(panel.body, bg=PANEL)
        line.pack(fill='x', pady=(0, 22))
        entry = ttk.Entry(line, textvariable=variable, style='Onyx.TEntry')
        entry.pack(side='left', fill='x', expand=True, ipady=7)
        button = Button(line, text='Explorar', symbol='folder', width=110, height=42,
                        command=lambda v=variable, k=kind: choose_file(app, v, k))
        button.pack(side='right', padx=(12, 0))
        app.inputs.extend([entry, button])
    label(panel.body, 'Workers — sesiones simultáneas. «Auto» elige los grupos de Python y el número de cargas.',
          color=MUTED, size=10, wraplength=650, justify='left').pack(anchor='w', pady=(0, 8))
    label(panel.body, 'Brainrot: scan completo cada 30 segundos y chequeo de la base al entrar un jugador nuevo.\n'
          'Steal An Egg: JobID persistente, filtro de eggs y rescan tras el reset y el fin de la noche.\n'
          'Ambos modos cambian de servidor tras 5 reconnects fallidos seguidos.\n'
          'La lista Featured se edita en config.txt; guardar los ajustes la conserva íntegra.',
          color=MUTED, size=10, wraplength=650, justify='left').pack(anchor='w', pady=(0, 20))
    buttons = tk.Frame(panel.body, bg=PANEL)
    buttons.pack(fill='x')
    app.load_button = Button(buttons, text='Cargar', command=app.load_settings, width=135)
    app.load_button.pack(side='left', padx=(0, 12))
    app.save_button = Button(buttons, text='Guardar ajustes', command=app.save_settings, primary=True, width=220)
    app.save_button.pack(side='left')
    app.inputs.extend([app.load_button, app.save_button])
