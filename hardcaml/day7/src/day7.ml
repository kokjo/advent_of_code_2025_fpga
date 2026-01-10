open! Core
open! Hardcaml
open! Signal

module I = struct
  type 'a t =
    { clock: 'a
    ; reset: 'a
    ; input_valid : 'a
    ; input_data : 'a [@bits 8]
    }
  [@@deriving hardcaml]
end

module O = struct
  type 'a t =
    { input_ready : 'a
    ; solver_done : 'a
    ; solver_error : 'a
    ; part_1 : 'a [@bits 64]
    ; part_2 : 'a [@bits 64]
    } [@@deriving hardcaml]
end

module States = struct
  type t =
    | Reset
    | Input
    | Done
    | Error
  [@@deriving sexp_of, compare ~localize, enumerate]
end

let create _ ({clock ; reset;  input_valid ; input_data } : _ I.t ) : _ O.t =
    let open Always in 
    let spec = Reg_spec.create ~reset ~clock () in
    let sm = State_machine.create (module States) spec in
    let wrport_en = Variable.reg spec ~width:1 in
    let wrport_addr = Variable.reg spec ~width:8 in
    let wrport_data = Variable.reg spec ~width:64 in
    let rdport_valid = Variable.reg spec ~width:1 in
    let rdport_addr = Variable.reg spec ~width:8 in
    let mem = Ram.create ~collision_mode:Read_before_write ~size:256 ~write_ports:[|
        { write_clock = clock
        ; write_enable = wrport_en.value
        ; write_address = wrport_addr.value
        ; write_data = wrport_data.value
        }
    |] ~read_ports: [|
        { read_clock = clock
        ; read_enable = vdd
        ; read_address = rdport_addr.value }
    |] () in
    let rdport_data = mem.(0) in
    let input_ready = Variable.wire ~default:(zero 1) () in
    let solver_done = Variable.wire ~default:(zero 1) () in
    let solver_error = Variable.wire ~default:(zero 1) () in
    let part_1 = Variable.reg spec ~width:64 in
    let part_2 = Variable.reg spec ~width:64 in
    let pipeline_0_valid = Variable.reg spec ~width:1 in
    let pipeline_0_addr = Variable.reg spec ~width:8 in
    let pipeline_0_data = Variable.reg spec ~width:64 in
    let pipeline_1_valid = Variable.reg spec ~width:1 in
    let pipeline_1_addr = Variable.reg spec ~width:8 in
    let pipeline_1_data = Variable.reg spec ~width:64 in
    let pipeline_2_valid = Variable.reg spec ~width:1 in
    let pipeline_2_data = Variable.reg spec ~width:64 in
    let part_2_sum = Variable.reg spec ~width:64 in
    compile 
        [ rdport_valid <-- vdd
        ; sm.switch
            (* Clear timeline memory on reset *)
            [ (Reset, 
                [ wrport_en <-- vdd
                ; if_ (wrport_addr.value ==: Signal.of_int_trunc 0xff ~width:8)
                    [ rdport_addr <-- zero 8
                    ; rdport_valid <-- vdd
                    ; sm.set_next Input
                    ]
                    [ wrport_en <-- one 1
                    ; wrport_addr <-- wrport_addr.value +: one 8
                    ; wrport_data <-- zero 64
                    ]
            ])
            ; (Input, [
                when_ (input_valid &: rdport_valid.value)
                    (* Setup report for next read *)
                    [ rdport_addr <-- rdport_addr.value +: one 8
                    ; rdport_valid <-- gnd
                    (* Write previous timeline data into memory *)
                    ; wrport_en <-- pipeline_0_valid.value
                    ; wrport_addr <-- pipeline_0_addr.value
                    ; wrport_data <-- pipeline_0_data.value
                    (* previous <-- current *)
                    ; pipeline_0_valid <-- pipeline_1_valid.value
                    ; pipeline_0_addr <-- pipeline_1_addr.value
                    ; pipeline_0_data <-- pipeline_1_data.value
                    (* current <-- memory + next *)
                    ; pipeline_1_valid <-- vdd
                    ; pipeline_1_addr <-- rdport_addr.value
                    ; pipeline_1_data <-- rdport_data +: mux2 pipeline_2_valid.value pipeline_2_data.value (zero 64)
                    (* clear next *)
                    ; pipeline_2_valid <-- gnd
                    ; pipeline_2_data <-- zero 64
                    ; when_ pipeline_0_valid.value 
                        [ part_2_sum <-- part_2_sum.value +: pipeline_0_data.value ]
                    (* Process challenge input bytes *)
                    ; switch input_data
                        [ (Signal.of_char '.',
                            [ input_ready <-- vdd
                            ])
                        ; (Signal.of_char 'S',
                            [ input_ready <-- vdd
                            ; pipeline_1_data <-- one 64
                            ])
                        ; (Signal.of_char '^', 
                            [ input_ready <-- vdd
                            ; pipeline_0_data <-- pipeline_1_data.value +: rdport_data
                            ; pipeline_1_data <-- mux2 pipeline_2_valid.value pipeline_2_data.value (zero 64)
                            ; pipeline_2_valid <-- vdd
                            ; pipeline_2_data <-- rdport_data
                            ; when_ (rdport_data >: zero 64)
                                [ part_1 <-- part_1.value +: one 64]
                            ])
                        ; (Signal.of_char '\n', 
                            [ part_2 <-- part_2_sum.value
                            ; when_ (rdport_addr.value ==: zero 8)
                                [ sm.set_next Done ]
                            ])
                        ]
                    ]
            ])
            ; (Done, [solver_done <-- vdd])
            ; (Error, [solver_error <-- vdd])
            ]
        ;
        ];
    { input_ready = input_ready.value
    ; solver_done = solver_done.value
    ; solver_error = solver_error.value
    ; part_1 = part_1.value
    ; part_2 = part_2.value
    }
;;

let hierarchical scope =
  let module Scoped = Hierarchy.In_scope (I) (O) in
  Scoped.hierarchical ~scope ~name:"day7" create
;;