from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, ImageMessage, TextSendMessage
from google.oauth2.service_account import Credentials
from google.generativeai import GenerativeModel
import google.generativeai as genai
import os
import json
import base64
import requests
import uuid
import shutil

app = Flask(__name__)

# === LINE 設定 ===
line_bot_api = LineBotApi(os.environ.get("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.environ.get("LINE_CHANNEL_SECRET"))

# === Gemini 模型初始化 ===
service_account = json.loads(os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON"))
credentials = Credentials.from_service_account_info(
    service_account,
    scopes=["https://www.googleapis.com/auth/cloud-platform"],
)
genai_client = genai
model = GenerativeModel(model_name="models/gemini-1.5-pro", credentials=credentials)

# === 建立使用者對話記憶 ===
user_histories = {}

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return 'OK'

# === 回應文字訊息 ===
@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    user_id = event.source.user_id
    message_text = event.message.text.strip()

    # 初始化使用者對話歷史
    if user_id not in user_histories:
        user_histories[user_id] = []

    user_histories[user_id].append({"role": "user", "parts": [message_text]})

    try:
        response = model.generate_content(user_histories[user_id])
        ai_text = response.text.strip()
        user_histories[user_id].append({"role": "model", "parts": [ai_text]})
    except Exception as e:
        ai_text = "⚠️ 發生錯誤，請稍後再試。\n\n" + str(e)

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=ai_text)
    )

# === 回應圖片訊息 ===
@handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event):
    user_id = event.source.user_id
    message_id = event.message.id

    # 下載圖片
    image_path = f"static/images/{str(uuid.uuid4())}.jpg"
    message_content = line_bot_api.get_message_content(message_id)
    with open(image_path, 'wb') as f:
        for chunk in message_content.iter_content():
            f.write(chunk)

    try:
        with open(image_path, "rb") as image_file:
            image_bytes = image_file.read()
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')
        response = model.generate_content(["請用繁體中文幫我分析這張圖片內容", {"inline_data": {"mime_type": "image/jpeg", "data": image_base64}}])
        ai_text = response.text.strip()
    except Exception as e:
        ai_text = "⚠️ 圖片分析時發生錯誤，請稍後再試。\n\n" + str(e)

    # 刪除圖片
    if os.path.exists(image_path):
        os.remove(image_path)

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=ai_text)
    )

if __name__ == "__main__":
    app.run()
