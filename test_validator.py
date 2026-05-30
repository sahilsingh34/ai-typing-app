"""Quick test for the word validator."""
from word_validator import WordValidator, levenshtein

v = WordValidator()

print("=== Dictionary Tests ===")
for w in ['analogy', 'suggestion', 'treatment', 'beautiful', 'hypothesis', 'hello']:
    print(f"  {w}: valid={v.is_valid_word(w)}")

print("\n=== Edit Distance Tests ===")
pairs = [
    ('analogy', 'suggestion'),
    ('treatement', 'treatment'),
    ('signnature', 'signature'),
    ('anology', 'analogy'),
]
for a, b in pairs:
    d = levenshtein(a, b)
    vc = v.is_valid_correction(a, b)
    print(f"  {a} -> {b}: dist={d}, valid_correction={vc}")

print("\n=== Local Correction Tests ===")
for t in ['treatement', 'signnature', 'analgy', 'definately', 'recieve']:
    print(f"  {t} -> {v.find_local_correction(t)}")

print("\n=== Stats ===")
print(v.get_stats())

# Test Groq client import
print("\n=== GroqClient import ===")
try:
    from groq_client import GroqClient
    print("  GroqClient imported OK")
except Exception as e:
    print(f"  ERROR: {e}")

# Test typing habits with validation
print("\n=== TypingHabits load ===")
try:
    from typing_habits import TypingHabits
    h = TypingHabits()
    print(f"  Loaded OK. Typos: {h._typos}")
    print(f"  Stats: {h.get_stats()}")
except Exception as e:
    print(f"  ERROR: {e}")
