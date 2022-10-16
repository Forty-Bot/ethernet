# SPDX-License-Identifier: AGPL-3.0-Only
# Copyright (C) 2022 Sean Anderson <seanga2@gmail.com>

import itertools
import random

import cocotb
from cocotb.clock import Clock
from cocotb.regression import TestFactory
from cocotb.result import SimTimeoutError
from cocotb.triggers import ClockCycles, FallingEdge, RisingEdge, Timer, with_timeout

from .util import compare_lists, send_recovered_bits, timeout, with_valids

def scramble(bits):
    lfsr = random.randrange(1, 0x7ff)
    for bit in bits:
        ldd = (lfsr >> 10) ^ ((lfsr >> 8) & 1)
        yield bit ^ ldd
        lfsr <<= 1
        lfsr &= 0x7ff
        lfsr |= ldd

async def send_scrambled(descrambler, data, valids):
    descrambler.signal_status.value = 1
    await send_recovered_bits(descrambler.clk, descrambler.scrambled,
                              descrambler.scrambled_valid, scramble(data), valids)
    descrambler.signal_status.value = 0

@timeout(10, 'us')
async def test_unlock(descrambler, valids):
    descrambler.signal_status.value = 0
    descrambler.scrambled_valid.value = 0
    descrambler.test_mode.value = 1
    await Timer(1)
    await cocotb.start(Clock(descrambler.clk, 8, units='ns').start())

    await cocotb.start(send_scrambled(descrambler,
        itertools.chain(itertools.repeat(1, 60),
                        itertools.repeat(0, 625//2),
                        itertools.repeat(1, 29),
                        itertools.repeat(0)),
        valids))

    await ClockCycles(descrambler.clk, 60)
    assert descrambler.locked.value
    try:
        await with_timeout(FallingEdge(descrambler.locked), 6, 'us')
    except SimTimeoutError:
        pass
    else:
        assert False
    await FallingEdge(descrambler.locked)

with_valids(globals(), test_unlock)

@timeout(10, 'us')
async def test_descramble(descrambler, valids):
    descrambler.signal_status.value = 0
    descrambler.scrambled_valid.value = 0
    descrambler.test_mode.value = 0
    await Timer(1)
    await cocotb.start(Clock(descrambler.clk, 8, units='ns').start())

    ins = [1] * 60 + [0] + [random.randrange(2) for _ in range(1000)]
    await cocotb.start(send_scrambled(descrambler, ins, valids))

    outs = []
    await RisingEdge(descrambler.locked)
    while descrambler.locked.value:
        await RisingEdge(descrambler.clk)
        valid = descrambler.descrambled_valid.value
        if valid == 0:
            pass
        elif valid == 1:
            outs.append(descrambler.descrambled[1].value)
        else:
            outs.append(descrambler.descrambled[1].value)
            outs.append(descrambler.descrambled[0].value)

    best_corr = -1
    best_off = None
    for off in range(28, 42):
        corr = sum(i == o for i, o in zip(ins[off:], outs))
        if corr > best_corr:
            best_corr = corr
            best_off = off

    print(f"best offset is {best_off} correlation {best_corr/(len(ins) - best_off)}")
    compare_lists(ins[best_off:], outs)

with_valids(globals(), test_descramble)
