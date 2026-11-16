"""An app's concepts are decided by the model once per kind and never by a word fixed in code."""

import json
import sqlite3

from kit import concepts

CONCEPTS = {"invoice": "a request for payment", "bank statement": "a list of payments in and out of an account", "payslip": "one salary payment"}


def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(concepts.MIGRATION)
    return conn


class Model:
    def __init__(self):
        self.asked = []

    def chat(self, model, messages, schema=None, **kw):
        names = messages[-1]["content"].split("Names:\n")[1].split("\n")
        self.asked += names
        answer = {"rekeningafschrift": "bank statement", "rechnung": "invoice", "loonstrook": "payslip", "holiday photo": "", "made up": "spaceship"}
        return {"content": json.dumps({"names": [{"given": n, "concept": answer.get(n, "")} for n in names]})}


def test_many_wordings_in_many_languages_mean_the_apps_concepts_and_each_is_decided_once():
    conn, model = db(), Model()
    kinds = ["Rekeningafschrift", "Bank statement", "bank_statement", "Rechnung", "Loonstrook", "Holiday photo", "made up", "Rechnung"]
    assert concepts.resolve(conn, model, "m", CONCEPTS, kinds) == 5  # the three that are a concept's own name need no model
    assert sorted(model.asked) == ["holiday photo", "loonstrook", "made up", "rechnung", "rekeningafschrift"]
    assert concepts.concept_of(conn, CONCEPTS, "Bank statement (Dutch)") == ""  # not decided yet
    assert (
        concepts.concept_of(conn, CONCEPTS, "Rekeningafschrift") == "bank statement"
        and concepts.concept_of(conn, CONCEPTS, "bank_statement") == "bank statement"
    )
    assert (
        concepts.concept_of(conn, CONCEPTS, "made up") == "" and concepts.concept_of(conn, CONCEPTS, "Holiday photo") == ""
    )  # a name that is no concept is none
    assert concepts.kinds_of(conn, CONCEPTS, "bank statement") == ["bank statement", "bank_statement", "rekeningafschrift"]
    assert concepts.resolve(conn, model, "m", CONCEPTS, kinds) == 0 and len(model.asked) == 5  # nothing is asked twice
