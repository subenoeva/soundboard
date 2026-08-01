"""What a knob is: enough about one parameter for the GUI to draw it.

Its own module rather than part of ``registry.py`` because both the registry and
the effects it builds need it, and putting it in either one makes the other import
in a circle.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ParamSpec:
    """One parameter of an effect: its bounds, its default and how to label it.

    The parameter panel is generated from these descriptors instead of being
    written per effect, which is the only reason an arbitrary VST3 -- whose
    parameters nobody here has ever seen -- can turn up with working sliders.
    """

    name: str
    """The attribute to set on the plugin, not the text the user reads."""

    label: str
    minimum: float
    maximum: float
    default: float
    unit: str = ""

    def clamp(self, value: float) -> float:
        """Pull ``value`` inside the declared range."""
        return min(max(value, self.minimum), self.maximum)
