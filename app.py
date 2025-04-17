import os
import base64
import requests
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, ImageMessage, TextSendMessage

import google.generativeai as genai

# 初始化 Flask 與 LINE
app = Flask(__name__)
line_bot_api = LineBotApi(os.environ.get("LINE_ACCESS_TOKEN"))
handler = WebhookHandler(os.environ.get("LINE_SECRET"))

# 初始化 Gemini API
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-1.5-pro-vision")

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK"

# 處理文字訊息
@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    user_text = event.message.text
    try:
        response = model.generate_content([{"role": "user", "parts": [user_text]}])
        reply_text = response.text
    except Exception as e:
        reply_text = f"❌ 發生錯誤：{str(e)}"
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))

# 處理圖片訊息
@handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event):
    try:
        # 抓取圖片內容
        image_content = line_bot_api.get_message_content(event.message.id)
        image_data = image_content.content
        image_bytes = image_data if isinstance(image_data, bytes) else b''.join(image_data)

        # base64 編碼圖片
        image_part = {
            "inline_data": {
                "mime_type": "image/jpeg",
                "data": base64.b64encode(image_bytes).decode("utf-8")
            }
        }

        # 設定 prompt 與圖片內容
        prompt = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": "請用繁體中文描述這張圖片的內容，若有外語請翻譯並整合成一句清楚說明。"},
                        image_part
                    ]
                }
            ]
        }

        # 呼叫 Gemini 回覆
        response = model.generate_content(prompt["contents"])
        answer = response.text.strip()
    except Exception as e:
        answer = f"❌ 圖片處理失敗：{str(e)}"

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=answer))

# 本地測試用（Render 上不會用到）
if __name__ == "__main__":
    app.run()

