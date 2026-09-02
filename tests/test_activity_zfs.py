from truepanel.activity import (
    ActivityIntensity,
    ActivityProvider,
    ActivityProviderStatus,
    ActivityState,
    ZfsActivityProvider,
    normalize_zfs_activity,
)


def test_scrub_normalizes_existing_collector_evidence():
    observations = normalize_zfs_activity(
        {
            "scrub_running": True,
            "resilver_running": False,
            "percent": 42,
        }
    )

    assert len(observations) == 1
    scrub = observations[0]
    assert scrub.source == "zfs"
    assert scrub.kind == "zfs.scrub"
    assert scrub.state is ActivityState.ACTIVE
    assert scrub.intensity is ActivityIntensity.MODERATE
    assert scrub.progress == 0.42
    assert scrub.evidence == ("storage.zfs_activity.scrub_running",)


def test_resilver_is_high_intensity_recovery_activity():
    observations = normalize_zfs_activity(
        {
            "scrub_running": False,
            "resilver_running": True,
            "percent": 75.5,
        }
    )

    assert len(observations) == 1
    resilver = observations[0]
    assert resilver.kind == "zfs.resilver"
    assert resilver.intensity is ActivityIntensity.HIGH
    assert resilver.progress == 0.755
    assert resilver.evidence == ("storage.zfs_activity.resilver_running",)


def test_simultaneous_operations_preserve_progress_uncertainty():
    observations = normalize_zfs_activity(
        {
            "scrub_running": True,
            "resilver_running": True,
            "percent": 50,
        }
    )

    assert {item.kind for item in observations} == {
        "zfs.scrub",
        "zfs.resilver",
    }
    assert all(item.progress is None for item in observations)


def test_inactive_zfs_evidence_does_not_invent_activity():
    assert normalize_zfs_activity(
        {
            "scrub_running": False,
            "resilver_running": False,
            "percent": 100,
        }
    ) == ()


def test_only_exact_boolean_true_can_assert_activity():
    assert normalize_zfs_activity(
        {
            "scrub_running": "true",
            "resilver_running": 1,
        }
    ) == ()


def test_invalid_progress_is_unknown_instead_of_clamped():
    for value in (-1, 101, float("inf"), "not-a-number", True):
        observations = normalize_zfs_activity(
            {
                "scrub_running": True,
                "percent": value,
            }
        )
        assert observations[0].progress is None


def test_raw_zpool_status_text_never_enters_normalized_payload():
    secret = "pool-name-that-must-not-leak"
    observations = normalize_zfs_activity(
        {
            "scrub_running": True,
            "percent": 12,
            "status_line": f"scan: scrub in progress on {secret}",
            "remaining": f"{secret}: 1h to go",
            "problem_line": f"{secret}: DEGRADED",
        }
    )

    payload = observations[0].as_dict()
    assert secret not in repr(payload)
    assert "status_line" not in repr(payload)
    assert "remaining" not in repr(payload)


def test_provider_reports_available_when_existing_evidence_is_readable():
    provider = ZfsActivityProvider(
        lambda: {
            "scrub_running": True,
            "resilver_running": False,
            "percent": 10,
        }
    )

    assert isinstance(provider, ActivityProvider)
    snapshot = provider.snapshot()
    assert snapshot.status is ActivityProviderStatus.AVAILABLE
    assert snapshot.observations[0].kind == "zfs.scrub"


def test_provider_source_failure_isolated_as_unavailable():
    sensitive = "do-not-leak-this-path"

    def broken_reader():
        raise RuntimeError(sensitive)

    snapshot = ZfsActivityProvider(broken_reader).snapshot()

    assert snapshot.status is ActivityProviderStatus.UNAVAILABLE
    assert snapshot.observations == ()
    assert sensitive not in repr(snapshot.as_dict())


def test_provider_rejects_non_mapping_source_without_propagating_error():
    snapshot = ZfsActivityProvider(lambda: None).snapshot()

    assert snapshot.status is ActivityProviderStatus.UNAVAILABLE
    assert snapshot.observations == ()
