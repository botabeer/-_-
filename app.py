fromfrom flask import Flask, request
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import os, random, typing, json

app = Flask(__name__)

# إعداد التوكن والسر
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_CHANNEL_SECRET:
    raise RuntimeError("Set LINE_CHANNEL_ACCESS_TOKEN and LINE_CHANNEL_SECRET environment variables")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# ======== تحميل الملفات ========
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

# ======== إعداد أوزان الألعاب ========
try:
    with open("game_weights.json", "r", encoding="utf-8") as f:
        game_weights = json.load(f)
except Exception:
    game_weights = {}

# ======== تتبع المواقع لكل مجموعة ========
indexes = {
    "questions": 0,
    "challenges": 0,
    "confessions": 0,
    "personal": 0
}

# ======== نقاط الشخصيات ========
personality_scores = {p:0 for p in ["الاجتماعي","الرومانسي","القائد","المغامر",
                                    "المفكر","المرح","المبدع","الهادئ","المتحمس","الحساس"]}

# ======== جلسات المجموعات ========
group_sessions = {}

# ======== المساعد ========
@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)

    if not signature:
        return "Missing X-Line-Signature", 400

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        print("⚠️ Invalid signature. Check your CHANNEL_SECRET and make sure this request is from LINE.")
        return "Invalid signature", 400
    except Exception as e:
        print(f"⚠️ Exception handling webhook: {e}")
        return str(e), 500

    return "OK", 200

# ======== تحليل الشخصية ========
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

# ======== اختيار العنصر التالي مع تكرار دائري ========
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

# ======== التعامل مع الرسائل ========
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    text = event.message.text.strip()
    user_id = event.source.user_id
    display_name = line_bot_api.get_profile(user_id).display_name

    # المساعدة
    if text == "مساعدة":
        line_bot_api.reply_message(event.reply_token, TextSendMessage(
            text=(
                "أوامر البوت:\n"
                "ابدأ - لبدء أي لعبة\n"
                "ايقاف - لإيقاف اللعبة الجارية\n"
                "سؤال - اختيار سؤال عشوائي من الأسئلة العامة\n"
                "تحدي - اختيار تحدي عشوائي\n"
                "اعتراف - اختيار اعتراف عشوائي\n"
                "شخصي - اختيار سؤال شخصي عشوائي\n"
                "لعبه - اختيار لعبة عشوائية من الألعاب العشر"
            )
        ))
        return

    # اختيار سؤال عام
    if text == "سؤال":
        item = get_next_item("questions")
        line_bot_api.reply_message(event.reply_token, TextSendMessage(
            text=f"{display_name}: {item}"
        ))
        return

    # اختيار تحدي
    if text == "تحدي":
        item = get_next_item("challenges")
        line_bot_api.reply_message(event.reply_token, TextSendMessage(
            text=f"{display_name}: {item}"
        ))
        return

    # اختيار اعتراف
    if text == "اعتراف":
        item = get_next_item("confessions")
        line_bot_api.reply_message(event.reply_token, TextSendMessage(
            text=f"{display_name}: {item}"
        ))
        return

    # اختيار سؤال شخصي
    if text == "شخصي":
        item = get_next_item("personal")
        line_bot_api.reply_message(event.reply_token, TextSendMessage(
            text=f"{display_name}: {item}"
        ))
        return

    # اختيار لعبة عشوائية
    if text.startswith("لعبه"):
        available_games = list(games.keys())[:10]
        chosen_game = random.choice(available_games)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(
            text=f"{display_name}: تم اختيار اللعبة -> {chosen_game}"
        ))
        return

    # أي رسالة أخرى
    line_bot_api.reply_message(event.reply_token, TextSendMessage(
        text="❌ لم أفهم الأمر، اكتب 'مساعدة' لمعرفة الأوامر."
    ))

# ======== تشغيل السيرفر ========
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
