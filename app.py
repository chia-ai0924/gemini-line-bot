import os
import tempfile
import traceback
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, ImageMessage, TextSendMessage
from google.oauth2 import service_account
from google.generativeai import GenerativeModel
import google.generativeai as genai
from PIL import Image
from dotenv import load_dotenv

# 載入 .env 變數
load_dotenv()

# 初始化 LINE bot
line_bot_api = LineBotApi(os.environ.get("LINE_ACCESS_TOKEN"))
handler = WebhookHandler(os.environ.get("LINE_SECRET"))

# 初始化 Gemini client
credentials = service_account.Credentials.from_service_account_file(
    os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
)
genai_client = genai.GenerativeModel(model_name="models/gemini-1.5-pro-002")
client = genai_client.start_chat(history=[])

app = Flask(__name__)

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except Exception as e:
        print("⚠️ 處理 LINE 訊息時發生錯誤：", e)
        traceback.print_exc()
        abort(400)

    return "OK"

@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
    user_text = event.message.text
    print(f"📩 收到文字訊息：{user_text}")
    try:
        response = client.send_message(user_text)
        reply = response.text
    except Exception as e:
        reply = f"⚠️ 發生錯誤：{e}"
        traceback.print_exc()

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    print("🖼️ 收到圖片訊息，準備處理中...")
    message_id = event.message.id

    try:
        # 下載圖片
        message_content = line_bot_api.get_message_content(message_id)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tf:
            for chunk in message_content.iter_content():
                tf.write(chunk)
            temp_image_path = tf.name

        print(f"✅ 圖片已儲存至暫存檔：{temp_image_path}")
        reply = generate_image_response(temp_image_path)

    except Exception as e:
        reply = f"⚠️ 圖片處理錯誤：{e}"
        traceback.print_exc()

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

def generate_image_response(image_path):
    print("✨ 使用 Gemini Vision 模型分析圖片中...")

    try:
        with Image.open(image_path) as img:
            prompt = "請用繁體中文說明這張圖片的內容。"
            content = [prompt, img]

            response = client.generate_content(contents=content)
            return response.text

    except Exception as e:
        print("❌ GPT 圖片分析錯誤：", e)
        traceback.print_exc()
        return f"⚠️ 發生錯誤：{e}"

if __name__ == "__main__":
    app.run()

