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

questions_file = load_file_lines("questions.txt")
challenges_file = load_file_lines("challenges.txt")
confessions_file = load_file_lines("confessions.txt")
personal_file = load_file_lines("personality.txt")
games_file = load_file_lines("games.txt")  # كل الألعاب متوفرة هنا
personality_descriptions = load_json_file("characters.txt")
game_weights = load_json_file("game_weights.json")

# جلسات المستخدمين
sessions: typing.Dict[str, dict] = {}

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

def format_question(player_name: str, q_index: int, question_text: str) -> str:
    return f"{player_name}\n\nالسؤال {q_index+1}:\n{question_text}"

def format_analysis(player_name: str, trait: str) -> str:
    description = personality_descriptions.get(trait, "وصف الشخصية غير متوفر.")
    return f"{player_name}\n\nتحليل شخصيتك ({trait}):\n{description}"

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    text = event.message.text.strip()
    user_id = event.source.user_id
    display_name = line_bot_api.get_profile(user_id).display_name

    arabic_to_english = {"١": "1", "٢": "2", "٣": "3", "٤": "4"}
    answer_text = arabic_to_english.get(text, text)

    # أوامر عامة
    if text == "مساعدة":
        reply = (
            "أوامر البوت:\n"
            "سؤال - اختيار سؤال من الأسئلة العامة\n"
            "تحدي - اختيار تحدي\n"
            "اعتراف - اختيار اعتراف\n"
            "شخصي - اختيار سؤال شخصي\n"
            "لعبه - بدء لعبة من قائمة الألعاب\n"
            "ايقاف - لإيقاف اللعبة الجارية"
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        return

    if text == "ايقاف":
        if user_id in sessions:
            del sessions[user_id]
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"{display_name}: تم إيقاف اللعبة."))
        else:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="لا توجد لعبة جارية لإيقافها."))
        return

    if text == "سؤال":
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=format_question(display_name, 0, random.choice(questions_file))))
        return

    if text == "تحدي":
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=format_question(display_name, 0, random.choice(challenges_file))))
        return

    if text == "اعتراف":
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=format_question(display_name, 0, random.choice(confessions_file))))
        return

    if text == "شخصي":
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=format_question(display_name, 0, random.choice(personal_file))))
        return

    # بدء اللعبة
    if text.startswith("لعبه"):
        if text not in games_file:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="اختر اللعبة بكتابة اسمها:\n" + "\n".join(games_file)))
            return
        sessions[user_id] = {
            "current_index": 0,
            "answers": [],
            "game_id": text
        }
        first_question = load_file_lines(f"{text}.txt")
        if not first_question:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="لا توجد أسئلة متاحة لهذه اللعبة."))
            return
        sessions[user_id]["questions"] = first_question
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=format_question(display_name, 0, first_question[0])))
        return

    # إذا اللاعب في جلسة
    if user_id in sessions:
        session = sessions[user_id]
        if answer_text not in ["1", "2", "3", "4"]:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="الرجاء اختيار رقم من 1 إلى 4"))
            return
        answer = int(answer_text)
        session["answers"].append(answer)
        session["current_index"] += 1

        if session["current_index"] < len(session["questions"]):
            next_q = session["questions"][session["current_index"]]
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=format_question(display_name, session["current_index"], next_q)))
        else:
            # انتهاء اللعبة وحساب الشخصية
            result = calculate_personality(session["answers"], session["game_id"])
            analysis_text = format_analysis(display_name, result)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=analysis_text))
            del sessions[user_id]
        return

    # أي رسالة أخرى يتم تجاهلها
    return

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
