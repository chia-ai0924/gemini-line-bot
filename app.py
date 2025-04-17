import os
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import google.generativeai as genai
import requests
import base64

app = Flask(__name__)

# LINE config
line_bot_api = LineBotApi(os.environ.get("LINE_ACCESS_TOKEN"))
handler = WebhookHandler(os.environ.get("LINE_SECRET"))

# Gemini config (使用 v1 API)
genai.configure(api_key=os.environ.get("GOOGLE_API_KEY"))
model = genai.GenerativeModel(model_name="gemini-1.5-pro-vision")

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except Exception as e:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    user_text = event.message.text
    response = model.generate_content(user_text)
    reply = response.text.strip()
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

@handler.add(MessageEvent, message=TextMessage)
def handle_image_message(event):
    message_id = event.message.id
    content = line_bot_api.get_message_content(message_id)

    # 將圖片暫存並 base64 編碼
    image_data = content.content
    image_base64 = base64.b64encode(image_data).decode("utf-8")

    # 建構 Gemini Vision 請求
    response = model.generate_content([
        {
            "mime_type": "image/jpeg",
            "data": image_base64,
        },
        {
            "text": "請描述這張圖片的內容。",
        }
    ])
    reply = response.text.strip()
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

if __name__ == "__main__":
    app.run()
