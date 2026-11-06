"""Search over everything that was read: the best passage first with where it is from, the index kept up to date, and no query ever breaks it."""

from kit import rag as kit_rag

from library import store


def add_doc(conn, name, text):
    conn.execute("INSERT INTO documents (sha256, name, kind, text) VALUES (?,?,?,?)", (name, name, "pdf", text))
    conn.commit()


def retrieve(conn, question, alternatives=None):
    return store.passages(conn, question, 6, alternatives)


def test_the_best_passage_comes_first_and_says_where_it_is_from(conn):
    add_doc(conn, "ziggo-march.pdf", "Ziggo internet and television invoice for March, total 62.50 euro, customer number 4412.")
    add_doc(conn, "rent.pdf", "Rental agreement: the monthly rent is 1150 euro and is due on the first of each month.")
    hits = retrieve(conn, "what is the monthly rent?")
    assert hits[0]["title"] == "rent.pdf" and hits[0]["source"] == "document" and "rent" in hits[0]["text"].lower()
    assert retrieve(conn, "the and for") == []  # nothing but filler words: nothing to search for


def test_the_index_is_updated_only_for_what_changed_and_forgets_deleted_items(conn):
    add_doc(conn, "a.pdf", "alpha beta gamma delta")
    add_doc(conn, "b.pdf", "epsilon zeta eta theta")
    assert kit_rag.reindex(conn, store._sources) == 2
    assert kit_rag.reindex(conn, store._sources) == 0  # nothing changed
    conn.execute("UPDATE documents SET text='iota kappa lambda' WHERE name='a.pdf'")
    assert kit_rag.reindex(conn, store._sources) == 1
    assert retrieve(conn, "kappa") and not retrieve(conn, "alpha")
    conn.execute("DELETE FROM documents WHERE name='b.pdf'")
    conn.commit()
    kit_rag.reindex(conn, store._sources)
    assert not retrieve(conn, "epsilon")


def test_quotes_and_operators_in_a_question_never_break_the_search(conn):
    add_doc(conn, "a.pdf", "the café bill was 12.50 for two coffees")
    assert retrieve(conn, 'what was the "café" bill AND OR NOT ( * ?')  # must not raise
    assert retrieve(conn, "12.50")


def test_without_full_text_search_a_word_match_still_finds_the_passage(conn, monkeypatch):
    add_doc(conn, "rent.pdf", "Rental agreement: the monthly rent is 1150 euro.")
    monkeypatch.setattr(kit_rag, "_fts", lambda c: False)
    assert kit_rag.reindex(conn, store._sources) == 0
    hits = retrieve(conn, "monthly rent")
    assert hits and hits[0]["title"] == "rent.pdf"


def test_longer_words_also_match_their_other_endings(conn):
    add_doc(conn, "ziggo.pdf", "Ziggo invoiced 62.50 euro for internet in March")
    assert retrieve(conn, "invoices")[0]["title"] == "ziggo.pdf"  # "invoices" finds "invoiced"


def test_other_phrasings_find_what_the_first_wording_misses_and_agreement_ranks_first(conn):
    add_doc(conn, "polis.pdf", "Autoverzekering polis: de dekking is allrisk met een eigen risico van 250 euro")
    add_doc(conn, "ziggo.pdf", "Ziggo invoice for internet and television, total 62.50 euro")
    assert retrieve(conn, "what does my car insurance cover") == []  # the English words are not in the Dutch policy
    hits = retrieve(conn, "what does my car insurance cover", ["autoverzekering dekking", "polis eigen risico"])
    assert hits and hits[0]["title"] == "polis.pdf"
