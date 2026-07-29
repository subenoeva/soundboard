"""Phase-1 command line: list devices and run the engine."""

from __future__ import annotations

import argparse
import sys

import sounddevice as sd
import soundfile as sf

from soundboard.audio.backend import AudioBackend
from soundboard.audio.engine import AudioEngine, EngineConfig
from soundboard.audio.portaudio import PortAudioBackend, find_device
from soundboard.audioio import load_mono_48k


def parse_sound_argument(value: str) -> tuple[str, str]:
    """Split a ``KEY=PATH`` assignment."""
    key, separator, path = value.partition("=")
    if not separator or not key or not path:
        raise ValueError(f"expected KEY=PATH, got {value!r}")
    return key, path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="soundboard")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("devices", help="list the audio devices PortAudio can see")

    run = subparsers.add_parser("run", help="run the engine and trigger clips from stdin")
    run.add_argument("--mic", required=True, help="substring of the physical microphone name")
    run.add_argument("--out", required=True, help="substring of the virtual cable input name")
    run.add_argument("--sound", action="append", default=[], metavar="KEY=PATH")
    run.add_argument("--blocksize", type=int, default=256)
    return parser


def _print_devices(backend: PortAudioBackend) -> int:
    for device in backend.list_devices():
        direction = []
        if device.max_input_channels:
            direction.append("in")
        if device.max_output_channels:
            direction.append("out")
        print(
            f"{device.index:3d}  {'/'.join(direction):7s}  [{device.hostapi}]  "
            f"{device.default_samplerate:.0f}Hz  {device.name}"
        )
    return 0


def _run(args: argparse.Namespace, backend: AudioBackend | None = None) -> int:
    if backend is None:
        backend = PortAudioBackend()

    try:
        devices = backend.list_devices()
        microphone = find_device(devices, args.mic, want_input=True)
        cable = find_device(devices, args.out, want_input=False)

        clips = {}
        for assignment in args.sound:
            key, path = parse_sound_argument(assignment)
            clips[key] = load_mono_48k(path)

        engine = AudioEngine(
            backend,
            EngineConfig(
                blocksize=args.blocksize,
                input_device=microphone.index,
                output_device=cable.index,
                output_channels=min(2, cable.max_output_channels) or 1,
            ),
        )
        engine.start()
    except (LookupError, OSError, sd.PortAudioError, sf.LibsndfileError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"microphone: {microphone.name}")
    print(f"output:     {cable.name}")
    print(f"keys:       {', '.join(sorted(clips)) or '(none)'}")
    print("type a key and press enter to play it; 'stop' to stop all; 'quit' to exit")

    try:
        for line in sys.stdin:
            command = line.strip()
            if command == "quit":
                break
            if command == "stop":
                engine.stop_all()
            elif command in clips:
                engine.play(clips[command])
            elif command:
                metrics = engine.metrics
                print(f"unknown key {command!r} | {metrics} | xruns={backend.xruns}")
    finally:
        engine.stop()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "devices":
        return _print_devices(PortAudioBackend())
    return _run(args)
