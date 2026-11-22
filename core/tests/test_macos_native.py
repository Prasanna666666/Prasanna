"""Checks that only mean something against the real operating system: they run on a macOS runner and are skipped everywhere else.

They use the real `security` tool and the real Keychain, with service names that carry a random suffix and are deleted afterwards, so they touch nothing of the owner's.
"""

from __future__ import annotations

import subprocess
import sys
import uuid

import pytest

from atlas_core.designation import AnchorRecord
from atlas_core.macos import KeychainAnchor, KeychainError, KeychainItems
from atlas_core.tasks import KeychainKeyProvider

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="needs the real macOS Keychain")


@pytest.fixture
def items():
    made: list[str] = []
    box = KeychainItems()
    yield box, made
    for service in made:
        box.delete(service)


def test_a_value_written_to_the_real_keychain_reads_back_and_deletes(items):
    box, made = items
    service = f"atlas-ci-{uuid.uuid4().hex}"
    made.append(service)
    assert box.read(service) is None
    value = "v" * 64 + " with spaces and 'quotes' and $dollars"
    box.write(service, value)
    assert box.read(service) == value
    box.write(service, "second")  # -U updates in place
    assert box.read(service) == "second"
    box.delete(service)
    assert box.read(service) is None
    box.delete(service)  # deleting what is not there is not an error


def test_a_store_key_is_created_once_256_bits_and_stays_the_same(items):
    box, made = items
    name = f"ci-{uuid.uuid4().hex}"
    made.append(f"atlas-{name}")
    first = box.secret(name)
    assert len(first) == 64 and int(first, 16) >= 0
    assert box.secret(name) == first
    assert KeychainItems().secret(name) == first  # a new object (a restart) sees the same key


def test_the_value_never_appears_in_the_process_list_while_it_is_stored(items):
    box, made = items
    service = f"atlas-ci-{uuid.uuid4().hex}"
    made.append(service)
    sentinel = "SENTINEL-" + uuid.uuid4().hex
    box.write(service, sentinel)
    listing = subprocess.run(["/bin/ps", "-axww", "-o", "command="], capture_output=True, text=True, check=False).stdout
    assert sentinel not in listing


def test_the_designation_anchor_round_trips_through_the_real_keychain_and_survives_a_restart(items):
    box, made = items
    made.append(KeychainAnchor.SERVICE)
    box.delete(KeychainAnchor.SERVICE)
    anchor = KeychainAnchor(box)
    assert anchor._load() is None
    record = AnchorRecord(7, "ab" * 32, None)
    anchor._save(record)
    assert KeychainAnchor(KeychainItems())._load() == record
    anchor._save(None)
    assert KeychainAnchor(KeychainItems())._load() is None


def test_the_task_store_key_provider_provisions_reads_and_never_replaces_the_real_item():
    provider = KeychainKeyProvider()
    items = KeychainItems()
    try:
        items.delete("atlas-task-key")
        with pytest.raises(Exception, match="not been provisioned"):
            provider.get()
        assert provider.provision() is True
        key = provider.get()
        assert len(key) == 64
        assert provider.provision() is False  # never replaces an existing key
        assert provider.get() == key
    finally:
        items.delete("atlas-task-key")


def test_an_unreadable_keychain_fails_closed_with_no_output_of_the_tool():
    box = KeychainItems(account="x", runner=lambda *a, **k: subprocess.CompletedProcess(a, 36, "SECRET-OUTPUT", "SECRET-ERROR"))
    with pytest.raises(KeychainError) as e:
        box.read("atlas-anything")
    assert "SECRET" not in str(e.value)
