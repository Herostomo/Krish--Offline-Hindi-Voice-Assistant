# 🎤 Krish – Hindi Voice Assistant (Raspberry Pi)

## 🧠 Overview

**Krish** is an Offline Hindi Voice Assistant built for Raspberry Pi.

It supports:

- Wake Word Detection
- Time & Weather
- Alarm
- Emergency Guidance (Gas, Earthquake, Fire, etc.)
- Indian States & Capitals
- Indian Scientists
- Hindi Stories, Dohe, Muhavare
- Grammar Help
- Music Player
- Math Calculations
- Offline Functionality

Main Script: help.py

---

# 🛠 Hardware Requirements

- Raspberry Pi (4/5 recommended)
- USB Microphone
- Speaker (3.5mm or USB)
- SD Card with Raspberry Pi OS

---

# 📦 Software Requirements

Install dependencies:

```bash
sudo apt update
sudo apt install python3-pip mpg123 alsa-utils
pip3 install vosk sounddevice requests
```

You also need:

- Vosk Hindi Model
- Piper TTS
- Hindi Voice Model for Piper

---

# 📁 Project Structure

```
Krish-Voice-Assistant/
│
├── krish.py
├── music
├── alarm.wav
├── weather_cache.json
```

Place MP3 songs inside:

```
/home/pi/music
```

---

# 🚀 How To Run

Navigate to project directory:

```bash
python3 krish.py
```

You will see:

```
🎤 Voice Assistant Started...
```

---

# 📘 USER MANUAL

---

## STEP 1 – Power Up Raspberry Pi

1. Insert SD card  
2. Connect power supply  
3. Boot Raspberry Pi  

Wait until system fully starts.

---

## STEP 2 – Connect Microphone

Plug USB mic into Raspberry Pi.

Check mic:

```bash
arecord -l
```

---

## STEP 3 – Connect Speaker

Plug speaker into audio jack or USB.

Test speaker:

```bash
aplay /usr/share/sounds/alsa/Front_Center.wav
```

---

## STEP 4 – Start Assistant

```bash
python3 help.py
```

---

# 🗣 How To Use

---

## 🟢 Wake Up Command

Say:

Suno Krish  
OR  
Namaskar Krish  

Assistant will respond and become active.

---

## 🕒 Ask Time

Example:

Time kya hua hai?  
Samay batao  

---

## 🌦 Ask Weather

Example:

Delhi ka mausam kya hai?  

(Works offline using cache if internet not available)

---

## ⏰ Set Alarm

Example:

Subah 6 baje alarm laga do  
10 minute baad alarm laga do  

Stop alarm:

Alarm band karo  

---

## 🎵 Play Music

Say:

Gaana chalao  

Stop:

Gaana band karo  

---

## 🧮 Math Calculations

Examples:

Paanch plus das  
Bees guna teen  
16 ka vargmool  

---

## 🚨 Emergency Help

Ask about:

- Gas leakage
- Earthquake
- Fire
- Electric shock
- Snake bite
- Dog bite
- Chest pain
- Fainting

Example:

Gas leak ho gaya  

---

## 🇮🇳 Indian Knowledge

States & Capitals:

Bharat ke rajyo ki rajdhani batao  

Single state:

Maharashtra ki rajdhani kya hai?  

Scientists:

Kalam ke baare mein batao  

Government Policy:

Koi sarkari yojana batao  

---

## 📖 Stories & Fun

Kahani sunao  
Doha sunao  
Muhavara batao  
Joke sunao  

---

## 🧑‍🏫 Hindi Grammar

Sangya kya hoti hai?  

---

## 🛑 Stop Assistant

To stop speaking:

Ruk jao Krish  

To put assistant to sleep:

So jao  

Wake again using wake word.

---

# 🌐 Weather System

- Uses Open-Meteo API
- Saves offline cache in:
  weather_cache.json
- If no internet → uses saved data

---

# 🎵 Music System

- Uses mpg123
- Random song selection
- Stops during emergency

---

# 🔐 Offline Features

| Feature | Offline Support |
|----------|----------------|
| Wake Word | Yes |
| Time | Yes |
| Alarm | Yes |
| Math | Yes |
| Stories | Yes |
| Music | Yes |
| Weather | Cache Only |

---

# ⚠ Important Notes

- Recommended SAMPLE_RATE for Vosk: 44100
- Ensure correct mic permissions
- Set correct Vosk and Piper model paths in script

---

# 📌 Future Improvements

- GUI Interface
- GSM module for real SOS call
- Smart Home integration
- Bluetooth Speaker support
- Multi-language support

---

# 👨‍💻 Author

Raspberry Pi Hindi Voice Assistant Project  
Developed using Python, Vosk & Piper TTS

---
