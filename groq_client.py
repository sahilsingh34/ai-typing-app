"""
KeyWise AI — Groq API Client
Handles word correction and sentence fixing using Groq LLM.
Supports English, Hindi, Hinglish, Urdu, and more.

Smart correction pipeline:
  1. PRE-FILTER  — Skip tiny words, numbers, URLs, common words
  2. DICTIONARY  — Skip if word is a known valid English/Hinglish word
  3. LOCAL FIX   — Try instant (<1ms) edit-distance correction locally
  4. API CALL    — Ask Groq only for genuinely ambiguous words
  5. POST-GUARD  — Validate Groq's response (Levenshtein + first-letter + length)
  6. CACHE       — Remember words the API returned unchanged ("known good")
"""
import threading
from groq import Groq
from word_validator import WordValidator

# ── Pre-filter: skip these common short words (no need to check at all) ────────
_SKIP_WORDS: set = {
    'a', 'i', 'is', 'in', 'on', 'at', 'to', 'be', 'or', 'an', 'as',
    'it', 'if', 'by', 'we', 'he', 'me', 'my', 'up', 'do', 'so', 'no',
    'go', 'oh', 'ok', 'am', 'are', 'was', 'the', 'and', 'but', 'for',
    'not', 'you', 'all', 'can', 'her', 'his', 'him', 'our', 'out',
    'yes', 'its', 'had', 'has', 'she', 'who', 'did', 'get', 'how',
    'let', 'now', 'see', 'off', 'say', 'too', 'use', 'way', 'may',
    'day', 'got', 'put', 'set', 'own', 'new', 'old', 'big', 'few',
    'man', 'men', 'two', 'any', 'add', 'ago', 'ask', 'why', 'one',
    'top', 'end', 'try', 'hey', 'bye', 'hi', 'ya', 'yep', 'nah',
}

# ── System prompts ─────────────────────────────────────────────────────────────
_AUTOCORRECT_PROMPT = (
    "You are a strict spelling-only corrector for English (India).\n"
    "You receive a single TARGET WORD and optional surrounding context.\n"
    "Your ONLY job: fix spelling mistakes in the target word.\n"
    "\n"
    "ABSOLUTE RULES (violation = failure):\n"
    "1. If the target word is ALREADY a correctly spelled English word, you "
    "MUST return it EXACTLY unchanged. Examples of correctly spelled words you "
    "must NEVER change: 'analogy', 'suggestion', 'beautiful', 'hypothesis', "
    "'treatment', 'available'.\n"
    "2. NEVER replace a correctly spelled word with a synonym, antonym, or "
    "contextually 'better' word. You are NOT a rewriter.\n"
    "3. Context is ONLY provided to disambiguate homophones (their/there, "
    "its/it's). NEVER use context to change the meaning or word choice.\n"
    "4. If misspelled, return the closest correctly spelled English (India) "
    "word that the user likely intended based on letter similarity.\n"
    "5. Never change proper nouns, abbreviations, or numbers.\n"
    "6. Return ONLY the single corrected word. No explanation, no punctuation, "
    "no quotes, no extra text."
)

_SENTENCE_FIX_PROMPT = (
    "You are a strict English (India) grammar and spelling corrector. Fix ONLY errors in the text below.\n"
    "STRICT RULES — you MUST follow all of these:\n"
    "- Fix ONLY spelling mistakes, grammar errors, and punctuation.\n"
    "- Do NOT add any new words, sentences, or explanations.\n"
    "- Do NOT expand, elaborate, or rewrite the text.\n"
    "- Do NOT change the meaning, tone, or structure.\n"
    "- The output MUST be approximately the same length as the input.\n"
    "- Return ONLY the corrected text. No commentary, no labels, nothing else.\n"
    "If the text has no errors, return it exactly as-is."
)

_SUGGEST_PROMPT = (
    "You are a typing prediction assistant for English (India).\n"
    "Given partial text, predict the single most likely NEXT WORD.\n"
    "Rules:\n"
    "- Return ONLY ONE word. Nothing else.\n"
    "- No punctuation, no quotes, no explanation.\n"
    "- Just the word, lowercase unless it's a proper noun."
)


class GroqClient:
    def __init__(self, config):
        self.config = config
        self._client: Groq | None = None
        self._lock = threading.Lock()
        self.validator = WordValidator()    # Smart local validation engine

    # ── Internal helpers ───────────────────────────────────────────────────────
    @property
    def _groq(self) -> Groq | None:
        """Lazy-initialize Groq client."""
        with self._lock:
            api_key = self.config.get('groq_api_key', '').strip()
            if not api_key:
                return None
            if self._client is None:
                self._client = Groq(api_key=api_key)
            return self._client

    def _should_check(self, word: str) -> bool:
        """Return True if this word should be checked for spelling."""
        if len(word) < 3:
            return False
        w = word.lower()
        if w in _SKIP_WORDS:
            return False
        if word.replace('.', '').replace(',', '').isnumeric():
            return False
        # Skip URLs, emails, code-like tokens
        if any(c in word for c in ('@', '/', '\\', ':', '#', '`')):
            return False
        return True

    # ── Public API ─────────────────────────────────────────────────────────────
    def refresh(self):
        """Reset client — call after API key change."""
        with self._lock:
            self._client = None

    def correct_word(self, word: str, context: str = '') -> str:
        """
        Smart spell-check pipeline for a single word.
        Returns the corrected spelling, or the original if already correct.

        Pipeline:
          1. Pre-filter (skip short/special words)
          2. Dictionary check (skip known valid words)
          3. Local edit-distance correction (instant <1ms fix)
          4. Groq API call (for genuinely ambiguous words)
          5. Post-API validation (reject rewrites)
          6. Cache known-good words
        """
        if not self._should_check(word):
            return word

        # ── Layer 1: Dictionary — is this already a valid word? ─────────────
        if self.validator.is_valid_word(word):
            return word  # Never touch a valid word

        # ── Layer 2: Local correction — try instant fix via edit distance ───
        local_fix = self.validator.find_local_correction(word)
        if local_fix:
            return local_fix  # Instant <1ms correction, no API needed

        # ── Layer 3: Groq API — only for genuinely ambiguous words ──────────
        client = self._groq
        if client is None:
            return word

        try:
            ctx_part = f'\nContext sentence so far: "{context}"' if context else ''
            response = client.chat.completions.create(
                model=self.config.get('model', 'llama-3.1-8b-instant'),
                messages=[
                    {'role': 'system', 'content': _AUTOCORRECT_PROMPT},
                    {'role': 'user',   'content': f'Word: {word}{ctx_part}'},
                ],
                max_tokens=20,
                temperature=0.0,
                timeout=1.5,
            )
            result = response.choices[0].message.content.strip()

            # Basic sanity: must be a single token
            if not result or ' ' in result or len(result) > len(word) * 2 + 4:
                return word

            # ── Layer 4: Post-API validation — reject rewrites ──────────────
            if result.lower() != word.lower():
                if not self.validator.is_valid_correction(word, result):
                    # Groq tried to rewrite the word — reject it
                    return word

            # If API returned it unchanged, cache it as "known good"
            if result.lower() == word.lower():
                self.validator.mark_known_good(word)
                return word

            return result

        except Exception:
            pass

        return word  # Fail silently — never block typing

    def suggest_next_words(self, context: str) -> str:
        """
        Predict the single next word given the current typing context.
        Returns one word, or '' on failure.
        """
        client = self._groq
        if client is None or not context.strip():
            return ''

        try:
            response = client.chat.completions.create(
                model=self.config.get('model', 'llama-3.1-8b-instant'),
                messages=[
                    {'role': 'system', 'content': _SUGGEST_PROMPT},
                    {'role': 'user',   'content': context[-200:]},
                ],
                max_tokens=8,
                temperature=0.1,
                timeout=1.5,
            )
            result = response.choices[0].message.content.strip()
            # Clean up: remove quotes, punctuation
            result = result.strip('"\'.,!?;:')
            # Take only the first word if multiple returned
            if result:
                first_word = result.split()[0]
                if first_word and len(first_word) < 30:
                    return first_word
        except Exception:
            pass

        return ''


    def fix_sentence(self, text: str) -> str:
        """
        Fix grammar, spelling, and punctuation of selected text.
        Returns the corrected version (same length), or the original on failure.
        """
        client = self._groq
        if client is None or not text.strip():
            return text

        # Cap output tokens to ~2× the input word count so the LLM
        # cannot expand a short sentence into a paragraph.
        word_count = len(text.split())
        max_tok = max(60, word_count * 2)

        try:
            response = client.chat.completions.create(
                model=self.config.get('model', 'llama-3.1-8b-instant'),
                messages=[
                    {'role': 'system', 'content': _SENTENCE_FIX_PROMPT},
                    {'role': 'user',   'content': text},
                ],
                max_tokens=max_tok,
                temperature=0.0,   # Deterministic — no creative expansion
                timeout=10.0,
            )
            result = response.choices[0].message.content.strip()
            return result if result else text
        except Exception:
            return text  # Fail silently

    def test_connection(self) -> tuple[bool, str]:
        """Test API key. Returns (success, message)."""
        key = self.config.get('groq_api_key', '').strip()
        if not key:
            return False, 'No API key set.'
        try:
            c = Groq(api_key=key)
            resp = c.chat.completions.create(
                model='llama-3.1-8b-instant',
                messages=[{'role': 'user', 'content': 'Reply with just the word OK'}],
                max_tokens=5,
                timeout=6,
            )
            ans = resp.choices[0].message.content.strip()
            return True, f'Connected! Model replied: "{ans}"'
        except Exception as e:
            return False, str(e)[:120]
