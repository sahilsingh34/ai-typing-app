"""
KeyWise AI — Groq API Client
Handles word correction and sentence fixing using Groq LLM.
Supports English, Hindi, Hinglish, Urdu, and more.
"""
import threading
from groq import Groq

# ── Pre-filter: skip these common words (no need to send to API) ──────────────
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
    # common Hinglish
    'kya', 'haan', 'nhi', 'toh', 'aur', 'bhi', 'bas', 'mai', 'muje',
    'hua', 'hue', 'kar', 'karo', 'sab', 'woh', 'yeh', 'ek', 'iss',
}

# ── System prompts ─────────────────────────────────────────────────────────────
_AUTOCORRECT_PROMPT = (
    "You are an autocorrect assistant for English and Hinglish.\n"
    "The user types in English or Hinglish (Hindi words written in English/Roman script).\n"
    "Given a single word, return ONLY the correctly spelled version.\n"
    "Rules:\n"
    "- If the word is correctly spelled, return it EXACTLY unchanged.\n"
    "- If misspelled, return only the correct spelling.\n"
    "- Keep Hinglish words in Roman script (e.g. accha, theek, kaise).\n"
    "- Never change proper nouns, abbreviations, or numbers.\n"
    "- Return ONLY the single word. No explanation, no punctuation, no quotes."
)

_SENTENCE_FIX_PROMPT = (
    "You are a grammar and spelling corrector. Fix ONLY errors in the text below.\n"
    "STRICT RULES — you MUST follow all of these:\n"
    "- Fix ONLY spelling mistakes, grammar errors, and punctuation.\n"
    "- Do NOT add any new words, sentences, or explanations.\n"
    "- Do NOT expand, elaborate, or rewrite the text.\n"
    "- Do NOT change the meaning, tone, or structure.\n"
    "- The output MUST be approximately the same length as the input.\n"
    "- Keep Hinglish words in Roman script (e.g. 'accha', 'theek').\n"
    "- Return ONLY the corrected text. No commentary, no labels, nothing else.\n"
    "If the text has no errors, return it exactly as-is."
)

_SUGGEST_PROMPT = (
    "You are a typing prediction assistant for English and Hinglish.\n"
    "Given partial text, predict the single most likely NEXT WORD.\n"
    "Rules:\n"
    "- Return ONLY ONE word. Nothing else.\n"
    "- No punctuation, no quotes, no explanation.\n"
    "- If Hinglish context, suggest Hinglish word.\n"
    "- Just the word, lowercase unless it's a proper noun."
)


class GroqClient:
    def __init__(self, config):
        self.config = config
        self._client: Groq | None = None
        self._lock = threading.Lock()

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
        """Return True if this word should be sent to the API."""
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
        Spell-check a single word.
        Returns the corrected spelling, or the original if already correct.
        """
        if not self._should_check(word):
            return word

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
            # Sanity: must be a single token and not wildly different length
            if result and ' ' not in result and len(result) <= len(word) * 2 + 4:
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

