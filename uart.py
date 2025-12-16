from amaranth import *
from amaranth.lib.cdc import FFSynchronizer
from stream import Stream

class UartRx(Elaboratable):
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

class TestDesign(Elaboratable):
    def __init__(self):
        self.loopback = Signal()
        self.uart_tx = UartTx(self.loopback, clkdiv_reset=16)
        self.uart_rx = UartRx(self.loopback, clkdiv_reset=16)

    def elaborate(self, platform):
        m = Module()
        m.submodules.uart_tx = uart_tx = self.uart_tx
        m.submodules.uart_rx = uart_rx = self.uart_rx
        
        with m.If(uart_tx.i.ready):
            m.d.sync += uart_tx.i.valid.eq(0)

        cnt = Signal(8)
        m.d.sync += cnt.eq(cnt - 1)

        with m.If(cnt == 0):
            m.d.comb += uart_rx.o.ready.eq(1)
            with m.If(~uart_tx.i.valid):
                m.d.sync += [
                    uart_tx.i.valid.eq(1),
                    uart_tx.i.data.eq(uart_tx.i.data + 1),
                ]
        return m

if __name__ == '__main__':
    from amaranth.sim import *
    dut = TestDesign()
    sim = Simulator(dut)
    sim.add_clock(1e-6)
    with sim.write_vcd("uart_tx.vcd"):
        sim.run_until(1000e-6, run_passive=True)


