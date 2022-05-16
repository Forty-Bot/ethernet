# SPDX-License-Identifier: AGPL-3.0-Only
# Copyright (C) 2022 Sean Anderson <seanga2@gmail.com>

Q = 1
SYNTH = yosys
PNR = nextpnr-ice40
ICARUS = iverilog
VVP = vvp

.PHONY: all
all: rtl/pcs.asc

.PHONY: FORCE
FORCE:

%.json: %.v
	$(SYNTH) -q -E $@.d -p "synth_ice40 -top top" -b json -o $@ -f verilog $<

%.vvp: %.v
	echo "+timescale+1ns/1ns" | \
	$(ICARUS) -Wall -c /dev/stdin -I$(<D) -M$@.pre -s $(*F) -o $@ $< && \
		( echo -n "$@: " && tr '\n' ' ' ) < $@.pre > $@.d; RET=$$?; rm -f $@.pre; exit $$RET

%.asc: %.json
	$(PNR) --pcf-allow-unconstrained --freq 125 --hx8k --package ct256 --json $< --asc $@

-include $(wildcard rtl/*.d)

export LIBPYTHON_LOC := $(shell cocotb-config --libpython)
VVPARGS := -M $(shell cocotb-config --lib-dir)
VVPARGS += -m $(shell cocotb-config --lib-name vpi icarus)

%.fst: rtl/%.vvp tb/%.py FORCE
	MODULE=tb.$* $(VVP) $(VVPARGS) $< -fst +vcd=$@

.PHONY: test
test: test_pcs

.PHONY: clean
clean:
	rm *.fst
	cd rtl && rm -f *.json *.asc *.vvp *.d *.pre
