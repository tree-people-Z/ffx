import json
import copy
from pathlib import Path

SETTINGS_PATH = Path(__file__).parent.parent / "settings.json"

DEFAULT_SETTINGS = {
    "general": {
        "output_mode": "same_dir",
        "suffix": "_converted",
        "custom_dir": "",
    },
    "ffmpeg": {
        "custom_ffmpeg_path": "",
        "custom_ffprobe_path": "",
        "enable_hardware": True,
    },
    "interface": {
        "maximize_on_start": False,
        "max_workers": 2,
    },
}


class Settings:
    def __init__(self):
        self.data = {}
        self._reset()

    def _reset(self):
        self.data = copy.deepcopy(DEFAULT_SETTINGS)

    def load(self):
        if not SETTINGS_PATH.exists():
            self._reset()
            return
        try:
            saved = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            self._reset()
            self._merge(self.data, saved)
        except (json.JSONDecodeError, OSError):
            self._reset()

    def save(self):
        SETTINGS_PATH.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2),
            encoding="utf-8")

    def get(self, section, key, default=None):
        return self.data.get(section, {}).get(key, default)

    def set(self, section, key, value):
        if section not in self.data:
            self.data[section] = {}
        self.data[section][key] = value

    @staticmethod
    def _merge(base, override):
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                Settings._merge(base[key], value)
            else:
                base[key] = value
