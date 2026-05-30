import sys
import os

log_file = "test_simple_log.txt"
with open(log_file, "w", encoding="utf-8") as f:
    f.write("Testing Windows Spell Checker COM API...\n")
    try:
        import win32com.client
        import pythoncom
        pythoncom.CoInitialize()
        
        f.write("Attempting to dispatch SpellCheckerFactory...\n")
        f.flush()
        factory = win32com.client.Dispatch("SpellCheckerFactory")
        f.write("SpellCheckerFactory instantiated successfully!\n")
        f.flush()
        
        is_supported = factory.IsSupported("en-US")
        f.write(f"en-US supported: {is_supported}\n")
        f.flush()
        
        checker = factory.CreateSpellChecker("en-US")
        f.write("SpellChecker created successfully!\n")
        f.flush()
        
        # Test some words
        for w in ["burger", "pizza", "pasta", "conflicting", "written", "treatement", "signnature"]:
            errors = checker.Check(w)
            has_errors = False
            if errors:
                err = errors.Next()
                if err:
                    has_errors = True
            f.write(f"  Word: '{w}' -> is_correct: {not has_errors}\n")
            f.flush()
            
    except Exception as e:
        f.write(f"Error: {e}\n")
        f.flush()


