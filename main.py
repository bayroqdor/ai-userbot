import asyncio
import os
import time
import shutil
import glob
import sqlite3
import random
import math
import yt_dlp
from pyrogram import Client, filters, enums
from pyrogram.types import Message
import google.generativeai as genai
from config import API_ID, API_HASH, GEMINI_API_KEY

# --- CONFIGURATION ---
genai.configure(api_key=GEMINI_API_KEY)

# Xavfsizlik va Model
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

# --- DATABASE ---
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

# --- HELPERS ---
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
        c.execute("INSERT INTO messages VALUES (?, ?, ?, ?, ?)", 
                  (message.date, message.chat.id, message.from_user.id if message.from_user else 0, text, msg_type))
        conn.commit()
        conn.close()
    except: pass

# --- PROGRESS BAR FUNCTION (YANGI) ---
def humanbytes(size):
    """Baytlarni MB/GB ga o'girish"""
    if not size: return ""
    power = 2**10
    n = 0
    dic_powerN = {0: ' ', 1: 'Ki', 2: 'Mi', 3: 'Gi', 4: 'Ti'}
    while size > power:
        size /= power
        n += 1
    return str(round(size, 2)) + " " + dic_powerN[n] + 'B'

# Oxirgi yangilangan vaqtni saqlash uchun (FloodWait oldini olish)
last_update_time = {}

async def progress_bar(current, total, message: Message, start_time, action_text):
    now = time.time()
    chat_id = message.chat.id
    
    # Har 3 soniyada yoki jarayon tugaganda yangilaymiz
    if chat_id in last_update_time and (now - last_update_time[chat_id] < 3) and (current != total):
        return

    last_update_time[chat_id] = now
    
    percentage = current * 100 / total
    speed = current / (now - start_time) if (now - start_time) > 0 else 0
    elapsed_time = round(now - start_time) * 1000
    time_to_completion = round((total - current) / speed) * 1000 if speed > 0 else 0
    estimated_total_time = elapsed_time + time_to_completion

    elapsed_time_str = time.strftime("%M:%S", time.gmtime(elapsed_time / 1000))
    estimated_total_time_str = time.strftime("%M:%S", time.gmtime(estimated_total_time / 1000))

    # Progress bar chizish
    progress_str = "[{0}{1}]".format(
        ''.join(["■" for i in range(math.floor(percentage / 10))]),
        ''.join(["□" for i in range(10 - math.floor(percentage / 10))])
    )

    text = f"""
{action_text}
{progress_str} **{round(percentage, 1)}%**

💾 **Hajm:** {humanbytes(current)} / {humanbytes(total)}
⏱ **Vaqt:** {elapsed_time_str} / {estimated_total_time_str}
🚀 **Tezlik:** {humanbytes(speed)}/s
"""
    try:
        await message.edit_text(text)
    except:
        pass

# --- AI HELPER ---
async def summarize_news(text, channel_name):
    prompt = f"Quyidagi yangilik '{channel_name}' kanalida chiqdi. Uning eng asosiy mazmunini 2-3 ta gap bilan O'zbek tilida yozib ber:\n\n{text}"
    try:
        response = await asyncio.to_thread(model.generate_content, prompt)
        return response.text
    except: return None

# ==========================================================
# --- HANDLERS ---
# ==========================================================

@app.on_message(filters.me & filters.command("stop", prefixes="."))
async def stop_handler(client, message):
    chat_id = message.chat.id
    if chat_id in active_backups:
        active_backups.remove(chat_id)
        await message.edit_text("🛑 Jarayon to'xtatildi.")
    else: await message.edit_text("⚠️ To'xtatadigan jarayon yo'q.")

# --- SETTINGS HANDLERS ---
@app.on_message(filters.me & filters.command("setdest", prefixes="."))
async def set_dest_handler(client, message):
    if len(message.command) < 2:
        return await message.edit_text("❌ Kanal ID yoki Usernameni kiriting.")
    target = message.command[1]
    if target == "off":
        set_setting("dest_channel", "off")
        return await message.edit_text("🔕 Digest o'chirildi.")
    try:
        chat = await app.get_chat(target)
        set_setting("dest_channel", chat.id)
        await message.edit_text(f"✅ Qabul qiluvchi kanal: {chat.title}")
    except: await message.edit_text("❌ Kanal topilmadi.")

@app.on_message(filters.me & filters.command("addsource", prefixes="."))
async def add_source_handler(client, message):
    chat_id = message.chat.id
    title = message.chat.title or "Kanal"
    if len(message.command) > 1:
        try:
            chat = await app.get_chat(message.command[1])
            chat_id = chat.id; title = chat.title
        except: return await message.edit_text("❌ Kanal topilmadi.")
    add_source_channel(chat_id, title)
    await message.edit_text(f"✅ Kuzatuvga olindi: {title}")

@app.on_message(filters.me & filters.command("delsource", prefixes="."))
async def del_source_handler(client, message):
    chat_id = message.chat.id
    if len(message.command) > 1:
        try: chat = await app.get_chat(message.command[1]); chat_id = chat.id
        except: pass
    remove_source_channel(chat_id)
    await message.edit_text(f"🗑 Olib tashlandi: {chat_id}")

@app.on_message(filters.me & filters.command("listsources", prefixes="."))
async def list_sources_handler(client, message):
    conn = sqlite3.connect('userbot.db'); c = conn.cursor()
    c.execute("SELECT title, chat_id FROM sources"); rows = c.fetchall(); conn.close()
    text = "📋 **Manbalar:**\n\n" + "\n".join([f"• {r[0]}" for r in rows])
    await message.edit_text(text if rows else "📭 Bo'sh")

# --- TOOLS WITH PROGRESS ---

# 1. TRANSCRIBE (.text) - Progress bilan
@app.on_message(filters.me & filters.command("text", prefixes="."))
async def transcribe_handler(client, message):
    target = message.reply_to_message
    if not target or not (target.voice or target.audio or target.video_note or target.video):
        await message.edit_text("❌ Media faylga reply qiling.")
        return

    status = await message.edit_text("⬇️ Yuklanmoqda...")
    file_path = None
    start_time = time.time()

    try:
        # Download with Progress
        file_path = await app.download_media(
            target,
            progress=progress_bar,
            progress_args=(status, start_time, "⬇️ Serverga yuklanmoqda")
        )
        
        await status.edit_text("🧠 Gemini Tahlil qilmoqda...")
        uploaded_file = await asyncio.to_thread(genai.upload_file, file_path)
        response = await asyncio.to_thread(model.generate_content, [uploaded_file, "Transcribe verbatim."])
        await status.edit_text(f"📝 **Matn:**\n\n{response.text}")
        
    except Exception as e:
        await status.edit_text(f"❌ Xato: {e}")
    finally:
        if file_path and os.path.exists(file_path): os.remove(file_path)

# 2. DOWNLOAD VIDEO (.link) - Progress bilan
@app.on_message(filters.me & filters.command("link", prefixes="."))
async def download_link_handler(client, message):
    if len(message.command) < 2: return await message.edit_text("❌ Link yo'q.")
    url = message.command[1]
    status = await message.edit_text(f"🔍 Tahlil qilinmoqda...")
    
    download_path = f"downloads/{message.id}"
    os.makedirs(download_path, exist_ok=True)
    ydl_opts = {'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best', 'outtmpl': f'{download_path}/%(title)s.%(ext)s', 'merge_output_format': 'mp4', 'noplaylist': True, 'quiet': True, 'no_warnings': True}
    
    try:
        await status.edit_text("⬇️ Serverga yuklanmoqda (yt-dlp)...")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl: await asyncio.to_thread(ydl.download, [url])
        files = glob.glob(f"{download_path}/*")
        if not files: return await status.edit_text("❌ Xato.")
        
        # Upload with Progress
        start_time = time.time()
        await app.send_video(
            message.chat.id, 
            video=files[0], 
            caption=f"🔗 {url}", 
            supports_streaming=True,
            progress=progress_bar,
            progress_args=(status, start_time, "📤 Telegramga yuklanmoqda")
        )
        await status.delete() # Progress tugagach statusni o'chiramiz
        await message.delete() # Original komandani ham
    except Exception as e:
        await status.edit_text(f"❌ {e}")
        await asyncio.sleep(5); await status.delete()
    finally:
        if os.path.exists(download_path): shutil.rmtree(download_path)

# 3. BACKUP (.backup) - Progress bilan
@app.on_message(filters.me & filters.command("backup", prefixes="."))
async def backup_handler(client, message):
    chat_id = message.chat.id
    if chat_id in active_backups: return await message.edit_text("⚠️ Jarayon ketmoqda.")
    active_backups.add(chat_id)
    status = await message.edit_text("⏳ Backup boshlandi...")
    folder = f"backup_{chat_id}_{int(time.time())}"
    os.makedirs(f"{folder}/media", exist_ok=True)
    
    forced = False
    try:
        # Xabarlarni yig'ish (Tez bo'lishi uchun progress shart emas, status yangilanadi)
        msgs = []
        async for m in app.get_chat_history(chat_id, limit=300):
            if chat_id not in active_backups: forced=True; break
            msgs.append(m)
        msgs.reverse()
        
        html = "<html><body><h2>History</h2>"
        for i, m in enumerate(msgs):
            if chat_id not in active_backups: forced=True; break
            if i%20==0: await status.edit_text(f"⏳ Fayllar yuklanmoqda: {i}/{len(msgs)}...")
            
            sender = m.from_user.first_name if m.from_user else "ID"
            txt = m.text or m.caption or ""
            med = ""
            if m.media:
                try: p = await app.download_media(m, file_name=f"{folder}/media/"); med = f"<br>[Media: {os.path.basename(p)}]" if p else ""
                except: pass
            html += f"<p><b>{sender}:</b> {txt} {med}</p>"
        
        if forced: raise Exception("To'xtatildi")
        
        with open(f"{folder}/index.html", "w") as f: f.write(html+"</body></html>")
        await status.edit_text("🗜 Arxivlanmoqda...")
        shutil.make_archive(folder, 'zip', folder)
        
        # Upload with Progress
        start_time = time.time()
        await app.send_document(
            "me", 
            f"{folder}.zip", 
            caption=f"📦 Backup: {chat_id}",
            progress=progress_bar,
            progress_args=(status, start_time, "📤 Arxiv yuborilmoqda")
        )
        await status.delete()
        
    except Exception as e: await status.edit_text(f"❌ {e}")
    finally:
        if chat_id in active_backups: active_backups.remove(chat_id)
        if os.path.exists(folder): shutil.rmtree(folder)
        if os.path.exists(f"{folder}.zip"): os.remove(f"{folder}.zip")

# --- OTHER HANDLERS ---
@app.on_message(filters.me & filters.command("qisqa", prefixes="."))
async def summarize_manual_handler(client, message):
    target = message.reply_to_message
    txt = target.text or target.caption if target else None
    if not txt: return await message.edit_text("❌ Matn yo'q.")
    await message.edit_text("🧠 ...")
    try: res = await asyncio.to_thread(model.generate_content, f"Summarize in Uzbek:\n{txt}"); await message.edit_text(f"📌 **Qisqa:**\n{res.text}")
    except Exception as e: await message.edit_text(f"❌ {e}")

@app.on_message(filters.me & filters.command(["en", "uz", "ru"], prefixes="."))
async def translation_handler(client, message):
    cmd = message.command[0]; map = {"en":"English","uz":"Uzbek","ru":"Russian"}; target = map.get(cmd, "Uzbek")
    if len(message.command)>1:
        txt = " ".join(message.command[1:])
        try: res = await asyncio.to_thread(model.generate_content, f"Translate to {target} only:\n{txt}"); await message.edit_text(res.text)
        except: pass
    elif message.reply_to_message:
        txt = message.reply_to_message.text or message.reply_to_message.caption
        if txt:
            await message.edit_text("🔄 ...")
            try: res = await asyncio.to_thread(model.generate_content, f"Translate to {target} only:\n{txt}"); await message.edit_text(f"🌍 **{cmd.upper()}:**\n{res.text}")
            except Exception as e: await message.edit_text(f"❌ {e}")

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
    await message.edit_text(f"📊 Jami xabarlar logi: {cnt}")

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