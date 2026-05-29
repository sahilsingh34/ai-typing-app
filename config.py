"""
KeyWise AI — Configuration Manager
Loads and saves settings from %APPDATA%\\KeyWise\\config.json
"""
import json
import os
from pathlib import Path

CONFIG_DIR = Path(os.environ.get('APPDATA', '.')) / 'KeyWise'
CONFIG_FILE = CONFIG_DIR / 'config.json'

DEFAULTS: dict = {
    'groq_api_key': '',
    'model': 'llama-3.1-8b-instant',
    'enabled': True,
    'autocorrect_enabled': True,
    'sentence_fix_enabled': True,
    'autostart': True,
}


class Config:
    def __init__(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self._data: dict = dict(DEFAULTS)
        self._load()

    # ------------------------------------------------------------------ load/save
    def _load(self):
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as fh:
                    saved = json.load(fh)
                self._data.update(saved)
            except Exception:
                pass  # Corrupt config — use defaults

    def _save(self):
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as fh:
                json.dump(self._data, fh, indent=2, ensure_ascii=False)
        except Exception:
            pass

    # ------------------------------------------------------------------ public API
    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value):
        self._data[key] = value
        self._save()
