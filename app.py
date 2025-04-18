
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage, ImageMessage
import os, json, requests
from PIL import Image
from io import BytesIO

from google.oauth2 import service_account
from google.api_core.client_options import ClientOptions
from google.generativeai import GenerativeModel

# 初始化 Flask 與 LINE Bot
app = Flask(__name__)
line_bot_api = LineBotApi(os.environ.get("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.environ.get("LINE_CHANNEL_SECRET"))

# 初始化 Gemini（Service Account 模式）
service_info = json.loads(os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON"))
credentials = service_account.Credentials.from_service_account_info(service_info)
client_options = ClientOptions(api_endpoint="https://generativelanguage.googleapis.com/")
model = GenerativeModel(model_name="models/gemini-1.5-pro", credentials=credentials, client_options=client_options)

# 使用者多輪記憶
user_histories = {}

def update_history(user_id, role, content):
    history = user_histories.setdefault(user_id, [])
    history.append({"role": role, "parts": [content]})
    if len(history) > 10:
        history.pop(0)

# 圖片下載
def download_image(image_id):
    headers = {'Authorization': f'Bearer {os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")}'}
    res = requests.get(f"https://api-data.line.me/v2/bot/message/{image_id}/content", headers=headers)
    return Image.open(BytesIO(res.content))

# LINE webhook endpoint
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except Exception as e:
        print("Webhook 處理錯誤：", e)
        return 'Error', 500
    return 'OK'

# 處理文字訊息
@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
    user_id = event.source.user_id
    text = event.message.text.strip()

    update_history(user_id, "user", text)
    try:
        response = model.generate_content(user_histories[user_id])
        reply = response.text.strip()
        update_history(user_id, "model", reply)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
    except Exception as e:
        print("文字處理錯誤：", e)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="⚠️ 回覆發生錯誤，請稍後再試。"))

# 處理圖片訊息
@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    user_id = event.source.user_id
    image_id = event.message.id
    try:
        img = download_image(image_id)
        response = model.generate_content([
            {"role": "user", "parts": ["請用繁體中文幫我看這張圖片在說什麼？", img]}
        ])
        reply = response.text.strip()
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
    except Exception as e:
        print("圖片處理錯誤：", e)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="⚠️ 圖片分析失敗，請稍後再試。"))

# 啟動應用
if __name__ == "__main__":
    app.run()
