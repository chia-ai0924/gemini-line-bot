from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage, ImageMessage
import os, json, time
import google.generativeai as genai
from PIL import Image
import requests
from io import BytesIO

# ========== 基本設定 ==========
app = Flask(__name__)
line_bot_api = LineBotApi(os.environ.get("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.environ.get("LINE_CHANNEL_SECRET"))
genai.configure(service_account=json.loads(os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")))
model = genai.GenerativeModel(model_name="models/gemini-1.5-pro")

# ========== 密碼與授權邏輯 ==========
password_list = [
    "921", "122", "321", "924", "901", "918", "519", "802", "0519", "603",
    "104", "123", "861", "010", "020", "030", "040", "050", "060", "070"
]
authorized_users = set()
used_passwords = set()
failed_attempts = {}

def check_authorization(user_id, text):
    # 已授權
    if user_id in authorized_users:
        return True, None

    # 解鎖密語
    if text.strip() == "放我進來":
        failed_attempts.pop(user_id, None)
        return False, None

    # 密碼驗證
    if text in password_list and text not in used_passwords:
        authorized_users.add(user_id)
        used_passwords.add(text)
        failed_attempts.pop(user_id, None)
        return True, "✅ 驗證成功，歡迎使用 AI！請開始對話。"

    # 密碼錯誤處理
    failed_attempts[user_id] = failed_attempts.get(user_id, 0) + 1
    attempts = failed_attempts[user_id]
    if attempts >= 3:
        return False, "⛔ 密碼錯誤已達 3 次，帳號已封鎖。請輸入密語「放我進來」來解除。"
    else:
        return False, f"⚠️ 密碼錯誤（已輸入 {attempts} 次），請重新輸入啟用密碼（錯誤達 3 次將被封鎖）"

# ========== 對話記憶 ==========
user_histories = {}

def update_history(user_id, role, content):
    history = user_histories.setdefault(user_id, [])
    history.append({"role": role, "parts": [content]})
    if len(history) > 10:
        history.pop(0)

# ========== 圖片處理 ==========
def download_image(image_id):
    headers = {'Authorization': f'Bearer {os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")}'}
    res = requests.get(f"https://api-data.line.me/v2/bot/message/{image_id}/content", headers=headers)
    return Image.open(BytesIO(res.content))

# ========== 回覆處理 ==========
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except Exception as e:
        print("發生錯誤：", e)
        return 'Error', 500
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
    user_id = event.source.user_id
    text = event.message.text.strip()

    authorized, message = check_authorization(user_id, text)
    if not authorized:
        if message:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=message))
        return

    if message:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=message))
        return

    update_history(user_id, "user", text)
    try:
        response = model.generate_content(user_histories[user_id])
        reply = response.text.strip()
        update_history(user_id, "model", reply)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
    except Exception as e:
        print("文字處理錯誤：", e)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="⚠️ 回覆發生錯誤，請稍後再試。"))

@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    user_id = event.source.user_id
    authorized, message = check_authorization(user_id, "")
    if not authorized:
        if message:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=message))
        return

    image_id = event.message.id
    try:
        img = download_image(image_id)
        response = model.generate_content([{"role": "user", "parts": ["請用繁體中文幫我看這張圖片在說什麼？", img]}])
        reply = response.text.strip()
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
    except Exception as e:
        print("圖片處理錯誤：", e)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="⚠️ 圖片分析失敗，請稍後再試。"))

# ========== 啟動應用 ==========
if __name__ == "__main__":
    app.run()
