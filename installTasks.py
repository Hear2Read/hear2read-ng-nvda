# A part of the Hear2Read NG voices addon for NVDA
# Copyright (C) 2013-2024, Hear2Read Project Contributors
# See the file COPYING for more details.

import os
import shutil

import gui
import wx
from logHandler import log

# repeating path variable initializations as importing from modules is not 
# allowed in installTasks
H2RNG_DATA_DIR = os.path.join(os.getenv("APPDATA"), "Hear2Read-NG")
H2RNG_VOICES_DIR = os.path.join(H2RNG_DATA_DIR, "Voices")
H2RNG_WAVS_DIR = os.path.join(H2RNG_DATA_DIR, "wavs")
H2RNG_UPDATE_FLAG = os.path.join(H2RNG_DATA_DIR, "pendingUpdate")

try:
    _dir=os.path.dirname(__file__.decode("mbcs"))
except AttributeError:
    _dir=os.path.dirname(__file__)
    
OLD_H2RNG_DATA_DIR = os.path.join(os.environ['ALLUSERSPROFILE'], 
                                  "Hear2Read-ng")

def move_old_voices():
    """Tries to move voices downloaded in addon version 1.4 and lower to the 
    new dir structure to be usable by this addon.
    """
    old_voices_dir = os.path.join(OLD_H2RNG_DATA_DIR, "Voices")

    if os.path.isdir(OLD_H2RNG_DATA_DIR):
        # try moving old voices
        for file in os.listdir(old_voices_dir):
            try:
                src_path = os.path.join(old_voices_dir, file)
                dst_path = os.path.join(H2RNG_VOICES_DIR, file)
                if not file.startswith("en") and not os.path.isfile(dst_path):
                    shutil.copy2(src=src_path, dst=dst_path)
                os.remove(src_path)
            except Exception as e:
                log.warn(f"Hear2Read NG unable to remove old voice file: "
                         f"{file}, Exception: {e}")
        
        old_wavs_dir = os.path.join(OLD_H2RNG_DATA_DIR, "wavs")

        if os.path.isdir(old_wavs_dir):
            try:
                shutil.copytree(src=old_wavs_dir, dst=H2RNG_WAVS_DIR, 
                                dirs_exist_ok=True)
            except Exception as e:
                log.warn(f"Hear2Read NG unable to copy old wav folders: {e}")

        # try deleting old data
        old_dirs = []
        old_dirs.append(old_voices_dir)
        old_dirs.append(old_wavs_dir)
        old_dirs.append(os.path.join(OLD_H2RNG_DATA_DIR, "espeak-ng-data"))

        for dir in old_dirs:
            try:
                if os.path.isdir(dir):
                    shutil.rmtree(dir)
            except Exception as e:
                log.warn(f"Hear2Read NG unable to remove old folder: {dir}, "
                         f"Exception: {e}")

        try:
            shutil.rmtree(OLD_H2RNG_DATA_DIR)
        except Exception as e:
            log.warn("Hear2Read NG unable to remove old Hear2Read data folder: "
                     f"{e}")
                
def onInstall():
    """Copies essential Hear2Read files to the designated data folder, then
    attempts to move data from older installs to this folder.
    """
    src_dir = os.path.join(_dir, "res")
    dll_name = "Hear2ReadNG_addon_engine.dll"

    # First check that the dll file is not in access, i.e., Hear2Read NG is not
    # the current TTS synth
    if os.path.isdir(H2RNG_DATA_DIR):
        try:
            # trying moving the dll first
            shutil.move(os.path.join(src_dir, dll_name), 
                        os.path.join(H2RNG_DATA_DIR, dll_name))
            
            # if the data dir is already present, need to take further steps:
            # touch a file called update flag. This is to ensure proper update 
            # behaviour in NVDA - NVDA runs onUninstall when updating, deleting
            # old voices
            with open(H2RNG_UPDATE_FLAG, 'a'):
                os.utime(H2RNG_UPDATE_FLAG, None)
        except Exception as e:
            if "Hear2ReadNG_addon_engine.dll" in str(e):
                gui.messageBox(
                    # Translators: message telling the user that Hear2Read NG was not installed correctly
                    _("Unable to update Hear2Read NG while it is running in NVDA\n"
                        "Please switch to a different synthesizer, restart NVDA and retry"),
                    # Translators: title of a message telling the user that Hear2Read NG was not installed correctly
                    _("Hear2Read NG Install Error"),
                    wx.OK | wx.ICON_ERROR)
                raise e
            else:
                log.warn("Unable to update Hear2Read properly. Old voices may be deleted")

    try:
        shutil.copytree(src=src_dir, dst=H2RNG_DATA_DIR, dirs_exist_ok=True)
        shutil.rmtree(src_dir)
    except Exception as e:
        log.warn(f"Error installing Hear2Read NG data files: {e}")
        if "Hear2ReadNG_addon_engine.dll" in str(e):
            gui.messageBox(
                # Translators: message telling the user that Hear2Read NG was not installed correctly
                _("Unable to update Hear2Read NG while it is running in NVDA\n"
                    "Please switch to a different synthesizer, restart NVDA and retry"),
                # Translators: title of a message telling the user that Hear2Read NG was not installed correctly
                _("Hear2Read NG Install Error"),
                wx.OK | wx.ICON_ERROR)
            raise e

    src_voice_dir = os.path.join(src_dir, "Voices")
    if os.path.isdir(src_voice_dir):
        for file in os.listdir(src_voice_dir):
            try:
                os.remove(os.path.join(src_voice_dir, file))
            except Exception as e:
                log.warn(f"Hear2Read NG unable to remove file from addon dir: "
                         f"{file}, Exception: {e}")

    move_old_voices()

def onUninstall():
    try:
        log.info("Hear2Read NG uninstalling...")
        if os.path.isfile(H2RNG_UPDATE_FLAG):
            # remove the update flag file so uninstall has the desired effect
            # subsequently
            os.remove(H2RNG_UPDATE_FLAG)
            log.info("Hear2Read update. Ignoring uninstall tasks")
            return
        shutil.rmtree(H2RNG_DATA_DIR)
    except Exception as e:
        log.warn(f"Error removing Hear2Read NG files on uninstall: {e}")