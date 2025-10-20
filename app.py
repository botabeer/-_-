from flask import Flask, request
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import os, typing, json, random

app = Flask(__name__)

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_CHANNEL_SECRET:
    raise RuntimeError("Set LINE_CHANNEL_ACCESS_TOKEN and LINE_CHANNEL_SECRET environment variables")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# تحميل الملفات
def load_json_file(filename: str) -> dict:
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

games_data = load_json_file("games.txt")           
questions_list = load_json_file("questions.txt")   
challenges_list = load_json_file("challenges.txt") 
confessions_list = load_json_file("confessions.txt") 
personality_list = load_json_file("personality.txt") 
characters_data = load_json_file("characters.txt") 
game_weights = load_json_file("game_weights.json") 

# جلسات اللاعبين الفردية
sessions = {}
# جلسات الألعاب الجماعية للقروب
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

# حساب الشخصية لكل لاعب
def calculate_personality(user_answers: typing.List[int], game_id: str) -> str:
    scores = {k: 0 for k in characters_data.keys()}
    weights = game_weights.get(game_id, [])
    for i, ans in enumerate(user_answers):
        if i >= len(weights):
            continue
        weight = weights[i].get(str(ans), {})
        for key, val in weight.items():
            if key in scores:
                scores[key] += val
    return max(scores, key=scores.get)

# الحصول على قائمة الأسئلة حسب نوع اللعبة
def get_questions_by_type(qtype: str) -> list:
    if qtype == "سؤال":
        return questions_list
    elif qtype == "تحدي":
        return challenges_list
    elif qtype == "اعتراف":
        return confessions_list
    elif qtype == "شخصي":
        return personality_list
    return []

# توليد نص السؤال مرقم
def format_question(index: int, question_text: str) -> str:
    lines = question_text.split("\n")
    question_line = f"السؤال {index+1}:\n{lines[0]}"
    options = "\n".join(lines[1:]) if len(lines) > 1 else ""
    return f"{question_line}\n{options}"

# تحويل الأرقام العربية ١–٤ إلى 1–4
def normalize_answer(ans: str) -> str:
    arabic_to_eng = {"١":"1","٢":"2","٣":"3","٤":"4"}
    return arabic_to_eng.get(ans, ans)

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    text = event.message.text.strip()
    text = normalize_answer(text)
    user_id = event.source.user_id
    display_name = line_bot_api.get_profile(user_id).display_name
    group_id = getattr(event.source, 'group_id', None)

    # عرض قائمة الألعاب
    if text == "لعبه":
        games_list = "\n".join([f"لعبه{i}" for i in range(1, 11)])
        reply_text = f"اختر اللعبة بكتابة اسمها:\n{games_list}\n\nابدأ - الانضمام للعبة الحالية\nإيقاف - إنهاء اللعبة الحالية\nأوامر: سؤال، تحدي، اعتراف، شخصي"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
        return

    # اختيار لعبة محددة للقروب
    if group_id and text in games_data.keys():
        group_sessions[group_id] = {"game_id": text, "players": {}}
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"تم اختيار {text} للعب الجماعي. كل شخص يكتب 'ابدأ' للانضمام."))
        return

    # الانضمام للعبة جماعية
    if text == "ابدأ" and group_id:
        gs = group_sessions.get(group_id)
        if not gs or not gs.get("game_id"):
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="لا توجد لعبة حالية للانضمام."))
            return
        game_id = gs["game_id"]
        players = gs["players"]
        if user_id not in players:
            players[user_id] = {"step": 0, "answers": []}
        player = players[user_id]
        q_list = games_data[game_id]
        if player["step"] < len(q_list):
            question_text = format_question(player["step"], q_list[player["step"]])
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"{display_name}\n\n{question_text}"))
        return

    # إنهاء اللعبة
    if text == "إيقاف":
        if group_id in group_sessions:
            del group_sessions[group_id]
        if user_id in sessions:
            del sessions[user_id]
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="تم إنهاء اللعبة الحالية."))
        return

    # الرد على الأسئلة في لعبة جماعية
    if group_id and group_id in group_sessions:
        gs = group_sessions[group_id]
        players = gs["players"]
        if user_id not in players:
            return
        if text not in ["1","2","3","4"]:
            return
        player = players[user_id]
        player["answers"].append(int(text))
        player["step"] += 1
        game_id = gs["game_id"]
        q_list = games_data[game_id]

        if player["step"] < len(q_list):
            question_text = format_question(player["step"], q_list[player["step"]])
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"{display_name}\n\n{question_text}"))
        else:
            result = calculate_personality(player["answers"], game_id)
            description = characters_data.get(result, "وصف الشخصية غير متوفر.")
            line_bot_api.reply_message(event.reply_token, TextSendMessage(
                text=f"{display_name}\n\nتم الانتهاء من اللعبة.\nتحليل شخصيتك ({result}):\n{description}"
            ))
            del players[user_id]
        return

    # أوامر اللعبة الفردية: سؤال، تحدي، اعتراف، شخصي
    if text in ["سؤال","تحدي","اعتراف","شخصي"]:
        questions = get_questions_by_type(text)
        if not questions:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"{display_name}: لا توجد أسئلة من نوع {text} حالياً."))
            return
        sessions[user_id] = {"step": 0, "answers": [], "questions": questions}
        question_text = format_question(0, questions[0])
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"{display_name}\n\n{question_text}"))
        return

    # الرد على الأسئلة الفردية
    if user_id in sessions:
        session = sessions[user_id]
        if text not in ["1","2","3","4"]:
            return
        session["answers"].append(int(text))
        session["step"] += 1
        if session["step"] < len(session["questions"]):
            question_text = format_question(session["step"], session["questions"][session["step"]])
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"{display_name}\n\n{question_text}"))
        else:
            # حساب وتحليل الشخصية بعد آخر سؤال
            result = calculate_personality(session["answers"], "default")
            description = characters_data.get(result, "وصف الشخصية غير متوفر.")
            line_bot_api.reply_message(event.reply_token, TextSendMessage(
                text=f"{display_name}\n\nتم الانتهاء من اللعبة.\nتحليل شخصيتك ({result}):\n{description}"
            ))
            del sessions[user_id]
        return

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
