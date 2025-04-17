import os
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, ImageMessage
import google.generativeai as genai
import requests
import base64

# 初始化 Flask 應用
app = Flask(__name__)

# LINE 機器人密鑰
line_bot_api = LineBotApi(os.environ.get("LINE_ACCESS_TOKEN"))
handler = WebhookHandler(os.environ.get("LINE_SECRET"))

# 設定 Gemini API 金鑰
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
model = genai.GenerativeModel(model_name="models/gemini-1.5-pro-vision")

@app.route("/")
def home():
    return "LINE Gemini Bot is running."

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return 'OK'

# 處理文字與圖片訊息事件
@handler.add(MessageEvent, message=(TextMessage, ImageMessage))
def handle_message(event):
    if isinstance(event.message, TextMessage):
        user_text = event.message.text
        gemini_response = model.generate_content([{"text": user_text}])
        reply_text = gemini_response.text if hasattr(gemini_response, "text") else "⚠️ 發生錯誤，請稍後再試"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))

    elif isinstance(event.message, ImageMessage):
        # 取得圖片內容
        image_content = line_bot_api.get_message_content(event.message.id)
        image_data = image_content.content
        image_base64 = base64.b64encode(image_data).decode("utf-8")

        # 發送給 Gemini 處理圖片
        gemini_response = model.generate_content(
            [ 
                {"text": "請分析這張圖片內容，並用繁體中文詳細說明"},
                {
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": image_base64
                    }
                }
            ]
        )
        reply_text = gemini_response.text if hasattr(gemini_response, "text") else "⚠️ 圖片處理失敗，請改傳其他圖片"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))

# 啟動應用（Render 不需要）
if __name__ == "__main__":
    app.run()
