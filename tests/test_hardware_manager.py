import pytest

from truepanel.hardware import (
    A125Capabilities,
    A125Controller,
    Buzzer,
    EnclosureController,
    EnclosureSlot,
    HardwareManager,
)


class FakeController:
    pass


def test_hardware_package_exports():
    assert A125Capabilities is not None
    assert A125Controller is not None
    assert Buzzer is not None
    assert EnclosureController is not None
    assert EnclosureSlot is not None
    assert HardwareManager is not None


def test_manager_does_not_construct_hardware_eagerly():
    created = []

    def enclosure_factory():
        created.append("enclosure")
        return FakeController()

    def buzzer_factory():
        created.append("buzzer")
        return FakeController()

    def a125_factory():
        created.append("a125")
        return FakeController()

    manager = HardwareManager(
        enclosure_factory=enclosure_factory,
        buzzer_factory=buzzer_factory,
        a125_factory=a125_factory,
    )

    assert created == []
    assert manager.loaded() == ()
    assert manager.registered() == (
        "a125",
        "buzzer",
        "enclosure",
        "health",
        "inventory",
        "smart",
        "topology",
    )


def test_enclosure_is_created_on_first_access_and_cached():
    created = []

    def factory():
        controller = FakeController()
        created.append(controller)
        return controller

    manager = HardwareManager(enclosure_factory=factory)

    first = manager.enclosure
    second = manager.enclosure

    assert first is second
    assert created == [first]
    assert manager.is_loaded("enclosure") is True
    assert manager.loaded() == ("enclosure",)


def test_controllers_are_loaded_independently():
    calls = []

    manager = HardwareManager(
        enclosure_factory=lambda: calls.append("enclosure") or FakeController(),
        buzzer_factory=lambda: calls.append("buzzer") or FakeController(),
        a125_factory=lambda: calls.append("a125") or FakeController(),
    )

    manager.buzzer

    assert calls == ["buzzer"]
    assert manager.is_loaded("buzzer") is True
    assert manager.is_loaded("enclosure") is False
    assert manager.is_loaded("a125") is False


def test_lcd_and_a125_share_the_same_controller():
    controller = FakeController()
    manager = HardwareManager(a125_factory=lambda: controller)

    assert manager.lcd is controller
    assert manager.a125 is controller
    assert manager.loaded() == ("a125",)


def test_reset_one_controller_causes_recreation():
    created = []

    def factory():
        controller = FakeController()
        created.append(controller)
        return controller

    manager = HardwareManager(enclosure_factory=factory)

    first = manager.enclosure
    manager.reset("enclosure")
    second = manager.enclosure

    assert first is not second
    assert created == [first, second]


def test_reset_all_controllers():
    manager = HardwareManager(
        enclosure_factory=FakeController,
        buzzer_factory=FakeController,
        a125_factory=FakeController,
    )

    manager.enclosure
    manager.buzzer
    manager.a125

    assert manager.loaded() == ("a125", "buzzer", "enclosure")

    manager.reset()

    assert manager.loaded() == ()


def test_registers_custom_controller_lazily():
    created = []

    def fan_factory():
        created.append("fans")
        return FakeController()

    manager = HardwareManager()
    manager.register("fans", fan_factory)

    assert created == []
    assert "fans" in manager.registered()

    controller = manager.controller("fans")

    assert isinstance(controller, FakeController)
    assert created == ["fans"]
    assert manager.is_loaded("fans") is True


def test_register_rejects_duplicate_without_replace():
    manager = HardwareManager()

    with pytest.raises(
        ValueError,
        match="Hardware controller already registered: enclosure",
    ):
        manager.register("enclosure", FakeController)


def test_register_replace_discards_cached_instance():
    first = FakeController()
    second = FakeController()

    manager = HardwareManager(enclosure_factory=lambda: first)

    assert manager.enclosure is first

    manager.register(
        "enclosure",
        lambda: second,
        replace=True,
    )

    assert manager.is_loaded("enclosure") is False
    assert manager.enclosure is second


def test_register_validates_name_and_factory():
    manager = HardwareManager()

    with pytest.raises(
        ValueError,
        match="Hardware controller name cannot be empty",
    ):
        manager.register("", FakeController)

    with pytest.raises(
        TypeError,
        match="Hardware controller factory must be callable",
    ):
        manager.register("invalid", None)


def test_unknown_controller_raises_key_error():
    manager = HardwareManager()

    with pytest.raises(
        KeyError,
        match="Unknown hardware controller: warp_drive",
    ):
        manager.controller("warp_drive")

    with pytest.raises(
        KeyError,
        match="Unknown hardware controller: warp_drive",
    ):
        manager.reset("warp_drive")


def test_health_service_is_created_lazily():
    inventory = FakeController()
    smart = FakeController()
    health = FakeController()
    calls = []

    manager = HardwareManager(
        inventory_factory=lambda: calls.append("inventory") or inventory,
        smart_factory=lambda: calls.append("smart") or smart,
        health_factory=lambda: calls.append("health") or health,
    )

    assert calls == []
    assert manager.health is health
    assert calls == ["health"]
    assert manager.loaded() == ("health",)


def test_reset_inventory_discards_cached_health():
    inventory_count = 0
    health_count = 0

    def inventory_factory():
        nonlocal inventory_count
        inventory_count += 1
        return FakeController()

    def health_factory():
        nonlocal health_count
        health_count += 1
        return FakeController()

    manager = HardwareManager(
        inventory_factory=inventory_factory,
        health_factory=health_factory,
    )

    first = manager.health
    manager.reset("inventory")
    second = manager.health

    assert first is not second
    assert health_count == 2
