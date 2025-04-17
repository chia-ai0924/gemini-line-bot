from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import os
import google.generativeai as genai
from google.api_core.exceptions import NotFound, InvalidArgument

app = Flask(__name__)

# LINE 憑證
line_bot_api = LineBotApi(os.environ.get("LINE_ACCESS_TOKEN"))
handler = WebhookHandler(os.environ.get("LINE_SECRET"))

# Gemini 設定
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
MODEL_NAME = "models/gemini-1.5-pro-latest"

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return "OK"

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_text = event.message.text

    try:
        model = genai.GenerativeModel(model_name=MODEL_NAME)
        response = model.generate_content([{"text": user_text}])
        reply_text = response.text.strip() if response.text else "⚠️ Gemini 沒有回應內容。"
    except NotFound as e:
        available_models = "\n".join(
            m.name for m in genai.list_models() if "generateContent" in m.supported_generation_methods
        )
        reply_text = (
            "⚠️ 無法回應，請確認模型是否支援。\n可用模型：\n" + available_models
        )
    except InvalidArgument as e:
        reply_text = f"⚠️ 請求格式錯誤：{str(e)}"
    except Exception as e:
        reply_text = f"❌ 系統錯誤：{str(e)}"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )

if __name__ == "__main__":
    app.run()
