# A part of the Hear2Read Indic Voices addon for NVDA
# Copyright (C) 2013-2024, Hear2Read Project Contributors
# See the file COPYING for more details.

import os
import shutil
import sys

import gui
import wx
from logHandler import log

# repeating path variable initializations as importing from modules is not 
# allowed in installTasks
H2RNG_DATA_DIR = os.path.join(os.getenv("APPDATA"), "Hear2Read-NG")
H2RNG_VOICES_DIR = os.path.join(H2RNG_DATA_DIR, "Voices")
H2RNG_WAVS_DIR = os.path.join(H2RNG_DATA_DIR, "wavs")
H2RNG_UPDATE_FLAG = os.path.join(H2RNG_DATA_DIR, "pendingUpdate")
H2RNG_ENGINE_DLL_PATH = os.path.join(H2RNG_DATA_DIR, "Hear2ReadNG_addon_engine.dll")

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
                log.warn(f"Hear2Read Indic unable to remove old voice file: "
                         f"{file}, Exception: {e}")
        
        old_wavs_dir = os.path.join(OLD_H2RNG_DATA_DIR, "wavs")

        if os.path.isdir(old_wavs_dir):
            try:
                copytree_overwrite(src=old_wavs_dir, dst=H2RNG_WAVS_DIR)
            except Exception as e:
                log.warn(f"Hear2Read Indic unable to copy old wav folders: {e}")

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
                log.warn(f"Hear2Read Indic unable to remove old folder: {dir}, "
                         f"Exception: {e}")

        try:
            shutil.rmtree(OLD_H2RNG_DATA_DIR)
        except Exception as e:
            log.warn("Hear2Read Indic unable to remove old Hear2Read data folder: "
                     f"{e}")

def copytree_compat(src, dst):
    """Copytree version with overwrite compatible for Python < 3.8. This is
    copied from the answer https://stackoverflow.com/a/13814557, and has a 
    fairly basic functionality not accounting for symlinks, which is sufficient
    for our purposes

    @param src: path to the source, to be copied from
    @type src: string
    @param dst: path to the destination, to be copied to
    @type dst: string
    """
    if not os.path.exists(dst):
        os.makedirs(dst)
    for item in os.listdir(src):
        s = os.path.join(src, item)
        d = os.path.join(dst, item)
        if os.path.isdir(s):
            copytree_compat(s, d)
        else:
            if not os.path.exists(d) or os.stat(s).st_mtime - os.stat(d).st_mtime > 1:
                shutil.copy2(s, d)

def copytree_overwrite(src, dst):
    """Wrapper to enable consistent behaviour in Python version < 3.8

    @param src: path to the source, to be copied from
    @type src: string
    @param dst: path to the destination, to be copied to
    @type dst: string
    """
    if sys.version_info >= (3, 8):
        shutil.copytree(src=src, dst=dst, dirs_exist_ok=True)
    else:
        copytree_compat(src=src, dst=dst)
                
def onInstall():
    """Copies essential Hear2Read files to the designated data folder, then
    attempts to move data from older installs to this folder.
    """
    src_dir = os.path.join(_dir, "res")
    dll_name = "Hear2ReadNG_addon_engine.dll"

    # First check that the dll file is not in access, i.e., Hear2Read Indic is not
    # the current TTS synth
    if os.path.isdir(H2RNG_DATA_DIR):            
        # if the data dir is already present, need to take further steps:
        # touch a file called update flag. This is to ensure proper update 
        # behaviour in NVDA - NVDA runs onUninstall when updating, deleting
        # old voices
        with open(H2RNG_UPDATE_FLAG, 'a'):
            os.utime(H2RNG_UPDATE_FLAG, None)
        try:
            # trying moving the dll first
            shutil.move(os.path.join(src_dir, dll_name), 
                        os.path.join(H2RNG_DATA_DIR, dll_name))
        except Exception as e:
            if dll_name in str(e):
                shutil.move(os.path.join(src_dir, dll_name), 
                        os.path.join(H2RNG_DATA_DIR, dll_name+".update"))
                # gui.messageBox(
                #     # Translators: message telling the user that Hear2Read Indic was not installed correctly
                #     _("Unable to update Hear2Read Indic while it is running in NVDA\n"
                #         "Please switch to a different synthesizer, restart NVDA and retry"),
                #     # Translators: title of a message telling the user that Hear2Read Indic was not installed correctly
                #     _("Hear2Read Indic Install Error"),
                #     wx.OK | wx.ICON_ERROR)
                # raise e
            else:
                log.warn("Unable to update Hear2Read properly. Old voices may be deleted")

    try:
        copytree_overwrite(src=src_dir, dst=H2RNG_DATA_DIR)
        shutil.rmtree(src_dir)
    except Exception as e:
        log.warn(f"Error installing Hear2Read Indic data files: {e}")
        if dll_name in str(e):
            gui.messageBox(
                # Translators: message telling the user that Hear2Read Indic was not installed correctly
                _("Unable to update Hear2Read Indic while it is running in NVDA\n"
                    "Please switch to a different synthesizer, restart NVDA and retry"),
                # Translators: title of a message telling the user that Hear2Read Indic was not installed correctly
                _("Hear2Read Indic Install Error"),
                wx.OK | wx.ICON_ERROR)
            raise e

    src_voice_dir = os.path.join(src_dir, "Voices")
    if os.path.isdir(src_voice_dir):
        for file in os.listdir(src_voice_dir):
            try:
                os.remove(os.path.join(src_voice_dir, file))
            except Exception as e:
                log.warn(f"Hear2Read Indic unable to remove file from addon dir: "
                         f"{file}, Exception: {e}")

    move_old_voices()

    # We have renamed the addon to conform with the rule of having no spaces
    # We will try to remove the older addon
    old_addon_dir = os.path.join(os.path.dirname(_dir), "Hear2Read NG")
    if os.path.isdir(old_addon_dir):
        log.info("Found older version of Hear2ReadNG, removing the addon")
        try:
            shutil.rmtree(old_addon_dir)
        except:
            log.warn("Hear2ReadNG was unable to remove the old addon. Please "
                     "remove manually")

def onUninstall():
    log.info("Hear2Read Indic uninstalling...")
    h2r_dll_update_file = H2RNG_ENGINE_DLL_PATH+".update"
    if os.path.isfile(H2RNG_UPDATE_FLAG):
            os.remove(H2RNG_UPDATE_FLAG)

    if os.path.isfile(h2r_dll_update_file):
        # remove the update flag file so uninstall has the desired effect
        # subsequently
        log.info("Hear2Read update. Ignoring uninstall tasks")
        try:
            log.info("Hear2Read update from onUninstall")
            shutil.move(h2r_dll_update_file, H2RNG_ENGINE_DLL_PATH)
        except Exception as e:
            log.error(f"Unable to install Hear2Read TTS Engine! {e}")
        return
    try:
        shutil.rmtree(H2RNG_DATA_DIR)
    except Exception as e:
        log.warn(f"Error removing Hear2Read Indic files on uninstall: {e}")