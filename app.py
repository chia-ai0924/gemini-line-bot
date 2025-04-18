
import os
import json
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, ImageMessage, TextSendMessage
from google.oauth2 import service_account
import google.generativeai as genai

app = Flask(__name__)

# LINE 設定
line_bot_api = LineBotApi(os.environ.get("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.environ.get("LINE_CHANNEL_SECRET"))

# Google Gemini Service Account 認證
credentials_info = json.loads(os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON"))
credentials = service_account.Credentials.from_service_account_info(credentials_info)
genai.configure(credentials=credentials)

# 模型設定
MODEL = "models/gemini-1.5-pro"
chat_history = {}
MAX_ATTEMPTS = 3
unlock_phrase = "放我進來"

# 載入密碼與授權紀錄檔案
PASSWORD_FILE = "passwords.json"
AUTH_FILE = "authorized_users.json"

if os.path.exists(PASSWORD_FILE):
    with open(PASSWORD_FILE, "r", encoding="utf-8") as f:
        passwords = json.load(f)
else:
    passwords = {}

if os.path.exists(AUTH_FILE):
    with open(AUTH_FILE, "r", encoding="utf-8") as f:
        authorized_users = set(json.load(f))
else:
    authorized_users = set()

password_attempts = {}

def save_passwords():
    with open(PASSWORD_FILE, "w", encoding="utf-8") as f:
        json.dump(passwords, f, ensure_ascii=False, indent=2)

def save_authorized_users():
    with open(AUTH_FILE, "w", encoding="utf-8") as f:
        json.dump(list(authorized_users), f, ensure_ascii=False, indent=2)

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature")
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except Exception as e:
        print("Webhook error:", e)
        abort(400)
    return "OK"

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    text = event.message.text.strip()

    if user_id in password_attempts and password_attempts[user_id] >= MAX_ATTEMPTS:
        if text == unlock_phrase:
            del password_attempts[user_id]
            reply = "✅ 解鎖成功，請重新輸入啟用密碼。"
        else:
            return
        line_bot_api.reply_message(event.reply_token, TextSendMessage(reply))
        return

    if user_id not in authorized_users:
        if text in passwords and not passwords[text]["used"]:
            passwords[text]["used"] = True
            authorized_users.add(user_id)
            save_passwords()
            save_authorized_users()
            chat_history[user_id] = []
            reply = "✅ 驗證成功，歡迎使用 AI！請開始對話。"
        else:
            password_attempts[user_id] = password_attempts.get(user_id, 0) + 1
            attempts = password_attempts[user_id]
            if attempts >= MAX_ATTEMPTS:
                reply = "⛔ 密碼錯誤已達 3 次，帳號已封鎖，請輸入密語『放我進來』解鎖。"
            else:
                reply = f"❌ 密碼錯誤（已輸入 {attempts} 次），請重新輸入（錯誤達 {MAX_ATTEMPTS} 次將封鎖）"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(reply))
        return

    # 記憶功能
    try:
        history = chat_history.get(user_id, [])
        history.append({"role": "user", "parts": [text]})
        model = genai.GenerativeModel(MODEL)
        response = model.generate_content(history)
        reply = response.text.strip()
        history.append({"role": "model", "parts": [reply]})
        chat_history[user_id] = history[-10:]
        line_bot_api.reply_message(event.reply_token, TextSendMessage(reply))
    except Exception as e:
        print("❌ 發生錯誤：", e)
        line_bot_api.reply_message(event.reply_token, TextSendMessage("⚠️ 系統發生錯誤，請稍後再試。"))

@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    line_bot_api.reply_message(event.reply_token, TextSendMessage("目前僅支援文字訊息，請先完成啟用密碼。"))

if __name__ == "__main__":
    app.run()
