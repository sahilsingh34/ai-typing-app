from word_validator import WordValidator

v = WordValidator()

with open('test_out2.txt', 'w') as f:
    f.write(f"valid bettea: {v.is_valid_word('bettea')}\n")
    f.write(f"local bettea: {v.find_local_correction('bettea')}\n")
    f.write(f"valid avability: {v.is_valid_word('avability')}\n")
    f.write(f"local avability: {v.find_local_correction('avability')}\n")
