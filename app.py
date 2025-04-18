import os
import json
import base64
import tempfile
import traceback
from flask import Flask, request, abort
from dotenv import load_dotenv
from PIL import Image
from collections import deque, defaultdict
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, ImageMessage, TextSendMessage
from google.oauth2 import service_account
from google.ai.generativelanguage_v1 import GenerativeServiceClient
from google.ai.generativelanguage_v1.types import Content, Part

# 載入環境變數
load_dotenv()

app = Flask(__name__)

# LINE 機器人金鑰
line_bot_api = LineBotApi(os.environ["LINE_ACCESS_TOKEN"])
handler = WebhookHandler(os.environ["LINE_SECRET"])

# Google Gemini API 憑證
if os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON"):
    sa_info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    credentials = service_account.Credentials.from_service_account_info(sa_info)
else:
    credentials = service_account.Credentials.from_service_account_file("gemini-line-bot-457106-aa75cedf9d80.json")

client = GenerativeServiceClient(credentials=credentials)
MODEL = "models/gemini-1.5-pro-002"

# 使用者對話記憶（最多 5 輪）與授權狀態
chat_histories = defaultdict(lambda: deque(maxlen=10))
authorized_users = {}  # user_id: True/False
failed_attempts = defaultdict(int)

# 多組一次性密碼
available_passwords = {"0000": False}  # False = 尚未被使用

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
        user_id = event.source.user_id

        # 已封鎖的使用者（密碼錯誤三次）
        if failed_attempts[user_id] >= 3:
            return

        # 未授權者先驗證密碼
        if not authorized_users.get(user_id, False):
            msg = event.message.text.strip()
            if msg in available_passwords and not available_passwords[msg]:
                authorized_users[user_id] = True
                available_passwords[msg] = True  # 密碼作廢
                reply = "✅ 密碼正確，已啟用智慧對話功能！"
            else:
                failed_attempts[user_id] += 1
                if failed_attempts[user_id] >= 3:
                    return  # 停止回應
                reply = "❌ 密碼錯誤，請重新輸入。"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
            return

        # 授權者可進行正常對話
        if isinstance(event.message, TextMessage):
            user_input = event.message.text.strip()
            reply = handle_text(user_id, user_input)

        elif isinstance(event.message, ImageMessage):
            message_id = event.message.id
            image_path = download_image_from_line(message_id)
            reply = handle_image(image_path)
            os.remove(image_path)

        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

    except Exception as e:
        error_msg = traceback.format_exc()
        print("❌ 發生錯誤：", error_msg)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="⚠️ 系統錯誤，請稍後再試"))

def handle_text(user_id, user_input):
    history = list(chat_histories[user_id])
    history.append(Part(text=f"使用者說（請用繁體中文回覆）：{user_input}"))
    content = Content(parts=history)

    response = client.generate_content(model=MODEL, contents=[content])
    answer = response.candidates[0].content.parts[0].text.strip()

    # 將問與答加入記憶
    chat_histories[user_id].append(Part(text=answer))
    return answer

def handle_image(image_path):
    with open(image_path, "rb") as f:
        image_data = f.read()
    image_base64 = base64.b64encode(image_data).decode("utf-8")

    content = Content(parts=[
        Part(text="請用繁體中文詳細說明這張圖片的內容與用途："),
        Part(inline_data={"mime_type": "image/jpeg", "data": image_base64})
    ])

    response = client.generate_content(model=MODEL, contents=[content])
    return response.candidates[0].content.parts[0].text.strip()

def download_image_from_line(message_id):
    message_content = line_bot_api.get_message_content(message_id)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as temp_file:
        for chunk in message_content.iter_content():
            temp_file.write(chunk)
        return temp_file.name

@app.route("/")
def home():
    return "Gemini LINE Bot 正在執行中！"

if __name__ == "__main__":
    app.run(port=5000)