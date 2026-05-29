"""
KeyWise AI — Auto-Correct Engine
Silently corrects typed words whenever Space is pressed.

Fast-typing safety:
  After Groq returns, we WAIT for a natural pause in the user's typing
  (200 ms of no keystrokes) before sending any arrow keys.  This prevents
  the user's own keystrokes from corrupting the navigation window.

  Additional guards:
  • Skip if user typed >25 chars since trigger (too far back to navigate)
  • Skip if Groq took >5 s (user has moved on)
  • Skip if no pause detected within 800 ms (user is typing continuously)
"""
import threading
import time

import keyboard


class AutoCorrect:
    def __init__(self, config, groq_client):
        self.config = config
        self.groq   = groq_client

        self._is_applying: bool  = False
        self._position:    int   = 0
        self._last_key_time: float = 0.0   # Timestamp of most recent keystroke
        self._backspace_count: int = 0
        self._trigger_id:  int   = 0
        self._lock = threading.Lock()
        self._apply_lock = threading.Lock()

    # ── Properties ─────────────────────────────────────────────────────────────
    @property
    def is_applying(self) -> bool:
        return self._is_applying

    @property
    def backspace_count(self) -> int:
        with self._lock:
            return self._backspace_count

    # ── Called by KeyboardHook for every user keystroke ─────────────────────────
    def notify_new_char(self):
        """Signal that the user typed 1 character."""
        with self._lock:
            self._position    += 1
            self._last_key_time = time.time()

    def notify_backspace(self):
        """Signal that the user pressed Backspace."""
        with self._lock:
            self._position      = max(0, self._position - 1)
            self._last_key_time = time.time()
            self._backspace_count += 1

    def _snapshot_position(self) -> int:
        with self._lock:
            return self._position

    def _ms_since_last_key(self) -> float:
        """Milliseconds elapsed since the last user keystroke."""
        with self._lock:
            return (time.time() - self._last_key_time) * 1000.0

    # ── Trigger ─────────────────────────────────────────────────────────────────
    def trigger(self, word: str, context: str):
        """
        Called (in a background thread) after each Space.
        Corrects the last typed word if misspelled.
        """
        if not self.config.get('enabled') or not self.config.get('autocorrect_enabled'):
            return
        if not word or len(word) < 3:
            return

        with self._lock:
            self._trigger_id += 1
            tid = self._trigger_id

        pos_at_trigger = self._snapshot_position()
        trigger_time   = time.time()
        backspaces_at_trigger = self.backspace_count

        # ── Query Groq (200–1 500 ms) ──────────────────────────────────────────
        corrected = self.groq.correct_word(word, context)
        if not corrected:
            return

        # Abort if state changed or a newer autocorrect trigger was launched
        if self.backspace_count != backspaces_at_trigger or self._trigger_id != tid:
            return

        corrected = self._match_case(word, corrected)
        if corrected == word:
            return  # Already correct

        # ── Guard 1: user typed too many chars or backspaced — navigating is risky ──
        pos_now     = self._snapshot_position()
        chars_after = pos_now - pos_at_trigger
        if chars_after > 25 or chars_after < 0:
            return

        # ── Guard 2: Groq was too slow — user has moved on ─────────────────────
        if time.time() - trigger_time > 5.0:
            return

        # ── Guard 3: Wait for a micro natural typing PAUSE (≥ 40 ms of silence) ─────
        PAUSE_MS   = 40    # Required silence before we navigate (instant, invisible delay)
        MAX_WAIT_S = 1.0   # Give up after 1.0 s if user keeps typing
        deadline   = time.time() + MAX_WAIT_S
        while time.time() < deadline:
            # Abort immediately if state changed
            if self.backspace_count != backspaces_at_trigger or self._trigger_id != tid:
                return
            if self._ms_since_last_key() >= PAUSE_MS:
                break           # User paused — safe to navigate
            time.sleep(0.025)   # Check every 25 ms
        else:
            return  # User kept typing for 800 ms — skip to avoid corruption

        # Re-check after the pause
        if self.backspace_count != backspaces_at_trigger or self._trigger_id != tid:
            return
        pos_now     = self._snapshot_position()
        chars_after = pos_now - pos_at_trigger
        if chars_after > 25 or chars_after < 0:
            return

        # Safely serialize correction application to prevent overlapping keyboard inputs
        with self._apply_lock:
            if self._trigger_id != tid or self.backspace_count != backspaces_at_trigger:
                return
            self._apply(word, corrected, chars_after)

    # ── Internal ────────────────────────────────────────────────────────────────
    @staticmethod
    def _match_case(original: str, corrected: str) -> str:
        """Match the capitalisation pattern of the original word."""
        if not original or not corrected:
            return corrected
        if original.isupper():
            return corrected.upper()
        if original[0].isupper():
            return corrected[0].upper() + corrected[1:].lower()
        return corrected.lower()

    def _apply(self, original: str, corrected: str, chars_after: int):
        """
        Navigate back to the misspelled word, select it, type the correction,
        then restore the cursor to where the user was.
        """
        self._is_applying = True
        try:
            # 3ms delay is extremely fast (under 70ms total) and 100% stable with continuous Shift-holding
            delay = 0.003

            # Step 1: Move LEFT past chars_after + space + original word
            total_back = chars_after + 1 + len(original)
            for _ in range(total_back):
                keyboard.send('left')
                if delay > 0:
                    time.sleep(delay)

            # Step 2: Select the original word by HOLDING Shift down continuously.
            # This is 100% stable because we don't spam shift-down/shift-up events,
            # which prevents Windows and Chrome from dropping the Shift modifier state.
            keyboard.press('shift')
            time.sleep(delay)
            for _ in range(len(original)):
                keyboard.send('right')
                if delay > 0:
                    time.sleep(delay)
            keyboard.release('shift')
            time.sleep(delay)

            # Step 3: Type corrected word (SendInput — no clipboard)
            keyboard.write(corrected, delay=delay)
            time.sleep(0.02)

            # Step 4: Move RIGHT back to original cursor position
            forward = 1 + chars_after
            for _ in range(forward):
                keyboard.send('right')
                if delay > 0:
                    time.sleep(delay)

        except Exception:
            pass
        finally:
            self._is_applying = False
