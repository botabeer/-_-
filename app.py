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

# الملفات
questions = load_file_lines("questions.txt")
challenges = load_file_lines("challenges.txt")
confessions = load_file_lines("confessions.txt")
personal_questions = load_file_lines("personality.txt")
games_data = load_json_file("games.txt")          # أسئلة اللعبة
game_weights = load_json_file("game_weights.json")  
personality_descriptions = load_json_file("characters.txt")  

# جلسات اللاعبين
sessions = {}

# تتبع الأسئلة العامة
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

# حساب الشخصية
def calculate_personality(user_answers: typing.List[int]) -> str:
    scores = game_weights.copy()  # يحتوي على جميع الشخصيات بصفر
    for i, ans in enumerate(user_answers):
        weight = games_data["game"][i]["answers"].get(str(ans), {}).get("weight", {})
        for key, val in weight.items():
            if key in scores:
                scores[key] += val
    return max(scores, key=scores.get)

# تنسيق السؤال
def format_question(index:int, question_data: dict) -> str:
    q_text = question_data["question"]
    options = []
    for i in range(1,5):
        opt_text = question_data["answers"][str(i)]["text"]
        options.append(f"{i}. {opt_text}")
    options_text = "\n".join(options)
    return f"السؤال {index+1}:\n{q_text}\n{options_text}"

# الحصول على الأسئلة العامة بدون تكرار
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

    # أمر المساعدة
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

    # الأسئلة العامة
    if text in ["سؤال","تحدي","اعتراف","شخصي"]:
        q_text = get_next_general_question(text)
        if not q_text:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"{display_name}: لا توجد أسئلة حالياً."))
            return
        sessions[user_id] = {"step":0,"answers":[],"questions":[q_text]}
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"{display_name}\n\n{q_text}"))
        return

    # بدء لعبة
    if text == "لعبه":
        questions_list = games_data["game"].copy()
        while len(questions_list) < 10:
            questions_list.extend(games_data["game"])
        questions_list = questions_list[:10]

        sessions[user_id] = {
            "step": 0,
            "answers": [],
            "questions": questions_list
        }
        question_text = format_question(0, sessions[user_id]["questions"][0])
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"{display_name}\n\n{question_text}"))
        return

    # الرد على أسئلة اللعبة
    if user_id in sessions and "questions" in sessions[user_id]:
        session = sessions[user_id]
        if text_conv not in ["1","2","3","4"]:
            return
        session["answers"].append(int(text_conv))
        step = session["step"]

        # إذا وصلنا لآخر سؤال
        if step+1 >= len(session["questions"]):
            trait = calculate_personality(session["answers"])
            desc = personality_descriptions.get(trait,"وصف الشخصية غير متوفر.")
            line_bot_api.reply_message(event.reply_token, TextSendMessage(
                text=f"{display_name}\n\nتم الانتهاء من اللعبة.\nتحليل شخصيتك ({trait}):\n{desc}"
            ))
            del sessions[user_id]
            return

        # إرسال السؤال التالي
        session["step"] += 1
        next_question = format_question(session["step"], session["questions"][session["step"]])
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"{display_name}\n\n{next_question}"))
        return

if __name__ == "__main__":
    port = int(os.getenv("PORT",5000))
    app.run(host="0.0.0.0", port=port)
