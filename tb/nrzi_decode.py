# SPDX-License-Identifier: AGPL-3.0-Only
# Copyright (C) 2022 Sean Anderson <seanga2@gmail.com>

import random

import cocotb
from cocotb.clock import Clock
from cocotb.regression import TestFactory
from cocotb.triggers import ClockCycles, FallingEdge, RisingEdge, Timer
from cocotb.types import LogicArray

from .nrzi_encode import nrzi_encode
from .util import alist, async_iter, compare_lists, timeout, send_recovered_bits, with_valids, print_list_at

async def nrzi_decode(bits):
    last = 1
    async for bit in bits:
        yield bit ^ last
        last = bit

@timeout(10, 'us')
async def test_rx(decoder, valids):
    decoder.nrzi_valid.value = 0
    decoder.nrzi.value = LogicArray('XX')
    decoder.rst.value = 1
    await Timer(1)
    await cocotb.start(Clock(decoder.clk, 8, units='ns').start())
    await ClockCycles(decoder.clk, 1)
    decoder.rst.value = 0

    ins = [random.randrange(2) for _ in range(1000)]
    await cocotb.start(send_recovered_bits(decoder.clk, decoder.nrzi,
                                           decoder.nrzi_valid, ins, valids))

    outs = []
    await RisingEdge(decoder.clk)
    for _ in ins:
        await RisingEdge(decoder.clk)
        valid = decoder.nrz_valid.value
        if valid == 0:
            pass
        elif valid == 1:
            outs.append(decoder.nrz[1].value)
        else:
            outs.append(decoder.nrz[1].value)
            outs.append(decoder.nrz[0].value)

    # Ignore the first bit, since it is influenced by the initial value
    compare_lists((await alist(nrzi_decode(async_iter(ins))))[1:], outs)

with_valids(globals(), test_rx)
