# coding: utf-8

# Copyright (c) 2023 Musharraf Omer
# This file is covered by the GNU General Public License.

# A part of the Hear2Read Indic Voices addon for NVDA
# Copyright (C) 2013-2024, Hear2Read Project Contributors
# See the file COPYING for more details.

# this is a slightly modified version of the corresponding file in the sonata
# project (https://github.com/mush42/sonata-nvda)

from threading import Thread
from urllib import request

import core
import globalPluginHandler
import gui
import queueHandler
import wx
from gui.message import DisplayableError
from logHandler import log
from synthDriverHandler import findAndSetNextSynth, getSynth, synthChanged

from globalPlugins.hear2readng_global_plugin.english_settings import (
    EnglishSpeechSettingsDialog,
)
from globalPlugins.hear2readng_global_plugin.utils import (
    H2RNG_VOICE_LIST_URL,
    parse_server_voices,
)
from globalPlugins.hear2readng_global_plugin.voice_manager import (
    Hear2ReadNGVoiceManagerDialog,
)

# from .voice_manager import Hear2ReadNGVoiceManagerDialog


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__voice_manager_shown = False
        curr_synth_name = getSynth().name
        self._voice_checker = lambda: wx.CallLater(2000, 
                                                    self._perform_checks)
        core.postNvdaStartup.register(self._voice_checker)

        # if "Hear2Read NG" not in curr_synth_name:
        #     self._voice_checker = lambda: wx.CallLater(2000, 
        #                                             self._perform_voice_check)
        #     core.postNvdaStartup.register(self._voice_checker)

        self.itemHandle = gui.mainFrame.sysTrayIcon.menu.Insert(
            4,
            wx.ID_ANY,
            # Translators: label of a menu item
            _("Hear2Read Voice Manager..."),
            # Translators: Hear2Read Indic's voice manager menu item help
            _("Open the voice manager to download Hear2Read Indic voices"),
        )
        gui.mainFrame.sysTrayIcon.menu.Bind(wx.EVT_MENU, self.on_manager, 
                                            self.itemHandle)
        
        self.eng_settings_active = False
        self.eng_settings_id = wx.Window.NewControlId()

        if "Hear2Read NG" in curr_synth_name:
            # self.eng_settings_id = wx.Window.NewControlId()
            self.make_eng_settings_menu()
            self.eng_settings_active = True
        
        synthChanged.register(self.on_synth_changed)
            
    def on_synth_changed(self, synth):
        if "Hear2Read NG" in synth.name:
            # self.eng_settings_id = wx.Window.NewControlId()
            self.make_eng_settings_menu()
            self.eng_settings_active = True
            self._perform_voice_check()
            
        elif self.eng_settings_active:
            gui.mainFrame.sysTrayIcon.menu.Remove(self.eng_settings_id)
            self.eng_settings_active = False

    def make_eng_settings_menu(self):
        self.itemHandle = gui.mainFrame.sysTrayIcon.menu.Insert(
                5,
                self.eng_settings_id,
                # Translators: label of a menu item
                _("Hear2Read English Voice Settings..."),
                # Translators: Hear2Read Indic's voice manager menu item help
                _("Open the settings for the English voice used in Hear2Read"),
            )
        gui.mainFrame.sysTrayIcon.menu.Bind(wx.EVT_MENU,
                                lambda e : gui.mainFrame.popupSettingsDialog(
                                    EnglishSpeechSettingsDialog), 
                                self.itemHandle)

    def on_manager(self, event=None):
        manager_dialog = Hear2ReadNGVoiceManagerDialog()
        try:
            gui.runScriptModalDialog(manager_dialog, callback=self.on_manager_close)
            self.__voice_manager_shown = True
        except Exception as e:
            log.error(f"Failed to open Manager: {e}")

    def on_manager_close(self, res):
        if not any(Hear2ReadNGVoiceManagerDialog.get_installed_voices()):
            self.on_no_voices(getSynth().name)

    def on_no_voices(self, curr_synth_name):
        
        if "Hear2Read NG" in curr_synth_name:    
            msg_res = gui.messageBox(
                # Translators: message telling the user that no voice is installed
                _(
                    "No Indic Hear2Read voice was found.\n"
                    "Please download a voice from the manager to continue using Hear2Read Synthesizer.\n"
                    "Do you want to open the voice manager now?"
                ),
                # Translators: title of a message telling the user that no Hear2Read Indic voice was found
                _("Hear2Read Indic Voices"),
                wx.YES_NO | wx.ICON_WARNING,)
            
            if msg_res == wx.YES:
                wx.CallAfter(self.on_manager)
            else:
                noVoiceDisplayError = DisplayableError(
                    titleMessage="Shutting Hear2Read Down", 
                    displayMessage="No Hear2Read voices found. \n"
                    "Please install voices to use Hear2Read. \n"
                    "Voices can be installed from the Hear2Read voice manager in the NVDA menu")
                noVoiceDisplayError.displayError(gui.mainFrame)
                queueHandler.queueFunction(queueHandler.eventQueue, findAndSetNextSynth, curr_synth_name)
        else:
            if wx.YES == gui.messageBox(
                # Translators: message telling the user that no voice is installed
                _(
                    "No Indic Hear2Read voice was found.\n"
                    "Please select a Hear2Read voice to download from the manager.\n"
                    "Do you want to open the voice manager now?"
                ),
                # Translators: title of a message telling the user that no Hear2Read Indic voice was found
                _("Hear2Read Indic Voices"),
                wx.YES_NO | wx.ICON_WARNING,):
                wx.CallAfter(self.on_manager)

    def on_voice_update(self, lang):

        if self.__voice_manager_shown:# or gui.isModalMessageBoxActive():
            return
        
        if wx.YES == gui.messageBox(
                # Translators: message telling the user that no voice is installed
                _(
                    f"Update found for installed {lang} Hear2Read voice.\n"
                    "Updated voice is available in the Hear2Read voice manager.\n"
                    "Do you want to open the voice manager now?"
                ),
                # Translators: title of a message telling the user that no Hear2Read Indic voice was found
                _("Hear2Read Voice Update"),
                wx.YES_NO | wx.ICON_INFORMATION,):
            wx.CallAfter(self.on_manager)

    def _perform_checks(self):
        
        self._perform_voice_check()
        
        if self.__voice_manager_shown:
            return
        
        self._perform_voice_update_check()

    # @gui.blockAction.when(gui.blockAction.Context.MODAL_DIALOG_OPEN)         
    def _perform_voice_check(self):
        if self.__voice_manager_shown:
            return

        if not any(Hear2ReadNGVoiceManagerDialog.get_installed_voices()):
            curr_synth_name = getSynth().name
            # queueHandler.queueFunction(queueHandler.eventQueue, self.on_no_voices, curr_synth_name)
            self.on_no_voices(curr_synth_name)

    
    def _perform_voice_update_check(self):
        """Populated the list of voices available on the server. Modifies the 
        class attribute server_voices, a list of Voice objects. The operation
        is done in a background thread while a BusyInfo is displayed.
        """
        # fetch_complete_event = Event()
        if self.__voice_manager_shown:# or gui.isModalMessageBoxActive():
            return

        def fetch():
            """Main function to fetch the voice list from the server. Sets the
            server_error_event/network_error_event attribute in case of failure 
            """
            try:
                with request.urlopen(H2RNG_VOICE_LIST_URL) as response:
                    resp_str = response.read().decode('utf-8')
                    server_voices = parse_server_voices(resp_str)
                    if server_voices:
                        installed_voices = Hear2ReadNGVoiceManagerDialog.get_installed_voices()
                        for iso, installed_voice in installed_voices.items():
                            server_voice = server_voices.get(iso, None)
                            if server_voice and server_voice.id != installed_voice.id:
                                log.info(f"checking update on {installed_voice.id}, found: {server_voice.id}")
                                self.on_voice_update(server_voice.display_name)
                                return
            except Exception as e:
                log.warn(f"Hear2Read unable to access internet to check voice updates: {e}")
            # finally:
            #     fetch_complete_event.set()

        Thread(target=fetch).start()

    def terminate(self):
        try:
            gui.mainFrame.sysTrayIcon.menu.DestroyItem(self.itemHandle)
        except:
            pass
