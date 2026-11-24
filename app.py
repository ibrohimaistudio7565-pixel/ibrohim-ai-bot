
import os
import requests
import logging
from flask import Flask, request, abort

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")

TELEGRAM = f"https://api.telegram.org/bot{BOT_TOKEN}"
GOOGLE = "https://generativelanguage.googleapis.com/v1beta"
modes = {}

def send(chat_id, text, keyboard=None):
    data = {"chat_id": chat_id, "text": text[:4000]}
    if keyboard:
        data["reply_markup"] = keyboard
    requests.post(f"{TELEGRAM}/sendMessage", json=data, timeout=30).raise_for_status()

def menu():
    return {"inline_keyboard": [
        [{"text": "💬 AI suhbat", "callback_data": "chat"}],
        [{"text": "🎨 Rasm yaratish", "callback_data": "image"}],
        [{"text": "🎵 Musiqa yaratish", "callback_data": "music"}],
        [{"text": "🎬 Video yaratish", "callback_data": "video"}]
    ]}

def gemini(prompt):
    r = requests.post(
        f"{GOOGLE}/models/gemini-2.5-flash:generateContent",
        params={"key": GEMINI_API_KEY},
        json={"contents": [{"parts": [{"text": prompt}]}]},
        timeout=120
    )
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]

def handle(update):
    if "callback_query" in update:
        q = update["callback_query"]
        chat_id = q["message"]["chat"]["id"]
        mode = q["data"]
        requests.post(f"{TELEGRAM}/answerCallbackQuery",
                      json={"callback_query_id": q["id"]}, timeout=15)
        modes[chat_id] = mode
        prompts = {
            "chat": "💬 Savolingizni yozing.",
            "image": "🎨 Qanday rasm yaratmoqchisiz? Tavsif yozing.",
            "music": "🎵 Qanday musiqa kerak? Tavsif yozing.",
            "video": "🎬 Qanday video kerak? 5–10 yoki 30–60 soniya ekanini ham yozing."
        }
        send(chat_id, prompts[mode])
        return

    msg = update.get("message", {})
    chat_id = msg.get("chat", {}).get("id")
    text = msg.get("text", "")

    if not chat_id:
        return

    if text.startswith("/start"):
        modes[chat_id] = "chat"
        send(chat_id, "🤖 IBROHIM AI BOT ga xush kelibsiz!\nXizmatni tanlang:", menu())
        return

    mode = modes.get(chat_id, "chat")

    if mode == "chat":
        try:
            send(chat_id, gemini(text))
        except Exception:
            logging.exception("Gemini error")
            send(chat_id, "AI bilan bog‘lanishda xatolik. API kalitini tekshiring.")
    elif mode == "image":
        send(chat_id, "🎨 Rasm yaratish xizmati hali ulanmagan.")
    elif mode == "music":
        send(chat_id, "🎵 Musiqa yaratish xizmati hali ulanmagan.")
    elif mode == "video":
        send(chat_id, "🎬 Video yaratish xizmati hali ulanmagan.")

@app.route("/")
def home():
    return "IBROHIM AI BOT ishlayapti!"

@app.route("/webhook", methods=["POST"])
def webhook():
    if WEBHOOK_SECRET and request.headers.get(
        "X-Telegram-Bot-Api-Secret-Token"
    ) != WEBHOOK_SECRET:
        abort(403)
    update = request.get_json(silent=True)
    if update:
        try:
            handle(update)
        except Exception:
            logging.exception("Update error")
    return "OK"

@app.route("/setup")
def setup():
    if not BOT_TOKEN:
        return "BOT_TOKEN kiritilmagan", 500
    url = os.environ.get("RENDER_EXTERNAL_URL", "").rstrip("/")
    if not url:
        return "Render URL topilmadi", 500
    data = {"url": url + "/webhook"}
    if WEBHOOK_SECRET:
        data["secret_token"] = WEBHOOK_SECRET
    r = requests.post(f"{TELEGRAM}/setWebhook", json=data, timeout=30)
    return r.text, r.status_code

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
    
