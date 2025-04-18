from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

import os
import json
import google.generativeai as genai
from google.oauth2.service_account import Credentials

app = Flask(__name__)

# 初始化 LINE
line_bot_api = LineBotApi(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))

# 初始化 Gemini（使用 Service Account）
service_account_info = json.loads(os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON"))
credentials = Credentials.from_service_account_info(
    service_account_info,
    scopes=["https://www.googleapis.com/auth/cloud-platform"]
)
genai.configure(credentials=credentials)
model = genai.GenerativeModel(model_name="models/gemini-1.5-pro", generation_config={"temperature": 0.7})

# === 使用者授權機制 ===
AUTHORIZED_USERS_FILE = "authorized_users.json"
PASSWORDS_FILE = "passwords.json"
MAX_FAILED_ATTEMPTS = 3
UNLOCK_PHRASE = "放我進來"

# 載入已授權用戶
def load_json(filename):
    if not os.path.exists(filename):
        with open(filename, "w") as f:
            json.dump({}, f)
    with open(filename, "r") as f:
        return json.load(f)

def save_json(filename, data):
    with open(filename, "w") as f:
        json.dump(data, f, indent=2)

authorized_users = load_json(AUTHORIZED_USERS_FILE)
passwords = load_json(PASSWORDS_FILE)
failed_attempts = {}

# 檢查是否授權
def is_authorized(user_id):
    return user_id in authorized_users

# 處理密碼驗證
def verify_password(user_id, message_text):
    if user_id in authorized_users:
        return True, ""

    # 解鎖密語
    if message_text.strip() == UNLOCK_PHRASE:
        failed_attempts.pop(user_id, None)
        return False, "✅ 解鎖成功，請重新輸入啟用密碼。"

    # 檢查是否已封鎖
    if failed_attempts.get(user_id, 0) >= MAX_FAILED_ATTEMPTS:
        return False, "⛔ 密碼錯誤已達 3 次，帳號已封鎖。請輸入密語「放我進來」來解鎖。"

    # 比對密碼
    if message_text in passwords:
        authorized_users[user_id] = {"authorized": True}
        save_json(AUTHORIZED_USERS_FILE, authorized_users)
        del passwords[message_text]
        save_json(PASSWORDS_FILE, passwords)
        failed_attempts.pop(user_id, None)
        return True, "✅ 驗證成功，歡迎使用 AI！請開始對話。"
    else:
        failed_attempts[user_id] = failed_attempts.get(user_id, 0) + 1
        remaining = MAX_FAILED_ATTEMPTS - failed_attempts[user_id]
        if remaining > 0:
            return False, f"⚠️ 密碼錯誤（已輸入 {failed_attempts[user_id]} 次），請重新輸入啟用密碼（錯誤達 3 次將被封鎖）"
        else:
            return False, "⛔ 密碼錯誤已達 3 次，帳號已封鎖。請輸入密語「放我進來」來解鎖。"

# 多輪記憶功能
conversation_history = {}

def build_prompt(user_id, user_input):
    history = conversation_history.get(user_id, [])
    history.append({"role": "user", "parts": [user_input]})
    conversation_history[user_id] = history[-10:]  # 最多保留 10 則訊息
    return history

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK"

@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
    user_id = event.source.user_id
    message_text = event.message.text.strip()

    if not is_authorized(user_id):
        success, response = verify_password(user_id, message_text)
        if success:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=response))
        else:
            if response:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text=response))
        return

    # 已授權用戶，開始與 Gemini 對話
    prompt = build_prompt(user_id, message_text)
    try:
        response = model.generate_content(prompt)
        reply = response.text
    except Exception as e:
        reply = f"⚠️ 發生錯誤，請稍後再試。\n{e}"

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

# 部署入口
if __name__ == "__main__":
    app.run()
