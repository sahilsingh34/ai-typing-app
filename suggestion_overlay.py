"""
KeyWise AI — Suggestion Overlay
A small, borderless, always-on-top floating window that shows
ghost text (next-word prediction) near the cursor position.
Press Tab to accept the suggestion.
"""
import threading
import tkinter as tk
import ctypes
import ctypes.wintypes


# ── Win32: get caret / cursor position ──────────────────────────────────────────
class _GUITHREADINFO(ctypes.Structure):
    _fields_ = [
        ('cbSize',        ctypes.wintypes.DWORD),
        ('flags',         ctypes.wintypes.DWORD),
        ('hwndActive',    ctypes.wintypes.HWND),
        ('hwndFocus',     ctypes.wintypes.HWND),
        ('hwndCapture',   ctypes.wintypes.HWND),
        ('hwndMenuOwner', ctypes.wintypes.HWND),
        ('hwndMoveSize',  ctypes.wintypes.HWND),
        ('hwndCaret',     ctypes.wintypes.HWND),
        ('rcCaret',       ctypes.wintypes.RECT),
    ]


class _POINT(ctypes.Structure):
    _fields_ = [('x', ctypes.c_long), ('y', ctypes.c_long)]


def _get_caret_screen_pos() -> tuple[int, int] | None:
    """Try to get the caret (text cursor) screen position via Win32 API."""
    try:
        gti = _GUITHREADINFO()
        gti.cbSize = ctypes.sizeof(gti)
        if ctypes.windll.user32.GetGUIThreadInfo(0, ctypes.byref(gti)):
            if gti.hwndCaret:
                pt = _POINT(gti.rcCaret.left, gti.rcCaret.bottom)
                ctypes.windll.user32.ClientToScreen(
                    gti.hwndCaret, ctypes.byref(pt)
                )
                return pt.x, pt.y
    except Exception:
        pass
    return None


def _get_mouse_pos() -> tuple[int, int]:
    """Fallback: use mouse cursor position."""
    try:
        pt = _POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
        return pt.x, pt.y
    except Exception:
        return 100, 100


# ── Suggestion Overlay ──────────────────────────────────────────────────────────
class SuggestionOverlay:
    """
    Floating ghost-text window showing next-word prediction.
    Runs a hidden tkinter root in a background thread.
    """

    def __init__(self):
        self._root: tk.Tk | None = None
        self._label: tk.Label | None = None
        self._current_text: str = ''
        self._visible: bool = False
        self._ready = threading.Event()

        # Start tkinter loop in a daemon thread
        t = threading.Thread(target=self._run_tk, daemon=True)
        t.start()
        self._ready.wait(timeout=3)   # Wait for tk to be ready

    # ── Tkinter thread ──────────────────────────────────────────────────────────
    def _run_tk(self):
        root = tk.Tk()
        self._root = root

        root.withdraw()                         # Start hidden
        root.overrideredirect(True)              # No title bar / border
        root.attributes('-topmost', True)        # Always on top
        root.attributes('-alpha', 0.85)          # Slight transparency
        root.configure(bg='#1e1e2e')

        # Try to make click-through (Windows-only)
        try:
            hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
            GWL_EXSTYLE = -20
            WS_EX_LAYERED = 0x80000
            WS_EX_TRANSPARENT = 0x20
            WS_EX_TOOLWINDOW = 0x80
            WS_EX_NOACTIVATE = 0x08000000
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            style |= WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
        except Exception:
            pass

        self._label = tk.Label(
            root,
            text='',
            font=('Consolas', 11),
            fg='#6b7280',              # Grey ghost text
            bg='#1e1e2e',
            padx=8, pady=4,
            anchor='w',
        )
        self._label.pack()

        self._ready.set()
        root.mainloop()

    # ── Public API (called from other threads) ──────────────────────────────────
    @property
    def current_suggestion(self) -> str:
        return self._current_text

    @property
    def is_visible(self) -> bool:
        return self._visible

    def show(self, text: str):
        """Display ghost-text suggestion near the caret."""
        if not self._root or not text.strip():
            return
        self._current_text = text.strip()
        self._root.after(0, self._do_show, self._current_text)

    def hide(self):
        """Hide the overlay."""
        if not self._root:
            return
        self._current_text = ''
        self._visible = False
        self._root.after(0, self._do_hide)

    def _do_show(self, text: str):
        try:
            self._label.config(text=text)

            # Position near caret
            pos = _get_caret_screen_pos()
            if pos is None:
                pos = _get_mouse_pos()

            x, y = pos
            # Offset: a bit to the right and below caret
            self._root.geometry(f'+{x + 4}+{y + 4}')
            self._root.deiconify()
            self._visible = True
        except Exception:
            pass

    def _do_hide(self):
        try:
            self._root.withdraw()
            self._visible = False
        except Exception:
            pass
