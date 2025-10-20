from flask import Flask, request
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import os, random, typing, json

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
games_data = load_json_file("games.txt")
personality_descriptions = load_json_file("characters.txt")
game_weights = load_json_file("game_weights.json")

# جلسات اللاعبين الفردية والجماعية
sessions = {}
group_sessions = {}

# لتعقب الأسئلة العامة لتجنب التكرار حتى 100
general_indices = {"سؤال": 0, "تحدي": 0, "اعتراف": 0, "شخصي": 0}

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
    return max(scores, key=scores.get)

# تنسيق السؤال مع ترقيمه
def format_question(index: int, question_text: str) -> str:
    lines = question_text.split("\n")
    question_line = f"السؤال {index+1}:\n{lines[0]}"
    options = "\n".join(lines[1:]) if len(lines) > 1 else ""
    return f"{question_line}\n{options}"

# الحصول على أسئلة حسب النوع مع تجنب التكرار حتى 100
def get_next_general_question(qtype: str) -> str:
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
    group_id = getattr(event.source, "group_id", None)

    arabic_to_english = {"١": "1", "٢": "2", "٣": "3", "٤": "4"}
    text_conv = arabic_to_english.get(text, text)

    # أمر المساعدة
    if text == "مساعدة":
        reply = (
            "أوامر البوت:\n\n"
            "سؤال  → عرض سؤال من الأسئلة العامة\n"
            "تحدي  → عرض تحدي\n"
            "اعتراف → عرض اعتراف\n"
            "شخصي  → عرض سؤال شخصي\n"
            "لعبه  → عرض قائمة الألعاب المتاحة (لعبه1 → لعبه10)\n"
            "ابدأ  → الانضمام للعبة الحالية في القروب\n"
            "إيقاف → إنهاء اللعبة الحالية"
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        return

    # أسئلة عامة (سؤال/تحدي/اعتراف/شخصي)
    if text in ["سؤال","تحدي","اعتراف","شخصي"]:
        q_text = get_next_general_question(text)
        if not q_text:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"{display_name}: لا توجد أسئلة حالياً."))
            return
        sessions[user_id] = {"step": 0, "answers": [], "questions": [q_text]}
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"{display_name}\n\n{q_text}"))
        return

    # عرض قائمة الألعاب
    if text == "لعبه":
        reply = "اختر اللعبة بكتابة اسمها:\n" + "\n".join([f"لعبه{i}" for i in range(1,11)])
        reply += "\n\nابدأ - الانضمام للعبة الحالية\nإيقاف - إنهاء اللعبة الحالية"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        return

    # بدء لعبة جماعية
    if group_id and text.startswith("لعبه"):
        if text not in games_data.keys():
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="اكتب لعبه1 حتى لعبه10"))
            return
        group_sessions[group_id] = {"game": text, "players": {}, "state": "joining"}
        line_bot_api.reply_message(event.reply_token, TextSendMessage(
            text=f"تم بدء الجلسة: {text}\nكل عضو يرسل 'ابدأ' للانضمام."
        ))
        return

    # الانضمام للعبة جماعية
    if group_id and text == "ابدأ":
        gs = group_sessions.get(group_id)
        if not gs or not gs.get("game"): 
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="لا توجد لعبة حالية للانضمام."))
            return
        players = gs["players"]
        game_id = gs["game"]
        if user_id not in players:
            players[user_id] = {"step": 0, "answers": []}
        step = players[user_id]["step"]
        q_list = games_data[game_id]
        question_text = format_question(step, q_list[step])
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"{display_name}\n\n{question_text}"))
        return

    # الرد على أسئلة اللعبة الجماعية
    if group_id and group_id in group_sessions and user_id in group_sessions[group_id]["players"]:
        gs = group_sessions[group_id]
        player = gs["players"][user_id]

        if text_conv not in ["1","2","3","4"]:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="الرجاء اختيار رقم بين 1 و4"))
            return

        player["answers"].append(int(text_conv))
        game_id = gs["game"]
        q_list = games_data[game_id]

        # بعد آخر سؤال مباشرة
        if player["step"] == len(q_list)-1:
            trait = calculate_personality(player["answers"], game_id)
            desc = personality_descriptions.get(trait, "وصف الشخصية غير متوفر.")
            line_bot_api.reply_message(event.reply_token, TextSendMessage(
                text=f"{display_name}\n\nتم الانتهاء من اللعبة.\nتحليل شخصيتك ({trait}):\n{desc}"
            ))
            del gs["players"][user_id]
            return

        # إذا لم يكن آخر سؤال
        player["step"] += 1
        question_text = format_question(player["step"], q_list[player["step"]])
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"{display_name}\n\n{question_text}"))
        return

    # الرد على أسئلة الألعاب الفردية
    if user_id in sessions:
        session = sessions[user_id]
        if text_conv not in ["1","2","3","4"]:
            return
        session["answers"].append(int(text_conv))
        session["step"] += 1
        if session["step"] < len(session["questions"]):
            q_text = format_question(session["step"], session["questions"][session["step"]])
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"{display_name}\n\n{q_text}"))
        else:
            trait = calculate_personality(session["answers"], "default")
            desc = personality_descriptions.get(trait, "وصف الشخصية غير متوفر.")
            line_bot_api.reply_message(event.reply_token, TextSendMessage(
                text=f"{display_name}\n\nتم الانتهاء من اللعبة.\nتحليل شخصيتك ({trait}):\n{desc}"
            ))
            del sessions[user_id]
        return

    # إنهاء اللعبة
    if text == "إيقاف":
        if group_id and group_id in group_sessions:
            del group_sessions[group_id]
        if user_id in sessions:
            del sessions[user_id]
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="تم إنهاء اللعبة الحالية."))
        return

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
