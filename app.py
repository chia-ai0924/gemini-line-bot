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
    messages = [
        {"role": "user", "parts": [f"你現在的角色是：{system_role}。請用這個角色來回答問題。"]},
        *history,
        {"role": "user", "parts": [msg]}
    ]

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

        preview_response = model.generate_content([
            {"role": "user", "parts": [
                {"text": "這張圖片的內容大致上是什麼？請用繁體中文簡短說明，約10字以內。"},
                {"inline_data": {"mime_type": "image/jpeg", "data": image_bytes}}
            ]}
        ])
        preview_text = preview_response.text.strip()

        if any(word in preview_text for word in ["手", "腳", "傷", "紅腫", "瘀青", "醫療", "外傷", "牙齒"]):
            prompt = "你是具備醫療常識的 AI 小護士，請根據圖片推論是否有可見異常並清楚說明可能的健康問題與建議（不超過 5 句話）。此為 AI 分析建議，無法替代專業醫療診斷。"
        elif any(word in preview_text for word in ["數學", "國語", "題目", "公式", "文字"]):
            prompt = "你是一位 AI 小老師，請協助解釋這張圖片中的題目或文字內容，並以繁體中文簡潔回答（不超過 5 句話）。"
        elif any(word in preview_text for word in ["植物", "花", "食物", "餐點", "家裡", "房間"]):
            prompt = "你是 AI 生活助理，請用輕鬆語氣描述圖片中的內容，並給予實用或有趣的說明（不超過 5 句話）。"
        elif any(word in preview_text for word in ["日文", "メニュー", "カタカナ", "ひらがな"]):
            prompt = "這張圖片是日文內容，請翻譯為繁體中文並以輕鬆自然的語氣簡短整理重點。回覆不超過 3 句話，幫助使用者快速理解重點即可。"
        else:
            prompt = "請描述這張圖片的內容，並使用繁體中文自然說明（不超過 5 句話）。"

        response = model.generate_content([
            {"role": "user", "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": "image/jpeg", "data": image_bytes}}
            ]}
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

@app.route("/static/images/<filename>")
def serve_image(filename):
    return send_from_directory(TEMP_DIR, filename)

if __name__ == '__main__':
    app.run(debug=True)

