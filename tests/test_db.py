# tests/test_db.py
import sqlite3
import main


def test_set_and_get_setting():
    main.set_setting("dest_channel", "12345")
    value = main.get_setting("dest_channel")
    assert value == "12345"


def test_add_and_get_all_sources():
    main.add_source_channel(1001, "Source 1")
    main.add_source_channel(1002, "Source 2")

    sources = main.get_all_sources()
    assert 1001 in sources
    assert 1002 in sources


def test_remove_source_channel():
    main.add_source_channel(1001, "Source 1")
    main.remove_source_channel(1001)

    sources = main.get_all_sources()
    assert 1001 not in sources


def test_log_message_inserts_row(fake_message):
    fake_msg = fake_message(text="Hello")
    main.log_message(fake_msg, "out")

    conn = sqlite3.connect("userbot.db")
    c = conn.cursor()
    c.execute("SELECT text, type FROM messages")
    rows = c.fetchall()
    conn.close()

    assert len(rows) == 1
    assert rows[0][0] == "Hello"
    assert rows[0][1] == "out"
