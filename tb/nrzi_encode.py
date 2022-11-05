# SPDX-License-Identifier: AGPL-3.0-Only
# Copyright (C) 2022 Sean Anderson <seanga2@gmail.com>

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer

from .util import compare_lists

def nrzi_encode(bits):
    last = 1
    for bit in bits:
        yield (last := last ^ bit)

@cocotb.test(timeout_time=100, timeout_unit='us')
async def test_encode(encoder):
    ins = [random.randrange(2) for _ in range(1000)]
    encoder.nrz.value = ins[0]
    await Timer(1)
    await cocotb.start(Clock(encoder.clk, 8, units='ns').start())

    async def send_nrz():
        for bit in ins:
            await FallingEdge(encoder.clk)
            encoder.nrz.value = bit
    await cocotb.start(send_nrz())

    outs = []
    await RisingEdge(encoder.clk)
    await RisingEdge(encoder.clk)
    for _ in ins:
        await RisingEdge(encoder.clk)
        outs.append(encoder.nrzi.value)

    # Ignore the first bit, since it is influenced by the initial value
    compare_lists(list(nrzi_encode(ins[1:])), outs[1:])
