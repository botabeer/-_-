from flask import Flask, request
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import os, typing, json

app = Flask(__name__)

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_CHANNEL_SECRET:
    raise RuntimeError("Set LINE_CHANNEL_ACCESS_TOKEN and LINE_CHANNEL_SECRET environment variables")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# تحميل الملفات
def load_file_lines(filename: str) -> typing.List[str]:
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    except Exception:
        return []

def load_json_file(filename: str) -> dict:
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

# ملفات خارجية
questions = load_file_lines("questions.txt")
challenges = load_file_lines("challenges.txt")
confessions = load_file_lines("confessions.txt")
personal_questions = load_file_lines("personality.txt")
game_weights = load_json_file("game_weights.json")
personality_descriptions = load_json_file("characters.txt")

# الأسئلة الخاصة باللعبة
game_questions = [
    "إذا حصلت على مفتاح سحري، ماذا تفعل أولًا؟\n1. أزور كل أصدقائي\n2. أستكشف أماكن غريبة\n3. أصنع اختراعات ممتعة\n4. أستريح وأفكر",
    "إذا اكتشفت بوابة زمنية، أين تذهب؟\n1. الماضي لرؤية التاريخ\n2. المستقبل لرؤية الاختراعات\n3. أرسل رسالة لنفسي\n4. أستمتع بالمغامرة دون التخطيط",
    "إذا تمكنت من التحدث مع شخصية من الماضي، ماذا تفعل أولًا؟\n1. أرفض استقباله\n2. أستمع إلى قصصه\n3. أستفيد من خبراته\n4. أحاول فهم أفكاره",
    "إذا كان بإمكانك التمتع بيوم بلا مسؤوليات، كيف تقضيه؟\n1. ألتقي بالأصدقاء\n2. أستكشف هواية جديدة\n3. أصنع مشروعًا ممتعًا\n4. أستريح وأقرأ",
    "إذا ربحت كنزًا سريًا، ماذا تفعل؟\n1. أشاركه مع أصدقائي\n2. أحتفظ به للمغامرة\n3. أستخدمه لابتكار شيء جديد\n4. أحلل أفضل طريقة للاستفادة منه",
    "إذا واجهت وحشًا غريبًا في الغابة، كيف تتصرف؟\n1. أتعامل معه بروح مرحة\n2. أبتكر خطة للتغلب عليه\n3. أهاجمه بحذر\n4. أراقب وأتعلم منه",
    "إذا كان بإمكانك التحليق في السماء، ماذا تختار؟\n1. الطيران مع أصدقائي\n2. الاستكشاف والتجوال\n3. رسم مسارات إبداعية\n4. الاستمتاع بالهدوء والسكينة",
    "إذا تلقيت رسالة سرية من مجهول، ماذا تفعل؟\n1. أشاركها مع الجميع\n2. أحاول حل اللغز\n3. أصنع مشروعًا مرتبطًا بها\n4. أحتفظ بها وأستمتع بالغموض",
    "إذا فاز صديقك في تحدي غريب، كيف تحتفل؟\n1. أرقص وأهتف معه\n2. أصفق بطريقة مبتكرة\n3. أخطط لمغامرة جديدة\n4. أشارك الفرح بهدوء",
    "إذا وجدت كتابًا سحريًا، ماذا تختار؟\n1. أقرأه مع أصدقائي\n2. أستكشف أسراره وأغامر\n3. أستخدمه لصنع أشياء مبتكرة\n4. أستمتع بالهدوء والتأم"
]

# اسم اللعبة لاستخدام الأوزان
game_id = "personal_game"

# جلسات المستخدمين
sessions = {}

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        print("Invalid signature – check your CHANNEL_SECRET")
    except Exception as e:
        print(f"Webhook exception: {e}")
    return "OK", 200

def calculate_personality(user_answers: typing.List[int], game_id: str) -> str:
    scores = {k: 0 for k in personality_descriptions.keys()}
    weights = game_weights.get(game_id, [])

    for i, ans in enumerate(user_answers):
        if i >= len(weights):
            continue
        weight = weights[i].get(str(ans), {})
        for key, val in weight.items():
            if key in scores:
                scores[key] += val

    if all(v == 0 for v in scores.values()):
        return list(scores.keys())[0]

    return max(scores, key=scores.get)

def format_question(index:int, question_text:str) -> str:
    lines = question_text.split("\n")
    question_line = f"السؤال {index+1}:\n{lines[0]}"
    options = "\n".join(lines[1:]) if len(lines)>1 else ""
    return f"{question_line}\n{options}"

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    text = event.message.text.strip()
    user_id = event.source.user_id
    display_name = line_bot_api.get_profile(user_id).display_name
    arabic_to_english = {"١":"1","٢":"2","٣":"3","٤":"4"}
    text_conv = arabic_to_english.get(text,text)

    # أمر المساعدة
    if text == "مساعدة":
        reply = (
            "أوامر البوت:\n\n"
            "سؤال  → عرض سؤال من الأسئلة العامة\n"
            "تحدي  → عرض تحدي\n"
            "اعتراف → عرض اعتراف\n"
            "شخصي  → عرض سؤال شخصي\n"
            "لعبه  → بدء لعبة شخصية مع أسئلة وتحليل مباشر"
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        return

    # الأسئلة العامة
    if text in ["سؤال","تحدي","اعتراف","شخصي"]:
        qlist = {"سؤال": questions, "تحدي": challenges, "اعتراف": confessions, "شخصي": personal_questions}
        index = general_indices[text] % len(qlist[text])
        general_indices[text] += 1
        q_text = qlist[text][index]
        sessions[user_id] = {"step":0,"answers":[],"questions":[q_text]}
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"{display_name}\n\n{q_text}"))
        return

    # بدء اللعبة الخاصة
    if text == "لعبه":
        sessions[user_id] = {"step":0,"answers":[],"questions":game_questions, "game": game_id}
        q_text = format_question(0, game_questions[0])
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"{display_name}\n\n{q_text}"))
        return

    # الرد على أسئلة اللعبة
    if user_id in sessions:
        session = sessions[user_id]
        if text_conv not in ["1","2","3","4"]:
            return
        session["answers"].append(int(text_conv))
        session["step"] += 1

        # إذا كانت هذه الإجابة الأخيرة
        if session["step"] >= len(session["questions"]):
            trait = calculate_personality(session["answers"], session.get("game","default"))
            desc = personality_descriptions.get(trait,"وصف الشخصية غير متوفر.")
            line_bot_api.reply_message(event.reply_token, TextSendMessage(
                text=f"{display_name}\n\nتم الانتهاء من اللعبة.\nتحليل شخصيتك ({trait}):\n{desc}"
            ))
            del sessions[user_id]
            return

        # إرسال السؤال التالي
        next_q = format_question(session["step"], session["questions"][session["step"]])
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"{display_name}\n\n{next_q}"))
        return

if __name__ == "__main__":
    port = int(os.getenv("PORT",5000))
    app.run(host="0.0.0.0", port=port)
