# SPDX-License-Identifier: AGPL-3.0-Only
# Copyright (C) 2023 Sean Anderson <seanga2@gmail.com>

import cocotb
from cocotb.binary import BinaryValue
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, Timer
from cocotb.utils import get_sim_time, get_sim_steps

from .axis_replay_buffer import send_packet

BAUD = 4e6
BIT_STEPS = get_sim_steps(1 / BAUD, 'sec', round_mode='round')

@cocotb.test(timeout_time=1, timeout_unit='ms')
async def test_tx(uart):
    uart.clk.value = BinaryValue('Z')
    uart.valid.value = 0
    uart.high_speed.value = BAUD == 4e6

    await Timer(1)
    await cocotb.start(Clock(uart.clk, 8, units='ns').start())
    await FallingEdge(uart.clk)

    msg = b"Hello"

    await cocotb.start(send_packet({
        'clk': uart.clk,
        'data': uart.data,
        'valid': uart.valid,
        'ready': uart.ready,
    }, msg))

    async def getchar():
        while not uart.tx.value:
            await FallingEdge(uart.clk)
        while uart.tx.value:
            await FallingEdge(uart.clk)
        await Timer(BIT_STEPS // 2)

        result = 0
        for _ in range(8):
            await Timer(BIT_STEPS)
            result >>= 1
            result |= 0x80 if uart.tx.value else 0

        return result

    then = get_sim_time()
    for c in msg:
        assert c == await getchar()
    now = get_sim_time()

    expected = BIT_STEPS * (10 * len(msg) - 1.5)
    actual = now - then
    assert abs(actual - expected) / expected < 0.01
