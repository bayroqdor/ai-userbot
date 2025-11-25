import asyncio
import os
import time
import shutil
import glob
import sqlite3
import random
import yt_dlp
from pyrogram import Client, filters, enums
from pyrogram.types import Message
import google.generativeai as genai
from config import API_ID, API_HASH, GEMINI_API_KEY

# --- CONFIGURATION ---
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

# --- DATABASE ---
def init_db():
    conn = sqlite3.connect('userbot.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS messages
                 (date text, chat_id integer, sender_id integer, text text, type text)''')
    conn.commit()
    conn.close()

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

# --- HANDLERS ---

@app.on_message(filters.me & filters.command("stop", prefixes="."))
async def stop_handler(client, message):
    chat_id = message.chat.id
    if chat_id in active_backups:
        active_backups.remove(chat_id)
        await message.edit_text("🛑 Process stopped. Cleaning up...")
    else:
        await message.edit_text("⚠️ No active process to stop.")

# 1. TRANSCRIBE (.text)
@app.on_message(filters.me & filters.command("text", prefixes="."))
async def transcribe_handler(client, message):
    target = message.reply_to_message
    if not target or not (target.voice or target.audio or target.video_note or target.video):
        await message.edit_text("❌ Reply to media file.")
        return

    status = await message.edit_text("⬇️ Downloading...")
    file_path = None
    try:
        file_path = await app.download_media(target)
        await status.edit_text("🧠 Processing...")
        uploaded_file = await asyncio.to_thread(genai.upload_file, file_path)
        
        response = await asyncio.to_thread(
            model.generate_content, 
            [uploaded_file, "Transcribe audio to text verbatim. Output only the text."]
        )
        await status.edit_text(f"📝 **Transcription:**\n\n{response.text}")
        
    except Exception as e:
        await status.edit_text(f"❌ Error: {str(e)}")
    finally:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)

# 2. SUMMARIZE (.qisqa) - TUZATILDI
@app.on_message(filters.me & filters.command("qisqa", prefixes="."))
async def summarize_handler(client, message):
    target = message.reply_to_message
    
    # Text yoki Caption borligini tekshiramiz
    original_text = None
    if target:
        original_text = target.text or target.caption
        
    if not original_text:
        await message.edit_text("❌ Matnli xabarga yoki rasm (caption) ga reply qiling.")
        return

    await message.edit_text("🧠 Reading...")
    prompt = f"Summarize the following text in Uzbek (2-3 sentences):\n\n{original_text}"
    
    try:
        response = await asyncio.to_thread(model.generate_content, prompt)
        await message.edit_text(f"📌 **Summary:**\n\n{response.text}")
    except Exception as e:
        await message.edit_text(f"❌ Error: {e}")

# 3. TRANSLATE (.uz, .en, .ru) - MANTIQ TUZATILDI
@app.on_message(filters.me & filters.command(["en", "uz", "ru"], prefixes="."))
async def translation_handler(client, message):
    cmd = message.command[0]
    target_map = {"en": "English", "uz": "Uzbek", "ru": "Russian"}
    target_lang = target_map.get(cmd, "Uzbek")
    
    # A) REJIM: Sizning gapingizni tarjima qilish (Reply bo'lishi mumkin, lekin matn sizda)
    # Masalan: .ru Salom ishlar qalay (Kimgadir reply qilgan holda)
    if len(message.command) > 1:
        text_to_translate = " ".join(message.command[1:])
        
        # Loading ko'rsatmaymiz, to'g'ridan-to'g'ri almashtiramiz
        prompt = f"Translate the following text to {target_lang}. Output ONLY the translation, no extra text:\n\n{text_to_translate}"
        try:
            response = await asyncio.to_thread(model.generate_content, prompt)
            await message.edit_text(response.text)
        except:
            pass
            
    # B) REJIM: Birovning gapini tarjima qilish (Reply bor, lekin sizda matn yo'q)
    # Masalan: .ru (Birovning xabariga reply)
    elif message.reply_to_message:
        target = message.reply_to_message
        original_text = target.text or target.caption
        
        if original_text:
            await message.edit_text("🔄 Translating...")
            prompt = f"Translate the following text to {target_lang}. Output only translation:\n\n{original_text}"
            try:
                response = await asyncio.to_thread(model.generate_content, prompt)
                await message.edit_text(f"🌍 **Translation ({cmd.upper()}):**\n\n{response.text}")
            except Exception as e:
                await message.edit_text(f"❌ Error: {e}")
        else:
            await message.edit_text("❌ Reply qilingan xabarda matn yo'q.")
    else:
        await message.edit_text("⚠️ Foydalanish:\n1. `.ru Salom` (Gapirish)\n2. `.ru` (Reply qilib tushunish)")

# 4. MAGIC TYPE (.type)
@app.on_message(filters.me & filters.command("type", prefixes="."))
async def type_handler(client, message):
    if len(message.command) < 2: return
    original_text = message.text.split(" ", 1)[1]
    typed_text = ""
    try:
        for char in original_text:
            typed_text += char
            if typed_text.strip(): 
                await message.edit_text(typed_text + " ▌") 
                await asyncio.sleep(0.05) 
        await message.edit_text(typed_text)
    except:
        await message.edit_text(original_text)

# 5. DOWNLOAD VIDEO (.link)
@app.on_message(filters.me & filters.command("link", prefixes="."))
async def download_link_handler(client, message):
    if len(message.command) < 2: return await message.edit_text("❌ No URL provided.")
    url = message.command[1]
    await message.edit_text(f"🔍 Analyzing: `{url}`")
    
    download_path = f"downloads/{message.id}"
    os.makedirs(download_path, exist_ok=True)
    
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': f'{download_path}/%(title)s.%(ext)s',
        'merge_output_format': 'mp4',
        'noplaylist': True, 'quiet': True, 'no_warnings': True, 'geo_bypass': True,
    }
    
    try:
        await message.edit_text("⬇️ Downloading...")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl: 
            await asyncio.to_thread(ydl.download, [url])
            
        files = glob.glob(f"{download_path}/*")
        if not files: 
            return await message.edit_text("❌ Download failed.")
            
        await message.edit_text("📤 Uploading...")
        await app.send_video(
            message.chat.id, 
            video=files[0], 
            caption=f"🔗 Source: {url}", 
            supports_streaming=True
        )
        await message.delete()
        
    except Exception as e:
        await message.edit_text(f"❌ Error: {e}")
        await asyncio.sleep(5)
        await message.delete()
    finally:
        if os.path.exists(download_path):
            shutil.rmtree(download_path)

# 6. BACKUP (.backup)
@app.on_message(filters.me & filters.command("backup", prefixes="."))
async def backup_handler(client, message):
    chat_id = message.chat.id
    if chat_id in active_backups: return await message.edit_text("⚠️ Backup already running.")
    active_backups.add(chat_id)
    
    status_msg = await message.edit_text("⏳ Backup started... (.stop to cancel)")
    
    folder_name = f"backup_{chat_id}_{int(time.time())}"
    media_folder = os.path.join(folder_name, "media")
    os.makedirs(media_folder, exist_ok=True)
    zip_filename = f"{folder_name}.zip"
    
    html = """<!DOCTYPE html><html><head><meta charset="UTF-8"><style>body{font-family:sans-serif;background:#1e1e1e;color:#fff;padding:20px}.msg{margin:10px 0;padding:10px;border-radius:10px;max-width:80%;clear:both}.in{background:#2b2b2b;float:left}.out{background:#4b6ca5;float:right}.name{font-size:12px;color:#ccc;font-weight:bold}img,video{max-width:100%}</style></head><body><h2>Chat History</h2>"""
    
    forced_stop = False
    try:
        messages = []
        async for msg in app.get_chat_history(chat_id, limit=300):
            if chat_id not in active_backups: forced_stop = True; break
            messages.append(msg)
        messages.reverse()
        
        counter = 0
        for msg in messages:
            if chat_id not in active_backups: forced_stop = True; break
            counter += 1
            if counter % 10 == 0: await status_msg.edit_text(f"⏳ {counter} msgs processed... (.stop)")
            
            cls = "out" if msg.from_user and msg.from_user.is_self else "in"
            name = msg.from_user.first_name if msg.from_user else "ID"
            text = msg.text or msg.caption or ""
            media_tag = ""
            
            if msg.media and (msg.photo or msg.video or msg.voice or msg.audio):
                try:
                    path = await app.download_media(msg, file_name=media_folder + "/")
                    if path:
                        fn = os.path.basename(path)
                        if msg.photo: media_tag = f'<br><img src="media/{fn}">'
                        elif msg.video: media_tag = f'<br><video controls src="media/{fn}"></video>'
                        elif msg.voice: media_tag = f'<br><audio controls src="media/{fn}"></audio>'
                except: pass
            
            html += f'<div class="msg {cls}"><div class="name">{name}</div>{text}{media_tag}</div>'
        
        html += "</body></html>"
        with open(os.path.join(folder_name, "index.html"), "w", encoding="utf-8") as f: f.write(html)
        
        await status_msg.edit_text("🗜 Archiving...")
        shutil.make_archive(folder_name, 'zip', folder_name)
        
        await status_msg.edit_text("📤 Uploading...")
        await app.send_document(
            "me", 
            zip_filename, 
            caption=f"📦 Backup: {chat_id}" + (" (STOPPED)" if forced_stop else "")
        )
        await status_msg.edit_text("✅ Done." if not forced_stop else "🛑 Stopped.")
        
    except Exception as e:
        await status_msg.edit_text(f"❌ Error: {e}")
        
    finally:
        if chat_id in active_backups: active_backups.remove(chat_id)
        if os.path.exists(folder_name): shutil.rmtree(folder_name)
        if os.path.exists(zip_filename): os.remove(zip_filename)

# 7. STATS
@app.on_message(filters.me & filters.command("stats", prefixes="."))
async def stats_handler(client, message):
    conn = sqlite3.connect('userbot.db')
    c = conn.cursor()
    try:
        c.execute("SELECT COUNT(*) FROM messages WHERE type='incoming'")
        inc = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM messages WHERE type='mention'")
        mn = c.fetchone()[0]
        await message.edit_text(f"📊 **Stats**\n📩 Incoming Logs: {inc}\n🔔 Mentions: {mn}")
    except: pass
    finally: conn.close()

# --- LOGGING HANDLERS ---
@app.on_message(filters.me & filters.private)
async def self_reply_handler(client, message):
    log_message(message, "outgoing")

@app.on_message(filters.private & ~filters.me & ~filters.bot)
async def incoming_dm_handler(client, message):
    log_message(message, "incoming")

@app.on_message(filters.mentioned & filters.group)
async def mention_handler(client, message):
    log_message(message, "mention")
    await app.send_message("me", f"🔔 **Mentioned:**\n{message.link}")

if __name__ == "__main__":
    init_db()
    app.run()