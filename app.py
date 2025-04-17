from flask import Flask, request, abort, send_from_directory
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, ImageMessage, TextSendMessage
from google.generativeai import configure, GenerativeModel
import os, time, uuid, threading, shutil, mimetypes
import requests

# 初始化 Flask
app = Flask(__name__)

# 建立圖片儲存資料夾
IMAGE_DIR = "static/images"
os.makedirs(IMAGE_DIR, exist_ok=True)

# 載入環境變數（請設定在 Render 環境變數中）
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# 初始化 LINE Bot
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# 初始化 Gemini API
configure(api_key=GEMINI_API_KEY)
model = GenerativeModel("gemini-1.5-pro-vision-latest")

# 自動刪除圖片（3 分鐘後）
def delete_file_later(file_path, delay=180):
    def delete():
        time.sleep(delay)
        if os.path.exists(file_path):
            os.remove(file_path)
    threading.Thread(target=delete).start()

# 提供靜態圖片路徑給 Gemini
@app.route("/static/images/<filename>")
def serve_image(filename):
    return send_from_directory(IMAGE_DIR, filename)

# LINE callback
@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except Exception as e:
        print("handle error:", e)
        abort(400)
    return "OK"

# 接收訊息
@handler.add(MessageEvent, message=(TextMessage, ImageMessage))
def handle_message(event):
    user_id = event.source.user_id

    if isinstance(event.message, TextMessage):
        prompt = event.message.text.strip()
        reply = chat_with_gemini(prompt)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

    elif isinstance(event.message, ImageMessage):
        # 取得圖片
        image_id = str(uuid.uuid4())
        ext = ".jpg"
        file_path = os.path.join(IMAGE_DIR, image_id + ext)
        message_content = line_bot_api.get_message_content(event.message.id)

        with open(file_path, "wb") as f:
            for chunk in message_content.iter_content():
                f.write(chunk)

        delete_file_later(file_path)

        # Gemini 分析圖片與提示語
        image_url = request.host_url + "static/images/" + image_id + ext
        reply = vision_with_gemini(image_url)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

# Gemini 圖片分析回覆（含自動翻譯）
def vision_with_gemini(image_url):
    prompt = (
        "請分析這張圖片的內容，如果文字為英文或其他語言，請翻譯為繁體中文，"
        "並用親切、有智慧的語氣，幫我說明這張圖的內容。例如是菜單、公告、商品資訊，請進行條列與簡要整理。"
    )

    try:
        response = model.generate_content(
            [
                prompt,
                {
                    "mime_type": mimetypes.guess_type(image_url)[0],
                    "uri": image_url,
                },
            ],
            stream=False,
        )
        return response.text.strip()
    except Exception as e:
        return f"發生錯誤，無法分析圖片：{str(e)}"

# Gemini 回覆文字訊息
def chat_with_gemini(prompt):
    try:
        response = model.generate_content(prompt, stream=False)
        return response.text.strip()
    except Exception as e:
        return f"發生錯誤，無法取得回覆：{str(e)}"

# 入口
if __name__ == "__main__":
    app.run()
