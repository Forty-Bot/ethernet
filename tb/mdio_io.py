# SPDX-License-Identifier: AGPL-3.0-Only
# Copyright (C) 2022 Sean Anderson <seanga2@gmail.com>

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, Edge, FallingEdge, First, RisingEdge, Timer
from cocotb.types import LogicArray

@cocotb.test(timeout_time=50, timeout_unit='us')
async def test_io(io):
    io.mdc.value = 0
    io.mdo_valid.value = 0
    await Timer(1)
    await cocotb.start(Clock(io.clk, 8, units='ns').start())
    # random phase
    await Timer(random.randrange(1, 9), units='ns')
    await cocotb.start(Clock(io.mdc, 400, units='ns').start())

    ins = [random.randrange(2) for _ in range(10)]
    await FallingEdge(io.mdc)

    async def send_ins():
        for bit in ins:
            await Timer(190, 'ns')
            io.mdio.value = bit
            await Timer(20, 'ns')
            io.mdio.value = LogicArray('X')
            await FallingEdge(io.mdc)
    await cocotb.start(send_ins())

    for bit in ins:
        while not io.ce.value:
            await RisingEdge(io.clk)
        assert io.mdi.value == bit
        await FallingEdge(io.clk)

    outs = [random.randrange(2) for _ in range(10)]
    io.mdio.value = LogicArray('Z')
    await FallingEdge(io.clk)
    for bit in outs:
        io.mdo.value = bit
        io.mdo_valid.value = 1
        await FallingEdge(io.clk)
        assert io.mdio_oe.value
        await FallingEdge(io.clk)
        await FallingEdge(io.clk)
        assert io.mdio.value == bit
        io.mdo_valid.value = 0
        await FallingEdge(io.clk)
        assert io.mdio.value.binstr == 'z'
