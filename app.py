import os
import google.generativeai as genai
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, ImageMessage, TextSendMessage
import requests
from PIL import Image
from io import BytesIO

app = Flask(__name__)

line_bot_api = LineBotApi(os.environ.get("LINE_ACCESS_TOKEN"))
handler = WebhookHandler(os.environ.get("LINE_SECRET"))
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

# 使用目前可用的 vision 模型（經查證）
model = genai.GenerativeModel(model_name="gemini-pro-vision")

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except Exception as e:
        print("❌ webhook callback error:", e)
        abort(400)
    return "OK"

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_text = event.message.text.strip()
    try:
        gemini_response = model.generate_content([{"text": user_text}])
        reply_text = gemini_response.text.strip()
    except Exception as e:
        print("❌ Gemini 回應錯誤：", e)
        # 額外印出可用模型協助查錯
        try:
            available_models = [m.name for m in genai.list_models()]
            reply_text = f"⚠️ 模型無效或無法使用。
請確認是否已啟用 Gemini 1.5 Pro Vision。

【可用模型】:\n" + "\n".join(available_models[:20])
        except Exception as ee:
            reply_text = f"❌ 系統錯誤：{str(e)}\n（列出模型時也失敗：{str(ee)}）"

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))

@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    try:
        image_content = line_bot_api.get_message_content(event.message.id)
        image_data = BytesIO()
        for chunk in image_content.iter_content():
            image_data.write(chunk)
        image_data.seek(0)
        image = Image.open(image_data)

        gemini_response = model.generate_content([{"text": "請分析這張圖片內容"}, image])
        reply_text = gemini_response.text.strip()
    except Exception as e:
        print("❌ 圖片處理錯誤：", e)
        reply_text = "⚠️ 處理圖片時發生錯誤，請稍後再試"

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))

if __name__ == "__main__":
    app.run()