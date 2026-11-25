import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytestmark = pytest.mark.gui


@pytest.fixture
def window(populated_db):
    from PySide6.QtWidgets import QApplication

    from app.ui.main_window import MainWindow
    from app.ui.styles import STYLESHEET

    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(STYLESHEET)
    win = MainWindow(populated_db)
    yield win
    win.close()


def test_all_pages_open(window):
    for i in range(5):
        window.go_to(i)


def test_add_search_and_full_test_session(window):
    wp = window.words_page
    wp.in_en.setText("bird"); wp.in_uk.setText("птах"); wp.add_word()
    assert wp.table.rowCount() == 6
    wp.search.setText("пт")
    assert wp.table.rowCount() == 1

    window.go_to(3)
    setup = window.test_page.setup
    setup.audio_cb.setChecked(False)
    setup._select_all()
    assert setup.spin.value() == 6
    setup._start()
    sess = window.test_page.session
    while window.test_page.stack.currentWidget() is sess:
        q = sess.questions[sess.index]
        if q.choices:
            sess._on_choice(q.correct_choice)
        else:
            for edit, f in zip(sess._inputs, q.fields):
                edit.setText(f.display)
            sess._on_primary()
        sess._on_primary()
    assert window.test_page.results.score.text().startswith("6 / 6")


def test_speaking_page_starts_topic_and_guided_reply(window, populated_db):
    populated_db.set_setting("lt_consent", "1")
    populated_db.set_setting("use_lt", "0")
    populated_db.set_setting("ollama_url", "http://127.0.0.1:9")
    page = window.speaking_page
    page.audio_cb.setChecked(False)
    page.new_topic()
    assert page.partner is not None and page.topic is not None
