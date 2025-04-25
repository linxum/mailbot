import threading
import time
from imapclient import IMAPClient
import email
from email.header import decode_header
import telebot
import html
import psycopg2

# --- Настройки ---
EMAIL = 'email'
PASSWORD = 'password'
IMAP_SERVER = 'server'

BOT_TOKEN = 'token'
CHAT_ID = "id"
ALLOWED_SENDER = 'email'

DB_PARAMS = {
    'host': 'ip',
    'port': '5432',
    'dbname': 'name',
    'user': 'user',
    'password': 'password'
}

bot = telebot.TeleBot(BOT_TOKEN)

# --- Работа с базой ---
def get_db_connection():
    return psycopg2.connect(**DB_PARAMS)

def is_uid_processed(uid):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM processed_emails WHERE uid = %s", (uid,))
            return cur.fetchone() is not None

def mark_uid_processed(uid):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO processed_emails (uid) VALUES (%s) ON CONFLICT DO NOTHING", (uid,))
        conn.commit()

# --- Обработка MIME и писем ---
def decode_mime_words(s):
    decoded = decode_header(s)
    return ''.join([
        part.decode(encoding or 'utf-8') if isinstance(part, bytes) else part
        for part, encoding in decoded
    ])

def extract_email_address(full_from_header):
    if '<' in full_from_header and '>' in full_from_header:
        return full_from_header.split('<')[1].split('>')[0].strip()
    return full_from_header.strip()

def extract_plain_text(msg):
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and "attachment" not in str(part.get("Content-Disposition", "")):
                charset = part.get_content_charset() or 'utf-8'
                try:
                    return part.get_payload(decode=True).decode(charset, errors='replace')
                except:
                    continue
    else:
        charset = msg.get_content_charset() or 'utf-8'
        return msg.get_payload(decode=True).decode(charset, errors='replace')
    return ""

def process_mail(server):
    server.select_folder('INBOX', readonly=True)
    messages = server.search(['UNSEEN'])
    for uid in messages:
        if is_uid_processed(uid):
            print(f"⏩ UID {uid} уже обработан.")
            continue

        raw_message = server.fetch([uid], ['BODY[]', 'FLAGS'])
        message_bytes = raw_message[uid][b'BODY[]']
        msg = email.message_from_bytes(message_bytes)

        subject = html.escape(decode_mime_words(msg.get('Subject', '')))
        from_raw = decode_mime_words(msg.get('From', ''))
        from_clean = extract_email_address(from_raw)

        if from_clean.lower() != ALLOWED_SENDER.lower():
            print(f"📭 Игнорируем письмо от {from_clean}")
            continue

        body = extract_plain_text(msg)
        body_safe = html.escape(body.strip())
        if len(body_safe) > 1000:
            body_safe = body_safe[:1000] + '...'

        text = (
            f"📬 <b>Новое письмо!</b>\n"
            f"👤 От: {html.escape(from_raw)}\n"
            f"📝 Тема: {subject}\n"
            f"📄 Сообщение:\n<pre>{body_safe}</pre>"
        )

        try:
            bot.send_message(CHAT_ID, text, parse_mode='HTML')
            mark_uid_processed(uid)
            print(f"✅ UID {uid} обработан и сохранён в БД.")
        except Exception as e:
            print("⚠️ Ошибка отправки:", e)

# --- Основной цикл ---
def mail_monitor():
    while True:
        try:
            with IMAPClient(IMAP_SERVER) as server:
                server.login(EMAIL, PASSWORD)
                print("📡 Мониторинг запущен.")

                while True:
                    try:
                        process_mail(server)
                        time.sleep(60)
                    except Exception as e:
                        print("⚠️ Ошибка при проверке писем:", e)
                        time.sleep(5)

        except Exception as e:
            print("❌ Ошибка подключения к IMAP:", e)
            time.sleep(10)

# --- Запуск ---
threading.Thread(target=mail_monitor, daemon=True).start()

@bot.message_handler(commands=['start'])
def handle_start(message):
    bot.send_message(message.chat.id, "👋 Бот следит за письмами.")
    print("chat.id пользователя:", message.chat.id)

print("🤖 Бот запущен.")
bot.infinity_polling()
