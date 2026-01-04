from amaranth import *
from amaranth.sim import *
from amaranth.lib.data import Struct, Enum
from amaranth.lib.memory import Memory, MemoryData
from amaranth_boards.ice40_hx8k_b_evn import ICE40HX8KBEVNPlatform
from stream import Stream, HexConverter, read_stream, write_stream
from uart import UartWrapper

class PipelineRegister(Struct):
    en: 1
    addr: 8
    data: 64

class Solver(Elaboratable):
    def __init__(self):
        self.i = Stream(8)
        self.done = Signal()
        self.error = Signal()
        self.splits = Signal(64)
        self.timelines = Signal(64)
    
    def elaborate(self, platform):
        m = Module()

        # Current sum of timelines per line
        sum = Signal(64)

        # Memory for timeline/beam data, contains two sections of 256 words.
        m.submodules.mem = mem = Memory(shape=64, depth=256, init=[0] * 256)
        rdport = mem.read_port()
        wrport = mem.write_port(domain = "sync")

        # Current line index
        addr = Signal(8)

        # Our window of timelines,
        # We have a sliding window of 3 timelines counters this is enough as
        # spliting is a local change which only modifies at most 2 values over a distance of 3.
        # We need to keep the index of each timeline as well for when we are wrapping back to 0.

        pipeline = [Signal(PipelineRegister, name=f"pipeline_{i}") for i in range(3)]

        rdport_delay = [Signal(name=f"rdport_deplay_{i}") for i in range(2)]
        m.d.sync += [a.eq(b) for a, b in zip(rdport_delay, rdport_delay[1:])]

        m.d.sync += [
            rdport.en.eq(1),
            wrport.en.eq(0),
        ]

        with m.FSM("RESET") as fsm:
            # Clear first half of memory
            with m.State("RESET"):
                m.d.sync += [
                    wrport.en.eq(1),
                    wrport.addr.eq(wrport.addr + 1),
                    wrport.data.eq(0),
                ]
                with m.If(wrport.addr == 0xff):
                    m.next = "INPUT"
                    m.d.sync += [
                        rdport.addr.eq(0),
                        rdport_delay[1].eq(1),
                    ]
            # Process a input a byte at a time.
            with m.State("INPUT"):
                with m.If(self.i.valid & rdport_delay[0]):
                    # Handshake input byte
                    m.d.comb += self.i.ready.eq(1)
                    # setup next read from memory
                    m.d.sync += [
                        rdport.addr.eq(rdport.addr + 1),
                        rdport_delay[0].eq(0),
                        rdport_delay[1].eq(1),
                    ]
                    # Writeback the newly calculated timeline counter when sliding out of window buffer
                    m.d.sync += [
                        wrport.en.eq(pipeline[0].en),
                        wrport.addr.eq(pipeline[0].addr),
                        wrport.data.eq(pipeline[0].data),
                    ]

                    m.d.sync += [
                        pipeline[0].eq(pipeline[1]),
                        pipeline[1].en.eq(1),
                        pipeline[1].addr.eq(rdport.addr),
                        pipeline[2].en.eq(0),
                        pipeline[2].addr.eq(0),
                        pipeline[2].data.eq(0),
                    ]

                    # Sum of the timelines for part 2
                    with m.If(pipeline[0].en):
                        m.d.sync += sum.eq(sum + pipeline[0].data)

                    with m.Switch(self.i.data):
                        with m.Case(ord('.')): # Nop
                            m.d.sync += pipeline[1].data.eq(rdport.data + Mux(pipeline[2].en, pipeline[2].data, 0))
                        with m.Case(ord("S")): # Beam start
                            m.d.sync += pipeline[1].data.eq(1)
                        with m.Case(ord('^')): # Split
                            # Part 1: Count splits
                            with m.If(rdport.data != 0):
                                m.d.sync += self.splits.eq(self.splits + 1)
                            # Split timelines
                            m.d.sync += [
                                pipeline[0].data.eq(rdport.data + pipeline[1].data),
                                pipeline[1].data.eq(Mux(pipeline[2].en, pipeline[2].data, 0)),
                                pipeline[2].en.eq(1),
                                pipeline[2].data.eq(rdport.data),
                            ]
                        with m.Case(ord('\n')): # Newline
                            m.d.sync += pipeline[1].en.eq(0)
                            with m.If(pipeline[0].en | pipeline[1].en):
                                m.d.comb += self.i.ready.eq(0),
                            with m.Else():
                                m.d.sync += [
                                    pipeline[1].en.eq(0),
                                    rdport.addr.eq(0) # reset line
                                ]
                                with m.If(rdport.addr == 0): # Double newline: No more input, done!
                                    m.next = "DONE"
                                with m.Else():
                                    m.d.sync += [
                                        self.timelines.eq(sum),
                                        sum.eq(0)
                                    ]
                        with m.Default():
                            m.next = "ERROR"
            with m.State("DONE"):
                pass # Stuck, wait for reset
            with m.State("ERROR"):
                pass # Stuck, wait for reset

            m.d.comb += [
                self.done.eq(fsm.ongoing("DONE")),
                self.error.eq(fsm.ongoing("ERROR"))
            ]

        return m

class Solution(Elaboratable):
    def __init__(self):
        self.i = Stream(8)
        self.o = Stream(8)
    
    def elaborate(self, platform):
        m = Module()
        reset = Signal()
        m.submodules.solver = solver = ResetInserter(reset)(Solver())
        m.submodules.hexout = hexout = HexConverter()

        m.d.comb += self.i.connect(solver.i)
        m.d.comb += hexout.o.connect(self.o)

        # Handshake
        with m.If(hexout.i.ready):
            m.d.sync += hexout.i.valid.eq(0)

        with m.FSM("RUNNING"):
            with m.State("RUNNING"):
                with m.If(solver.done):
                    m.next = "PRINT PART 1"
            with m.State("PRINT PART 1"):
                with m.If(~hexout.i.valid):
                    m.d.sync += [
                        hexout.i.valid.eq(1),
                        hexout.i.data.eq(solver.splits)
                    ]
                    m.next = "PRINT PART 2"
            with m.State("PRINT PART 2"):
                with m.If(~hexout.i.valid):
                    m.d.sync += [
                        hexout.i.valid.eq(1),
                        hexout.i.data.eq(solver.timelines)
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
        sim.run_until(args.time, run_passive=True)
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
    test_parser.add_argument("--time", dest="time", type=float, default=1e-3)
    test_parser.add_argument("--vcd", dest="vcd", default=None)
    test_parser.add_argument("--data", dest="data", default=None, type=FileType("rb"))
    return parser.parse_args()

def main():
    args = parse_args()
    return args.func(args)

if __name__ == "__main__": main()