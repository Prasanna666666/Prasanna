"""Programs that used to be called Orbit take over what they left: the data folder and the database file are renamed once, never copied or lost."""

from kit import db


def test_a_database_kept_under_the_old_name_is_taken_over(tmp_path, monkeypatch):
    monkeypatch.setenv("ATLAS_HOME", str(tmp_path))
    (tmp_path / "orbit.db").write_text("old data")
    (tmp_path / "orbit.db-wal").write_text("journal")
    db.adopt_old_name(tmp_path / "finance.db", tmp_path / "orbit.db")
    assert (tmp_path / "finance.db").read_text() == "old data" and (tmp_path / "finance.db-wal").exists() and not (tmp_path / "orbit.db").exists()


def test_a_new_database_is_never_replaced_by_an_old_one(tmp_path):
    (tmp_path / "orbit.db").write_text("old")
    (tmp_path / "finance.db").write_text("new")
    db.adopt_old_name(tmp_path / "finance.db", tmp_path / "orbit.db")
    assert (tmp_path / "finance.db").read_text() == "new" and (tmp_path / "orbit.db").read_text() == "old"


def test_the_old_data_folder_is_renamed_once(tmp_path, monkeypatch):
    monkeypatch.delenv("ATLAS_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".orbit").mkdir()
    (tmp_path / ".orbit" / "keep.txt").write_text("x")
    assert db.home() == tmp_path / ".atlas" and (tmp_path / ".atlas" / "keep.txt").read_text() == "x" and not (tmp_path / ".orbit").exists()


def test_a_deployed_service_without_the_platform_key_refuses_everything(monkeypatch):
    from kit import sign

    monkeypatch.delenv("PLATFORM_KEY", raising=False)
    monkeypatch.delenv("ATLAS_REQUIRE_SIGNATURE", raising=False)
    assert sign.valid("GET", "/api/x", None) is True  # a throwaway run checks nothing
    monkeypatch.setenv("ATLAS_REQUIRE_SIGNATURE", "1")
    assert sign.valid("GET", "/api/x", None) is False and sign.valid("GET", "/api/x", "1.abc") is False
    monkeypatch.setenv("PLATFORM_KEY", "k")
    header = sign.sign("GET", "/api/x")["X-Platform-Sig"]
    assert sign.valid("GET", "/api/x", header) is True and sign.valid("POST", "/api/x", header) is False


class _Said:
    def __init__(self, data):
        self.data = data

    def chat(self, model, messages, schema=None, **kw):
        import json

        return {"content": json.dumps(self.data)}


def test_health_details_keep_only_what_the_document_prints():
    from kit import extract

    text = "Uitslag bloedonderzoek 1 maart 2026. Hemoglobine 8,4 mmol/L (7,5 - 10,0). Cholesterol totaal 5,1 mmol/L. Metformine 500 mg 2 maal daags. Controle op 2026-06-01."
    said = {
        "values": [
            {"test": "Hemoglobine", "value": "8,4", "unit": "mmol/L", "range": "7,5 - 10,0"},
            {"test": "Cholesterol totaal", "value": "6,2", "unit": "mmol/L"},  # the model got the number wrong: not in the document
            {"test": "Ferritine", "value": "55", "unit": "ug/L"},  # a test the document does not mention
            {"test": "Cholesterol totaal", "value": "5,1", "unit": "mg/dL", "range": "3 - 5"},  # unit and range invented: dropped, value kept
        ],
        "medicines": [{"name": "Metformine", "dose": "500 mg", "duration": "6 maanden"}, {"name": "Aspirine", "dose": "100 mg"}],
        "follow_up": "2026-06-01",
    }
    out = extract.medical_details(_Said(said), "m", "bloed.pdf", text)
    assert [(v["test"], v["value"], v["number"], v["unit"], v["range"]) for v in out["values"]] == [
        ("Hemoglobine", "8,4", 8.4, "mmol/L", "7,5 - 10,0"),
        ("Cholesterol totaal", "5,1", 5.1, "", ""),
    ]
    assert out["medicines"] == [{"name": "Metformine", "dose": "500 mg", "duration": ""}]  # Aspirine is not in the document; the duration was invented
    assert out["follow_up"] == "2026-06-01"
    assert extract.medical_details(_Said({"follow_up": "2030-01-01"}), "m", "x", text)["follow_up"] is None  # a date the document does not write
