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
	$(SYNTH) -q -E $@.d -p "synth_ice40 -top $(*F)" -b json -o $@ -f verilog $<

%.post.v: %.json %.v
	( echo '`include "common.vh"'; grep timescale $*.v; \
	  $(SYNTH) -q -b verilog -f json $< ) | sed 's/endmodule/`DUMP(1)\n\0/g' > $@

# Don't warn about including the timescale from common.vh
IFLAGS := -g2012 -Wall -Wno-timescale

define run-icarus =
$(ICARUS) $(IFLAGS) -I$(<D) -M$@.pre -s $(TOP) -o $@ $< $(EXTRA_V) && \
	( echo -n "$@: " && tr '\n' ' ' ) < $@.pre > $@.d; RET=$$?; rm -f $@.pre; exit $$RET
endef

%.vvp: TOP = $(*F)
%.vvp: %.v
	$(run-icarus)

%.post.vvp: TOP = $(*F)
%.post.vvp: EXTRA_V := $(shell $(SYNTH)-config --datdir)/ice40/cells_sim.v
# Don't warn about unused SB_IO ports
%.post.vvp: IFLAGS += -Wno-portbind
%.post.vvp: %.post.v
	$(run-icarus)

%.asc: %.json
	$(PNR) --pcf-allow-unconstrained --freq 125 --hx8k --package ct256 --json $< --asc $@

-include $(wildcard rtl/*.d)

export LIBPYTHON_LOC := $(shell cocotb-config --libpython)
VVPFLAGS := -M $(shell cocotb-config --lib-dir)
VVPFLAGS += -m $(shell cocotb-config --lib-name vpi icarus)

# Always use color output if we have a tty. This allows for easy use of -O
ifeq ($(shell test -c /dev/stdin && echo 1),1)
export COCOTB_ANSI_OUTPUT=1
endif

define run-vvp =
MODULE=tb.$* $(VVP) $(VVPFLAGS) $< -fst +vcd=$@
endef

%.fst: rtl/%.vvp tb/%.py FORCE
	$(run-vvp)

%.post.fst: rtl/%.post.vvp tb/%.py FORCE
	$(run-vvp)

MODULES := pcs pmd nrzi_encode nrzi_decode scramble descramble mdio mdio_io mii_io_rx mii_io_tx

.PHONY: test
test: $(addsuffix .fst,$(MODULES)) $(addsuffix .post.fst,$(MODULES))

.PHONY: clean
clean:
	rm *.fst
	cd rtl && rm -f *.json *.asc *.pre *.vvp *.d *.post.v
