import random
from statistics import NormalDist

import cocotb
from cocotb.binary import BinaryValue
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

def print_list_at(l, i):
    print(' ' * max(50 - i, 0), *l[max(i - 50, 0):i+50], sep='')

@cocotb.test(timeout_time=100, timeout_unit='us')
async def test_rx(pmd):
    pmd.signal_detect.value = 0
    await Timer(1)
    await cocotb.start(Clock(pmd.rx_clk_125, 8, units='ns').start())
    # random phase
    await Timer(random.randrange(0, 8000), units='ps')
    await cocotb.start(Clock(pmd.rx_clk_250, 4, units='ns').start())

    ins = [random.randrange(2) for _ in range(1000)]
    async def generate_bits():
        # random phase
        await Timer(random.randrange(0, 8000), units='ps')
        pmd.signal_detect.value = 1
        # Target BER is 1e9 and the maximum jitter is 1.4ns
        # This is just random jitter (not DDJ or DCJ) but it'll do
        delay_dist = NormalDist(8000, 1400 / NormalDist().inv_cdf(1-2e-9))
        for i, delay in zip(ins, (int(delay) for delay in delay_dist.samples(len(ins)))):
            pmd.rx.value = i
            try:
                pmd.delay.value = delay
            except AttributeError:
                pass
            await Timer(delay, units='ps')
            #await Timer(8100, units='ps')
        pmd.signal_detect.value = 0
    await cocotb.start(generate_bits())

    # Wait for things to stabilize
    await RisingEdge(pmd.signal_status)
    outs = []
    while pmd.signal_status.value:
        await RisingEdge(pmd.rx_clk_125)
        valid = pmd.pmd_data_rx_valid.value
        if valid == 0:
            pass
        elif valid == 1:
            outs.append(pmd.pmd_data_rx[1].value)
        else:
            outs.append(pmd.pmd_data_rx[1].value)
            outs.append(pmd.pmd_data_rx[0].value)

    best_corr = -1
    best_off = None
    for off in range(-7, 8):
        corr = sum(i == o for i, o in zip(ins[off:], outs))
        if corr > best_corr:
            best_corr = corr
            best_off = off

    print(f"best offset is {best_off} correlation {best_corr/(len(ins) - best_off)}")
    for idx, (i, o) in enumerate(zip(ins[best_off:], outs)):
        if i != o:
            print(idx)
            print_list_at(ins, idx + best_off)
            print_list_at(outs, idx)
            assert False
    # There will be a few bits at the end not recorded because signal_detect
    # isn't delayed like the data signals
    assert best_corr > len(ins) - best_off - 10
