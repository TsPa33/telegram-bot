"""Clipboard and context-menu support for Tkinter, including Cyrillic layouts.

Use a custom binding tag ahead of Tk class bindings so that physical
Ctrl+C/X/V/A work in non-Latin layouts without triggering native actions twice.
Apply to Toplevel dialogs automatically when their widgets receive focus.
"""
from __future__ import annotations

import os
import tkinter as tk

_TAG = 'CarPotClipboard'
_WINDOWS_KEYS = {65: 'all', 67: 'copy', 86: 'paste', 88: 'cut'}
_SYMBOL_KEYS = {
    'a': 'all', 'c': 'copy', 'v': 'paste', 'x': 'cut',
    'cyrillic_ef': 'all', 'cyrillic_es': 'copy',
    'cyrillic_em': 'paste', 'cyrillic_che': 'cut',
}
_SUPPORTED = ('Entry', 'TEntry', 'Text', 'TCombobox', 'Treeview')


class ClipboardSupport:
    def __init__(self, root: tk.Misc) -> None:
        self.root = root
        self.menu = tk.Menu(root, tearoff=False)
        root.bind_class(_TAG, '<KeyPress>', self._key, add='+')
        root.bind_all('<FocusIn>', self._on_focus, add='+')
        root.bind_all('<Button-3>', self._right_click, add='+')
        root.after_idle(lambda: self._attach_existing(root))

    def _attach_existing(self, parent: tk.Misc) -> None:
        for widget in parent.winfo_children():
            self._attach(widget)
            self._attach_existing(widget)

    def _attach(self, widget: tk.Misc) -> None:
        if widget.winfo_class() not in _SUPPORTED:
            return
        tags = widget.bindtags()
        if _TAG not in tags:
            widget.bindtags((tags[0], _TAG, *tags[1:]))

    def _on_focus(self, event: tk.Event) -> None:
        self._attach(event.widget)

    @staticmethod
    def _writable(widget: tk.Misc) -> bool:
        try:
            return widget.winfo_class() != 'Treeview' and str(widget.cget('state')) == 'normal'
        except tk.TclError:
            return False

    @staticmethod
    def _selection(widget: tk.Misc) -> str:
        try:
            kind = widget.winfo_class()
            if kind == 'Treeview':
                columns = [str(v) for v in widget['columns']]
                lines = []
                for item in widget.selection():
                    values = widget.item(item, 'values')
                    if values:
                        lines.append('\t'.join(str(v) for v in values[:len(columns)]))
                return '\n'.join(lines)
            if kind == 'Text':
                return widget.get('sel.first', 'sel.last')
            return widget.get()[int(widget.index('sel.first')):int(widget.index('sel.last'))]
        except (tk.TclError, ValueError):
            return ''

    def _copy(self, widget: tk.Misc) -> None:
        value = self._selection(widget)
        if value:
            self.root.clipboard_clear()
            self.root.clipboard_append(value)

    def _delete_selection(self, widget: tk.Misc) -> None:
        try:
            widget.delete('sel.first', 'sel.last')
        except tk.TclError:
            pass

    def _execute(self, widget: tk.Misc, action: str) -> None:
        kind = widget.winfo_class()
        if action == 'copy':
            self._copy(widget)
            return
        if action == 'all':
            if kind == 'Treeview':
                widget.selection_set(widget.get_children(''))
            elif kind == 'Text':
                widget.tag_add('sel', '1.0', 'end-1c')
            else:
                widget.selection_range(0, 'end')
                widget.icursor('end')
            return
        if not self._writable(widget):
            return
        if action == 'cut':
            text = self._selection(widget)
            if text:
                self._copy(widget)
                self._delete_selection(widget)
        elif action == 'paste':
            try:
                value = self.root.clipboard_get()
            except tk.TclError:
                return
            if value:
                self._delete_selection(widget)
                widget.insert('insert', value)

    def _key(self, event: tk.Event) -> str | None:
        widget = event.widget
        if widget.winfo_class() not in _SUPPORTED:
            return None
        control = bool(event.state & 0x0004)
        shift = bool(event.state & 0x0001)
        symbol = str(event.keysym).lower()
        if control:
            if symbol == 'insert':
                action = 'copy'
            else:
                action = _SYMBOL_KEYS.get(symbol)
                if not action and os.name == 'nt':
                    action = _WINDOWS_KEYS.get(event.keycode)
        elif shift and symbol == 'insert':
            action = 'paste'
        elif shift and symbol == 'delete':
            action = 'cut'
        else:
            return None
        if not action:
            return None
        self._execute(widget, action)
        return 'break'

    def _right_click(self, event: tk.Event) -> None:
        widget = event.widget
        if widget.winfo_class() not in _SUPPORTED:
            return
        self._attach(widget)
        if widget.winfo_class() == 'Treeview':
            row = widget.identify_row(event.y)
            if row and row not in widget.selection():
                widget.selection_set(row)
        widget.focus_set()
        menu = self.menu
        menu.delete(0, 'end')
        writable = self._writable(widget)
        selected = bool(self._selection(widget))
        for label, action, enabled in (
            ('Вирізати', 'cut', selected and writable),
            ('Копіювати', 'copy', selected),
            ('Вставити', 'paste', writable),
            ('Виділити все', 'all', True),
        ):
            menu.add_command(label=label, state='normal' if enabled else 'disabled',
                             command=lambda a=action, w=widget: self._execute(w, a))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()


def install_clipboard_support(root: tk.Misc) -> ClipboardSupport:
    """Install once on the main window and apply to future Toplevel dialogs."""
    return ClipboardSupport(root)
