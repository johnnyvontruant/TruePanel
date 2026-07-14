from truepanel.lab.session_manager import session_service


def test_returns_same_instance():
    assert session_service() is session_service()


def test_session_manager_can_start_session():
    service = session_service()

    # Clean up from any previous test.
    if (
        service.current_session() is not None
        and service.current_session().active
    ):
        service.stop_session()

    session = service.start_session()

    assert session.active

    summary = service.stop_session()

    assert summary.commands == 0

