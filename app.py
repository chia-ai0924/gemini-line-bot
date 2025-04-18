from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, ImageMessage, TextSendMessage
import os
import json
import base64
import requests
import google.generativeai as genai
from google.oauth2.service_account import Credentials
from PIL import Image
from io import BytesIO
import tempfile

app = Flask(__name__)

# 初始化 LINE API
line_bot_api = LineBotApi(os.environ.get("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.environ.get("LINE_CHANNEL_SECRET"))

# 初始化 Gemini（使用 Service Account）
service_account_info = json.loads(os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON"))
credentials = Credentials.from_service_account_info(service_account_info)
genai.configure(credentials=credentials)
model = genai.GenerativeModel(model_name="models/gemini-1.5-pro")

# 對話記憶容器
user_histories = {}

# 設定圖片暫存路徑
TEMP_IMAGE_DIR = "./static/images"
os.makedirs(TEMP_IMAGE_DIR, exist_ok=True)

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except Exception as e:
        print(f"❌ 發生錯誤：\n{e}")
        abort(400)
    return 'OK'

# 清理圖片暫存
def cleanup_temp_images():
    for file in os.listdir(TEMP_IMAGE_DIR):
        path = os.path.join(TEMP_IMAGE_DIR, file)
        if os.path.isfile(path):
            os.remove(path)

@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    user_id = event.source.user_id

    # 取得圖片
    message_content = line_bot_api.get_message_content(event.message.id)
    image_data = message_content.content
    image = Image.open(BytesIO(image_data))
    
    # 儲存為暫存檔案
    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg", dir=TEMP_IMAGE_DIR) as temp_file:
        image_path = temp_file.name
        image.save(image_path)

    try:
        # 發送給 Gemini 分析
        with open(image_path, "rb") as f:
            img = Image.open(f)
            img_bytes = f.read()

        response = model.generate_content([
            "請分析這張圖片，並用繁體中文說明內容或提供有用的資訊。",
            img_bytes
        ])
        reply = response.text
    except Exception as e:
        print(f"❌ 圖片分析錯誤：{e}")
        reply = "⚠️ 圖片處理時發生錯誤，請稍後再試。"

    # 回覆使用者
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply)
    )
    cleanup_temp_images()

@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
    user_id = event.source.user_id
    msg = event.message.text.strip()

    # 多輪對話記憶初始化
    if user_id not in user_histories:
        user_histories[user_id] = []

    # 加入歷史對話
    user_histories[user_id].append({"role": "user", "parts": [msg]})

    try:
        # 回覆內容
        response = model.generate_content(user_histories[user_id])
        reply = response.text

        # 加入機器人回應到記憶中
        user_histories[user_id].append({"role": "model", "parts": [reply]})

    except Exception as e:
        print(f"❌ 回覆錯誤：{e}")
        reply = "⚠️ 回覆發生錯誤，請稍後再試。"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply)
    )

if __name__ == "__main__":
    app.run()
