import os
from pathlib import Path

APPDATA = Path(os.getenv('APPDATA') or Path.home())
H2RNG_DATA_DIR = APPDATA / "Hear2Read-NG"
H2RNG_PHONEME_DIR = H2RNG_DATA_DIR / "espeak-ng-data"
H2RNG_ENGINE_DLL_PATH = H2RNG_DATA_DIR / "h2r-ng.dll"
H2RNG_VOICES_DIR = H2RNG_DATA_DIR / "Voices"
H2RNG_WAVS_DIR = H2RNG_DATA_DIR / "wavs"
EN_VOICE_ALOK = "en_US-arctic-medium"
ADDON_NAME = "Hear2ReadNG"