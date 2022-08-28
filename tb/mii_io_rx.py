# SPDX-License-Identifier: AGPL-3.0-Only
# Copyright (C) 2022 Sean Anderson <seanga2@gmail.com>

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, Edge, FallingEdge, First, RisingEdge, Timer
from cocotb.types import LogicArray

from .util import ClockEnable

@cocotb.test(timeout_time=500, timeout_unit='ns')
async def test_io(io):
    io.isolate.value = 0
    io.ce.value = 0
    io.valid.value = LogicArray('X')
    io.err.value = LogicArray('X')
    io.data.value = LogicArray('X' * 4)
    await Timer(1)
    await cocotb.start(Clock(io.clk, 8, units='ns').start())
    await ClockCycles(io.clk, 1)

    async def clock_monitor():
        await FallingEdge(io.rx_clk)
        fall = cocotb.utils.get_sim_time('ns')
        while True:
            await RisingEdge(io.rx_clk)
            rise = cocotb.utils.get_sim_time('ns')
            assert round(rise - fall) == 20
            await FallingEdge(io.rx_clk)
            fall = cocotb.utils.get_sim_time('ns')
            high = round(fall - rise)
            assert high >= 12 and high <= 28
    await cocotb.start(clock_monitor())

    async def send_datum(valid, err, data, delay, early=True):
        if early:
            await Timer(1)
        io.valid.value = valid
        io.err.value = err
        io.data.value = data
        io.ce.value = 1
        await ClockCycles(io.clk, 2 if early else 1, False)
        io.ce.value = 0
        io.valid.value = LogicArray('X')
        io.err.value = LogicArray('X')
        io.data.value = LogicArray('X' * 4)
        await ClockCycles(io.clk, delay - 1, early)

    async def send_data():
        await send_datum(1, 0, 1, 5, True)
        await send_datum(0, 1, 2, 4, True)
        await send_datum(1, 0, 3, 5, True)
        await send_datum(0, 1, 4, 6, True)
        await send_datum(1, 0, 5, 5, True)
        await FallingEdge(io.clk)
        await send_datum(0, 1, 6, 5, False)
        await send_datum(1, 0, 7, 4, False)
        await send_datum(0, 1, 8, 5, False)
        await send_datum(1, 0, 9, 6, False)
        await send_datum(0, 1, 10, 5, False)
    await cocotb.start(send_data())

    async def recv_datum(valid, err, data):
        await RisingEdge(io.rx_clk)
        assert io.rx_dv.value == valid
        assert io.rx_er.value == err
        assert io.rxd.value == data

    await RisingEdge(io.rx_clk)
    await recv_datum(1, 0, 1)
    await recv_datum(0, 1, 2)
    await recv_datum(1, 0, 3)
    await recv_datum(0, 1, 4)
    await recv_datum(1, 0, 5)
    await recv_datum(0, 1, 6)
    await recv_datum(1, 0, 7)
    await recv_datum(0, 1, 8)
    await recv_datum(1, 0, 9)
    await recv_datum(0, 1, 10)

    io.isolate.value = 1
    await FallingEdge(io.clk)
    assert io.rx_clk.value.binstr == 'z'
    assert io.rx_dv.value.binstr == 'z'
    assert io.rx_er.value.binstr == 'z'
    assert io.rxd.value.binstr == 'zzzz'
