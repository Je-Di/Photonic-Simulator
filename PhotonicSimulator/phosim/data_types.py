from __future__ import annotations

from typing import NamedTuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .components import Component


class OpticalPower(dict):
    """
    Optical power is stored as a dictionary with one power value for every wavelength.
    This class extends the builtin dictionary by the following features:
        - __getitem__ returns 0 instead of raising an error when a key (=wavelength) is not present.
        - +, -, *, / operators are implemented.
    """
    def __getitem__(self, key):
        if key not in self.keys():
            return 0
        return super().__getitem__(key)

    def __add__(self, rhs):
        ret = self.copy()
        for wavelength in rhs.keys():
            ret[wavelength] += rhs[wavelength]
        return ret

    def __sub__(self, rhs):
        ret = self.copy()
        for wavelength in rhs.keys():
            ret[wavelength] -= rhs[wavelength]
        return ret

    def __mul__(self, scalar):
        ret = self.copy()
        for wavelength in ret.keys():
            ret[wavelength] *= scalar
        return ret

    def __truediv__(self, scalar):
        ret = self.copy()
        for wavelength in ret.keys():
            ret[wavelength] /= scalar
        return ret

    def copy(self):
        return OpticalPower(super().copy())


class IntRange(NamedTuple):
    min: int
    max: int

    def in_range(self, value: int) -> bool:
        return self.min == -1 or value >= self.min and self.max == -1 or value <= self.max


class ConnectionEndpoint(NamedTuple):
    component: Component
    port_id: int = 0
