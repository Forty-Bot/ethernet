// SPDX-License-Identifier: AGPL-3.0-Only
/*
 * Copyright (C) 2022 Sean Anderson <seanga2@gmail.com>
 */

`default_nettype none

`include "common.vh"

/* 4b5b code groups */
`define CODE_0 5'b11110
`define CODE_1 5'b01001
`define CODE_2 5'b10100
`define CODE_3 5'b10101
`define CODE_4 5'b01010
`define CODE_5 5'b01011
`define CODE_6 5'b01110
`define CODE_7 5'b01111
`define CODE_8 5'b10010
`define CODE_9 5'b10011
`define CODE_A 5'b10110
`define CODE_B 5'b10111
`define CODE_C 5'b11010
`define CODE_D 5'b11011
`define CODE_E 5'b11100
`define CODE_F 5'b11101

`define CODE_I 5'b11111

`define CODE_J 5'b11000
`define CODE_K 5'b10001
`define CODE_T 5'b01101
`define CODE_R 5'b00111

`define CODE_H 5'b00100

`timescale 1ns/1ns

module pcs (
	/* MII */
	input tx_clk,
	input tx_ce,
	input tx_en,
	input [3:0] txd,
	input tx_er,

	input rx_clk,
	output rx_ce,
	output rx_dv,
	output [3:0] rxd,
	output rx_er,

	output crs,
	output col,

	/* PMA */
	output pma_data_tx,
	input [1:0] pma_data_rx,
	input [1:0] pma_data_rx_valid,
	input link_status
);

	wire transmitting, receiving;

	pcs_tx tx (
		.clk(tx_clk),
		.ce(tx_ce),
		.enable(tx_en),
		.data(txd),
		.err(tx_er),
		.bits(pma_data_tx),
		.link_status(link_status),
		.tx(transmitting)
	);

	pcs_rx rx (
		.clk(rx_clk),
		.ce(rx_ce),
		.valid(rx_dv),
		.data(rxd),
		.err(rx_er),
		.bits(pma_data_rx),
		.bits_valid(pma_data_rx_valid),
		.link_status(link_status),
		.rx(receiving)
	);

	/*
	 * NB: These signals are not required to be in any particular clock
	 * domain.
	 */
	assign col = transmitting && receiving;
	assign crs = transmitting || receiving;

	`DUMP

endmodule

/* Transmit process */
module pcs_tx (
	/* MII */
	input clk,
	input ce,
	input enable,
	input [3:0] data,
	input err,

	/* PMA */
	output bits,
	input link_status,

	/* Internal */
	output reg tx
);

	localparam IDLE		= 0;
	localparam START_J	= 1;
	localparam START_K	= 2;
	localparam ERROR_J	= 3;
	localparam ERROR_K	= 4;
	localparam ERROR	= 5;
	localparam DATA		= 6;
	localparam END_T	= 7;
	localparam END_R	= 8;

	reg [3:0] last_data;
	reg tx_next;
	reg [4:0] code, code_next;
	reg [3:0] state, state_next;

	initial tx = 0;
	initial code = `CODE_I;
	initial state = IDLE;

	always @(*) begin
		case (last_data)
		4'h0: code_next = `CODE_0;
		4'h1: code_next = `CODE_1;
		4'h2: code_next = `CODE_2;
		4'h3: code_next = `CODE_3;
		4'h4: code_next = `CODE_4;
		4'h5: code_next = `CODE_5;
		4'h6: code_next = `CODE_6;
		4'h7: code_next = `CODE_7;
		4'h8: code_next = `CODE_8;
		4'h9: code_next = `CODE_9;
		4'hA: code_next = `CODE_A;
		4'hB: code_next = `CODE_B;
		4'hC: code_next = `CODE_C;
		4'hD: code_next = `CODE_D;
		4'hE: code_next = `CODE_E;
		4'hF: code_next = `CODE_F;
		endcase

		tx_next = tx;
		if (enable) begin
			if (err)
				state_next = ERROR;
			else
				state_next = DATA;
		end else begin
			state_next = END_T;
		end

		case (state)
		IDLE: begin
			tx_next = 0;
			code_next = `CODE_I;
			state_next = IDLE;
			if (enable) begin
				if (err)
					state_next = ERROR_J;
				else
					state_next = START_J;
			end
		end
		START_J: begin
			tx_next = 1;
			code_next = `CODE_J;
			if (err)
				state_next = ERROR_K;
			else
				state_next = START_K;
		end
		START_K: begin
			code_next = `CODE_K;
		end
		ERROR_J: begin
			tx_next = 1;
			code_next = `CODE_J;
			state_next = ERROR_K;
		end
		ERROR_K: begin
			code_next = `CODE_K;
			state_next = ERROR;
		end
		ERROR: begin
			code_next = `CODE_H;
		end
		DATA: ;
		END_T: begin
			tx_next = 0;
			code_next = `CODE_T;
			state_next = END_R;
		end
		END_R: begin
			code_next = `CODE_R;
			state_next = IDLE;
		end
		endcase

	end

	always @(posedge clk, negedge link_status) begin
		if (!link_status) begin
			tx <= 0;
			code <= `CODE_I;
			state <= IDLE;
		end else if (ce) begin
			last_data <= data;
			tx <= tx_next;
			code <= code_next;
			state <= state_next;
		end else begin
			code <= code << 1;
		end
	end

`ifndef SYNTHESIS
	reg [255:0] state_text;

	always @(*) begin
		case (state)
		IDLE: state_text = "IDLE";
		START_J: state_text = "START_J";
		START_K: state_text = "START_K";
		ERROR_J: state_text = "ERROR_J";
		ERROR_K: state_text = "ERROR_K";
		ERROR: state_text = "ERROR";
		DATA: state_text = "DATA";
		END_T: state_text = "END_T";
		END_R: state_text = "END_R";
		endcase
	end
`endif

	/* Transmit bits process */
	assign bits = code[4];
endmodule

module pcs_rx_bits (
	input clk,
	/*
	 * Whether to start a new frame using the last value of @unaligned
	 * (instead of @aligned). This will adjust the alignment of @aligned.
	 * Should be a combinatorial input.
	 */
	input start,
	/*
	 * Fill the input buffer with 1s. This will take effect the cycle
	 * after it is asserted. It is possible that an overlapping R/J will
	 * not be detected, but any legal (non-overlapping) R/J will be
	 * detected properly. Should be a combinatorial input.
	 */
	input flush,
	/*
	 * The input bits from the PMA. The @bits[1] should be the
	 * oldest bit. If only one bit is valid, then @bits[1] will be
	 * considered valid. There cannot be more than two valid bits in one
	 * cycle.
	 */
	input [1:0] bits, bits_valid,

	/*
	 * Whether there was activity detected, as defined by 24.2.4.4.1. When
	 * this signal is asserted, then @unaligned contains valid code groups
	 * (such as /I/J/).
	 */
	output reg activity,
	/*
	 * Whether there are at least 10 1s in the input buffer, aligned
	 * or unaligned. This signal may be used to detect the end of a carrier
	 * event, as defined by 24.2.4.4.2.
	 */
	output reg idle,
	/*
	 * Whether @aligned contains valid code groups. This signal will be
	 * asserted (on average) every 5 clock cycles, and can be used as
	 * a clock enable.
	 */
	output reg indicate,
	/*
	 * The output bits from the alignment process. Despite the name, both
	 * code groups are aligned. @unaligned assumes that we are not
	 * receiving and tries to detect a new start of stream. @aligned
	 * assumes that we are receiving and bases the alignment of its code
	 * group off of a previous start of stream.
	 */
	output reg [9:0] aligned, unaligned
);

	reg activity_next, idle_next, indicate_next;
	reg [9:0] aligned_next, unaligned_next;

	/* A shift buffer containing the previous values of @bits. */
	reg [9:0] buffer, buffer_next;
	initial buffer = { `CODE_I, `CODE_I };
	/*
	 * The buffer combined with the new bits (e.g. the total set of bits we
	 * have to work with)
	 */
	wire [11:0] raw_bits = { buffer, bits };
	/* buffer_next before being shifted by bits_valid */
	reg [11:0] buffer_next_raw;
	/*
	 * The number of bits left to receive for the current code group.
	 * A value of 0 (or 1 if @bits_valid is 2) indicates that the current
	 * code group will be finished this cycle, and that @indicate_next will be
	 * set.
	 */
	reg [2:0] bits_remaining, bits_remaining_next;
	initial bits_remaining = 4;
	/*
	 * Whether the last unaligned code group had an "extra" valid bit. If
	 * this was the case, then the buffer will already contain an extra
	 * valid bit of the next code group.
	 */
	reg extra, extra_next;

	/* Detect an IJ pair (or a false carrier) */
	function start_ij(input [9:0] bits);
		start_ij = !(&bits[9:2]) && !bits[0];
	endfunction

	always @(*) begin
		idle_next = &raw_bits[10:1];
		if (bits_valid & 2)
			idle_next = idle_next || &raw_bits[9:0];

		buffer_next_raw = raw_bits;
		if (flush)
			buffer_next_raw = { 9'h1FF, extra ? buffer[0] : 1'b1, bits };

		/* buffer_next = buffer_next_raw << bits_valid */
		if (bits_valid == 0)
			buffer_next = buffer_next_raw[11:2];
		else if (bits_valid == 1)
			buffer_next = buffer_next_raw[10:1];
		else
			buffer_next = buffer_next_raw[9:0];

		/* bits_remaining_next = (bits_remaining - bits_valid) % 5 */
		if (bits_valid > bits_remaining)
			bits_remaining_next = 5 + bits_remaining - bits_valid;
		else
			bits_remaining_next = bits_remaining - bits_valid;
		if (start)
			bits_remaining_next = 4 - bits_valid - extra;

		/* indicate = bits_remaining < bits_remaining_next */
		indicate_next = 0;
		if (bits_valid != 0)
			indicate_next = bits_remaining == 0;
		if (bits_valid & 2)
			indicate_next = indicate_next || bits_remaining == 1;
		/*
		 * If we are re-aligning, then indicate will not be valid
		 * (since it is using the old alignment). There should always
		 * be at least 3 clock cycles between indicates, so it's safe
		 * to just ignore it.
		 */
		if (start)
			indicate_next = 0;

		aligned_next = raw_bits[10:1];
		if (bits_valid & 2 && bits_remaining & 1)
			aligned_next = raw_bits[9:0];

		activity_next = 0;
		extra_next = 0;
		unaligned_next = raw_bits[10:1];
		if (bits_valid == 1) begin
			activity_next = start_ij(raw_bits[10:1]);
		end else if (bits_valid & 2) begin
			if (start_ij(raw_bits[10:1])) begin
				activity_next = 1;
				extra_next = 1;
			end else if (start_ij(raw_bits[9:0])) begin
				activity_next = 1;
				unaligned_next = raw_bits[9:0];
			end
		end

		/*
		 * If we are flushing flush then activity is based on stale
		 * data. Ignore it so we don't accidentally detect activity for
		 * data we are going to flush anyway.
		 */
		if (flush)
			activity_next = 0;
	end

	always @(posedge clk) begin
		buffer <= buffer_next;
		bits_remaining <= bits_remaining_next;
		extra <= extra_next;
		activity <= activity_next;
		idle <= idle_next;
		indicate <= indicate_next;
		aligned <= aligned_next;
		unaligned <= unaligned_next;
	end

endmodule

/* Receive process */
module pcs_rx (
	/* MII */
	input clk,
	output reg ce,
	output reg valid,
	output reg [3:0] data,
	output reg err,

	/* PMA */
	input [1:0] bits,
	input [1:0] bits_valid,
	input link_status,

	/* Internal */
	output reg rx
);

	localparam IDLE		= 0;
	localparam START_J	= 1;
	localparam START_K	= 2;
	localparam BAD_SSD	= 3;
	localparam DATA		= 4;
	localparam FAILED	= 5;

	reg start, flush;
	wire activity, idle, indicate;
	wire [9:0] aligned, unaligned;

	reg [3:0] data_next;
	reg ce_next, valid_next, err_next;
	reg [2:0] state, state_next;
	initial state = IDLE;
	/* Receive shift buffer */
	reg [9:0] buffer, buffer_next;
	/* Whether we are aligned and receiving */
	reg rx_next;

	pcs_rx_bits rx_bits (
		.clk(clk),
		.start(start),
		.flush(flush),
		.bits(bits),
		.bits_valid(bits_valid),
		.activity(activity),
		.idle(idle),
		.indicate(indicate),
		.aligned(aligned),
		.unaligned(unaligned)
	);

	always @(*) begin
		case (aligned[9:5])
		`CODE_0: data_next = 4'h0;
		`CODE_1: data_next = 4'h1;
		`CODE_2: data_next = 4'h2;
		`CODE_3: data_next = 4'h3;
		`CODE_4: data_next = 4'h4;
		`CODE_5: data_next = 4'h5;
		`CODE_6: data_next = 4'h6;
		`CODE_7: data_next = 4'h7;
		`CODE_8: data_next = 4'h8;
		`CODE_9: data_next = 4'h9;
		`CODE_A: data_next = 4'hA;
		`CODE_B: data_next = 4'hB;
		`CODE_C: data_next = 4'hC;
		`CODE_D: data_next = 4'hD;
		`CODE_E: data_next = 4'hE;
		`CODE_F: data_next = 4'hF;
		`CODE_J: data_next = 4'h5;
		`CODE_K: data_next = 4'h5;
		/* This doesn't do anything :( */
		default: data_next = 4'hX;
		endcase

		start = 0;
		flush = 0;
		rx_next = rx;
		ce_next = indicate;
		state_next = state;
		valid_next = valid;
		err_next = 0;

`define BAD_SSD begin \
	state_next = BAD_SSD; \
	data_next = 4'b1110; \
	err_next = 1; \
end

		case (state)
		/* These two states evaluate continuously */
		IDLE: begin
			rx_next = 0;
			valid_next = 0;
			if (activity) begin
				start = 1;
				rx_next = 1;
				ce_next = 0;
				if (unaligned == { `CODE_I, `CODE_J })
					state_next = START_J;
				else
					`BAD_SSD;
			end
		end
		BAD_SSD: begin
			`BAD_SSD;
			if (idle)
				state_next = IDLE;
		end
		/* These states transition only on indicate */
		START_J: begin
			if (aligned[4:0] == `CODE_K) begin
				state_next = START_K;
				valid_next = 1;
			end else
				`BAD_SSD;

			if (!indicate)
				state_next = START_J;
		end
		START_K: begin
			if (indicate)
				state_next = DATA;
		end
		DATA: begin
			case (aligned[9:5])
			`CODE_0,
			`CODE_1,
			`CODE_2,
			`CODE_3,
			`CODE_4,
			`CODE_5,
			`CODE_6,
			`CODE_7,
			`CODE_8,
			`CODE_9,
			`CODE_A,
			`CODE_B,
			`CODE_C,
			`CODE_D,
			`CODE_E,
			`CODE_F:
				;
			`CODE_T:
				if (aligned[4:0] == `CODE_R) begin
					flush = 1;
					state_next = IDLE;
					valid_next = 0;
				end else begin
					err_next = 1;
				end
			`CODE_I: begin
				err_next = 1;
				if (aligned[4:0] == `CODE_I)
					state_next = IDLE;
			end
			default:
				err_next = 1;
			endcase

			if (!indicate)
				state_next = DATA;
		end
		FAILED: begin
			err_next = 1;
			rx_next = 0;
			if (indicate)
				state_next = IDLE;
		end
		endcase

		if (!link_status) begin
			flush = 1;
			if (indicate && valid_next) begin
				state_next = FAILED;
				err_next = 1;
			end else begin
				state_next = IDLE;
			end
		end
	end

	always @(posedge clk) begin
		rx <= rx_next;
		state <= state_next;
		ce <= ce_next;
		if (ce_next) begin
			data <= data_next;
			valid <= valid_next;
			err <= err_next;
		end
	end

`ifndef SYNTHESIS
	wire [4:0] aligned_hi = aligned[9:5];
	wire [4:0] aligned_lo = aligned[4:0];
	wire [4:0] unaligned_hi = unaligned[9:5];
	wire [4:0] unaligned_lo = unaligned[4:0];
	reg [255:0] state_text;

	always @(*) begin
		case (state)
		IDLE: state_text = "IDLE";
		START_J: state_text = "START_J";
		START_K: state_text = "START_K";
		BAD_SSD: state_text = "BAD_SSD";
		DATA: state_text = "DATA";
		FAILED: state_text = "FAILED";
		endcase
	end
`endif

endmodule

/* For timing purposes */
module top (
	input clk, in_next,
	output out
);

	reg [11:0] in;
	always @(posedge clk)
		in = { in[10:0], in_next };

	wire tx_ce;
	wire tx_en;
	wire [3:0] txd;
	wire tx_er;
	wire [1:0] pma_data_rx;
	wire [1:0] pma_data_rx_valid;
	wire link_status;

	assign { tx_ce, tx_en, txd, tx_er, pma_data_rx, pma_data_rx_valid, link_status } = in;

	wire rx_ce;
	wire rx_dv;
	wire [3:0] rxd;
	wire rx_er;
	wire pma_data_tx;
	wire crs;
	wire col;

	reg [9:0] out_next;

	always @(posedge clk)
		out_next = { rx_ce, rx_dv, rxd, rx_er, pma_data_tx, crs, col };

	assign out = ^out_next;

	pcs pcs (
		clk,
		tx_ce,
		tx_en,
		txd,
		tx_er,

		clk,
		rx_ce,
		rx_dv,
		rxd,
		rx_er,

		crs,
		col,

		pma_data_tx,
		pma_data_rx,
		pma_data_rx_valid,
		link_status
	);

endmodule
