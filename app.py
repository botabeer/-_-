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

# ملفات الأسئلة
questions = load_file_lines("questions.txt")
challenges = load_file_lines("challenges.txt")
confessions = load_file_lines("confessions.txt")
personal_questions = load_file_lines("personality.txt")  # أسئلة شخصية

# شخصيات ووصفها
personality_descriptions = {}
try:
    with open("characters.txt", "r", encoding="utf-8") as f:
        parts = f.read().split("\n\n")
        for part in parts:
            if not part.strip():
                continue
            key, _, desc = part.partition("\n")
            personality_descriptions[key.strip()] = desc.strip()
except Exception:
    personality_descriptions = {}

# أوزان الإجابات لكل لعبة
game_weights = load_json_file("game_weights.json")

# الأسئلة من ملف الألعاب
games = load_json_file("games.txt")  # {"لعبه1": ["سؤال1","سؤال2",...]}

# جلسات اللاعبين
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
    return max(scores, key=scores.get)

def get_next_item(category: str) -> str:
    items = {
        "سؤال": questions,
        "تحدي": challenges,
        "اعتراف": confessions,
        "شخصي": personal_questions
    }.get(category, [])
    if not items:
        return "لا توجد عناصر متاحة."
    return random.choice(items)

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    text = event.message.text.strip()
    user_id = event.source.user_id
    try:
        display_name = line_bot_api.get_profile(user_id).display_name
    except Exception:
        display_name = "عضو"

    # دعم الأرقام بالعربي والانجليزي
    arabic_to_english = {"١": "1", "٢": "2", "٣": "3", "٤": "4"}
    if text in arabic_to_english:
        text = arabic_to_english[text]

    # أوامر الأسئلة
    if text in ["سؤال", "تحدي", "اعتراف", "شخصي"]:
        item = get_next_item(text)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"{display_name}: {item}"))
        return

    # عرض قائمة الألعاب عند كتابة "لعبه"
    if text == "لعبه":
        if not games:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"{display_name}: لا توجد ألعاب متاحة."))
            return
        game_list = "\n".join(games.keys())
        line_bot_api.reply_message(event.reply_token, TextSendMessage(
            text=f"{display_name}: اختر اللعبة بكتابة اسمها:\n{game_list}"
        ))
        return

    # بدء اللعبة بعد اختيار الاسم
    if text in games:
        sessions[user_id] = {
            "current_index": 0,
            "answers": [],
            "game_id": text,
            "questions": games[text]
        }
        first_question = sessions[user_id]["questions"][0]
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"{display_name}: {first_question}"))
        return

    # إنهاء اللعبة
    if text.lower() == "ايقاف" and user_id in sessions:
        del sessions[user_id]
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"{display_name}: تم إيقاف اللعبة."))
        return

    # الرد أثناء اللعبة
    if user_id in sessions:
        session = sessions[user_id]
        if text not in ["1", "2", "3", "4"]:
            return
        answer = int(text)
        session["answers"].append(answer)
        session["current_index"] += 1

        if session["current_index"] < len(session["questions"]):
            next_q = session["questions"][session["current_index"]]
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"{display_name}: {next_q}"))
        else:
            game_id = session["game_id"]
            result = calculate_personality(session["answers"], game_id)
            description = personality_descriptions.get(result, "وصف الشخصية غير متوفر.")
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(
                    text=f"{display_name}: تم الانتهاء من اللعبة.\n{display_name} -> تحليل شخصيتك: {result}\n{description}"
                )
            )
            del sessions[user_id]
        return

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
