# SPDX-License-Identifier: AGPL-3.0-Only
# Copyright (C) 2023 Sean Anderson <seanga2@gmail.com>

import cocotb
from cocotb.binary import BinaryValue
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, Timer
from cocotb.utils import get_sim_time, get_sim_steps

from .axis_replay_buffer import recv_packet

BAUD = 4e6
BIT_STEPS = get_sim_steps(1 / BAUD, 'sec', round_mode='round')

def as_bits(c):
    for _ in range(8):
        yield c & 1
        c >>= 1

async def putchar(rx, c):
    for bit in (0, *as_bits(c), 1):
        rx.value = bit
        await Timer(BIT_STEPS)

@cocotb.test(timeout_time=1, timeout_unit='ms')
async def test_rx(uart):
    uart.clk.value = BinaryValue('Z')
    uart.rst.value = 1
    uart.ready.value = 1
    uart.rx.value = 1
    uart.high_speed.value = 1

    await Timer(1)
    uart.rst.value = 0
    await cocotb.start(Clock(uart.clk, 8, units='ns').start())
    await FallingEdge(uart.clk)

    msg = b"Hell\0"
    signals = {
        'clk': uart.clk,
        'data': uart.data,
        'valid': uart.valid,
        'ready': uart.ready,
    }

    await cocotb.start(recv_packet(signals, msg))
    for c in msg:
        await putchar(uart.rx, c)

    overflows = 0
    frame_errors = 0

    async def count_errors():
        nonlocal overflows
        nonlocal frame_errors
        while True:
            await FallingEdge(uart.clk)
            overflows += uart.overflow.value
            frame_errors += uart.frame_error.value

    monitor = await cocotb.start(count_errors())

    uart.rx.value = 0
    await Timer(BIT_STEPS * 20)

    uart.rx.value = 1
    await Timer(BIT_STEPS)

    assert frame_errors == 1

    uart.ready.value = 0
    await putchar(uart.rx, 0xFF)
    await putchar(uart.rx, 0)

    assert overflows == 1

    uart.ready.value = 1
    await recv_packet(signals, (0xFF,))

    monitor.kill()
