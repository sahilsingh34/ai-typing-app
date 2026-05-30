"""
KeyWise AI — Sentence Fixer
Triggered by Alt+Shift+S. Reads selected text via clipboard,
sends it to Groq for grammar/spelling/clarity fix, and pastes it back.
Works in any application.
"""
import time
import threading

import keyboard
import pyperclip


class SentenceFixer:
    def __init__(self, config, groq_client):
        self.config = config
        self.groq = groq_client
        self._lock = threading.Lock()   # Prevent concurrent fixes
        self.is_simulating = False      # Track simulated key events

    def trigger(self, hook=None):
        """
        Entry point — called in a background thread.
        1. Copy selection (Ctrl+C)
        2. Send to Groq
        3. Paste back (Ctrl+V)
        4. Restore original clipboard
        """
        if not self._lock.acquire(blocking=False):
            return  # Already running

        try:
            self._fix(hook)
        finally:
            self._lock.release()

    # ── Core fix workflow ───────────────────────────────────────────────────────
    def _fix(self, hook=None):
        import win32gui
        # ① Save original clipboard
        try:
            original_clip = pyperclip.paste()
        except Exception:
            original_clip = ''

        # Record starting state
        start_keys = hook.keystroke_count if hook else 0
        start_hwnd = None
        try:
            start_hwnd = win32gui.GetForegroundWindow()
        except Exception:
            pass

        try:
            # ② Clear clipboard so we can detect if Ctrl+C worked
            pyperclip.copy('')
            time.sleep(0.05)

            # ③ Copy currently selected text
            try:
                self.is_simulating = True
                keyboard.send('ctrl+c')
                time.sleep(0.30)   # Give OS time to populate clipboard
            finally:
                self.is_simulating = False

            try:
                selected = pyperclip.paste()
            except Exception:
                selected = ''

            if not selected or not selected.strip():
                return  # Nothing selected

            # ④ Fix with Groq
            fixed = self.groq.fix_sentence(selected)

            # Safety check: if user typed something or switched window during the API call, abort!
            if hook and hook.keystroke_count != start_keys:
                return
            if start_hwnd:
                try:
                    if win32gui.GetForegroundWindow() != start_hwnd:
                        return
                except Exception:
                    pass

            if not fixed or fixed == selected:
                return  # No change

            # ⑤ Paste the fixed text back
            try:
                self.is_simulating = True
                pyperclip.copy(fixed)
                time.sleep(0.05)
                keyboard.send('ctrl+v')
                time.sleep(0.15)
            finally:
                self.is_simulating = False

        except Exception:
            pass

        finally:
            # ⑥ Restore original clipboard after a short delay
            time.sleep(0.40)
            try:
                pyperclip.copy(original_clip)
            except Exception:
                pass

