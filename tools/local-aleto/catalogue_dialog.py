"""Tkinter interface for an explicit Oracle modification selection."""
import queue
import sqlite3
import threading
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from catalogue_client import includes_year


class CatalogueDialog:
    def __init__(self, owner):
        self.owner = owner
        self.client = owner.catalogue_client
        self.window = tk.Toplevel(owner.root)
        self.window.title('Каталог CarPot · вибір модифікації')
        self.window.transient(owner.root)
        self.window.grab_set()
        self.window.columnconfigure(1, weight=1)
        self.window.minsize(570, 255)
        self.messages = queue.Queue()
        self.kind = tk.StringVar(value='passenger')
        self.offline = tk.BooleanVar(value=False)
        self.name = tk.StringVar(value=owner.brand.get())
        self.year = tk.StringVar(value=owner.year.get())
        self.status = tk.StringVar(value='Завантажте марки з Warehouse Staging')
        self.boxes = {}
        self.rows = {}
        self.cursors = {}
        self.buttons = []
        ttk.Label(self.window, text='Тип').grid(row=0, column=0, sticky='w', padx=8, pady=6)
        self.kind_box = ttk.Combobox(self.window, textvariable=self.kind, state='readonly',
                                     values=('passenger', 'commercial'))
        self.kind_box.grid(row=0, column=1, sticky='ew', padx=8)
        self.kind_box.bind('<<ComboboxSelected>>', lambda _: self.clear('make'))
        ttk.Label(self.window, text='Пошук марки').grid(row=1, column=0, sticky='w', padx=8)
        self.name_entry = ttk.Entry(self.window, textvariable=self.name)
        self.name_entry.grid(row=1, column=1, sticky='ew', padx=8)
        self.name.trace_add('write', lambda *_: self.clear('make'))
        for index, (level, heading) in enumerate((('make', 'Марка'), ('model', 'Модель'),
                                                   ('modification', 'Модифікація')), 2):
            index = 5 if level == 'modification' else index
            ttk.Label(self.window, text=heading).grid(row=index, column=0, sticky='w', padx=8, pady=5)
            box = ttk.Combobox(self.window, state='readonly')
            box.grid(row=index, column=1, sticky='ew', padx=8)
            box.bind('<<ComboboxSelected>>', lambda _, key=level: self.changed(key))
            self.boxes[level] = box
            self.rows[level] = []
            self.cursors[level] = 0
            button = ttk.Button(self.window, text='Завантажити / далі', command=lambda key=level: self.load(key))
            button.grid(row=index, column=2, padx=8)
            self.buttons.append(button)
        ttk.Label(self.window, text='Рік').grid(row=4, column=0, sticky='w', padx=8)
        self.year_entry = ttk.Entry(self.window, textvariable=self.year)
        self.year_entry.grid(row=4, column=1, sticky='ew', padx=8)
        self.year.trace_add('write', lambda *_: self.clear('modification'))
        cache_switch = ttk.Checkbutton(self.window, text='З локального кешу', variable=self.offline,
                                       command=lambda: self.clear('make'))
        cache_switch.grid(row=4, column=2, padx=8)
        self.buttons.append(cache_switch)
        ttk.Label(self.window, textvariable=self.status, wraplength=550).grid(row=6, columnspan=3, padx=8, pady=8)
        confirm = ttk.Button(self.window, text='Вибрати модифікацію', command=self.confirm)
        confirm.grid(row=7, columnspan=3, pady=6)
        self.buttons.append(confirm)
        self.window.after(100, self.poll)

    def clear(self, level):
        levels = tuple(self.boxes)
        for key in levels[levels.index(level):]:
            self.rows[key] = []
            self.cursors[key] = 0
            self.boxes[key].configure(values=[])
            self.boxes[key].set('')

    def changed(self, level):
        levels = tuple(self.boxes)
        index = levels.index(level)
        if index + 1 < len(levels):
            self.clear(levels[index + 1])

    def selected(self, level):
        index = self.boxes[level].current()
        return self.rows[level][index] if index >= 0 else None

    def load(self, level):
        if self.cursors[level] is None:
            self.status.set('Далі сторінок немає')
            return
        parent_level = {'model': 'make', 'modification': 'model'}.get(level)
        parent = self.selected(parent_level) if parent_level else None
        if parent_level and not parent:
            self.status.set('Спочатку виберіть попереднє поле')
            return
        year_text = self.year.get().strip()
        if year_text and (not year_text.isdigit() or not 1886 <= int(year_text) <= 2100):
            self.status.set('Укажіть коректний рік')
            return
        credentials = None
        offline = self.offline.get()
        if not offline and not self.client.connected:
            email = simpledialog.askstring('Warehouse Staging', 'Електронна пошта', parent=self.window)
            if not email:
                return
            password = simpledialog.askstring('Warehouse Staging', 'Пароль', show='*', parent=self.window)
            if not password:
                return
            credentials = email, password
        params = dict(kind=self.kind.get(), name=self.name.get().strip(), parent=parent['id'] if parent else None,
                      after=self.cursors[level])
        year = int(year_text) if year_text else None
        self.status.set('Завантаження…')
        self.toggle(True)

        def retrieve():
            try:
                if credentials:
                    self.client.login(*credentials)
                rows, cursor, cache_stamp = self.client.page(level, offline=offline, **params)
                if level == 'modification':
                    rows = [row for row in rows if includes_year(row.get('construction_interval'), year)]
                self.messages.put((level, rows, cursor, None, cache_stamp))
            except (OSError, ValueError, KeyError, TypeError, AttributeError, sqlite3.Error) as error:
                self.messages.put((level, [], None, str(error), None))

        threading.Thread(target=retrieve, daemon=True).start()

    def toggle(self, busy):
        for widget in (*self.buttons, self.name_entry, self.year_entry):
            widget.configure(state='disabled' if busy else 'normal')
        for widget in (self.kind_box, *self.boxes.values()):
            widget.configure(state='disabled' if busy else 'readonly')

    def poll(self):
        try:
            level, rows, cursor, error, cache_stamp = self.messages.get_nowait()
        except queue.Empty:
            pass
        else:
            self.toggle(False)
            if error:
                self.status.set(error)
            else:
                self.rows[level].extend(rows)
                self.cursors[level] = cursor
                self.boxes[level].configure(values=[f'{row["name"]} · #{row["id"]}' for row in self.rows[level]])
                origin = f'Кеш від {cache_stamp[:10]} · ' if cache_stamp else ''
                self.status.set(origin + f'Додано записів: {len(rows)}' + (' · є наступна сторінка' if cursor else ''))
        self.window.after(100, self.poll)

    def confirm(self):
        maker, model, modification = map(self.selected, ('make', 'model', 'modification'))
        if not all((maker, model, modification)):
            messagebox.showinfo('CarPot', 'Виберіть марку, модель і модифікацію', parent=self.window)
            return
        text = self.year.get().strip()
        if text and (not text.isdigit() or not 1886 <= int(text) <= 2100):
            self.status.set('Укажіть коректний рік')
            return
        self.owner.apply_catalogue(self.kind.get(), maker, model, modification, text)
        self.window.destroy()
