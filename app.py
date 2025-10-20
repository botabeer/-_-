from flask import Flask, request
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import os, random, typing, json, re

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

games = load_json_file("games.txt")           # بيانات الألعاب
personality_descriptions = load_json_file("characters.txt")  # وصف الشخصيات
game_weights = load_json_file("game_weights.json")  # أوزان الشخصية لكل إجابة

# جلسات اللاعبين
sessions = {}
group_sessions: typing.Dict[str, typing.Dict] = {}

# تحويل الأرقام العربية إلى إنجليزية
arabic_to_english = {"١": "1", "٢": "2", "٣": "3", "٤": "4"}

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

def format_question(text: str) -> str:
    """
    يفصل السؤال عن الخيارات (1-4) ويجعلها مرئية بشكل مرتب
    """
    lines = text.splitlines()
    formatted = []
    question_line = lines[0] if lines else text
    formatted.append(f"{question_line}")
    options = re.findall(r"\b[1-4][\.\)\-]?\s*(.+)", text)
    for i, opt in enumerate(options, 1):
        formatted.append(f"{i}. {opt}")
    return "\n".join(formatted) if options else text

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    text = event.message.text.strip()
    user_id = event.source.user_id
    group_id = getattr(event.source, "group_id", None)
    try:
        display_name = line_bot_api.get_profile(user_id).display_name
    except:
        display_name = "عضو"

    # أوامر المساعدة
    if text == "مساعدة":
        reply = (
            "أوامر البوت:\n"
            "سؤال - اختيار سؤال من الأسئلة العامة\n"
            "تحدي - اختيار تحدي\n"
            "اعتراف - اختيار اعتراف\n"
            "شخصي - اختيار سؤال شخصي\n"
            "لعبه - بدء لعبة عشوائية\n"
            "لعبه1 إلى لعبه10 - اختيار لعبة محددة\n"
            "ابدأ - الانضمام للعبة الجماعية الحالية\n"
            "ايقاف - إيقاف اللعبة الجارية"
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        return

    # أوامر الأسئلة العشوائية
    if text == "سؤال":
        q = random.choice(questions_file)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"{display_name}\n\n{format_question(q)}"))
        return
    if text == "تحدي":
        q = random.choice(challenges_file)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"{display_name}\n\n{format_question(q)}"))
        return
    if text == "اعتراف":
        q = random.choice(confessions_file)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"{display_name}\n\n{format_question(q)}"))
        return
    if text == "شخصي":
        q = random.choice(personal_file)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"{display_name}\n\n{format_question(q)}"))
        return

    # بدء لعبة جماعية محددة
    if group_id and re.match(r"^لعبه\d+$", text):
        group_sessions[group_id] = {"game": text, "players": {}, "state": "joining"}
        line_bot_api.reply_message(event.reply_token, TextSendMessage(
            text=f"تم بدء الجلسة: {text}\n{display_name}، كل عضو يرسل 'ابدأ' للانضمام."
        ))
        return

    # الانضمام للعبة الجماعية
    if group_id and text == "ابدأ":
        gs = group_sessions.get(group_id)
        if not gs: 
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="لا توجد لعبة نشطة للانضمام إليها."))
            return
        players = gs["players"]
        if user_id not in players:
            players[user_id] = {"step": 0, "answers": []}
        step = players[user_id]["step"]
        game_key = gs["game"]
        game_questions = games.get(game_key, [])
        if not game_questions:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="لا توجد أسئلة متاحة لهذه اللعبة."))
            return
        question_text = f"{display_name}\n\nالسؤال {step+1}:\n{format_question(game_questions[step])}"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=question_text))
        return

    # الإجابة داخل اللعبة الجماعية
    if group_id and group_id in group_sessions:
        gs = group_sessions[group_id]
        if user_id in gs["players"]:
            ans_text = arabic_to_english.get(text, text)
            if ans_text not in ["1", "2", "3", "4"]:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="الرجاء اختيار رقم من 1 إلى 4"))
                return
            answer = int(ans_text)
            player = gs["players"][user_id]
            game_key = gs["game"]
            game_questions = games.get(game_key, [])
            player["answers"].append(answer)
            player["step"] += 1

            # السؤال التالي أو النهاية
            if player["step"] < len(game_questions):
                question_text = f"{display_name}\n\nالسؤال {player['step']+1}:\n{format_question(game_questions[player['step']])}"
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text=question_text))
            else:
                result = calculate_personality(player["answers"], game_key)
                description = personality_descriptions.get(result, "وصف الشخصية غير متوفر.")
                final_text = f"{display_name}\n\nتم الانتهاء من اللعبة.\nتحليل شخصيتك ({result}):\n{description}"
                line_bot_api.push_message(group_id, TextSendMessage(text=final_text))
                del gs["players"][user_id]
        return

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
