# SPDX-License-Identifier: AGPL-3.0-Only
# Copyright (C) 2023 Sean Anderson <seanga2@gmail.com>

import cocotb
from cocotb.binary import BinaryValue
from cocotb.clock import Clock
from cocotb.regression import TestFactory
from cocotb.triggers import FallingEdge, Timer

from .axis_replay_buffer import send_packet, recv_packet
from .mdio import wb_read, wb_write, wb_err
from .util import BIT, ClockEnable, GENMASK, timeout

CMD_CLEAR = BIT(0)
CMD_WE = BIT(1)
CMD_POSTINC = BIT(2)
CMD_ADDR0 = 0x00
CMD_ADDR8 = 0x08
CMD_ADDR16 = 0x10
CMD_ADDR32 = 0x18

STATUS_WE = BIT(0)
STATUS_ERR = BIT(1)
STATUS_OVERFLOW = BIT(3)

class Encoder:
    def __init__(self):
        self.last_addr = None

    def encode(self, addr, data=None, postinc=False):
        cmd = CMD_POSTINC if postinc else 0
        if data is None:
            data_bytes = ()
        else:
            cmd |= CMD_WE
            data_bytes = data.to_bytes(2, 'big')

        if self.last_addr is None:
            cmd |= CMD_CLEAR
            self.last_addr = 0

        def addr_len(last):
            if (addr ^ last) & ~GENMASK(15, 0):
                return 4
            if (addr ^ last) & GENMASK(15, 8):
                return 2
            if (addr ^ last) & GENMASK(7, 0):
                return 1
            return 0

        len_zero = addr_len(0)
        len_last = addr_len(self.last_addr)
        if len_zero < len_last:
            addr_len = len_zero
            cmd |= CMD_CLEAR
        else:
            addr_len = len_last

        addr_bytes = (addr & GENMASK(addr_len * 8 - 1, 0)).to_bytes(addr_len, 'big')
        if addr_len == 4:
            cmd |= CMD_ADDR32
        elif addr_len == 2:
            cmd |= CMD_ADDR16
        elif addr_len == 1:
            cmd |= CMD_ADDR8
        else:
            cmd |= CMD_ADDR0

        self.last_addr = (addr & ~GENMASK(7, 0)) | ((addr + postinc) & GENMASK(7, 0))
        return (cmd, *addr_bytes, *data_bytes)

@timeout(10, 'us')
async def test_bridge(bridge, in_ratio, out_ratio):
    bridge.clk.value = BinaryValue('Z')
    bridge.rst.value = 1
    bridge.s_axis_valid.value = 0
    bridge.m_axis_ready.value = 1
    bridge.wb_ack.value = 0
    bridge.wb_err.value = 0
    bridge.overflow.value = 0

    await Timer(1)
    bridge.rst.value = 0
    await cocotb.start(Clock(bridge.clk, 8, units='ns').start())
    await FallingEdge(bridge.clk)
    await cocotb.start(ClockEnable(bridge.clk, bridge.m_axis_ready, out_ratio))

    s_axis = {
        'clk': bridge.clk,
        'ready': bridge.s_axis_ready,
        'valid': bridge.s_axis_valid,
        'data': bridge.s_axis_data,
    }

    m_axis = {
        'clk': bridge.clk,
        'ready': bridge.m_axis_ready,
        'valid': bridge.m_axis_valid,
        'data': bridge.m_axis_data,
    }

    wb = {
        'clk': bridge.clk,
        'ack': bridge.wb_ack,
        'err': bridge.wb_err,
        'cyc': bridge.wb_cyc,
        'stb': bridge.wb_stb,
        'we': bridge.wb_we,
        'addr': bridge.wb_addr,
        'data_write': bridge.wb_data_write,
        'data_read': bridge.wb_data_read,
    }

    e = Encoder()

    async def read(addr, data, postinc=False, resp=0):
        await send_packet(s_axis, e.encode(addr, None, postinc), in_ratio)

        bridge.overflow.value = bool(resp & STATUS_OVERFLOW)
        if resp & STATUS_ERR:
            await wb_err(wb)
            bridge.overflow.value = 0
            await recv_packet(m_axis, (resp,))
        else:
            await wb_read(wb, addr, data)
            bridge.overflow.value = 0
            await recv_packet(m_axis, (resp, *data.to_bytes(2, 'little')))

    async def write(addr, data, postinc=False, resp=STATUS_WE):
        await send_packet(s_axis, e.encode(addr, data, postinc), in_ratio)

        bridge.overflow.value = bool(resp & STATUS_OVERFLOW)
        if resp & STATUS_ERR:
            await wb_err(wb)
        else:
            await wb_write(wb, addr, data)
        bridge.overflow.value = 0

        await recv_packet(m_axis, (resp,))

    for f in read, write:
        await f(0x01234567, 0x89ab)
        await f(0x01234567, 0xcdef)
        await f(0x012345fe, 1, True)
        await f(0x012345ff, 2, True)
        await f(0x01234500, 3)
        await f(0x012345ff, 4, True)
        await f(0x01234600, 5)
        await f(0x0123ffff, 6)
        await f(0x01ffffff, 7)
        await f(0xffffffff, 8)
        await f(0x0000ffff, 9)
        await f(0x000000ff, 10)
        await f(0x00000000, 11)

    # fast back-to-back
    recv = await cocotb.start(recv_packet(m_axis, (STATUS_WE, 0, 4, 0)))
    await send_packet(s_axis, e.encode(1, 2))
    await wb_write(wb, 1, 2)
    await send_packet(s_axis, e.encode(3))
    await wb_read(wb, 3, 4)
    await recv

    # bus error/overflow
    await write(5, 6, resp=STATUS_WE | STATUS_ERR | STATUS_OVERFLOW)
    await read(7, 8, resp=STATUS_ERR)
    await read(9, 10, resp=STATUS_OVERFLOW)
    await write(11, 12)

bridge_tests = TestFactory(test_bridge)
bridge_tests.add_option('in_ratio', (1, 4))
bridge_tests.add_option('out_ratio', (1, 4))
bridge_tests.generate_tests()
