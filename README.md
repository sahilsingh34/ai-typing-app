# KeyWise AI — Intelligent Typing Assistant

A system-wide AI-powered typing assistant for Windows that provides real-time autocorrect, inline ghost text predictions, and grammar fixing — all powered by Groq's ultra-fast LLM API.

## ✨ Features

### Ghost Text Inline Suggestions
- **Next word prediction** — faded gray text appears right after your cursor
- **Sentence completion** — context-aware predictions using Groq LLM
- **Press Ctrl** to accept suggestion (tap Ctrl alone — Ctrl+C/V/Z work normally)
- **Lightweight overlay UI** — borderless, transparent background, sits flush with cursor
- Works **system-wide** across all native Windows apps (Notepad, Word, etc.)

### Smart Autocorrect
- Fixes spelling errors silently after each Space
- **Fast-typing safe** — waits for natural pause before correcting (no text corruption)
- Preserves capitalization (ALLCAPS, Title Case, lowercase)
- Supports **English + Hinglish** (Hindi in Roman script)

### Grammar Fix (F9)
- Select any text → press **F9** → AI fixes grammar, spelling, punctuation
- Strict: only fixes errors, never expands or rewrites
- Output token-capped to prevent paragraph generation

### Learns from Your Typing
- Builds local word frequency + bigram cache from your actual typing
- Provides **instant local predictions** (<1ms) before API response
- Stored at `%APPDATA%/KeyWise/habits.json` — fully private, never uploaded
- Auto-prunes to stay lightweight (top 5000 words, 8000 bigrams)

### Technical Highlights
- **Zero clipboard pollution** — uses `keyboard.write()` (Windows SendInput API)
- **DPI-aware** ghost text font sizing (matches any display scaling)
- **Keyboard hook integration** for physical keyboard input
- Runs from system tray with settings UI
- Auto-start with Windows (optional)

## ⌨️ Controls

| Action | Key |
|--------|-----|
| Accept suggestion | **Ctrl** (tap alone) |
| Dismiss suggestion | **Escape** or any key |
| Fix grammar | **F9** (select text first) |

## 🚀 Quick Start

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Run the app:
   ```bash
   python main.py
   ```

3. On first run, the Settings window opens — enter your **Groq API key**
   - Get one free at [console.groq.com](https://console.groq.com)

4. Start typing in any app — suggestions appear automatically!

## 📁 Project Structure

```
├── main.py              # Entry point — wires all components
├── config.py            # Settings manager (%APPDATA%/KeyWise/config.json)
├── keyboard_hook.py     # Global keyboard hook — captures all input
├── ghost_text.py        # Transparent overlay UI near cursor
├── autocorrect.py       # Silent word correction on Space
├── groq_client.py       # Groq LLM API client
├── sentence_fixer.py    # Grammar fix (F9)
├── typing_habits.py     # Local word frequency learner
├── tray_manager.py      # System tray icon + settings UI
├── setup_autostart.py   # Windows startup registry
└── requirements.txt     # Python dependencies
```

## 🔧 Requirements

- Windows 10/11
- Python 3.10+
- Groq API key (free tier available)

## 📝 License

MIT
