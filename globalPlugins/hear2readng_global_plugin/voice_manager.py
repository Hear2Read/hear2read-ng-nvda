# A part of the Hear2Read NG voices addon for NVDA
# Copyright (C) 2013-2024, Hear2Read Project Contributors
# See the file COPYING for more details.

import glob
import operator
import os
import zipfile
from functools import partial
from pathlib import Path
from threading import Event, Thread
from urllib import request

import core
import gui
import synthDriverHandler
import wx
from logHandler import log

from synthDrivers._H2R_NG_Speak import (
    H2RNG_DATA_DIR,
    H2RNG_VOICES_DIR,
    lang_names,
    populateVoices,
)

from .utils import DownloadThread, Voice, check_files, onInstall

# Constants and global variables:

DLL_FILE_NAME_PREFIX = "Hear2ReadNG_addon_engine"
DOWNLOAD_SUFFIX = ".download"

# URL suffix for voice files
H2RNG_VOICES_DOWNLOAD_HTTP = "https://hear2read.org/Hear2Read/voices-piper/"
# voice list URL
H2RNG_VOICE_LIST_URL = "https://hear2read.org/nvda-addon/getH2RNGVoiceNames.php"

# TODO remove copyright, add copyright
# TODO rename the synth file to have no spaces(?)


class Hear2ReadNGVoiceManagerDialog(wx.Dialog):
    def __init__(self, parent=gui.mainFrame, title="Hear2ReadNG voice manager"):
        """Constructor for the main window of the voice download manager. 
        Performs installation checks and initializes class attributes. Also 
        populates the list of voices to be displayed in the manager.
        """
        super().__init__(parent, title=title)

        # Check the synth files and try one time install if installTasks failed
        if not check_files():
            try:
                voices_moved = onInstall()
                # recheck after attempting install
                install_success = check_files()
            except Exception as e:
                install_success = False
            
            # Warn user and exit in case installing data failed
            if not install_success:
                gui.messageBox(
                    # Translators: message telling the user that Hear2Read NG was not installed correctly
                    _("Hear2Read NG addon not installed properly.\n"
                      "Please reinstall the addon from the file and retry.\n"),
                    # Translators: title of a message telling the user that Hear2Read NG was not installed correctly
                    _("Hear2Read NG Error"),
                    wx.OK | wx.ICON_ERROR,)
                self.Destroy()
                return
            
            # Inform user voices have been transferred and prompt NVDA restart
            if voices_moved:
                retval = gui.messageBox(
                    # Translators: content of a message box
                    _("Successfully moved voices downloaded in previous"
                        " version.\n"
                        "To use these voices, you need to restart NVDA.\n"
                        "Do you want to restart NVDA now?"),
                    # Translators: title of a message box
                    _("Voices installed"),
                        wx.YES_NO | wx.ICON_WARNING,
                    )
                if retval == wx.YES:
                    core.restart()
                    self.Destroy()

        # initialize attributes:

        # list of Voice objects of voices on the server
        self.server_voices = {}
        # list of Voice objects of voices installed
        self.installed_voices = {}
        # dictionary of Voice objects of voices that have updates, keyed by 
        # ISO 2 codes of the corresponding languages
        self.update_langs = {}
        # list of Voice objects of Voices to be displayed in the window
        self.display_voices = []
        # event set on network error
        self.network_error_event = Event()
        # thread to perform downloads on
        self.download_thread = None
        # progress dialog to show download progress
        self.progress_dialog = None

        self.get_display_voices()

        if not self.display_voices:
            gui.messageBox(
                # Translators: message telling the user that no voices are installed and no internet connection
                _("No Hear2Read NG voices installed and \n"
                  "unable to connect to the internet \n"
                  "Please check internet connection and retry "),
                # Translators: title of a message telling the user that Hear2Read NG was not installed correctly
                _("Hear2Read NG No Voices"),
                wx.OK | wx.ICON_ERROR,)
            self.Destroy()
            return

        self.setup_display()


    def setup_display(self):
        """Helper function that initializes the display elements
        """
        self.SetFont(wx.Font(12, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL,
                              wx.FONTWEIGHT_NORMAL))

        self.vbox = wx.BoxSizer(wx.VERTICAL)
        self.vboxHelper = gui.guiHelper.BoxSizerHelper(self, wx.VERTICAL)

        top_sizer = wx.BoxSizer(wx.HORIZONTAL)

        # TODO no logo for now
        # Logo button
        # logo_button = wx.Button(self.title_panel, label="", size=(216, 48),
        #                          style=wx.NO_BORDER)
        # logo_button.SetBackgroundColour("#b3c6ff")

        # logo_bitmap = wx.StaticBitmap(logo_button,
        #                                bitmap=wx.Bitmap(
        #                                    "hear2read-horizontal@2x.png"))
        # logo_button.Bind(wx.EVT_BUTTON, self.on_logo_click)
        
        self.title_text = wx.StaticText(self, label="Hear2Read Voice Manager")
        self.title_text.SetFont(wx.Font(22, wx.FONTFAMILY_DEFAULT,
                                    wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        self.title_text.SetForegroundColour("#FF101FBB")
        self.title_text.SetBackgroundColour("#b3c6ff")
        top_sizer.Add(self.title_text, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)

        # top_sizer.AddStretchSpacer()
        # top_sizer.Add(logo_button, 0, wx.ALIGN_RIGHT | wx.ALIGN_CENTER_VERTICAL, 0)

        self.vboxHelper.addItem(top_sizer)
        
        # Set a larger font
        font = self.GetFont()
        font.SetPointSize(int(font.GetPointSize() * 1.25))

        self.list_ctrl = self.vboxHelper.addLabeledControl(
                        "Hear2Read Voice List", wx.ListCtrl, 
                        style=wx.LC_REPORT | wx.BORDER_NONE | wx.LC_NO_HEADER)

        self.list_ctrl.InsertColumn(0, 'Voice')#, width=140)
        self.list_ctrl.InsertColumn(1, 'Action')#, width=80)
        self.list_ctrl.SetFont(font=font)
                
        self.display_voice_list()


    def display_voice_list(self):
        """Helper function to populate the UI ListCtrl of the voices with the 
        appropriate on click functionality
        """
        # Add voices to the list
        for voice in self.display_voices:
            if voice.lang_iso in self.update_langs.keys():
                self.list_ctrl.Append([voice.display_name, "Update"])
            else:
                self.list_ctrl.Append([voice.display_name, voice.state])

        self.list_ctrl.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.on_click_item)

        if self.display_voices:
            self.list_ctrl.SetColumnWidth(0, wx.LIST_AUTOSIZE)
            self.list_ctrl.SetColumnWidth(1, wx.LIST_AUTOSIZE)

        if self.list_ctrl.GetColumnWidth(1) < 130:
            self.list_ctrl.SetColumnWidth(0, 145)
            self.list_ctrl.SetColumnWidth(1, 135)

        self.list_ctrl.SetMinSize((self.title_text.GetSize().GetWidth(), -1))

        self.vbox.Add(self.vboxHelper.sizer, border=10, flag=wx.ALL)
        self.vbox.Fit(self)
        self.SetSizer(self.vbox)
        # TODO check if redundant
        self.vbox.Fit(self)

        self.Fit()
        self.Layout()
        
        # on the event of network error, warn the user and inform that only 
        # voices already installed are being shown
        if self.network_error_event.is_set():
            gui.messageBox(_("Failed to fetch voices from server " 
                            "\nPlease check your internet connection "
                             "\nWe will only display installed voices "),
            # Translators: The title of a dialog presented when an error occurs.
                            _("Network Error"),
                            wx.OK | wx.ICON_WARNING)


    def delete_voice_files(self, voice):
        """Function to delete voice files associated with the voice

        @param voice: the Voice object to be removed
        @type voice: utils.Voice
        """
        # TODO remove wav files as well
        voice_files = Path(H2RNG_VOICES_DIR).glob(f"{voice.id}*")

        for f in voice_files:
            f.unlink()

    def on_click_item(self, event):
        """On click event handler for the items in the list of voices. Depending
        on the state of the voice, it is possible to perform one of three 
        actions on the voice: dowload, update or remove 

        @param event: the event passed by the wx gui
        """
        self.curr_index = event.GetIndex()
        voice = self.display_voices[self.curr_index]
        action = self.list_ctrl.GetItem(self.curr_index, 1).GetText()

        if action == "Download":
            self.download_voice(voice)
        elif action == "Update":
            self.update_voice(voice)
        else:
            self.remove_voice(voice)

    def download_voice(self, voice):
        """Handles on click behaviour for voice download

        @param voice: the Voice object of the voice to be downloaded
        @type voice: utils.Voice
        """
        # list of tuples of files and respective download URLs
        download_queue = []

        # the main model file
        file = f"{voice.id}.onnx"
        download_url = f"{H2RNG_VOICES_DOWNLOAD_HTTP}{file}"
        download_queue.append((os.path.join(H2RNG_VOICES_DIR,
                                            f"{file}{DOWNLOAD_SUFFIX}"), 
                               download_url))
        
        # the model config file
        file_config = f"{file}.json"
        download_url_config = f"{H2RNG_VOICES_DOWNLOAD_HTTP}{file_config}"
        download_queue.append((os.path.join(H2RNG_VOICES_DIR,
                                            f"{file_config}{DOWNLOAD_SUFFIX}"),  
                               download_url_config))
        
        # the extras file, if present
        if voice.extra:
            file_extra = f"{file}.zip"
            download_url_extra = f"{H2RNG_VOICES_DOWNLOAD_HTTP}{file_extra}"
            download_queue.append((os.path.join(H2RNG_VOICES_DIR,
                                             f"{file_extra}{DOWNLOAD_SUFFIX}"),  
                                   download_url_extra))

        # Show progress dialog
        self.progress_dialog = wx.ProgressDialog("Downloading",
                        f"Downloading {voice.display_name}. Please wait...",
                        maximum=100, parent=self,
                        style=wx.PD_CAN_ABORT | wx.PD_AUTO_HIDE)

        # Start download thread
        self.download_thread = DownloadThread(download_queue=download_queue,
                    cancel_event = Event(),
                    progress_callback=self.update_progress,
                    complete_callback=lambda: self.on_download_complete(voice),
                    cancel_callback=partial(self.on_download_cancel, voice))

        self.download_thread.start()

    def remove_voice(self, voice):
        """Handler for on-click behaviour of removing voice

        @param voice: the Voice object of the voice to be removed
        @type voice: utils.Voice
        """
        # first check that the current voice is not the one being removed
        # TODO: this is not a breaking change, check if necessary
        curr_synth = synthDriverHandler.getSynth()

        if ("Hear2Read NG" in curr_synth.name and 
            (curr_synth.voice == voice.id)):
            gui.messageBox(
                # Translators: message in a message box
                _("Cannot remove currently active voice!"),
                # Translators: title of a message box
                _("Error"),
                style=wx.ICON_ERROR
            )
            return
        
        confirm_remove = gui.messageBox(
            # Translators: message in a message box
            _("Do you want to remove this voice?\n Voice: "
              f"{voice.display_name}"),
            # Translators: title of a message box
            _("Remove Voice?"),
            style=wx.YES_NO|wx.ICON_WARNING)
        
        if confirm_remove == wx.YES:
            try:
                self.delete_voice_files(voice)
            except:
                log.exception("Failed to remove voice files", exc_info=True)
                gui.messageBox(
                    # Translators: message in a message box
                    _("Failed to remove voice\nSee NVDA's log for more details "),
                    # Translators: title of a message box
                    _("Failed"),
                    style=wx.ICON_WARNING
                )
            else:
                gui.messageBox(
                    # Translators: message in a message box
                    _("Voice removed successfully."),
                    # Translators: title of a message box
                    _("Done"),
                    style=wx.ICON_INFORMATION
                )
            self.list_ctrl.SetItem(self.curr_index, 1, "Download")        

    def update_voice(self, voice):
        """Helper function to handle on click behaviour for voice update. 
        Currently behaviour is identical to downloading the voice

        @param voice: the Voice object of the voice to be updated
        @type voice: utils.Voice
        """
        self.download_voice(voice)

    def update_progress(self, percent):
        """Callback function to update progress dialog with download progress.

        @param percent: integer percent of file downloaded
        @type percent: int
        """
        if self.progress_dialog:
            keep_going, skip = self.progress_dialog.Update(percent)
            if not keep_going:
                self.download_thread.cancel()

    def on_download_complete(self, voice):
        """Callback function on completion of downloads. Removes old voices if 
        present, renames voice files to remove the download suffix, and updates 
        the UI. The file management tasks are done on a background thread.

        @param voice: the Voice object of the voice downloaded
        @type voice: utils.Voice
        """
        voice_install_event = Event()

        if self.progress_dialog:
            self.progress_dialog.Destroy()
            self.progress_dialog = None

        installing_dialog = wx.BusyInfo("Installing {}... Please wait ", 
                                        parent=self)
        wx.Yield()

        def dismiss_installing_dialog():
            nonlocal installing_dialog
            installing_dialog = None

        def post_install_tasks(voice):
            """Handles UI changes after all install tasks are complete. 
            Dismisses the BusyInfo dialog and updates the list item status.
            Finally, prompts the user to restart NVDA to apply changes.

            @param voice: the Voice object of the voice installed
            @type voice: utils.Voice
            """
            # TODO the thread seems redundant, check
            self.list_ctrl.SetItem(self.curr_index, 1, "Remove")

            dismiss_installing_dialog()

            gui.messageBox(_(f"{voice.display_name} installed successfully "),
                        _("Download Complete"), 
                        wx.OK | wx.ICON_INFORMATION)
            
            retval = gui.messageBox(
                # Translators: content of a message box
                _(
                    f"Successfully downloaded voice  {voice.display_name}.\n"
                    "To use this voice, you need to restart NVDA.\n"
                    "Do you want to restart NVDA now?"
                ),
                # Translators: title of a message box
                _("Voice installed"),
                    wx.YES_NO | wx.ICON_WARNING,
                )
            
            if retval == wx.YES:
                core.restart()
                self.Destroy()
            
        def remove_suffix_extract(voice):
            """Does the file handling operations of renaming the files to remove
            the suffix and extracting extras zip file, if present

            @param voice: the Voice object of the voice being installed
            @type voice: utils.Voice
            """
            voice_files = Path(H2RNG_VOICES_DIR).glob(f"{voice.id}*")
            for file in voice_files:
                if file.is_file():
                    # Check if the filename ends with suffix and remove
                    if file.match(f"*{DOWNLOAD_SUFFIX}"):
                        new_file = file.with_suffix("")
                        os.rename(file, new_file)
                    
                    # extract extra files
                    if new_file.match("*.zip"):
                        with zipfile.ZipFile(new_file, 'r') as zipf:
                            zipf.extractall(H2RNG_DATA_DIR)
                        new_file.unlink()

        def remove_old_voice(old_voice):
            """Removes old voice files and the corresponding entry from the
            voice updates dictionary maintained.

            @param old_voice: the Voice object of the voice being removed
            @type old_voice: utils.Voice
            """
            if Path(H2RNG_VOICES_DIR, f"{old_voice.id}.onnx"):
                self.delete_voice_files(old_voice)
            self.update_langs.pop(old_voice.lang_iso)

        def voice_install_tasks(voice):
            """Function performing the install tasks of renaming downloaded 
            files, removing old voice files, and extracting the extras zipfile.
            Finally, sets the voice_install_event, allowing for post install
            tasks to be performed

            @param voice: the Voice object of the voice being installed
            @type voice: utils.Voice
            """
            try:
                remove_suffix_extract(voice)
                # Check if updating an older voice, remove old voice
                old_voice = self.update_langs.get(voice.lang_iso)
                if old_voice:
                    remove_old_voice(old_voice)
            except Exception as e:
                wx.CallAfter(
                lambda : gui.messageBox(
                    _(f"Failed to install {voice.display_name}: {e}"
                        "\nPlease check if you have low disk space and retry"),
                    # Translators: The title of a dialog presented when an error occurs.
                    _("Error"),
                    wx.OK | wx.ICON_ERROR))
            finally:
                wx.CallAfter(lambda: post_install_tasks(voice))
                voice_install_event.set()

        # Start the install tasks on a background thread
        Thread(target=lambda: voice_install_tasks(voice)).start()

        # wait for install to complete
        voice_install_event.wait()

    def on_download_cancel(self, voice, error_message=None):
        """Callback on the event the download is interrupted. In case the 
        user interrupts the download, a default message is shown. In case of
        download failure due to other exceptions, the exception message is 
        shown additionally.

        @param voice: the Voice object of the voice to be downloaded
        @type voice: utils.Voice
        @param error_message: the additional error message to be shown if the 
        download was not cancelled by the user, defaults to None
        @type error_message: string, optional
        """
        self.delete_voice_files(voice)

        if self.progress_dialog:
            self.progress_dialog.Destroy()
            self.progress_dialog = None

        if error_message:
            gui.messageBox(
                    _(f"Unable to download {voice.display_name} "
                      "\nPlease check internet connection "),
                    # Translators: The title of a dialog presented when an error occurs.
                    _("Download Error"),
                    wx.OK | wx.ICON_ERROR
                )
            # wx.MessageBox(error_message, "Error", wx.OK | wx.ICON_ERROR)
        else:
            gui.messageBox(
                    _("Download was canceled "),
                    # Translators: The title of a dialog presented when an error occurs.
                    _("Download Canceled"),
                    wx.OK | wx.ICON_WARNING
                )

    @classmethod  
    def get_installed_voices(self):
        """Classmethod to get installed voices. Returns a dictionary of voices
        keyed by the ISO code of the language

        @return: Dictionary of installed voices keyed by the 2 letter ISO code 
        of the language
        @rtype: dict
        """
        installed_voices = {}

        if not os.path.isdir(H2RNG_VOICES_DIR):
            return installed_voices

        # clear incomplete downloads -shyam
        for voice_file in glob.glob(os.path.join(H2RNG_VOICES_DIR,
                                                  f"*.{DOWNLOAD_SUFFIX}")):
            os.remove(voice_file)

        for id, display_name in populateVoices().items():
            if id.startswith("en"):
                continue
            voice_iso = id.split("-")[0].split("_")[0]
            installed_voices[voice_iso] = Voice(id, voice_iso, 
                                                display_name, "Remove")
        
        return installed_voices


    def get_server_voices(self):
        """Populated the list of voices available on the server. Modifies the 
        class attribute server_voices, a list of Voice objects. The operation
        is done in a background thread while a BusyInfo is displayed.
        """
        fetch_complete_event = Event()
        self.server_voices.clear()
        
        loading_dialog = wx.BusyInfo("Fetching voice list... Please wait ", 
                                        parent=self)
        wx.Yield()

        def parse_server_voices(resp_str):
            """Parses the pipe separated file list response from the server

            @param resp_str: string of pipe separated voice related files
            @type resp_str: string
            """
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
                            self.server_voices[iso_lang] = Voice(id=parts[0], 
                                    lang_iso=iso_lang,
                                    display_name=lang_names[iso_lang],
                                    state="Download", 
                                    extra=extra)
                        else:
                            self.server_voices[iso_lang] = Voice(id=parts[0], 
                                    lang_iso=iso_lang,
                                    display_name=f"Unknown Lang ({iso_lang})",
                                    state="Download", 
                                    extra=extra)

        def dismiss_loading_dialog():
            nonlocal loading_dialog
            loading_dialog = None

        def fetch():
            """Main function to fetch the voice list from the server. Sets the
            network_error_event attribute in case of failure 
            """
            try:
                with request.urlopen(H2RNG_VOICE_LIST_URL) as response:
                    resp_str = response.read().decode('utf-8')
                    parse_server_voices(resp_str)
            except Exception as e:
                self.network_error_event.set()
                log.warn(f"Hear2Read unable to access server: {e}")
            finally:
                wx.CallAfter(dismiss_loading_dialog)
                fetch_complete_event.set()

        Thread(target=fetch).start()

        fetch_complete_event.wait()
    

    def get_display_voices(self):
        """Compiles the voices to be diplayed from the lists of installed voices
        and voices available online. Modifies the attribute display_voices to
        be a list of Voice objects and sorts it by display_name
        """
        self.installed_voices = self.get_installed_voices()
        self.get_server_voices()

        if not self.server_voices:
            self.display_voices = sorted(list(self.installed_voices.values()),
                                    key=operator.attrgetter("display_name"))
            return
        
        for key in set(self.installed_voices.keys()).union(
                                                    self.server_voices.keys()):
            local_voice = self.installed_voices.get(key)
            server_voice = self.server_voices.get(key)

            if not local_voice:
                self.display_voices.append(server_voice)
                continue

            if not server_voice:
                self.display_voices.append(local_voice)
                continue

            if local_voice.id != server_voice.id:
                self.display_voices.append(server_voice)
                self.update_langs[local_voice.lang_iso] = local_voice
            else:
                self.display_voices.append(local_voice)

        self.display_voices.sort(key=operator.attrgetter("display_name"))
