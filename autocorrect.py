"""
KeyWise AI — Auto-Correct Engine
Silently corrects typed words whenever Space is pressed.
Designed for fast typists: corrections apply even if you've
continued typing — navigates back to the word, fixes it, returns.

Each word gets a unique generation counter. The keyboard hook
increments a global char counter; the autocorrect reads it at
apply-time to know exactly how far back to navigate.
"""
import threading
import time

import keyboard
import pyperclip


class AutoCorrect:
    def __init__(self, config, groq_client):
        self.config = config
        self.groq = groq_client

        self._is_applying: bool = False
        # Global position counter: incremented for every char/space/enter
        # typed after any autocorrect trigger.
        self._position: int = 0
        self._lock = threading.Lock()

    # ── Properties ─────────────────────────────────────────────────────────────
    @property
    def is_applying(self) -> bool:
        return self._is_applying

    # ── Called by KeyboardHook for every user keystroke ─────────────────────────
    def notify_new_char(self):
        """Signal that the user typed 1 character (letter, space, etc.)."""
        with self._lock:
            self._position += 1

    def notify_backspace(self):
        """Signal that the user pressed backspace."""
        with self._lock:
            self._position = max(0, self._position - 1)

    def _snapshot_position(self) -> int:
        """Take a snapshot of current position."""
        with self._lock:
            return self._position

    def trigger(self, word: str, context: str):
        """
        Entry point: called (in a background thread) after each Space.
        Checks if the last word needs correction and applies it silently.
        Works even if user has continued typing (navigates back to fix).
        """
        if not self.config.get('enabled') or not self.config.get('autocorrect_enabled'):
            return
        if not word or len(word) < 3:
            return

        # Snapshot position at time of trigger (right after space)
        pos_at_trigger = self._snapshot_position()

        # Query Groq (takes ~200-1500ms)
        corrected = self.groq.correct_word(word, context)

        if not corrected:
            return  # Nothing to fix

        # Preserve original capitalisation before comparing
        corrected = self._match_case(word, corrected)

        # Now check if anything actually changed (case-sensitive)
        if corrected == word:
            return  # Word is already correct (including case)

        # Calculate how many chars user typed SINCE this trigger
        pos_now = self._snapshot_position()
        chars_after = pos_now - pos_at_trigger

        self._apply(word, corrected, chars_after)

    # ── Internal ───────────────────────────────────────────────────────────────
    @staticmethod
    def _match_case(original: str, corrected: str) -> str:
        """Match the capitalisation pattern of the original word."""
        if not original or not corrected:
            return corrected
        # ALL CAPS (e.g. "ILLUSION", "NASA")
        if original.isupper():
            return corrected.upper()
        # Title Case (e.g. "Hello", "London")
        if original[0].isupper():
            return corrected[0].upper() + corrected[1:].lower()
        # Lowercase — return as-is from LLM
        return corrected.lower()

    def _apply(self, original: str, corrected: str, chars_after: int):
        """
        Navigate back to the misspelled word, select it, replace it,
        then navigate forward to restore cursor position.
        """
        self._is_applying = True
        try:
            delay = 0.004  # ms per keystroke

            # Total chars to go back:
            # chars_after (everything typed since space)
            # + 1 (the space itself)
            # + len(original) (the misspelled word)
            total_back = chars_after + 1 + len(original)

            # Step 1: Move LEFT to start of the misspelled word
            for _ in range(total_back):
                keyboard.send('left')
                time.sleep(delay)

            # Step 2: Select the word (Shift+Right × len)
            for _ in range(len(original)):
                keyboard.send('shift+right')
                time.sleep(delay)

            # Step 3: Replace selection with corrected word
            _clipboard_type(corrected)
            time.sleep(0.05)

            # Step 4: Move RIGHT back to where user was typing
            # Forward: 1 (space) + chars_after
            forward = 1 + chars_after
            for _ in range(forward):
                keyboard.send('right')
                time.sleep(delay)

        except Exception:
            pass
        finally:
            self._is_applying = False


# ── Clipboard-based text injection ─────────────────────────────────────────────
def _clipboard_type(text: str):
    try:
        prev = pyperclip.paste()
    except Exception:
        prev = ''

    try:
        pyperclip.copy(text)
        time.sleep(0.04)
        keyboard.send('ctrl+v')
        time.sleep(0.08)
    finally:
        threading.Timer(0.5, _restore_clipboard, args=(prev,)).start()


def _restore_clipboard(text: str):
    try:
        pyperclip.copy(text)
    except Exception:
        pass
