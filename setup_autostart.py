"""
KeyWise AI — Windows Auto-Start Helper
Adds / removes the app from the Windows startup registry.
"""
import os
import sys
import winreg

_REG_PATH = r'Software\Microsoft\Windows\CurrentVersion\Run'
_APP_NAME = 'KeyWiseAI'


def _exe_command() -> str:
    """Return the command string that launches KeyWise AI."""
    if getattr(sys, 'frozen', False):
        # Running as a compiled .exe
        return f'"{sys.executable}"'
    else:
        # Running as a Python script
        script = os.path.abspath(
            os.path.join(os.path.dirname(__file__), 'main.py')
        )
        return f'"{sys.executable}" "{script}"'


def setup_autostart():
    """Register KeyWise AI to start with Windows (current user)."""
    cmd = _exe_command()
    key = winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        _REG_PATH,
        0,
        winreg.KEY_SET_VALUE,
    )
    winreg.SetValueEx(key, _APP_NAME, 0, winreg.REG_SZ, cmd)
    winreg.CloseKey(key)


def remove_autostart():
    """Remove KeyWise AI from Windows startup."""
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            _REG_PATH,
            0,
            winreg.KEY_SET_VALUE,
        )
        winreg.DeleteValue(key, _APP_NAME)
        winreg.CloseKey(key)
    except FileNotFoundError:
        pass  # Already removed
