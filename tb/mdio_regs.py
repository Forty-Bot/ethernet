# SPDX-License-Identifier: AGPL-3.0-Only
# Copyright (C) 2022 Sean Anderson <seanga2@gmail.com>

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, Timer
from cocotb.types import LogicArray

def BIT(n):
    return 1 << n

BMCR = 0
BMSR = 1
PHYID1 = 2
PHYID2 = 3
EXTSTATUS = 15

BMCR_RESET = BIT(15)
BMCR_LOOPBACK = BIT(14)
BMCR_SPEED_LSB = BIT(13)
BMCR_PDOWN = BIT(11)
BMCR_ISOLATE = BIT(10)
BMCR_DUPLEX = BIT(8)
BMCR_COLTEST = BIT(7)
BMCR_SPEED_MSB = BIT(6)

BMSR_100BASEXFD = BIT(14)
BMSR_100BASEXHD = BIT(13)
BMSR_LSTATUS = BIT(2)
BMSR_EXTCAP = BIT(0)

@cocotb.test(timeout_time=1, timeout_unit='us')
async def test_mdio(regs):
    regs.cyc.value = 1
    regs.stb.value = 0
    regs.link_status.value = 1
    await Timer(1)
    await cocotb.start(Clock(regs.clk, 8, units='ns').start())

    async def xfer(regad, data=None):
        await FallingEdge(regs.clk)
        regs.stb.value = 1
        regs.addr.value = regad
        if data is None:
            regs.we.value = 0
        else:
            regs.we.value = 1
            regs.data_write.value = data

        await FallingEdge(regs.clk)
        assert regs.ack.value or regs.err.value
        regs.stb.value = 0
        regs.we.value = LogicArray('X')
        regs.addr.value = LogicArray('X' * 4)
        regs.data_write.value = LogicArray('X' * 16)
        if data is None and regs.ack.value:
            return regs.data_read.value

    async def bmcr_toggle(bit, signal):
        if signal:
            assert not signal.value
        await xfer(BMCR, bit)
        if signal:
            assert signal.value
        assert await xfer(BMCR) == (BMCR_SPEED_LSB | bit)
        await xfer(BMCR, 0)
        if signal:
            assert not signal.value

    assert await xfer(BMCR) == (BMCR_SPEED_LSB | BMCR_ISOLATE)
    await bmcr_toggle(BMCR_LOOPBACK, regs.loopback)
    await bmcr_toggle(BMCR_PDOWN, regs.pdown)
    await bmcr_toggle(BMCR_ISOLATE, regs.isolate)
    await bmcr_toggle(BMCR_DUPLEX, None)
    await bmcr_toggle(BMCR_COLTEST, regs.coltest)
    await xfer(BMCR, BMCR_RESET)
    assert await xfer(BMCR) == (BMCR_SPEED_LSB | BMCR_ISOLATE)

    await xfer(BMSR, 0xffff)
    assert await xfer(BMSR) == (BMSR_100BASEXFD | BMSR_100BASEXHD | BMSR_LSTATUS | BMSR_EXTCAP)
    regs.link_status.value = 0
    assert not await xfer(BMSR) & BMSR_LSTATUS
    regs.link_status.value = 1
    assert not await xfer(BMSR) & BMSR_LSTATUS
    assert await xfer(BMSR) & BMSR_LSTATUS

    await xfer(PHYID1, 0xffff)
    assert await xfer(PHYID1) == 0

    await xfer(PHYID2, 0xffff)
    assert await xfer(PHYID2) == 0

    # I'm pretty sure this register will never be implemented
    assert await xfer(EXTSTATUS) is None
    assert await xfer(EXTSTATUS, 0) is None
