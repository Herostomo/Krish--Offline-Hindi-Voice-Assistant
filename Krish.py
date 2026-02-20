import sounddevice as sd
import queue
import json
import subprocess
import tempfile
import os
import random
import threading
import re
from datetime import datetime, timedelta
from vosk import Model, KaldiRecognizer
import math
import requests
import socket

# ================= CONFIG =================

VOSK_MODEL_PATH = "YOUR VOSK MODEL"
PIPER_BIN = "YOUR PIPER MODEL"
PIPER_MODEL = "YOUR PIPER VOICE MODEL"
WEATHER_CACHE_FILE = "/home/pi/weather_cache.json"

SAMPLE_RATE = 44100   # ✅ MUST be 16000 for Vosk
BLOCK_SIZE = 4096
MUSIC_FOLDER = "/home/pi/music"
ALARM_SOUND = "/home/pi/alarm.wav"
assistant_awake = False
WAKE_WORDS = ["krish", "कृष", "कृष्ण","क्रिश"]
# ================= GLOBALS =================

audio_queue = queue.Queue()
music_process = None
alarm_time = None
alarm_active = False
alarm_repeat = None   # None / "daily"
state_speaking_active = False
awaiting_confirmation = False
tts_process = None
interrupt_tts = False
current_state_index = 0
last_response=""

# ================= AUDIO CALLBACK =================

def callback(indata, frames, time, status):
    if status:
        print(status)
    audio_queue.put(bytes(indata))

# ================= SPEAK =================

def speak(text):
    global tts_process, interrupt_tts
    interrupt_tts = False

    with tempfile.NamedTemporaryFile(mode="w", delete=False) as tf:
        tf.write(text)
        text_path = tf.name

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as wf:
        wav_path = wf.name

    cmd = f"{PIPER_BIN} --model {PIPER_MODEL} --output_file {wav_path} < {text_path}"
    subprocess.run(cmd, shell=True)

    tts_process = subprocess.Popen(["aplay", wav_path])

    while tts_process.poll() is None:
        if interrupt_tts:
            tts_process.terminate()
            break

    os.remove(text_path)
    os.remove(wav_path)


    
# ================= INTERNET CHECK =================

def is_internet_available():
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=3)
        return True
    except:
        return False
        
# ================= WEATHER CODE MAP =================

weather_codes = {
    0: "आसमान साफ है",
    1: "हल्का साफ मौसम",
    2: "आंशिक बादल",
    3: "बादल छाए हुए हैं",
    45: "कोहरा है",
    48: "घना कोहरा",
    51: "हल्की फुहार",
    61: "हल्की बारिश",
    63: "मध्यम बारिश",
    65: "तेज़ बारिश",
    71: "हल्की बर्फ",
    95: "तूफान की संभावना"
}

# ================= WEATHER FUNCTIONS =================

def get_coordinates(city):
    try:
        geo_url = (
            "https://geocoding-api.open-meteo.com/v1/search"
            f"?name={city}&count=1&language=hi&format=json"
        )

        response = requests.get(geo_url)
        data = response.json()

        if "results" not in data or len(data["results"]) == 0:
            return None, None

        lat = data["results"][0]["latitude"]
        lon = data["results"][0]["longitude"]

        return lat, lon

    except Exception as e:
        print("Geocoding error:", e)
        return None, None


def get_weather(city):

    if not city:
        speak("शहर समझ नहीं आया")
        return

    city_en = normalize_city(city)

    # 1️⃣ Load cache ONCE
    weather_cache = load_weather_cache()

    # ================= OFFLINE MODE =================
    if not is_internet_available():
        speak("इंटरनेट उपलब्ध नहीं है। ऑफलाइन मौसम बता रहा हूँ।")

        if city_en in weather_cache:
            info = weather_cache[city_en]
            speak(f"{info['hi']} में तापमान {info['temp']} डिग्री है और {info['desc']}")
        else:
            speak("इस शहर का ऑफलाइन मौसम उपलब्ध नहीं है")
        return

    # ================= ONLINE MODE =================
    speak("मौसम जानकारी प्राप्त की जा रही है")

    lat, lon = get_coordinates(city_en)

    if lat is None or lon is None:
        speak("शहर नहीं मिला")
        return

    try:
        weather_url = (
            f"https://api.open-meteo.com/v1/forecast?"
            f"latitude={lat}&longitude={lon}&current_weather=true"
        )

        response = requests.get(weather_url)
        data = response.json()

        current = data["current_weather"]
        temp = current["temperature"]
        code = current["weathercode"]

        desc = weather_codes.get(code, "सामान्य मौसम")

        speak(f"{city} में वर्तमान तापमान {temp} डिग्री है और {desc}")

        # 2️⃣ Update cache
        print("DEBUG: Updating cache (overwrite allowed) for:", city_en)

        weather_cache[city_en] = {
            "hi": city,
            "temp": temp,
            "desc": desc,
            "time": datetime.now().isoformat()
        }

        save_weather_cache(weather_cache)


    except Exception as e:
        print(e)
        speak("मौसम जानकारी प्राप्त नहीं हो पाई")

        
# ================= CITY NORMALIZATION =================

CITY_MAP = {
    "मुंबई": "Mumbai",
    "दिल्ली": "Delhi",
    "पुणे": "Pune",
    "नागपुर": "Nagpur",
    "बेंगलुरु": "Bangalore",
    "चेन्नई": "Chennai",
    "कोलकाता": "Kolkata",
    "हैदराबाद": "Hyderabad",
    "नाशिक":"Nasik",
    "नाशिक":"Nashik",
    "अमरावती":"Amaravati"
}



def normalize_city(city):
    if not city:
        return None

    city = city.strip()
    return CITY_MAP.get(city, city)


def load_weather_cache():
    if os.path.exists(WEATHER_CACHE_FILE):
        try:
            with open(WEATHER_CACHE_FILE, "r") as f:
                return json.load(f)
        except:
            return {}
    return {}


def save_weather_cache(cache):
    print("DEBUG: Saving to file:", os.path.abspath(WEATHER_CACHE_FILE))
    with open(WEATHER_CACHE_FILE, "w") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

# ================= CITY EXTRACTION =================
    
def extract_city(text):
    words = text.split()

    ignore = [
        "का", "के", "की",
        "बताओ", "बता",
        "क्या", "है",
        "आज", "मौसम",
        "weather"
    ]

    # Remove ignore words
    filtered = [w for w in words if w not in ignore]

    # Return FIRST valid word instead of last
    if filtered:
        return filtered[0]

    return None



# ================= MUSIC CONTROL =================
def play_music():
    global music_process

    if music_process:
        speak("गाना पहले से चल रहा है")
        return

    if not os.path.exists(MUSIC_FOLDER):
        os.makedirs(MUSIC_FOLDER)

    songs = [f for f in os.listdir(MUSIC_FOLDER) if f.lower().endswith(".mp3")]

    if not songs:
        speak("कोई गाना नहीं मिला")
        return

    song = random.choice(songs)
    song_path = os.path.join(MUSIC_FOLDER, song)

    music_process = subprocess.Popen(
        ["mpg123", song_path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    speak("गाना शुरू हो गया")

def stop_music():
    global music_process

    if music_process:
        music_process.terminate()
        music_process = None
        speak("गाना बंद हो गया")

# ================= HINDI NUMBER MAP =================

hindi_numbers = {
    "एक":1, "दो":2, "तीन":3, "चार":4, "पांच":5, "छह":6,
    "सात":7, "आठ":8, "नौ":9, "दस":10, "ग्यारह":11,
    "बारह":12, "तेरह":13, "चौदह":14, "पंद्रह":15,
    "सोलह":16, "सत्रह":17, "अठारह":18, "उन्नीस":19,
    "बीस":20, "तीस":30, "चालीस":40, "पैंतालीस":45
}


reverse_hindi_numbers = {v: k for k, v in hindi_numbers.items()}

# ================= TIME FORMAT =================

def get_period(hour24):
    if 4 <= hour24 < 12:
        return "सुबह"
    elif 12 <= hour24 < 16:
        return "दोपहर"
    elif 16 <= hour24 < 19:
        return "शाम"
    else:
        return "रात"

def format_time_hindi(hour24, minute):
    period = get_period(hour24)
    hour12 = hour24 % 12
    if hour12 == 0:
        hour12 = 12

    hour_word = reverse_hindi_numbers.get(hour12, str(hour12))
    minute_word = reverse_hindi_numbers.get(minute, str(minute))

    if minute == 0:
        return f"{period} के {hour_word} बजे"

    return f"{period} के {hour_word} बजकर {minute_word} मिनट"




# ================= INTENT DETECTION =================


def detect_intent(text):
    text = text.strip().lower()
    stop_words = ["बस", "रुक", "रुको", "स्टॉप", "चुप"]
    global assistant_awake
    
    if any(word in text for word in ["नाम", "कौन", "who are you", "आप कौन"]):
        return "NAME"
        
    if any(word in text for word in ["सही","गलत"]):
        return "SAHI"
        
    for w in stop_words:
        if re.search(rf"\b{w}\b", text):
            return "STOP_SPEAKING"
            
    if any(word in text for word in["अपने","बार में","आपने बारे में"]):
        return "intro"
        
    if awaiting_confirmation:
        if any(w in text for w in ["हाँ", "ha", "yes"]):
            return "CONFIRM_YES"
        if any(w in text for w in ["नहीं", "no", "न", "रुको"]):
            return "CONFIRM_NO"

    if any(word in text for word in ["समय","टाइम","वक्त","बजा"]):
        return "TIME"

    if "गाना" in text and any(w in text for w in ["चलाओ","लगाओ","शुरू"]):
        return "PLAY_MUSIC"

    if "गाना" in text and any(w in text for w in ["बंद","रोक"]):
        return "STOP_MUSIC"

    if "अलार्म" in text and any(w in text for w in ["लगाओ","सेट","कर"]):
        return "SET_ALARM"

    if "अलार्म" in text and any(w in text for w in ["बंद","रोक","स्टॉप"]):
        return "STOP_ALARM"
    
    if any(word in text for word in ["sos", "एसओएस", "मदद कॉल", "इमरजेंसी कॉल","मदद के लिए कॉल करो"]):
        return "SOS_CALL"
    
    math_keywords = [
    # Addition
    "जोड़", "जोड", "jod",
    "प्लस", "plus",

    # Subtraction
    "घट", "माइनस", "minus",

    # Multiplication
    "गुणा", "गुना", "guna",
    "multiply", "मल्टीप्लाई",

    # Division
    "भाग", "bhaag", "divide",

    # Square
    "वर्ग", "वर्गमूल"
]
    if any(w in text for w in WAKE_WORDS):
        assistant_awake=True
        return "WAKE_UP"
        
    if not assistant_awake:
        return None
        
    if "सो जाओ" in text or "sleep" in text:
        return "SLEEP"

    if any(word in text for word in math_keywords):
        return "CALCULATE"

    emergency_keywords = ["गैस","भूकंप","आग","करंट","साँप","कुत्ता","सीने","बेहोश","खून"]
    if any(word in text for word in emergency_keywords):
        return "EMERGENCY"

    if "मौसम" in text or "weather" in text:
        return "WEATHER"
    
    if any(word in text for word in ["राज्यों", "states", "स्टेट","राज्यो"]) and \
       any(word in text for word in ["राजधानी", "capital", "कैपिटल","राजधानियों"]):
       return "STATE_CAPITALS"
       
    for state in INDIA_STATES_CAPITALS.keys():
        if state in text and any(w in text for w in ["राजधानी", "capital"]):
            return "SINGLE_STATE_CAPITAL"

    if any(x in text for x in ["कहानी", "story"]):
        return "stories"
        
    if any(x in text for x in ["दोहे", "dohe","दोहा"]):
        return "dohe"

    if any(x in text for x in ["जोक", "joke","चुटकुला"]):
        return "jokes"

    if any(x in text for x in ["योजना", "सरकारी"]):
        return "govt_policies"

    if any(x in text for x in ["वैज्ञानिक", "कलाम", "रमन"]):
        return "scientists"

    if any(x in text for x in ["मानव अधिकार", "human rights"]):
        return "human_rights_info"

    if any(x in text for x in ["व्याकरण", "संज्ञा", "क्रिया", "काल"]):
        return "grammar"

    if "दोहराओ" in text:
        return "REPEAT"

    if "बस करो" in text or "रुको" in text:
        return "STOP"

    if "मुहावरा" in text or "muhavara" in text or "idiom" in text:
        return "MUHAVARA"


    return None

# ================= TIME EXTRACTION =================

# --------------------------
# Hindi numbers 0-99 + hundreds/thousands
# --------------------------
hindi_numbers = {
    "शून्य":0, "एक":1, "दो":2, "तीन":3, "चार":4,
    "पांच":5, "छह":6, "सात":7, "आठ":8, "नौ":9,
    "दस":10, "ग्यारह":11, "बारह":12, "तेरह":13,
    "चौदह":14, "पंद्रह":15, "सोलह":16, "सत्रह":17,
    "अठारह":18, "उन्नीस":19, "बीस":20, "इक्कीस":21,
    "बाईस":22, "तेइस":23, "चौबीस":24, "पच्चीस":25,
    "छब्बीस":26, "सत्ताईस":27, "अट्ठाईस":28, "उनतीस":29,
    "तीस":30, "इकतीस":31, "बत्तीस":32, "तेतीस":33, "चौतीस":34,
    "पैंतीस":35, "छत्तीस":36, "सैंतीस":37, "अड़तीस":38, "उनतालीस":39,
    "चालीस":40, "इकतालीस":41, "बयालीस":42, "तैंतालीस":43, "चवालीस":44,
    "पैंतालीस":45, "छियालीस":46, "सैंतालीस":47, "अड़तालीस":48, "उनचास":49,
    "पचास":50, "इक्यावन":51, "बावन":52, "तिरेपन":53, "चौवन":54,
    "पचपन":55, "छप्पन":56, "सत्तावन":57, "अट्ठावन":58, "उनसठ":59,
    "साठ":60, "इकसठ":61, "बासठ":62, "तिरेसठ":63, "चौंसठ":64,
    "पैंसठ":65, "छियासठ":66, "सड़सठ":67, "अड़सठ":68, "उनहत्तर":69,
    "सत्तर":70, "इकहत्तर":71, "बहत्तर":72, "तिरेहत्तर":73, "चौहत्तर":74,
    "पचहत्तर":75, "छिहत्तर":76, "सत्तहत्तर":77, "अठहत्तर":78, "उन्यासी":79,
    "अस्सी":80, "इक्यासी":81, "बयासी":82, "तिरासी":83, "चौरासी":84,
    "पचासी":85, "छियासी":86, "सत्तासी":87, "अठासी":88, "नवासी":89,
    "नब्बे":90, "इक्यानवे":91, "बानवे":92, "त्रियानवे":93, "चौरानवे":94,
    "पचानवे":95, "छियानवे":96, "सत्तानवे":97, "अट्ठानवे":98, "निन्यानवे":99,
    "सौ":100, "हजार":1000
}

# --------------------------
# Convert Hindi number words → numeric
# --------------------------
def hindi_to_number(words):
    tokens = words.strip().split()
    total = 0
    current = 0
    for word in tokens:
        if word in hindi_numbers:
            val = hindi_numbers[word]
            if val == 100:
                current = max(1, current) * 100
            elif val == 1000:
                total += max(1, current) * 1000
                current = 0
            else:
                current += val
    return total + current

# --------------------------
# Extract time robustly
# --------------------------
def extract_time(text):
    text = text.lower().strip()
    words = text.split()

    now = datetime.now()
    hour = None
    minute = 0
    alarm_repeat = None
    target_date = now

    # ---------- Relative time ----------
    if "minute" in text or "मिनट" in text:
        for word in words:
            if word.isdigit():
                mins = int(word)
                alarm = now + timedelta(minutes=mins)
                return alarm, alarm.hour, alarm.minute

    if "aadha" in text or "आधा" in text:
        if "ghanta" in text or "घंटा" in text:
            alarm = now + timedelta(minutes=30)
            return alarm, alarm.hour, alarm.minute

    # ---------- Tomorrow ----------
    if "कल" in text:
        target_date = now + timedelta(days=1)

    # ---------- Weekday ----------
    weekdays = {
        "monday":0, "tuesday":1, "wednesday":2,
        "thursday":3, "friday":4, "saturday":5, "sunday":6
    }
    for day in weekdays:
        if day in text:
            today_weekday = now.weekday()
            target_weekday = weekdays[day]
            days_ahead = target_weekday - today_weekday
            if days_ahead <= 0:
                days_ahead += 7
            target_date = now + timedelta(days=days_ahead)

    # ---------- Daily repeat ----------
    if "daily" in text or "रोज" in text:
        alarm_repeat = "daily"

    # ---------- Special words ----------
    i = 0
    while i < len(words):
        word = words[i]
        next_word = words[i+1] if i+1 < len(words) else None
        h = None

        if word in ["साढ़े", "sade"]:
            if next_word:
                if next_word.isdigit():
                    h = int(next_word)
                elif next_word in hindi_numbers:
                    h = hindi_numbers[next_word]
            if h is not None:
                hour = h
                minute = 30
                i += 1

        elif word in ["सवा", "sava"]:
            if next_word:
                if next_word.isdigit():
                    h = int(next_word)
                elif next_word in hindi_numbers:
                    h = hindi_numbers[next_word]
            if h is not None:
                hour = h
                minute = 15
                i += 1

        elif word in ["पौने", "paune"]:
            if next_word:
                if next_word.isdigit():
                    h = int(next_word)
                elif next_word in hindi_numbers:
                    h = hindi_numbers[next_word]
            if h is not None:
                hour = max(0, h - 1)
                minute = 45
                i += 1
        i += 1

    # ---------- Normal number detection ----------
    if hour is None:
        numbers = []
        for word in words:
            if word.isdigit():
                numbers.append(int(word))
            elif word in hindi_numbers:
                numbers.append(hindi_numbers[word])
        if len(numbers) >= 2:
            hour = numbers[0]
            minute = numbers[1]
        elif len(numbers) == 1:
            hour = numbers[0]

    # ---------- AM / PM ----------
    if hour is not None:
        if any(x in text for x in ["शाम","रात","pm"]):
            if hour < 12:
                hour += 12
        if any(x in text for x in ["सुबह","am"]):
            if hour == 12:
                hour = 0

    # ---------- Safety check ----------
    if hour is None or hour < 0 or hour > 23:
        hour = 0
    if minute < 0 or minute > 59:
        minute = 0


    alarm = target_date.replace(hour=hour, minute=minute, second=0)
    if alarm <= now and alarm_repeat != "daily":
        alarm += timedelta(days=1)

    return alarm, hour, minute




# ================= ALARM THREAD =================

def alarm_checker():
    global alarm_time, alarm_active, alarm_repeat

    while True:
        if alarm_time and datetime.now() >= alarm_time:

            alarm_active = True
            speak("अलार्म बज रहा है")

            while alarm_active:
                subprocess.Popen(["aplay", ALARM_SOUND])
                threading.Event().wait(2)

            if alarm_repeat == "daily":
                alarm_time += timedelta(days=1)
            else:
                alarm_time = None

        threading.Event().wait(1)
# ================= Calculation HANDLER =================
# ==========================
# HINDI NUMBER MAPS
# ==========================

# -------------------------
# Complete Hindi numbers
# -------------------------
HINDI_NUMBERS = {
    "शून्य":0, "एक":1, "दो":2, "तीन":3, "चार":4,
    "पांच":5, "छह":6, "सात":7, "आठ":8, "नौ":9,
    "दस":10, "ग्यारह":11, "बारह":12, "तेरह":13,
    "चौदह":14, "पंद्रह":15, "सोलह":16, "सत्रह":17,
    "अठारह":18, "उन्नीस":19, "बीस":20, "इक्कीस":21,
    "बाईस":22, "तेइस":23, "चौबीस":24, "पच्चीस":25,
    "छब्बीस":26, "सत्ताईस":27, "अट्ठाईस":28, "उनतीस":29,
    "तीस":30, "इकतीस":31, "बत्तीस":32, "तेतीस":33, "चौतीस":34,
    "पैंतीस":35, "छत्तीस":36, "सैंतीस":37, "अड़तीस":38, "उनतालीस":39,
    "चालीस":40, "इकतालीस":41, "बयालीस":42, "तैंतालीस":43, "चवालीस":44,
    "पैंतालीस":45, "छियालीस":46, "सैंतालीस":47, "अड़तालीस":48, "उनचास":49,
    "पचास":50, "इक्यावन":51, "बावन":52, "तिरेपन":53, "चौवन":54,
    "पचपन":55, "छप्पन":56, "सत्तावन":57, "अट्ठावन":58, "उनसठ":59,
    "साठ":60, "इकसठ":61, "बासठ":62, "तिरेसठ":63, "चौंसठ":64,
    "पैंसठ":65, "छियासठ":66, "सड़सठ":67, "अड़सठ":68, "उनहत्तर":69,
    "सत्तर":70, "इकहत्तर":71, "बहत्तर":72, "तिरेहत्तर":73, "चौहत्तर":74,
    "पचहत्तर":75, "छिहत्तर":76, "सत्तहत्तर":77, "अठहत्तर":78, "उन्यासी":79,
    "अस्सी":80, "इक्यासी":81, "बयासी":82, "तिरासी":83, "चौरासी":84,
    "पचासी":85, "छियासी":86, "सत्तासी":87, "अठासी":88, "नवासी":89,
    "नब्बे":90, "इक्यानवे":91, "बानवे":92, "त्रियानवे":93, "चौरानवे":94,
    "पचानवे":95, "छियानवे":96, "सत्तानवे":97, "अट्ठानवे":98, "निन्यानवे":99,
    "सौ":100, "हजार":1000
}

# -------------------------
# Convert Hindi number word(s) → numeric
# -------------------------
def hindi_to_number(text):
    tokens = text.strip().split()
    total = 0
    current = 0
    for word in tokens:
        if word in HINDI_NUMBERS:
            val = HINDI_NUMBERS[word]
            if val == 100:
                current = max(1, current) * 100
            elif val == 1000:
                total += max(1, current) * 1000
                current = 0
            else:
                current += val
        else:
            # Unknown word, ignore
            continue
    return total + current

# -------------------------
# Main Calculator
# -------------------------
def calculate_expression(text):
    text = text.lower().strip()

    # -------------------------
    # Operators
    # -------------------------
    operator_map = {
        "जोड़": "+", "प्लस": "+",
        "घट": "-", "माइनस": "-",
        "गुणा": "*", "गुना": "*",
        "भाग": "/", "डिवाइड": "/"
    }

    for k, v in operator_map.items():
        text = text.replace(k, v)

    # -------------------------
    # Replace Hindi numbers
    # -------------------------
    # Match sequences of Hindi words
    hindi_pattern = r'\b([एकदोतीनचारपांचछहसातआठनौदसग्यारहबारहतेरहचौदहपंद्रहसोलहसत्रहअठारहउन्नीसबीसइक्कीसबाईसतेइसचौबीसपच्चीसछब्बीससत्ताईसअट्ठाईसउनतीसतीसइकतीसबत्तीसतेतीसचौतीसपैंतीसछत्तीससैंतीसअड़तीसउनतालीसचालीसइकतालीसबयालीसतैंतालीसचवालीसपैंतालीसछियालीससैंतालीसअड़तालीसउनचासपचासइक्यावनबावनतिरेपनचौवनपचपनछप्पनसत्तावनअट्ठावनउनसठसाठइकसठबासठतिरेसठचौंसठपैंसठछियासठसड़सठअड़सठउनहत्तरसत्तरइकहत्तरबहत्तरतिरेहत्तरचौहत्तरपचहत्तरछिहत्तरसत्तहत्तरअठहत्तरउन्यासीअस्सीइक्यासीबयासीतिरासीचौरासीपचासीछियासीसत्तासीअठासीनवासीनब्बेइक्यानवेबानवेत्रियानवेचौरानवेपचानवेछियानवेसत्तानवेअट्ठानवेनिन्यानवेसौहजार\s]+)\b'
    matches = re.findall(hindi_pattern, text)
    for match in matches:
        number = hindi_to_number(match)
        text = text.replace(match, str(number), 1)

    # -------------------------
    # Square
    # -------------------------
    sq = re.search(r'(\d+)\s*का\s*वर्ग', text)
    if sq:
        return int(sq.group(1)) ** 2

    # -------------------------
    # Square Root
    # -------------------------
    sqrt = re.search(r'(\d+)\s*का\s*वर्गमूल', text)
    if sqrt:
        return round(math.sqrt(int(sqrt.group(1))), 2)

    # -------------------------
    # Final Expression
    # -------------------------
    expr = re.sub(r'[^0-9+\-*/().]', '', text)

    try:
        return eval(expr, {"__builtins__": None}, {})
    except:
        return None



# ================= STATES & CAPITALS =================

INDIA_STATES_CAPITALS = {
    "आंध्र प्रदेश": "अमरावती",
    "अरुणाचल प्रदेश": "ईटानगर",
    "असम": "दिसपुर",
    "बिहार": "पटना",
    "छत्तीसगढ़": "रायपुर",
    "गोवा": "पणजी",
    "गुजरात": "गांधीनगर",
    "हरियाणा": "चंडीगढ़",
    "हिमाचल प्रदेश": "शिमला",
    "झारखंड": "रांची",
    "कर्नाटक": "बेंगलुरु",
    "केरल": "तिरुवनंतपुरम",
    "मध्य प्रदेश": "भोपाल",
    "महाराष्ट्र": "मुंबई",
    "मणिपुर": "इंफाल",
    "मेघालय": "शिलांग",
    "मिजोरम": "आइजोल",
    "नागालैंड": "कोहिमा",
    "ओडिशा": "भुवनेश्वर",
    "पंजाब": "चंडीगढ़",
    "राजस्थान": "जयपुर",
    "सिक्किम": "गंगटोक",
    "तमिलनाडु": "चेन्नई",
    "तेलंगाना": "हैदराबाद",
    "त्रिपुरा": "अगरतला",
    "उत्तर प्रदेश": "लखनऊ",
    "उत्तराखंड": "देहरादून",
    "पश्चिम बंगाल": "कोलकाता"
}

# ================= INTENT HANDLER =================

def handle_intent(intent, text):
    global alarm_time, alarm_active
    global state_speaking_active, awaiting_confirmation
    global interrupt_tts
    global current_state_index
    global assistant_awake, last_response
    stop_words = ["बस", "रुक", "रुको", "स्टॉप", "चुप"]
    if intent == "TIME":
        assistant_awake = True
        now = datetime.now()
        speak(f"अभी {format_time_hindi(now.hour, now.minute)}")

    elif intent == "PLAY_MUSIC":
        assistant_awake = True
        play_music()

    elif intent == "STOP_MUSIC":
        assistant_awake = True
        stop_music()
    elif intent == "intro":
        speak("मैं आपका डिजिटल मित्र हूँ "
            "जो आपके रोज़मर्रा के कामों को आसान बना सकता है।")

        speak("मैं आपको समय और मौसम की जानकारी दे सकता हूँ।")
        speak("आपके लिए अलार्म लगा सकता हूँ।")
        speak("ज़रूरत पड़ने पर SOS नंबर पर कॉल भी लगा सकता हूँ।")
        speak("मैं सामान्य गणित के सवाल हल करके दिखा सकता हूँ।")
        speak("आपके मनपसंदीदा गाने चला सकता हूँ।")
        speak("और आपातकालीन परिस्थितियों में क्या करना चाहिए "
            "जैसे गैस लीक होने पर कैसे सतर्क रहें — यह भी बता सकता हूँ।")
        speak("मैं आपको हमारे देश के राज्यों और उनकी राजधानियों के बारे में जानकारी दे सकता हूँ।")
        speak("सरकारी नीतियों को सरल भाषा में समझा सकता हूँ ।")
        speak("और भारतीय वैज्ञानिकों की प्रेरणादायक कहानियाँ भी साझा कर सकता हूँ।")
        speak ("मैं आपको आपके मानवाधिकारों के प्रति जागरूक कर सकता हूँ।")
        speak("हिंदी व्याकरण सिखा सकता हूँ।")
        speak("मुहावरे और दोहे समझा सकता हूँ।")
        speak("अगर मन हल्का करना हो,"
            "तो मैं दादा-दादी की तरह प्यारी कहानियाँ सुना सकता हूँ,")
        speak("या फिर मज़ेदार चुटकुले सुनाकर मुस्कान ला सकता हूँ।")

        speak("तो बताइए,"
            "आज मैं आपकी किस प्रकार सहायता कर सकता हूँ?")
        return
    elif intent == "SET_ALARM":
        assistant_awake = True
        result = extract_time(text)
        if result:
            alarm, hour, minute = result
            alarm_time = alarm
            speak(f"अलार्म {format_time_hindi(hour, minute)} के लिए सेट हो गया है")
        else:
            speak("समय समझ नहीं आया")

    elif intent == "STOP_ALARM":
        if alarm_active:
            alarm_active = False
            speak("अलार्म बंद कर दिया गया है")
        else:
            speak("कोई अलार्म बज नहीं रहा है")

    elif intent == "EMERGENCY":

        stop_music()

        if "गैस" in text:
            speak("तुरंत गैस बंद करें। बिजली के स्विच ना चलाएं। खिड़कियां खोल दें।")

        elif "भूकंप" in text:
            speak("टेबल के नीचे छुप जाएं। दीवार और कांच से दूर रहें।")

        elif "आग" in text:
            speak("छोटी आग को कंबल से बुझाएं। बड़ी आग में तुरंत बाहर निकलें।")

        elif "करंट" in text:
            speak("पहले मेन स्विच बंद करें। सीधे हाथ से न छुएं।")

        elif "साँप" in text:
            speak("घबराएं नहीं। तुरंत अस्पताल जाएं।")

        elif "कुत्ता" in text:
            speak("घाव धोएं और डॉक्टर को दिखाएं।")

        elif "सीने" in text:
            speak("व्यक्ति को बैठाएं और एम्बुलेंस बुलाएं।")

        elif "बेहोश" in text:
            speak("सीधा लिटाएं और सांस जांचें।")

        elif "खून" in text:
            speak("घाव पर दबाव बनाएं।")
            
    elif intent == "SOS_CALL":
        stop_music()
        speak("एस ओ एस कॉल शुरू करने के लिए जी एस एम मॉड्यूल की आवश्यकता है")
    
    elif intent == "CALCULATE":
        result = calculate_expression(text)
        if result is not None:
            speak(f"उत्तर है {result}")
        else:
            speak("गणना समझ नहीं आई")
            
    elif intent == "WEATHER":
        city = extract_city(text)
        get_weather(city)

    elif intent == "STATE_CAPITALS":
        global state_speaking_active, awaiting_confirmation, current_state_index

        state_speaking_active = True

        states = list(INDIA_STATES_CAPITALS.items())

        if current_state_index == 0:
            speak("भारत के सभी राज्यों और उनकी राजधानियों के नाम बता रहा हूँ")

        for i in range(current_state_index, len(states)):
            state, capital = states[i]

            if not state_speaking_active:
                return

            speak(f"{state} की राजधानी {capital} है")
            current_state_index = i + 1

            if current_state_index % 5 == 0:
                awaiting_confirmation = True
                speak("मैं सुन रहा हूँ, आप सुन रहे हो ना")
                return

        state_speaking_active = False
        current_state_index = 0


    elif intent == "SAHI":
        assistant_awake = True
        speak("हाँ, आप सही बोल रहे हैं।")
            
    elif intent == "STOP_SPEAKING":
        
        interrupt_tts = True
        state_speaking_active = False
        awaiting_confirmation = False
        speak("ठीक है, रोक दिया")

        
    elif intent == "CONFIRM_YES":
        assistant_awake = True
        awaiting_confirmation = False
        speak("ठीक है, आगे बता रहा हूँ")
        handle_intent("STATE_CAPITALS", "")



    for w in stop_words:
        if re.search(rf"\b{w}\b", text):
            assistant_awake = True
            return "STOP_SPEAKING"

            
        elif intent == "CONFIRM_NO":
            assistant_awake = True
            state_speaking_active = False
            awaiting_confirmation = False
            speak("ठीक है, रोक रहा हूँ")
            
        elif intent == "SINGLE_STATE_CAPITAL":
            assistant_awake = True
            for state, capital in INDIA_STATES_CAPITALS.items():
                if state in text:
                    speak(f"{state} की राजधानी {capital} है")
                    return
            speak("इस राज्य की जानकारी उपलब्ध नहीं है")


    if intent == "stories":
        assistant_awake = True
        speak("कहानी सुना रहा हूँ")
        speak(random.choice(stories))
        
    elif intent == "dohe":
        assistant_awake = True
        speak("मैं एक दोहा सुना रहा हूँ")
        speak(random.choice(dohe))

    elif intent == "jokes":
        assistant_awake = True
        speak(random.choice(jokes))

    elif intent == "govt_policies":
        assistant_awake = True
        policy = random.choice(list(govt_policies.items()))
        speak(policy[0] + "। " + policy[1])

    elif intent == "scientists":
        assistant_awake = True
        for key in scientists:
            if key in text:
                speak(scientists[key])
                return
        speak("डॉ कलाम और सी वी रमन प्रसिद्ध भारतीय वैज्ञानिक हैं।")

    elif intent == "human_rights_info":
        assistant_awake = True
        speak(human_rights_info)

    elif intent == "grammar":
        assistant_awake = True
        for key in grammar:
            if key in text:
                speak(grammar[key])
                return
        speak("संज्ञा, क्रिया और काल हिंदी व्याकरण के भाग हैं।")

    elif intent == "REPEAT":
        speak(last_response)

    elif intent == "STOP":
        speak("ठीक है। मैं रुक रहा हूँ।")
        awaiting_confirmation = False

    if intent == "WAKE_UP":
        intro = (
            "बताइए,"
            "मैं आपकी किस प्रकार सहायता कर सकता हूँ?"
        )
        last_response = intro
        speak(intro)
        return
        
    elif intent == "MUHAVARA":
        assistant_awake = True
        name, meaning = random.choice(list(muhavare.items()))
        response = f"मुहावरा है {name}। इसका अर्थ है {meaning}"
        last_response = response
        speak(response)
        
    elif intent == "SLEEP":
        assistant_awake = False
        speak("ठीक है। जब आप कृष कहेंगे तब मैं वापस आ जाऊँगा।")

    elif intent == "NAME":
        speak("मेरा नाम Krish है")


#===========DATA=============

stories = [
    "एक गाँव में अर्जुन नाम का लड़का था। वह हर दिन अपने घर के पास झाड़ी साफ करता और बुजुर्गों की मदद करता। एक दिन गाँव में बाढ़ आई, लेकिन अर्जुन की मेहनत से सब सुरक्षित रहे। Moral: मेहनत और मदद से बड़ी मुसीबतों का सामना किया जा सकता है।",

    "सिया नाम की लड़की हमेशा अपने स्कूल की किताबें दूसरों के साथ साझा करती थी। एक दिन उसने देखा कि एक नया बच्चा पढ़ाई नहीं कर पा रहा था। सिया ने उसे पढ़ाया और उसकी मदद की। Moral: दयालुता और सहयोग से सबकी जिंदगी बेहतर बनती है।",

    "एक बार नन्हा राजू अपने खेत में काम कर रहा था। उसने देखा कि कुछ लोग जंगल में कचरा फेंक रहे हैं। उसने उन्हें समझाया और सभी ने मिलकर साफ-सफाई की। Moral: पर्यावरण की रक्षा करना हम सबकी जिम्मेदारी है।",

    "एक गांव में हरि नाम का लड़का रोज़ नई चीज़ें सीखता। वह किताबें पढ़ता, सवाल पूछता और प्रयोग करता। धीरे-धीरे वह अपने गाँव का सबसे होशियार बन गया और दूसरों को भी सिखाया। Moral: ज्ञान और जिज्ञासा से इंसान महान बन सकता है।",

    "एक दिन छोटे से पक्षी मोहन ने उड़ने की कोशिश की। बार-बार गिरने के बावजूद उसने हार नहीं मानी। अंत में वह आकाश में ऊँचा उड़ गया और खुश हुआ। Moral: साहस और धैर्य से हर लक्ष्य प्राप्त किया जा सकता है।"
]

jokes = [
    "टीचर: सबसे आलसी जानवर कौन है? स्टूडेंट: कछुआ!",
    "डॉक्टर: रोज़ व्यायाम करो। मरीज: मोबाइल उठाना भी गिना जाएगा?",
    "पापा: पढ़ाई कैसी चल रही है? बेटा: नेटवर्क स्लो है!"
]
govt_policies = {
    "आयुष्मान भारत": "पांच लाख तक मुफ्त इलाज की योजना।",
    "प्रधानमंत्री आवास योजना": "गरीबों को पक्का घर देने की योजना।",
    "डिजिटल इंडिया": "सरकारी सेवाएं ऑनलाइन उपलब्ध कराने की पहल।"
}
scientists = {
    "कलाम": "डॉ ए पी जे अब्दुल कलाम भारत के मिसाइल मैन थे और राष्ट्रपति रहे।",
    "रमन": "सी वी रमन ने रमन प्रभाव खोजा और नोबेल पुरस्कार जीता।"
}
human_rights_info = (
    "हर व्यक्ति को जीवन, स्वतंत्रता और सम्मान का अधिकार है। "
    "इन्हें मानव अधिकार कहा जाता है।"
)
grammar = {
    "संज्ञा": "जिस शब्द से व्यक्ति, वस्तु या स्थान का बोध हो उसे संज्ञा कहते हैं।",
    "क्रिया": "जो शब्द कार्य या अवस्था बताए उसे क्रिया कहते हैं।",
    "काल": "क्रिया के समय को काल कहते हैं। भूत, वर्तमान और भविष्य।"
}
muhavare = {
    "आँखों का तारा": "बहुत प्यारा व्यक्ति",
    "दाल में काला": "कुछ गड़बड़ होना",
    "नाक में दम करना": "बहुत परेशान करना",
    "सिर पर चढ़ाना": "ज़रूरत से ज़्यादा महत्व देना",
    "हाथ पर हाथ धरे रहना": "कुछ न करना",
    "दाँत खट्टे करना": "बुरी तरह हराना",
    "पानी फिर जाना": "मेहनत बेकार होना"
}

dohe = [
    "बूंद-बूंद से सागर बनता है,\nमेहनत से ही सफलता सजता है।\nMoral: मेहनत और निरंतर प्रयास से बड़ी उपलब्धियाँ मिलती हैं।",

    "सत्य बोलो, कभी न झूठ बोलो,\nसच्चाई की जीत हमेशा होती है।\nMoral: ईमानदारी जीवन में सम्मान और सफलता लाती है।",

    "बूँद-बूँद घड़ी पानी जमा हो,\nधैर्य से सब मुश्किलें आसान हो।\nMoral: धैर्य और संयम से बड़ी समस्याएँ हल होती हैं।",

    "ज्ञान ही धन है, अज्ञान ही रोग,\nपढ़ाई से मिटते जीवन के रोग।\nMoral: शिक्षा और ज्ञान सबसे बड़ा धन हैं।",

    "दोस्ती निभाओ, साथ हो सच्चा,\nसुख-दुख में साथ रहे वही मित्र अच्छा।\nMoral: सच्चा मित्र वही जो हमेशा साथ निभाए।"
]


# ================= MAIN =================

threading.Thread(target=alarm_checker, daemon=True).start()

model = Model(VOSK_MODEL_PATH)
rec = KaldiRecognizer(model, SAMPLE_RATE)

print("🎤 Voice Assistant Started...")

with sd.RawInputStream(
        samplerate=SAMPLE_RATE,
        blocksize=BLOCK_SIZE,
        dtype="int16",
        channels=1,
        callback=callback):

    while True:
        data = audio_queue.get()
        if rec.AcceptWaveform(data):
            result = json.loads(rec.Result())
            text = result.get("text", "")
            print("ASR:", text)

            intent = detect_intent(text)
            if intent:
                handle_intent(intent, text)
