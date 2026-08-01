"""The catalogue of built-in blocks: what the palette offers and how it builds it."""

from __future__ import annotations

import numpy as np
import pytest

from soundboard.effects.registry import BUILT_INS, create


def test_create_builds_the_requested_kind() -> None:
    effect = create("gain")

    assert effect.kind == "gain"


def test_create_applies_the_declared_defaults() -> None:
    effect = create("compressor")

    # A freshly dropped block has to be usable on a voice straight away, so the
    # defaults are the registry's rather than pedalboard's -- pedalboard ships
    # ratio 1.0, which is a compressor that does nothing.
    assert effect.params()["ratio"] == pytest.approx(3.0)


def test_create_overrides_the_defaults_it_is_given() -> None:
    effect = create("gain", {"gain_db": -6.0})

    assert effect.params()["gain_db"] == pytest.approx(-6.0)


def test_create_rejects_an_unknown_kind() -> None:
    with pytest.raises(KeyError, match="unknown effect"):
        create("flanger")


def test_create_rejects_a_parameter_the_block_does_not_have() -> None:
    # effects.json is written by us but edited by whoever wants to, and a key that
    # matches nothing would silently do nothing at all.
    with pytest.raises(KeyError, match="no parameter"):
        create("gain", {"gian_db": -6.0})


@pytest.mark.parametrize("kind", list(BUILT_INS))
def test_every_built_in_processes_a_block(kind: str) -> None:
    effect = create(kind)
    block = np.linspace(-0.5, 0.5, 256, dtype=np.float32)

    effect.process(block)

    # Catches a descriptor whose name does not match the plugin's attribute, and
    # a default the plugin refuses, which are the two ways this table rots.
    assert block.shape == (256,)
    assert np.all(np.isfinite(block))


@pytest.mark.parametrize("kind", list(BUILT_INS))
def test_every_default_sits_inside_its_declared_range(kind: str) -> None:
    for spec in BUILT_INS[kind].params:
        # The slider is drawn from minimum/maximum: a default outside them would
        # come up pinned to an end and jump the moment the user touched it.
        assert spec.minimum <= spec.default <= spec.maximum, spec.name
