"""
KeyWise AI — Global Keyboard Hook
Captures all keystrokes system-wide, builds a word buffer,
triggers autocorrect on Space, and shows a ghost-text suggestion
near the cursor. Registers F9 for grammar fix.

Ghost Text Suggestion Flow:
  1. User types "I want to " (Space pressed)
  2. Instantly check local habits for prediction (<1ms)
  3. Also ask Groq for prediction (~400ms)
  4. Ghost text appears next to cursor
  5. Ctrl (tap alone) → types the word, hides overlay
     Any other key → hides overlay, nothing typed

Ctrl-tap detection:
  - Ctrl DOWN → sets _ctrl_held=True, _ctrl_used=False
  - Any key pressed while Ctrl held → _ctrl_used=True
  - Ctrl UP → if _ctrl_used is still False → accept suggestion
  - Ctrl+C/V/Z/Shift never accidentally accepts.
"""
import threading
import time

import keyboard

from ghost_text import GhostTextOverlay, get_caret_screen_pos


class KeyboardHook:
    def __init__(self, config, autocorrect, sentence_fixer,
                 groq_client=None, typing_habits=None):
        self.config         = config
        self.autocorrect    = autocorrect
        self.sentence_fixer = sentence_fixer
        self.groq           = groq_client
        self.habits         = typing_habits     # TypingHabits instance

        # Word buffer — characters of the word currently being typed
        self._word_buf: list[str] = []
        # Context buffer — last ~300 chars for Groq context
        self._ctx_buf: list[str] = []

        # Shift / Caps-Lock state
        self._shift: bool = False
        self._caps:  bool = False

        # Ctrl-tap state
        self._ctrl_held: bool = False
        self._ctrl_used: bool = False

        self._running: bool = False

        # Ghost text overlay
        self._ghost = GhostTextOverlay()

        # Stale-request guard
        self._suggestion_gen: int = 0

        # Currently active full predicted suggestion word
        self._active_suggestion: str = ""

    # ── Lifecycle ────────────────────────────────────────────────────────────────
    def start(self) -> None:
        self._running = True

        # F9 → fix selected text with Groq
        keyboard.add_hotkey(
            'f9',
            self._on_sentence_fix_hotkey,
            suppress=True,
            trigger_on_release=True,
        )

        # Observe ALL key events (non-suppressing)
        keyboard.hook(self._on_key, suppress=False)

    def stop(self) -> None:
        self._running = False
        try:
            keyboard.unhook_all()
        except Exception:
            pass
        try:
            self._ghost.shutdown()
        except Exception:
            pass
        # Save typing habits on exit
        if self.habits:
            try:
                self.habits.save()
            except Exception:
                pass

    # ── Hotkey callback ──────────────────────────────────────────────────────────
    def _on_sentence_fix_hotkey(self) -> None:
        if self.config.get('sentence_fix_enabled') and self.config.get('enabled'):
            self._ghost.hide()
            threading.Thread(target=self.sentence_fixer.trigger,
                             daemon=True).start()

    # ── Ghost text helpers ───────────────────────────────────────────────────────
    def _cancel_suggestion(self) -> None:
        self._suggestion_gen += 1
        self._active_suggestion = ""
        self._ghost.hide()

    def _accept_ghost_suggestion(self) -> None:
        """
        Accept ghost word: type it via SendInput (no clipboard).
        """
        word = self._ghost.get_current_word()  # This is the suffix
        self._ghost.hide()
        self._active_suggestion = ""
        if not word:
            return

        self.autocorrect._is_applying = True
        try:
            # Type suffix instantly to avoid fast-typing race conditions/interleaving
            keyboard.write(word + ' ', delay=0.0)
            time.sleep(0.02)

            for ch in word + ' ':
                self._ctx_buf.append(ch)
                self.autocorrect.notify_new_char()
            self._trim_ctx()

            # Record full completed word (prefix + suffix)
            prefix = ''.join(self._word_buf)
            full_word = prefix + word
            self._word_buf.clear()

            if self.habits:
                self.habits.record_word(full_word)
        except Exception:
            pass
        finally:
            self.autocorrect._is_applying = False

    def _request_suggestion(self, context: str) -> None:
        """
        Two-stage prediction:
        1. Instant local prediction from typing habits (<1ms)
        2. Groq API prediction (~400ms) — replaces local if available
        """
        if not self.config.get('enabled'):
            return

        self._suggestion_gen += 1
        gen = self._suggestion_gen

        def show_if_matching(suggested_word: str):
            prefix = ''.join(self._word_buf)
            if suggested_word.lower().startswith(prefix.lower()):
                suffix = suggested_word[len(prefix):]
                if suffix:
                    pos = get_caret_screen_pos()
                    if pos:
                        x, y, pt = pos
                        self._active_suggestion = suggested_word
                        self._ghost.show(suffix, x, y, pt)
                else:
                    self._cancel_suggestion()
            else:
                self._cancel_suggestion()

        # ── Stage 1: Instant local prediction ──────────────────────────────
        if self.habits:
            local_pred = self.habits.predict(context)
            if local_pred and gen == self._suggestion_gen:
                show_if_matching(local_pred)

        # ── Stage 2: Groq API (async) ──────────────────────────────────────
        if not self.groq:
            return

        def _fetch() -> None:
            time.sleep(0.35)   # Brief delay so autocorrect finishes first

            if gen != self._suggestion_gen:
                return  # Stale

            result = self.groq.suggest_next_words(context)

            if gen != self._suggestion_gen or not result:
                return

            # Groq result replaces local prediction
            show_if_matching(result)

        threading.Thread(target=_fetch, daemon=True).start()

    # ── Key event handler ────────────────────────────────────────────────────────
    def _on_key(self, event) -> None:
        if not self._running:
            return
        if self.autocorrect.is_applying:
            return

        name: str = event.name or ''
        is_down   = event.event_type == 'down'
        is_up     = event.event_type == 'up'

        # ── Track Shift / Caps Lock ──
        if name in ('left shift', 'right shift', 'shift'):
            self._shift = is_down
            if self._ctrl_held and is_down:
                self._ctrl_used = True
            return

        if name == 'caps lock' and is_down:
            self._caps = not self._caps
            if self._ctrl_held:
                self._ctrl_used = True
            return

        # ── Ctrl tap detection ──────────────────────────────────────────────
        if name in ('left ctrl', 'right ctrl', 'ctrl'):
            if is_down:
                self._ctrl_held = True
                self._ctrl_used = False
            elif is_up:
                if not self._ctrl_used and self._ghost.get_current_word():
                    threading.Thread(target=self._accept_ghost_suggestion,
                                     daemon=True).start()
                self._ctrl_held = False
                self._ctrl_used = False
            return

        # ── Windows key — ignore ──
        if name in ('left windows', 'right windows'):
            return

        # Only process key-DOWN events from here
        if not is_down:
            return

        # ── Ctrl held + another key → shortcut (Ctrl+C, etc.) ──
        if self._ctrl_held:
            self._ctrl_used = True
            return

        # ── Alt — ignore ──
        if name in ('alt', 'left alt', 'right alt'):
            return

        # ── Tab — clear word buffer, hide overlay ──
        if name == 'tab':
            self._word_buf.clear()
            self._cancel_suggestion()
            return

        # ── Escape — dismiss suggestion ──
        if name == 'escape':
            self._cancel_suggestion()
            return

        # ── Space — autocorrect + learn + request suggestion ──
        if name == 'space':
            word    = ''.join(self._word_buf)
            context = ''.join(self._ctx_buf[-200:])
            self._word_buf.clear()
            self._ctx_buf.append(' ')
            self._trim_ctx()
            self.autocorrect.notify_new_char()

            if self.config.get('enabled'):
                # Record word in typing habits
                if self.habits and word:
                    self.habits.record_word(word)

                if self.config.get('autocorrect_enabled') and word:
                    threading.Thread(
                        target=self.autocorrect.trigger,
                        args=(word, context),
                        daemon=True,
                    ).start()

                # On Space, clear active suggestion and request prediction for next word
                self._cancel_suggestion()
                full_ctx = ''.join(self._ctx_buf[-200:])
                self._request_suggestion(full_ctx)
            return

        # ── Backspace ──
        if name == 'backspace':
            if self._word_buf:
                self._word_buf.pop()
            if self._ctx_buf:
                self._ctx_buf.pop()
            self.autocorrect.notify_backspace()

            if self._active_suggestion:
                prefix = ''.join(self._word_buf)
                if self._active_suggestion.lower().startswith(prefix.lower()):
                    suffix = self._active_suggestion[len(prefix):]
                    def update_pos():
                        time.sleep(0.01)  # Micro-sleep to let application update caret
                        pos = get_caret_screen_pos()
                        if pos and self._active_suggestion:
                            x, y, pt = pos
                            self._ghost.show(suffix, x, y, pt)
                    threading.Thread(target=update_pos, daemon=True).start()
                else:
                    self._cancel_suggestion()
            else:
                self._suggestion_gen += 1
            return

        # ── Enter ──
        if name in ('enter', 'return'):
            self._word_buf.clear()
            self._ctx_buf.append('\n')
            self._trim_ctx()
            self.autocorrect.notify_new_char()
            self._cancel_suggestion()
            return

        # ── Regular printable character ──
        if len(name) == 1:
            upper = self._shift ^ self._caps
            char  = name.upper() if upper else name
            self._word_buf.append(char)
            self._ctx_buf.append(char)
            self._trim_ctx()
            self.autocorrect.notify_new_char()

            # Dynamic narrowing: if we have an active suggestion, check if it still matches
            if self._active_suggestion:
                prefix = ''.join(self._word_buf)
                if self._active_suggestion.lower().startswith(prefix.lower()):
                    suffix = self._active_suggestion[len(prefix):]
                    if suffix:
                        def update_pos():
                            time.sleep(0.01)  # Micro-sleep to let application update caret
                            pos = get_caret_screen_pos()
                            if pos and self._active_suggestion:
                                x, y, pt = pos
                                self._ghost.show(suffix, x, y, pt)
                        threading.Thread(target=update_pos, daemon=True).start()
                    else:
                        self._cancel_suggestion()
                else:
                    self._cancel_suggestion()
            else:
                self._suggestion_gen += 1

    # ── Helpers ──────────────────────────────────────────────────────────────────
    def _trim_ctx(self) -> None:
        if len(self._ctx_buf) > 300:
            self._ctx_buf = self._ctx_buf[-300:]
