# A part of the Hear2Read Indic Voices addon for NVDA
# Copyright (C) 2013-2024, Hear2Read Project Contributors
# See the file COPYING for more details.

import os
import shutil
import sys
import urllib.request
from dataclasses import dataclass
from glob import glob
from io import StringIO
from pathlib import Path
from threading import Thread

import addonHandler
import config
import globalVars
import gui
import windowUtils
import wx
from configobj import ConfigObj
from configobj.validate import Validator
from gui.contextHelp import ContextHelpMixin
from gui.guiHelper import (
    BORDER_FOR_DIALOGS,
    SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS,
    BoxSizerHelper,
    ButtonHelper,
)
from logHandler import log

from .file_utils import (
    ADDON_NAME,
    EN_VOICE_ALOK,
    H2RNG_DATA_DIR,
    H2RNG_DLL_NAME,
    H2RNG_ENGINE_DLL_PATH,
    H2RNG_ENGINE_UPDATE_PATH,
    H2RNG_PHONEME_DIR,
    H2RNG_VOICES_DIR,
    H2RNG_WAVS_DIR,
)

LOG_TAG = f"{ADDON_NAME}-{os.path.basename(__file__).removesuffix(".py")}"

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
                "sa":"Sanskrit",
                "si":"Sinhala",
                "ta":"Tamil", 
                "te":"Telugu", 
                "en":"English"}


_curAddon = addonHandler.getCodeAddon()
# URL suffix for voice files
H2RNG_VOICES_DOWNLOAD_HTTP = "https://hear2read.org/Hear2Read/voices-piper/"
# H2RNG_VOICES_DOWNLOAD_HTTP = "https://hear2read.org/Hear2Read/voices-piper/phone_dur/"
# voice list URL
H2RNG_VOICE_LIST_URL = "https://hear2read.org/nvda-addon/getH2RNGVoiceNames.php"
# H2RNG_VOICE_LIST_URL = "https://hear2read.org/nvda-addon/getH2RNG2VoiceNames.php"
H2RNG_UPDATE_FLAG = H2RNG_DATA_DIR / "pendingUpdate"
H2RNG_CONFIG_FILE = H2RNG_DATA_DIR / "h2rng.ini"
# config section
SCT_General = "General"
SCT_EngSynth = "English"
# general section items
ID_ShowStartupPopup = "ShowStartupPopup"
# English synth section items
ID_EnglishSynthName = "EnglishSynthName"
ID_EnglishSynthVoice = "EnglishSynthVoice"
ID_EnglishSynthVariant = "EnglishSynthVariant"
ID_EnglishSynthRate = "EnglishSynthRate"
ID_EnglishSynthVolume = "EnglishSynthVolume"
ID_EnglishSynthPitch = "EnglishSynthPitch"
ID_EnglishSynthInflection = "EnglishSynthInflection"

try:
    _diros=os.path.dirname(__file__.decode("mbcs"))
except AttributeError:
    _diros=os.path.dirname(__file__)

_dir = Path(_diros)
_dir = _dir.parent.parent
    
#TODO: obsolete remove
OLD_H2RNG_DATA_DIR = os.path.join(os.environ['ALLUSERSPROFILE'], 
                                  "Hear2Read-ng")

# try:
#     _h2r_config = config.conf["hear2read"]
# except KeyError:
#     confspec = {
#         "engSynth": "string(default='oneCore')",
#         "engVoice": "string(default='')",
#         "engVariant": "string(default='')",
#         "engRate": "integer(default=50)",
#         "engPitch": "integer(default=50)",
#         "engVolume": "integer(default=100)",
#         "engInflection": "integer(default=80)",
#         "showStartupMsg": "boolean(default=True)"
#     }
    
#     config.conf.spec["hear2read"] = confspec
#     config.conf.validate(config.conf.validator)
#     _h2r_config = config.conf["hear2read"]

class H2RConfigManager():
    """Class to save Hear2Read addon related config parameters. Used as a
    singleton.

    The code has been adapted from the code in the wordAccessEnhancement addon 
    """
    _GeneralConfSpec = """[{section}]
    {showStartupPopup} = boolean(default=True)
    """.format(
        section=SCT_General,
        showStartupPopup=ID_ShowStartupPopup)

    _EngSynthConfSpec = """[{section}]
    {englishSynthName} = string(default='oneCore')
    {englishSynthVoice} = string(default='')
    {englishSynthVariant} = string(default='')
    {englishSynthRate} = integer(default=50)
    {englishSynthVolume} = integer(default=100)
    {englishSynthPitch} = integer(default=50)
    {englishSynthInflection} = integer(default=80)
    """.format(
        section=SCT_EngSynth,
        englishSynthName = ID_EnglishSynthName, 
        englishSynthVoice = ID_EnglishSynthVoice,
        englishSynthVariant = ID_EnglishSynthVariant,
        englishSynthRate = ID_EnglishSynthRate,
        englishSynthVolume = ID_EnglishSynthVolume,
        englishSynthPitch = ID_EnglishSynthPitch,
        englishSynthInflection = ID_EnglishSynthInflection)

    configspec = ConfigObj(StringIO("""# addon Configuration File
    {0}{1}""".format(_GeneralConfSpec, _EngSynthConfSpec)
    ), list_values=False, encoding="UTF-8")

    def __init__(self):
        self.loadSettings()
        config.post_configSave.register(self.handlePostConfigSave)

    def __getitem__(self, key):
        return self.addonConfig[key]

    def __contains__(self, key):
        return key in self.addonConfig

    def get(self, key, default=None):
        return self.addonConfig.get(key, default)

    def __setitem__(self, key, val):
        self.addonConfig[key] = val

    def loadConfig(self, file):
        config_out = ConfigObj(file,
            configspec=self.configspec,
            encoding='utf-8',
            default_encoding='utf-8')
        config_out.newlines = "\r\n"
        # config_out._errors = []
        val = Validator()
        result = config_out.validate(val, copy=True, preserve_errors=True)     
        if type(result) is not dict:
            result = None
        return config_out, result
    
    def loadSettings(self):
        self.parse_old_config()
        if H2RNG_CONFIG_FILE.exists():
            # there is allready a config file
            try:
                h2r_config, errors = self.loadConfig(H2RNG_CONFIG_FILE)
                if errors:
                    e = Exception("Error parsing configuration file:\n%s" % h2r_config.errors)
                    raise e
            except Exception as e:
                log.warning(f"{LOG_TAG}: {e}")
                # error on reading config file, so delete it
                os.remove(H2RNG_CONFIG_FILE)
                log.warning(f"{LOG_TAG}: Hear2Read Addon configuration file error: configuration " 
                           "reset to factory defaults")
        if H2RNG_CONFIG_FILE.exists():
            self.addonConfig, errors = self.loadConfig(H2RNG_CONFIG_FILE)
            # if self.addonConfig.errors:
            #     log.warning(self.addonConfig.errors)
            #     log.warning(
            #         "Hear2Read Addon configuration file error: configuration reset to factory defaults")
            #     os.remove(H2RNG_CONFIG_FILE)
            #     self.warnConfigurationReset()
            #     # reset configuration to factory defaults
            #     self.addonConfig =\
            #         self._versionToConfiguration[self._currentConfigVersion](None)
            #     self.addonConfig.filename = H2RNG_CONFIG_FILE
        else:
            # no add-on configuration file found
            self.addonConfig, errors = self.loadConfig(None)
            self.addonConfig.filename = H2RNG_CONFIG_FILE
        
        if not H2RNG_CONFIG_FILE.exists():
            self.saveSettings(True)

    def parse_old_config(self):
        """TODO: populate config saved in beta versions 1.6 to 1.7
        """
        pass

    def handlePostConfigSave(self):
        self.saveSettings(True)

    def canConfigurationBeSaved(self, force):
        # Never save config or state if running securely or if running from the launcher.
        try:
            # for NVDA version >= 2023.2
            from NVDAState import shouldWriteToDisk
            writeToDisk = shouldWriteToDisk()
        except ImportError:
            # for NVDA version < 2023.2
            writeToDisk = not (globalVars.appArgs.secure or globalVars.appArgs.launcher)
        if not writeToDisk:
            log.debug(f"{LOG_TAG}: Not writing add-on configuration, either --secure or --launcher "
                      "args present")
            return False
        # after an add-on removing, configuration is deleted
            # so  don't save configuration if there is no nvda restart
        if _curAddon.isPendingRemove:
            return False
        # We don't save the configuration, in case the user
            # would not have checked the "Save configuration on exit
            # " checkbox in General settings and force is False
        if not force and not config.conf['general']['saveConfigurationOnExit']:
            return False
        return True

    def saveSettings(self, force=False):
        if self.addonConfig is None:
            return
        if not self.canConfigurationBeSaved(force):
            return
        try:
            val = Validator()
            self.addonConfig.validate(val, copy=True)
            self.addonConfig.write()
            log.warning(f"{LOG_TAG}: configuration saved")
        except Exception:
            log.warning(f"{LOG_TAG}:  Could not save configuration - probably read only file system")

    def terminate(self):
        self.saveSettings()
        config.post_configSave.unregister(self.handlePostConfigSave)

_h2r_config = H2RConfigManager()

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

def postUpdateCheck():
    """Check if Hear2Read is being run post addon update, and rename the 
    updated dll file
    """
    h2r_dll_update_file = str(H2RNG_ENGINE_DLL_PATH)+".update"
    try:
        os.remove(H2RNG_UPDATE_FLAG)
    except:
        pass
    try:
        # log.info(f"{LOG_TAG}: update from postUpdateCheck")
        shutil.move(h2r_dll_update_file, H2RNG_ENGINE_DLL_PATH)
    except FileNotFoundError:
        # log.info(f"{LOG_TAG}: Not post update, doing nothing")
        pass

def check_files():
    """
    Checks whether the files and directories vital to Hear2Read Indic are 
    present

    @return: returns True only if the engine DLL, the phoneme data dir
    and at least one voice are present
    @rtype: bool
    """

    postUpdateCheck()

    try:
        if not H2RNG_ENGINE_DLL_PATH.is_file():
            log.error(f"{LOG_TAG}: check_files failed: dll doesn't exist: {H2RNG_ENGINE_DLL_PATH}")
            return False

        if not H2RNG_PHONEME_DIR.is_dir():
            log.error(f"{LOG_TAG}: check_files failed: phoneme data doesn't exist: {H2RNG_PHONEME_DIR}")
            return False

    except Exception as e:
        log.warn(f"{LOG_TAG}: check_files failed with exception: {e}")
        return False
            
    return True


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
    """Checks and populates voice list based on the files present in the voice
    directory

    @return: Dictionary of voice files keyed by the iso2 code of the language
    @rtype: dict
    """
    remove_duplicate_voices()
    voices = dict()
    #list all files in Language directory
    file_list = os.listdir(H2RNG_VOICES_DIR)
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

def remove_duplicate_voices():
    """Ensures only one voice per language is present. Retains only the last
    voice file when sorted alphabetically
    """
    file_list = glob("*.onnx", root_dir=H2RNG_VOICES_DIR)
    iso2_set = set()
    for file in file_list:
        iso2 = file.split("-")[0]
        iso2_set.add(iso2)

    # log.info(f"{LOG_TAG}: got lang list: {iso2_set}")

    for iso2 in iso2_set:
        lang_voices = sorted(glob(f"{iso2}*.onnx", root_dir=H2RNG_VOICES_DIR))
        if len(lang_voices) > 1:
            for f in lang_voices[:-1]:
                json_file = f + ".json"
                log.warn(f"{LOG_TAG}: Found duplicate voice, deleting: {f}")
                os.remove(H2RNG_VOICES_DIR / f)
                if (H2RNG_VOICES_DIR / json_file).exists():
                    os.remove(H2RNG_VOICES_DIR / json_file)


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
                dst_path = H2RNG_VOICES_DIR / file
                if not file.startswith("en") and not dst_path.is_file():
                    shutil.copy2(src=src_path, dst=dst_path)
                    voices_moved = True
                os.remove(src_path)
            except Exception as e:
                log.warn(f"{LOG_TAG}: unable to remove old voice file: {file}")
        
        old_wavs_dir = os.path.join(OLD_H2RNG_DATA_DIR, "wavs")

        if os.path.isdir(old_wavs_dir):
            try:
                copytree_overwrite(src=old_wavs_dir, dst=H2RNG_WAVS_DIR)
            except Exception as e:
                log.warn(f"{LOG_TAG}: unable to copy old wav folders")

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
                log.warn(f"{LOG_TAG}: unable to remove old folder: {dirname}")

        try:
            shutil.rmtree(OLD_H2RNG_DATA_DIR)
        except Exception as e:
            log.warn(f"{LOG_TAG}: unable to remove old Hear2Read data folder")
            
    return voices_moved

# def show_voice_manager():

def onInstall():
    """A fallback that tries moving the required data files in case it wasn't
    done by installTasks.py It is duplicated as importing is not available with
    installTasks.py. TODO: do a temporary import instead of duplicating

    @raises e: raises any exceptions that can occur while transferring the data
    @return: returns True if any voices from an older version (<v1.5) have been
    moved to this version successfully
    @rtype: bool
    """
    # log.info("onInstall from manager")

    # resources folder
    src_dir = _dir / "res"
    src_dll = src_dir / H2RNG_DLL_NAME

    # nothing can be done if there is no directory
    if not src_dir.is_dir():
        return

    # First check if update, i.e., H2RNG_DATA_DIR exists.
    if H2RNG_DATA_DIR.is_dir():            
        # if the data dir is already present, need to take further steps:
        # touch a file called update flag. This is to ensure proper update 
        # behaviour in NVDA - NVDA runs onUninstall when updating, deleting
        # old voices
        with open(H2RNG_UPDATE_FLAG, 'a'):
            os.utime(H2RNG_UPDATE_FLAG, None)
        try:
            # trying moving the dll first
            # log.info(f"{LOG_TAG}: Trying to move dll: {src_dir / H2RNG_DLL_NAME} -> {H2RNG_DATA_DIR / H2RNG_DLL_NAME}")
            shutil.move(src_dll, H2RNG_ENGINE_UPDATE_PATH)
            if src_dll.exists() and H2RNG_ENGINE_UPDATE_PATH.exists():
                try:
                    src_dll.unlink()
                except Exception as e:
                    log.warn(f"{LOG_TAG}: Unable to delete dll from res, might create issues: {e}")
        except Exception as e:
            log.warn(f"{LOG_TAG}: Ran into error moving files onInstall: {e}")
            if H2RNG_DLL_NAME in str(e) and not H2RNG_ENGINE_UPDATE_PATH.exists():
                log.error(f"{LOG_TAG}: Unable to install engine. Install will probably fail")
            else:
                log.warn(f"{LOG_TAG}: Unable to update Hear2Read properly. Old voices may be "
                         "deleted")
    try:
        copytree_overwrite(src=src_dir, dst=H2RNG_DATA_DIR)
        shutil.rmtree(src_dir)
    except Exception as e:
        log.warn(f"Error installing Hear2Read Indic data files: {e}")
        if H2RNG_DLL_NAME in str(e):
            # if the dll has been copied successfully, we can ignore this, as we will clean up on
            # restart
            if H2RNG_ENGINE_UPDATE_PATH.exists():
                pass
            else:
                gui.messageBox(
                    # Translators: message telling the user that Hear2Read Indic was not installed correctly
                    _("Unable to update Hear2ReadNG while it is running in NVDA\n"
                        "Please switch to a different synthesizer, restart NVDA and retry"),
                    # Translators: title of a message telling the user that Hear2Read Indic was not installed correctly
                    _("Hear2ReadNG Install Error"),
                    wx.OK | wx.ICON_ERROR)
                raise e

    src_voice_dir = src_dir / "Voices"
    if src_voice_dir.is_dir():
        for file in os.listdir(src_voice_dir):
            try:
                os.remove(src_voice_dir / file)
            except Exception as e:
                log.warn(f"{LOG_TAG}: unable to remove file from addon dir: {file}, {e}")

    move_old_voices()

    # We have renamed the addon to conform with the rule of having no spaces
    # We will try to remove the older addon
    old_addon_dir = _dir.parent / "Hear2Read NG"
    if old_addon_dir.is_dir():
        log.info(f"{LOG_TAG}: Found older version of Hear2ReadNG, removing the addon")
        try:
            shutil.rmtree(old_addon_dir)
        except:
            log.warn(f"{LOG_TAG}: Unable to remove the old addon. Please remove manually")

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
                            chunk = response.read(65536)
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


class _StartupInfoDialog(
    ContextHelpMixin,
    wx.Dialog  # wxPython does not seem to call base class initializer, put last in MRO
):
    """A dialog informing the user of the changes to Hear2Read regarding English
    being spoken using a different synthesizer.
    This code has been scavenged and modified from NVDA, from 
    gui.addonStoreGui.messageDialogs._SafetyWarningDialog"""

    helpId = "H2RStartup"

    def __init__(self, parent=gui.mainFrame):
        # Translators: The warning of a dialog
        super().__init__(parent, title="Hear2Read Update Info")
        mainSizer = wx.BoxSizer(wx.VERTICAL)
        sHelper = BoxSizerHelper(self, orientation=wx.VERTICAL)

        _infoText = _(
            # Translators: Info that is displayed when Hear2Read is started.
            "Hear2Read uses Microsoft OneCore as the default English TTS. This helps improve "
            "navigation since OneCore has a quicker response. English volume and rate can be "
            "changed by switching the voice to English. These parameters are separate for the "
            "English and the Indic voices. The English voice will retain these parameters after "
            "switching the voice back to Indic\n\n"

            "Users can change to a different English TTS using the Hear2Read English voice "
            "settings option in the NVDA menu (NVDA+n), where they can also modify English voice "
            "parameters, like volume and rate."
            # "Hear2Read uses Microsoft OneCore as the default English TTS. This helps improve "
            # "navigation since OneCore has a quicker response.\n\n"

            # "Users can change the English TTS using the Hear2Read English voice settings option in " 
            # "the NVDA menu (NVDA+n), where they can also modify English voice parameters, like "
            # "volume and rate. These parameters are separate for the English and the Indic "
            # "voices.\n\n"

            # "Alternatively, to change the English volume and rate, the user can switch the voice "
            # "to English and make the changes. The English voice will retain these parameters after "
            # "switching the voice back to Indic."
        )

        sText = sHelper.addItem(wx.StaticText(self, label=_infoText))
        # the wx.Window must be constructed before we can get the handle.
        self.scaleFactor = windowUtils.getWindowScalingFactor(self.GetHandle())
        sText.Wrap(
            # 600 was fairly arbitrarily chosen by a visual user to look acceptable on their machine.
            self.scaleFactor * 600,
        )

        sHelper.sizer.AddSpacer(SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS)

        self.dontShowAgainCheckbox = sHelper.addItem(
            wx.CheckBox(
                self,
                label=_(
                    # Translators: The label of a checkbox in the startup info dialog
                    "&Don't show this message again"
                ),
            ),
        )

        bHelper = sHelper.addDialogDismissButtons(ButtonHelper(wx.HORIZONTAL))

        # Translators: The label of a button in a dialog
        okButton = bHelper.addButton(self, wx.ID_OK, label=_("&OK"))
        okButton.Bind(wx.EVT_BUTTON, self.onOkButton)

        mainSizer.Add(sHelper.sizer, border=BORDER_FOR_DIALOGS, flag=wx.ALL)
        self.Sizer = mainSizer
        mainSizer.Fit(self)
        self.CentreOnScreen()

    def onOkButton(self, evt: wx.CommandEvent):
        _h2r_config[SCT_General][ID_ShowStartupPopup] = not self.dontShowAgainCheckbox.GetValue()
        config.conf.save()
        self.EndModal(wx.ID_OK)