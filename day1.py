from amaranth import *
from amaranth.sim import *
from amaranth_boards.ice40_hx8k_b_evn import ICE40HX8KBEVNPlatform
from stream import Stream, HexConverter, read_stream, write_stream
from uart import UartWrapper

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
                pass # Stuck, wait for reset
            with m.State("DONE"):
                pass # Stuck, wait for reset

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
        # The check (tmp == 0) & (self.dail == 0) will not work as we can be stuck at tmp == 0 for many cycles while waiting for input
        with m.If(((tmp == 1) & (self.dail == 99)) | ((tmp == -1) & (self.dail == 1))):
            m.d.sync += self.part_1_clicks.eq(self.part_1_clicks + 1)

        # Part 2: Check if next dail position is 0 AND the dail is still rotating
        with m.If((tmp != 0) & (self.dail == 0)):
            m.d.sync += self.part_2_clicks.eq(self.part_2_clicks + 1)
                    
        m.d.comb += self.busy.eq(tmp != 0)
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

        with m.FSM("RUNNING"):
            with m.State("RUNNING"):
                with m.If(self.parser.done & ~dail.busy):
                    m.next = "PRINT PART 1"
            with m.State("PRINT PART 1"):
                with m.If(~hexout.i.valid):
                    m.d.sync += [
                        hexout.i.valid.eq(1),
                        hexout.i.data.eq(dail.part_1_clicks),
                    ]
                    m.next = "PRINT PART 2"
            with m.State("PRINT PART 2"):
                with m.If(~hexout.i.valid):
                    m.d.sync += [
                        hexout.i.valid.eq(1),
                        hexout.i.data.eq(dail.part_2_clicks),
                    ]
                    m.d.comb += reset.eq(1)
                    m.next = "RUNNING"
            
        return m

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
