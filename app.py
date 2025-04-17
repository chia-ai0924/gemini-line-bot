import os
import json
import tempfile
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, ImageMessage, TextSendMessage

import google.generativeai as genai
from google.oauth2 import service_account
from dotenv import load_dotenv
load_dotenv()

# 初始化 Flask App
app = Flask(__name__)

# LINE Bot 金鑰
line_bot_api = LineBotApi(os.environ.get("LINE_ACCESS_TOKEN"))
handler = WebhookHandler(os.environ.get("LINE_SECRET"))

# 判斷金鑰來源：Render 的 JSON or 本地金鑰檔
if os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON"):
    service_account_info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    credentials = service_account.Credentials.from_service_account_info(service_account_info)
else:
    credentials = service_account.Credentials.from_service_account_file("gemini-line-bot-457106-aa75cedf9d80.json")

genai.configure(credentials=credentials)

# 模型名稱
MODEL_NAME = "models/gemini-1.5-pro-vision"

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK"

@handler.add(MessageEvent, message=(TextMessage, ImageMessage))
def handle_message(event):
    try:
        if isinstance(event.message, TextMessage):
            user_input = event.message.text
            response = generate_gemini_text(user_input)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=response))

        elif isinstance(event.message, ImageMessage):
            message_id = event.message.id
            image_path = download_image_from_line(message_id)
            response = generate_gemini_vision(image_path)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=response))
            os.remove(image_path)

    except Exception as e:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"⚠️ 發生錯誤：{str(e)}"))

# 下載 LINE 傳來的圖片
def download_image_from_line(message_id):
    message_content = line_bot_api.get_message_content(message_id)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as temp_file:
        for chunk in message_content.iter_content():
            temp_file.write(chunk)
        return temp_file.name

# Gemini 處理文字
def generate_gemini_text(prompt):
    model = genai.GenerativeModel(MODEL_NAME)
    response = model.generate_content(prompt)
    return response.text.strip()

# Gemini 處理圖片（已修正傳入格式）
def generate_gemini_vision(image_path):
    model = genai.GenerativeModel(MODEL_NAME)
    with open(image_path, "rb") as img_file:
        image_bytes = img_file.read()
        response = model.generate_content([
            "請以繁體中文描述這張圖片的內容與可能用途：", 
            {"mime_type": "image/jpeg", "data": image_bytes}
        ])
    return response.text.strip()

@app.route("/")
def home():
    return "LINE Gemini Bot is running."

if __name__ == "__main__":
    app.run(port=5000)

