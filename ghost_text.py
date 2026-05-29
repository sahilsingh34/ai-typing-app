"""
KeyWise AI — Ghost Text Overlay
Displays the next-word suggestion as a low-opacity, floating label
positioned right next to the text cursor.  The suggestion is NOT
inserted into the target application until the user presses Alt.

Thread-safe: all public methods can be called from any thread.
The tkinter event loop runs on a dedicated non-daemon thread so
it is never killed abruptly (avoids Tcl_AsyncDelete crashes).
"""
import ctypes
import ctypes.wintypes
import queue
import threading
import tkinter as tk


# ── Win32: locate the text caret on screen ────────────────────────────────────
class _GUITHREADINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize",        ctypes.wintypes.DWORD),
        ("flags",         ctypes.wintypes.DWORD),
        ("hwndActive",    ctypes.wintypes.HWND),
        ("hwndFocus",     ctypes.wintypes.HWND),
        ("hwndCapture",   ctypes.wintypes.HWND),
        ("hwndMenuOwner", ctypes.wintypes.HWND),
        ("hwndMoveSize",  ctypes.wintypes.HWND),
        ("hwndCaret",     ctypes.wintypes.HWND),
        ("rcCaret",       ctypes.wintypes.RECT),
    ]


def get_caret_screen_pos() -> tuple[int, int] | None:
    """
    Return the screen (x, y) immediately to the right of the active
    text caret, or None if the caret cannot be located (e.g. browser).
    """
    info = _GUITHREADINFO()
    info.cbSize = ctypes.sizeof(_GUITHREADINFO)
    try:
        ok = ctypes.windll.user32.GetGUIThreadInfo(0, ctypes.byref(info))
        if ok and info.hwndCaret:
            pt = ctypes.wintypes.POINT(
                info.rcCaret.right,
                info.rcCaret.top,
            )
            ctypes.windll.user32.ClientToScreen(info.hwndCaret, ctypes.byref(pt))
            return int(pt.x), int(pt.y)
    except Exception:
        pass
    return None


# ── Ghost text overlay ─────────────────────────────────────────────────────────
class GhostTextOverlay:
    """
    A borderless, semi-transparent window that floats next to the cursor
    showing the predicted next word.

    Interaction contract (enforced by KeyboardHook):
      • Alt pressed  → call get_current_word(), type it, call hide()
      • Escape / any key → call hide()
    """

    _ALPHA    = 0.45          # Opacity: 45 % feels like 'ghost' text
    _FG       = '#b0b8cc'     # Soft grey-blue — legible but clearly secondary
    _BG       = '#1a1a2e'     # Very dark background; almost invisible in dark apps
    _FONT     = ('Segoe UI', 11)
    _OFFSET_X = 6             # px right of caret right-edge
    _OFFSET_Y = 0             # px relative to caret top

    def __init__(self) -> None:
        self._q: queue.Queue = queue.Queue()
        self._alive = True
        self._word  = ''
        self._lock  = threading.Lock()
        # Non-daemon so the thread is shut down gracefully via shutdown()
        self._t = threading.Thread(target=self._tk_main,
                                   name='KeyWise-GhostText',
                                   daemon=False)
        self._t.start()

    # ── Public (thread-safe) ──────────────────────────────────────────────────
    def show(self, word: str, x: int, y: int) -> None:
        """Show ghost text at screen position (x, y)."""
        with self._lock:
            self._word = word
        self._q.put(('show', word,
                     x + self._OFFSET_X,
                     y + self._OFFSET_Y))

    def hide(self) -> None:
        """Hide the overlay without typing anything."""
        with self._lock:
            self._word = ''
        self._q.put(('hide',))

    def get_current_word(self) -> str:
        """Return the word currently shown ('' if hidden)."""
        with self._lock:
            return self._word

    def shutdown(self) -> None:
        """Cleanly stop the tkinter thread. Call once on app exit."""
        self._alive = False
        self._q.put(('quit',))

    # ── Private: tkinter thread ───────────────────────────────────────────────
    def _tk_main(self) -> None:
        root = tk.Tk()
        root.overrideredirect(True)         # No title bar / borders
        root.attributes('-topmost', True)   # Always on top
        root.attributes('-alpha', self._ALPHA)
        root.configure(bg=self._BG)
        root.withdraw()                     # Start hidden

        lbl = tk.Label(
            root,
            text='',
            font=self._FONT,
            fg=self._FG,
            bg=self._BG,
            padx=6,
            pady=3,
        )
        lbl.pack()

        def poll() -> None:
            try:
                while True:
                    msg = self._q.get_nowait()
                    cmd = msg[0]
                    if cmd == 'show':
                        _, word, x, y = msg
                        lbl.config(text=word)
                        root.geometry(f'+{x}+{y}')
                        root.deiconify()
                        root.lift()
                        root.update_idletasks()
                    elif cmd == 'hide':
                        root.withdraw()
                    elif cmd == 'quit':
                        root.destroy()
                        return
            except queue.Empty:
                pass
            if self._alive:
                root.after(40, poll)        # Poll every 40 ms

        root.after(40, poll)
        root.mainloop()
