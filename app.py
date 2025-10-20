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

# تحميل الملفات
questions = load_file_lines("questions.txt")
challenges = load_file_lines("challenges.txt")
confessions = load_file_lines("confessions.txt")
personal_questions = load_file_lines("personality.txt")
games = load_json_file("games.txt")  # تنسيق JSON: {"اسم اللعبة": ["سؤال1", "سؤال2", ...]}

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
    """
    تحسب نتيجة الشخصية بناءً على إجابات المستخدم وملف game_weights.json
    """
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
    """
    للحصول على العنصر التالي من أي قائمة
    """
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

    # أوامر المساعدة
    if text == "مساعدة":
        reply = (
            "أوامر البوت:\n"
            "لعبه - لبدء لعبة تفاعلية من قائمة الألعاب\n"
            "ايقاف - لإيقاف اللعبة الجارية\n"
            "سؤال - اختيار سؤال من الأسئلة العامة\n"
            "تحدي - اختيار تحدي\n"
            "اعتراف - اختيار اعتراف\n"
            "شخصي - اختيار سؤال شخصي"
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        return

    # بدء اللعبة عند أمر "لعبه"
    if text == "لعبه":
        available_games = list(games.keys())
        if not available_games:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="لا توجد ألعاب متاحة."))
            return

        # اختيار اللعبة عشوائيًا
        chosen_game = random.choice(available_games)
        group_sessions[user_id] = {
            "game_started": True,
            "game_name": chosen_game,
            "answers": [],
            "current_index": 0
        }

        # إرسال رسالة بدء اللعبة
        line_bot_api.reply_message(event.reply_token, TextSendMessage(
            text=f"{display_name}: تم بدء اللعبة -> {chosen_game}"
        ))

        # إرسال أول سؤال مع اسم المستخدم
        game_questions = games.get(chosen_game, [])
        if game_questions:
            first_question = game_questions[0]
            line_bot_api.push_message(
                user_id,
                TextSendMessage(text=f"{display_name}: {first_question}")
            )
        return

    # التعامل مع إجابات المستخدم داخل اللعبة
    session = group_sessions.get(user_id)
    if session and session.get("game_started"):
        chosen_game = session["game_name"]
        game_questions = games.get(chosen_game, [])

        # حفظ إجابة المستخدم
        session["answers"].append(text)
        session["current_index"] += 1

        # إذا بقيت أسئلة، إرسال السؤال التالي مع اسم المستخدم
        if session["current_index"] < len(game_questions):
            next_question = game_questions[session["current_index"]]
            line_bot_api.reply_message(event.reply_token, TextSendMessage(
                text=f"{display_name}: {next_question}"
            ))
            return

        # بعد انتهاء جميع الأسئلة، حساب التحليل الشخصي
        personality_name = calculate_personality(session["answers"], chosen_game)

        # البحث عن وصف الشخصية
        description = ""
        for block in personalities:
            lines = block.strip().split("\n")
            if lines and lines[0] == personality_name:
                description = "\n".join(lines[1:]).strip()
                break
        if not description:
            description = "وصف الشخصية غير متوفر."

        line_bot_api.reply_message(event.reply_token, TextSendMessage(
            text=f"{display_name}: تم الانتهاء من اللعبة.\nتحليل شخصيتك -> {personality_name}\n{description}"
        ))

        # إنهاء الجلسة
        del group_sessions[user_id]
        return

    # باقي الأوامر العادية
    if text == "سؤال":
        line_bot_api.reply_message(event.reply_token, TextSendMessage(
            text=f"{display_name}: {get_next_item('questions')}"
        ))
        return

    if text == "تحدي":
        line_bot_api.reply_message(event.reply_token, TextSendMessage(
            text=f"{display_name}: {get_next_item('challenges')}"
        ))
        return

    if text == "اعتراف":
        line_bot_api.reply_message(event.reply_token, TextSendMessage(
            text=f"{display_name}: {get_next_item('confessions')}"
        ))
        return

    if text == "شخصي":
        line_bot_api.reply_message(event.reply_token, TextSendMessage(
            text=f"{display_name}: {get_next_item('personal')}"
        ))
        return

    # أي نص آخر يتم تجاهله الآن

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
