# SPDX-License-Identifier: AGPL-3.0-Only
# Copyright (C) 2023 Sean Anderson <seanga2@gmail.com>

import cocotb
from cocotb.binary import BinaryValue
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer

from .mdio import wb_read, wb_write, wb_err
from .mdio_regs import wb_xfer

@cocotb.test(timeout_time=50, timeout_unit='us')
async def test_reg(reg):
    reg.clk.value = BinaryValue('Z')
    reg.rst.value = 0
    reg.s_cyc.value = 1
    reg.s_stb.value = 0
    reg.m_ack.value = 0
    reg.m_err.value = 0

    await Timer(1)
    await cocotb.start(Clock(reg.clk, 8, units='ns').start())
    await FallingEdge(reg.clk)

    master = {
        'clk': reg.clk,
        'ack': reg.m_ack,
        'err': reg.m_err,
        'cyc': reg.m_cyc,
        'stb': reg.m_stb,
        'we': reg.m_we,
        'addr': reg.m_addr,
        'data_write': reg.m_data_write,
        'data_read': reg.m_data_read,
    }

    slave = {
        'clk': reg.clk,
        'ack': reg.s_ack,
        'err': reg.s_err,
        'cyc': reg.s_cyc,
        'stb': reg.s_stb,
        'we': reg.s_we,
        'addr': reg.s_addr,
        'data_write': reg.s_data_write,
        'data_read': reg.s_data_read,
    }

    async def resp():
        await wb_read(master, 0x0123, 0x4567)
        await wb_write(master, 0x89ab, 0xcdef)
        await wb_err(master)

    await cocotb.start(resp())

    assert await wb_xfer(slave, 0x0123) == 0x4567
    await wb_xfer(slave, 0x89ab, 0xcdef)
    assert await wb_xfer(slave, 0xdead) is None

    reg.rst.value = 1
    reg.s_cyc.value = 1
    reg.m_ack.value = 1
    reg.m_err.value = 1
    await FallingEdge(reg.clk)
    assert not reg.m_cyc.value
    assert not reg.m_stb.value
    assert not reg.s_ack.value
    assert not reg.s_err.value
