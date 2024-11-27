# A part of the Hear2Read NG voices addon for NVDA
# Copyright (C) 2013-2024, Hear2Read Project Contributors
# See the file COPYING for more details.

import os
import shutil
import urllib.request
from dataclasses import dataclass
from threading import Thread

import gui
import wx
from logHandler import log

from synthDrivers._H2R_NG_Speak import (
    EN_VOICE_ALOK,
    H2RNG_DATA_DIR,
    H2RNG_ENGINE_DLL_PATH,
    H2RNG_PHONEME_DIR,
    H2RNG_VOICES_DIR,
    H2RNG_WAVS_DIR,
)

try:
    _dir=os.path.dirname(__file__.decode("mbcs"))
except AttributeError:
    _dir=os.path.dirname(__file__)

_dir = os.path.abspath(os.path.join(_dir, os.pardir, os.pardir))
    
OLD_H2RNG_DATA_DIR = os.path.join(os.environ['ALLUSERSPROFILE'], 
                                  "Hear2Read-ng")

def check_files():
    """
    Checks whether the files and directories vital to Hear2Read NG are 
    present

    @return: returns True only if the engine DLL, the phoneme data dir
    and the English voice files are present
    @rtype: bool
    """
    dll_is_present = False
    phonedir_is_present = False
    eng_voice_is_present = False

    try:
        if os.path.isfile(H2RNG_ENGINE_DLL_PATH):
            dll_is_present = True

        if os.listdir(H2RNG_PHONEME_DIR):
            phonedir_is_present = True

        eng_model_file = os.path.join(H2RNG_VOICES_DIR, 
                                    f"{EN_VOICE_ALOK}.onnx")
        if os.path.isfile(eng_model_file) and os.path.isfile(
                                                f"{eng_model_file}.json"):
            eng_voice_is_present = True
    except Exception as e:
        log.warn(f"Hear2Read NG check failed with exception: {e}")
            
    return dll_is_present and phonedir_is_present and eng_voice_is_present


def move_old_voices():
    """Tries to move voices downloaded in addon version 1.4 and lower to the 
    new dir structure to be usable by this addon. This is slightly different 
    from the version in installTasks as it prompts to restart NVDA if voices
    have been moved and updated

    @return: returns True if any voices from an older version (<v1.5) have been
    moved to this version successfully
    @rtype: bool
    """
    old_voices_dir = os.path.join(OLD_H2RNG_DATA_DIR, "Voices")
    voices_moved = False

    if os.path.isdir(OLD_H2RNG_DATA_DIR):
        # try moving old voices
        for file in os.listdir(old_voices_dir):
            try:
                src_path = os.path.join(old_voices_dir, file)
                dst_path = os.path.join(H2RNG_VOICES_DIR, file)
                if not file.startswith("en") and not os.path.isfile(dst_path):
                    shutil.copy2(src=src_path, dst=dst_path)
                    voices_moved = True
                os.remove(src_path)
            except Exception as e:
                log.warn("Hear2Read NG unable to remove old voice file: "
                         f"{file}")
        
        old_wavs_dir = os.path.join(OLD_H2RNG_DATA_DIR, "wavs")

        if os.path.isdir(old_wavs_dir):
            try:
                shutil.copytree(src=old_wavs_dir, dst=H2RNG_WAVS_DIR, 
                                dirs_exist_ok=True)
            except Exception as e:
                log.warn("Hear2Read NG unable to copy old wav folders")

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
                dirname = os.path.basename(dir)
                log.warn(f"Hear2Read NG unable to remove old folder: {dirname}")

        try:
            shutil.rmtree(OLD_H2RNG_DATA_DIR)
        except Exception as e:
            log.warn("Hear2Read NG unable to remove old Hear2Read data folder")
            
    return voices_moved


def onInstall():
    """A fallback that tries moving the required data files in case it wasn't
    done by installTasks.py

    @raises e: raises any exceptions that can occur while transferring the data
    @return: returns True if any voices from an older version (<v1.5) have been
    moved to this version successfully
    @rtype: bool
    """
    log.info("onInstall from manager")

    src_dir = os.path.join(_dir, "res")

    try:
        shutil.copytree(src=src_dir, dst=H2RNG_DATA_DIR, dirs_exist_ok=True)
        shutil.rmtree(src_dir)
    except Exception as e:
        log.warn(f"Error installing Hear2Read NG data files: {e}")
        if "Hear2ReadNG_addon_engine.dll" in str(e):
            gui.messageBox(
                # Translators: message telling the user that Hear2Read NG was not installed correctly
                _("Unable to update Hear2Read NG while it is running in NVDA\n"
                    "Please switch to a different synthesizer, restart NVDA "
                    "and retry"),
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

    return move_old_voices()

@dataclass
class Voice:
    """Dataclass encapsulating voice related variables:
    
    @param id: the voice id: used for voice files and in NVDA
    @param lang_iso: the 2 letter ISO code of the language
    @param display_name: name of the language in English, for display
    @param state: action on click in voice manager. One of 
    {"Download", "Remove", "Update"}
    @param extra: boolean storing whether the extra zip file is present for 
    download
    """
    id: str
    lang_iso: str
    display_name: str
    state: str
    extra: bool=False


class DownloadThread(Thread):
    """Subclass of Thread to run downloads in the background. It accepts a list 
    of downloads to perform, a list of tuples (<file location>, <download url>)

    @param Thread: the thread on which to run the download
    @type Thread: threading.Thread
    """
    def __init__(self, download_queue, cancel_event, progress_callback,
                 complete_callback, cancel_callback):
        """_summary_

        @param download_queue: list of tuples(pairs) of strings containing 
        filename as first element and download URL as second 
        @type download_queue: list(tuple(string, string))
        @param cancel_event: threading event that is set if the cancel button is 
        pressed
        @type cancel_event: threading.Event
        @param progress_callback: callback to update progress of download. 
        Updates percent of file downloaded
        @type progress_callback: function
        @param complete_callback: called on successful completion of download
        @type complete_callback: function
        @param cancel_callback: called on interruption of download. Takes an 
        optional error message if download is interrupted due to an Exception
        @type cancel_callback: function(error_message=None)
        """
        super().__init__()
        
        self.download_queue = download_queue
        self.cancel_event = cancel_event
        self.progress_callback = progress_callback
        self.complete_callback = complete_callback
        self.cancel_callback = cancel_callback

    def run(self):
        try:
            for download in self.download_queue:
                with urllib.request.urlopen(download[1]) as response:
                    total_size = response.length
                    with open(download[0], 'wb') as out_file:
                        downloaded = 0
                        while not self.cancel_event.is_set():
                            chunk = response.read(8192)
                            if not chunk:
                                break
                            
                            out_file.write(chunk)
                            downloaded += len(chunk)

                            percent = min(int(downloaded * 100 / total_size), 100)
                            wx.CallAfter(self.progress_callback, percent)

                        if self.cancel_event.is_set():
                            wx.CallAfter(self.cancel_callback)
                            return
                        
            wx.CallAfter(self.complete_callback)
            
        except Exception as e:
            wx.CallAfter(self.cancel_callback, error_message=str(e))

    def cancel(self):
        self.cancel_event.set() 

