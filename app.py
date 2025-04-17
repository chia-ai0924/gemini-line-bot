import os
import json
import base64
import tempfile
from flask import Flask, request, abort
from dotenv import load_dotenv
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, ImageMessage, TextSendMessage

from google.oauth2 import service_account
from google.ai.generativelanguage_v1 import GenerativeServiceClient
from google.ai.generativelanguage_v1.types import Content, Part

load_dotenv()
app = Flask(__name__)

# LINE 金鑰
line_bot_api = LineBotApi(os.environ.get("LINE_ACCESS_TOKEN"))
handler = WebhookHandler(os.environ.get("LINE_SECRET"))

# Google Service Account 金鑰
if os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON"):
    service_account_info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    credentials = service_account.Credentials.from_service_account_info(service_account_info)
else:
    credentials = service_account.Credentials.from_service_account_file("gemini-line-bot-457106-aa75cedf9d80.json")

# Gemini v1 client
client = GenerativeServiceClient(credentials=credentials)
MODEL = "models/gemini-1.5-pro-vision-latest"  # ✅ 使用最新版 Vision 模型

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return "OK"

@handler.add(MessageEvent, message=(TextMessage, ImageMessage))
def handle_message(event):
    try:
        if isinstance(event.message, TextMessage):
            prompt = event.message.text
            reply = generate_text_response(prompt)
        elif isinstance(event.message, ImageMessage):
            message_id = event.message.id
            image_path = download_image_from_line(message_id)
            reply = generate_image_response(image_path)
            os.remove(image_path)

        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

    except Exception as e:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"⚠️ 發生錯誤：{str(e)}"))

# 處理文字
def generate_text_response(prompt):
    content = Content(parts=[Part(text=prompt)])
    response = client.generate_content(model=MODEL, contents=[content])
    return response.candidates[0].content.parts[0].text.strip()

# 處理圖片
def generate_image_response(image_path):
    with open(image_path, "rb") as f:
        image_data = f.read()
    image_base64 = base64.b64encode(image_data).decode("utf-8")

    content = Content(parts=[
        Part(text="請以繁體中文描述這張圖片的內容與可能用途："),
        Part(inline_data={"mime_type": "image/jpeg", "data": image_base64})
    ])

    response = client.generate_content(model=MODEL, contents=[content])
    return response.candidates[0].content.parts[0].text.strip()

# 下載 LINE 圖片
def download_image_from_line(message_id):
    message_content = line_bot_api.get_message_content(message_id)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as temp_file:
        for chunk in message_content.iter_content():
            temp_file.write(chunk)
        return temp_file.name

@app.route("/")
def home():
    return "Gemini LINE Bot is running!"

if __name__ == "__main__":
    app.run(port=5000)

