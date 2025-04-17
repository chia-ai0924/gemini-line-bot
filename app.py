import os
from dotenv import load_dotenv
load_dotenv()
import json
import tempfile
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, ImageMessage, TextSendMessage

import google.generativeai as genai
from google.oauth2 import service_account

# 初始化 Flask App
app = Flask(__name__)

# 設定 LINE Bot 金鑰
line_bot_api = LineBotApi(os.environ.get("LINE_ACCESS_TOKEN"))
handler = WebhookHandler(os.environ.get("LINE_SECRET"))

# 載入 Google 服務帳戶金鑰（使用本地檔案）
credentials = service_account.Credentials.from_service_account_file(
    "gemini-line-bot-457106-aa75cedf9d80.json"
)
genai.configure(credentials=credentials)

# 模型名稱（如果已開通 vision 模型，建議使用 vision）
MODEL_NAME = "models/gemini-1.5-pro-vision"

# 處理 LINE Webhook
@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return "OK"

# 處理文字與圖片訊息
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

# 下載圖片並暫存
def download_image_from_line(message_id):
    message_content = line_bot_api.get_message_content(message_id)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as temp_file:
        for chunk in message_content.iter_content():
            temp_file.write(chunk)
        return temp_file.name

# 呼叫 Gemini 處理文字
def generate_gemini_text(prompt):
    model = genai.GenerativeModel(MODEL_NAME)
    response = model.generate_content(prompt)
    return response.text.strip()

# 呼叫 Gemini Vision 處理圖片
def generate_gemini_vision(image_path):
    model = genai.GenerativeModel(MODEL_NAME)
    with open(image_path, "rb") as img:
        response = model.generate_content(["請以繁體中文描述這張圖片的內容與可能用途：", img])
    return response.text.strip()

# 本地測試首頁
@app.route("/")
def home():
    return "LINE Gemini Bot is running."

if __name__ == "__main__":
    app.run(port=5000)
