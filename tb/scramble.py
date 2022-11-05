# SPDX-License-Identifier: AGPL-3.0-Only
# Copyright (C) 2022 Sean Anderson <seanga2@gmail.com>

import itertools
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer

from .util import alist, ReverseList, print_list_at, compare_lists

threshold = 32

async def descramble(scrambled):
    consecutive = 0
    locked = False
    lfsr = ReverseList([0] * 11)
    async for s in scrambled:
        ldd = lfsr[8] ^ lfsr[10]

        if s ^ ldd:
            consecutive += 1
        else:
            consecutive = 0

        if consecutive >= threshold:
            locked = True

        if locked:
            yield s ^ ldd
            lfsr.append(ldd)
        else:
            lfsr.append(0 if s else 1)

@cocotb.test(timeout_time=10, timeout_unit='us')
async def test_scramble(scrambler):
    scrambler.unscrambled.value = 1
    await Timer(1)
    await cocotb.start(Clock(scrambler.clk, 8, units='ns').start())

    idles = threshold + 10
    ins = [1] * idles + [0] + [random.randrange(2) for _ in range(1000)]
    async def send():
        for bit in ins:
            await FallingEdge(scrambler.clk)
            scrambler.unscrambled.value = bit
    await cocotb.start(send())

    async def recv():
        for _ in ins:
            await RisingEdge(scrambler.clk)
            yield scrambler.scrambled.value

    compare_lists(ins[idles-1:], await alist(descramble(recv())))
