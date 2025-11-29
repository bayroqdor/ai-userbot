import asyncio
import os
import time
import shutil
import glob
import sqlite3
import random
import math
import html
import yt_dlp
from datetime import datetime, timedelta
from pyrogram import Client, filters, enums
from pyrogram.types import Message
import google.generativeai as genai
from config import API_ID, API_HASH, GEMINI_API_KEY

# ==========================================================
# --- 1. SOZLAMALAR ---
# ==========================================================
genai.configure(api_key=GEMINI_API_KEY)

safety_settings = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
]

try:
    model = genai.GenerativeModel('gemini-2.0-flash', safety_settings=safety_settings)
except:
    try:
        model = genai.GenerativeModel('gemini-1.5-flash', safety_settings=safety_settings)
    except:
        model = genai.GenerativeModel('gemini-pro', safety_settings=safety_settings)

app = Client("my_userbot", api_id=API_ID, api_hash=API_HASH)
active_backups = set()

# ==========================================================
# --- 2. BAZA VA YORDAMCHI FUNKSIYALAR ---
# ==========================================================

def init_db():
    conn = sqlite3.connect('userbot.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS messages
                 (date text, chat_id integer, sender_id integer, text text, type text)''')
    c.execute('''CREATE TABLE IF NOT EXISTS settings
                 (key text primary key, value text)''')
    c.execute('''CREATE TABLE IF NOT EXISTS sources
                 (chat_id integer primary key, title text)''')
    conn.commit()
    conn.close()

def set_setting(key, value):
    conn = sqlite3.connect('userbot.db')
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()

def get_setting(key):
    conn = sqlite3.connect('userbot.db')
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key=?", (key,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None

def add_source_channel(chat_id, title):
    conn = sqlite3.connect('userbot.db')
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO sources VALUES (?, ?)", (chat_id, title))
    conn.commit()
    conn.close()

def remove_source_channel(chat_id):
    conn = sqlite3.connect('userbot.db')
    c = conn.cursor()
    c.execute("DELETE FROM sources WHERE chat_id=?", (chat_id,))
    conn.commit()
    conn.close()

def get_all_sources():
    conn = sqlite3.connect('userbot.db')
    c = conn.cursor()
    c.execute("SELECT chat_id FROM sources")
    result = {row[0] for row in c.fetchall()}
    conn.close()
    return result

def log_message(message: Message, msg_type="incoming"):
    try:
        conn = sqlite3.connect('userbot.db')
        c = conn.cursor()
        text = message.text or message.caption or "[Media]"
        # Convert datetime to ISO format string
        date_str = message.date.isoformat() if message.date else datetime.now().isoformat()
        c.execute("INSERT INTO messages VALUES (?, ?, ?, ?, ?)", 
                  (date_str, message.chat.id, message.from_user.id if message.from_user else 0, text, msg_type))
        conn.commit()
        conn.close()
    except: pass

# --- PROGRESS BAR ---
def humanbytes(size):
    if not size: return ""
    power = 2**10
    n = 0
    dic_powerN = {0: ' ', 1: 'Ki', 2: 'Mi', 3: 'Gi', 4: 'Ti'}
    while size > power:
        size /= power
        n += 1
    return str(round(size, 2)) + " " + dic_powerN[n] + 'B'

last_update_time = {}

async def progress_bar(current, total, message: Message, start_time, action_text):
    now = time.time()
    chat_id = message.chat.id
    if chat_id in last_update_time and (now - last_update_time[chat_id] < 3) and (current != total):
        return
    last_update_time[chat_id] = now
    percentage = current * 100 / total
    speed = current / (now - start_time) if (now - start_time) > 0 else 0
    
    progress_str = "[{0}{1}]".format(
        ''.join(["■" for i in range(math.floor(percentage / 10))]),
        ''.join(["□" for i in range(10 - math.floor(percentage / 10))])
    )
    text = f"{action_text}\n{progress_str} **{round(percentage, 1)}%**\n💾 {humanbytes(current)} / {humanbytes(total)}\n🚀 {humanbytes(speed)}/s"
    try: await message.edit_text(text)
    except: pass

# --- AI HELPER ---
async def summarize_news(text, channel_name):
    prompt = f"Quyidagi yangilik '{channel_name}' kanalida chiqdi. Uning eng asosiy mazmunini 2-3 ta gap bilan O'zbek tilida yozib ber:\n\n{text}"
    try:
        response = await asyncio.to_thread(model.generate_content, prompt)
        return response.text
    except: return None

# --- HTML STYLES (TELEGRAM DARK MODE) ---
HTML_HEAD = """
<!DOCTYPE html>
<html lang="uz">
<head>
<meta charset="UTF-8">
<style>
    body { background-color: #0e1621; color: #fff; font-family: sans-serif; margin: 0; padding: 20px; }
    .container { max-width: 700px; margin: 0 auto; display: flex; flex-direction: column; gap: 8px; }
    .message { max-width: 80%; padding: 8px 12px; border-radius: 12px; position: relative; font-size: 15px; word-wrap: break-word; }
    .incoming { align-self: flex-start; background-color: #182533; }
    .outgoing { align-self: flex-end; background-color: #2b5278; }
    .sender-name { font-weight: bold; color: #64b5f6; font-size: 13px; margin-bottom: 4px; display: block; }
    .meta { font-size: 11px; color: #8fa0b5; text-align: right; margin-top: 4px; }
    img, video { max-width: 100%; border-radius: 8px; margin-bottom: 5px; display: block; }
    audio { width: 100%; margin-top: 5px; }
</style>
</head>
<body><div class="container">
"""
HTML_FOOTER = "</div></body></html>"

# ==========================================================
# --- 3. HANDLERS ---
# ==========================================================

@app.on_message(filters.me & filters.command("stop", prefixes="."))
async def stop_handler(client, message):
    chat_id = message.chat.id
    if chat_id in active_backups:
        active_backups.remove(chat_id)
        await message.edit_text("🛑 To'xtatildi.")
    else: await message.edit_text("⚠️ Jarayon yo'q.")

# --- SETTINGS ---
@app.on_message(filters.me & filters.command("setdest", prefixes="."))
async def set_dest_handler(client, message):
    if len(message.command) < 2: return await message.edit_text("❌ ID kiriting.")
    target = message.command[1]
    if target == "off": set_setting("dest_channel", "off"); return await message.edit_text("🔕 O'chirildi.")
    try: chat = await app.get_chat(target); set_setting("dest_channel", chat.id); await message.edit_text(f"✅ Qabul: {chat.title}")
    except: await message.edit_text("❌ Kanal topilmadi.")

@app.on_message(filters.me & filters.command("addsource", prefixes="."))
async def add_source_handler(client, message):
    chat_id = message.chat.id; title = message.chat.title or "Kanal"
    if len(message.command) > 1:
        try: chat = await app.get_chat(message.command[1]); chat_id = chat.id; title = chat.title
        except: return await message.edit_text("❌ Xato.")
    add_source_channel(chat_id, title)
    await message.edit_text(f"✅ Qo'shildi: {title}")

@app.on_message(filters.me & filters.command("delsource", prefixes="."))
async def del_source_handler(client, message):
    chat_id = message.chat.id
    if len(message.command) > 1:
        try: chat = await app.get_chat(message.command[1]); chat_id = chat.id
        except: pass
    remove_source_channel(chat_id)
    await message.edit_text(f"🗑 Olib tashlandi.")

@app.on_message(filters.me & filters.command("listsources", prefixes="."))
async def list_sources_handler(client, message):
    conn = sqlite3.connect('userbot.db'); c = conn.cursor()
    c.execute("SELECT title, chat_id FROM sources"); rows = c.fetchall(); conn.close()
    await message.edit_text("📋 **Manbalar:**\n\n" + "\n".join([f"• {r[0]}" for r in rows]) if rows else "📭 Bo'sh")

# --- TOOLS ---

# 1. TRANSCRIBE (.text)
@app.on_message(filters.me & filters.command("text", prefixes="."))
async def transcribe_handler(client, message):
    target = message.reply_to_message
    if not target or not (target.voice or target.audio or target.video_note or target.video):
        await message.edit_text("❌ Media reply qiling.")
        return
    status = await message.edit_text("⬇️ Yuklanmoqda...")
    file_path = None; start = time.time()
    try:
        file_path = await app.download_media(target, progress=progress_bar, progress_args=(status, start, "⬇️ Serverga..."))
        await status.edit_text("🧠 Tahlil...")
        uploaded = await asyncio.to_thread(genai.upload_file, file_path)
        res = await asyncio.to_thread(model.generate_content, [uploaded, "Transcribe verbatim."])
        await status.edit_text(f"📝 **Matn:**\n\n{res.text}")
    except Exception as e: await status.edit_text(f"❌ {e}")
    finally:
        if file_path and os.path.exists(file_path): os.remove(file_path)

# 2. DOWNLOAD (.link)
@app.on_message(filters.me & filters.command("link", prefixes="."))
async def download_link_handler(client, message):
    if len(message.command) < 2: return await message.edit_text("❌ Link yo'q.")
    url = message.command[1]; status = await message.edit_text(f"🔍 Tahlil...")
    path = f"downloads/{message.id}"; os.makedirs(path, exist_ok=True)
    opts = {'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best', 'outtmpl': f'{path}/%(title)s.%(ext)s', 'merge_output_format': 'mp4', 'noplaylist': True, 'quiet': True, 'no_warnings': True}
    try:
        await status.edit_text("⬇️ Serverga...")
        with yt_dlp.YoutubeDL(opts) as ydl: await asyncio.to_thread(ydl.download, [url])
        files = glob.glob(f"{path}/*")
        if not files: return await status.edit_text("❌ Xato.")
        await app.send_video(message.chat.id, video=files[0], caption=f"🔗 {url}", supports_streaming=True, progress=progress_bar, progress_args=(status, time.time(), "📤 Yuklanmoqda"))
        await status.delete(); await message.delete()
    except Exception as e: await status.edit_text(f"❌ {e}"); await asyncio.sleep(5); await status.delete()
    finally:
        if os.path.exists(path): shutil.rmtree(path)

# 3. BACKUP (.backup) - SANA VA SONI BILAN
@app.on_message(filters.me & filters.command("backup", prefixes="."))
async def backup_handler(client, message):
    chat_id = message.chat.id
    if chat_id in active_backups: return await message.edit_text("⚠️ Backup ketmoqda.")
    
    args = message.command[1] if len(message.command) > 1 else "200"
    limit_count = 0; start_date = None; end_date = None; mode_text = ""
    is_date_mode = False

    if "-" in args and len(args.split("-")) == 2:
        try:
            parts = args.split("-")
            s_date = datetime.strptime(parts[0].strip(), "%d.%m.%Y")
            e_date = datetime.strptime(parts[1].strip(), "%d.%m.%Y").replace(hour=23, minute=59, second=59)
            if s_date > e_date: s_date, e_date = e_date, s_date
            start_date, end_date, is_date_mode = s_date, e_date, True
            mode_text = f"{start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')}"
        except: return await message.edit_text("❌ Format: `.backup 01.11.2024-05.11.2024`")
    elif args.isdigit():
        limit_count = int(args); mode_text = f"Oxirgi {limit_count} ta"
    else: return await message.edit_text("❌ Xato buyruq.")

    active_backups.add(chat_id)
    status = await message.edit_text(f"⏳ Backup boshlandi... ({mode_text})")
    base_folder = f"backup_{chat_id}_{int(time.time())}"
    media_folder_abs = os.path.join(base_folder, "media")
    os.makedirs(media_folder_abs, exist_ok=True)
    forced = False
    
    try:
        msgs = []
        async for m in app.get_chat_history(chat_id):
            if chat_id not in active_backups: forced=True; break
            if is_date_mode:
                if m.date > end_date: continue
                if m.date < start_date: break
                msgs.append(m)
            else:
                if len(msgs) >= limit_count: break
                msgs.append(m)
            if len(msgs) % 50 == 0: await status.edit_text(f"⏳ Yig'ilmoqda: {len(msgs)} ta...")

        if not msgs:
            await status.edit_text("❌ Xabarlar topilmadi.")
            active_backups.remove(chat_id); shutil.rmtree(base_folder); return

        msgs.reverse()
        html_content = HTML_HEAD
        for i, m in enumerate(msgs):
            if chat_id not in active_backups: forced=True; break
            if i % 20 == 0: await status.edit_text(f"⏳ Fayllar yuklanmoqda: {i}/{len(msgs)}")
            is_me = m.from_user and m.from_user.is_self; msg_class = "outgoing" if is_me else "incoming"
            sender = html.escape(m.from_user.first_name if m.from_user else "Deleted")
            text_content = html.escape(m.text or m.caption or "").replace("\n", "<br>")
            date_str = m.date.strftime("%H:%M")
            media_html = ""
            if m.media:
                try:
                    fp = await app.download_media(m, file_name=media_folder_abs + "/")
                    if fp:
                        fn = os.path.basename(fp); rel = f"media/{fn}"
                        if m.photo: media_html = f'<a href="{rel}"><img src="{rel}"></a>'
                        elif m.video or m.video_note: media_html = f'<video controls><source src="{rel}"></video>'
                        elif m.voice or m.audio: media_html = f'<audio controls><source src="{rel}"></audio>'
                        else: media_html = f'<a href="{rel}">📎 {fn}</a>'
                except: pass
            html_content += f'<div class="message {msg_class}"><span class="sender-name">{sender}</span>{media_html}<div class="text">{text_content}</div><div class="meta">{date_str}</div></div>'
        
        html_content += HTML_FOOTER
        if forced: raise Exception("To'xtatildi")
        with open(f"{base_folder}/index.html", "w", encoding="utf-8") as f: f.write(html_content)
        await status.edit_text("🗜 Arxivlanmoqda...")
        shutil.make_archive(base_folder, 'zip', base_folder)
        await app.send_document("me", f"{base_folder}.zip", caption=f"📦 Backup: {chat_id}\n📊 {len(msgs)} ta\n🎯 {mode_text}", progress=progress_bar, progress_args=(status, time.time(), "📤 Yuborilmoqda"))
        await status.delete()
    except Exception as e: await status.edit_text(f"❌ {e}")
    finally:
        if chat_id in active_backups: active_backups.remove(chat_id)
        if os.path.exists(base_folder): shutil.rmtree(base_folder)
        if os.path.exists(f"{base_folder}.zip"): os.remove(f"{base_folder}.zip")

# 4. TRANSLATE (.tr, .uz, .en, .ru) 
@app.on_message(filters.me & filters.command(["tr", "uz", "en", "ru"], prefixes="."))
async def translation_handler(client, message):
    cmd = message.command[0]
    # Tilni aniqlash
    if cmd == "tr":
        if len(message.command) < 2: return await message.edit_text("⚠️ Kod yozing: `.tr en`")
        lang_code = message.command[1]
        text_args = message.command[2:] # .tr en Hello World
    else:
        lang_code = cmd # .uz, .en, .ru
        text_args = message.command[1:] # .uz Hello World

    langs = {"en": "English", "ru": "Russian", "uz": "Uzbek", "tr": "Turkish", "ar": "Arabic", "de": "German"}
    target = langs.get(lang_code, lang_code)

    # 1. Matn yozilgan bo'lsa (Tarjima qilib EDIT qilish)
    if text_args:
        txt = " ".join(text_args)
        try:
            res = await asyncio.to_thread(model.generate_content, f"Translate to {target}. Output ONLY translation:\n\n{txt}")
            await message.edit_text(res.text)
        except: pass
    
    # 2. Reply qilingan bo'lsa (Birovning gapini tarjima qilish)
    elif message.reply_to_message:
        target_msg = message.reply_to_message
        txt = target_msg.text or target_msg.caption
        if txt:
            await message.edit_text(f"🔄 ...")
            try:
                res = await asyncio.to_thread(model.generate_content, f"Translate to {target}. Output only translation:\n\n{txt}")
                await message.edit_text(f"🌍 **{lang_code.upper()}:**\n\n{res.text}")
            except Exception as e: await message.edit_text(f"❌ {e}")
        else: await message.edit_text("❌ Matn yo'q.")
    else: await message.edit_text(f"⚠️ Namuna:\n`.{lang_code} Salom`\n`.{lang_code}` (Reply)")

# 5. QISQA (.qisqa)
@app.on_message(filters.me & filters.command("qisqa", prefixes="."))
async def summarize_handler(client, message):
    target = message.reply_to_message
    txt = target.text or target.caption if target else None
    if not txt: return await message.edit_text("❌ Matn yo'q.")
    await message.edit_text("🧠 ...")
    try: res = await asyncio.to_thread(model.generate_content, f"Summarize in Uzbek:\n{txt}"); await message.edit_text(f"📌 **Qisqa:**\n{res.text}")
    except Exception as e: await message.edit_text(f"❌ {e}")

# 6. TYPE (.type)
@app.on_message(filters.me & filters.command("type", prefixes="."))
async def type_handler(client, message):
    if len(message.command)<2: return
    txt = message.text.split(" ", 1)[1]; curr=""
    try:
        for c in txt: curr+=c; await message.edit_text(curr+" ▌"); await asyncio.sleep(0.05)
        await message.edit_text(curr)
    except: await message.edit_text(txt)

@app.on_message(filters.me & filters.command("stats", prefixes="."))
async def stats_handler(client, message):
    conn = sqlite3.connect('userbot.db'); c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM messages"); cnt = c.fetchone()[0]; conn.close()
    await message.edit_text(f"📊 Jami loglar: {cnt}")

@app.on_message(filters.channel & ~filters.me)
async def channel_monitor(client, message):
    if message.chat.id not in get_all_sources(): return
    dest = get_setting("dest_channel")
    if not dest or dest=="off": return
    txt = message.text or message.caption
    if txt and len(txt)>50:
        sum_text = await summarize_news(txt, message.chat.title)
        if sum_text: await app.send_message(int(dest), f"{sum_text}\n\n📰 {message.chat.title}\n🔗 {message.link}")

@app.on_message(filters.me & filters.private)
async def log_out(c, m): log_message(m, "out")
@app.on_message(filters.private & ~filters.me & ~filters.bot)
async def log_in(c, m): log_message(m, "in")

if __name__ == "__main__":
    init_db()
    app.run()