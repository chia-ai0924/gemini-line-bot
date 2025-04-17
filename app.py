import os
import tempfile
import requests
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, ImageMessage, TextSendMessage

import google.generativeai as genai
from google.generativeai.types.content_types import Content, Part

# 初始化
app = Flask(__name__)
line_bot_api = LineBotApi(os.environ.get("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.environ.get("LINE_CHANNEL_SECRET"))
genai.configure(api_key=os.environ.get("GOOGLE_API_KEY"))

# 建立 Gemini 1.5 Pro Vision 模型
model = genai.GenerativeModel(model_name="models/gemini-1.5-pro-vision")

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
def handle_text_message(event):
    user_input = event.message.text
    try:
        response = model.generate_content(user_input)
        reply = response.text
    except Exception as e:
        reply = f"發生錯誤：{e}"
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

@handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event):
    try:
        # 取得圖片內容並暫存
        message_content = line_bot_api.get_message_content(event.message.id)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tf:
            for chunk in message_content.iter_content():
                tf.write(chunk)
            temp_path = tf.name

        # 讀取圖片並送入 Gemini 模型
        with open(temp_path, "rb") as img:
            image_bytes = img.read()

        vision_input: Content = [
            Part.from_data(image_bytes, mime_type="image/jpeg"),
            Part.from_text("請用繁體中文說明這張圖片的內容，若包含文字請翻譯並整合說明")
        ]

        response = model.generate_content(vision_input)
        reply = response.text
    except Exception as e:
        reply = f"發生錯誤：{e}"
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
