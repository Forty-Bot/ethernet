# SPDX-License-Identifier: AGPL-3.0-Only
# Copyright (C) 2022 Sean Anderson <seanga2@gmail.com>

import random
from statistics import NormalDist

import cocotb
from cocotb.binary import BinaryValue
from cocotb.clock import Clock
from cocotb.regression import TestFactory
from cocotb.triggers import RisingEdge, Timer

from .util import compare_lists, print_list_at, timeout

BITS = 1000

def random_delays(count):
    # Target BER is 1e9 and the maximum jitter is 1.4ns
    # This is just random jitter (not DDJ or DCJ) but it'll do
    delay_dist = NormalDist(8000, 1400 / NormalDist().inv_cdf(1-2e-9))
    return (int(delay) for delay in delay_dist.samples(count))

def mindelays(count):
    return (7900,) * count

def maxdelays(count):
    return (8100,) * count

@timeout(100, 'us')
async def test_rx(pmd, delays):
    pmd.signal_detect.value = 0
    await Timer(1)
    await cocotb.start(Clock(pmd.rx_clk_125, 8, units='ns').start())
    # random phase
    await Timer(random.randrange(1, 8000), units='ps')
    await cocotb.start(Clock(pmd.rx_clk_250, 4, units='ns').start())

    ins = [random.randrange(2) for _ in range(BITS)]
    async def generate_bits():
        # random phase
        await Timer(random.randrange(1, 8000), units='ps')
        pmd.signal_detect.value = 1
        for i, delay in zip(ins, delays(len(ins))):
            pmd.indicate_data.value = i
            try:
                pmd.delay.value = delay
            except AttributeError:
                pass
            await Timer(delay, units='ps')
        pmd.signal_detect.value = 0
    await cocotb.start(generate_bits())

    # Wait for things to stabilize
    await RisingEdge(pmd.signal_status)
    outs = []
    while pmd.signal_status.value:
        await RisingEdge(pmd.rx_clk_125)
        valid = pmd.rx_data_valid.value
        if valid == 0:
            pass
        elif valid == 1:
            outs.append(pmd.rx_data[1].value)
        else:
            outs.append(pmd.rx_data[1].value)
            outs.append(pmd.rx_data[0].value)

    best_corr = -1
    best_off = None
    for off in range(16):
        corr = sum(i == o for i, o in zip(ins[off:], outs))
        if corr > best_corr:
            best_corr = corr
            best_off = off

    print(f"best offset is {best_off} correlation {best_corr/(len(ins) - best_off)}")
    compare_lists(ins[best_off:], outs)
    # There will be a few bits at the end not recorded because signal_detect
    # isn't delayed like the data signals
    print(best_corr, len(ins), best_off)
    assert best_corr > len(ins) - best_off - 10

rx_tests = TestFactory(test_rx)
rx_tests.add_option('delays', (random_delays, mindelays, maxdelays))
rx_tests.generate_tests()
