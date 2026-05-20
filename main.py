import io
import os
import json
import time
import ctypes
import requests
import pyaudio
from dotenv import load_dotenv
from vosk import Model, KaldiRecognizer
from groq import Groq

# Загрузка переменных из .env
load_dotenv()

# --- КОНФИГУРАЦИЯ ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
FISH_API_KEY = os.getenv("FISH_API_KEY")
VOICE_ID = "4c3eaacc1a0545cdb0295bfddf3e3785"
VOSK_MODEL_PATH = "model" 

TEMP_FILES = [os.path.join(os.path.abspath(os.getcwd()), f"v_{i}.mp3") for i in range(2)]
current_file_idx = 0

session = requests.Session()
history = []
is_speaking = False

client = Groq(api_key=GROQ_API_KEY)
model = Model(VOSK_MODEL_PATH)
rec = KaldiRecognizer(model, 16000)

p = pyaudio.PyAudio()
mic_stream = p.open(format=pyaudio.paInt16, channels=1, rate=16000, input=True, frames_per_buffer=4000)

def speak(text):
    global current_file_idx, is_speaking
    is_speaking = True
    
    url = "https://api.fish.audio/v1/tts"
    payload = {"text": text, "reference_id": VOICE_ID, "format": "mp3", "latency": "low", "model_id": "S1"}
    headers = {"Authorization": f"Bearer {FISH_API_KEY}", "Content-Type": "application/json"}
    
    try:
        response = session.post(url, json=payload, headers=headers)
        if response.status_code == 200:
            current_file_idx = (current_file_idx + 1) % 2
            target_file = TEMP_FILES[current_file_idx]
            alias = f"j{current_file_idx}"
            
            mci = ctypes.windll.winmm.mciSendStringW
            mci(f"stop {alias}", None, 0, 0)
            mci(f"close {alias}", None, 0, 0)
            
            with open(target_file, "wb") as f:
                f.write(response.content)
            
            mci(f'open "{target_file}" type mpegvideo alias {alias}', None, 0, 0)
            mci(f'play {alias} wait', None, 0, 0) 
    except Exception as e:
        print(f"[ОШИБКА]: {e}")
    finally:
        rec.Reset()
        is_speaking = False

def think(user_input):
    global history
    messages = [{"role": "system", "content": "Ты — полезный и лаконичный голосовой помощник. Отвечай кратко, по делу и дружелюбно. Избегай длинных вступлений."}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_input})

    try:
        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant", 
            messages=messages,
            max_tokens=100,
            temperature=0.7
        )
        answer = completion.choices[0].message.content
        history.extend([{"role": "user", "content": user_input}, {"role": "assistant", "content": answer}])
        if len(history) > 4: history = history[-4:]
        return answer
    except:
        return "Извините, возникла техническая ошибка."

print("--- СИСТЕМА АКТИВИРОВАНА ---")

try:
    while True:
        data = mic_stream.read(2000, exception_on_overflow=False)
        if not is_speaking and rec.AcceptWaveform(data):
            result = json.loads(rec.Result())
            text = result.get("text", "")
            if text:
                print(f"Вы: {text}")
                reply = think(text)
                print(f"Помощник: {reply}")
                speak(reply)
except KeyboardInterrupt:
    print("\nОтключение...")
finally:
    mic_stream.stop_stream()
    mic_stream.close()
    p.terminate()