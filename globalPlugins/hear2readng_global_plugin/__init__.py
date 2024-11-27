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
import wx
from logHandler import log

from .voice_manager import Hear2ReadNGVoiceManagerDialog


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
    #TODO simplify to rhvoice version
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__voice_manager_shown = False
        self._voice_checker = lambda: wx.CallLater(2000, 
                                                   self._perform_voice_check)
        core.postNvdaStartup.register(self._voice_checker)
        self.itemHandle = gui.mainFrame.sysTrayIcon.menu.Insert(
            4,
            wx.ID_ANY,
            # Translators: label of a menu item
            _("Hear2Read Indic &voice manager..."),
            # Translators: Hear2ReadNG's voice manager menu item help
            _("Open the voice manager to download Hear2Read Indic voices"),
        )
        gui.mainFrame.sysTrayIcon.menu.Bind(wx.EVT_MENU, self.on_manager, self.itemHandle)

    def on_manager(self, event):
        manager_dialog = Hear2ReadNGVoiceManagerDialog()
        try:
            gui.runScriptModalDialog(manager_dialog)
            self.__voice_manager_shown = True
        except Exception as e:
            log.error(f"Failed to open Manager: {e}")

    def _perform_voice_check(self):
        if self.__voice_manager_shown:
            return

        if not any(Hear2ReadNGVoiceManagerDialog.get_installed_voices()):

            if wx.YES == gui.messageBox(
                # Translators: message telling the user that no voice is installed
                _(
                    "No Indic Hear2ReadNG voice was found.\n"
                    "You can download Indic voices from the voice manager.\n"
                    "Do you want to open the voice manager now?"
                ),
                # Translators: title of a message telling the user that no Hear2ReadNG voice was found
                _("Hear2Read Indic Voices"),
                wx.YES_NO | wx.ICON_WARNING,):

                self.on_manager(None)


    def terminate(self):
        try:
            gui.mainFrame.sysTrayIcon.menu.DestroyItem(self.itemHandle)
        except:
            pass
