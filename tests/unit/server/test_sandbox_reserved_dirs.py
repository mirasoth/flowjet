"""Contract: sandbox push/pull skip the reserved workspace names.

`.soothe` is the single private framework namespace (the sync-engine twin
test lives in the soothe and soothe-nano repos); the sandbox must neither
push it into the guest nor pull guest-written `.soothe/**` back to the host.
"""

from flowjet.core.sandbox.arbox import _PULL_SKIP_DIRS, _PUSH_SKIP_DIRS


def test_reserved_namespace_is_skipped_in_both_directions() -> None:
    assert ".soothe" in _PUSH_SKIP_DIRS
    assert ".soothe" in _PULL_SKIP_DIRS


def test_push_and_pull_skip_sets_are_symmetric() -> None:
    assert _PUSH_SKIP_DIRS == _PULL_SKIP_DIRS
