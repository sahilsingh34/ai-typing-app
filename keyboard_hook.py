"""
KeyWise AI — Global Keyboard Hook
Captures all keystrokes system-wide, builds a word buffer,
triggers autocorrect on Space, types inline suggestions,
and accepts them on Tab. Registers Alt+Shift+S hotkey.

Inline Suggestion Flow:
  1. User types "I want to " (space)
  2. Groq predicts: "go to the store"
  3. KeyWise types "go to the store" and selects it (highlighted)
  4. Tab → deselects (accepts)   |   Any other key → replaces selection
"""
import threading
import time

import keyboard
import pyperclip


class KeyboardHook:
    def __init__(self, config, autocorrect, sentence_fixer,
                 groq_client=None):
        self.config = config
        self.autocorrect = autocorrect
        self.sentence_fixer = sentence_fixer
        self.groq = groq_client

        # Word buffer — tracks characters of the currently-typed word
        self._word_buf: list[str] = []
        # Context buffer — last ~300 chars (for Groq context)
        self._ctx_buf: list[str] = []

        # Shift / Caps-Lock tracking for proper case in word buffer
        self._shift: bool = False
        self._caps: bool = False

        self._running: bool = False

        # Inline suggestion state
        self._suggestion_gen: int = 0          # Cancel stale requests
        self._pending_suggestion: bool = False  # Is a suggestion currently selected?
        self._pending_len: int = 0              # Length of the suggestion text

    # ── Lifecycle ───────────────────────────────────────────────────────────────
    def start(self):
        self._running = True

        # Alt+Shift+S → sentence fix
        keyboard.add_hotkey(
            'alt+shift+s',
            self._on_sentence_fix_hotkey,
            suppress=True,
            trigger_on_release=False,
        )

        # Hook all key events (non-suppressing — we just observe)
        keyboard.hook(self._on_key, suppress=False)

    def stop(self):
        self._running = False
        try:
            keyboard.unhook_all()
        except Exception:
            pass

    # ── Hotkey callbacks ────────────────────────────────────────────────────────
    def _on_sentence_fix_hotkey(self):
        if self.config.get('sentence_fix_enabled') and self.config.get('enabled'):
            threading.Thread(target=self.sentence_fixer.trigger, daemon=True).start()

    # ── Inline suggestion helpers ───────────────────────────────────────────────
    def _cancel_pending(self):
        """Mark any pending suggestion as cancelled (don't delete text — OS handles it)."""
        self._pending_suggestion = False
        self._pending_len = 0
        self._suggestion_gen += 1

    def _type_suggestion(self, text: str):
        """
        Type suggestion text inline and select it (highlight it).
        If user types anything, the selection is naturally replaced by the OS.
        """
        if not text.strip():
            return

        self.autocorrect._is_applying = True
        try:
            # Save original clipboard
            try:
                prev_clip = pyperclip.paste()
            except Exception:
                prev_clip = ''

            # Paste the suggestion
            pyperclip.copy(text)
            time.sleep(0.03)
            keyboard.send('ctrl+v')
            time.sleep(0.06)

            # Select the pasted text by pressing Shift+Left × len
            n = len(text)
            self._pending_len = n
            for _ in range(n):
                keyboard.send('shift+left')
                time.sleep(0.004)

            self._pending_suggestion = True

            # Restore clipboard later
            threading.Timer(0.5, lambda: _safe_clip(prev_clip)).start()

        except Exception:
            self._pending_suggestion = False
            self._pending_len = 0
        finally:
            self.autocorrect._is_applying = False

    def _accept_suggestion(self):
        """Accept: move cursor to end of selection (deselect, keep text)."""
        self.autocorrect._is_applying = True
        try:
            keyboard.send('right')     # Deselect → cursor at end of suggestion
            time.sleep(0.02)

            # Add the accepted text to context buffer
            # (We don't know the exact text, but that's OK — context will
            #  pick up naturally from future typing)
        except Exception:
            pass
        finally:
            self._pending_suggestion = False
            self._pending_len = 0
            self.autocorrect._is_applying = False

    def _dismiss_suggestion(self):
        """Dismiss: delete the selected suggestion text."""
        self.autocorrect._is_applying = True
        try:
            keyboard.send('delete')    # Delete selected text
            time.sleep(0.02)
        except Exception:
            pass
        finally:
            self._pending_suggestion = False
            self._pending_len = 0
            self.autocorrect._is_applying = False

    def _request_suggestion(self, context: str):
        """Request next-word suggestion from Groq in background."""
        if not self.groq:
            return
        if not self.config.get('enabled'):
            return

        self._suggestion_gen += 1
        gen = self._suggestion_gen

        def _fetch():
            # Small delay to let autocorrect finish first
            time.sleep(0.5)

            if gen != self._suggestion_gen:
                return  # User typed more — cancel

            result = self.groq.suggest_next_words(context)

            if gen != self._suggestion_gen:
                return  # Stale

            if result and gen == self._suggestion_gen:
                self._type_suggestion(result)

        threading.Thread(target=_fetch, daemon=True).start()

    # ── Key event handler ───────────────────────────────────────────────────────
    def _on_key(self, event):
        if not self._running:
            return
        # Ignore events we generate ourselves
        if self.autocorrect.is_applying:
            return

        name: str = event.name or ''

        # ── Track Shift / Caps Lock state ──
        if name in ('left shift', 'right shift', 'shift'):
            self._shift = (event.event_type == 'down')
            return
        if name == 'caps lock' and event.event_type == 'down':
            self._caps = not self._caps
            return

        if event.event_type != 'down':
            return   # Only process key-down events from here

        # ── Modifier keys: ignore (except Alt — used for accepting) ──
        if name in ('left ctrl', 'right ctrl', 'ctrl',
                     'left windows', 'right windows'):
            return

        # ── Alt: accept suggestion if pending ──
        if name in ('alt', 'left alt', 'right alt'):
            if self._pending_suggestion:
                threading.Thread(target=self._accept_suggestion, daemon=True).start()
            return

        # ── Tab: normal behavior — reset word buffer ──
        if name == 'tab':
            self._word_buf.clear()
            return

        # ── Escape: dismiss suggestion ──
        if name == 'escape':
            if self._pending_suggestion:
                threading.Thread(target=self._dismiss_suggestion, daemon=True).start()
                return
            return

        # ── Any other key while suggestion is pending → cancel tracking ──
        # (The OS will naturally replace the selected text when user types)
        if self._pending_suggestion:
            self._cancel_pending()

        # ── Space: trigger autocorrect + suggestion ──
        if name == 'space':
            word = ''.join(self._word_buf)
            context = ''.join(self._ctx_buf[-200:])
            self._word_buf.clear()
            self._ctx_buf.append(' ')
            self._trim_ctx()
            self.autocorrect.notify_new_char()  # Space = 1 cursor position

            if self.config.get('enabled'):
                # Autocorrect the last word
                if self.config.get('autocorrect_enabled') and word:
                    threading.Thread(
                        target=self.autocorrect.trigger,
                        args=(word, context),
                        daemon=True,
                    ).start()

                # Request next-word inline suggestion
                full_ctx = ''.join(self._ctx_buf[-200:])
                self._request_suggestion(full_ctx)
            return

        # ── Backspace: remove last char ──
        if name == 'backspace':
            if self._word_buf:
                self._word_buf.pop()
            if self._ctx_buf:
                self._ctx_buf.pop()
            self.autocorrect.notify_backspace()  # Position decremented
            self._suggestion_gen += 1
            return

        # ── Enter: reset word buffer ──
        if name in ('enter', 'return'):
            self._word_buf.clear()
            self._ctx_buf.append('\n')
            self._trim_ctx()
            self.autocorrect.notify_new_char()  # Enter = 1 cursor position
            self._suggestion_gen += 1
            return

        # ── Regular printable character ──
        if len(name) == 1:
            upper = self._shift ^ self._caps
            char = name.upper() if upper else name
            self._word_buf.append(char)
            self._ctx_buf.append(char)
            self._trim_ctx()
            self.autocorrect.notify_new_char()  # Char = 1 cursor position
            self._suggestion_gen += 1


    def _trim_ctx(self):
        if len(self._ctx_buf) > 300:
            self._ctx_buf = self._ctx_buf[-300:]


def _safe_clip(text: str):
    try:
        pyperclip.copy(text)
    except Exception:
        pass
