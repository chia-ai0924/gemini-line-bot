from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, ImageMessage, TextMessage, TextSendMessage
import os
import base64
import requests
import google.generativeai as genai

# 初始化
app = Flask(__name__)

# LINE 機器人設定
line_bot_api = LineBotApi(os.environ.get("LINE_ACCESS_TOKEN"))
handler = WebhookHandler(os.environ.get("LINE_SECRET"))

# 設定 Gemini API 金鑰與模型
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
model = genai.GenerativeModel("models/gemini-1.5-pro-vision")

# 根路由
@app.route("/")
def home():
    return "Gemini LINE Bot is running."

# LINE webhook callback
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get("X-Line-Signature")
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# 處理文字與圖片訊息
@handler.add(MessageEvent, message=(TextMessage, ImageMessage))
def handle_message(event):
    if isinstance(event.message, TextMessage):
        user_text = event.message.text
        reply = gemini_reply(user_text)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

    elif isinstance(event.message, ImageMessage):
        image_content = line_bot_api.get_message_content(event.message.id)
        image_data = image_content.content
        image_bytes = image_data if isinstance(image_data, bytes) else b''.join(image_data)

        image_part = {
            "inline_data": {
                "mime_type": "image/jpeg",
                "data": base64.b64encode(image_bytes).decode("utf-8")
            }
        }

        prompt = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": "請幫我看這張圖片，說明內容是什麼，若有外語請翻譯成繁體中文"},
                        image_part
                    ]
                }
            ]
        }

        try:
            response = model.generate_content(prompt["contents"])
            answer = response.text.strip()
        except Exception as e:
            answer = f"圖片處理時發生錯誤：{str(e)}"

        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=answer))

# Gemini 處理文字
def gemini_reply(text):
    try:
        response = model.generate_content([{"role": "user", "parts": [text]}])
        return response.text.strip()
    except Exception as e:
        return f"無法取得 Gemini 回覆：{str(e)}"

if __name__ == "__main__":
    app.run()

