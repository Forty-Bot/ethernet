# SPDX-License-Identifier: AGPL-3.0-Only
# Copyright (C) 2022 Sean Anderson <seanga2@gmail.com>

import functools
import random

import cocotb
from cocotb.result import SimTimeoutError
from cocotb.triggers import with_timeout, FallingEdge
from cocotb.types import LogicArray

async def alist(xs):
    return [x async for x in xs]

# From https://stackoverflow.com/a/7864317/5086505
class classproperty(property):
    def __get__(self, cls, owner):
        return classmethod(self.fget).__get__(None, owner)()

class timeout:
    def __init__(self, time, unit):
        self.time = time
        self.unit = unit

    def __call__(self, f):
        coro = cocotb.coroutine(f)

        @functools.wraps(f)
        async def wrapped(*args, **kwargs):
            r = coro(*args, **kwargs)
            try:
                return await with_timeout(r, self.time, self.unit)
            except SimTimeoutError:
                r.kill()
                raise
        return wrapped

class ReverseList(list):
    def __init__(self, iterable=None):
        super().__init__(reversed(iterable) if iterable is not None else None)

    @staticmethod
    def _slice(key):
        start = -1 - key.start if key.start else None
        stop = -key.stop if key.stop else None
        return slice(start, stop, key.step)

    def __getitem__(self, key):
        if isinstance(key, slice):
            return ReverseList(super().__getitem__(self._slice(key)))
        return super().__getitem__(-1 - key)

    def __setitem__(self, key, value):
        if isinstance(key, slice):
            super().__setitem__(self._slice(key), value)
        else:
            super().__setitem__(-1 - key, value)

    def __delitem__(self, key):
        if isinstance(key, slice):
            super().__delitem__(self._slice(key))
        else:
            super().__delitem__(-1 - key)

    def __reversed__(self):
        return super().__iter__()

    def __iter__(self):
        return super().__reversed__()

def one_valid():
    return 1

def two_valid():
    return 2

def rand_valid():
    return random.randrange(3)

class saw_valid:
    def __init__(self):
        self.last = 0
        # Lie for TestFactory
        self.__qualname__ = self.__class__.__qualname__

    def __call__(self):
        self.last += 1
        if self.last > 2:
            self.last = 0
        return self.last

async def send_recovered_bits(clk, data, valid, bits, valids):
    await FallingEdge(clk)
    try:
        while True:
            v = valids()
            valid.value = v
            if v == 0:
                d = 'XX'
            elif v == 1:
                d = (next(bits), 'X')
            else:
                first = next(bits)
                try:
                    second = next(bits)
                except StopIteration:
                    second = 'X'
                d = (first, second)
            data.value = LogicArray(d)
            await FallingEdge(clk)
    except StopIteration:
        pass
