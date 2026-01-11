open! Core
open! Hardcaml

module I : sig
  type 'a t =
    { clock : 'a
    ; reset : 'a
    ; input_valid : 'a
    ; input_data : 'a
    }
  [@@deriving hardcaml]
end

module O : sig
  type 'a t =
    { input_ready : 'a
    ; solver_done : 'a
    ; solver_error : 'a
    ; part_1 : 'a
    ; part_2 : 'a
    ; input_transfer_count : 'a
    } [@@deriving hardcaml]
end

val hierarchical : Scope.t -> Signal.t I.t -> Signal.t O.t