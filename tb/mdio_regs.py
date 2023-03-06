# SPDX-License-Identifier: AGPL-3.0-Only
# Copyright (C) 2022 Sean Anderson <seanga2@gmail.com>

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, Timer
from cocotb.types import LogicArray

from .util import BIT

BMCR = 0
BMSR = 1
PHYID1 = 2
PHYID2 = 3
EXTSTATUS = 15
NWCR = 16
PWCR = 17
DCR = 18
FCCR = 19
SECR = 21
VCR = 30

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

VCR_DTEST = BIT(15)
VCR_LTEST = BIT(14)

async def wb_xfer(signals, addr, data=None, delay=1):
    await FallingEdge(signals['clk'])
    signals['stb'].value = 1
    signals['addr'].value = addr
    if data is None:
        signals['we'].value = 0
    else:
        signals['we'].value = 1
        signals['data_write'].value = data

    for _ in range(delay + 1):
        await FallingEdge(signals['clk'])
        if signals['ack'].value or signals['err'].value:
            break

    assert signals['ack'].value or signals['err'].value
    signals['stb'].value = 0
    signals['we'].value = LogicArray('X')
    signals['addr'].value = LogicArray('X' * len(signals['addr']))
    signals['data_write'].value = LogicArray('X' * 16)
    if data is None and signals['ack'].value:
        return signals['data_read'].value

@cocotb.test(timeout_time=2, timeout_unit='us')
async def test_mdio(regs):
    regs.cyc.value = 1
    regs.stb.value = 0
    regs.link_status.value = 1
    regs.positive_wraparound.value = 0
    regs.negative_wraparound.value = 0
    regs.false_carrier.value = 0
    regs.symbol_error.value = 0
    await Timer(1)
    await cocotb.start(Clock(regs.clk, 8, units='ns').start())

    def xfer(regad, data=None):
        return wb_xfer({
            'clk': regs.clk,
            'stb': regs.stb,
            'we': regs.we,
            'addr': regs.addr,
            'data_write': regs.data_write,
            'data_read': regs.data_read,
            'ack': regs.ack,
            'err': regs.err,
        }, regad, data)

    async def reg_toggle(reg, bit, signal, ro_mask=0):
        if signal:
            assert not signal.value
        await xfer(reg, bit)
        if signal:
            assert signal.value
        assert await xfer(reg) == (ro_mask | bit)
        await xfer(reg, 0)
        if signal:
            assert not signal.value

    def bmcr_toggle(bit, signal):
        return reg_toggle(BMCR, bit, signal, ro_mask=BMCR_SPEED_LSB)

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

    async def counter_test(reg, signal, edge_triggered=False, active_high=True):
        signal.value = 1 if active_high else 0
        await FallingEdge(regs.clk)
        assert await xfer(reg) == 1
        await xfer(reg, 0xfffe)
        if edge_triggered:
            signal.value = 0 if active_high else 1
        await FallingEdge(regs.clk)
        if edge_triggered:
            signal.value = 1 if active_high else 0
        await FallingEdge(regs.clk)
        signal.value = 0 if active_high else 1
        assert await xfer(reg) == 0x7fff
        assert await xfer(reg) == 0

    await counter_test(NWCR, regs.negative_wraparound)
    await counter_test(PWCR, regs.positive_wraparound)
    await xfer(DCR) # Clear DCR from the BMSR testing
    await counter_test(DCR, regs.link_status, True, False)
    await counter_test(FCCR, regs.false_carrier)
    await counter_test(SECR, regs.symbol_error)

    await reg_toggle(VCR, VCR_DTEST, regs.descrambler_test)
    await reg_toggle(VCR, VCR_LTEST, regs.link_monitor_test)
