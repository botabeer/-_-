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

# ===================== أسئلة اللعبة المدمجة =====================
games_data = {
    "game": [
        {
            "question": "إذا تلقيت دعوة لحضور ورشة فنية، ماذا تفعل؟",
            "answers": {
                "1": {"text": "أشارك مع الآخرين وأتفاعل معهم", "weight": {"الاجتماعي": 2}},
                "2": {"text": "أدرس تقنيات الورشة قبل التطبيق", "weight": {"المفكر": 2}},
                "3": {"text": "أبتكر أسلوبًا فنيًا جديدًا", "weight": {"المبدع": 2}},
                "4": {"text": "أراقب الورشة وأتعلم بهدوء", "weight": {"الهادئ": 2}}
            }
        },
        {
            "question": "وجدت صديقًا قديمًا يحتاج لمساعدة، كيف تتصرف؟",
            "answers": {
                "1": {"text": "أقف بجانبه وأدعمه فورًا", "weight": {"الاجتماعي": 2}},
                "2": {"text": "أفكر في أفضل حل لمساعدته", "weight": {"المفكر": 2}},
                "3": {"text": "أستخدم فكرة مبتكرة لتقديم المساعدة", "weight": {"المبدع": 2}},
                "4": {"text": "أراقب الوضع وأتصرف بهدوء", "weight": {"الهادئ": 2}}
            }
        },
        {
            "question": "إذا حصلت على فرصة لكتابة كتاب، ماذا تختار؟",
            "answers": {
                "1": {"text": "أكتب قصة جماعية مع أصدقائي", "weight": {"الاجتماعي": 2}},
                "2": {"text": "أبحث عن أفكار دقيقة ومعلومات موثوقة", "weight": {"المفكر": 2}},
                "3": {"text": "أبتكر أسلوب سرد مختلف ومبدع", "weight": {"المبدع": 2}},
                "4": {"text": "أكتب بهدوء في أوقات معينة", "weight": {"الهادئ": 2}}
            }
        },
        {
            "question": "إذا حصلت على هدية مفاجئة، كيف تتصرف؟",
            "answers": {
                "1": {"text": "أشارك الفرحة مع الآخرين", "weight": {"الاجتماعي": 2}},
                "2": {"text": "أفكر في معناها وكيف يمكن الاستفادة منها", "weight": {"المفكر": 2}},
                "3": {"text": "أستعملها بطريقة مبتكرة", "weight": {"المبدع": 2}},
                "4": {"text": "أحتفظ بها وأستمتع بها بهدوء", "weight": {"الهادئ": 2}}
            }
        },
        {
            "question": "إذا حصلت على فرصة السفر، ماذا تختار؟",
            "answers": {
                "1": {"text": "أسافر مع أصدقائي ونشارك المغامرة", "weight": {"الاجتماعي": 2}},
                "2": {"text": "أخطط الرحلة بدقة قبل السفر", "weight": {"المفكر": 2}},
                "3": {"text": "أختر أماكن غير تقليدية لتجربة جديدة", "weight": {"المبدع": 2}},
                "4": {"text": "أستمتع بالرحلة بمفردي وبهدوء", "weight": {"الهادئ": 2}}
            }
        },
        # ... أضف باقي الأسئلة حتى تصل 100 بنفس الطريقة ...
    ]
}

game_weights = {
    "الاجتماعي": 0,
    "الرومانسي": 0,
    "القائد": 0,
    "المغامر": 0,
    "المفكر": 0,
    "المرح": 0,
    "المبدع": 0,
    "الهادئ": 0,
    "المتحمس": 0,
    "الحساس": 0
}

# ===================== باقي الكود كما هو =====================
# دوال التحميل
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

# الملفات العامة
questions = load_file_lines("questions.txt")
challenges = load_file_lines("challenges.txt")
confessions = load_file_lines("confessions.txt")
personal_questions = load_file_lines("personality.txt")
personality_descriptions = load_json_file("characters.txt")  

# جلسات اللاعبين
sessions = {}
general_indices = {"سؤال":0, "تحدي":0, "اعتراف":0, "شخصي":0}

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

def calculate_personality(user_answers: typing.List[int]) -> str:
    scores = game_weights.copy()
    for i, ans in enumerate(user_answers):
        weight = games_data["game"][i % len(games_data["game"])]["answers"].get(str(ans), {}).get("weight", {})
        for key, val in weight.items():
            if key in scores:
                scores[key] += val
    return max(scores, key=scores.get)

def format_question(index:int, question_data: dict) -> str:
    q_text = question_data["question"]
    options = []
    for i in range(1,5):
        opt_text = question_data["answers"][str(i)]["text"]
        options.append(f"{i}. {opt_text}")
    options_text = "\n".join(options)
    return f"السؤال {index+1}:\n{q_text}\n{options_text}"

def get_next_general_question(qtype:str) -> str:
    qlist = {"سؤال": questions, "تحدي": challenges, "اعتراف": confessions, "شخصي": personal_questions}.get(qtype, [])
    if not qlist:
        return ""
    index = general_indices[qtype] % len(qlist)
    general_indices[qtype] += 1
    return qlist[index]

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    text = event.message.text.strip()
    user_id = event.source.user_id
    display_name = line_bot_api.get_profile(user_id).display_name

    arabic_to_english = {"١":"1","٢":"2","٣":"3","٤":"4"}
    text_conv = arabic_to_english.get(text,text)

    if text == "مساعدة":
        reply = (
            "أوامر البوت:\n\n"
            "سؤال  → عرض سؤال من الأسئلة العامة\n"
            "تحدي  → عرض تحدي\n"
            "اعتراف → عرض اعتراف\n"
            "شخصي  → عرض سؤال شخصي\n"
            "لعبه  → بدء اللعبة الفردية الجديدة\n"
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        return

    if text in ["سؤال","تحدي","اعتراف","شخصي"]:
        q_text = get_next_general_question(text)
        if not q_text:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"{display_name}: لا توجد أسئلة حالياً."))
            return
        sessions[user_id] = {"step":0,"answers":[],"questions":[q_text]}
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"{display_name}\n\n{q_text}"))
        return

    if text == "لعبه":
        sessions[user_id] = {
            "step": 0,
            "answers": [],
            "questions": games_data["game"]
        }
        question_text = format_question(0, sessions[user_id]["questions"][0])
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"{display_name}\n\n{question_text}"))
        return

    if user_id in sessions and "questions" in sessions[user_id]:
        session = sessions[user_id]
        if text_conv not in ["1","2","3","4"]:
            return
        session["answers"].append(int(text_conv))
        step = session["step"]

        # بعد كل 5 أسئلة إعطاء التحليل الحالي
        if (step + 1) % 5 == 0:
            trait = calculate_personality(session["answers"])
            desc = personality_descriptions.get(trait,"وصف الشخصية غير متوفر.")
            line_bot_api.reply_message(event.reply_token, TextSendMessage(
                text=f"{display_name}\nتحليل مؤقت للشخصية ({trait}):\n{desc}"
            ))

        # إرسال السؤال التالي (دوراني)
        session["step"] = (step + 1) % len(session["questions"])
        next_question = format_question(session["step"], session["questions"][session["step"]])
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"{display_name}\n\n{next_question}"))
        return

if __name__ == "__main__":
    port = int(os.getenv("PORT",5000))
    app.run(host="0.0.0.0", port=port)
