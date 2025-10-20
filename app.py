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
            return json.loads(f.read())
    except Exception:
        return {}

questions = load_file_lines("questions.txt")
challenges = load_file_lines("challenges.txt")
confessions = load_file_lines("confessions.txt")
personal_questions = load_file_lines("personality.txt")
games = load_json_file("games.txt")

try:
    with open("characters.txt", "r", encoding="utf-8") as f:
        personalities = f.read().split("\n\n")
except Exception:
    personalities = []

try:
    with open("game_weights.json", "r", encoding="utf-8") as f:
        game_weights = json.load(f)
except Exception:
    game_weights = {}

indexes = {"questions": 0, "challenges": 0, "confessions": 0, "personal": 0}

personality_scores = {p: 0 for p in ["الاجتماعي", "الرومانسي", "القائد", "المغامر",
                                    "المفكر", "المرح", "المبدع", "الهادئ", "المتحمس", "الحساس"]}

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

def calculate_personality(user_answers: typing.List[int], game_name: str) -> str:
    scores = {k: 0 for k in personality_scores.keys()}
    weights = game_weights.get(game_name, [])
    for i, answer in enumerate(user_answers):
        if i >= len(weights):
            continue
        ans_dict = weights[i].get(str(answer))
        if ans_dict:
            for key, val in ans_dict.items():
                scores[key] += val
    return max(scores, key=scores.get)

def get_next_item(category: str) -> str:
    global indexes
    items = {
        "questions": questions,
        "challenges": challenges,
        "confessions": confessions,
        "personal": personal_questions
    }.get(category, [])

    if not items:
        return "لا توجد عناصر متاحة."

    idx = indexes[category]
    item = items[idx]
    indexes[category] = (idx + 1) % len(items)
    return item

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    text = event.message.text.strip()
    user_id = event.source.user_id
    display_name = line_bot_api.get_profile(user_id).display_name

    # بدء اللعبة تلقائيًا إذا المستخدم جديد
    if user_id not in group_sessions:
        group_sessions[user_id] = {"game_started": True, "answers": []}
        available_games = list(games.keys())[:10]
        if available_games:
            first_game = available_games[0]
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"{display_name}: تم بدء اللعبة تلقائيًا -> {first_game}")
            )
            next_question = get_next_item("questions")
            line_bot_api.push_message(
                user_id,
                TextSendMessage(text=f"{display_name}: السؤال الأول -> {next_question}")
            )
        return

    # استقبال الإجابة وحساب التحليل بعد عدد معين من الأسئلة
    session = group_sessions.get(user_id)
    if session and "game_started" in session:
        try:
            answer = int(text)  # نفترض أن الإجابة رقمية
        except ValueError:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="أرسل رقم الإجابة فقط."))
            return

        session["answers"].append(answer)
        next_question = get_next_item("questions")
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"{display_name}: السؤال التالي -> {next_question}"))

        # بعد 5 أسئلة، حساب التحليل
        if len(session["answers"]) >= 5:
            first_game = list(games.keys())[0]
            personality_result = calculate_personality(session["answers"], first_game)
            line_bot_api.push_message(
                user_id,
                TextSendMessage(text=f"{display_name}: تم الانتهاء من اللعبة. تحليل شخصيتك -> {personality_result}")
            )
            del group_sessions[user_id]
        return

    # أوامر عادية
    if text == "مساعدة":
        reply = (
            "أوامر البوت:\n"
            "ابدأ - لبدء أي لعبة\n"
            "ايقاف - لإيقاف اللعبة الجارية\n"
            "سؤال - اختيار سؤال من الأسئلة العامة\n"
            "تحدي - اختيار تحدي\n"
            "اعتراف - اختيار اعتراف\n"
            "شخصي - اختيار سؤال شخصي\n"
            "لعبه - اختيار لعبة عشوائية من الألعاب العشر"
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        return

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
