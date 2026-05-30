from word_validator import WordValidator
import groq_client
v = WordValidator()
print('valid:', v.is_valid_word('bettea'))
print('local:', v.find_local_correction('bettea'))
print('valid:', v.is_valid_word('avability'))
print('local:', v.find_local_correction('avability'))
