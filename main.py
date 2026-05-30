"""
KeyWise AI — Entry Point
Wires all components together and starts the app.
"""
import sys
import threading


def main():
    from config import Config
    from groq_client import GroqClient
    from autocorrect import AutoCorrect
    from sentence_fixer import SentenceFixer
    from keyboard_hook import KeyboardHook
    from tray_manager import TrayManager
    from setup_autostart import setup_autostart
    from typing_habits import TypingHabits

    # ── Bootstrap ──
    config = Config()
    groq_client = GroqClient(config)
    habits = TypingHabits()

    sentence_fixer = SentenceFixer(config, groq_client)
    autocorrect    = AutoCorrect(config, groq_client)
    autocorrect.habits = habits  # Connect self-learning habits engine

    keyboard_hook  = KeyboardHook(
        config, autocorrect, sentence_fixer,
        groq_client=groq_client,
        typing_habits=habits,
    )
    tray = TrayManager(config, groq_client, keyboard_hook)

    # ── Auto-start registry (silent failure if denied) ──
    try:
        if config.get('autostart', True):
            setup_autostart()
    except Exception:
        pass

    # ── Start global keyboard hook ──
    keyboard_hook.start()

    # ── Open Settings on first run (no API key) ──
    if not config.get('groq_api_key'):
        threading.Timer(1.2, tray.open_settings).start()

    # ── Run system tray — blocks until user quits ──
    tray.run()


if __name__ == '__main__':
    main()
