"""What a knob is: enough about one parameter for the GUI to draw it.

Its own module rather than part of ``registry.py`` because both the registry and
the effects it builds need it, and putting it in either one makes the other import
in a circle.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ParamValue = float | bool | str
ParamType = Literal["float", "bool", "choice"]


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
    default: ParamValue
    unit: str = ""
    type: ParamType = "float"
    choices: tuple[str, ...] = ()

    def clamp(self, value: float) -> float:
        """Pull ``value`` inside the declared range."""
        return min(max(value, self.minimum), self.maximum)

    def coerce(self, value: ParamValue) -> ParamValue:
        """Validate a value from QML or JSON against the descriptor."""
        if self.type == "float":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{self.name!r} expects a number")
            return self.clamp(float(value))
        if self.type == "bool":
            if not isinstance(value, bool):
                raise TypeError(f"{self.name!r} expects a boolean")
            return value
        if not isinstance(value, str) or value not in self.choices:
            raise ValueError(f"{self.name!r} expects one of {self.choices!r}")
        return value
