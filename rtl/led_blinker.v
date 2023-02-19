// SPDX-License-Identifier: AGPL-3.0-Only
/*
 * Copyright (C) 2023 Sean Anderson <seanga2@gmail.com>
 *
 * This is an LED blinker designed to make it easier to monitor internal
 * signals with LEDs. The blinker is active for ~16 and inactive for ~16 ms.
 * When triggered, the corresponding output will go high the next time
 * the blinker becomes active. This results in blinking at 30 Hz if
 * continuously triggered. All outputs blink at the same time.
 */

`include "common.vh"

module led_blinker (
	input clk,
	input [LEDS - 1:0] triggers,
	output reg [LEDS - 1:0] out,

	input test_mode
);

	parameter LEDS		= 2;

	localparam TIMER_RESET		= 21'h1ffffe;
	/* 16 cycles before the end */
	localparam TEST_TIMER_RESET	= 21'h0ccccf;

	reg active, active_next;
	reg [LEDS - 1:0] out_next, triggered, triggered_next;
	reg [20:0] lfsr, lfsr_next;

	initial begin
		active = 0;
		triggered = {LEDS{1'b0}};
		out = {LEDS{1'b0}};
		lfsr = TEST_TIMER_RESET;
	end

	always @(*) begin
		active_next = active;
		triggered_next = triggered | triggers;
		out_next = out;
		lfsr_next = { lfsr[19:0], lfsr[20] ^ lfsr[18] };
		if (&lfsr) begin
			if (active) begin
				active_next = 0;
				triggered_next = triggered_next & ~out;
				out_next = {LEDS{1'b0}};
			end else begin
				active_next = 1;
				out_next = triggered;
			end
			lfsr_next = test_mode ? 21'hCCCCF : 21'h1FFFFE;
		end
	end

	always @(posedge clk) begin
		active <= active_next;
		triggered <= triggered_next;
		out <= out_next;
		lfsr <= lfsr_next;
	end

endmodule