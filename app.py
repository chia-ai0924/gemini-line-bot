# ✅ 加入 Gemini 文字回覆 + 圖片分析 + 多輪記憶 + 角色切換按鈕 + 選單處理 + 自動建立 Rich Menu

import os
import json
import requests
import shutil
import google.generativeai as genai
from flask import Flask, request, abort, send_from_directory
from google.oauth2 import service_account
from linebot import LineBotApi, WebhookHandler
from linebot.models import (MessageEvent, TextMessage, ImageMessage,
                            TextSendMessage, TemplateSendMessage, ButtonsTemplate,
                            PostbackAction, PostbackEvent, RichMenu, RichMenuArea, URIAction, PostbackAction)

app = Flask(__name__)

# ✅ LINE 設定
line_bot_api = LineBotApi(os.environ.get("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.environ.get("LINE_CHANNEL_SECRET"))

# ✅ Gemini 設定（使用 API 金鑰）
genai.configure(api_key=os.environ.get("GOOGLE_API_KEY"))
model = genai.GenerativeModel("gemini-1.5-pro-vision")

# ✅ 圖片暫存資料夾
TEMP_DIR = "static/images"
os.makedirs(TEMP_DIR, exist_ok=True)

# ✅ 使用者對話記憶
user_histories = {}
user_roles = {}  # 儲存使用者選擇的角色

# ✅ 角色指令選單
ROLES = {
    "nurse": "你是親切專業的 AI 小護士，會給健康建議。",
    "teacher": "你是溫柔博學的 AI 小老師，幫助學生理解知識。",
    "assistant": "你是高效率的生活助理，協助處理日常問題。"
}

# ✅ 啟動時建立 Rich Menu（只會執行一次）
def create_rich_menu():
    try:
        menus = line_bot_api.get_rich_menu_list()
        if menus:
            print("已存在 Rich Menu，略過建立")
            return

        rich_menu = RichMenu(
            size={"width": 2500, "height": 1686},
            selected=True,
            name="角色選單",
            chat_bar_text="點我切換角色",
            areas=[
                RichMenuArea(
                    bounds={"x": 0, "y": 0, "width": 833, "height": 1686},
                    action=PostbackAction(label="🩺 小護士", data="role_nurse")
                ),
                RichMenuArea(
                    bounds={"x": 834, "y": 0, "width": 833, "height": 1686},
                    action=PostbackAction(label="📚 小老師", data="role_teacher")
                ),
                RichMenuArea(
                    bounds={"x": 1667, "y": 0, "width": 833, "height": 1686},
                    action=PostbackAction(label="🧭 助理", data="role_assistant")
                )
            ]
        )

        rich_menu_id = line_bot_api.create_rich_menu(rich_menu)
        with open("角色選單.png", "rb") as f:
            line_bot_api.set_rich_menu_image(rich_menu_id, "image/png", f)
        line_bot_api.set_default_rich_menu(rich_menu_id)
        print("✅ Rich Menu 已建立並套用")
    except Exception as e:
        print("Rich Menu 建立失敗:", e)

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
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"✅ 角色已切換為：{role_key}，你現在的 AI 身分是：{ROLES[role_key]}")
            )

@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    user_id = event.source.user_id
    msg = event.message.text.strip()

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
    messages = [{"role": "system", "parts": [system_role]}] + history
    messages.append({"role": "user", "parts": [msg]})

    try:
        response = model.generate_content(messages)
        reply = response.text.strip()
        history.append({"role": "user", "parts": [msg]})
        history.append({"role": "model", "parts": [reply]})
        user_histories[user_id] = history[-10:]
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
    except Exception as e:
        print("Text error:", e)
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

        response = model.generate_content([
            {
                "role": "user",
                "parts": [
                    {"text": "請分析這張圖片的內容，若非中文請翻譯並以繁體中文說明："},
                    {"inline_data": {"mime_type": "image/jpeg", "data": open(image_path, "rb").read()}}
                ]
            }
        ])
        reply = response.text.strip()
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
    except Exception as e:
        print("Image error:", e)
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
    create_rich_menu()
    app.run(debug=True)
