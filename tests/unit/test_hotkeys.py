import pytest

from soundboard.hotkeys import FakeHotkeyManager, PynputHotkeyManager


def test_fake_hotkey_manager_triggers_the_registered_callback() -> None:
    manager = FakeHotkeyManager()
    calls = []
    manager.register("<ctrl>+<alt>+1", lambda: calls.append(1))

    manager.trigger("<ctrl>+<alt>+1")

    assert calls == [1]


def test_fake_hotkey_manager_forgets_an_unregistered_combo() -> None:
    manager = FakeHotkeyManager()
    manager.register("<ctrl>+<alt>+1", lambda: None)

    manager.unregister("<ctrl>+<alt>+1")

    with pytest.raises(KeyError):
        manager.trigger("<ctrl>+<alt>+1")


def test_fake_hotkey_manager_rejects_a_malformed_combo() -> None:
    manager = FakeHotkeyManager()

    with pytest.raises(ValueError):
        manager.register("not-a-real-combo!!", lambda: None)


def test_pynput_hotkey_manager_rejects_a_malformed_combo_without_touching_the_os() -> None:
    # Validation happens before the OS-level listener is (re)started, so this is safe
    # to run anywhere, unlike a successful `register` — see the `display`-marked test.
    manager = PynputHotkeyManager()

    with pytest.raises(ValueError):
        manager.register("not-a-real-combo!!", lambda: None)


@pytest.mark.display
def test_pynput_hotkey_manager_starts_a_real_listener_on_success() -> None:
    manager = PynputHotkeyManager()
    try:
        manager.register("<ctrl>+<alt>+9", lambda: None)
        assert manager._listener is not None
    finally:
        manager.stop()
