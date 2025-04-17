from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import google.generativeai as genai
import os

app = Flask(__name__)

# 設定環境變數
line_bot_api = LineBotApi(os.environ.get("LINE_ACCESS_TOKEN"))
handler = WebhookHandler(os.environ.get("LINE_SECRET"))
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

# ✅ 使用 v1 API 初始化 Gemini 1.5 Pro Vision 模型
model = genai.GenerativeModel(
    model_name="models/gemini-1.5-pro-vision"
)

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except Exception as e:
        print(f"Webhook Error: {e}")
        abort(400)

    return "OK"

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_text = event.message.text
    try:
        response = model.generate_content([{"text": user_text}])
        reply_text = response.text.strip()
    except Exception as e:
        reply_text = f"❌ 發生錯誤：{str(e)}"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )

if __name__ == "__main__":
    app.run()
