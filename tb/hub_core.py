# SPDX-License-Identifier: AGPL-3.0-Only
# Copyright (C) 2022 Sean Anderson <seanga2@gmail.com>

import itertools

import cocotb
from cocotb.binary import BinaryValue
from cocotb.clock import Clock
from cocotb.handle import ModifiableObject
from cocotb.triggers import ClockCycles, Event, FallingEdge, RisingEdge, Timer
from cocotb.types import LogicArray

PORT_COUNT = 4

class Memory(ModifiableObject):
    def __init__(self, handle, path):
        super().__init__(handle, path)

@cocotb.test(timeout_time=100, timeout_unit='ns')
async def test_hub(hub):
    hub.rx_dv.value = 0
    await Timer(1)
    await cocotb.start(Clock(hub.clk, 8, units='ns').start())

    await FallingEdge(hub.clk)
    assert not hub.tx_en.value

    def check(jam, active_port=None, data=None):
        if jam:
            data = 5

        for i in range(PORT_COUNT):
            if not jam and i == active_port:
                assert not hub.tx_en[i].value
            else:
                assert hub.tx_en[i].value
                if data is None:
                    assert hub.tx_er[i].value
                else:
                    assert not hub.tx_er[i].value
                    assert hub.txd.value[i * 4:(i + 1) * 4 - 1] == data

    hub.rx_dv[0].value = 1
    hub.rx_er[0].value = 0
    rxd = LogicArray(itertools.repeat('X', PORT_COUNT * 4))
    rxd[3:0] = BinaryValue(1, 4, False).binstr
    hub.rxd.value = rxd
    await FallingEdge(hub.clk)
    check(False, 0, 1)

    hub.rx_er[0].value = 1
    await FallingEdge(hub.clk)
    check(False, 0)

    hub.rx_dv[1].value = 1
    hub.rx_er[1].value = 0 
    rxd[7:4] = BinaryValue(2, 4, False).binstr
    hub.rxd.value = rxd
    await FallingEdge(hub.clk)
    check(True)

    hub.rx_dv[0].value = 0
    for i in range(1, PORT_COUNT):
        hub.rx_dv[i].value = 1
        hub.rx_er[i].value = 0
        rxd = LogicArray(itertools.repeat('X', PORT_COUNT * 4))
        rxd[(i + 1) * 4 - 1:i * 4] = BinaryValue(i + 1, 4, False).binstr
        hub.rxd.value = rxd
        await FallingEdge(hub.clk)
        check(False, i, i + 1)
        hub.rx_dv[i].value = 0

    await FallingEdge(hub.clk)
    assert not hub.tx_en.value
