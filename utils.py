from amaranth import *
from amaranth.lib.cdc import FFSynchronizer
from amaranth.hdl.rec import DIR_FANIN, DIR_FANOUT
from amaranth.sim import SimulatorContext
from amaranth.build import ResourceError

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
                cnt.eq(18),
                tmp.eq(self.i.data)
            ]

        with m.If((cnt > 2) & ~self.o.valid):
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
        with m.If((cnt == 2) & ~self.o.valid):
            m.d.sync += [
                self.o.valid.eq(1),
                self.o.data.eq(ord('\r')),
                cnt.eq(cnt - 1)
            ]
        with m.If((cnt == 1) & ~self.o.valid):
            m.d.sync += [
                self.o.valid.eq(1),
                self.o.data.eq(ord('\n')),
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
            # for _ in range(random.randint(0, 3)):
            #     ctx.set(stream.valid, 0)
            #     await ctx.tick()
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

class UartRx(Elaboratable):
    """Basic UART RX module"""
    def __init__(self, rx, clkdiv_width = 16, clkdiv_reset = int(12e6 / 9600)-1):
        self.clkdiv = Signal(clkdiv_width, reset=clkdiv_reset)
        self.rx = rx
        self.o = Stream()

    def elaborate(self, platform):
        m = Module()

        rx = Signal()
        m.submodules.ffsync = ffsync = FFSynchronizer(self.rx, rx)

        with m.If(self.o.ready):
            m.d.sync += self.o.valid.eq(0)

        clkcnt = Signal.like(self.clkdiv)
        m.d.sync += clkcnt.eq(Mux(clkcnt == 0, self.clkdiv, clkcnt - 1))

        bitcnt = Signal(range(9))

        pattern = Signal(8)
        with m.FSM() as f:
            with m.State("IDLE"):
                with m.If(rx == 0):
                    m.d.sync += [
                        clkcnt.eq(self.clkdiv >> 1),
                        bitcnt.eq(7),
                    ]
                    m.next = "STARTBIT"

            with m.State("STARTBIT"):
                with m.If(clkcnt == 0):
                    m.next = "DATABIT"

            with m.State("DATABIT"):
                with m.If(clkcnt == 0):
                    m.d.sync += [
                        pattern.eq(Cat(pattern[1:], rx)),
                        bitcnt.eq(bitcnt - 1),
                    ]
                    with m.If(bitcnt == 0):
                        m.next = "STOPBIT"

            with m.State("STOPBIT"):
                with m.If(clkcnt == 0):
                    with m.If(self.o.ready | ~self.o.valid):
                        m.d.sync += [
                            self.o.valid.eq(1),
                            self.o.data.eq(pattern),
                        ]
                    m.next = "IDLE"
                
        return m

class UartTx(Elaboratable):
    """Basic UART TX module"""
    def __init__(self, tx, clkdiv_width=16, clkdiv_reset = int(12e6 / 9600)-1):
        self.clkdiv = Signal(clkdiv_width, reset=clkdiv_reset)
        self.tx = tx
        self.i = Stream()

    def elaborate(self, platform):
        m = Module()
        
        pattern = Signal(9, reset=0x1ff)
        bitcnt = Signal(4)

        clkcnt = Signal.like(self.clkdiv)
        m.d.sync += clkcnt.eq(Mux(clkcnt == 0, self.clkdiv, clkcnt - 1))

        with m.FSM() as f:
            with m.State("IDLE"):
                m.d.comb += self.i.ready.eq(1)
                with m.If(self.i.valid):
                    m.d.sync += [
                        pattern.eq(Cat(Const(0, 1), self.i.data)),
                        bitcnt.eq(9),
                        clkcnt.eq(self.clkdiv)
                    ]
                    m.next = "DATA"

            with m.State("DATA"):
                with m.If(clkcnt == 0):
                    m.d.sync += [
                        pattern.eq(Cat(pattern[1:], Const(1, 1))),
                        bitcnt.eq(bitcnt - 1)
                    ]
                    with m.If(bitcnt == 0):
                        m.next = "IDLE"

        m.d.comb += self.tx.eq(pattern[0])
        
        return m

class Blinker(Elaboratable):
    def __init__(self, pin, start=240000, limit=120000):
        self.pin = pin
        self.stb = Signal()
    def elaborate(self, platform):
        m = Module()

        limit = int(platform.default_clk_frequency // 50)
        start = limit * 4

        count = Signal(24)
        m.d.sync += self.pin.eq(count <= limit)
        with m.If(count != 0):
            m.d.sync += count.eq(count - 1)
        with m.Else():
            with m.If(self.stb):
                m.d.sync += count.eq(start)

        return m

class UartWrapper(Elaboratable):
    """ Simple UART wrapper for running on actual hardware"""
    def __init__(self, inner):
        self.inner = inner

    def elaborate(self, platform):
        m = Module()

        uart = platform.request("uart")
        m.submodules.uart_rx = uart_rx = UartRx(uart.rx.i)
        m.submodules.uart_tx = uart_tx = UartTx(uart.tx.o)
        m.submodules.inner = inner = self.inner
        m.d.comb += [
            uart_rx.o.connect(inner.i),
            inner.o.connect(uart_tx.i),
        ]

        blinkies = [
            uart_rx.o.valid & uart_rx.o.ready,  # TX transfers
            uart_tx.i.valid & uart_tx.i.ready,  # RX transfers
            self.inner.solution.done,           # Done
            self.inner.solution.error,          # Error
            1,                                  # Running
        ]

        for i, expr in enumerate(blinkies):
            try:
                led = platform.request("led", i)
                blinker = Blinker(led.o)
                m.submodules += blinker
                m.d.comb += blinker.stb.eq(expr)
            except ResourceError:
                pass # No more leds, let it fail. leds are optional.

        return m

class Harness(Elaboratable):
    def __init__(self, solution):
        self.i = Stream(8)
        self.o = Stream(8)
        self.solution = solution
    
    def elaborate(self, platform):
        m = Module()

        reset = Signal()
        m.submodules.solution = solution = ResetInserter(reset)(self.solution)
        m.submodules.hexout = hexout = HexConverter()

        m.d.comb += [
            self.i.connect(solution.i),
            hexout.o.connect(self.o)
        ]

        # Handshake for hexout
        with m.If(hexout.i.ready):
            m.d.sync += hexout.i.valid.eq(0)

        with m.FSM("RUNNING"):
            with m.State("RUNNING"):
                with m.If(solution.done):
                    m.next = "PRINT PART 1"
                with m.If(solution.error):
                    m.next = "PRINT ERROR"
            with m.State("PRINT PART 1"):
                with m.If(~hexout.i.valid):
                    m.d.sync += [
                        hexout.i.valid.eq(1),
                        hexout.i.data.eq(solution.part_1)
                    ]
                    m.next = "PRINT PART 2"
            with m.State("PRINT PART 2"):
                with m.If(~hexout.i.valid):
                    m.d.sync += [
                        hexout.i.valid.eq(1),
                        hexout.i.data.eq(solution.part_2)
                    ]
                    m.d.comb += reset.eq(1)
                    m.next = "RUNNING"
            with m.State("PRINT ERROR"):
                with m.If(~hexout.i.valid):
                    m.d.sync += [
                        hexout.i.valid.eq(1),
                        hexout.i.data.eq(0xdeadbeefdeadbeef)
                    ]
                    m.d.comb += reset.eq(1)
                    m.next = "RUNNING"

        return m