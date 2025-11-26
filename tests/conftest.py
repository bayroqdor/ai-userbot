# tests/conftest.py
import sqlite3
import pytest

import main  # main.py dagi kodlar


@pytest.fixture(autouse=True)
def patch_sqlite_tmp_db(tmp_path, monkeypatch):
    """
    Barcha testlar uchun sqlite bazani vaqtinchalik faylga yo'naltiramiz:
    main.sqlite3.connect('userbot.db') -> tmp_path/'userbot.db'
    """
    db_path = tmp_path / "userbot.db"

    def _connect_override(*args, **kwargs):
        return sqlite3.connect(db_path)

    # main ichidagi sqlite3 modulining connect funksiyasini almashtiramiz
    monkeypatch.setattr(main.sqlite3, "connect", _connect_override)

    # Har bir test sessiyasi boshida jadval strukturasini yaratamiz
    main.init_db()
    yield


@pytest.fixture(autouse=True)
def patch_gemini(monkeypatch):
    """
    Google Gemini chaqiruvlarini mock qilamiz:
    - model.generate_content
    - genai.upload_file
    """
    class DummyResponse:
        def __init__(self, text):
            self.text = text

    def fake_generate_content(prompt, *args, **kwargs):
        # Promptni qisqa qilib qaytaramiz
        return DummyResponse(f"[FAKE_RESPONSE] {str(prompt)[:30]}")

    def fake_upload_file(path):
        # Oddiy string qaytaradigan stub
        return f"uploaded://{path}"

    monkeypatch.setattr(main.model, "generate_content", fake_generate_content)
    monkeypatch.setattr(main.genai, "upload_file", fake_upload_file)
    yield


@pytest.fixture
def fake_chat():
    class FakeChat:
        def __init__(self, chat_id=123, title="Test Chat"):
            self.id = chat_id
            self.title = title

    return FakeChat


@pytest.fixture
def fake_from_user():
    class FakeFromUser:
        def __init__(self, user_id=1, first_name="Tester", is_self=False):
            self.id = user_id
            self.first_name = first_name
            self.is_self = is_self

    return FakeFromUser


@pytest.fixture
def fake_message(fake_chat, fake_from_user):
    """
    Minimal Pyrogram Message o'rnini bosuvchi klass.
    Handlerlarda ishlatiladigan field/methodlarni qoplaydi.
    """
    from datetime import datetime

    class FakeMessage:
        def __init__(self, text="", command=None, chat=None, reply_to_message=None, from_user=None):
            self.id = 111
            self.text = text
            self.caption = None
            self.chat = chat or fake_chat()
            self.reply_to_message = reply_to_message
            self.from_user = from_user or fake_from_user()
            self.date = datetime.now()
            self._edited_text = None
            self._deleted = False
            # Pyrogram .command property o'rnini bosish
            self.command = command or []

        async def edit_text(self, new_text):
            self._edited_text = new_text
            self.text = new_text
            return self

        async def delete(self):
            self._deleted = True

    return FakeMessage


@pytest.fixture
def fake_client(monkeypatch, fake_chat):
    """
    Pyrogram Client o'rnini bosuvchi obyekt.
    Faqat testda kerak bo'ladigan metodlarni beradi.

    Eslatma: Handlerlar ichida ko'proq global main.app ishlatiladi,
    lekin bu fixture orqali kerak bo'lsa main.app metodlarini patch qilamiz.
    """
    class FakeClient:
        def __init__(self):
            self._sent_messages = []
            self._sent_docs = []
            self._sent_videos = []

        async def get_chat(self, target):
            return fake_chat(chat_id=999, title="Dest Chat")

        asy
