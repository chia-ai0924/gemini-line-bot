from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, ImageMessage
from google.generativeai import GenerativeModel, configure
import os, json
from io import BytesIO
from PIL import Image

# 初始化 LINE API
line_bot_api = LineBotApi(os.environ.get("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.environ.get("LINE_CHANNEL_SECRET"))

# 初始化 Gemini API（使用 Service Account）
service_account = json.loads(os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON"))
configure(service_account=service_account)
model = GenerativeModel("models/gemini-1.5-pro")

# 初始化 Flask
app = Flask(__name__)

# 授權與密碼機制
AUTHORIZED_USERS_FILE = "authorized_users.json"
PASSWORDS_FILE = "passwords.json"
MAX_FAILED_ATTEMPTS = 3
UNLOCK_PHRASE = "放我進來"

# 載入 JSON 資料
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

# 密碼處理邏輯
def check_password(user_id, message):
    if authorized_users.get(user_id): return True, None

    if failed_attempts.get(user_id, 0) >= MAX_FAILED_ATTEMPTS:
        if message.strip() == UNLOCK_PHRASE:
            failed_attempts[user_id] = 0
            return False, "✅ 解鎖成功，請重新輸入啟用密碼。"
        return False, "⛔ 密碼錯誤已達 3 次，帳號已封鎖。\n請輸入密語「放我進來」解鎖。"

    if message in passwords:
        authorized_users[user_id] = True
        del passwords[message]
        save_json(AUTHORIZED_USERS_FILE, authorized_users)
        save_json(PASSWORDS_FILE, passwords)
        return True, "✅ 驗證成功，歡迎使用 AI！請開始對話。"
    else:
        failed_attempts[user_id] = failed_attempts.get(user_id, 0) + 1
        if failed_attempts[user_id] >= MAX_FAILED_ATTEMPTS:
            return False, "⛔ 密碼錯誤已達 3 次，帳號已封鎖。\n請輸入密語「放我進來」解鎖。"
        return False, f"⚠️ 密碼錯誤（已輸入 {failed_attempts[user_id]} 次），請重新輸入啟用密碼（錯誤達 3 次將被封鎖）"

# 圖片處理
def get_image_data(message_id):
    content = line_bot_api.get_message_content(message_id)
    image_data = BytesIO(content.content)
    image = Image.open(image_data)
    return image

def make_vision_prompt(image):
    return [{
        "parts": [
            {"text": "請用繁體中文說明這張圖片的內容。"},
            {"inline_data": {"mime_type": "image/png", "data": image_to_bytes(image)}}
        ]
    }]

def image_to_bytes(image):
    with BytesIO() as output:
        image.save(output, format="PNG")
        return output.getvalue()

# LINE Webhook
@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK"

# 處理訊息
@handler.add(MessageEvent, message=(TextMessage, ImageMessage))
def handle_message(event):
    user_id = event.source.user_id
    token = event.reply_token

    # 驗證授權
    if not authorized_users.get(user_id):
        ok, msg = check_password(user_id, event.message.text if isinstance(event.message, TextMessage) else "")
        if msg:
            reply_text(token, msg)
        return

    # 圖片訊息
    if isinstance(event.message, ImageMessage):
        try:
            image = get_image_data(event.message.id)
            result = model.generate_content(make_vision_prompt(image))
            reply_text(token, result.text.strip())
        except Exception as e:
            reply_text(token, f"❌ 發生錯誤，請稍後再試。\n\n{e}")
        return

    # 文字訊息（多輪記憶）
    user_input = event.message.text.strip()
    conversations.setdefault(user_id, [])
    conversations[user_id].append({"role": "user", "parts": [user_input]})

    try:
        result = model.generate_content(conversations[user_id])
        conversations[user_id].append({"role": "model", "parts": [result.text]})
        reply_text(token, result.text.strip())
    except Exception as e:
        reply_text(token, f"❌ 發生錯誤，請稍後再試。\n\n{e}")

