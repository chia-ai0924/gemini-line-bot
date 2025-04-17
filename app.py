from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, ImageMessage, TextSendMessage
import os
import google.generativeai as genai
import requests
from io import BytesIO
from PIL import Image

app = Flask(__name__)

# 讀取環境變數
line_bot_api = LineBotApi(os.environ.get("LINE_ACCESS_TOKEN"))
handler = WebhookHandler(os.environ.get("LINE_SECRET"))
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

# 使用 Gemini 1.5 Pro Vision 模型 (v1 API)
model = genai.GenerativeModel(model_name="gemini-1.5-pro-vision")

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except Exception as e:
        print(f"Error: {e}")
        abort(400)

    return "OK"

# 文字訊息處理
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_text = event.message.text
    try:
        gemini_response = model.generate_content(user_text)
        reply_text = gemini_response.text
    except Exception as e:
        reply_text = f"❌ 發生錯誤：{str(e)}"
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))

# 圖片訊息處理
@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    try:
        # 取得圖片內容
        message_content = line_bot_api.get_message_content(event.message.id)
        image_data = BytesIO(message_content.content)
        image = Image.open(image_data)

        # 使用 Gemini Vision 分析圖片
        gemini_response = model.generate_content([
            "請描述這張圖片的內容，並用繁體中文回答：",
            image
        ])
        reply_text = gemini_response.text
    except Exception as e:
        reply_text = f"❌ 圖片辨識失敗：{str(e)}"

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))

if __name__ == "__main__":
    app.run()
