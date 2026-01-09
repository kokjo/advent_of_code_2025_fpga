from amaranth import *
from amaranth.sim import *
from amaranth.lib.data import Struct, Enum
from amaranth.lib.memory import Memory, MemoryData
from amaranth_boards.ice40_hx8k_b_evn import ICE40HX8KBEVNPlatform
from utils import Stream, Harness, UartWrapper, read_stream, write_stream
from argparse import ArgumentParser, FileType

class PipelineRegister(Struct):
    ""
    en: 1
    addr: 8
    data: 64

class Solution(Elaboratable):
    def __init__(self):
        self.i = Stream(8)
        self.done = Signal()
        self.error = Signal()
        self.part_1 = Signal(64)
        self.part_2 = Signal(64)
    
    def elaborate(self, platform):
        m = Module()

        # Current sum of timelines per line
        sum = Signal(64)

        # Memory for timeline/beam data
        m.submodules.mem = mem = Memory(shape=64, depth=256, init=[0] * 256)
        rdport = mem.read_port()
        wrport = mem.write_port(domain = "sync")

        # Current line index
        addr = Signal(8)

        # Our window of timelines,
        # We have a sliding window of 3 timelines counters, this is enough as
        # spliting is a local change which only modifies 3 values(previous, current and next)
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
                    # 1. Setup next read from memory
                    m.d.sync += [
                        rdport.addr.eq(rdport.addr + 1),
                        rdport_delay[0].eq(0),
                        rdport_delay[1].eq(1),
                    ]

                    # 2. Writeback the newly calculated timeline counter when sliding out of window buffer
                    m.d.sync += [
                        wrport.en.eq(pipeline[0].en),
                        wrport.addr.eq(pipeline[0].addr),
                        wrport.data.eq(pipeline[0].data),
                    ]

                    # 3. Shift the pipeline forward
                    m.d.sync += [
                        pipeline[0].eq(pipeline[1]),
                        pipeline[1].en.eq(1),
                        pipeline[1].addr.eq(rdport.addr),
                        pipeline[1].data.eq(rdport.data + Mux(pipeline[2].en, pipeline[2].data, 0))
                        pipeline[2].en.eq(0),
                        pipeline[2].addr.eq(0),
                        pipeline[2].data.eq(0),
                    ]

                    # 4. Sum of the timelines for part 2
                    with m.If(pipeline[0].en):
                        m.d.sync += sum.eq(sum + pipeline[0].data)

                    # 5. Handle input data
                    with m.Switch(self.i.data):
                        # 5a. Nop
                        with m.Case(ord('.')):
                            # As this can be handled in a single cycle, ack the input immediately
                            m.d.comb += self.i.ready.eq(1)

                        # 5b. Beam start
                        with m.Case(ord("S")):
                            # As this can be handled in a single cycle, ack the input immediately
                            m.d.comb += self.i.ready.eq(1)

                            # Change pipeline data for current timeline to 1
                            m.d.sync += pipeline[1].data.eq(1)

                        # 5c. Split
                        with m.Case(ord('^')):
                            # As this can be handled in a single cycle, ack the input immediately
                            m.d.comb += self.i.ready.eq(1)

                            # Part 1: Count splits
                            with m.If(rdport.data != 0):
                                m.d.sync += self.part_1.eq(self.part_1 + 1)

                            # Split timelines
                            m.d.sync += [
                                pipeline[0].data.eq(rdport.data + pipeline[1].data),
                                pipeline[1].data.eq(Mux(pipeline[2].en, pipeline[2].data, 0)),
                                pipeline[2].en.eq(1),
                                pipeline[2].data.eq(rdport.data),
                            ]

                        # 5d. Newline
                        with m.Case(ord('\n')):
                            # Flush pipeline(2 cycles)
                            m.d.sync += pipeline[1].en.eq(0)
                            with m.If((pipeline[0].en == 0) & (pipeline[1].en == 0)):
                                # Acknowledge input, when pipeline is flushed
                                m.d.comb += self.i.ready.eq(1),

                                # Reset memory report counter(move to beginning)
                                m.d.sync += rdport.addr.eq(0)

                                # Check for double newline, this is our exit condition.
                                with m.If(rdport.addr == 0):
                                    m.next = "DONE"
                                with m.Else():
                                    # Part 2: Count timelines
                                    m.d.sync += [
                                        self.part_2.eq(sum),
                                        sum.eq(0)
                                    ]

                        # 5. Default case, move FSM to ERROR state.
                        with m.Default():
                            m.next = "ERROR"

            with m.State("DONE"):
                pass # Stuck, wait for reset

            with m.State("ERROR"):
                pass # Stuck, wait for reset

            # Expose status signals to harness
            m.d.comb += [
                self.done.eq(fsm.ongoing("DONE")),
                self.error.eq(fsm.ongoing("ERROR"))
            ]

        return m

def cmd_test(args):
    dut = Harness(Solution())
    sim = Simulator(dut)
    sim.add_clock(1e-6)
    sim.add_testbench(write_stream(args.data.read(), dut.i))
    sim.add_testbench(read_stream(dut.o))
    with sim.write_vcd(args.vcd):
        sim.run_until(args.time, run_passive=True)
    print()

def cmd_build(args):
    ICE40HX8KBEVNPlatform().build(UartWrapper(Harness(Solution())), do_program=args.program)

def main():
    parser = ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    build_parser = subparsers.add_parser("build")
    build_parser.set_defaults(func = cmd_build)
    build_parser.add_argument("--program", dest="program", default=False, action="store_true")
    test_parser = subparsers.add_parser("test")
    test_parser.set_defaults(func = cmd_test)
    test_parser.add_argument("--time", dest="time", type=float, default=1e-3)
    test_parser.add_argument("--vcd", dest="vcd", default="day7.vcd")
    test_parser.add_argument("--data", dest="data", default=None, type=FileType("rb"))
    args = parser.parse_args()
    return args.func(args)

if __name__ == "__main__": main()