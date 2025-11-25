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
SYSTEM_PROMPT = "Javoblaring qisqa va londa bo'lsin. O'zbek tilida javob ber."

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

@app.on_message(filters.me & filters.command("stop", prefixes="."))
async def stop_handler(client, message):
    chat_id = message.chat.id
    if chat_id in active_backups:
        active_backups.remove(chat_id)
        await message.edit_text("🛑 Stopped.")
    else:
        await message.edit_text(⚠️ No active process.")

@app.on_message(filters.me & filters.command("text", prefixes="."))
async def transcribe_handler(client, message):
    target = message.reply_to_message
    if not target or not (target.voice or target.audio or target.video_note or target.video):
        await message.edit_text("❌ Reply to media.")
        return

    status = await message.edit_text("⬇️ Downloading...")
    file_path = None
    try:
        file_path = await app.download_media(target)
        await status.edit_text("🧠 Processing...")
        
        uploaded_file = await asyncio.to_thread(genai.upload_file, file_path)
        response = await asyncio.to_thread(
            model.generate_content, 
            [uploaded_file, "Transcribe audio to text verbatim. No extra comments."]
        )
        await status.edit_text(f"📝 **Transcription:**\n\n{response.text}")
        
    except Exception as e:
        await status.edit_text(f"❌ Error: {str(e)}")
    finally:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)

@app.on_message(filters.me & filters.command("qisqa", prefixes="."))
async def summarize_handler(client, message):
    target = message.reply_to_message
    if not target or not target.text:
        await message.edit_text("❌ Reply to text.")
        return

    await message.edit_text("🧠 Reading...")
    prompt = f"Summarize the following text in Uzbek in 2-3 sentences:\n\n{target.text}"
    
    try:
        response = await asyncio.to_thread(model.generate_content, prompt)
        await message.edit_text(f"📌 **Summary:**\n\n{response.text}")
    except Exception as e:
        await message.edit_text(f"❌ Error: {e}")

@app.on_message(filters.me & filters.command(["en", "uz", "ru"], prefixes="."))
async def translation_handler(client, message):
    cmd = message.command[0]
    target_map = {"en": "English", "uz": "Uzbek", "ru": "Russian"}
    target_lang = target_map.get(cmd, "Uzbek")
    
    if message.reply_to_message and message.reply_to_message.text:
        await message.edit_text("🔄 ...")
        prompt = f"Translate the following text to {target_lang}. Output only translation:\n\n{message.reply_to_message.text}"
        try:
            response = await asyncio.to_thread(model.generate_content, prompt)
            await message.edit_text(f"🌍 **{cmd.upper()}:**\n\n{response.text}")
        except Exception as e:
            await message.edit_text(f"❌ Error: {e}")
            
    elif len(message.command) > 1:
        text_to_translate = " ".join(message.command[1:])
        prompt = f"Translate the following text to {target_lang}. Output only translation:\n\n{text_to_translate}"
        try:
            response = await asyncio.to_thread(model.generate_content, prompt)
            await message.edit_text(response.text)
        except:
            pass
    else:
        await message.edit_text("⚠️ Reply or type text.")

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

@app.on_message(filters.me & filters.command("link", prefixes="."))
async def download_link_handler(client, message):
    if len(message.command) < 2: return await message.edit_text("❌ No URL.")
    url = message.command[1]
    await message.edit_text(f"🔍 `{url}`")
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
        with yt_dlp.YoutubeDL(ydl_opts) as ydl: await asyncio.to_thread(ydl.download, [url])
        files = glob.glob(f"{download_path}/*")
        if not files: return await message.edit_text("❌ Failed.")
        await message.edit_text("📤 Uploading...")
        await app.send_video(message.chat.id, video=files[0], caption=f"🔗 {url}", supports_streaming=True)
        await message.delete()
    except Exception as e:
        await message.edit_text(f"❌ Error: {e}")
        await asyncio.sleep(5)
        await message.delete()
    finally:
        if os.path.exists(download_path): shutil.rmtree(download_path)

@app.on_message(filters.me & filters.command("backup", prefixes="."))
async def backup_handler(client, message):
    chat_id = message.chat.id
    if chat_id in active_backups: return await message.edit_text("⚠️ Process active.")
    active_backups.add(chat_id)
    status_msg = await message.edit_text("⏳ Backup started... (.stop)")
    folder = f"backup_{chat_id}_{int(time.time())}"
    media_folder = os.path.join(folder, "media")
    os.makedirs(media_folder, exist_ok=True)
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
            if counter % 10 == 0: await status_msg.edit_text(f"⏳ {counter} msgs... (.stop)")
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
        with open(os.path.join(folder, "index.html"), "w", encoding="utf-8") as f: f.write(html)
        await status_msg.edit_text("🗜 Archiving...")
        shutil.make_archive(folder, 'zip', folder)
        await status_msg.edit_text("📤 Uploading...")
        await app.send_document("me", f"{folder}.zip", caption=f"📦 Backup {chat_id}" + (" (STOPPED)" if forced_stop else ""))
        await status_msg.edit_text("✅ Done." if not forced_stop else "🛑 Stopped.")
    except Exception as e: await status_msg.edit_text(f"❌ {e}")
    finally:
        if chat_id in active_backups: active_backups.remove(chat_id)
        if os.path.exists(folder): shutil.rmtree(folder)
        if os.path.exists(f"{folder}.zip"): os.remove(f"{folder}.zip")

@app.on_message(filters.me & filters.command("stats", prefixes="."))
async def stats_handler(client, message):
    conn = sqlite3.connect('userbot.db')
    c = conn.cursor()
    try:
        c.execute("SELECT COUNT(*) FROM messages WHERE type='incoming'")
        inc = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM messages WHERE type='mention'")
        mn = c.fetchone()[0]
        await message.edit_text(f"📊 **Stats**\n📩 Incoming: {inc}\n🔔 Mentions: {mn}")
    except: pass
    finally: conn.close()

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