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
    Tracks word frequency, word→next_word bigrams, and word1→word2→next_word trigrams
    from the user's actual typing, as well as locally learned typo corrections.
    """

    def __init__(self):
        self._lock    = threading.Lock()
        self._dirty   = False
        self._words:   Counter        = Counter()
        self._bigrams: dict[str, Counter] = defaultdict(Counter)
        self._trigrams: dict[str, Counter] = defaultdict(Counter)  # Trigrams for 2-word context
        self._typos:   dict[str, str] = {}                       # Typo -> Correction map
        self._last_word: str          = ''
        self._last_word_2: str        = ''                       # Two words back
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
                    
                raw_trigrams = data.get('trigrams', {})
                for prev2, nexts in raw_trigrams.items():
                    self._trigrams[prev2] = Counter(nexts)
                    
                self._typos = data.get('typos', {})
                
                # ── Validate ALL stored typo mappings on load ──────────────
                # Purge any bad mappings from past LLM errors using
                # edit distance validation (e.g. 'analogy' → 'suggestion')
                try:
                    from word_validator import levenshtein, WordValidator
                    v = WordValidator()
                    bad_keys = []
                    for m, c in self._typos.items():
                        dist = levenshtein(m, c)
                        max_ok = max(2, int(len(m) * 0.45))
                        # Bad if: edit distance too high, or first letter mismatch
                        # on long words, or original is a valid dictionary word
                        if dist > max_ok:
                            bad_keys.append(m)
                        elif len(m) >= 4 and m[0] != c[0]:
                            bad_keys.append(m)
                        elif v.is_valid_word(m):
                            bad_keys.append(m)
                    if bad_keys:
                        for k in bad_keys:
                            del self._typos[k]
                        self._dirty = True
                        self._schedule_save()
                except Exception:
                    pass
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
            bigram_items = sorted(
                self._bigrams.items(),
                key=lambda kv: sum(kv[1].values()),
                reverse=True,
            )[:_MAX_BIGRAMS]
            for prev, nexts in bigram_items:
                top_bigrams[prev] = dict(nexts.most_common(10))
                
            top_trigrams = {}
            trigram_items = sorted(
                self._trigrams.items(),
                key=lambda kv: sum(kv[1].values()),
                reverse=True,
            )[:5000]
            for prev2, nexts in trigram_items:
                top_trigrams[prev2] = dict(nexts.most_common(10))

            data = {
                'words': top_words, 
                'bigrams': top_bigrams,
                'trigrams': top_trigrams,
                'typos': self._typos
            }
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
                if self._last_word_2:
                    key = f"{self._last_word_2}|{self._last_word}"
                    self._trigrams[key][w] += 1
            self._last_word_2 = self._last_word
            self._last_word = w
            self._dirty = True

        self._schedule_save()

    def record_typo(self, misspelled: str, corrected: str):
        """
        Record a user typo correction to bypass API calls next time.
        Only learns corrections that pass edit-distance validation to
        prevent storing bad mappings (e.g. 'analogy' → 'suggestion').
        """
        if not misspelled or not corrected:
            return
        m = misspelled.lower().strip()
        c = corrected.lower().strip()
        if m == c or len(m) < 3:
            return

        # ── Validate before learning ──────────────────────────────────────
        # Import here to avoid circular imports
        try:
            from word_validator import levenshtein, WordValidator
            v = WordValidator()
            # Never learn a correction for a word that is already valid!
            if v.is_valid_word(m):
                return
            dist = levenshtein(m, c)
            max_allowed = max(2, int(len(m) * 0.45))
            # Reject if edit distance is too high (likely a rewrite, not a fix)
            if dist > max_allowed:
                return
            # Reject if first letter changed on long words (likely wrong word)
            if len(m) >= 4 and m[0] != c[0]:
                return
        except Exception:
            pass  # If validator unavailable, learn anyway (backward compat)

        with self._lock:
            self._typos[m] = c
            self._dirty = True
        self._schedule_save()

    def remove_typo(self, word: str):
        """Remove a bad typo mapping (called when validation detects a bad entry)."""
        w = word.lower().strip()
        with self._lock:
            if w in self._typos:
                del self._typos[w]
                self._dirty = True
        self._schedule_save()

    def get_typo_correction(self, word: str) -> str | None:
        """Return a locally learned typo correction if available."""
        w = word.lower().strip()
        with self._lock:
            return self._typos.get(w)

    # ── Public: predict ─────────────────────────────────────────────────────────
    def predict(self, context: str, prefix: str = '') -> str:
        """
        Predict the most likely next word matching the typed prefix based on
        the user's typing patterns using a Trigram -> Bigram -> Unigram backoff model.
        """
        words = context.strip().split()
        last_1 = ""
        last_2 = ""
        if len(words) >= 1:
            last_1 = words[-1].lower().strip('.,!?;:')
        if len(words) >= 2:
            last_2 = words[-2].lower().strip('.,!?;:')

        pref = prefix.lower().strip()

        with self._lock:
            # 1. Try TRIGRAM prediction (two-word context)
            if last_1 and last_2:
                key = f"{last_2}|{last_1}"
                nexts = self._trigrams.get(key)
                if nexts:
                    matches = [(w, c) for w, c in nexts.items() if w.startswith(pref)]
                    if matches:
                        top_word, count = max(matches, key=lambda item: item[1])
                        if count >= 2:
                            return top_word

            # 2. Try BIGRAM prediction (one-word context)
            if last_1:
                nexts = self._bigrams.get(last_1)
                if nexts:
                    matches = [(w, c) for w, c in nexts.items() if w.startswith(pref)]
                    if matches:
                        top_word, count = max(matches, key=lambda item: item[1])
                        if count >= 2:
                            return top_word

            # 3. Try UNIGRAM prediction (frequent unigrams matching prefix)
            if pref:
                matches = [(w, c) for w, c in self._words.items() if w.startswith(pref)]
                if matches:
                    top_word, count = max(matches, key=lambda item: item[1])
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
                'trigrams':     sum(len(v) for v in self._trigrams.values()),
                'typos_learned': len(self._typos),
            }
