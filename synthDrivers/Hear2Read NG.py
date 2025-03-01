# -*- coding: UTF-8 -*-
#synthDrivers/Hear2Read NG.py
# A part of the Hear2Read Indic Voices addon for NVDA
# Copyright (C) 2013-2024, Hear2Read Project Contributors
# See the file COPYING for more details.

import re
import string
import unicodedata
from collections import OrderedDict

import config
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

# TEXT_CHARS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
UNK_SCRIPT = "Unknown"

unicode_ranges = {
    "devanagari": (0x0900, 0x097F),
    "bengali": (0x0980, 0x09FF),
    "gurmukhi": (0x0A00, 0x0A7F),
    "gujarati": (0x0A80, 0x0AFF),
    "oriya": (0x0B00, 0x0B7F),
    "tamil": (0x0B80, 0x0BFF),
    "telugu": (0x0C00, 0x0C7F),
    "kannada": (0x0C80, 0x0CFF),
    "malayalam": (0x0D00, 0x0D7F),
    "sinhala": (0x0D80, 0x0DFF),
    "english": (0x0000, 0x007F),
    "indic": (0x0900, 0x0DFF),
}
INDIC_RANGE = (0x0900, 0x0DFF)

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
        PitchCommand,
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
        confspec = {
            "engSynth": "string(default='oneCore')",
            "engVoice": "string(default='')",
            "engVariant": "string(default='')",
            "engRate": "integer(default=50)",
            "engPitch": "integer(default=50)",
            "engVolume": "integer(default=100)",
            "engInflection": "integer(default=80)",
        }
        config.conf.spec["hear2read"] = confspec

        # Have H2R pitch be set to the engsynth value to allow PitchCommand
        # to be used for capitals
        config.conf["speech"][self.name]["pitch"] = config.conf[
                                                        "hear2read"]["engPitch"]
        _H2R_NG_Speak.initialize(self._onIndexReached)

        #_H2R_NG_Speak.eng_synth = "oneCore"
        # self.eng_synth = getSynthInstance("oneCore")
        # eng_voices = self.eng_synth._getAvailableVoices()
        # for voice in eng_voices.values():
        #     # Hardcoding the voice as well for now
        #     if "Zira" in voice.displayName:
        #         eng_voice = voice.id
        #         self.eng_synth._set_voice(eng_voice)

        self.__voices = _H2R_NG_Speak.populateVoices()
        self._variant="0"
        self.alpha_regex = re.compile("([a-zA-Z]+)", re.ASCII)
        synthIndexReached.register(self._receiveIndexNotification)
        synthDoneSpeaking.register(self._receiveDoneNotification)
        # log.info("H2R NG: init done")

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
        # lang = _H2R_NG_Speak.getCurrentVoice().split("-")[0].split("_")[0]
        lang = "en"
        return lang

    def speak(self, speechSequence: SpeechSequence):
        isPrevASCII = True
        firstText = True
        self.currIndex = 0
        self.negIndex = -2
        self.subsequences = []
        subSequence : SpeechSequence = []
        indexCmd = None
        
        self._set_script_range()

        # log.info(f"got script range: {hex(self._script_range[0])} - {hex(self._script_range[1])}")

        # log.info(f"speech sequence: {speechSequence}")
        for item in speechSequence:
            if isinstance(item,str):
                text = item
                # log.info(f"speechSequence: {text}")
                isCurrASCII = item.isascii()
                if not isCurrASCII:
                    # quick hack to check if text has ascii and unicode characters
                    if text.upper().isupper():
                        if subSequence:
                            self.subsequences.append((isPrevASCII, subSequence))
                        self._process_mixed_text(text, indexCmd)
                        indexCmd = None
                        subSequence = []
                        # if firstText:
                        firstText = False
                        isPrevASCII = isCurrASCII
                        continue
                    
                    split_unicode_texts = self._process_non_native_unicode(text)

                    if len(split_unicode_texts) > 1:
                        if subSequence:
                            self.subsequences.append((isPrevASCII, subSequence))
                            subSequence = []
                        for isASCII, txt in split_unicode_texts:
                            subSequence.append(txt)
                            subSequence.append(IndexCommand(self.negIndex))
                            self.subsequences.append((isASCII, subSequence))
                            subSequence = []
                            self.negIndex -= 1
                        continue
                    else:
                        isCurrASCII, text = split_unicode_texts[0]


                if not firstText and isPrevASCII != isCurrASCII:
                    # if isASCII:
                    if subSequence:
                        self.subsequences.append((isPrevASCII, subSequence))
                        isPrevASCII = isCurrASCII
                        subSequence = []
                    # elif text.upper().isupper():
                    #     if indexCmd:
                    #         self._process_mixed_text(item, indexCmd)
                    #         subSequence = []
                subSequence.append(text)
                isPrevASCII = isCurrASCII
                firstText = False
            elif isinstance(item, IndexCommand):
                indexCmd = item
                subSequence.append(item)
                # pass
            elif isinstance(item, CharacterModeCommand):
                subSequence.append(item)
                # pass
            elif isinstance(item, LangChangeCommand):
                pass
            elif isinstance(item, BreakCommand):
                subSequence.append(item)
                # pass
            elif isinstance(item, PitchCommand):
                subSequence.append(item)
                # pass
            elif isinstance(item, VolumeCommand):
                subSequence.append(item)
                # pass
            elif isinstance(item, PhonemeCommand):
                subSequence.append(item)
                # pass
            else:
                log.error("Unknown speech: %s"%item)
            # subSequence.append(item)  
            
        if subSequence:
            self.subsequences.append((isPrevASCII, subSequence))

        # log.info("Joining subsequences: ")
        subsequences_joined = []
        for isEng, subSeq in self.subsequences:
            # log.info(f"subseq: isEng {isEng}, {subSeq}")
            # isASCII = txt.isascii()
            if not subsequences_joined:
                subsequences_joined.append([isEng, subSeq])
                isPrevEng = isEng
            elif isPrevEng == isEng:
                #   txt.isascii()==split_texts[-1].isascii()):
                # if not split_texts[-1].isascii and split_texts_base[i+1].isascii:
                #     continue
                subsequences_joined[-1][1].extend(subSeq)
            else:
                subsequences_joined.append([isEng, subSeq])
                isPrevEng = isEng

        self.subsequences = [(isEng, subSeq)
                             for isEng, subSeq in subsequences_joined]
        
        # log.info("Printing subsequences: ")
        # for isEng, subSeq in self.subsequences:
            # log.info(f"subseq: isEng {isEng}, {subSeq}")

        if self.subsequences:
            self._processSubSequences()

    def _process_mixed_text(self, text, idxCmd):
        # log.info(f"_process_mixed_text: {text}, {idxCmd}")
        split_texts = self.alpha_regex.split(text)
        # log.info(f"mixed texts: {split_texts}")
        split_texts_checked = []
        split_texts_joined = []

        for txt in split_texts:
            if txt.isascii():
                split_texts_checked.append([True, txt])
            else:
                split_unicode_texts = self._process_non_native_unicode(txt)
                split_texts_checked.extend(split_unicode_texts)

        for isASCII, txt in split_texts_checked:
            # isASCII = txt.isascii()
            if not split_texts_joined:
                split_texts_joined.append([isASCII, txt])
                isPrevASCII = isASCII
            elif (self.is_nontext(txt) or 
                  isPrevASCII == isASCII):
                #   txt.isascii()==split_texts[-1].isascii()):
                # if not split_texts[-1].isascii and split_texts_base[i+1].isascii:
                #     continue
                split_texts_joined[-1][1] += txt
            else:
                split_texts_joined.append([isASCII, txt])
                isPrevASCII = isASCII
        
        # log.info(f"mixed texts cleaned: {split_texts_joined}")

        subSequence : SpeechSequence = []
        
        # self.negIndex = -2

        for isASCII, txt in split_texts_joined[:-1]:
            if txt:
                subSequence.append(txt)
                subSequence.append(IndexCommand(self.negIndex))
                # log.info(f"appending subseq \"{txt}\", idx: {self.negIndex}")
                self.subsequences.append((isASCII, subSequence))
                subSequence = []
                self.negIndex-=1
        isASCII, txt = split_texts_joined[-1]
        subSequence.append(txt)
        if not idxCmd:
            idxCmd = IndexCommand(self.negIndex)
            self.negIndex -= 1
        subSequence.append(idxCmd)
        # log.info(f"appending subseq \"{txt}\", idx: {idxCmd}")
        self.subsequences.append((isASCII, subSequence))
        
    def is_nontext(self, txt):
        ret = txt.isascii() and not bool(re.search(r'[a-zA-Z0-9]', txt))
        return ret

    def _processSubSequences(self):
        if not self.subsequences:
            log.warn("Hear2Read: No speech sequences to process!")
            return
        isASCII, subSequence = self.subsequences.pop(0)
        # log.info(f"_processSubSequences: isASCII: {isASCII}")
        # log.info(f"_processSubsequence: subsequence {subSequence}")

        if isinstance(subSequence[-1], IndexCommand):
            self.currIndex = subSequence[-1].index
            # log.info(f"index boundary at: {self.currIndex}")
        if isASCII:
            # log.info(f"_processSubSequences: sending ASCII: {subSequence}")
            #TODO make sure this works even if no synth
            _H2R_NG_Speak.speak_eng(subSequence)
        else:
            self._speak_h2r(subSequence)

    def _process_non_native_unicode(self, text):
        split_texts = []
        prev_range = ()
        text_bit = ""
        has_curr_lang = False
        is_prev_valid_lang = False

        # log.info(f"_process_non_native_unicode: {text}")

        for c in text:
            # log.info(f"checking: {c}")
            if self._script_range[0] <= ord(c) <=self._script_range[1] or c in "।॥":
                # log.info(f"adding: {c}")
                text_bit += c
                has_curr_lang = True
                is_prev_valid_lang = True
                continue

            # log.info("skipped 1st if")

            if c in string.whitespace or c in string.punctuation:
                if is_prev_valid_lang:
                    # log.info(f"adding punct: {c}")
                    text_bit += c
                continue

            # log.info("skipped 2st if")

            if  c in string.digits or re.match("\\W", c):
                if is_prev_valid_lang:
                    # log.info(f"extending unicode nonalpha: {c}")
                    text_bit += c
                else:
                    # log.info(f"adding unicode nonalpha: {c}")
                    split_texts.append((True, c))
                continue

            # send all non Indic, Unicode punct to English (em, en dashes etc)
            if re.match("\\W", c):
                # log.info(f"adding unicode nonalphanumeric: {c}")
                split_texts.append((True, c))
                continue

            if not prev_range:
                # log.info(f"first non native: {c}")
                lang = unicodedata.name(c, UNK_SCRIPT).lower().split()[0]
                prev_range = unicode_ranges.get(lang, (0x0900, 0x0DFF))
                # if not prev_range:
                #     prev_range = unicode_ranges["indic"]
                if text_bit:
                    split_texts.append((False, text_bit))
                    text_bit = ""
                    is_prev_valid_lang = False

                # log.info(f"adding first non native: {lang}")
                split_texts.append((True, f"{lang} script"))
                continue

            # log.info("skipped 3st if")

            # Checks for whether script is English or not
            if prev_range != INDIC_RANGE:
                is_prev_curr_lang = prev_range[0] <= ord(c) <= prev_range[1]
            else:
                is_prev_curr_lang = not prev_range[0] <= ord(c) <= prev_range[1]

            if is_prev_curr_lang:
                # log.info("is_prev_curr_lang")
                continue

            # log.info("skipped 4st if")

            lang = unicodedata.name(c, UNK_SCRIPT).lower().split()[0]

            prev_range = unicode_ranges.get(lang, (0x0900, 0x0DFF))

            if text_bit:
                split_texts.append((False, text_bit))
                text_bit = ""
                is_prev_valid_lang = False
                
            split_texts.append((True, f"{lang} script"))

        if text_bit:
            split_texts.append((False, text_bit))

        # log.info(f"first run splits: {split_texts}")

        split_texts_joined = []

        for isASCII, text in split_texts:
            if split_texts_joined and split_texts_joined[-1][0] == isASCII:
                split_texts_joined[-1][1] += text
                # split_texts_joined[-1] = (isASCII, split_texts_joined[-1][1]
                #                           + text)
            else:
                split_texts_joined.append([isASCII, text])

        # log.info(f"_process_non_native_unicode: o/p: {split_texts_joined}")

        return split_texts_joined


    def _speak_h2r(self, speechSequence: SpeechSequence):
        """Helper function working as the speak function for pure Indic/Unicode 
        strings 

        @param speechSequence: SpeechSequence associated with the text
        @type speechSequence: SpeechSequence
        """
        charMode = False
        self.sequences = []
        # self.processsed_seqs = 0
        textSSML = []
        # log.info(f"_speak_h2r: speech sequence: {speechSequence}")
        for item in speechSequence:
            if isinstance(item,str):
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
        
        textmarked=u"".join(textSSML)           
        if (textmarked != ""):
            params = _H2R_NG_Speak.SpeechParams(piperPhoneLen, amplitude, charMode)
            _H2R_NG_Speak.speak(textmarked, params)

    def cancel(self):
        # log.info("cancel")
        self.subsequences = []
        _H2R_NG_Speak.stop()

    def pause(self,switch):
        # log.info("pause")
        _H2R_NG_Speak.pause(switch)

    def _get_rate(self):
        # we use the English voice setting to set English rate and volume
        if self.is_curr_voice_eng():
            return config.conf["hear2read"]["engRate"]
        return (nvdaRate)

    def _set_rate(self,rate):
        # we use the English voice setting to set English rate and volume
        if self.is_curr_voice_eng():
            _H2R_NG_Speak.set_eng_synth_rate(rate)
            config.conf["hear2read"]["engRate"] = rate
            return
        # NVDA sends a rate between 0 and 100
        global nvdaRate, piperPhoneLen
        nvdaRate = rate
        piperPhoneLen = (1 / (((rate) / 75) + (1 / 3))) if (rate < 50) else (1 / (((rate - 50) / 25) + 1))
        
    def _get_volume(self):
        # we use the English voice setting to set English rate and volume
        # engvol = config.conf["hear2read"]["engVolume"]
        # log.info(f"h2r _get_volume: {volume}, {engvol}")
        if self.is_curr_voice_eng():
            return config.conf["hear2read"]["engVolume"]
        return volume
        
    def _set_volume(self, new_volume):
        # we use the English voice setting to set English rate and volume
        # log.info(f"h2r _set_volume: {new_volume}, voice: {
        # _H2R_NG_Speak.getCurrentVoice()}, is voice eng? {
        # self.is_curr_voice_eng()}")
        if self.is_curr_voice_eng():
            _H2R_NG_Speak.set_eng_synth_volume(new_volume)
            config.conf["hear2read"]["engVolume"] = new_volume
            return
        global volume, amplitude
        volume = new_volume
        amplitude = volume        

    def _getAvailableVoices(self):
        # return OrderedDict((voiceID,VoiceInfo(voiceID,voiceName,voiceID.split("-")[0].split("_")[0]))
        #         for voiceID, voiceName in self.__voices.items())
        return OrderedDict((voiceID,VoiceInfo(voiceID,voiceName,"en"))
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
                lang_iso = identifier.split("_")[0].split("-")[0]
                return
            except Exception as e:
                raise e
                return
            
        self._set_script_range()

    def _set_script_range(self):        
        lang_iso = self._get_voice().split("_")[0].split("-")[0]

        if lang_iso in ["hi", "mr", "ne"]:
            self._script_range = unicode_ranges["devanagari"]
        elif lang_iso in ["as", "bn"]:
            self._script_range = unicode_ranges["bengali"]
        else:
            lang_name = _H2R_NG_Speak.lang_names[lang_iso].lower()
            self._script_range = unicode_ranges[lang_name]

    def _onIndexReached(self, index):
        # log.info(f"_onIndexReached: {index}")
        if index != 0:
            synthIndexReached.notify(synth=self, index=index)
        elif self.subsequences:
            self._processSubSequences()
        else:
            synthDoneSpeaking.notify(synth=self) 

    def _receiveIndexNotification(self, synth, index):
        # log.info(f"received index reached: {index}, from: {synth.name}")
        if self.name != synth.name:
            synthIndexReached.notify(synth=self, index=index)
            return
        # if index == self.currIndex and self.subsequences:
        #     self._processSubSequences()

    def _receiveDoneNotification(self, synth):
        # log.info(f"received synth done: {synth.name}")
        if self.name != synth.name:
            if self.subsequences:
                self._processSubSequences()
            else:
                synthDoneSpeaking.notify(synth=self)
            # return
        # if self.subsequences:
        #     self._processSubSequences()

    def terminate(self):
        synthDoneSpeaking.unregister(self._receiveDoneNotification)
        synthIndexReached.unregister(self._receiveIndexNotification)
        _H2R_NG_Speak.terminate()

    def _get_variant(self):
        return self._variant

    def _set_variant(self,val):
        return

    def _getAvailableVariants(self):
        return OrderedDict((ID,VoiceInfo(ID, name)) for ID, name in self._variantDict.items())
    
    def is_curr_voice_eng(self):
        """Function to check if the current voice is set to English

        @return: Return True if the current voice is English
        @rtype: bool
        """
        return _H2R_NG_Speak.getCurrentVoice().split("_")[0] == "en"
