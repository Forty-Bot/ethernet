# SPDX-License-Identifier: AGPL-3.0-Only
# Copyright (C) 2022 Sean Anderson <seanga2@gmail.com>

import enum
import itertools

from .util import classproperty

class Code(enum.Enum):
    _0 = (0b11110, '0')
    _1 = (0b01001, '1')
    _2 = (0b10100, '2')
    _3 = (0b10101, '3')
    _4 = (0b01010, '4')
    _5 = (0b01011, '5')
    _6 = (0b01110, '6')
    _7 = (0b01111, '7')
    _8 = (0b10010, '8')
    _9 = (0b10011, '9')
    _A = (0b10110, 'A')
    _B = (0b10111, 'B')
    _C = (0b11010, 'C')
    _D = (0b11011, 'D')
    _E = (0b11100, 'E')
    _F = (0b11101, 'F')
    _I = (0b11111, 'I')
    _J = (0b11000, 'J')
    _K = (0b10001, 'K')
    _T = (0b01101, 'T')
    _R = (0b00111, 'R')
    _H = (0b00100, 'H')
    _V0 = (0b00000, 'V')
    _V1 = (0b00001, 'V')
    _V2 = (0b00010, 'V')
    _V3 = (0b00011, 'V')
    _V4 = (0b00101, 'V')
    _V5 = (0b00110, 'V')
    _V6 = (0b01000, 'V')
    _V7 = (0b01100, 'V')
    _V8 = (0b10000, 'V')
    _V9 = (0b11001, 'V')

    @classmethod
    def _missing_(cls, value):
        return cls.__members__['_' + value]

    @classmethod
    def decode(cls, bits):
        value = 0
        for bit in bits:
            value = (value << 1) | bit
        return cls(value)

    @classproperty
    def encode(cls):
        if not hasattr(cls, '_encode'):
            cls._encode = { data: cls(f"{data:X}") for data in range(16) }
        return cls._encode

    def __new__(cls, code, name):
        self = object.__new__(cls)
        self._value_ = code
        return self

    def __init__(self, code, name):
        self._name_ = name
        try:
            self.data = int(name, 16)
        except ValueError:
            self.data = None

    def __hash__(self):
        return hash(self.value)

    def __int__(self):
        if self.data is None:
            raise ValueError
        return self.data

    def __index__(self):
        return self._value_

    def __repr__(self):
        return f"{self.__class__.__name__}({self._value_:#07b}, '{self.name}')"

    def __str__(self):
        return f"/{self._name_}/"

    def __iter__(self):
        code = self.value
        for _ in range(5):
            yield (code & 0x10) >> 4
            code <<= 1

def as_nibbles(data):
    for byte in data:
       yield byte >> 4
       yield byte & 0xf
