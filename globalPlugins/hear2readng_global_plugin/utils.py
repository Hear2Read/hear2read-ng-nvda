# A part of the Hear2Read Indic Voices addon for NVDA
# Copyright (C) 2013-2024, Hear2Read Project Contributors
# See the file COPYING for more details.

import os
import shutil
import sys
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

# H2RNG_DATA_DIR = os.path.join(os.getenv("APPDATA"), "Hear2Read-NG")
# H2RNG_PHONEME_DIR = os.path.join(H2RNG_DATA_DIR, "espeak-ng-data")
# H2RNG_ENGINE_DLL_PATH = os.path.join(H2RNG_DATA_DIR, "Hear2ReadNG_addon_engine.dll")
# H2RNG_VOICES_DIR = os.path.join(H2RNG_DATA_DIR, "Voices")
# H2RNG_WAVS_DIR = os.path.join(H2RNG_DATA_DIR, "wavs")
# EN_VOICE_ALOK = "en_US-arctic-medium"

lang_names = {"as":"Assamese", 
                "bn":"Bengali", 
                "gu":"Gujarati", 
                "hi":"Hindi", 
                "kn":"Kannada", 
                "ml":"Malayalam", 
                "mr":"Marathi", 
                "ne":"Nepali", 
                "or":"Odia", 
                "pa":"Punjabi", 
                "si":"Sinhala",
                "ta":"Tamil", 
                "te":"Telugu", 
                "en":"English"}

# URL suffix for voice files
H2RNG_VOICES_DOWNLOAD_HTTP = "https://hear2read.org/Hear2Read/voices-piper/"
# voice list URL
H2RNG_VOICE_LIST_URL = "https://hear2read.org/nvda-addon/getH2RNGVoiceNames.php"

try:
    _dir=os.path.dirname(__file__.decode("mbcs"))
except AttributeError:
    _dir=os.path.dirname(__file__)

_dir = os.path.abspath(os.path.join(_dir, os.pardir, os.pardir))
    
OLD_H2RNG_DATA_DIR = os.path.join(os.environ['ALLUSERSPROFILE'], 
                                  "Hear2Read-ng")

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


def check_files():
    """
    Checks whether the files and directories vital to Hear2Read Indic are 
    present

    @return: returns True only if the engine DLL, the phoneme data dir
    and at least one voice are present
    @rtype: bool
    """
    # dll_is_present = False
    # phonedir_is_present = False
    # voice_is_present = False

    try:
        if not os.path.isfile(H2RNG_ENGINE_DLL_PATH):
            return False
            # dll_is_present = True

        if not os.listdir(H2RNG_PHONEME_DIR):
            return False
            # phonedir_is_present = True

    except Exception as e:
        log.warn(f"Hear2Read Indic check failed with exception: {e}")
        return False
            
    return True
    # return dll_is_present and phonedir_is_present and voice_is_present


def parse_server_voices(resp_str):
    """Parses the pipe separated file list response from the server

    @param resp_str: string of pipe separated voice related files
    @type resp_str: string
    """
    server_voices = {}
    server_files = resp_str.split('|')
    for file in server_files:
        if file.startswith("en"):
            continue
        parts = file.split(".")
        if parts[-1] == "onnx":
            if f"{file}.json" in server_files:
                iso_lang = parts[0].split("-")[0].split("_")[0]
                extra = False
                if f"{file}.zip" in server_files:
                    extra = True
                if iso_lang in lang_names.keys():
                    server_voices[iso_lang] = Voice(id=parts[0], 
                            lang_iso=iso_lang,
                            display_name=lang_names[iso_lang],
                            state="Download", 
                            extra=extra)
                else:
                    server_voices[iso_lang] = Voice(id=parts[0], 
                            lang_iso=iso_lang,
                            display_name=f"Unknown Lang ({iso_lang})",
                            state="Download", 
                            extra=extra)

    return server_voices


def populateVoices():
    pathName = os.path.join(H2RNG_VOICES_DIR)
    voices = dict()
    #list all files in Language directory
    file_list = os.listdir(pathName)
    #FIXME: the english voice is obsolete, maybe remove the voiceid?
    en_voice = EN_VOICE_ALOK
    voices[en_voice] = "English"
    for file in file_list:
        list = file.split(".")
        if list[-1] == "onnx":
            if f"{file}.json" not in file_list:
                continue
            nameList = list[0].split("-")
            lang = nameList[0].split("_")[0]
            
            # Already set the sole English voice
            if lang == "en":
                continue
            
            language = lang_names.get(lang)
            if language:
                voices[list[0]] = language
            else:
                voices[list[0]] = f"Unknown language ({list[0]})"

    return voices

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
                log.warn("Hear2Read Indic unable to remove old voice file: "
                         f"{file}")
        
        old_wavs_dir = os.path.join(OLD_H2RNG_DATA_DIR, "wavs")

        if os.path.isdir(old_wavs_dir):
            try:
                copytree_overwrite(src=old_wavs_dir, dst=H2RNG_WAVS_DIR)
            except Exception as e:
                log.warn("Hear2Read Indic unable to copy old wav folders")

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
                log.warn(f"Hear2Read Indic unable to remove old folder: {dirname}")

        try:
            shutil.rmtree(OLD_H2RNG_DATA_DIR)
        except Exception as e:
            log.warn("Hear2Read Indic unable to remove old Hear2Read data folder")
            
    return voices_moved

# def show_voice_manager():

def onInstall():
    """A fallback that tries moving the required data files in case it wasn't
    done by installTasks.py It is duplicated as importing is not available with
    installTasks.py

    @raises e: raises any exceptions that can occur while transferring the data
    @return: returns True if any voices from an older version (<v1.5) have been
    moved to this version successfully
    @rtype: bool
    """
    # log.info("onInstall from manager")

    src_dir = os.path.join(_dir, "res")

    try:
        copytree_overwrite(src=src_dir, dst=H2RNG_DATA_DIR)
        shutil.rmtree(src_dir)
    except Exception as e:
        log.warn(f"Error installing Hear2Read Indic data files: {e}")
        if "Hear2ReadNG_addon_engine.dll" in str(e):
            gui.messageBox(
                # Translators: message telling the user that Hear2Read Indic was not installed correctly
                _("Unable to update Hear2Read Indic while it is running in NVDA\n"
                    "Please switch to a different synthesizer, restart NVDA "
                    "and retry"),
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

