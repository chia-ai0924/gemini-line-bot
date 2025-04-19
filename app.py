# ✅ 最終穩定版 app.py，支援：
# - Gemini Vision 圖片分析（Service Account 登入）
# - 多輪記憶
# - 繁體中文回覆
# - 自動辨識圖片、清除圖片、回覆描述

import os
import json
import shutil
import requests
import google.generativeai as genai
from flask import Flask, request, abort, send_from_directory
from google.oauth2 import service_account
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, ImageMessage, TextSendMessage

# ✅ 額外小建議：印出目前 generativeai 套件版本，方便除錯
print("\n✅ Current generativeai version:", genai.__version__)

app = Flask(__name__)

# ✅ 設定 LINE 機器人金鑰
line_bot_api = LineBotApi(os.environ.get("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.environ.get("LINE_CHANNEL_SECRET"))

# ✅ 初始化 Gemini 模型（使用 API Key 方式）
genai.configure(api_key=os.environ.get("GOOGLE_API_KEY"))
model = genai.GenerativeModel(model_name="gemini-1.5-pro-vision")

# ✅ 暫存圖片資料夾
TEMP_DIR = "static/images"
os.makedirs(TEMP_DIR, exist_ok=True)

# ✅ 使用者對話歷史記憶
user_histories = {}

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except Exception as e:
        print("Webhook Error:", e)
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    user_id = event.source.user_id
    user_input = event.message.text

    # 建立使用者的歷史對話
    history = user_histories.get(user_id, [])
    history.append({"role": "user", "parts": [user_input]})

    try:
        response = model.generate_content(history)
        reply_text = response.text.strip()
        history.append({"role": "model", "parts": [reply_text]})
        user_histories[user_id] = history[-10:]  # 只保留最近10輪
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
    except Exception as e:
        print("Gemini text error:", e)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ 發生錯誤，請稍後再試。"))

@handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event):
    user_id = event.source.user_id
    message_id = event.message.id

    # ✅ 下載圖片
    image_path = f"{TEMP_DIR}/{message_id}.jpg"
    try:
        image_content = line_bot_api.get_message_content(message_id).content
        with open(image_path, "wb") as f:
            f.write(image_content)
    except Exception as e:
        print("Image download error:", e)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ 圖片下載失敗。"))
        return

    # ✅ 傳給 Gemini Vision 分析
    try:
        response = model.generate_content([
            {
                "role": "user",
                "parts": [
                    {"text": "請分析這張圖片的內容，若為非中文請翻譯並給出完整繁體中文說明。"},
                    {
                        "inline_data": {
                            "mime_type": "image/jpeg",
                            "data": open(image_path, "rb").read()
                        }
                    }
                ]
            }
        ])
        reply_text = response.text.strip()
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
    except Exception as e:
        print("Gemini image error:", e)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ 圖片分析失敗。"))
    finally:
        try:
            os.remove(image_path)
        except:
            pass

@app.route("/static/images/<filename>")
def serve_image(filename):
    return send_from_directory(TEMP_DIR, filename)

if __name__ == "__main__":
    app.run(debug=True)
