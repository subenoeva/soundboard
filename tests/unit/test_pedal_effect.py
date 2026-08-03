"""The adapter that puts a pedalboard plugin behind the Effect protocol."""

from __future__ import annotations

import numpy as np
import pytest
from pedalboard import Delay, Gain, Reverb

from soundboard.effects.params import ParamSpec
from soundboard.effects.pedal import PedalEffect


def _impulse(frames: int = 256) -> np.ndarray:
    block = np.zeros(frames, dtype=np.float32)
    block[0] = 1.0
    return block


def test_process_writes_the_result_back_into_the_block() -> None:
    effect = PedalEffect("gain", Gain(gain_db=6.0206))
    block = np.full(64, 0.25, dtype=np.float32)

    effect.process(block)

    # +6.02 dB is a factor of two exactly. The engine reads back the buffer it
    # passed in, so an adapter that returned a new array would change nothing.
    assert np.allclose(block, 0.5, atol=1e-4)


def _echo() -> PedalEffect:
    """A 480-frame echo: an impulse in one 256-frame block lands in the next one.

    Delay is the plugin that makes state visible at a block boundary. Reverb's
    would do too, but only from the fourth block onwards -- its wet signal starts
    after a pre-delay -- which says nothing extra and reads as arbitrary.
    """
    return PedalEffect("delay", Delay(delay_seconds=0.01, feedback=0.0, mix=0.5))


def test_state_carries_across_blocks() -> None:
    effect = _echo()
    effect.process(_impulse())
    tail = np.zeros(256, dtype=np.float32)

    effect.process(tail)

    # pedalboard resets a plugin on every process() call unless told otherwise,
    # which would drop the echo here -- along with the compressor's envelope and
    # every filter's history -- at each block boundary.
    assert np.max(np.abs(tail)) > 0.4


def test_reset_drops_the_tail() -> None:
    effect = _echo()
    effect.process(_impulse())

    effect.reset()
    tail = np.zeros(256, dtype=np.float32)
    effect.process(tail)

    # The echo was in flight and reset() threw it away, which is what a device
    # change or a stream restart needs: none of that state describes the new
    # signal.
    assert np.all(tail == 0.0)


def test_latency_is_zero_even_for_reverb() -> None:
    # The built-ins delay nothing: Reverb's 25 ms figure is pre-delay on the wet
    # signal alone and the dry path comes out at sample 0, so summing it into the
    # chain latency would show the user a delay nothing waits for.
    assert PedalEffect("reverb", Reverb()).latency_frames == 0


def _gain() -> PedalEffect:
    return PedalEffect(
        "gain",
        Gain(),
        (ParamSpec(name="gain_db", label="Gain", minimum=-24.0, maximum=24.0, default=0.0),),
    )


def test_set_param_reaches_the_plugin() -> None:
    effect = _gain()

    effect.set_param("gain_db", 6.0206)

    block = np.full(64, 0.25, dtype=np.float32)
    effect.process(block)
    assert np.allclose(block, 0.5, atol=1e-4)


def test_set_param_clamps_to_the_declared_range() -> None:
    effect = _gain()

    effect.set_param("gain_db", 400.0)

    # The value can come from a hand-edited effects.json as easily as from a
    # slider, and a plugin fed a value outside its range either throws or
    # distorts. The descriptor already states the bounds, so it enforces them.
    assert effect.params() == {"gain_db": 24.0}


def test_set_param_rejects_an_unknown_name() -> None:
    # Loudly, per AGENTS.md: a name that reaches setattr() with no descriptor
    # behind it would either bounce off the plugin or add a stray attribute, and
    # the slider would sit there doing nothing.
    with pytest.raises(KeyError, match="no parameter"):
        _gain().set_param("wetness", 0.5)


def test_the_descriptors_come_back_off_the_block() -> None:
    # The parameter panel reads them from here rather than from the registry,
    # because for a VST3 the registry has nothing to say: the plugin is the only
    # thing that knows what knobs it has.
    assert [spec.name for spec in _gain().param_specs()] == ["gain_db"]


def test_params_reports_what_the_plugin_currently_holds() -> None:
    effect = _gain()

    effect.set_param("gain_db", -3.0)

    # This is what persistence writes out, so it has to read back off the plugin
    # rather than from a copy the adapter keeps beside it.
    assert effect.params() == {"gain_db": pytest.approx(-3.0)}
