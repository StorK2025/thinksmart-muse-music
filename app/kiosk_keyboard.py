"""Small native touch keyboard for the single WebKitGTK kiosk window.

Works without a compositor input-panel protocol. Text goes directly to WebKit's
input method, including cross-origin frames; input values are never inspected,
stored or logged. Existing hardware input is forwarded to the original context.
"""

import gi

gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('WebKit2', '4.1')
from gi.repository import Gdk, GLib, Gtk, WebKit2


class TouchInputContext(WebKit2.InputMethodContext):
    def __init__(self, original, on_focus):
        super().__init__()
        self.original = original
        self.on_focus = on_focus
        if original is not None:
            for name in ('committed', 'delete-surrounding', 'preedit-started',
                         'preedit-changed', 'preedit-finished'):
                original.connect(name, self._forward_signal, name)
        self.connect('notify::input-purpose', self._sync_properties)
        self.connect('notify::input-hints', self._sync_properties)

    def _forward_signal(self, _original, *args):
        self.emit(args[-1], *args[:-1])

    def _sync_properties(self, *_args):
        if self.original is not None:
            self.original.set_input_purpose(self.get_input_purpose())
            self.original.set_input_hints(self.get_input_hints())

    def do_filter_key_event(self, event):
        return self.original.filter_key_event(event) if self.original else False

    def do_get_preedit(self):
        return self.original.get_preedit() if self.original else ('', [], 0)

    def do_notify_focus_in(self):
        if self.original:
            self.original.notify_focus_in()
        self.on_focus(True)

    def do_notify_focus_out(self):
        if self.original:
            self.original.notify_focus_out()
        self.on_focus(False)

    def do_notify_cursor_area(self, x, y, width, height):
        if self.original:
            self.original.notify_cursor_area(x, y, width, height)

    def do_notify_surrounding(self, text, length, cursor_index, selection_index):
        if self.original:
            self.original.notify_surrounding(text, length, cursor_index, selection_index)

    def do_reset(self):
        if self.original:
            self.original.reset()

    def do_set_enable_preedit(self, enabled):
        if self.original:
            self.original.set_enable_preedit(enabled)


class TouchKeyboard:
    def __init__(self, view):
        self.view = view
        self.focused = False
        self.uppercase = False
        self.symbols = False
        self._focus_timer = 0
        self.letter_keys = []
        self.action_buttons = {}
        self.widget = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        self.widget.set_name('thinksmart-keyboard')
        self.widget.set_border_width(8)
        self.widget.set_no_show_all(True)
        self.widget.set_hexpand(True)

        self.toggle_button = self._button('键盘', lambda: self.show())
        self.toggle_button.set_name('thinksmart-keyboard-toggle')
        self.toggle_button.set_halign(Gtk.Align.END)
        self.toggle_button.set_valign(Gtk.Align.CENTER)
        self.toggle_button.set_margin_end(12)
        self.toggle_button.set_size_request(74, 42)
        self.toggle_button.set_no_show_all(True)

        self._css = Gtk.CssProvider()
        self._css.load_from_data(b'''
          #thinksmart-keyboard { background: #14212d; color: #f4f7fb; }
          #thinksmart-keyboard button, #thinksmart-keyboard-toggle {
            background-image: none; background-color: #293b4c; color: #f4f7fb;
            border: 1px solid #425567; border-radius: 8px; box-shadow: none;
            font-family: "Noto Sans CJK SC", sans-serif; font-size: 19px;
            padding: 2px 8px; min-height: 40px;
          }
          #thinksmart-keyboard button:active { background-color: #356a8b; }
          #thinksmart-keyboard button.suggested-action { background-color: #146c99; }
          #thinksmart-keyboard-toggle { font-size: 15px; background-color: #24455e; }
        ''')
        Gtk.StyleContext.add_provider_for_screen(
            view.get_screen(), self._css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self._build_keys()
        self.context = TouchInputContext(view.get_input_method_context(), self._focus_changed)
        view.set_input_method_context(self.context)
        view.connect('load-changed', self._load_changed)
        view.connect('notify::uri', lambda *_args: self._sync_toggle())
        self._sync_toggle()

    @staticmethod
    def _button(label, callback):
        button = Gtk.Button.new_with_label(label)
        button.set_can_focus(False)
        button.set_focus_on_click(False)
        button.connect('clicked', lambda _button: callback())
        return button

    def _row(self):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        row.set_homogeneous(True)
        self.widget.pack_start(row, False, False, 0)
        return row

    def _build_keys(self):
        self.letter_keys = []
        self.action_buttons = {}
        for child in self.widget.get_children():
            self.widget.remove(child)
            child.destroy()

        rows = (['1234567890', '!@#$%^&*()', '[]{}<>/\\|~', '+-=_:;,.?\'"']
                if self.symbols else ['1234567890', 'qwertyuiop', 'asdfghjkl@', 'zxcvbnm._-'])
        for characters in rows:
            row = self._row()
            for char in characters:
                label = char.upper() if self.uppercase and char.isalpha() else char
                button = self._button(label, lambda c=char: self.insert(c))
                row.pack_start(button, True, True, 0)
                if char.isalpha():
                    self.letter_keys.append((button, char))

        row = self._row()
        actions = [
            ('symbols', '字母' if self.symbols else '符号', self.toggle_symbols),
            ('shift', '小写' if self.uppercase else '大写', self.toggle_case),
            ('backspace', '退格', lambda: self.send_key(Gdk.KEY_BackSpace)),
            ('space', '空格', lambda: self.insert(' ')),
            ('left', '←', lambda: self.send_key(Gdk.KEY_Left)),
            ('right', '→', lambda: self.send_key(Gdk.KEY_Right)),
            ('tab', '下一栏', lambda: self.send_key(Gdk.KEY_Tab)),
            ('enter', '回车', lambda: self.send_key(Gdk.KEY_Return)),
            ('hide', '收起', self.hide),
        ]
        for name, label, callback in actions:
            button = self._button(label, callback)
            if name == 'enter':
                button.get_style_context().add_class('suggested-action')
            row.pack_start(button, True, True, 0)
            self.action_buttons[name] = button
        for child in self.widget.get_children():
            child.show_all()

    def insert(self, text):
        if self.focused:
            self.context.emit('committed', text.upper() if self.uppercase else text)

    def send_key(self, keyval):
        if not self.focused:
            return
        seat = self.view.get_display().get_default_seat()
        device = seat.get_keyboard() if seat else None
        keymap = Gdk.Keymap.get_for_display(self.view.get_display())
        found, entries = keymap.get_entries_for_keyval(keyval)
        for event_type in (Gdk.EventType.KEY_PRESS, Gdk.EventType.KEY_RELEASE):
            event = Gdk.Event.new(event_type)
            event.window = self.view.get_window()
            event.send_event = True
            event.time = Gdk.CURRENT_TIME
            event.keyval = keyval
            event.state = Gdk.ModifierType(0)
            event.group = entries[0].group if found else 0
            event.hardware_keycode = entries[0].keycode if found else 0
            if device:
                event.set_device(device)
            self.view.event(event)

    def toggle_case(self):
        self.uppercase = not self.uppercase
        for button, char in self.letter_keys:
            button.set_label(char.upper() if self.uppercase else char)
        self.action_buttons['shift'].set_label('小写' if self.uppercase else '大写')

    def toggle_symbols(self):
        self.symbols = not self.symbols
        self._build_keys()

    def _focus_changed(self, focused):
        self.focused = focused
        if self._focus_timer:
            GLib.source_remove(self._focus_timer)
        # Debounce focus changes between fields so the page does not jump.
        self._focus_timer = GLib.timeout_add(120, self._apply_focus)

    def _apply_focus(self):
        self._focus_timer = 0
        if self.focused:
            self.show()
        else:
            self.hide()
        return False

    def _sync_toggle(self):
        uri = self.view.get_uri() or ''
        is_web_page = uri.startswith(('https://', 'http://'))
        is_music = uri.startswith(('https://music.163.com/', 'https://www.music.163.com/'))
        self.toggle_button.set_visible(is_web_page and not is_music and not self.widget.get_visible())

    def show(self):
        self.widget.show()
        self._sync_toggle()

    def hide(self):
        self.widget.hide()
        self._sync_toggle()

    def _load_changed(self, _view, event):
        if event == WebKit2.LoadEvent.STARTED:
            self.focused = False
            if self._focus_timer:
                GLib.source_remove(self._focus_timer)
                self._focus_timer = 0
            self.hide()
