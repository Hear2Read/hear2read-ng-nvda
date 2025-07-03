
import os

H2RNG_DATA_DIR = os.path.join(os.getenv("APPDATA"), "Hear2Read-NG")
H2RNG_PHONEME_DIR = os.path.join(H2RNG_DATA_DIR, "espeak-ng-data")
H2RNG_ENGINE_DLL_PATH = os.path.join(H2RNG_DATA_DIR, "Hear2ReadNG_addon_engine.dll")
H2RNG_VOICES_DIR = os.path.join(H2RNG_DATA_DIR, "Voices")
H2RNG_WAVS_DIR = os.path.join(H2RNG_DATA_DIR, "wavs")
EN_VOICE_ALOK = "en_US-arctic-medium"