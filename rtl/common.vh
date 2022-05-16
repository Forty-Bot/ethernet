// SPDX-License-Identifier: AGPL-3.0-Only
/*
 * Copyright (C) 2022 Sean Anderson <seanga2@gmail.com>
 */

`ifndef COMMON_VH
`define COMMON_VH

`ifdef SYNTHESIS
`define DUMP
`else
`define DUMP \
	reg [4096:0] vcdfile; \
	initial begin \
		if ($value$plusargs("vcd=%s", vcdfile)) begin \
			$dumpfile(vcdfile); \
			$dumpvars; \
		end \
	end
`endif

`endif /* COMMON_VH */
