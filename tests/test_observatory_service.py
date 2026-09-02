from types import SimpleNamespace

from truepanel.web import service


def test_production_launcher_injects_observatory_snapshot(monkeypatch):
    settings = SimpleNamespace(
        host="127.0.0.1",
        port=8787,
        config_path="/tmp/truepanel.yaml",
        allow_config_writes=False,
    )
    monkeypatch.setattr(
        service.MissionControlServiceSettings,
        "from_environment",
        classmethod(lambda cls: settings),
    )

    loaded_config = {"loaded": "from configured path"}
    loaded_paths = []

    def load_config(path):
        loaded_paths.append(path)
        return loaded_config

    monkeypatch.setattr(service, "load_config", load_config)

    status_provider = object()
    monkeypatch.setattr(service, "ServiceStatusProvider", lambda: status_provider)

    plex_provider = object()
    monkeypatch.setattr(
        service,
        "activity_providers_from_environment",
        lambda: (plex_provider,),
    )

    created = {}
    snapshot_service = object()

    def build_snapshot(**kwargs):
        created.update(kwargs)
        return snapshot_service

    monkeypatch.setattr(service, "ObservatorySnapshotService", build_snapshot)

    served = {}
    monkeypatch.setattr(service, "serve", lambda **kwargs: served.update(kwargs))

    service.main()

    assert loaded_paths == [settings.config_path]
    assert created == {
        "service_status_provider": status_provider,
        "config": loaded_config,
        "activity_providers": (plex_provider,),
    }
    assert served == {
        "host": settings.host,
        "port": settings.port,
        "snapshot_service": snapshot_service,
        "allow_config_writes": False,
        "config_path": settings.config_path,
    }
