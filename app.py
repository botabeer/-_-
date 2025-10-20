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

questions = load_file_lines("questions.txt")
challenges = load_file_lines("challenges.txt")
confessions = load_file_lines("confessions.txt")
personal_questions = load_file_lines("personality.txt")
games = load_json_file("games.json")  # ملف الألعاب مع الأوزان

try:
    with open("characters.txt", "r", encoding="utf-8") as f:
        personalities_text = f.read()
except Exception:
    personalities_text = ""

# استخراج وصف الشخصية من الملف
personality_descriptions = {}
for part in personalities_text.split("\n\n"):
    if not part.strip():
        continue
    key, _, desc = part.partition("\n")
    personality_descriptions[key.strip()] = desc.strip()

indexes = {"questions": 0, "challenges": 0, "confessions": 0, "personal": 0}

# جلسات المستخدمين أثناء اللعب
sessions = {}

# -----------------------------
# هيكل لتخزين أسماء اللاعبين لكل مجموعة
# group_players[group_id] = { user_id: "اسم اللاعب" }
# -----------------------------
group_players = {}

def register_player_name(group_id: str, user_id: str) -> str:
    """
    يسجل اسم اللاعب في القروب باستخدام LINE API عند أول تفاعل.
    يعيد الاسم المسجل أو 'عضو' كافتراضي.
    """
    if group_id not in group_players:
        group_players[group_id] = {}
    if user_id in group_players[group_id]:
        return group_players[group_id][user_id]

    try:
        profile = line_bot_api.get_profile(user_id)
        name = profile.display_name
    except:
        name = "عضو"
    group_players[group_id][user_id] = name
    return name

def get_player_name(group_id: str, user_id: str) -> str:
    """
    يعيد اسم اللاعب المسجل في القروب أو 'عضو' إذا لم يكن مسجلاً.
    """
    return group_players.get(group_id, {}).get(user_id, "عضو")

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
    scores = {k: 0 for k in personality_descriptions.keys()}
    weights = games.get(game_name, [])
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
    group_id = event.source.group_id if hasattr(event.source, "group_id") else user_id
    display_name = register_player_name(group_id, user_id)

    arabic_to_english = {"١": "1", "٢": "2", "٣": "3", "٤": "4"}

    # إذا المستخدم في جلسة لعبة
    if user_id in sessions:
        text_conv = arabic_to_english.get(text, text)
        if text_conv not in ["1", "2", "3", "4"]:
            # تجاهل أي رد غير صحيح
            return

        answer = int(text_conv)
        session = sessions[user_id]
        session["answers"].append(answer)
        session["current_index"] += 1

        if session["current_index"] < len(session["questions"]):
            # السؤال التالي
            next_q = session["questions"][session["current_index"]]
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"{display_name}: {next_q}"))
        else:
            # انتهاء اللعبة وحساب الشخصية
            game_id = session["game_id"]
            result = calculate_personality(session["answers"], game_id)
            description = personality_descriptions.get(result, "وصف الشخصية غير متوفر.")
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"{display_name}: تم الانتهاء من اللعبة.\nتحليل شخصيتك -> {result}\n{description}")
            )
            del sessions[user_id]
        return

    # أوامر عامة
    if text == "مساعدة":
        reply = (
            "أوامر البوت:\n"
            "ابدأ - لبدء أي لعبة\n"
            "ايقاف - لإيقاف اللعبة الجارية\n"
            "سؤال - اختيار سؤال من الأسئلة العامة\n"
            "تحدي - اختيار تحدي\n"
            "اعتراف - اختيار اعتراف\n"
            "شخصي - اختيار سؤال شخصي\n"
            "لعبه - بدء لعبة عشوائية من الألعاب العشر"
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        return

    if text == "سؤال":
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"{display_name}: {get_next_item('questions')}"))
        return

    if text == "تحدي":
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"{display_name}: {get_next_item('challenges')}"))
        return

    if text == "اعتراف":
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"{display_name}: {get_next_item('confessions')}"))
        return

    if text == "شخصي":
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"{display_name}: {get_next_item('personal')}"))
        return

    if text == "لعبه":
        available_games = list(games.keys())[:10]
        if not available_games:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="لا توجد ألعاب متاحة."))
            return
        chosen_game = random.choice(available_games)
        game_questions = [f"السؤال {i+1}" for i in range(len(games[chosen_game]))]
        sessions[user_id] = {"game_id": chosen_game, "questions": game_questions, "current_index": 0, "answers": []}
        # إرسال أول سؤال
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"{display_name}: {game_questions[0]}"))
        return

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
