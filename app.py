import os
import json
import random
import typing
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

# تهيئة تطبيق Flask
app = Flask(__name__)

# مفاتيح LINE من المتغيرات البيئية
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")

if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_CHANNEL_SECRET:
    raise RuntimeError("❌ تأكد من تعيين المتغيرات البيئية LINE_CHANNEL_ACCESS_TOKEN و LINE_CHANNEL_SECRET")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# دوال تحميل الملفات
def load_file_lines(filename: str) -> typing.List[str]:
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    except Exception as e:
        print(f"⚠️ خطأ أثناء تحميل {filename}: {e}")
        return []

def load_json_file(filename: str) -> dict:
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️ خطأ أثناء تحميل JSON {filename}: {e}")
        return {}

# تحميل الملفات الخارجية
questions = load_file_lines("questions.txt")
challenges = load_file_lines("challenges.txt")
confessions = load_file_lines("confessions.txt")
personal_questions = load_file_lines("personality.txt")
games_data = load_json_file("games.txt")
game_weights = load_json_file("game_weights.json")
personality_descriptions = load_json_file("characters.txt")

# الجلسات
sessions = {}
general_indices = {"سؤال": 0, "تحدي": 0, "اعتراف": 0, "شخصي": 0}

# 🟩 نقطة اختبار للتأكد أن السيرفر يعمل (للتحقق من Render)
@app.route("/", methods=["GET"])
def home():
    return "✅ Bot is running on Render", 200

# 🟩 المسار الأساسي للـ Webhook
@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    print("📩 Received event from LINE")

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        print("❌ Invalid signature – تحقق من CHANNEL_SECRET")
        abort(400)
    except Exception as e:
        print(f"⚠️ Webhook exception: {e}")
        abort(500)
    return "OK", 200

# حساب الشخصية
def calculate_personality(user_answers: typing.List[int]) -> str:
    scores = game_weights.copy()
    for i, ans in enumerate(user_answers):
        try:
            weight = games_data["game"][i]["answers"].get(str(ans), {}).get("weight", {})
            for key, val in weight.items():
                if key in scores:
                    scores[key] += val
        except Exception:
            continue
    return max(scores, key=scores.get) if scores else "غير معروف"

# تنسيق السؤال
def format_question(index: int, question_data: dict) -> str:
    q_text = question_data.get("question", "")
    options = []
    for i in range(1, 5):
        opt_text = question_data.get("answers", {}).get(str(i), {}).get("text", "")
        options.append(f"{i}. {opt_text}")
    return f"السؤال {index+1}:\n{q_text}\n" + "\n".join(options)

# جلب سؤال عام
def get_next_general_question(qtype: str) -> str:
    qlist = {
        "سؤال": questions,
        "تحدي": challenges,
        "اعتراف": confessions,
        "شخصي": personal_questions
    }.get(qtype, [])
    if not qlist:
        return ""
    index = general_indices[qtype] % len(qlist)
    general_indices[qtype] += 1
    return qlist[index]

# معالج رسائل LINE
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    text = event.message.text.strip()
    user_id = event.source.user_id
    display_name = line_bot_api.get_profile(user_id).display_name

    arabic_to_english = {"١": "1", "٢": "2", "٣": "3", "٤": "4"}
    text_conv = arabic_to_english.get(text, text)

    # أوامر المساعدة
    if text == "مساعدة":
        reply = (
            "أوامر البوت:\n\n"
            "سؤال  → عرض سؤال عام\n"
            "تحدي  → عرض تحدي\n"
            "اعتراف → عرض اعتراف\n"
            "شخصي  → عرض سؤال شخصي\n"
            "لعبه  → بدء اللعبة الفردية (5 أسئلة فقط)\n"
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        return

    # الأوامر العامة
    if text in ["سؤال", "تحدي", "اعتراف", "شخصي"]:
        q_text = get_next_general_question(text)
        if not q_text:
            msg = f"{display_name}: لا توجد أسئلة حالياً."
        else:
            msg = f"{display_name}\n\n{q_text}"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=msg))
        return

    # بدء اللعبة
    if text == "لعبه":
        if not games_data.get("game"):
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🚫 لا توجد بيانات للعبة."))
            return
        shuffled_questions = games_data["game"][:]
        random.shuffle(shuffled_questions)
        # فقط أول 5 أسئلة
        shuffled_questions = shuffled_questions[:5]
        sessions[user_id] = {"step": 0, "answers": [], "questions": shuffled_questions, "active": True}
        question_text = format_question(0, shuffled_questions[0])
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"{display_name}\n\n{question_text}"))
        return

    # متابعة اللعبة
    if user_id in sessions and sessions[user_id].get("active"):
        session = sessions[user_id]
        if text_conv not in ["1", "2", "3", "4"]:
            return
        session["answers"].append(int(text_conv))
        session["step"] += 1

        # إذا جاوب على 5 أسئلة → تحليل وتوقف اللعبة
        if session["step"] >= 5:
            trait = calculate_personality(session["answers"])
            desc = personality_descriptions.get(trait, "وصف الشخصية غير متوفر.")
            result_text = f"{display_name}\n\nتحليل شخصيتك ({trait}):\n{desc}\n\nاكتب 'لعبه' لبدء جولة جديدة 🔁"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=result_text))
            sessions[user_id]["active"] = False  # إيقاف اللعبة
            return

        # إرسال السؤال التالي
        next_question = format_question(session["step"], session["questions"][session["step"]])
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"{display_name}\n\n{next_question}"))
        return

# 🔵 تشغيل السيرفر
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    print(f"🚀 Running on port {port}")
    app.run(host="0.0.0.0", port=port)
