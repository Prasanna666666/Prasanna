"""What the assistant adds at once (ROUTINE_WRITES) can be taken back, but only through the delete tools, which it may only prepare and the owner confirms. There is no general undo (O-7). This test fixes, tool by tool, which delete tool takes each addition back, and names the two additions for which there is no tool that removes exactly what was added."""

from finance import toolrun
from finance.modules import tools as registry

TAKEN_BACK_BY = {
    "add_person": "delete_person",
    "add_task": "delete_task",
    "add_note": "delete_note",
    "create_event": "delete_event",
}
NO_EXACT_REMOVAL = {
    "add_important_date": "a date is removed only together with its person (delete_person)",
    "import_statements": "the payments are removed one by one (delete_transaction); there is no tool for a whole import",
}


def test_every_routine_addition_is_either_taken_back_by_a_prepared_delete_or_named_as_a_gap():
    assert set(TAKEN_BACK_BY) | set(NO_EXACT_REMOVAL) == set(toolrun.ROUTINE_WRITES)


def test_the_delete_tools_exist_and_are_only_prepared_never_run_at_once():
    names = set(registry())
    for delete in TAKEN_BACK_BY.values():
        assert delete in names
        assert delete in toolrun.STAGED and delete not in toolrun.ROUTINE_WRITES


def test_the_gaps_are_real_so_the_documents_stay_honest():
    names = set(registry())
    assert "delete_important_date" not in names and "delete_import" not in names
