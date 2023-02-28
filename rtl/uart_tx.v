// SPDX-License-Identifier: AGPL-3.0-Only
/*
 * Copyright (C) 2022 Sean Anderson <seanga2@gmail.com>
 *
 * 8n1@115200; no one uses anything else (and neither do I)
 */

`include "common.vh"

module uart_tx (
	input clk,

	input [7:0] data,
	output reg ready,
	input valid,

	output reg tx,

	/* Run at 4M for testing */
	input high_speed
);

	/* 1085 cycles, for 115200 baud with a 125 MHz clock */
	parameter SLOW_VALUE	= 11'h78c;
	/* 31 cycles, for 4M baud with a 125 MHz clock */
	parameter FAST_VALUE	= 11'h68e;

	reg [7:0] data_last;
	reg valid_last, ready_next;
	reg [10:0] lfsr, lfsr_next;
	reg [3:0] counter, counter_next;
	reg [8:0] bits, bits_next;

	initial begin
		ready = 1'b1;
		valid_last = 1'b0;
		bits = 9'h1ff;
	end	

	always @(*) begin
		tx = bits[0];

		ready_next = ready;
		counter_next = counter;
		lfsr_next = { lfsr[9:0], lfsr[10] ^ lfsr[8] };
		bits_next = bits;

		if (&lfsr) begin
			if (counter)
				counter_next = counter - 1;
			else
				ready_next = 1;
			lfsr_next = high_speed ? FAST_VALUE : SLOW_VALUE;
			bits_next = { 1'b1, bits[8:1] };
		end

		if (valid_last && ready) begin
			ready_next = 0;
			counter_next = 9;
			lfsr_next = high_speed ? FAST_VALUE : SLOW_VALUE;
			bits_next = { data_last, 1'b0 };
		end
	end

	always @(posedge clk) begin
		data_last <= data;
		ready <= ready_next;
		valid_last <= valid;
		counter <= counter_next;
		lfsr <= lfsr_next;
		bits <= bits_next;
	end

endmodule
