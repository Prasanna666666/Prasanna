"""The layers of the app, kept by tests so they cannot drift back.

1. One common layer (`kit`) holds everything the apps share; it knows no app. An app (`library`, `finance`, `atlas`, `images`) imports the common layer and never another app; apps talk to
   each other over HTTP, not through code.
2. No code decides by a word the model happened to use for a kind of file. An app declares the concepts it needs in its own config and asks for those (`kit.concepts`); a word like
   "invoice" compared with `kind` in code is the old way and fails here."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APPS = ("library", "finance", "atlas", "images")
ALLOWED_APP_IMPORTS = {"kit": set(), "library": {"kit", "images"}, "finance": {"kit"}, "atlas": {"kit"}, "images": {"kit"}}


def sources(package: str):
    return list((ROOT / package / "src").rglob("*.py"))


def test_the_common_layer_knows_no_app_and_no_app_imports_another():
    for package, allowed in ALLOWED_APP_IMPORTS.items():
        for path in sources(package):
            for line in path.read_text().splitlines():
                match = re.match(r"\s*(?:from|import)\s+(kit|library|finance|atlas|images)\b", line)
                if match and match[1] != package:
                    assert match[1] in allowed, f"{path.relative_to(ROOT)} imports {match[1]}: {line.strip()}"


KIND_WORDS = "invoice|receipt|payslip|tax|insurance|contract|ticket|booking|bank_statement|bank statement|annual_statement|annual statement|medical|passport|prescription|lab report"
DECIDES_BY_A_WORD = re.compile(rf"""\bkind\b["']?[\])]*\s*(?:==|!=|=|IN|NOT IN|in|not in)\s*\(?\s*['"]({KIND_WORDS})['"]""")


def test_no_code_decides_by_a_word_the_model_used_for_a_kind_of_file():
    found = []
    for package in ("kit", *APPS):
        for path in sources(package):
            for number, line in enumerate(path.read_text().splitlines(), 1):
                if (
                    DECIDES_BY_A_WORD.search(line) and not line.lstrip().startswith("#") and "concepts.of(" not in line
                ):  # a concept compared with a concept is fine
                    found.append(f"{path.relative_to(ROOT)}:{number}: {line.strip()[:110]}")
    assert not found, "decided by a kind word, not by a concept:\n" + "\n".join(found)


JS_DECIDES_BY_A_WORD = re.compile(rf"""\.kind\s*(?:===|!==)\s*['"]({KIND_WORDS})['"]""")


def test_no_page_decides_by_a_word_the_model_used_for_a_kind_of_file():
    found = []
    for package in APPS:
        for path in (ROOT / package / "src").rglob("*.js"):
            for number, line in enumerate(path.read_text().splitlines(), 1):
                if JS_DECIDES_BY_A_WORD.search(line):
                    found.append(f"{path.relative_to(ROOT)}:{number}: {line.strip()[:110]}")
    assert not found, "a page decides by a kind word, not by a concept:\n" + "\n".join(found)
