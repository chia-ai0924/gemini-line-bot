import os
import traceback
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import google.generativeai as genai
from google.api_core.exceptions import NotFound

# 設定 LINE 與 Gemini API 金鑰
line_bot_api = LineBotApi(os.getenv("LINE_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_SECRET"))
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

app = Flask(__name__)

# 嘗試載入 Gemini 模型（使用 v1 正式版）
try:
    model = genai.GenerativeModel(model_name="models/gemini-1.5-pro-vision")
except Exception as e:
    print("❌ 載入 Gemini 模型失敗：", e)
    model = None

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except Exception as e:
        print("❌ LINE Webhook 錯誤：", e)
        traceback.print_exc()
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_text = event.message.text
    reply = ""

    if not model:
        reply = "❌ 尚未正確初始化 Gemini 模型，請稍後再試。"
    else:
        try:
            gemini_response = model.generate_content([{"text": user_text}])
            reply = gemini_response.text.strip()
        except NotFound as nf:
            print("❌ 找不到模型，可能模型名稱錯誤或帳號無權限：", nf)
            try:
                # 額外偵錯：列出所有可用模型
                models = genai.list_models()
                available = "\n".join([m.name for m in models if "generateContent" in m.supported_generation_methods])
                reply = "⚠️ 模型無效或無法使用。\n請確認是否已啟用 Gemini 1.5 Pro Vision。\n\n【可用模型】:\n" + available
            except Exception as list_err:
                print("⚠️ 列出模型失敗：", list_err)
                reply = "❌ 模型錯誤，且無法取得模型列表。\n請聯絡管理者。"
        except Exception as e:
            print("❌ 呼叫 Gemini 發生錯誤：", e)
            traceback.print_exc()
            reply = "❌ AI 回覆失敗，請稍後再試。"

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

if __name__ == "__main__":
    app.run()
