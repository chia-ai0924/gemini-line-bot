# ✅ Gemini 1.5 Pro (支援 Vision) with Service Account 登入（v1beta 相容）

import os
import json
import traceback
import requests
import shutil
import google.generativeai as genai
from flask import Flask, request, abort, send_from_directory
from google.oauth2 import service_account
from linebot import LineBotApi, WebhookHandler
from linebot.models import (MessageEvent, TextMessage, ImageMessage,
                            TextSendMessage, TemplateSendMessage, ButtonsTemplate,
                            PostbackAction, PostbackEvent, RichMenu, RichMenuArea, URIAction)

app = Flask(__name__)

# ✅ LINE 設定
line_bot_api = LineBotApi(os.environ.get("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.environ.get("LINE_CHANNEL_SECRET"))

# ✅ Gemini 設定（Service Account + v1beta）
service_account_info = json.loads(os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON"))
credentials = service_account.Credentials.from_service_account_info(service_account_info)
genai.configure(credentials=credentials)
model = genai.GenerativeModel("models/gemini-1.5-pro-latest")

# ✅ 印出可用模型清單
try:
    print("\n📋 可用模型清單：")
    for m in genai.list_models():
        print("✅", m.name)
except Exception as e:
    print("❌ 模型列印錯誤：", e)

# ✅ 圖片暫存資料夾
TEMP_DIR = "static/images"
os.makedirs(TEMP_DIR, exist_ok=True)

user_histories = {}
user_roles = {}

ROLES = {
    "nurse": "你是親切專業的 AI 小護士，會給健康建議。",
    "teacher": "你是溫柔博學的 AI 小老師，幫助學生理解知識。",
    "assistant": "你是高效率的生活助理，協助處理日常問題。"
}

ROLE_WELCOME = {
    "nurse": "我是你的專屬 AI 小護士，我會比對一切有關醫療疾病相關的資訊，整合你的需求來做回應。請問有什麼需要幫忙的嗎？",
    "teacher": "嗨，我是 AI 小老師，準備好一起學習新知識了嗎？我可以幫你解釋課題、複習觀念，也可以回答你對世界的各種好奇喔。",
    "assistant": "你好！我是你的 AI 生活助理，可以幫你查資訊、列待辦清單、提醒重要事項，讓生活更有效率。請問今天需要我幫忙什麼呢？"
}

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except Exception as e:
        print("Webhook Error:", e)
        abort(400)
    return 'OK'

@handler.add(PostbackEvent)
def handle_postback(event):
    user_id = event.source.user_id
    data = event.postback.data
    if data.startswith("role_"):
        role_key = data.replace("role_", "")
        if role_key in ROLES:
            user_roles[user_id] = ROLES[role_key]
            welcome = ROLE_WELCOME.get(role_key, "你現在的 AI 角色已更新。")
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=welcome)
            )

@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    user_id = event.source.user_id
    msg = event.message.text.strip()

    if msg in ["🩺 AI 小護士", "📚 AI 小老師", "🧭 生活助理"]:
        role_key = {
            "🩺 AI 小護士": "nurse",
            "📚 AI 小老師": "teacher",
            "🧭 生活助理": "assistant"
        }[msg]
        user_roles[user_id] = ROLES[role_key]
        welcome = ROLE_WELCOME.get(role_key, f"✅ 你現在的 AI 身分是：{ROLES[role_key]}")
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=welcome)
        )
        return

    if msg == "角色選單":
        buttons_template = ButtonsTemplate(
            title='請選擇角色', text='切換你希望的 AI 角色：',
            actions=[
                PostbackAction(label='🩺 AI 小護士', data='role_nurse'),
                PostbackAction(label='📚 AI 小老師', data='role_teacher'),
                PostbackAction(label='🧭 生活助理', data='role_assistant')
            ]
        )
        template_message = TemplateSendMessage(alt_text='角色選單', template=buttons_template)
        line_bot_api.reply_message(event.reply_token, template_message)
        return

    history = user_histories.get(user_id, [])
    system_role = user_roles.get(user_id, ROLES["assistant"])
    messages = history + [{"role": "user", "parts": [f"{system_role}\n{msg}"]}]

    try:
        response = model.generate_content(messages)
        reply = response.text.strip()
        history.append({"role": "user", "parts": [msg]})
        history.append({"role": "model", "parts": [reply]})
        user_histories[user_id] = history[-10:]
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
    except Exception as e:
        print("Text error:", e)
        traceback.print_exc()
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ 回覆錯誤，請稍後再試。"))

@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    user_id = event.source.user_id
    msg_id = event.message.id
    image_path = f"{TEMP_DIR}/{msg_id}.jpg"

    try:
        content = line_bot_api.get_message_content(msg_id).content
        with open(image_path, "wb") as f:
            f.write(content)

        with open(image_path, "rb") as image_file:
            image_bytes = image_file.read()

        response = model.generate_content([
            {
                "role": "user",
                "parts": [
                    {"text": "請分析這張圖片的內容，若非中文請翻譯並以繁體中文說明。"},
                    {"inline_data": {"mime_type": "image/jpeg", "data": image_bytes}}
                ]
            }
        ])
        reply = response.text.strip()
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
    except Exception as e:
        print("Image error:", e)
        traceback.print_exc()
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ 圖片分析錯誤。"))
    finally:
        try:
            os.remove(image_path)
        except:
            pass

@handler.add(MessageEvent)
def handle_other(event):
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text="請傳送文字或圖片。輸入『角色選單』可切換角色 🧠"))

@app.route("/static/images/<filename>")
def serve_image(filename):
    return send_from_directory(TEMP_DIR, filename)

if __name__ == '__main__':
    app.run(debug=True)
