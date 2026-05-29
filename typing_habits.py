"""
KeyWise AI — Typing Habits Learner
Learns from user's typing patterns to improve suggestions.

Maintains a local word frequency + bigram cache stored at
%APPDATA%/KeyWise/habits.json.  Used by the suggestion engine
to provide instant local predictions (<1 ms) before the API response
arrives, or as a fallback when offline.
"""
import json
import os
import threading
from collections import Counter, defaultdict
from pathlib import Path

_HABITS_DIR  = Path(os.environ.get('APPDATA', '.')) / 'KeyWise'
_HABITS_FILE = _HABITS_DIR / 'habits.json'

# Limits
_MAX_WORDS   = 5000    # Keep top N words by frequency
_MAX_BIGRAMS = 8000    # Keep top N bigrams


class TypingHabits:
    """
    Tracks word frequency and word→next_word bigrams from the user's
    actual typing.  Periodically saves to disk.

    Public API (all thread-safe):
      • record_word(word)           — call after each space
      • predict(context) → str     — instant local prediction
      • save()                      — persist to disk
    """

    def __init__(self):
        self._lock    = threading.Lock()
        self._dirty   = False
        self._words:   Counter        = Counter()
        self._bigrams: dict[str, Counter] = defaultdict(Counter)
        self._last_word: str          = ''
        self._save_timer: threading.Timer | None = None
        self._load()

    # ── Load / Save ─────────────────────────────────────────────────────────────
    def _load(self):
        """Load habits from disk."""
        try:
            if _HABITS_FILE.exists():
                with open(_HABITS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self._words = Counter(data.get('words', {}))
                raw_bigrams = data.get('bigrams', {})
                for prev, nexts in raw_bigrams.items():
                    self._bigrams[prev] = Counter(nexts)
        except Exception:
            pass  # Corrupt file — start fresh

    def save(self):
        """Persist habits to disk. Called automatically, but can be called manually."""
        with self._lock:
            if not self._dirty:
                return
            # Prune to keep top N
            top_words = dict(self._words.most_common(_MAX_WORDS))
            top_bigrams = {}
            # Sort bigrams by total downstream frequency
            bigram_items = sorted(
                self._bigrams.items(),
                key=lambda kv: sum(kv[1].values()),
                reverse=True,
            )[:_MAX_BIGRAMS]
            for prev, nexts in bigram_items:
                # Keep top 10 next-words per predecessor
                top_bigrams[prev] = dict(nexts.most_common(10))

            data = {'words': top_words, 'bigrams': top_bigrams}
            self._dirty = False

        try:
            _HABITS_DIR.mkdir(parents=True, exist_ok=True)
            with open(_HABITS_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception:
            pass

    def _schedule_save(self):
        """Auto-save every 30 seconds after a change."""
        if self._save_timer and self._save_timer.is_alive():
            return  # Already scheduled
        self._save_timer = threading.Timer(30.0, self.save)
        self._save_timer.daemon = True
        self._save_timer.start()

    # ── Public: record ──────────────────────────────────────────────────────────
    def record_word(self, word: str):
        """
        Record that the user typed `word`.
        Call after each Space (with the completed word).
        """
        if not word or len(word) < 2:
            return
        w = word.lower().strip()
        if not w:
            return

        with self._lock:
            self._words[w] += 1
            if self._last_word:
                self._bigrams[self._last_word][w] += 1
            self._last_word = w
            self._dirty = True

        self._schedule_save()

    # ── Public: predict ─────────────────────────────────────────────────────────
    def predict(self, context: str) -> str:
        """
        Instant local prediction based on learned bigrams.
        Returns the most likely next word, or '' if not confident.

        context: the full typing context (we use only the last word).
        """
        words = context.strip().split()
        if not words:
            return ''

        last = words[-1].lower().strip('.,!?;:')
        if not last:
            return ''

        with self._lock:
            nexts = self._bigrams.get(last)
            if not nexts:
                return ''
            # Return the most common next-word if it has >= 3 occurrences
            top_word, count = nexts.most_common(1)[0]
            if count >= 3:
                return top_word

        return ''

    def get_stats(self) -> dict:
        """Return stats for the settings UI."""
        with self._lock:
            return {
                'unique_words': len(self._words),
                'total_typed':  sum(self._words.values()),
                'bigrams':      sum(len(v) for v in self._bigrams.values()),
            }
