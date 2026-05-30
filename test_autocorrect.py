"""Quick test to verify the autocorrect rewrite works correctly."""
import sys
sys.path.insert(0, '.')

print("=" * 60)
print("Testing WordValidator")
print("=" * 60)

from word_validator import WordValidator

v = WordValidator()

# Test 1: Valid words should NOT be corrected
valid_words = ['burger', 'analogy', 'booking', 'service', 'cooking',
               'doctor', 'the', 'hello', 'world', 'beautiful',
               'availability', 'suggestion', 'hypothesis']
print("\n--- Valid words (should all be True) ---")
for w in valid_words:
    result = v.is_valid_word(w)
    status = "✓" if result else "✗ FAIL"
    print(f"  {status} is_valid_word('{w}') = {result}")

# Test 2: Misspelled words should get corrections
misspelled = {
    'teh': 'the',
    'helo': 'hello',
    'wrld': 'world',
    'bruger': 'burger',
}
print("\n--- Misspelled words (should get corrections) ---")
for typo, expected in misspelled.items():
    result = v.find_local_correction(typo)
    status = "✓" if result else "✗ FAIL"
    print(f"  {status} find_local_correction('{typo}') = '{result}' (expected '{expected}')")

# Test 3: Valid words should NOT get local corrections  
print("\n--- Valid words should NOT get corrections ---")
no_correct = ['burger', 'analogy', 'booking', 'service', 'cooking', 'doctor']
for w in no_correct:
    # is_valid_word should be True (so groq_client won't even call find_local_correction)
    valid = v.is_valid_word(w)
    status = "✓" if valid else "✗ FAIL"
    print(f"  {status} is_valid_word('{w}') = {valid} (should be True, skips correction)")

# Test 4: is_valid_correction guards
print("\n--- Correction validation guards ---")
tests = [
    ('analogy', 'analogy', True, 'identical = valid'),
    ('analogy', 'analysis', False, 'valid word changed = reject'),
    ('teh', 'the', True, 'close typo = accept'),
    ('burger', 'burgers', False, 'valid word changed = reject'),
]
for orig, corr, expected, desc in tests:
    result = v.is_valid_correction(orig, corr)
    status = "✓" if result == expected else "✗ FAIL"
    print(f"  {status} is_valid_correction('{orig}', '{corr}') = {result} ({desc})")

print("\n" + "=" * 60)
print("All tests completed!")
print("=" * 60)
