import pytest

from soundboard.cli import build_parser, parse_sound_argument


def test_parses_a_sound_assignment() -> None:
    key, path = parse_sound_argument("a=C:/clips/laugh.wav")

    assert key == "a"
    assert path == "C:/clips/laugh.wav"


def test_rejects_a_sound_argument_without_a_key() -> None:
    with pytest.raises(ValueError, match="KEY=PATH"):
        parse_sound_argument("laugh.wav")


def test_devices_subcommand_is_available() -> None:
    args = build_parser().parse_args(["devices"])

    assert args.command == "devices"


def test_run_subcommand_collects_sounds() -> None:
    args = build_parser().parse_args(
        ["run", "--mic", "realtek", "--out", "cable", "--sound", "a=x.wav", "--sound", "b=y.wav"]
    )

    assert args.mic == "realtek"
    assert args.out == "cable"
    assert args.sound == ["a=x.wav", "b=y.wav"]
