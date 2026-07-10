"""Test yolu kurulumu — tek yerden (per-dosya sys.path hack'i yerine).

İki import yolu:
 · `const` (paketsiz): saf çekirdek, HA'sız da çalışır
 · `custom_components.geoshake.*` (paket): mqtt_client vb. — venv'de HA kurulu
"""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))  # custom_components.geoshake paketi
sys.path.insert(0, str(_ROOT / "custom_components" / "geoshake"))  # düz `const`
