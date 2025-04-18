
import os
import json
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, ImageMessage, TextSendMessage
from google.oauth2 import service_account
import google.generativeai as genai

app = Flask(__name__)

# LINE 機器人設定
line_bot_api = LineBotApi(os.environ.get("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.environ.get("LINE_CHANNEL_SECRET"))

# 載入 Google Service Account 憑證
credentials_info = json.loads(os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON"))
credentials = service_account.Credentials.from_service_account_info(credentials_info)
genai.configure(credentials=credentials)

# 設定模型
MODEL = "models/gemini-1.5-pro"
chat_history = {}
verified_users = set()
used_passwords = set()
password_attempts = {}
activation_passwords = {"0000"}  # 可擴充多組密碼
unlock_phrase = "放我進來"
MAX_ATTEMPTS = 3

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

    # 解鎖機制
    if user_id in password_attempts and password_attempts[user_id] >= MAX_ATTEMPTS:
        if text == unlock_phrase:
            del password_attempts[user_id]
            reply_text = "✅ 解鎖成功，請重新輸入啟用密碼。"
        else:
            return  # 鎖定期間完全不回應
        line_bot_api.reply_message(event.reply_token, TextSendMessage(reply_text))
        return

    if user_id not in verified_users:
        if text in activation_passwords and text not in used_passwords:
            verified_users.add(user_id)
            used_passwords.add(text)
            chat_history[user_id] = []
            reply_text = "✅ 驗證成功，歡迎使用 AI！請開始對話。"
        else:
            password_attempts[user_id] = password_attempts.get(user_id, 0) + 1
            attempts = password_attempts[user_id]
            if attempts >= MAX_ATTEMPTS:
                reply_text = "⛔ 已連續輸入錯誤 3 次，帳號已封鎖，請輸入密語解鎖。"
            else:
                reply_text = f"⚠️ 密碼錯誤（已輸入 {attempts} 次），請重新輸入啟用密碼（錯誤達 {MAX_ATTEMPTS} 次將被封鎖）"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(reply_text))
        return

    # 多輪對話邏輯
    try:
        history = chat_history.get(user_id, [])
        history.append({"role": "user", "parts": [text]})

        model = genai.GenerativeModel(MODEL)
        response = model.generate_content(history)
        reply_text = response.text.strip()

        history.append({"role": "model", "parts": [reply_text]})
        chat_history[user_id] = history[-10:]  # 最多保留最近 10 則對話

        line_bot_api.reply_message(event.reply_token, TextSendMessage(reply_text))
    except Exception as e:
        print("❌ 發生錯誤：", e)
        line_bot_api.reply_message(event.reply_token, TextSendMessage("❌ 發生錯誤，請稍後再試。"))

@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    line_bot_api.reply_message(event.reply_token, TextSendMessage("目前僅支援文字訊息，可先輸入密碼解鎖後開始使用。"))

if __name__ == "__main__":
    app.run()
