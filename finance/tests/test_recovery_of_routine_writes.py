"""What the assistant adds at once (ROUTINE_WRITES) can be taken back: a person, task, note, event or date by `undo_last_additions` (the latest question's additions, prepared and then confirmed by the owner), and a person, task, note or event also by its own delete tool. Only a whole statement import has no single undo: its payments are removed one by one (O-7)."""

from finance import additions, toolrun
from finance.modules import tools as registry

JOURNALED = {"add_person", "add_task", "add_note", "create_event", "add_important_date"}
NO_UNDO = {"import_statements": "the payments are removed one by one (delete_transaction); there is no tool for a whole import"}
OWN_DELETE = {"add_person": "delete_person", "add_task": "delete_task", "add_note": "delete_note", "create_event": "delete_event"}


def test_every_routine_addition_is_journaled_for_undo_or_named_as_the_one_gap():
    assert JOURNALED | set(NO_UNDO) == set(toolrun.ROUTINE_WRITES)
    assert set(additions.TABLES) == JOURNALED


def test_undo_and_the_delete_tools_are_only_prepared_never_run_at_once():
    names = set(registry())
    for tool in [*OWN_DELETE.values(), "undo_last_additions"]:
        assert tool in names and tool in toolrun.STAGED and tool not in toolrun.ROUTINE_WRITES


def test_the_gap_is_real_so_the_documents_stay_honest():
    assert "delete_import" not in set(registry())
