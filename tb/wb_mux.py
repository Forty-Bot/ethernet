# SPDX-License-Identifier: AGPL-3.0-Only
# Copyright (C) 2023 Sean Anderson <seanga2@gmail.com>

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, Timer
from cocotb.types import LogicArray

from .util import BIT, GENMASK

ADDR_WIDTH = 5
DATA_WIDTH = 16
SLAVES = 4

def get(signal, slave, width):
    return (signal.value >> (slave * width)) & GENMASK(width - 1, 0)

def check(mux):
    selected = False
    for i in range(SLAVES):
        cyc = get(mux.s_cyc, i, 1)
        assert cyc == mux.m_cyc.value
        if mux.m_addr.value & BIT(i + ADDR_WIDTH) and not selected:
            selected = True
            stb = bool(mux.s_stb.value & BIT(i))
            assert stb == mux.m_stb.value
            if not cyc and stb:
                continue

            assert get(mux.s_addr, i, ADDR_WIDTH) == mux.m_addr.value & GENMASK(ADDR_WIDTH - 1, 0)
            we = get(mux.s_we, i, 1)
            assert we == mux.m_we.value
            if we:
                assert get(mux.s_data_write, i, DATA_WIDTH) == mux.m_data_write.value

            assert mux.m_ack.value == get(mux.s_ack, i, 1)
            assert mux.m_err.value == get(mux.s_err, i, 1)
            assert mux.m_data_read.value == get(mux.s_data_read, i, DATA_WIDTH)
        else:
            assert not get(mux.s_stb, i, 1)

    if not selected and mux.m_cyc.value and mux.m_stb.value:
        assert not mux.m_ack.value
        assert mux.m_err.value

@cocotb.test(timeout_time=1, timeout_unit='us')
async def test_mdio(mux):
    mux.m_cyc.value = 1
    mux.m_stb.value = 1
    mux.m_we.value = 1
    mux.m_data_write.value = 0x1364
    mux.s_ack.value = 0
    mux.s_err.value = 0
    mux.s_data_read.value = 0x0123456789abcdef

    for i in range(4):
        mux.m_addr.value = BIT(i + 5) | 0x15
        mux.s_ack.value = BIT(i)
        mux.s_err.value = GENMASK(SLAVES - 1, 0) ^ BIT(i)
        await Timer(1)
        check(mux)

        mux.s_ack.value = GENMASK(SLAVES - 1, 0) ^ BIT(i)
        mux.s_err.value = BIT(i)
        await Timer(1)
        check(mux)

    mux.m_addr.value = 0
    await Timer(1)
    check(mux)

    mux.m_stb.value = 0
    await Timer(1)
    check(mux)

    mux.m_cyc.value = 0
    mux.m_stb.value = 1
    await Timer(1)
    check(mux)

    mux.m_cyc.value = 1
    mux.m_addr.value = 0x1ff
    mux.m_we.value = 0
    await Timer(1)
    check(mux)
