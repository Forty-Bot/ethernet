// SPDX-License-Identifier: AGPL-3.0-Only
/*
 * Copyright (C) 2022 Sean Anderson <seanga2@gmail.com>
 */

`include "common.vh"

module nrzi_decode (
	input clk,
	input [1:0] nrzi,
	input [1:0] nrzi_valid,
	output reg [1:0] nrz,
	output reg [1:0] nrz_valid
);

	reg [1:0] nrz_next;
	reg nrzi_last;
	reg nrzi_last_next;

	always @(*) begin
		nrz_next[0] = nrzi[1] ^ nrzi[0];
		nrz_next[1] = nrzi[1] ^ nrzi_last;

		nrzi_last_next = nrzi_last;
		if (nrzi_valid != 0)
			nrzi_last_next = nrzi[1];
		if (nrzi_valid & 2)
			nrzi_last_next = nrzi[0];
	end

	always @(posedge clk) begin
		nrzi_last <= nrzi_last_next;
		nrz_valid <= nrzi_valid;
		nrz <= nrz_next;
	end

	`DUMP(0)

endmodule
