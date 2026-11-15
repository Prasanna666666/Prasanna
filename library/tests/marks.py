"""Test fixtures only: which declared app a file of a given kind (as these tests name them) is marked for. In the app itself the model marks each file; nothing in the code maps a kind to an app."""

APPS_OF = {
    **{kind: ["finance"] for kind in ("invoice", "receipt", "payslip", "bank_statement", "annual_statement", "tax", "insurance", "contract")},
    **{kind: ["travel"] for kind in ("ticket", "booking")},
    "medical": ["health"],
}
