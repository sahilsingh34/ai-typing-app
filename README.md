# KeyWise AI

> **AI-powered silent autocorrect for Windows — works in any app.**

## What it does

| Action | What happens |
|---|---|
| You type a word + **Space** | AI silently corrects spelling (if wrong) |
| You select text + **Alt+Shift+S** | AI fixes grammar, spelling & clarity |
| Right-click tray icon | Enable/disable, Settings, Quit |

Supports **English, Hindi, Hinglish, Urdu**, and more languages out of the box.

---

## Quick Start

### 1. Install Python dependencies
```
pip install -r requirements.txt
```

### 2. Get a free Groq API key
→ Sign up at **https://console.groq.com** (free tier is generous)

### 3. Run the app
```
python main.py
```

On first launch, the Settings window opens automatically — paste your API key and click **Save & Close**.

### 4. Use it
- Type normally in **any app** (Notepad, Word, Chrome, WhatsApp Web…)
- Words are corrected silently after each Space
- Select bad text → **Alt+Shift+S** → instant grammar fix

---

## Build a portable .exe

```
build.bat
```

The `.exe` in `dist\KeyWiseAI.exe` is self-contained. Copy it to any Windows 10/11 PC — no Python needed. The user just needs to add their Groq API key in Settings.

---

## Settings

Stored in `%APPDATA%\KeyWise\config.json`

| Setting | Default | Description |
|---|---|---|
| Groq API Key | *(empty)* | Your key from console.groq.com |
| Model | `llama-3.1-8b-instant` | Fastest for real-time corrections |
| Auto-correct | On | Spell-fix on Space |
| Sentence fix | On | Grammar fix on Alt+Shift+S |
| Start with Windows | On | Registry autostart |

---

## Limitations

- Works best in apps that support standard clipboard paste
- Some password managers / secure fields may behave unexpectedly — disable KeyWise temporarily with one click in the tray
- API calls depend on internet + Groq uptime (corrections silently skipped on failure)

---

## Architecture

```
main.py  ─► keyboard_hook.py  (presses space → word)
                  │
                  ▼
           autocorrect.py  ─► groq_client.py  ─► Groq API
                  │
                  ▼
           keyboard: backspace × N + paste corrected word

Alt+Shift+S ─► sentence_fixer.py  ─► groq_client.py
                       │
                       ▼
               clipboard: Ctrl+C → fix → Ctrl+V
```
