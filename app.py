import os
import traceback
from io import BytesIO
from PIL import Image
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, ImageMessage, TextSendMessage
import google.generativeai as genai

app = Flask(__name__)

LINE_ACCESS_TOKEN = os.environ.get("LINE_ACCESS_TOKEN")
LINE_SECRET = os.environ.get("LINE_SECRET")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_SECRET)
genai.configure(api_key=GEMINI_API_KEY)

try:
    model = genai.GenerativeModel("gemini-pro-vision")
except Exception as e:
    print("❌ 模型初始化失敗：", e)
    model = None

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except Exception as e:
        print("❌ webhook callback 錯誤：", e)
        traceback.print_exc()
        abort(400)
    return "OK"

@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
    user_text = event.message.text
    try:
        if not model:
            raise ValueError("模型尚未初始化")
        response = model.generate_content(user_text)
        reply_text = response.text.strip()
    except Exception as e:
        print("❌ Gemini 回覆錯誤：", e)
        traceback.print_exc()
        try:
            available_models = genai.list_models()
            usable = [m.name for m in available_models if "generateContent" in m.supported_generation_methods]
            reply_text = "⚠️ 無法回應，請確認模型是否支援。
可用模型：
" + "
".join(usable[:10])
        except Exception as ee:
            reply_text = f"❌ 系統錯誤：{str(e)}
（取得模型列表也失敗：{str(ee)}）"

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))

@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    try:
        image_content = line_bot_api.get_message_content(event.message.id)
        image_stream = BytesIO()
        for chunk in image_content.iter_content():
            image_stream.write(chunk)
        image_stream.seek(0)

        try:
            image = Image.open(image_stream)
        except Exception:
            raise ValueError("圖片格式解析失敗，請確認為 JPG/PNG 格式")

        response = model.generate_content([
            "請分析這張圖片內容，若包含文字請翻譯為繁體中文：",
            image
        ])
        reply_text = response.text.strip()
    except Exception as e:
        print("❌ 圖片處理錯誤：", e)
        traceback.print_exc()
        reply_text = f"⚠️ 圖片處理失敗：{str(e)}"

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))

if __name__ == "__main__":
    app.run()