# 部署測試註解：嘗試換機器 2025-04-21 04:44

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
import socket
from datetime import datetime
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

# 處理文字訊息（使用非阻塞 thread）
def process_text_gemini(uid, user_message, history, prompt):
    try:
        medical_keywords = [
            "頭", "頭部", "頭髮", "眼睛", "耳朵", "鼻子", "嘴巴", "牙齒", "脖子", "肩膀",
            "手", "手指", "手掌", "手臂", "指甲",
            "腳", "腳趾", "膝蓋", "大腿", "小腿", "腳底", "腳踝",
            "背", "腰", "胸部", "肚子", "腹部",
            "器官", "心臟", "肝臟", "肺", "胃", "腸", "腎臟", "膀胱",
            "子宮", "卵巢", "睪丸", "神經", "骨頭", "肌肉", "皮膚",
            "紅腫", "瘀青", "腫脹", "發炎", "痠痛", "疼痛", "癢", "流血", "破皮",
            "身體", "健康", "外傷", "生病", "不舒服", "不適"
        ]
        if any(word in user_message for word in medical_keywords):
            prompt = get_role_prompt("nurse")

        response = model.generate_content([{"role": "system", "parts": [prompt]}] + history)
        reply_text = response.text.strip()
    except Exception as e:
        print("文字訊息錯誤：", e)
        reply_text = "❌ 系統忙碌或出錯，請稍後再試一次。"

    history.append({"role": "model", "parts": [reply_text]})
    user_histories[uid] = history
    try:
        line_bot_api.push_message(uid, TextSendMessage(text=reply_text))
    except Exception as e:
        print("最終回覆推送失敗：", e)

@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
    uid = event.source.user_id
    user_message = event.message.text.strip()
    role = user_roles.get(uid, "assistant")
    prompt = get_role_prompt(role)
    history = user_histories.get(uid, [])[-8:]
    history.append({"role": "user", "parts": [user_message]})
    try:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🔄 正在處理中，請稍候..."))
    except Exception as e:
        print("預先提示錯誤：", e)
    threading.Thread(target=process_text_gemini, args=(uid, user_message, history, prompt)).start()

body_parts = [
    "頭", "頭部", "頭髮", "眼睛", "耳朵", "鼻子", "嘴巴", "牙齒", "脖子", "肩膀",
    "手", "手指", "手掌", "手臂", "指甲",
    "腳", "腳趾", "膝蓋", "大腿", "小腿", "腳底", "腳踝",
    "背", "腰", "胸部", "肚子", "腹部",
    "心臟", "肝臟", "肺", "胃", "腸", "腎臟", "膀胱",
    "子宮", "卵巢", "睪丸", "神經", "骨頭", "肌肉", "皮膚",
    "器官", "身體"
]

symptom_words = [
    "紅腫", "瘀青", "腫脹", "發炎", "痠痛", "疼痛", "癢", "流血", "破皮",
    "外傷", "生病", "不舒服", "不適", "受傷"
]

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
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🔍 分析圖片中，請稍候..."))
    except Exception as e:
        print("圖片處理提示錯誤：", e)

    try:
        preview = model.generate_content([
            {"role": "user", "parts": [
                {"text": "請用繁體中文說明這張圖片大致上是什麼類型的內容，約 10 字以內"},
                {"inline_data": {"mime_type": "image/jpeg", "data": image_bytes}}
            ]}
        ])
        preview_text = preview.text.strip()

        if any(p in preview_text for p in body_parts) and any(s in preview_text for s in symptom_words):
            system_prompt = get_role_prompt("nurse")
        else:
            system_prompt = get_role_prompt(user_roles.get(uid, "assistant"))

        full_response = model.generate_content([
            {"role": "system", "parts": [system_prompt]},
            {"role": "user", "parts": [
                {"text": "請幫我將這張圖片的內容完整翻譯為繁體中文，並補充 3 句建議或提醒。"},
                {"inline_data": {"mime_type": "image/jpeg", "data": image_bytes}}
            ]}
        ])
        reply_text = full_response.text.strip()
    except Exception as e:
        print("圖片分析錯誤：", e)
        reply_text = "❌ 圖片分析失敗或逾時，請稍後再試一次。"

    try:
        line_bot_api.push_message(uid, TextSendMessage(text=reply_text))
    except Exception as e:
        print("圖片最終推送失敗：", e)

@app.route("/test-gemini")
def test_gemini():
    def run_gemini():
        try:
            start = time.time()
            result = model.generate_content("請用繁體中文說一句話測試")
            duration = round(time.time() - start, 2)
            hostname = socket.gethostname()
            return f"✅ 測試成功（{duration} 秒），機器：{hostname}\n\n{result.text}"
        except Exception as e:
            hostname = socket.gethostname()
            return f"❌ 錯誤：{e}（host: {hostname}）"

    result_holder = {}
    def run():
        result_holder["response"] = run_gemini()

    thread = threading.Thread(target=run)
    thread.start()
    thread.join(timeout=10)

    if "response" not in result_holder:
        return f"❌ 錯誤：Gemini 回應逾時或未完成，請稍後再試。（host: {socket.gethostname()}）"

    return result_holder["response"]

@app.route("/test-models")
def test_models():
    try:
        models = genai.list_models()
        model_names = [m.name for m in models]
        return json.dumps(model_names, ensure_ascii=False)
    except Exception as e:
        return f"❌ 錯誤：{e}"

@app.route("/test-credentials")
def test_credentials():
    try:
        info = {
            "project_id": credentials.project_id,
            "client_email": credentials.service_account_email
        }
        return json.dumps(info, ensure_ascii=False)
    except Exception as e:
        return f"❌ 錯誤：{e}"

@app.route("/")
def home():
    return "Gemini LINE Bot 運行中"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))


