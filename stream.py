from amaranth import *
from amaranth.hdl.rec import DIR_FANIN, DIR_FANOUT

class Stream(Record):
    def __init__(self, width=8, src_loc_at=0):
        super().__init__([
            ("valid", 1, DIR_FANOUT),
            ("ready", 1, DIR_FANIN),
            ("data", width, DIR_FANOUT)
        ], src_loc_at=src_loc_at+1)
