from flask import Flask, request, abort
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

# تحميل الملفات
def load_file_lines(filename: str) -> typing.List[str]:
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    except Exception:
        return []

def load_games_from_txt(filename: str) -> dict:
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.loads(f.read())
    except Exception:
        return {}

questions_file = load_file_lines("questions.txt")
challenges_file = load_file_lines("challenges.txt")
confessions_file = load_file_lines("confessions.txt")
personal_file = load_file_lines("personality.txt")
games = load_games_from_txt("games.txt")

try:
    with open("characters.txt", "r", encoding="utf-8") as f:
        personalities = f.read().split("\n\n")
except Exception:
    personalities = []

# النقاط لكل شخصية
personality_scores = {
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

# أوزان جميع الألعاب
game_weights = {
    "لعبه1": [
        {"1":{"الاجتماعي":2,"المغامر":1},"2":{"المفكر":2},"3":{"الهادئ":2},"4":{"المبدع":2}},
        {"1":{"المغامر":2},"2":{"الهادئ":2},"3":{"المفكر":1},"4":{"الاجتماعي":2}},
        {"1":{"المبدع":2},"2":{"القائد":2},"3":{"الهادئ":2},"4":{"المفكر":1}},
        {"1":{"المفكر":2},"2":{"الهادئ":1},"3":{"المبدع":2},"4":{"المغامر":1}},
        {"1":{"الحساس":2},"2":{"المتحمس":2},"3":{"المبدع":1},"4":{"الهادئ":1}}
    ],
    "لعبه2": [
        {"1":{"المغامر":2},"2":{"الحساس":2},"3":{"المبدع":1},"4":{"الهادئ":1}},
        {"1":{"المغامر":2},"2":{"الهادئ":2},"3":{"الاجتماعي":2},"4":{"المفكر":1}},
        {"1":{"المغامر":2},"2":{"المبدع":2},"3":{"الحساس":1},"4":{"المفكر":1}},
        {"1":{"الاجتماعي":2},"2":{"الحساس":2},"3":{"المتحمس":1},"4":{"المبدع":1}},
        {"1":{"المغامر":2},"2":{"الهادئ":1},"3":{"المفكر":1},"4":{"المبدع":1}}
    ],
    "لعبه3": [
        {"1":{"المغامر":2},"2":{"المفكر":1},"3":{"الهادئ":2},"4":{"المبدع":1}},
        {"1":{"المغامر":2},"2":{"الاجتماعي":2},"3":{"القائد":1},"4":{"المتحمس":1}},
        {"1":{"المغامر":2},"2":{"الهادئ":2},"3":{"المبدع":1},"4":{"الحساس":1}},
        {"1":{"المفكر":2},"2":{"المتحمس":2},"3":{"الاجتماعي":1},"4":{"الهادئ":1}},
        {"1":{"المغامر":2},"2":{"الهادئ":1},"3":{"المبدع":2},"4":{"الحساس":1}}
    ],
    "لعبه4": [
        {"1":{"المغامر":2},"2":{"الهادئ":1},"3":{"المبدع":2},"4":{"المتحمس":1}},
        {"1":{"الاجتماعي":2},"2":{"المغامر":2},"3":{"المفكر":1},"4":{"الهادئ":1}},
        {"1":{"المفكر":2},"2":{"المبدع":2},"3":{"الهادئ":1},"4":{"الحساس":1}},
        {"1":{"الحساس":2},"2":{"المتحمس":2},"3":{"الاجتماعي":1},"4":{"الهادئ":1}},
        {"1":{"المغامر":2},"2":{"المبدع":2},"3":{"المفكر":1},"4":{"الهادئ":1}}
    ],
    "لعبه5": [
        {"1":{"المغامر":2},"2":{"الهادئ":1},"3":{"المتحمس":1},"4":{"المبدع":2}},
        {"1":{"المغامر":2},"2":{"الاجتماعي":1},"3":{"الهادئ":1},"4":{"المتحمس":2}},
        {"1":{"المفكر":2},"2":{"المبدع":2},"3":{"الحساس":1},"4":{"الهادئ":1}},
        {"1":{"الحساس":2},"2":{"المتحمس":2},"3":{"المبدع":1},"4":{"الهادئ":1}},
        {"1":{"المغامر":2},"2":{"المفكر":1},"3":{"المبدع":2},"4":{"الهادئ":1}}
    ],
    "لعبه6": [
        {"1":{"الهادئ":2},"2":{"المغامر":1},"3":{"المفكر":1},"4":{"المبدع":2}},
        {"1":{"الحساس":2},"2":{"المغامر":1},"3":{"المبدع":2},"4":{"الهادئ":1}},
        {"1":{"المفكر":2},"2":{"المغامر":1},"3":{"الهادئ":1},"4":{"المبدع":2}},
        {"1":{"المغامر":2},"2":{"الحساس":1},"3":{"المتحمس":2},"4":{"المبدع":1}},
        {"1":{"المغامر":2},"2":{"الهادئ":1},"3":{"المبدع":2},"4":{"المفكر":1}}
    ],
    "لعبه7": [
        {"1":{"الاجتماعي":2},"2":{"المغامر":1},"3":{"الهادئ":1},"4":{"المبدع":2}},
        {"1":{"المفكر":2},"2":{"المغامر":1},"3":{"الحساس":1},"4":{"الهادئ":2}},
        {"1":{"المغامر":2},"2":{"الهادئ":2},"3":{"المبدع":1},"4":{"الحساس":1}},
        {"1":{"المغامر":2},"2":{"المتحمس":1},"3":{"الهادئ":1},"4":{"المبدع":2}},
        {"1":{"المغامر":2},"2":{"المفكر":2},"3":{"الهادئ":1},"4":{"المبدع":1}}
    ],
    "لعبه8": [
        {"1":{"الاجتماعي":2},"2":{"المغامر":1},"3":{"المفكر":1},"4":{"الهادئ":2}},
        {"1":{"المتحمس":2},"2":{"المغامر":1},"3":{"المبدع":2},"4":{"الهادئ":1}},
        {"1":{"المفكر":2},"2":{"المغامر":1},"3":{"الهادئ":1},"4":{"المبدع":2}},
        {"1":{"الحساس":2},"2":{"المتحمس":2},"3":{"المغامر":1},"4":{"المبدع":1}},
        {"1":{"المغامر":2},"2":{"الهادئ":1},"3":{"المبدع":2},"4":{"المفكر":1}}
    ],
    "لعبه9": [
        {"1":{"المغامر":2},"2":{"الهادئ":1},"3":{"المتحمس":1},"4":{"المبدع":2}},
        {"1":{"المغامر":2},"2":{"الاجتماعي":1},"3":{"الهادئ":1},"4":{"المتحمس":2}},
        {"1":{"المفكر":2},"2":{"المبدع":2},"3":{"الحساس":1},"4":{"الهادئ":1}},
        {"1":{"الحساس":2},"2":{"المتحمس":2},"3":{"المبدع":1},"4":{"الهادئ":1}},
        {"1":{"المغامر":2},"2":{"المفكر":1},"3":{"المبدع":2},"4":{"الهادئ":1}}
    ],
    "لعبه10": [
        {"1":{"الرومانسي":2},"2":{"المغامر":1},"3":{"الهادئ":1},"4":{"الحساس":2}},
        {"1":{"المغامر":2},"2":{"الاجتماعي":1},"3":{"المبدع":2},"4":{"المتحمس":1}},
        {"1":{"المفكر":2},"2":{"المغامر":1},"3":{"الهادئ":1},"4":{"المبدع":2}},
        {"1":{"الحساس":2},"2":{"المتحمس":2},"3":{"المغامر":1},"4":{"المبدع":1}},
        {"1":{"المغامر":2},"2":{"المبدع":2},"3":{"الهادئ":1},"4":{"المفكر":1}}
    ]
}

group_sessions = {}

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK"

def calculate_personality(user_answers: typing.List[int], game_name: str) -> str:
    scores = {k:0 for k in personality_scores.keys()}
    weights = game_weights.get(game_name, [])
    for i, answer in enumerate(user_answers):
        if i >= len(weights):
            continue
        ans_dict = weights[i].get(str(answer))
        if ans_dict:
            for key, val in ans_dict.items():
                scores[key] += val
    return max(scores, key=scores.get)

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    global group_sessions
    text = event.message.text.strip()
    user_id = event.source.user_id
    display_name = line_bot_api.get_profile(user_id).display_name

    # أمر المساعدة
    if text == "مساعدة":
        line_bot_api.reply_message(event.reply_token, TextSendMessage(
            text=(
                "أوامر البوت:\n"
                "ابدأ - لبدء أي لعبة\n"
                "ايقاف - لإيقاف اللعبة الجارية\n"
                "سؤال - اختيار سؤال عشوائي\n"
                "تحدي - اختيار تحدي عشوائي\n"
                "اعتراف - اختيار اعتراف عشوائي\n"
                "شخصي - اختيار نصيحة شخصية عشوائية\n"
                "لعبه1 إلى لعبه10 - للعب الألعاب المختلفة"
            )
        ))
        return

    # بدء اللعبة
    if text.startswith("ابدأ"):
        game_name = text.split()[-1] if len(text.split()) > 1 else None
        if game_name and game_name in games:
            group_sessions[user_id] = {"game": game_name, "answers": [], "current_q":0}
            first_q = games[game_name][0]
            line_bot_api.reply_message(event.reply_token, TextSendMessage(
                text=f"@{display_name} اختر رقم الإجابة لكل سؤال:\n{first_q}"
            ))
        return

    # ايقاف اللعبة
    if text == "ايقاف" and user_id in group_sessions:
        del group_sessions[user_id]
        line_bot_api.reply_message(event.reply_token, TextSendMessage(
            text=f"@{display_name} تم إيقاف اللعبة."
        ))
        return

    # الألعاب مباشرة
    if text.startswith("لعبه") and text in games:
        group_sessions[user_id] = {"game": text, "answers": [], "current_q":0}
        first_q = games[text][0]
        line_bot_api.reply_message(event.reply_token, TextSendMessage(
            text=f"@{display_name} اختر رقم الإجابة لكل سؤال:\n{first_q}"
        ))
        return

    # التعامل مع اختيار الإجابة رقم
    if text.isdigit() and user_id in group_sessions:
        session = group_sessions[user_id]
        game_name = session["game"]
        current_q = session["current_q"]
        session["answers"].append(int(text))
        session["current_q"] += 1

        if session["current_q"] < len(games[game_name]):
            next_q = games[game_name][session["current_q"]]
            line_bot_api.reply_message(event.reply_token, TextSendMessage(
                text=f"@{display_name} السؤال التالي:\n{next_q}"
            ))
        else:
            top_personality = calculate_personality(session["answers"], game_name)
            description = next((p for p in personalities if p.startswith(top_personality)), "شخصية غير محددة")
            line_bot_api.reply_message(event.reply_token, TextSendMessage(
                text=f"@{display_name} لقد اكتملت اللعبة! شخصيتك هي: {top_personality}\n\n{description}"
            ))
            del group_sessions[user_id]

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
