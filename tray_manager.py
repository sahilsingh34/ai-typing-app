"""
KeyWise AI — System Tray + Settings Window
Dark-themed settings UI built with tkinter.
"""
import threading
import tkinter as tk

from PIL import Image, ImageDraw, ImageFont
import pystray

from setup_autostart import setup_autostart, remove_autostart


# ── Icon generation ─────────────────────────────────────────────────────────────
def _make_tray_icon(size: int = 64) -> Image.Image:
    """Create a purple pill-shaped icon with 'KW' text."""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = max(2, size // 16)
    # Gradient-like purple circle
    d.ellipse([pad, pad, size - pad, size - pad], fill='#7C3AED')
    # Inner highlight
    hi = pad + size // 8
    d.ellipse([hi, hi, size - hi, size - hi], fill='#9F67FF', outline=None)
    d.ellipse([pad, pad, size - pad, size - pad], outline='#5B21B6', width=max(1, size // 20))
    # Draw "K" letter
    lw = max(1, size // 10)
    x1, x2 = size // 3, size * 2 // 3
    y1, y2 = size // 4, size * 3 // 4
    mid = size // 2
    d.line([(x1, y1), (x1, y2)], fill='white', width=lw)
    d.line([(x1, mid), (x2, y1)], fill='white', width=lw)
    d.line([(x1, mid), (x2, y2)], fill='white', width=lw)
    return img


# ── Palette ─────────────────────────────────────────────────────────────────────
_C = {
    'bg':      '#0d0d1a',
    'surface': '#16162a',
    'card':    '#1e1e35',
    'border':  '#2a2a4a',
    'accent':  '#7C3AED',
    'accent2': '#a78bfa',
    'text':    '#e2e8f0',
    'muted':   '#8892a4',
    'success': '#10b981',
    'error':   '#f87171',
    'warn':    '#fbbf24',
}


# ── Settings Window ──────────────────────────────────────────────────────────────
class SettingsWindow:
    def __init__(self, config, groq_client):
        self.config = config
        self.groq = groq_client
        self._root: tk.Tk | None = None

    def show(self):
        """Open (or focus) the settings window."""
        if self._root and self._is_alive():
            self._root.lift()
            self._root.focus_force()
            return
        threading.Thread(target=self._build, daemon=True).start()

    def _is_alive(self) -> bool:
        try:
            return bool(self._root and self._root.winfo_exists())
        except Exception:
            return False

    # ── Build UI ──────────────────────────────────────────────────────────────
    def _build(self):
        root = tk.Tk()
        self._root = root
        root.title('KeyWise AI  —  Settings')
        root.geometry('500x640')
        root.resizable(False, False)
        root.configure(bg=_C['bg'])
        root.attributes('-topmost', True)

        # ── Fonts ──
        F_TITLE  = ('Segoe UI', 17, 'bold')
        F_LABEL  = ('Segoe UI', 10)
        F_SMALL  = ('Segoe UI', 9)
        F_BOLD   = ('Segoe UI', 10, 'bold')
        F_SECTION = ('Segoe UI', 8, 'bold')

        # ─────────────────────── Header ─────────────────────────────────────
        header = tk.Frame(root, bg=_C['accent'], height=72)
        header.pack(fill='x')
        header.pack_propagate(False)

        hbox = tk.Frame(header, bg=_C['accent'])
        hbox.pack(expand=True)
        tk.Label(hbox, text='⌨', font=('Segoe UI', 22), fg='white',
                 bg=_C['accent']).pack(side='left', padx=(0, 8), pady=18)
        tk.Label(hbox, text='KeyWise AI', font=F_TITLE, fg='white',
                 bg=_C['accent']).pack(side='left', pady=18)

        # ─────────────────────── Bottom bar (always visible) ─────────────
        # Pack from the bottom FIRST so it's never pushed off-screen
        bottom = tk.Frame(root, bg=_C['bg'], padx=28, pady=12)
        bottom.pack(side='bottom', fill='x')

        status_var = tk.StringVar(value='')
        status_lbl = tk.Label(bottom, textvariable=status_var,
                              font=('Segoe UI', 9), fg=_C['success'],
                              bg=_C['bg'], wraplength=440, justify='left')
        status_lbl.pack(anchor='w', pady=(0, 6))

        def set_status(msg: str, colour: str = _C['success']):
            root.after(0, lambda: (
                status_var.set(msg),
                status_lbl.config(fg=colour),
            ))

        # ───────────────────────── Scrollable body ───────────────────────
        body = tk.Frame(root, bg=_C['bg'], padx=28, pady=12)
        body.pack(fill='both', expand=True)

        # Helper: section heading
        def section(txt: str, top: int = 14):
            tk.Frame(body, bg=_C['bg'], height=top).pack()
            row = tk.Frame(body, bg=_C['bg'])
            row.pack(fill='x')
            tk.Label(row, text=txt.upper(), font=F_SECTION,
                     fg=_C['accent2'], bg=_C['bg']).pack(side='left')
            tk.Frame(body, bg=_C['border'], height=1).pack(fill='x', pady=(3, 0))

        # Helper: card frame
        def card(pady: int = 6) -> tk.Frame:
            f = tk.Frame(body, bg=_C['card'], padx=14, pady=10,
                         highlightthickness=1, highlightbackground=_C['border'])
            f.pack(fill='x', pady=(pady, 0))
            return f

        # Helper: labelled entry
        def entry_row(parent, label: str, var: tk.StringVar,
                      show: str = '') -> tk.Entry:
            row = tk.Frame(parent, bg=_C['card'])
            row.pack(fill='x', pady=3)
            tk.Label(row, text=label, font=F_LABEL, fg=_C['muted'],
                     bg=_C['card'], width=14, anchor='w').pack(side='left')
            e = tk.Entry(row, textvariable=var, font=F_LABEL,
                         bg=_C['surface'], fg=_C['text'],
                         insertbackground=_C['text'], relief='flat',
                         bd=0, highlightthickness=1,
                         highlightbackground=_C['border'],
                         highlightcolor=_C['accent'], show=show)
            e.pack(side='left', fill='x', expand=True, ipady=7, padx=(6, 0))
            return e

        # Helper: check row
        def check_row(parent, label: str, var: tk.BooleanVar, detail: str = ''):
            row = tk.Frame(parent, bg=_C['card'])
            row.pack(fill='x', pady=2)
            cb = tk.Checkbutton(row, text=label, variable=var,
                                font=F_BOLD, fg=_C['text'], bg=_C['card'],
                                selectcolor=_C['surface'],
                                activebackground=_C['card'],
                                activeforeground=_C['text'],
                                cursor='hand2')
            cb.pack(anchor='w')
            if detail:
                tk.Label(row, text=detail, font=F_SMALL, fg=_C['muted'],
                         bg=_C['card']).pack(anchor='w', padx=24)

        # ──────────────── Section 1 : API Key ────────────────────────────────
        section('🔑  Groq API Key')
        k_card = card()

        api_var = tk.StringVar(value=self.config.get('groq_api_key', ''))
        api_entry = entry_row(k_card, 'API Key:', api_var, show='●')

        show_var = tk.BooleanVar(value=False)
        def _toggle_show():
            api_entry.config(show='' if show_var.get() else '●')
        show_row = tk.Frame(k_card, bg=_C['card'])
        show_row.pack(anchor='w')
        tk.Checkbutton(show_row, text='Show key', variable=show_var,
                       command=_toggle_show, font=F_SMALL, fg=_C['muted'],
                       bg=_C['card'], selectcolor=_C['surface'],
                       activebackground=_C['card'], cursor='hand2').pack(side='left')
        tk.Label(show_row,
                 text='  Get your free key at console.groq.com',
                 font=F_SMALL, fg=_C['muted'], bg=_C['card']).pack(side='left')

        # ──────────────── Section 2 : Model ──────────────────────────────────
        section('🤖  AI Model')
        m_card = card(4)
        m_row = tk.Frame(m_card, bg=_C['card'])
        m_row.pack(fill='x', pady=3)
        tk.Label(m_row, text='Model:', font=F_LABEL, fg=_C['muted'],
                 bg=_C['card'], width=14, anchor='w').pack(side='left')

        model_var = tk.StringVar(value=self.config.get('model', 'llama-3.1-8b-instant'))
        models = [
            'llama-3.1-8b-instant',
            'llama-3.3-70b-versatile',
            'gemma2-9b-it',
            'mixtral-8x7b-32768',
        ]
        opt = tk.OptionMenu(m_row, model_var, *models)
        opt.config(
            bg=_C['surface'], fg=_C['text'], font=F_LABEL,
            activebackground=_C['accent'], activeforeground='white',
            highlightthickness=1, highlightbackground=_C['border'],
            relief='flat', bd=0, padx=8, pady=6,
            indicatoron=True, cursor='hand2',
        )
        opt['menu'].config(
            bg=_C['surface'], fg=_C['text'], font=F_LABEL,
            activebackground=_C['accent'], activeforeground='white',
            relief='flat', bd=0,
        )
        opt.pack(side='left', padx=(6, 0), fill='x', expand=True)
        tk.Label(m_card,
                 text='  llama-3.1-8b-instant is fastest •  llama-3.3-70b for best quality',
                 font=F_SMALL, fg=_C['muted'], bg=_C['card']).pack(anchor='w', pady=(4, 0))

        # ──────────────── Section 3 : Features ───────────────────────────────
        section('⚡  Features')
        f_card = card(4)
        ac_var = tk.BooleanVar(value=self.config.get('autocorrect_enabled', True))
        sf_var = tk.BooleanVar(value=self.config.get('sentence_fix_enabled', True))
        as_var = tk.BooleanVar(value=self.config.get('autostart', True))

        check_row(f_card, '✅  Auto-correct words on Space', ac_var,
                  'Silently fixes spelling after each word — all languages')
        check_row(f_card, '✅  Fix sentence on Alt + Shift + S', sf_var,
                  'Select any text → press Alt+Shift+S → AI rewrites it')
        check_row(f_card, '🚀  Start KeyWise AI with Windows', as_var,
                  'Added to startup registry (current user only)')

        # ─────────────────────── Buttons in bottom bar ───────────────────────
        btn_frame = tk.Frame(bottom, bg=_C['bg'])
        btn_frame.pack(fill='x')

        def mk_btn(text: str, cmd, bg: str, width: int = 13) -> tk.Button:
            b = tk.Button(btn_frame, text=text, command=cmd,
                          bg=bg, fg='white', font=('Segoe UI', 10, 'bold'),
                          relief='flat', bd=0, pady=9, padx=14,
                          cursor='hand2', width=width,
                          activebackground=_C['accent2'], activeforeground='white')
            b.pack(side='left', padx=(0, 10))
            return b

        def _test_api():
            key = api_var.get().strip()
            if not key:
                set_status('❌  Enter an API key first.', _C['error'])
                return
            set_status('⏳  Testing connection…', _C['warn'])

            def _run():
                # Temporarily set key for test
                old = self.config.get('groq_api_key')
                self.config.set('groq_api_key', key)
                self.groq.refresh()
                ok, msg = self.groq.test_connection()
                self.config.set('groq_api_key', old)
                self.groq.refresh()
                colour = _C['success'] if ok else _C['error']
                icon   = '✅' if ok else '❌'
                set_status(f'{icon}  {msg}', colour)

            threading.Thread(target=_run, daemon=True).start()

        def _save():
            self.config.set('groq_api_key',         api_var.get().strip())
            self.config.set('model',                 model_var.get())
            self.config.set('autocorrect_enabled',   ac_var.get())
            self.config.set('sentence_fix_enabled',  sf_var.get())
            self.config.set('autostart',             as_var.get())
            self.groq.refresh()

            try:
                if as_var.get():
                    setup_autostart()
                else:
                    remove_autostart()
            except Exception:
                pass

            set_status('✅  Settings saved!', _C['success'])
            root.after(1200, root.destroy)


        mk_btn('🔌  Test API',     _test_api, bg='#065f46', width=13)
        mk_btn('💾  Save & Close', _save,     bg=_C['accent'], width=15)

        # Footer
        tk.Label(bottom,
                 text='KeyWise AI  •  Powered by Groq  •  No cloud account needed',
                 font=('Segoe UI', 8), fg=_C['border'], bg=_C['bg']).pack(pady=(8, 0))



        root.mainloop()


# ── Tray Manager ─────────────────────────────────────────────────────────────────
class TrayManager:
    def __init__(self, config, groq_client, keyboard_hook):
        self.config = config
        self.groq = groq_client
        self.keyboard_hook = keyboard_hook
        self._settings = SettingsWindow(config, groq_client)
        self._icon: pystray.Icon | None = None

    def open_settings(self):
        self._settings.show()

    # ── Menu ──────────────────────────────────────────────────────────────────
    def _build_menu(self):
        enabled = self.config.get('enabled', True)
        toggle_label = ('✅  Autocorrect ON  (click to disable)'
                        if enabled else
                        '❌  Autocorrect OFF (click to enable)')
        return pystray.Menu(
            pystray.MenuItem(toggle_label, self._toggle_enabled),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('⚙️  Settings', self._open_settings_action),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('❌  Quit KeyWise AI', self._quit),
        )

    def _toggle_enabled(self, icon, item):
        self.config.set('enabled', not self.config.get('enabled', True))
        icon.menu = self._build_menu()
        icon.update_menu()

    def _open_settings_action(self, icon, item):
        threading.Thread(target=self.open_settings, daemon=True).start()

    def _quit(self, icon, item):
        self.keyboard_hook.stop()
        icon.stop()

    # ── Run ───────────────────────────────────────────────────────────────────
    def run(self):
        img = _make_tray_icon(64)
        self._icon = pystray.Icon(
            name='KeyWiseAI',
            icon=img,
            title='KeyWise AI  —  Right-click for options',
            menu=self._build_menu(),
        )
        self._icon.run()
