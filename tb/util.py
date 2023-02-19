# SPDX-License-Identifier: AGPL-3.0-Only
# Copyright (C) 2022 Sean Anderson <seanga2@gmail.com>

import functools
import random

import cocotb
from cocotb.result import SimTimeoutError
from cocotb.triggers import ClockCycles, FallingEdge, with_timeout
from cocotb.types import LogicArray

async def alist(xs):
    return [x async for x in xs]

async def async_iter(it):
    for i in it:
        yield i

def BIT(n):
    return 1 << n

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

def with_valids(g, f):
    for valids in (one_valid, two_valid, rand_valid, saw_valid()):
        async def test(*args, valids=valids, **kwargs):
            await f(*args, valids=valids, **kwargs)
        test.__name__ = f"{f.__name__}_{valids.__qualname__}"
        test.__qualname__ = f"{f.__qualname__}_{valids.__qualname__}"
        test.valids = valids
        g[test.__name__] = cocotb.test()(test)

async def send_recovered_bits(clk, data, valid, bits, valids):
    bits = iter(bits)
    await FallingEdge(clk)
    try:
        while True:
            v = valids()
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
                    v = 1
                d = (first, second)
            data.value = LogicArray(d)
            valid.value = v
            await FallingEdge(clk)
    except StopIteration:
        pass

def print_list_at(l, i):
    print(' ' * max(50 - i, 0), *l[max(i - 50, 0):i+50], sep='')

def compare_lists(ins, outs):
    assert outs
    for idx, (i, o) in enumerate(zip(ins, outs)):
        if i != o:
            print(idx)
            print_list_at(ins, idx)
            print_list_at(outs, idx)
            assert False, "Differring bit"

async def ClockEnable(clk, ce, ratio):
    ce.value = 1
    if ratio == 1:
        return

    while True:
        await ClockCycles(clk, 1, False)
        ce.value = 0
        await ClockCycles(clk, ratio - 1, False)
        ce.value = 1

# Adapted from https://stackoverflow.com/a/1630350/5086505
def lookahead(it):
    it = iter(it)
    last = next(it)
    for val in it:
        yield last, False
        last = val
    yield last, True
