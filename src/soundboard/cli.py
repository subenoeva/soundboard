"""Command line: device listing, engine control, and the Supabase sound library."""

from __future__ import annotations

import argparse
import getpass
import sys
from collections.abc import Callable
from pathlib import Path

import numpy as np
import platformdirs

from soundboard.audio.backend import AudioBackend
from soundboard.audio.engine import AudioEngine, EngineConfig
from soundboard.audio.portaudio import PortAudioBackend, find_device
from soundboard.audioio import load_mono_48k
from soundboard.library.cache import SoundCache
from soundboard.remote import auth, categories, sounds
from soundboard.remote.client import SessionStore, build_client
from soundboard.remote.models import RemoteClient


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
    run.add_argument(
        "--sound", action="append", default=[], metavar="KEY=PATH-OR-ID-OR-NAME"
    )
    run.add_argument("--blocksize", type=int, default=256)

    auth_parser = subparsers.add_parser("auth", help="manage your Supabase session")
    auth_sub = auth_parser.add_subparsers(dest="auth_command", required=True)
    signup = auth_sub.add_parser("signup")
    signup.add_argument("--email", required=True)
    login = auth_sub.add_parser("login")
    login.add_argument("--email", required=True)
    auth_sub.add_parser("logout")
    auth_sub.add_parser("whoami")

    sounds_parser = subparsers.add_parser("sounds", help="manage the shared sound library")
    sounds_sub = sounds_parser.add_subparsers(dest="sounds_command", required=True)
    add = sounds_sub.add_parser("add")
    add.add_argument("path")
    add.add_argument("--name", required=True)
    add.add_argument("--category")
    listing = sounds_sub.add_parser("list")
    listing.add_argument("--mine", action="store_true")
    listing.add_argument("--category")
    edit = sounds_sub.add_parser("edit")
    edit.add_argument("id")
    edit.add_argument("--name")
    edit.add_argument("--category")
    edit.add_argument("--gain-db", type=float)
    edit.add_argument("--trim-start", type=int)
    edit.add_argument("--trim-end", type=int)
    edit.add_argument("--loop", dest="loop", action="store_true")
    edit.add_argument("--no-loop", dest="loop", action="store_false")
    edit.set_defaults(loop=None)
    rm = sounds_sub.add_parser("rm")
    rm.add_argument("id")

    categories_parser = subparsers.add_parser("categories", help="manage shared categories")
    categories_sub = categories_parser.add_subparsers(dest="categories_command", required=True)
    cat_add = categories_sub.add_parser("add")
    cat_add.add_argument("name")
    cat_add.add_argument("--color")
    categories_sub.add_parser("list")
    cat_rm = categories_sub.add_parser("rm")
    cat_rm.add_argument("name")

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


def _resolve_sound_pcm(
    value: str, remote_client: RemoteClient | None, cache: SoundCache | None
) -> np.ndarray:
    if Path(value).exists():
        return load_mono_48k(value)

    client = remote_client if remote_client is not None else build_client()
    active_cache = cache if cache is not None else SoundCache(_default_cache_dir())
    sound = sounds.find_sound_by_name(client, value)
    if sound is None:
        sound = sounds.get_sound(client, value)
    return sounds.resolve_pcm(client, active_cache, sound)


def _default_cache_dir() -> Path:
    return Path(platformdirs.user_cache_dir("soundboard")) / "pcm"


def _run(
    args: argparse.Namespace,
    backend: AudioBackend | None = None,
    remote_client: RemoteClient | None = None,
    cache: SoundCache | None = None,
) -> int:
    if backend is None:
        backend = PortAudioBackend()

    try:
        devices = backend.list_devices()
        microphone = find_device(devices, args.mic, want_input=True)
        cable = find_device(devices, args.out, want_input=False)

        clips = {}
        for assignment in args.sound:
            key, value = parse_sound_argument(assignment)
            clips[key] = _resolve_sound_pcm(value, remote_client, cache)

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
    except Exception as exc:  # CLI boundary: report cleanly, see _auth
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


def _auth(
    args: argparse.Namespace,
    client: RemoteClient | None = None,
    store: SessionStore | None = None,
    password_prompt: Callable[[], str] | None = None,
    display_name_prompt: Callable[[], str] | None = None,
) -> int:
    client = client if client is not None else build_client()
    store = store if store is not None else SessionStore()
    password_prompt = password_prompt or (lambda: getpass.getpass("password: "))
    display_name_prompt = display_name_prompt or (lambda: input("display name: "))

    try:
        if args.auth_command == "signup":
            auth.sign_up(client, args.email, password_prompt())
            print(f"signed up as {args.email}; check your email to confirm before logging in")
        elif args.auth_command == "login":
            session = auth.log_in(
                client, store, args.email, password_prompt(), display_name_prompt
            )
            print(f"logged in as {session.email}")
        elif args.auth_command == "logout":
            auth.log_out(client, store)
            print("logged out")
        elif args.auth_command == "whoami":
            loaded_session = store.load()
            if loaded_session is None:
                print("error: no session; run `soundboard auth login`", file=sys.stderr)
                return 1
            print(loaded_session.email)
        return 0
    except Exception as exc:  # CLI boundary: always report, never crash silently
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _sounds(
    args: argparse.Namespace, client: RemoteClient | None = None, store: SessionStore | None = None
) -> int:
    client = client if client is not None else build_client()
    store = store if store is not None else SessionStore()

    try:
        if args.sounds_command == "add":
            session = auth.require_session(client, store)
            category_id = None
            if args.category:
                category_id = categories.add_category(client, session, args.category).id
            sound = sounds.add_sound(
                client, session, args.path, name=args.name, category_id=category_id
            )
            print(f"added {sound.name!r} ({sound.id})")
        elif args.sounds_command == "list":
            session = auth.require_session(client, store)
            owner_id = session.user_id if args.mine else None
            category_id = None
            if args.category:
                matches = [c for c in categories.list_categories(client) if c.name == args.category]
                category_id = matches[0].id if matches else "__none__"
            names = auth.display_names(client, [s.owner_id for s in sounds.list_sounds(client)])
            for sound in sounds.list_sounds(client, owner_id=owner_id, category_id=category_id):
                owner_name = names.get(sound.owner_id, sound.owner_id)
                print(f"{sound.id}  {sound.name!r}  by {owner_name}")
        elif args.sounds_command == "edit":
            session = auth.require_session(client, store)
            fields: dict[str, object] = {}
            if args.name is not None:
                fields["name"] = args.name
            if args.gain_db is not None:
                fields["gain_db"] = args.gain_db
            if args.trim_start is not None:
                fields["trim_start_frames"] = args.trim_start
            if args.trim_end is not None:
                fields["trim_end_frames"] = args.trim_end
            if args.loop is not None:
                fields["loop"] = args.loop
            if args.category is not None:
                fields["category_id"] = categories.add_category(client, session, args.category).id
            sound = sounds.edit_sound(client, args.id, **fields)
            print(f"updated {sound.name!r}")
        elif args.sounds_command == "rm":
            auth.require_session(client, store)
            sounds.remove_sound(client, args.id)
            print("removed")
        return 0
    except Exception as exc:  # CLI boundary: report cleanly, see _auth
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _categories(
    args: argparse.Namespace, client: RemoteClient | None = None, store: SessionStore | None = None
) -> int:
    client = client if client is not None else build_client()
    store = store if store is not None else SessionStore()

    try:
        if args.categories_command == "add":
            session = auth.require_session(client, store)
            category = categories.add_category(client, session, args.name, color=args.color)
            print(f"added {category.name!r} ({category.id})")
        elif args.categories_command == "list":
            auth.require_session(client, store)
            for category in categories.list_categories(client):
                print(f"{category.id}  {category.name}")
        elif args.categories_command == "rm":
            auth.require_session(client, store)
            categories.remove_category(client, args.name)
            print("removed")
        return 0
    except Exception as exc:  # CLI boundary: report cleanly, see _auth
        print(f"error: {exc}", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "devices":
        return _print_devices(PortAudioBackend())
    if args.command == "run":
        return _run(args)
    if args.command == "auth":
        return _auth(args)
    if args.command == "sounds":
        return _sounds(args)
    if args.command == "categories":
        return _categories(args)
    raise AssertionError(f"unhandled command {args.command!r}")  # argparse guarantees a match
