
import os
import json
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, ImageMessage, TextSendMessage
from google.oauth2 import service_account
from google.generativeai import GenerativeModel
from google.api_core.client_options import ClientOptions

from io import BytesIO
from PIL import Image

# 建立 Flask app
app = Flask(__name__)

# 初始化 LINE Bot
line_bot_api = LineBotApi(os.environ.get("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.environ.get("LINE_CHANNEL_SECRET"))

# 初始化 Gemini 模型（舊版寫法）
service_info = json.loads(os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON"))
credentials = service_account.Credentials.from_service_account_info(service_info)
client_options = ClientOptions(api_endpoint="https://generativelanguage.googleapis.com/")
model = GenerativeModel("models/gemini-1.5-pro", credentials=credentials, client_options=client_options)

# 密碼驗證與授權管理
AUTHORIZED_USERS_FILE = "authorized_users.json"
PASSWORDS_FILE = "passwords.json"
MAX_FAILED_ATTEMPTS = 3
UNLOCK_PHRASE = "放我進來"

def load_json(filename):
    return json.load(open(filename, "r", encoding="utf-8")) if os.path.exists(filename) else {}

authorized_users = load_json(AUTHORIZED_USERS_FILE)
passwords = load_json(PASSWORDS_FILE)
failed_attempts = {}
conversations = {}

def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def reply_text(token, text):
    line_bot_api.reply_message(token, TextSendMessage(text=text))

def check_password(user_id, message):
    if authorized_users.get(user_id): return True, None
    if failed_attempts.get(user_id, 0) >= MAX_FAILED_ATTEMPTS:
        if message.strip() == UNLOCK_PHRASE:
            failed_attempts[user_id] = 0
            return False, None
        return False, "⛔ 密碼錯誤已達 3 次，帳號已封鎖。
請輸入密語「放我進來」解鎖。"
    if message in passwords:
        authorized_users[user_id] = True
        del passwords[message]
        save_json(AUTHORIZED_USERS_FILE, authorized_users)
        save_json(PASSWORDS_FILE, passwords)
        return True, "✅ 驗證成功，歡迎使用 AI！請開始對話。"
    else:
        failed_attempts[user_id] = failed_attempts.get(user_id, 0) + 1
        if failed_attempts[user_id] >= MAX_FAILED_ATTEMPTS:
            return False, "⛔ 密碼錯誤已達 3 次，帳號已封鎖。
請輸入密語「放我進來」解鎖。"
        return False, f"⚠️ 密碼錯誤（已輸入 {failed_attempts[user_id]} 次），請重新輸入啟用密碼（錯誤達 3 次將被封鎖）"

def image_to_bytes(image):
    with BytesIO() as output:
        image.save(output, format="PNG")
        return output.getvalue()

def get_image_prompt(image):
    return [{
        "parts": [
            {"text": "請以繁體中文說明這張圖片的內容。"},
            {"inline_data": {"mime_type": "image/png", "data": image_to_bytes(image)}}
        ]
    }]

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except:
        abort(400)
    return "OK"

@handler.add(MessageEvent, message=(TextMessage, ImageMessage))
def handle_message(event):
    user_id = event.source.user_id
    token = event.reply_token

    if not authorized_users.get(user_id):
        ok, msg = check_password(user_id, event.message.text if isinstance(event.message, TextMessage) else "")
        if msg:
            reply_text(token, msg)
        return

    if isinstance(event.message, ImageMessage):
        try:
            content = line_bot_api.get_message_content(event.message.id)
            image = Image.open(BytesIO(content.content))
            response = model.generate_content(get_image_prompt(image))
            reply_text(token, response.text.strip())
        except Exception as e:
            reply_text(token, f"❌ 圖片處理錯誤：{e}")
        return

    user_input = event.message.text.strip()
    conversations.setdefault(user_id, [])
    conversations[user_id].append({"role": "user", "parts": [user_input]})
    try:
        response = model.generate_content(conversations[user_id])
        conversations[user_id].append({"role": "model", "parts": [response.text]})
        reply_text(token, response.text.strip())
    except Exception as e:
        reply_text(token, f"❌ 回應失敗：{e}")
