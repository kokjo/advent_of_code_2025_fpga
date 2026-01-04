from amaranth import *
from amaranth.hdl.rec import DIR_FANIN, DIR_FANOUT
from amaranth.sim import SimulatorContext

class Stream(Record):
    def __init__(self, width=8, src_loc_at=0):
        super().__init__([
            ("valid", 1, DIR_FANOUT),
            ("ready", 1, DIR_FANIN),
            ("data", width, DIR_FANOUT)
        ], src_loc_at=src_loc_at+1)

class HexConverter(Elaboratable):
    """ Simple Hex converter, accepts 64 bits of input, outputs 8 bit ascii characters"""
    def __init__(self):
        self.i = Stream(64)
        self.o = Stream(8)

    def elaborate(self, platform):
        m = Module()
        cnt = Signal(5)
        tmp = Signal(64)

        with m.If(self.o.ready):
            m.d.sync += self.o.valid.eq(0),

        with m.If(self.i.valid & (cnt == 0)):
            m.d.comb += self.i.ready.eq(1)
            m.d.sync += [
                cnt.eq(16),
                tmp.eq(self.i.data)
            ]

        with m.If(cnt != 0 & (self.o.ready | ~self.o.valid)):
            digit = (tmp >> 60) & 0xf
            with m.Switch(digit):
                with m.Case(0, 1, 2, 3, 4, 5, 6, 7, 8, 9):
                    m.d.sync += self.o.data.eq(ord('0') + digit)
                with m.Case(10, 11, 12, 13, 14, 15):
                    m.d.sync += self.o.data.eq(ord('a') + (digit - 10))
            m.d.sync += [
                self.o.valid.eq(1),
                tmp.eq(tmp << 4),
                cnt.eq(cnt - 1)
            ]

        return m

import random

def write_stream(data, stream):
    async def process(ctx: SimulatorContext):
        for i, byte in enumerate(data):
            ctx.set(stream.valid, 1)
            ctx.set(stream.data, byte)
            while ctx.get(stream.ready) != 1:
                await ctx.tick()
            await ctx.tick()
            for _ in range(random.randint(0, 3)):
                ctx.set(stream.valid, 0)
                await ctx.tick()
        ctx.set(stream.valid, 0)
    return process

def read_stream(stream):
    async def process(ctx: SimulatorContext):
        ctx.set(stream.ready, 1)
        while True:
            if ctx.get(stream.valid):
                print(chr(ctx.get(stream.data)), end="")
            await ctx.tick()
    return process