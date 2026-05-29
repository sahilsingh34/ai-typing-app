"""
KeyWise AI — Ghost Text Overlay
Displays the next-word suggestion as inline ghost text — faded gray
text floating right at the cursor position with a fully transparent
background so it looks exactly like macOS Notes inline completion.

The suggestion is NOT inserted into the target application until
the user presses Alt to accept it.

Thread-safe: public methods can be called from any thread.
The tkinter event loop runs on a dedicated non-daemon thread.
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


_uia = None


def get_uia_caret_pos() -> tuple[int, int, int] | None:
    """
    Fallback using Windows UI Automation (UIA) to locate the caret position
    in applications like Chrome, VS Code, Edge, and other Electron/Chromium apps
    where GetGUIThreadInfo fails to return a caret HWND.
    """
    global _uia
    try:
        if _uia is None:
            import win32com.client
            import pythoncom
            pythoncom.CoInitialize()
            _uia = win32com.client.Dispatch("UIAutomation.CUIAutomation")

        focused = _uia.GetFocusedElement()
        if not focused:
            return None

        # Try UIA TextPattern
        try:
            pattern = focused.GetCurrentPattern(10014)  # UIA_TextPatternId
            if pattern:
                sel = pattern.GetSelection()
                if sel and sel.Length > 0:
                    rng = sel.GetElement(0)  # IUIAutomationTextRange
                    rects = rng.GetBoundingRectangles()

                    # Caret is a degenerate range, GetBoundingRectangles() returns empty.
                    # We clone and expand it to TextUnit_Character (0) to get the bounding box.
                    if not rects or len(rects) == 0:
                        clone = rng.Clone()
                        clone.ExpandToEnclosingUnit(0)  # TextUnit_Character
                        rects = clone.GetBoundingRectangles()

                        if rects and len(rects) >= 4:
                            left = rects[0]
                            top = rects[1]
                            width = rects[2]
                            height = rects[3]

                            # Determine precise caret position (left edge vs right edge)
                            # by comparing endpoints: Start of caret to Start of character.
                            relation = rng.CompareEndpoints(0, clone, 0)
                            x_pos = left + width if relation > 0 else left

                            # DPI scaling
                            dpi = 96
                            try:
                                hwnd = focused.CurrentNativeWindowHandle
                                if hwnd:
                                    d = ctypes.windll.user32.GetDpiForWindow(hwnd)
                                    if d and d > 0:
                                        dpi = d
                            except Exception:
                                try:
                                    d = ctypes.windll.user32.GetDpiForSystem()
                                    if d and d > 0:
                                        dpi = d
                                except Exception:
                                    pass

                            font_px = height * 0.75
                            pt_size = max(8, min(24, round(font_px * 72 / dpi)))

                            return int(x_pos), int(top), pt_size
        except Exception:
            pass
    except Exception:
        pass
    return None


def get_caret_screen_pos() -> tuple[int, int, int] | None:
    """
    Return (x, y, pt_size) where x/y is the screen position just right of
    the active text caret, and pt_size is the correct font point size derived
    from the caret height and the window's actual DPI.
    Returns None if the caret cannot be located.
    """
    info = _GUITHREADINFO()
    info.cbSize = ctypes.sizeof(_GUITHREADINFO)
    try:
        ok = ctypes.windll.user32.GetGUIThreadInfo(0, ctypes.byref(info))
        if ok and info.hwndCaret:
            caret_h = info.rcCaret.bottom - info.rcCaret.top

            # Get the actual DPI of the window that owns the caret.
            # This is essential for correct pt calculation on scaled displays.
            dpi = 96
            try:
                d = ctypes.windll.user32.GetDpiForWindow(info.hwndCaret)
                if d and d > 0:
                    dpi = d
            except Exception:
                try:
                    d = ctypes.windll.user32.GetDpiForSystem()
                    if d and d > 0:
                        dpi = d
                except Exception:
                    pass

            # caret_h is the LINE height (includes line-spacing).
            # Actual font cap-height is typically ~0.75× the line height.
            # Formula: pt = (px × 0.75) × 72 / dpi
            font_px  = caret_h * 0.75   # font portion of line height
            pt_size  = max(8, min(24, round(font_px * 72 / dpi)))

            pt = ctypes.wintypes.POINT(
                info.rcCaret.right,
                info.rcCaret.top,
            )
            ctypes.windll.user32.ClientToScreen(info.hwndCaret, ctypes.byref(pt))
            return int(pt.x), int(pt.y), pt_size
    except Exception:
        pass

    # Fallback to UI Automation for Chrome, Edge, VS Code, Discord, etc.
    return get_uia_caret_pos()


# ── Ghost text overlay ─────────────────────────────────────────────────────────
class GhostTextOverlay:
    """
    A borderless, background-transparent window that renders only faded
    gray text right next to the cursor — mimicking macOS inline completion.

    Key trick:  wm_attributes('-transparentcolor', _TRANSP_KEY) makes every
    pixel of colour _TRANSP_KEY completely see-through, so the window
    background vanishes and only the text is visible.

    Interaction contract (enforced by KeyboardHook):
      • Alt        → call get_current_word(), type it, call hide()
      • Esc / key  → call hide()
    """

    # Colour used as the "invisible" background
    _TRANSP_KEY = '#010101'   # Near-black; won't clash with real app content

    # Ghost text style — light gray like Gmail Smart Compose
    _FG         = '#9a9a9a'
    _FONT_FACE  = 'Segoe UI'

    # Position: sit flush right after caret, no extra gap
    _OFFSET_X   = 0
    _OFFSET_Y   = 0

    def __init__(self) -> None:
        self._q: queue.Queue = queue.Queue()
        self._alive = True
        self._word  = ''
        self._lock  = threading.Lock()
        self._t = threading.Thread(target=self._tk_main,
                                   name='KeyWise-GhostText',
                                   daemon=False)
        self._t.start()

    # ── Public API (thread-safe) ──────────────────────────────────────────────
    def show(self, word: str, x: int, y: int, caret_h: int = 16) -> None:
        """Show ghost text at screen position (x, y) with given caret height."""
        with self._lock:
            self._word = word
        self._q.put(('show', word,
                     x + self._OFFSET_X,
                     y + self._OFFSET_Y,
                     caret_h))

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
        root.overrideredirect(True)             # No title bar / border
        root.attributes('-topmost', True)       # Float above all windows
        root.attributes('-alpha', 1.0)          # Full alpha — transparency via key colour
        root.configure(bg=self._TRANSP_KEY)
        root.wm_attributes('-transparentcolor', self._TRANSP_KEY)  # Magic: bg → invisible
        root.withdraw()                         # Start hidden

        lbl = tk.Label(
            root,
            text='',
            font=(self._FONT_FACE, 11),
            fg=self._FG,
            bg=self._TRANSP_KEY,
            padx=0,          # No extra horizontal padding
            pady=0,          # No extra vertical padding
            bd=0,
        )
        lbl.pack(padx=0, pady=0)

        def poll() -> None:
            try:
                while True:
                    msg = self._q.get_nowait()
                    cmd = msg[0]

                    if cmd == 'show':
                        _, word, x, y, pt_size = msg
                        # Use the DPI-corrected pt_size directly
                        lbl.config(text=word, font=(self._FONT_FACE, pt_size))
                        root.update_idletasks()   # Measure new size first
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
                root.after(30, poll)

        root.after(30, poll)
        root.mainloop()
