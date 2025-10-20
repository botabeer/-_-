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
games_data = load_file_lines("games.txt")  # يمكن تعديلها لتكون json لو حبيت
personality_descriptions = load_json_file("characters.txt")  # وصف الشخصيات
game_weights = load_json_file("game_weights.json")  # أوزان كل إجابة

# جلسات اللاعبين
sessions = {}
group_sessions = {}

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
    return max(scores, key=scores.get)

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    text = event.message.text.strip()
    user_id = event.source.user_id
    display_name = line_bot_api.get_profile(user_id).display_name

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

    # أسئلة عامة
    if text == "سؤال":
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"{display_name}\n{random.choice(questions)}"))
        return
    if text == "تحدي":
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"{display_name}\n{random.choice(challenges)}"))
        return
    if text == "اعتراف":
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"{display_name}\n{random.choice(confessions)}"))
        return
    if text == "شخصي":
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"{display_name}\n{random.choice(personal_questions)}"))
        return

    # عرض قائمة الألعاب
    if text == "لعبه":
        reply = "اختر اللعبة بكتابة اسمها:\n" + "\n".join([f"لعبه{i}" for i in range(1,11)])
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        return

    # بدء لعبة في القروب
    group_id = getattr(event.source, "group_id", None)
    if group_id and text.startswith("لعبه"):
        if text not in [f"لعبه{i}" for i in range(1,11)]:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="اكتب لعبه1 حتى لعبه10"))
            return
        group_sessions[group_id] = {"game": text, "players": {}, "state": "joining"}
        line_bot_api.reply_message(event.reply_token, TextSendMessage(
            text=f"تم بدء الجلسة: {text}\n{display_name} كل عضو يرسل 'ابدأ' للانضمام."
        ))
        return

    # الانضمام للعبة بالقروب
    if group_id and text == "ابدأ":
        gs = group_sessions.get(group_id)
        if not gs: return
        players = gs["players"]
        if user_id not in players:
            players[user_id] = {"step": 0, "answers": []}
        step = players[user_id]["step"]
        question_list = games_data  # استبدال بـأسئلة اللعبة الفعلية
        q = question_list[step]
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"{display_name}\n{q}"))
        return

    # الردود على أسئلة اللعبة
    if (group_id and group_id in group_sessions and user_id in group_sessions[group_id]["players"]):
        gs = group_sessions[group_id]
        player = gs["players"][user_id]

        if text_conv not in ["1","2","3","4"]:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="الرجاء اختيار رقم بين 1 و4"))
            return
        ans_num = int(text_conv)

        player["answers"].append(ans_num)
        player["step"] += 1

        # السؤال التالي أو إنهاء اللعبة
        question_list = games_data  # استبدال بـأسئلة اللعبة الفعلية
        if player["step"] < len(question_list):
            next_q = question_list[player["step"]]
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"{display_name}\n{next_q}"))
        else:
            # حساب الشخصية بعد آخر سؤال
            trait = calculate_personality(player["answers"], gs["game"])
            desc = personality_descriptions.get(trait, "وصف الشخصية غير متوفر.")
            final_text = f"{display_name}\nتم الانتهاء من اللعبة.\nتحليل شخصيتك ({trait}):\n{desc}"
            line_bot_api.push_message(group_id, TextSendMessage(text=final_text))
            del gs["players"][user_id]
        return

    # إنهاء اللعبة
    if text == "إيقاف":
        if group_id and group_id in group_sessions:
            del group_sessions[group_id]
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="تم إنهاء اللعبة الحالية."))
        return

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
