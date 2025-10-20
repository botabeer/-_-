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

games_data = load_json_file("games.txt")           # ألعاب 1-10
characters_data = load_json_file("characters.txt") # أوصاف الشخصيات
game_weights = load_json_file("game_weights.json") # أوزان الشخصيات لكل إجابة

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

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    text = event.message.text.strip()
    user_id = event.source.user_id
    display_name = line_bot_api.get_profile(user_id).display_name
    group_id = getattr(event.source, 'group_id', None)

    # عرض قائمة الألعاب
    if text == "لعبه":
        games_list = "\n".join([f"لعبه{i}" for i in range(1, 11)])
        reply_text = f"اختر اللعبة بكتابة اسمها:\n{games_list}\n\nابدأ - الانضمام للعبة الحالية\nإيقاف - إنهاء اللعبة الحالية"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
        return

    # اختيار لعبة محددة للقروب
    if group_id and text in games_data.keys():
        group_sessions[group_id] = {
            "game_id": text,
            "players": {}
        }
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
        step = players[user_id]["step"]
        question_list = games_data[game_id]
        if step < len(question_list):
            question = question_list[step]
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"{display_name}\n\n{question}"))
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
            return  # فقط 1-4 مقبولة
        player = players[user_id]
        player["answers"].append(int(text))
        player["step"] += 1
        game_id = gs["game_id"]
        q_list = games_data[game_id]

        if player["step"] < len(q_list):
            next_q = q_list[player["step"]]
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"{display_name}\n\n{next_q}"))
        else:
            result = calculate_personality(player["answers"], game_id)
            description = characters_data.get(result, "وصف الشخصية غير متوفر.")
            line_bot_api.reply_message(event.reply_token, TextSendMessage(
                text=f"{display_name}\n\nتم الانتهاء من اللعبة.\nتحليل شخصيتك ({result}):\n{description}"
            ))
            del players[user_id]
        return

    # التحقق من الجلسة الفردية (خارج القروب)
    if user_id in sessions:
        session = sessions[user_id]
        game_id = session["game_id"]
        q_list = games_data[game_id]
        if text not in ["1","2","3","4"]:
            return
        session["answers"].append(int(text))
        session["current_index"] += 1

        if session["current_index"] < len(q_list):
            next_q = q_list[session["current_index"]]
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"{display_name}\n\n{next_q}"))
        else:
            result = calculate_personality(session["answers"], game_id)
            description = characters_data.get(result, "وصف الشخصية غير متوفر.")
            line_bot_api.reply_message(event.reply_token, TextSendMessage(
                text=f"{display_name}\n\nتم الانتهاء من اللعبة.\nتحليل شخصيتك ({result}):\n{description}"
            ))
            del sessions[user_id]
        return

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
