from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, ImageMessage, TextSendMessage
import os
import requests
import json
import base64
from google.generativeai import GenerativeModel, configure
from PIL import Image
from io import BytesIO

app = Flask(__name__)

# 設定 LINE 與 Gemini API 金鑰
line_bot_api = LineBotApi(os.environ.get("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.environ.get("LINE_CHANNEL_SECRET"))
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
configure(api_key=GEMINI_API_KEY)

# 初始化 Gemini 模型
model = GenerativeModel("models/gemini-1.5-pro")

# 使用者記憶與驗證
user_context = {}           # 儲存上下文記憶 {user_id: [history]}
authorized_users = set()    # 儲存已通過驗證的用戶 user_id
password_pool = {"0000"}    # 密碼池（每組僅能使用一次）
used_passwords = set()      # 已使用密碼紀錄
failed_attempts = {}        # 密碼錯誤次數 {user_id: count}
blocked_users = set()       # 被封鎖的使用者
UNLOCK_PHRASE = "放我進來"  # 解鎖用密語

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except Exception as e:
        print("處理 webhook 時發生錯誤：", e)
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    msg = event.message.text.strip()

    # ✅ 封鎖處理
    if user_id in blocked_users:
        if msg == UNLOCK_PHRASE:
            blocked_users.remove(user_id)
            failed_attempts[user_id] = 0
            line_bot_api.reply_message(event.reply_token, TextSendMessage("✅ 解鎖成功，請重新輸入啟用密碼。"))
        return

    # ✅ 密碼驗證流程
    if user_id not in authorized_users:
        if msg in password_pool and msg not in used_passwords:
            authorized_users.add(user_id)
            used_passwords.add(msg)
            user_context[user_id] = []
            line_bot_api.reply_message(event.reply_token, TextSendMessage("✅ 驗證成功，歡迎使用 AI！請開始對話。"))
        else:
            failed_attempts[user_id] = failed_attempts.get(user_id, 0) + 1
            attempts = failed_attempts[user_id]
            if attempts >= 3:
                blocked_users.add(user_id)
                line_bot_api.reply_message(event.reply_token, TextSendMessage("❌ 密碼錯誤 3 次，您已被封鎖，請輸入『放我進來』來解鎖。"))
            else:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(f"⚠️ 密碼錯誤（已輸入 {attempts} 次），請重新輸入啟用密碼（錯誤達 3 次將被封鎖）"))
        return

    # ✅ 正常多輪對話流程（繁體中文為預設語言）
    history = user_context.setdefault(user_id, [])
    history.append({"role": "user", "parts": [msg]})
    try:
        response = model.generate_content(history)
        reply_text = response.text.strip()
        if not reply_text:
            reply_text = "⚠️ 抱歉，我暫時無法理解你的問題。"
    except Exception as e:
        print("發生錯誤：", e)
        reply_text = "❌ 發生錯誤，請稍後再試。"

    history.append({"role": "model", "parts": [reply_text]})
    line_bot_api.reply_message(event.reply_token, TextSendMessage(reply_text))

if __name__ == "__main__":
    app.run(debug=True)
