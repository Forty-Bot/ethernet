// SPDX-License-Identifier: AGPL-3.0-Only
/*
 * Copyright (C) 2022 Sean Anderson <seanga2@gmail.com>
 *
 * 8n1@115200; no one uses anything else (and neither do I)
 */

`include "common.vh"

module uart_rx (
	input clk,
	input rst,

	output reg [7:0] data,
	input ready,
	output reg valid,

	input rx,

	/* Run at 4M for testing */
	input high_speed,
	/* No one ready */
	output reg overflow,
	/* Missing stop bit */
	output reg frame_error
);

	/* 1085 cycles, for 115200 baud with a 125 MHz clock */
	parameter SLOW_FULL	= 11'h78c;
	parameter SLOW_HALF	= 11'h202;
	/* 31 cycles, for 4M baud with a 125 MHz clock */
	parameter FAST_FULL	= 11'h68e;
	parameter FAST_HALF	= 11'h34c;

	localparam ERROR	= 11;
	localparam IDLE		= 10;
	localparam START	= 9;
	localparam D0		= 8;
	localparam D1		= 7;
	localparam D2		= 6;
	localparam D3		= 5;
	localparam D4		= 4;
	localparam D5		= 3;
	localparam D6		= 2;
	localparam D7		= 1;
	localparam STOP		= 0;

	reg [3:0] state, state_next;
	reg [10:0] lfsr, lfsr_next;
	reg [7:0] bits, bits_next, data_next;
	reg ready_last;
	reg valid_next, overflow_next, frame_error_next;

	always @(*) begin
		state_next = state;
		lfsr_next = { lfsr[9:0], lfsr[10] ^ lfsr[8] };
		bits_next = bits;
		data_next = data;
		valid_next = valid && !ready_last;
		overflow_next = 0;
		frame_error_next = 0;

		case (state)
		IDLE: if (!rx) begin
			state_next = START;
			lfsr_next = high_speed ? FAST_HALF : SLOW_HALF;
		end
		START: if (&lfsr) begin
			state_next = rx ? IDLE : D0;
			lfsr_next = high_speed ? FAST_FULL : SLOW_FULL;
		end
		D0, D1, D2, D3, D4, D5, D6, D7: if (&lfsr) begin
			lfsr_next = high_speed ? FAST_FULL : SLOW_FULL;
			bits_next = { rx, bits[7:1] };
			state_next = state - 1;
		end
		STOP: if (&lfsr) begin
			lfsr_next = high_speed ? FAST_FULL : SLOW_FULL;
			if (rx) begin
				state_next = IDLE;
				if (valid_next)
					overflow_next = 1;
				else
					data_next = bits;
				valid_next = 1;
			end else begin
				frame_error_next = 1;
				state_next = ERROR;
			end
		end
		ERROR: if (&lfsr) begin
			lfsr_next = high_speed ? FAST_FULL : SLOW_FULL;
			if (rx)
				state_next = IDLE;
		end
		endcase
	end

	always @(posedge clk) begin
		lfsr <= lfsr_next;
		bits <= bits_next;
		data <= data_next;
	end

	always @(posedge clk, posedge rst) begin
		if (rst) begin
			state <= IDLE;
			valid <= 0;
			ready_last <= 0;
			overflow <= 0;
			frame_error <= 0;
		end else begin
			state <= state_next;
			valid <= valid_next;
			ready_last <= ready;
			overflow <= overflow_next;
			frame_error <= frame_error_next;
		end
	end

endmodule
