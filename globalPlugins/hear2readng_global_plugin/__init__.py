# coding: utf-8

# Copyright (c) 2023 Musharraf Omer
# This file is covered by the GNU General Public License.

# A part of the Hear2Read Indic Voices addon for NVDA
# Copyright (C) 2013-2024, Hear2Read Project Contributors
# See the file COPYING for more details.

# this is a slightly modified version of the corresponding file in the sonata
# project (https://github.com/mush42/sonata-nvda)

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
                                                    self._perform_voice_check)
        core.postNvdaStartup.register(self._voice_checker)

        # if "Hear2Read NG" not in curr_synth_name:
        #     self._voice_checker = lambda: wx.CallLater(2000, 
        #                                             self._perform_voice_check)
        #     core.postNvdaStartup.register(self._voice_checker)

        self.itemHandle = gui.mainFrame.sysTrayIcon.menu.Insert(
            4,
            wx.ID_ANY,
            # Translators: label of a menu item
            _("Hear2Read Voice Downloader..."),
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

    # @gui.blockAction.when(gui.blockAction.Context.MODAL_DIALOG_OPEN)         
    def _perform_voice_check(self):
        if self.__voice_manager_shown:# or gui.isModalMessageBoxActive():
            return

        if not any(Hear2ReadNGVoiceManagerDialog.get_installed_voices()):
            curr_synth_name = getSynth().name
            # queueHandler.queueFunction(queueHandler.eventQueue, self.on_no_voices, curr_synth_name)
            self.on_no_voices(curr_synth_name)

    def terminate(self):
        try:
            gui.mainFrame.sysTrayIcon.menu.DestroyItem(self.itemHandle)
        except:
            pass
