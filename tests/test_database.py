def test_verbs_seeded(db):
    verbs = db.get_verbs()
    assert len(verbs) > 100
    assert any(v.v1 == "go" and v.v2 == "went" and v.v3 == "gone" for v in verbs)


def test_word_crud_and_duplicates(db):
    wid = db.add_word("  Cat ", " кіт ", "/kæt/", "A cat")
    assert db.word_exists("cat") and not db.word_exists("cat", exclude_id=wid)
    db.update_word(wid, "kitten", "кошеня", "", "")
    w = db.get_words()[0]
    assert (w.english, w.ukrainian) == ("kitten", "кошеня")
    db.delete_word(wid)
    assert db.get_words() == []


def test_stats_streak_and_delete_cleanup(db):
    wid = db.add_word("cat", "кіт")
    db.record_answer("word", wid, True, "en2uk")
    db.record_answer("word", wid, True, "quiz")
    st = db.get_stats("word")[wid]
    assert (st.correct, st.wrong, st.streak, st.accuracy) == (2, 0, 2, 100)
    db.record_answer("word", wid, False, "quiz")
    st = db.get_stats("word")[wid]
    assert (st.correct, st.wrong, st.streak) == (2, 1, 0)
    assert db.overall_stats() == (2, 1)
    db.delete_word(wid)
    assert wid not in db.get_stats("word")


def test_settings_roundtrip(db):
    assert db.get_setting("k", "d") == "d"
    db.set_setting("k", "v1")
    db.set_setting("k", "v2")
    assert db.get_setting("k") == "v2"
