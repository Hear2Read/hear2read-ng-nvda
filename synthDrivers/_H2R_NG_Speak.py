# -*- coding: UTF-8 -*-
# A part of the Hear2Read Indic Voices addon for NVDA
# Copyright (C) 2013-2024, Hear2Read Project Contributors
# See the file COPYING for more details.

import os
import queue
import threading
from collections import OrderedDict
from ctypes import (
    CFUNCTYPE,
    POINTER,
    Structure,
    c_bool,
    c_char_p,
    c_float,
    c_int,
    c_int16,
    cdll,
    sizeof,
)
from urllib.request import urlopen

import config
import gui
import nvwave
import wx
from logHandler import log
from synthDriverHandler import changeVoice, getSynthInstance

isSpeaking = False
onIndexReached = None
bgThread=None
bgQueue = None
player = None
en_player = None
H2RNG_SpeakDLL=None


H2RNG_DATA_DIR = os.path.join(os.getenv("APPDATA"), "Hear2Read-NG")
H2RNG_VOICES_DIR = os.path.join(H2RNG_DATA_DIR, "Voices")
H2RNG_PHONEME_DIR = os.path.join(H2RNG_DATA_DIR, "espeak-ng-data")
H2RNG_WAVS_DIR = os.path.join(H2RNG_DATA_DIR, "wavs")
H2RNG_ENGINE_DLL_PATH = os.path.join(H2RNG_DATA_DIR, "Hear2ReadNG_addon_engine.dll")

#error codes
EE_OK=0
EE_INTERNAL_ERROR=-1
EE_BUFFER_FULL=1
EE_NOT_FOUND=2

# offset between ascii and devanagari digits in unicode
DEVANAGARI_DIGIT_OFFSET = 2358

en_voice_amy = "en_US-amy-low"
EN_VOICE_ALOK = "en_US-arctic-medium"
en_voice = EN_VOICE_ALOK
en_qual = "med"
eng_synth = "oneCore"

ALOK_ID = 13
DIPAL_ID = 2
AMARPREET_ID = 1

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
qual_to_hz = {"low":16000, "med":22050}
digit_offsets = {"as": 2486, "ne":2358}

curr_voice = ""

# constants that can be returned by H2R_Speak_callback
CALLBACK_CONTINUE_SYNTHESIS=0
CALLBACK_ABORT_SYNTHESIS=1

def encodeH2RSpeakString(text):
    return text.encode('utf8')

def decodeH2RSpeakString(data):
    return data.decode('utf8')
    
# callback function decorators
t_H2RNG_audiocallback=CFUNCTYPE(c_int, POINTER(c_int16), c_int, c_bool)
t_H2RNG_indexcallback=CFUNCTYPE(c_int, c_int)

class Callbacks(Structure):
    _fields_ = [("ttsAudioCallback", t_H2RNG_audiocallback),
                ("ttsIndexCallback", t_H2RNG_indexcallback)]
                       
class SpeechParams(Structure):
    _fields_ = [("phoneLen", c_float), 
                ("volume", c_int), 
                ("charMode", c_bool), ]
       
def getCurrentVoice():
    
    if curr_voice:
        return curr_voice
    else:
    # TODO: raise exception?
        return None
        
def setCurrentVoice(voiceID=en_voice):
    global curr_voice
    curr_voice = voiceID

@t_H2RNG_audiocallback
def audiocallback(wav, numsamples, isEng):
    global isSpeaking
    
    try:
        if not isSpeaking:
            player.stop()
            return CALLBACK_ABORT_SYNTHESIS

        if not wav:
            isSpeaking = False
            player.idle()
            en_player.idle()
            onIndexReached(None)
            return CALLBACK_ABORT_SYNTHESIS
        
        prevByte = 0
        
        #write wav to file to test output
        # with wave.open(os.path.join(H2RNG_DATA_DIR, str(i) + ".wav"), "w") as f:
            # f.setnchannels(1)
            # f.setsampwidth(2)
            # f.setframerate(16000)
            # f.writeframes(wav_str)
        # i=i+1

        if isEng:
            player.sync()
            en_player.feed(wav,
                            size=numsamples * sizeof(c_int16))
        else:
            en_player.sync()
            player.feed(wav,
                            size=numsamples * sizeof(c_int16))

        return CALLBACK_CONTINUE_SYNTHESIS
        
    except Exception as e:
        log.error(f"audiocallback FAILED: {e}", exc_info=True)
        
@t_H2RNG_indexcallback
def indexcallback(index):
    onIndexReached(index)
    return CALLBACK_CONTINUE_SYNTHESIS


class BgThread(threading.Thread):
    def __init__(self):
        super().__init__(name=f"{self.__class__.__module__}.{self.__class__.__qualname__}")
        self.setDaemon(True)

    def run(self):
        while True:
            func, args, kwargs = bgQueue.get()
            if not func:
                break
            try:
                func(*args, **kwargs)
            except Exception as e:
                log.error(f"Error running function from queue: {e}", 
                          exc_info=True)
            bgQueue.task_done()

def _execWhenDone(func, *args, mustBeAsync=False, **kwargs):
    if mustBeAsync or bgQueue.unfinished_tasks != 0:
        # Either this operation must be asynchronous or There is still an operation in progress.
        # Therefore, run this asynchronously in the background thread.
        bgQueue.put((func, args, kwargs))
    else:
        func(*args, **kwargs)
        
def _speak(text, params):
    global isSpeaking
    isSpeaking = True
    
    text2=text.encode('utf8',errors='ignore')
    
    # log.info("_speak calling H2RNG_SpeakDLL.H2R_Speak_synthesizeText: " + text + " lenscale: " + str(params.phoneLen) + ", amplitude: " + str(params.volume))
    returncode = H2RNG_SpeakDLL.H2R_Speak_synthesizeText(text2, params)
    return returncode

def findNextTerminator(string, start):
    index = start

    whitespace = { " ", "\r", "\t", "\n"  }
    while (index < len(string)) :

        if (string[index] == "." or 
            string[index] == "!" or
            string[index] == "?" or
            string[index] == ";" or
            ord(string[index]) == 0x0964) :

            if (string[index + 1] in whitespace):
                break
        index += 1

    if start == index: 
        return 0
    
    return index
    
def characterMode(text):
    
    if len(text) > 1:
        return text
        
    unicodeHex = ord(text)
    if unicodeHex == 0x0901:
    # chandrabindu
        return "चंद्रबिंदु."
    if unicodeHex == 0x0902:
    # anuswaara
        return "अनुस्वार."
    if unicodeHex == 0x0901:
    # visarga
        return "विसर्ग."
    if 0x0915 <= unicodeHex <= 0x0939:
    # add a to consonants
        return text #+ chr(0x093E) + "."
    if unicodeHex == 0x093C:
    # nukta
        return "नुक्ता."
    # if 0x093E <= unicodeHex <= 0x094C:
    # # vowel signs - convert to independent vowel
        # return chr(unicodeHex - 0x38) + "."
    if unicodeHex == 0x094D:
    # halant
        return "हलन्त."
        
    if unicodeHex == 0x0981:
        return "চন্দ্ৰবিন্দু"
    if unicodeHex == 0x0982:
        return "উনস্বৰ"
    if unicodeHex == 0x0983:
        return "বিসৰ্গ"
    if unicodeHex == 0x09CD:
        return "হছন্ত"
        
    if unicodeHex == 0x0D4D:
        return "ചന്ദ്രക്കല"
    if unicodeHex == 0x0D02:
        return "അനുസ്വാരം"
    if unicodeHex == 0x0D03:
        return "വിസർഗം"
        
    return text
    
def asm_replacement_rules(text):
# replace bengali ra and nuqta combinations with single char
    return (text.replace("র","ৰ")
                .replace("য়","য়")
                .replace("ড়","ড়")
                .replace("ড়","ৰ")
                .replace("ঢ়","ঢ়")
                .replace("ঢ়","ৰ্হ"))

def mal_replacement_rules(text):
# replace zwj combination chillu  and nuqta combinations with single char
    return (text.replace("ര്‍","ർ")
                .replace("ല്‍","ൽ")
                .replace("ള്‍","ൾ")
                .replace("ന്‍","ൻ")
                .replace("ണ്‍","ൺ")
                .replace("ക്‍","ൿ"))

def mar_replacement_rules(text):
# remove zwj from halant zwj combos 
    return (text.replace("्‍","्")
                .replace("्‌","्"))


def speak(text, params):
    global bgQueue
    # log.info("_H2R_NG_Speak speak() text = " + text + ", charMode: " + str(charMode))
    # convert ascii digits to devanagari
    
    # if not text.isascii():
        # apply language relevant text preprocessing
        # if getCurrentVoice() and getCurrentVoice().split("-")[0] == "as":
            # text = asm_replacement_rules(text)
            
        # replace english digits with indic
        # digit_offset = digit_offsets.get(getCurrentVoice().split("-")[0], 0)
        # text = ''.join([chr(ord(x) + digit_offset) if 48 <= ord(x) <= 58 else x for x in text])
    
    # break text info individual sentences if necessary and send only 1 sentence at a time to DLL
    # end of sentence is period or denda
#    text=text.encode('utf8',errors='ignore')
    if params.charMode:
        _execWhenDone(_speak, characterMode(text), params, mustBeAsync=True)
        return
    else:
        _execWhenDone(_speak, text.replace("।", "."), params, mustBeAsync=True)
        return

def stop():
    global isSpeaking
    # Kill all speech from now.
    # We still want parameter changes to occur, so requeue them.
    params = []
    try:
        while True:
            item = bgQueue.get_nowait()
            if item[0] != _speak:
                params.append(item)
            bgQueue.task_done()
            
    except queue.Empty:
        # Let the exception break us out of this loop, as queue.empty() is not reliable anyway.
        pass
    for item in params:
        bgQueue.put(item)
    isSpeaking = False
#    H2RNG_SpeakDLL.H2R_Speak_stop();
    player.stop()
    en_player.stop()

    if EngSynth:
        EngSynth.cancel()

def pause(switch):    
    player.pause(switch)
    en_player.pause(switch)
    if EngSynth:
        EngSynth.pause(switch)

def populateVoices():
    pathName = os.path.join(H2RNG_DATA_DIR, "Voices")
    voices = dict()
    #list all files in Language directory
    file_list = os.listdir(pathName)
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

def _setVoiceByIdentifier(voiceID=None):
    global player
    
    v=getCurrentVoice()
    if voiceID:
        voice_attrs = voiceID.split("-")
    
    if not voiceID or not v or voice_attrs[0].split("_")[0] == "en":
        H2RNG_SpeakDLL.H2R_Speak_setEngVoiceMain()
        setCurrentVoice(en_voice)
        player.close()
        player = nvwave.WavePlayer(channels=1, 
                            samplesPerSec=qual_to_hz[en_qual], 
                            bitsPerSample=16, 
                            outputDevice=config.conf["speech"]["outputDevice"], 
                            buffered=True)
        return EE_NOT_FOUND
      
    curr_attrs = v.split("-")
    qual = voice_attrs[-1][:3]
    curr_qual = curr_attrs[-1][:3]
        
    if voiceID == v:
        return EE_OK
     
    # workaround to set dipal's voice as default for guj, if the json doesn't contain the correct ID
    if voice_attrs[0] == "gu" and voice_attrs[1] == "h2r" and H2RNG_SpeakDLL.H2R_Speak_GetSpeakerID() <= 0:
        if curr_qual != qual:
            if player:
                player.close()
            player = nvwave.WavePlayer(channels=1, samplesPerSec=qual_to_hz[qual], bitsPerSample=16, outputDevice=config.conf["speech"]["outputDevice"], buffered=True)
        setCurrentVoice(voiceID)
        H2RNG_SpeakDLL.H2R_Speak_SetVoice(c_char_p(encodeH2RSpeakString(voiceID)), c_char_p(encodeH2RSpeakString(H2RNG_DATA_DIR)))
        return(H2RNG_SpeakDLL.H2R_Speak_SetSpeakerID(DIPAL_ID))
        
    # workaround to set amarpreet's voice as default for pan 
    if voice_attrs[0] == "pa" and voice_attrs[1] == "tdilh2r" and H2RNG_SpeakDLL.H2R_Speak_GetSpeakerID() <= 0:
        if curr_qual != qual:
            if player:
                player.close()
            player = nvwave.WavePlayer(channels=1, samplesPerSec=qual_to_hz[qual], bitsPerSample=16, outputDevice=config.conf["speech"]["outputDevice"], buffered=True)
        setCurrentVoice(voiceID)
        H2RNG_SpeakDLL.H2R_Speak_SetVoice(c_char_p(encodeH2RSpeakString(voiceID)), c_char_p(encodeH2RSpeakString(H2RNG_DATA_DIR)))
        return(H2RNG_SpeakDLL.H2R_Speak_SetSpeakerID(AMARPREET_ID))
        
    # if curr_lang == "en" or curr_qual != qual:
    if curr_qual != qual:
        player.close()
        player = nvwave.WavePlayer(channels=1, samplesPerSec=qual_to_hz[qual], bitsPerSample=16, outputDevice=config.conf["speech"]["outputDevice"], buffered=True)
    
    setCurrentVoice(voiceID)
    #TODO async - handle exceptions differently
    return(H2RNG_SpeakDLL.H2R_Speak_SetVoice(c_char_p(encodeH2RSpeakString(voiceID)), c_char_p(encodeH2RSpeakString(H2RNG_DATA_DIR))))
    

def setVoiceByIdentifier(voiceID=None):
    _execWhenDone(_setVoiceByIdentifier, voiceID=voiceID, mustBeAsync=True)

#TODO there is no use other than setting to eng
def setVoiceByLanguage(lang):
    
    global curr_voice, player
    
    lang = lang.split("_")[0]
    
    if lang == "en":
        # log.info("_H2R_NG_Speak_setVoiceByLanguage: english voice not changed: " + en_voice)
        # H2RNG_SpeakDLL.H2R_Speak_setEngVoiceMain()
        # setCurrentVoice(en_voice)
        # player.close()
        # player = nvwave.WavePlayer(channels=1, samplesPerSec=qual_to_hz[en_qual], bitsPerSample=16, outputDevice=config.conf["speech"]["outputDevice"], buffered=True)
        return en_voice
        
    #Get all files in the Voices Directory
    pathName = os.path.join(H2RNG_DATA_DIR, "Voices")
    file_list = os.listdir(pathName)
    
    for file_name in file_list:
        parts = file_name.split(".")
        if parts[-1] == "onnx":
        # Found one of the NVDA Addon onnx voice file
            # log.info("_H2R_NG_Speak setVoiceByLanguage: parts = %s", parts[0])
            file_lang = parts[0].split("-")[0]
            if file_lang == lang:
                # matching language
                
                # log.info("_H2R_NG_Speak:setVoiceByLanguage - found %s for lang %s",file_lang, lang)

                hr = _setVoiceByIdentifier(parts[0])
                curr_voice = parts[0]
                return curr_voice
                
                # TODO: send error message on fail

    # modifying to default to english
    # -shyam 231107
    # log.info("_H2R_NG_Speak setVoiceByLanguage: defaulting to eng")
    _setVoiceByIdentifier()
    
    exceptionString = " Voice does not exist  '" + lang + "'";
    raise Exception(exceptionString)
    return None

def init_eng_voice():
    global H2RNG_SpeakDLL, en_player, en_voice, en_qual
    #Get all files in the Voices Directory
    file_list = os.listdir(H2RNG_VOICES_DIR)

    if EN_VOICE_ALOK.lower() + ".onnx" in file_list:
        H2RNG_SpeakDLL.H2R_Speak_SetVoiceEn(c_char_p(encodeH2RSpeakString(EN_VOICE_ALOK)), c_char_p(encodeH2RSpeakString(H2RNG_DATA_DIR)))
        H2RNG_SpeakDLL.H2R_Speak_SetSpeakerIDEn(ALOK_ID)
        en_player = nvwave.WavePlayer(channels=1, samplesPerSec=22050, bitsPerSample=16, outputDevice=config.conf["speech"]["outputDevice"], buffered=True)
        en_voice = EN_VOICE_ALOK.lower()
        en_qual = "med"
    elif EN_VOICE_ALOK + ".onnx" in file_list:
        H2RNG_SpeakDLL.H2R_Speak_SetVoiceEn(c_char_p(encodeH2RSpeakString(EN_VOICE_ALOK)), c_char_p(encodeH2RSpeakString(H2RNG_DATA_DIR)))
        H2RNG_SpeakDLL.H2R_Speak_SetSpeakerIDEn(ALOK_ID)
        en_player = nvwave.WavePlayer(channels=1, samplesPerSec=22050, bitsPerSample=16, outputDevice=config.conf["speech"]["outputDevice"], buffered=True)
        en_voice = EN_VOICE_ALOK
        en_qual = "med"
    else:
        H2RNG_SpeakDLL.H2R_Speak_SetVoiceEn(c_char_p(encodeH2RSpeakString(en_voice_amy)), c_char_p(encodeH2RSpeakString(H2RNG_DATA_DIR)))
        en_player = nvwave.WavePlayer(channels=1, samplesPerSec=16000, bitsPerSample=16, outputDevice=config.conf["speech"]["outputDevice"], buffered=True)
        en_voice = en_voice_amy
        en_qual = "low"

def init_eng_synth(default_synth="oneCore"):

    eng_synth = config.conf.get("hear2read", {}).get("engSynth", default_synth)
    eng_voice = config.conf.get("hear2read", {}).get("engVoice", "")
    eng_variant = config.conf.get("hear2read", {}).get("engVariant", "")

    log.info(f"init_eng_synth: got synth and voice from config: {eng_synth}, {eng_voice}")

    set_eng_synth(eng_synth=eng_synth)
    if eng_voice and eng_voice in get_eng_synth_voicelist().keys():
        set_eng_voice(eng_voice)
    if eng_variant and eng_variant in get_eng_synth_variantlist().keys():
        set_eng_variant(eng_variant)

    set_eng_synth_rate(config.conf["hear2read"]["engRate"])
    set_eng_synth_pitch(config.conf["hear2read"]["engPitch"])
    set_eng_synth_volume(config.conf["hear2read"]["engVolume"])
    set_eng_synth_inflection(config.conf["hear2read"]["engInflection"])




def set_eng_synth(eng_synth):
    global EngSynth, EngVoices
    
    try:
        if EngSynth:
            EngSynth.cancel()
            EngSynth.terminate()
            del EngSynth
    except NameError as e:
        log.info("EngSynth not defined. Ignoring")
        pass

    # eng_synth = config.conf.get("hear2read", {}).get("engSynth", eng_synth)
    # eng_voice = config.conf.get("hear2read", {}).get("engVoice", "")

    EngSynth = getSynthInstance(eng_synth)
    EngVoices = EngSynth._get_availableVoices()
    
    # if eng_voice not in EngVoices.keys():
    for voice in EngVoices.values():
        # log.info(f"onecore voice: {voice.displayName}, id: {voice.id}")
        # Hardcoding the voice as well for now
        if ((voice.language and voice.language.startswith("en")) 
                or (not voice.language 
                    and "english" in voice.displayName.lower())):
            eng_voice = voice.id
            break
    
    EngSynth._set_voice(eng_voice)
    # config.conf["hear2read"]["engSynth"] = EngSynth.name
    # config.conf["hear2read"]["engVoice"] = EngSynth.voice
    return True

def get_eng_voice():
    return EngSynth.voice

def set_eng_voice(voice_id):
    if voice_id not in get_eng_synth_voicelist().keys():
        log.warn(f"English voice {voice_id} not found in synthesizer, skipping")
        return
    log.info(f"set_eng_voice: {voice_id}")
    EngSynth._set_voice(voice_id)

    log.info(f"voice changed to: {get_eng_voice()}")
    if get_eng_voice() != voice_id:
        log.info("failed changing the voice. trying change_voice")
        changeVoice(EngSynth, voice_id)
        log.info(f"2nd attempt voice changed to: {get_eng_voice()}")

    # config.conf["hear2read"]["engVoice"] = EngSynth.voice

def get_eng_variant():
    try:
        return EngSynth._get_variant()
    except NotImplementedError as e:
        return ""

def set_eng_variant(variant):
    if variant not in get_eng_synth_variantlist():
        log.warn(f"English variant {variant} not found in synthesizer, skipping")
        return

    EngSynth._set_variant(variant)

def get_eng_synth_rate():
    return EngSynth._get_rate()

def set_eng_synth_rate(rate):
    EngSynth._set_rate(rate)

def get_eng_synth_pitch():
    return EngSynth._get_pitch()

def set_eng_synth_pitch(pitch):
    EngSynth._set_pitch(pitch)

def get_eng_synth_volume():
    return EngSynth._get_volume()

def set_eng_synth_volume(volume):
    EngSynth._set_volume(volume)

def get_eng_synth_inflection():
    return EngSynth._get_inflection()

def set_eng_synth_inflection(inflection):
    EngSynth._set_inflection(inflection)

def get_eng_synth_name():
    if EngSynth:
        return EngSynth.name
    else:
        return ""

def get_eng_synth_desc():
    if EngSynth:
        return EngSynth.description
    else:
        return ""
    
def get_eng_synth():
    try:
        return EngSynth if EngSynth else None
    except NameError as e:
        return None
    
def get_eng_synth_voicelist():
    try:
       all_voices = EngSynth._get_availableVoices()
    #    log.info(f"got all voices: {all_voices}")
    except Exception as e:
        log.warn(f"get_eng_synth_voicelist: Unable to list voices from \"{EngSynth.name}\"")
        return OrderedDict()
    return  OrderedDict(
            (id, voice_info)
            for id, voice_info in all_voices.items()
            if ((voice_info.language and voice_info.language.startswith("en")) 
                or (not voice_info.language 
                    and "english" in voice_info.displayName.lower()))
        )

def get_eng_synth_variantlist():
    try:
        return EngSynth._get_availableVariants()
    except NotImplementedError as e:
        log.warn(f"get_eng_synth_variantlist: Unable to list variaants from \"{EngSynth.name}\"")
        return []
    
def speak_eng(speech_sequence):
    # TODO throw exception if not?
    if EngSynth:
        EngSynth.speak(speech_sequence)
    
# TODO remove deprecated?
def _checkIfUpdates():
    show_update = False
    stamp_url = 'https://hear2read.org/nvda-addon/getNGUpdateStamp.php'
    server_stamp = urlopen(stamp_url).read()
    stamp_file = os.path.join(H2RNG_DATA_DIR, "ng-update")
    if os.path.isfile(stamp_file):
        with open(stamp_file, encoding="utf-8") as f:
            local_stamp = f.read()
        if int(server_stamp) > int(local_stamp):
            show_update = True
            
    elif server_stamp and (int(server_stamp) > 0):
        show_update = True
    
    if show_update:
        gui.messageBox(
                _("Update available for Hear2Read Indic synthesiser\n" +
                    "Open the Hear2Read Indic Voice Manager app to update"),
                # Translators: The title of a dialog presented when an error occurs.
                _("Hear2Read Indic Update!"),
                wx.OK | wx.ICON_WARNING
            )
  
# check if update stamp file has been modified -shyam 
# TODO deprecated 
def checkIfUpdates():
    # log.info("_H2R checkIfUpdates entered")
    # use another thread as _execWhenDone is used for synthesis -shyam
    update_thread = threading.Thread(target=_checkIfUpdates)
    update_thread.start()
    
def H2R_Speak_errcheck(res, func, args):
    if res != EE_OK:
        raise RuntimeError("%s: code %d" % (func.__name__, res))
    return res

def initialize(idxCallback=None):
    """
    @param idxCallback: A function which is called when eSpeak reaches an index.
        It is called with one argument:
        the number of the index or C{None} when speech stops.
    """
    global H2RNG_SpeakDLL, EngSynth, bgThread, bgQueue, player, onIndexReached#, i, libc
    
    H2RNG_SpeakDLL = cdll.LoadLibrary(H2RNG_ENGINE_DLL_PATH)

    H2RNG_SpeakDLL.H2R_Speak_init.argtypes=[c_char_p,Callbacks]
    H2RNG_SpeakDLL.H2R_Speak_init.errcheck=H2R_Speak_errcheck
    H2RNG_SpeakDLL.H2R_Speak_synthesizeText.errcheck=H2R_Speak_errcheck
    H2RNG_SpeakDLL.H2R_Speak_synthesizeText.argtypes=(c_char_p, SpeechParams)
    H2RNG_SpeakDLL.H2R_Speak_SetVoice.argtypes=[c_char_p,c_char_p]
    H2RNG_SpeakDLL.H2R_Speak_SetVoice.errcheck=H2R_Speak_errcheck
    H2RNG_SpeakDLL.H2R_Speak_SetVoiceEn.argtypes=[c_char_p,c_char_p]
    H2RNG_SpeakDLL.H2R_Speak_SetVoiceEn.errcheck=H2R_Speak_errcheck
    H2RNG_SpeakDLL.H2R_Speak_SetSpeakerIDEn.errcheck=H2R_Speak_errcheck
            
    callbacks = Callbacks(audiocallback, indexcallback)
    
    H2RNG_SpeakDLL.H2R_Speak_init(c_char_p(encodeH2RSpeakString(H2RNG_DATA_DIR)), callbacks)
    
    init_eng_voice()
    H2RNG_SpeakDLL.H2R_Speak_setEngVoiceMain()
    setCurrentVoice(en_voice)
    
    player = nvwave.WavePlayer(channels=1, samplesPerSec=qual_to_hz[en_qual], bitsPerSample=16, outputDevice=config.conf["speech"]["outputDevice"], buffered=False)

    onIndexReached = idxCallback
    bgQueue = queue.Queue()
    bgThread=BgThread()
    bgThread.start()

    init_eng_synth()


def terminate():
    global bgThread, bgQueue, player, en_player, H2RNG_SpeakDLL , onIndexReached, EngSynth
    stop()
    bgQueue.put((None, None, None))
    bgThread.join()
    H2RNG_SpeakDLL.H2R_Speak_Terminate()
    bgThread=None
    bgQueue=None
    player.close()
    player=None
    en_player.close()
    en_player=None
    # H2RNG_SpeakDLL=None
    del H2RNG_SpeakDLL
    onIndexReached = None
    if EngSynth:
        EngSynth.cancel()
        EngSynth.terminate()
        del EngSynth

def info():
    # Python 3.8: a path string must be specified, a NULL is fine when what we need is version string.
    return H2RNG_SpeakDLL.H2R_Speak_Info(None)