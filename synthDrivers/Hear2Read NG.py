# -*- coding: UTF-8 -*-
#synthDrivers/Hear2Read NG.py
# A part of the Hear2Read Indic Voices addon for NVDA
# Copyright (C) 2013-2024, Hear2Read Project Contributors
# See the file COPYING for more details.

from collections import OrderedDict

import languageHandler

# import globalVars
from logHandler import log
from speech.commands import (
    BreakCommand,
    CharacterModeCommand,
    IndexCommand,
    LangChangeCommand,
    PhonemeCommand,
    PitchCommand,
    RateCommand,
    VolumeCommand,
)
from speech.types import SpeechSequence
from synthDriverHandler import (
    SynthDriver,
    VoiceInfo,
    getSynthInstance,
    synthDoneSpeaking,
    synthIndexReached,
)

from globalPlugins.hear2readng_global_plugin.utils import check_files

from . import _H2R_NG_Speak

#error codes
EE_OK=0
EE_INTERNAL_ERROR=-1
EE_BUFFER_FULL=1
EE_NOT_FOUND=2

nvdaRate = 50
piperPhoneLen = 1.0
volume = 100
amplitude = 100

checkedUpdate = False

class SynthDriver(SynthDriver):
    name = "Hear2Read NG"
    description = "Hear2Read Indic Voices"

    supportedSettings=(
        SynthDriver.VoiceSetting(), #necessary
#        SynthDriver.VariantSetting(),
        SynthDriver.RateSetting(),
#        SynthDriver.RateBoostSetting(),
#        SynthDriver.PitchSetting(),
#        SynthDriver.InflectionSetting(),
        SynthDriver.VolumeSetting(),
    )
    supportedCommands = {
        IndexCommand, #easy, should support
        CharacterModeCommand,
#        LangChangeCommand,
        BreakCommand,
#        PitchCommand,
#        RateCommand,
        # VolumeCommand,
#        PhonemeCommand,
    }
    supportedNotifications = {synthIndexReached, synthDoneSpeaking}

    __voices = dict()

    @classmethod
    def check(cls):
        if not check_files():
            raise FileNotFoundError("Hear2Read Indic files not found!")
            return False
            # try:
                # install_tasks()
            # except Exception as e:
                # log.error(f"Hear2Read Indic install tasks on check synth failed: {e}")
            # finally:
                # return check_files()
        return True

    def __init__(self):
        if not self.check():
            return
        # log.info("H2R NG: init started")
        _H2R_NG_Speak.initialize(self._onIndexReached)
        self.eng_synth = getSynthInstance("oneCore")
        self.__voices = _H2R_NG_Speak.populateVoices()
        self._variant="0"
        log.info("H2R NG: init done")

    def _processText(self, text):
        # We need to make several replacements.
        if not text.isascii():
            if self._get_language() == "as":
                text = _H2R_NG_Speak.asm_replacement_rules(text)
            elif self._get_language() == "ml":
                text = _H2R_NG_Speak.mal_replacement_rules(text)
            elif self._get_language() == "mr":
                text = _H2R_NG_Speak.mar_replacement_rules(text)
                
            digit_offset = _H2R_NG_Speak.digit_offsets.get(self._get_language(), 0)
            text = ''.join([chr(ord(x) + digit_offset) if 48 <= ord(x) <= 58 else x for x in text])
        
        # copied from the espeak addon: 
        # https://github.com/jcsteh/nvda/blob/aa5b4a0d05f6c258ada2dec7768c2d34e8910a0d/source/synthDrivers/espeak.py
        # -shyam
        return text.translate({
            0x3C: u"&lt;", # <: because of XML
            0x3E: u"&gt;", # >: because of XML
        })

    def _get_language(self):
        lang = _H2R_NG_Speak.getCurrentVoice().split("-")[0].split("_")[0]
        return lang

    def speak(self, speechSequence: SpeechSequence):
        charMode = False
        isASCII = True
        #TODO have multiple speech sequences and register on synthIndexReached
        # to alternate ascii and non ascii sub sequences
        # self.sequences = {}
        textSSML = []
        # log.info(f"speech sequence: {speechSequence}")
        for item in speechSequence:
            if isinstance(item,str):
                if isASCII and not item.isascii():
                    # log.info(f"detected first nonascii: {item}")
                    isASCII = False
                    # self.eng_synth.speak(speechSequence)
                    # return
                textSSML.append(self._processText(item))
            elif isinstance(item, IndexCommand):
                textSSML.append("<mark " + str(item.index) + ">")
            elif isinstance(item, CharacterModeCommand):
                charMode = item.state
            elif isinstance(item, LangChangeCommand):
                pass
            elif isinstance(item, BreakCommand):
                pass
            elif isinstance(item, VolumeCommand):
                pass
            elif isinstance(item, PhonemeCommand):
                pass
            else:
                log.error("Unknown speech: %s"%item)
                
        if isASCII:
            self.eng_synth.speak(speechSequence)
            return
        
        textmarked=u"".join(textSSML)           
        if (textmarked != ""):
            params = _H2R_NG_Speak.SpeechParams(piperPhoneLen, amplitude, charMode)
            _H2R_NG_Speak.speak(textmarked, params)

    def cancel(self):
        _H2R_NG_Speak.stop()
        self.eng_synth.cancel()

    def pause(self,switch):
        _H2R_NG_Speak.pause(switch)
        self.eng_synth.pause(switch)

    def _get_rate(self):
        return (nvdaRate)

    def _set_rate(self,rate):
        # NVDA sends a rate between 0 and 100
        global nvdaRate, piperPhoneLen
        nvdaRate = rate
        piperPhoneLen = (1 / (((rate) / 75) + (1 / 3))) if (rate < 50) else (1 / (((rate - 50) / 25) + 1))
        
    def _get_volume(self):
        return volume
        
    def _set_volume(self, new_volume):
        global volume, amplitude
        volume = new_volume
        amplitude = volume        

    def _getAvailableVoices(self):
        return OrderedDict((voiceID,VoiceInfo(voiceID,voiceName,voiceID.split("-")[0].split("_")[0]))
                for voiceID, voiceName in self.__voices.items())

    def _get_voice(self):
        return _H2R_NG_Speak.getCurrentVoice()

    def _set_voice(self, identifier):
        if not identifier:
            return
        # TODO: this is more or less redundant -shyam
        if "en_US" not in identifier: 
            identifier=identifier.lower()
        
        # modifying to prevent crash on deleting a selected voice b/w sessions
        # -shyam 231107
        if identifier not in self.__voices.keys():            
            self.__voices = _H2R_NG_Speak.populateVoices()
            
            if identifier not in self.__voices.keys():
                res = _H2R_NG_Speak.setVoiceByLanguage(identifier.split("-")[0].split("_")[0])
        
        else:
            try:
            #TODO better exception handling
                res = _H2R_NG_Speak._setVoiceByIdentifier(voiceID=identifier)
                return
            except Exception as e:
                raise e
                return

    def _onIndexReached(self, index):
            
        if index is not None:
            synthIndexReached.notify(synth=self, index=index)
        else:
            synthDoneSpeaking.notify(synth=self)

    def terminate(self):
        _H2R_NG_Speak.terminate()
        self.eng_synth.terminate()

    def _get_variant(self):
        return self._variant

    def _set_variant(self,val):
        return

    def _getAvailableVariants(self):
        return OrderedDict((ID,VoiceInfo(ID, name)) for ID, name in self._variantDict.items())
