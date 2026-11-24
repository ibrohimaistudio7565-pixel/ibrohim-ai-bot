
import os
import logging
import sqlite3
import requests

from flask import Flask, request, abort

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL", "").rstrip("/")

TELEGRAM = f"https://api.telegram.org/bot{BOT_TOKEN}"
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/"
    "v1beta/models/gemini-3.5-flash-lite:generateContent"
)

YOUTUBE_CHANNEL = "https://www.youtube.com/@IBROHIM_AI_7565"
DB = "ibrohim_bot.db"

# Vaqtinchalik suhbat rejimlari va xotirasi
modes = {}
history = {}


def db():
    return sqlite3.connect(DB)


def init_db():
    with db() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                youtube_confirmed INTEGER DEFAULT 0
            )
        """)


init_db()


def confirmed(user_id):
    with db() as con:
        row = con.execute(
            "SELECT youtube_confirmed FROM users WHERE user_id=?",
            (user_id,)
        ).fetchone()
    return bool(row and row[0])


def confirm_user(user_id):
    with db() as con:
        con.execute("""
            INSERT INTO users (user_id, youtube_confirmed)
            VALUES (?, 1)
            ON CONFLICT(user_id)
            DO UPDATE SET youtube_confirmed=1
        """, (user_id,))


def telegram(method, data):
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN sozlanmagan")

    r = requests.post(
        f"{TELEGRAM}/{method}",
        json=data,
        timeout=30
    )
    r.raise_for_status()
    return r.json()


def send(chat_id, text, keyboard=None):
    data = {
        "chat_id": chat_id,
        "text": str(text)[:4000]
    }

    if keyboard:
        data["reply_markup"] = keyboard

    telegram("sendMessage", data)


def youtube_menu():
    return {
        "inline_keyboard": [
            [{
                "text": "📺 YouTube kanaliga obuna bo‘lish",
                "url": YOUTUBE_CHANNEL
            }],
            [{
                "text": "✅ Obuna bo‘ldim",
                "callback_data": "youtube_confirm"
            }]
        ]
    }


def menu():
    return {
        "inline_keyboard": [
            [{"text": "💬 AI suhbat", "callback_data": "chat"}],
            [{"text": "🎨 Rasm yaratish", "callback_data": "image"}],
            [{"text": "🎵 Musiqa yaratish", "callback_data": "music"}],
            [{"text": "🎬 Video yaratish", "callback_data": "video"}]
        ]
    }


def gemini(prompt, user_id):
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY sozlanmagan")

    messages = history.setdefault(user_id, [])

    messages.append({
        "role": "user",
        "parts": [{"text": prompt}]
    })

    # Suhbat tarixini cheklash
    messages[:] = messages[-12:]

    r = requests.post(
        GEMINI_URL,
        headers={
            "x-goog-api-key": GEMINI_API_KEY,
            "Content-Type": "application/json"
        },
        json={
            "contents": messages,
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 2048
            }
        },
        timeout=90
    )

    if not r.ok:
        logging.error(
            "Gemini HTTP %s: %s",
            r.status_code,
            r.text[:1000]
        )
        r.raise_for_status()

    data = r.json()
    answer = data["candidates"][0]["content"]["parts"][0]["text"]

    messages.append({
        "role": "model",
        "parts": [{"text": answer}]
    })

    return answer


def handle(update):

    # Tugmalar
    if "callback_query" in update:
        q = update["callback_query"]
        chat_id = q["message"]["chat"]["id"]
        user_id = q["from"]["id"]
        action = q["data"]

        telegram("answerCallbackQuery", {
            "callback_query_id": q["id"]
        })

        if action == "youtube_confirm":
            confirm_user(user_id)
            modes[chat_id] = "chat"

            send(
                chat_id,
                "🎉 Rahmat! Tasdiqlashingiz qabul qilindi.\n\n"
                "🤖 IBROHIM AI BOT xizmatlaridan foydalanishingiz mumkin!",
                menu()
            )
            return

        if not confirmed(user_id):
            send(
                chat_id,
                "🔒 Avval YouTube kanalimizga obuna bo‘ling!",
                youtube_menu()
            )
            return

        if action in ["chat", "image", "music", "video"]:
            modes[chat_id] = action

            prompts = {
                "chat": "💬 Savolingizni yozing.",
                "image": "🎨 Qanday rasm yaratmoqchisiz? Tavsif yozing.",
                "music": "🎵 Qanday musiqa kerakligini yozing.",
                "video": (
                    "🎬 Qanday video kerakligini yozing. "
                    "5–10 yoki 30–60 soniya ekanini ham belgilang."
                )
            }

            send(chat_id, prompts[action])

        return

    # Oddiy xabarlar
    msg = update.get("message", {})
    chat_id = msg.get("chat", {}).get("id")
    user_id = msg.get("from", {}).get("id")
    text = msg.get("text", "")

    if not chat_id or not user_id:
        return

    if text.startswith("/start"):
        if not confirmed(user_id):
            send(
                chat_id,
                "🤖 IBROHIM AI BOT ga xush kelibsiz!\n\n"
                "Botdan foydalanish uchun YouTube kanalimizga "
                "obuna bo‘ling va tasdiqlash tugmasini bosing.",
                youtube_menu()
            )
        else:
            modes[chat_id] = "chat"
            send(
                chat_id,
                "🤖 IBROHIM AI BOT ga xush kelibsiz!\n"
                "Xizmatni tanlang:",
                menu()
            )
        return

    if not confirmed(user_id):
        send(
            chat_id,
            "🔒 Botdan foydalanish uchun avval YouTube kanalimizga "
            "obuna bo‘ling.",
            youtube_menu()
        )
        return

    if not text:
        send(chat_id, "Iltimos, matnli xabar yuboring.")
        return

    if text == "/menu":
        send(chat_id, "Xizmatni tanlang:", menu())
        return

    if text == "/reset":
        history.pop(user_id, None)
        modes[chat_id] = "chat"
        send(chat_id, "Suhbat tarixi tozalandi.", menu())
        return

    mode = modes.get(chat_id, "chat")

    if mode == "chat":
        try:
            send(chat_id, gemini(text, user_id))
        except Exception:
            logging.exception("Gemini error")
            send(
                chat_id,
                "⚠️ AI bilan bog‘lanishda xatolik yuz berdi. "
                "API kaliti, model yoki limitlarni tekshiring."
            )

    elif mode == "image":
        send(
            chat_id,
            "🎨 Rasm yaratish bo‘limi tanlandi. "
            "Haqiqiy rasm yaratish xizmati hali ulanmagan."
        )

    elif mode == "music":
        send(
            chat_id,
            "🎵 Musiqa yaratish bo‘limi tanlandi. "
            "Haqiqiy musiqa yaratish xizmati hali ulanmagan."
        )

    elif mode == "video":
        send(
            chat_id,
            "🎬 Video yaratish bo‘limi tanlandi. "
            "Haqiqiy video yaratish xizmati hali ulanmagan."
        )


@app.route("/")
def home():
    return "IBROHIM AI BOT ishlayapti!"


@app.route("/webhook", methods=["POST"])
def webhook():
    if WEBHOOK_SECRET:
        if request.headers.get(
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

    if not RENDER_URL:
        return "RENDER_EXTERNAL_URL kiritilmagan", 500

    data = {
        "url": RENDER_URL + "/webhook"
    }

    if WEBHOOK_SECRET:
        data["secret_token"] = WEBHOOK_SECRET

    try:
        result = telegram("setWebhook", data)
        return result, 200
    except Exception:
        logging.exception("Webhook setup error")
        return {"ok": False, "description": "Webhook sozlashda xato"}, 500


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000))
)
        
