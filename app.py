from flask import Flask, request, abort, send_from_directory
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, ImageMessage, TextSendMessage, PostbackEvent
import os
import json
import requests
import threading
import time
import uuid
import shutil
import concurrent.futures
from google.oauth2.service_account import Credentials
import google.generativeai as genai

# 初始化 Flask
app = Flask(__name__)

# 設定 LINE Bot 金鑰
line_bot_api = LineBotApi(os.environ.get("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.environ.get("LINE_CHANNEL_SECRET"))

# 初始化 Gemini
service_account_info = json.loads(os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON"))
credentials = Credentials.from_service_account_info(service_account_info)
genai.configure(credentials=credentials, client_options={"api_endpoint": "https://generativeai.googleapis.com"})
model = genai.GenerativeModel(model_name="models/gemini-1.5-pro-latest", generation_config={"temperature": 0.7})

# Gemini 安全執行包裝器（含 timeout）
def safe_generate_content(parts, timeout=10):
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(model.generate_content, parts)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            raise TimeoutError("Gemini API 回應逾時")

# 建立使用者對話記憶 dict
user_histories = {}

# 使用者角色預設（角色切換用）
user_roles = {}
def get_role_prompt(role):
    if role == "nurse":
        return "你是貼心又有耐心的 AI 小護士，擅長照顧人並提供健康建議。請用親切語氣回答使用者問題。"
    elif role == "teacher":
        return "你是充滿耐心的 AI 小老師，擅長用簡單清楚的方式教導使用者。請用鼓勵語氣說明。"
    else:
        return "你是實用派的生活助理 AI，幫助使用者解決日常大小事，請用務實口吻精簡說明。"

# 自動清除圖片的背景任務
def auto_delete_image(path, delay=180):
    def delete():
        time.sleep(delay)
        if os.path.exists(path):
            os.remove(path)
    threading.Thread(target=delete).start()

# Webhook endpoint
@app.route("/callback", methods=["POST", "HEAD"])
def callback():
    if request.method == "HEAD":
        return "OK", 200
    signature = request.headers.get("X-Line-Signature")
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except Exception as e:
        print(f"Webhook error: {e}")
        abort(400)
    return "OK"

# 角色切換 postback
@handler.add(PostbackEvent)
def handle_postback(event):
    data = event.postback.data
    if data in ["nurse", "teacher", "assistant"]:
        user_roles[event.source.user_id] = data
        role_name = {"nurse": "AI 小護士", "teacher": "AI 小老師", "assistant": "生活助理"}[data]
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"你現在的角色是：{role_name}，有什麼我可以幫忙的嗎？"))

# 處理文字訊息
@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
    uid = event.source.user_id
    user_message = event.message.text.strip()

    role = user_roles.get(uid, "assistant")
    prompt = get_role_prompt(role)

    history = user_histories.get(uid, [])[-8:]
    history.append({"role": "user", "parts": [user_message]})

    try:
        response = safe_generate_content([{"role": "system", "parts": [prompt]}] + history)
        reply_text = response.text.strip()
    except Exception as e:
        print("文字訊息錯誤：", e)
        reply_text = "❌ 系統忙碌或出錯，請稍後再試一次。"

    history.append({"role": "model", "parts": [reply_text]})
    user_histories[uid] = history

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))

# 處理圖片訊息（分類角色 + 翻譯文字 + 三句補充）
@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    uid = event.source.user_id
    message_id = event.message.id
    image_content = line_bot_api.get_message_content(message_id).content

    image_id = str(uuid.uuid4())
    image_path = f"static/images/{image_id}.jpg"
    os.makedirs("static/images", exist_ok=True)
    with open(image_path, "wb") as f:
        f.write(image_content)
    auto_delete_image(image_path)

    with open(image_path, "rb") as img_file:
        image_bytes = img_file.read()

    try:
        preview = safe_generate_content([
            {"role": "user", "parts": [
                {"text": "請用繁體中文說明這張圖片大致上是什麼類型的內容，約 10 字以內"},
                {"inline_data": {"mime_type": "image/jpeg", "data": image_bytes}}
            ]}
        ])
        preview_text = preview.text.strip()

        if any(word in preview_text for word in ["手", "腳", "傷", "紅腫", "瘀青", "牙齒"]):
            system_prompt = get_role_prompt("nurse")
        elif any(word in preview_text for word in ["數學", "國語", "題目", "公式", "文字"]):
            system_prompt = get_role_prompt("teacher")
        elif any(word in preview_text for word in ["植物", "花", "食物", "餐點", "家裡", "房間"]):
            system_prompt = get_role_prompt("assistant")
        else:
            system_prompt = "請幫我翻譯這張圖片的所有文字為繁體中文，並補充 3 句建議或提醒。"

        translate_response = safe_generate_content([
            {"role": "system", "parts": [system_prompt]},
            {"role": "user", "parts": [
                {"text": "請幫我將圖片中的所有文字完整翻譯為繁體中文。"},
                {"inline_data": {"mime_type": "image/jpeg", "data": image_bytes}}
            ]}
        ])
        translated_text = translate_response.text.strip()

        summary_response = safe_generate_content([
            {"role": "user", "parts": [
                {"text": f"以下是圖片翻譯後的文字內容：{translated_text}\n請根據這段內容，補充 3 句繁體中文的說明、建議或提醒。"}
            ]}
        ])
        supplement = summary_response.text.strip()

        reply_text = f"📘 翻譯結果：\n{translated_text}\n\n💡 小提醒：\n{supplement}"

    except Exception as e:
        print("圖片訊息錯誤：", e)
        reply_text = "❌ 圖片分析失敗或回應逾時，請稍後再試一次。"

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))

# 測試首頁
@app.route("/")
def home():
    return "Gemini LINE Bot 運行中"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
