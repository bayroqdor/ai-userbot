# tests/test_handlers.py
import pytest
import sqlite3
from datetime import datetime

import main


# -------------------------------
#  TARJIMA HANDLERI (.tr / .uz /.en /.ru)
# -------------------------------

@pytest.mark.asyncio
async def test_translation_tr_inline(fake_client, fake_message):
    """
    .tr en Hello world
    cmd='tr', lang_code='en', inline matn
    """
    msg = fake_message(
        text=".tr en Hello world",
        command=["tr", "en", "Hello", "world"]
    )

    await main.translation_handler(fake_client, msg)

    # patch_gemini fixtureimiz [FAKE_RESPONSE] ... qaytaryapti
    assert msg._edited_text.startswith("[FAKE_RESPONSE]")


@pytest.mark.asyncio
async def test_translation_tr_reply(fake_client, fake_message):
    """
    .tr en  reply holati
    """
    reply_msg = fake_message(text="Salom dunyo")
    msg = fake_message(
        text=".tr en",
        command=["tr", "en"],
        reply_to_message=reply_msg
    )

    await main.translation_handler(fake_client, msg)

    assert msg._edited_text.startswith("🌍 **EN:**")
    assert "[FAKE_RESPONSE]" in msg._edited_text


@pytest.mark.asyncio
async def test_translation_tr_no_lang(fake_client, fake_message):
    """
    .tr  (lang_code yo'q)
    """
    msg = fake_message(
        text=".tr",
        command=["tr"]
    )

    await main.translation_handler(fake_client, msg)

    assert "⚠️ Kod yozing" in msg._edited_text


@pytest.mark.asyncio
async def test_translation_uz_inline(fake_client, fake_message):
    """
    .uz Salom dunyo
    cmd='uz', lang_code='uz', inline matn
    """
    msg = fake_message(
        text=".uz Salom dunyo",
        command=["uz", "Salom", "dunyo"]
    )

    await main.translation_handler(fake_client, msg)

    assert msg._edited_text.startswith("[FAKE_RESPONSE]")


@pytest.mark.asyncio
async def test_translation_uz_no_text_no_reply(fake_client, fake_message):
    """
    .uz  (matn yo'q, reply yo'q)
    """
    msg = fake_message(
        text=".uz",
        command=["uz"]
    )

    await main.translation_handler(fake_client, msg)

    # Foydalanuvchiga namuna ko'rsatadi
    assert "Namuna:" in msg._edited_text


# -------------------------------
#  QISQA (.qisqa)
# -------------------------------

@pytest.mark.asyncio
async def test_qisqa_handler_ok(fake_client, fake_message):
    reply_msg = fake_message(text="Bu juda uzun matn bo'lishi mumkin...")
    msg = fake_message(text=".qisqa", command=["qisqa"], reply_to_message=reply_msg)

    await main.summarize_handler(fake_client, msg)

    assert msg._edited_text.startswith("📌 **Qisqa:**")
    assert "[FAKE_RESPONSE]" in msg._edited_text


@pytest.mark.asyncio
async def test_qisqa_handler_no_text(fake_client, fake_message):
    msg = fake_message(text=".qisqa", command=["qisqa"], reply_to_message=None)

    await main.summarize_handler(fake_client, msg)
    assert "❌ Matn yo'q." in msg._edited_text


# -------------------------------
#  SETTINGS HANDLERLAR
# -------------------------------

@pytest.mark.asyncio
async def test_set_dest_handler_on(fake_client, fake_message, monkeypatch):
    """
    .setdest @channel  -> app.get_chat chaqiriladi va dest_channel DBga yoziladi.
    """
    async def fake_get_chat(target):
        class FakeChat:
            id = 555
            title = "Dest Channel"
        return FakeChat()

    monkeypatch.setattr(main.app, "get_chat", fake_get_chat)

    msg = fake_message(
        text=".setdest @channel",
        command=["setdest", "@channel"]
    )

    await main.set_dest_handler(fake_client, msg)

    val = main.get_setting("dest_channel")
    assert val == "555"
    assert "✅ Qabul" in msg._edited_text


@pytest.mark.asyncio
async def test_set_dest_handler_off(fake_client, fake_message):
    msg = fake_message(
        text=".setdest off",
        command=["setdest", "off"]
    )

    await main.set_dest_handler(fake_client, msg)

    val = main.get_setting("dest_channel")
    assert val == "off"
    assert "O'chirildi" in msg._edited_text


@pytest.mark.asyncio
async def test_addsource_and_listsources(fake_client, fake_message):
    """
    .addsource va .listsources kombinatsiyasi
    """
    msg_add = fake_message(
        text=".addsource",
        command=["addsource"]
    )
    await main.add_source_handler(fake_client, msg_add)

    msg_list = fake_message(
        text=".listsources",
        command=["listsources"]
    )
    await main.list_sources_handler(fake_client, msg_list)

    assert "📋 **Manbalar:**" in msg_list._edited_text
    assert "Test Chat" in msg_list._edited_text  # fake_chat title


@pytest.mark.asyncio
async def test_delsource(fake_client, fake_message):
    """
    .delsource handleri DBdan o'chirayotganini tekshirish
    """
    main.add_source_channel(123, "Source Chat")

    msg = fake_message(
        text=".delsource",
        command=["delsource"]
    )
    await main.del_source_handler(fake_client, msg)

    sources = main.get_all_sources()
    assert 123 not in sources
    assert "Olib tashlandi" in msg._edited_text


# -------------------------------
#  STATS (.stats)
# -------------------------------

@pytest.mark.asyncio
async def test_stats_handler(fake_client, fake_message):
    """
    .stats loglar sonini chiqaradi
    """
    class DummyMsg:
        def __init__(self, text):
            from datetime import datetime
            self.text = text
            self.caption = None
            self.date = datetime.now()
            self.chat = type("C", (), {"id": 1})
            self.from_user = type("U", (), {"id": 1})

    main.log_message(DummyMsg("Hello 1"), "in")
    main.log_message(DummyMsg("Hello 2"), "out")

    msg = fake_message(
        text=".stats",
        command=["stats"]
    )

    await main.stats_handler(fake_client, msg)

    assert "📊 Jami loglar: 2" in msg._edited_text


# -------------------------------
#  STOP HANDLER (.stop)
# -------------------------------

@pytest.mark.asyncio
async def test_stop_handler(fake_client, fake_message):
    """
    .stop active_backups to'plamidan chat_id ni olib tashlaydi
    """
    chat_id = 999
    main.active_backups.add(chat_id)

    msg = fake_message(
        text=".stop",
        command=["stop"],
        chat=type("C", (), {"id": chat_id, "title": "Test Chat"})
    )

    await main.stop_handler(fake_client, msg)

    assert chat_id not in main.active_backups
    assert "To'xtatildi" in msg._edited_text
