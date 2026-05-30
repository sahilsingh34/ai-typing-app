"""
KeyWise AI — Auto-Correct Engine
Silently corrects typed words whenever Space is pressed.

Word replacement strategy (BACKSPACE-BASED — no arrow keys):
  After Space is pressed, the cursor is right after the space.
  We simply:
    1. Backspace over the space + the misspelled word
    2. Type the corrected word + space
  This is the same approach used by keyboard.add_abbreviation()
  and is fundamentally reliable because it never navigates away
  from the current cursor position.

Fast-typing safety:
  After Groq returns, we WAIT for a natural pause in the user's typing
  (40 ms of no keystrokes) before sending any backspaces.  This prevents
  the user's own keystrokes from corrupting the replacement.

  Additional guards:
  • Skip if user typed any extra chars since the triggering Space
  • Skip if Groq took >5 s (user has moved on)
  • Skip if no pause detected within 1.0 s (user is typing continuously)
"""
import threading
import time

import keyboard


class AutoCorrect:
    def __init__(self, config, groq_client):
        self.config = config
        self.groq   = groq_client
        self.habits = None                 # Set dynamically in main.py

        self._is_applying: bool  = False
        self._last_key_time: float = 0.0   # Timestamp of most recent keystroke
        self._trigger_id:  int   = 0       # Monotonic counter to detect stale triggers
        self._chars_since_trigger: int = 0 # Chars typed AFTER the triggering Space
        self._lock = threading.Lock()
        self._apply_lock = threading.Lock()

    # ── Properties ─────────────────────────────────────────────────────────────
    @property
    def is_applying(self) -> bool:
        return self._is_applying

    # ── Called by KeyboardHook for every user keystroke ─────────────────────────
    def notify_keystroke(self):
        """Signal that the user typed a character AFTER the last Space trigger."""
        with self._lock:
            self._chars_since_trigger += 1
            self._last_key_time = time.time()

    def _reset_char_counter(self):
        """Reset the chars-since-trigger counter (called on each new Space)."""
        with self._lock:
            self._chars_since_trigger = 0

    def _get_chars_since_trigger(self) -> int:
        with self._lock:
            return self._chars_since_trigger

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

        # Reset char counter — any chars typed from now are "after trigger"
        self._reset_char_counter()
        trigger_time = time.time()

        # ── Step 1: Check if this is a locally learned typo ────────────────────
        corrected = None
        if hasattr(self, 'habits') and self.habits:
            local_corrected = self.habits.get_typo_correction(word)
            if local_corrected:
                # Double-check: validate the local correction is still sane
                validator = getattr(self.groq, 'validator', None)
                if validator and not validator.is_valid_correction(word, local_corrected):
                    # Bad local mapping — purge it and fall through to API
                    self.habits.remove_typo(word)
                else:
                    corrected = local_corrected

        # ── Query Groq (if not learned locally) ────────────────────────────────
        if not corrected:
            corrected = self.groq.correct_word(word, context)
            if not corrected:
                return

            # If Groq successfully corrected it, learn this typo locally!
            # The groq.correct_word() already validates via WordValidator,
            # so the correction reaching here is trustworthy.
            if corrected != word and hasattr(self, 'habits') and self.habits:
                self.habits.record_typo(word, corrected)

        # Abort if a newer autocorrect trigger was launched
        with self._lock:
            if self._trigger_id != tid:
                return

        corrected = self._match_case(word, corrected)
        if corrected == word:
            return  # Already correct

        # ── Guard 1: user typed extra chars — cursor has moved, can't backspace safely ──
        if self._get_chars_since_trigger() > 0:
            return

        # ── Guard 2: Groq was too slow — user has moved on ─────────────────────
        if time.time() - trigger_time > 5.0:
            return

        # ── Guard 3: Wait for a micro natural typing PAUSE (≥ 40 ms of silence) ─────
        PAUSE_MS   = 40    # Required silence before we act
        MAX_WAIT_S = 1.0   # Give up after 1.0 s if user keeps typing
        deadline   = time.time() + MAX_WAIT_S
        while time.time() < deadline:
            # Abort immediately if state changed
            with self._lock:
                if self._trigger_id != tid:
                    return
            if self._get_chars_since_trigger() > 0:
                return  # User started typing again
            if self._ms_since_last_key() >= PAUSE_MS:
                break           # User paused — safe to act
            time.sleep(0.025)   # Check every 25 ms
        else:
            return  # User kept typing for 1s — skip

        # Final check before applying
        with self._lock:
            if self._trigger_id != tid:
                return
        if self._get_chars_since_trigger() > 0:
            return

        # Safely serialize correction application
        with self._apply_lock:
            with self._lock:
                if self._trigger_id != tid:
                    return
            if self._get_chars_since_trigger() > 0:
                return
            self._apply(word, corrected)

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

    def _apply(self, original: str, corrected: str):
        """
        BACKSPACE-BASED replacement (no arrow keys, no shift-select).

        At this point, the cursor is right after the Space that triggered
        autocorrect. We:
          1. Backspace 1 (delete the space)
          2. Backspace len(original) (delete the misspelled word)
          3. Type the corrected word + space

        This is simple, reliable, and works in every application.
        """
        self._is_applying = True
        try:
            delay = 0.005  # 5ms between keystrokes — fast but stable

            # Step 1: Delete space + original word via backspaces
            total_backspaces = 1 + len(original)  # 1 for space + word length
            for _ in range(total_backspaces):
                keyboard.send('backspace')
                time.sleep(delay)

            # Step 2: Type corrected word + space
            keyboard.write(corrected + ' ', delay=delay)
            time.sleep(0.02)

        except Exception:
            pass
        finally:
            self._is_applying = False
