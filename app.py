import os
import base64
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, ImageMessage, TextSendMessage

import google.generativeai as genai

# 初始化 Flask 與 LINE SDK
app = Flask(__name__)
line_bot_api = LineBotApi(os.environ.get("LINE_ACCESS_TOKEN"))
handler = WebhookHandler(os.environ.get("LINE_SECRET"))

# 設定 Gemini API 金鑰
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

# 初始化 Gemini 1.5 Pro Vision 模型（v1 API）
model = genai.GenerativeModel(
    model_name="models/gemini-1.5-pro-vision",
    generation_config={
        "temperature": 0.9,
        "top_p": 1,
        "top_k": 1,
        "max_output_tokens": 2048,
    },
)

# Webhook 接收端點
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
        response = model.generate_content(
            [{"role": "user", "parts": [user_text]}],
            stream=False
        )
        reply_text = response.text.strip()
    except Exception as e:
        reply_text = f"❌ 發生錯誤：{str(e)}"
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))

# 處理圖片訊息
@handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event):
    try:
        # 取得圖片內容
        image_content = line_bot_api.get_message_content(event.message.id)
        image_data = image_content.content
        image_bytes = image_data if isinstance(image_data, bytes) else b''.join(image_data)

        # base64 編碼
        image_part = {
            "inline_data": {
                "mime_type": "image/jpeg",
                "data": base64.b64encode(image_bytes).decode("utf-8")
            }
        }

        # Gemini prompt 組合
        parts = [
            {"text": "請用繁體中文描述這張圖片的內容，若有外語請翻譯並整合說明。"},
            image_part
        ]

        response = model.generate_content(parts, stream=False)
        answer = response.text.strip()
    except Exception as e:
        answer = f"❌ 圖片處理失敗：{str(e)}"

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=answer))

# 本地測試時啟動 Flask（Render 不會用到）
if __name__ == "__main__":
    app.run()

