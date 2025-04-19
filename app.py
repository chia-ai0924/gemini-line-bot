import os
import json
import requests
import time
from flask import Flask, request, abort, send_from_directory
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, ImageMessage, TextSendMessage
import google.generativeai as genai
from google.oauth2 import service_account
from datetime import datetime
import threading

app = Flask(__name__)

# 設定 Line API
line_bot_api = LineBotApi(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))

# 設定 Gemini Service Account
service_account_info = json.loads(os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON"))
credentials = service_account.Credentials.from_service_account_info(
    service_account_info,
    scopes=["https://www.googleapis.com/auth/cloud-platform"],
)
genai_client = genai.GenerativeModel(
    model_name="models/gemini-1.5-pro-vision",
    client_options={"api_endpoint": "https://generativelanguage.googleapis.com"},
    credentials=credentials,
)

# 建立圖片暫存資料夾
IMAGE_DIR = "./static/images"
if not os.path.exists(IMAGE_DIR):
    os.makedirs(IMAGE_DIR)

# 自動刪除圖片
def delete_file_later(filepath, delay=180):
    def delete():
        time.sleep(delay)
        if os.path.exists(filepath):
            os.remove(filepath)
    threading.Thread(target=delete).start()

@app.route("/static/images/<path:filename>")
def serve_image(filename):
    return send_from_directory(IMAGE_DIR, filename)

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return "OK"

@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    try:
        # 抓取圖片
        message_id = event.message.id
        image_content = line_bot_api.get_message_content(message_id).content
        filename = f"{message_id}.jpg"
        filepath = os.path.join(IMAGE_DIR, filename)
        with open(filepath, "wb") as f:
            f.write(image_content)

        delete_file_later(filepath)

        # 建立圖片網址（含 token 保護可加入）
        image_url = f"{request.url_root}static/images/{filename}"

        # 發送到 Gemini 分析
        response = genai_client.generate_content([
            {"text": "請用繁體中文說明這張圖片的內容，並給出有幫助的分析。"},
            {"image_url": image_url}
        ])
        reply_text = response.text.strip()
        line_bot_api.reply_message(
            event.reply_token, TextSendMessage(text=reply_text)
        )

    except Exception as e:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=f"⚠️ 圖片處理時發生錯誤，請稍後再試。\n\n{str(e)}"),
        )

@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
    try:
        user_input = event.message.text

        response = genai_client.generate_content([
            {"text": f"請用繁體中文回答以下問題：{user_input}"}
        ])
        reply_text = response.text.strip()
        line_bot_api.reply_message(
            event.reply_token, TextSendMessage(text=reply_text)
        )
    except Exception as e:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=f"⚠️ 回覆時發生錯誤，請稍後再試。\n\n{str(e)}"),
        )

if __name__ == "__main__":
    app.run()

