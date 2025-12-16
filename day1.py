from amaranth import *
from amaranth.sim import *
from amaranth_boards.ice40_hx8k_b_evn import ICE40HX8KBEVNPlatform
from stream import Stream
from uart import UartRx, UartTx

class Parser(Elaboratable):
    """Parser for day 1"""
    def __init__(self):
        self.i = Stream(8)
        self.o = Stream(16)
        self.done = Signal()
        self.clear = Signal()
        self.error = Signal()

    def elaborate(self, platform):
        m = Module()
        number = Signal(signed(16))
        invert = Signal()

        # Output handshake: Clear o.valid on o.ready
        with m.If(self.o.ready):
            m.d.sync += self.o.valid.eq(0)

        # Simple Input parsing state machine
        with m.FSM("READ LR") as fsm:
            # If 'R' or 'L': clear number signal, set invert signal, next state = READ NUMBER
            # If '\n': next state = DONE
            # Otherwise: next state = Error
            # Always accepts input(i.ready.eq(1)
            with m.State("READ LR"):
                m.d.comb += self.i.ready.eq(1)
                m.d.sync += number.eq(0)
                with m.If(self.i.valid):
                    with m.Switch(self.i.data):
                        with m.Case(ord('L')):
                            m.d.sync += invert.eq(1)
                            m.next = "READ NUMBER"
                        with m.Case(ord('R')):
                            m.d.sync += invert.eq(0)
                            m.next = "READ NUMBER"
                        with m.Case(ord('\n')):
                            m.next = "DONE"
                        with m.Default():
                            m.next = "ERROR"
            # If digit('0'-'9'): Accept input, number = 10*number + digit, next state = READ NUMBER
            # if '\n': Only Accept input if output is not stalled, next state = READ LR
            # Otherwise: next state = Error
            # Input conditionally accepted, can stall if output is stalling.
            with m.State("READ NUMBER"):
                with m.If(self.i.valid):
                    with m.Switch(self.i.data):
                        for digit in "0123456789":
                            with m.Case(ord(digit)):
                                m.d.comb += self.i.ready.eq(1)
                                m.d.sync += number.eq(10*number + int(digit))
                                m.next = "READ NUMBER"
                        with m.Case(ord('\n')):
                            with m.If(self.o.ready | ~self.o.valid):
                                m.d.comb += self.i.ready.eq(1)
                                m.d.sync += [
                                    self.o.valid.eq(1),
                                    self.o.data.eq(Mux(invert, -number, number)),
                                ]
                                m.next = "READ LR"
                        with m.Default():
                            m.d.comb += self.i.ready.eq(1)
                            m.next = "ERROR"
            with m.State("ERROR"):
                pass # stuck, wait for reset
            with m.State("DONE"):
                pass # stuck, wait for reset

            m.d.comb += [
                self.error.eq(fsm.ongoing("ERROR")),
                self.done.eq(fsm.ongoing("DONE") & ~self.o.valid),
            ]
        return m

class Dail(Elaboratable):
    """Dail implementation for day 1"""
    def __init__(self):
        self.i = Stream(16)
        self.busy = Signal()
        self.dail = Signal(8, init=50)
        self.part_1_clicks = Signal(16)
        self.part_2_clicks = Signal(16)

    def elaborate(self, platform):
        m = Module()
        tmp = Signal(signed(16))

        # This Dail implementaion is very slow, due to being implemented without deivsion using just simple counters.
        # However running at 12MHz we have a clock divider for a UART running at 115200 baud of 104.
        # Thus we have 1040 clocks per UART byte and we have at least 3 bytes per input number('L' or 'R', at least 1 number, '\n')
        # This means that we have 3120 clocks of headroom, which is pleanty to process this at line speed without any buffering.

        # Wait for input
        with m.If(tmp == 0):
            m.d.comb += self.i.ready.eq(1)
            with m.If(self.i.valid):
                m.d.sync += tmp.eq(self.i.data)

        # Rotate dail backwards
        with m.If(tmp < 0):
            m.d.sync += [
                tmp.eq(tmp + 1),
                self.dail.eq(Mux(self.dail == 0, 99, self.dail - 1)),
            ]

        # Rotate dail forwards
        with m.Elif(tmp > 0):
            m.d.sync += [
                tmp.eq(tmp - 1),
                self.dail.eq(Mux(self.dail == 99, 0, self.dail + 1)),
            ]
        
        # Part 1: Check if next dail position is 0 AND this is the last step in the current rotation
        with m.If(((tmp == 1) & (self.dail == 99)) | ((tmp == -1) & (self.dail == 1))):
            m.d.sync += self.part_1_clicks.eq(self.part_1_clicks + 1)

        # Part 2: Check if next dail position is 0 AND the dail is still rotating
        with m.If((tmp != 0) & (self.dail == 0)):
            m.d.sync += self.part_2_clicks.eq(self.part_2_clicks + 1)
                    
        m.d.comb += self.busy.eq(tmp != 0)
        return m

class HexConverter(Elaboratable):
    """ Simple Hex converter, accepts 32 bits of input, outputs 8 bit ascii characters"""
    def __init__(self):
        self.i = Stream(32)
        self.o = Stream(8)

    def elaborate(self, platform):
        m = Module()
        cnt = Signal(4)
        tmp = Signal(32)

        with m.If(self.o.ready):
            m.d.sync += self.o.valid.eq(0),

        with m.If(self.i.valid & (cnt == 0)):
            m.d.comb += self.i.ready.eq(1)
            m.d.sync += [
                cnt.eq(8),
                tmp.eq(self.i.data)
            ]

        with m.If(cnt != 0 & (self.o.ready | ~self.o.valid)):
            digit = (tmp >> 28) & 0xf
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


class Solution(Elaboratable):
    def __init__(self):
        self.i = Stream(8)
        self.o = Stream(8)

    def elaborate(self, platform):
        m = Module()
        reset = Signal()
        # Great feature of Amaranth here: Transforms
        # ResetInserter: rewrite a whole module(Parser and Dail) to use a reset signal
        # Amaranth also have a EnableInserter, which controls if the circut is running/enabled based on external signal.
        # Transforms can also besued for moving clock doamins
        # These transforms makes it possible to yank that kind of logic from modules and control it externally
        m.submodules.parser = parser = ResetInserter(reset)(Parser())
        m.submodules.dail = dail = ResetInserter(reset)(Dail())
        m.submodules.hexout = hexout = HexConverter()

        # Just chain the input/output interfaces of our modules together.
        m.d.comb += [
            self.i.connect(parser.i),
            parser.o.connect(dail.i),
            hexout.o.connect(self.o),
        ]

        # Handshake
        with m.If(hexout.i.ready):
            m.d.sync += hexout.i.valid.eq(0)

        # Trigger output(hexout) based on doneness and if dail is busy.
        # Also reset parser and dail, so that we are ready for our next problem input
        with m.If(parser.done & ~dail.busy & (hexout.i.ready | ~hexout.i.valid)):
            m.d.sync += [
                hexout.i.valid.eq(1),
                hexout.i.data.eq(dail.part_1_clicks),
            ]
            m.d.comb += reset.eq(1)

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
        return m

def write_stream(data, stream):
    async def process(ctx: SimulatorContext):
        for i, byte in enumerate(data):
            ctx.set(stream.valid, 1)
            ctx.set(stream.data, byte)
            while ctx.get(stream.ready) != 1:
                await ctx.tick()
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

def cmd_test(args):
    dut = Solution()
    sim = Simulator(dut)
    sim.add_clock(1e-6)
    sim.add_testbench(write_stream(args.data.read(), dut.i))
    sim.add_testbench(read_stream(dut.o))
    with sim.write_vcd(args.vcd):
        sim.run_until(1, run_passive=True)
    print()

def cmd_build(args):
    ICE40HX8KBEVNPlatform().build(UartWrapper(Solution()), do_program=args.program)

def parse_args():
    from argparse import ArgumentParser, FileType
    parser = ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    build_parser = subparsers.add_parser("build")
    build_parser.set_defaults(func = cmd_build)
    build_parser.add_argument("--program", dest="program", default=False, action="store_true")
    test_parser = subparsers.add_parser("test")
    test_parser.set_defaults(func = cmd_test)
    test_parser.add_argument("--vcd", dest="vcd", default=None)
    test_parser.add_argument("--data", dest="data", default=None, type=FileType("rb"))
    return parser.parse_args()

def main():
    args = parse_args()
    return args.func(args)

if __name__ == "__main__": main()
