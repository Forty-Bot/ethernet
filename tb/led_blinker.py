# SPDX-License-Identifier: AGPL-3.0-Only
# Copyright (C) 2023 Sean Anderson <seanga2@gmail.com>

import cocotb
from cocotb.binary import BinaryValue
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, Timer

from .util import BIT

@cocotb.test(timeout_time=1, timeout_unit='us')
async def test_elastic(led):
    led.clk.value = BinaryValue('Z')
    led.triggers.value = 0
    led.test_mode.value = 1

    await Timer(1)
    await cocotb.start(Clock(led.clk, 2, units='ns').start())

    await FallingEdge(led.clk)
    assert not led.out.value

    led.triggers.value = 1
    await FallingEdge(led.clk)
    assert not led.out.value

    led.triggers.value = 0
    while not led.out.value:
        await FallingEdge(led.clk)
    assert led.out.value == 1

    led.triggers.value = 1
    await FallingEdge(led.clk)

    led.triggers.value = 0
    await ClockCycles(led.clk, 16, False)
    led.triggers.value = 2

    await FallingEdge(led.clk)
    assert not led.out.value
    while not led.out.value:
        await FallingEdge(led.clk)
    assert led.out.value == 2
