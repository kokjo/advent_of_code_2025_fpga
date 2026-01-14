open! Core
open! Hardcaml
open! Hardcaml_waveterm
open! Hardcaml_test_harness

module Day7 = Advent_of_code_2025_day_7.Day7
module Harness = Cyclesim_harness.Make (Day7.I) (Day7.O)

let ( <--. ) = Bits.( <--. )

let day7_example_data = [%blob "7_example"];;
let day7_actual_data = [%blob "7_actual"];;

let day7_testbench (challenge_data) (sim : Harness.Sim.t) = 
  let inputs = Cyclesim.inputs sim in
  let outputs = Cyclesim.outputs sim in
  let cycle ?n () = Cyclesim.cycle ?n sim in
  let send_byte byte = 
    inputs.input_data <--. byte;
    inputs.input_valid <--. 1;
    while not (Bits.to_bool !(outputs.input_ready)) do
      cycle ();
    done;
    cycle ();
    inputs.input_valid <--. 0;
  in
  let challenge_data = String.to_list challenge_data in
  List.iter challenge_data ~f:(fun x -> send_byte (Char.to_int x));
  cycle ~n:3 ();
  let solver_done = Bits.to_unsigned_int !(outputs.solver_done) in
  let solver_error = Bits.to_unsigned_int !(outputs.solver_error) in
  let part_1 = Bits.to_unsigned_int !(outputs.part_1) in
  let part_2 = Bits.to_unsigned_int !(outputs.part_2) in
  print_s [%message (solver_done : int)];
  print_s [%message (solver_error : int)];
  print_s [%message (part_1 : int)];
  print_s [%message (part_2 : int)];
;;

let waves_config = Waves_config.no_waves
(* let waves_config = Waves_config.to_directory "/tmp" |> Waves_config.as_wavefile_format ~format:Vcd *)

let%expect_test "Test Day7 works on example input" =
  Harness.run_advanced ~waves_config ~create:Day7.hierarchical (day7_testbench day7_example_data);
  [%expect {|
    (solver_done 1)
    (solver_error 0)
    (part_1 21)
    (part_2 40)
  |}]

let%expect_test "Test Day7 works on actual input" =
  Harness.run_advanced  ~waves_config ~create:Day7.hierarchical (day7_testbench day7_actual_data);
  [%expect {|
    (solver_done 1)
    (solver_error 0)
    (part_1 1642)
    (part_2 47274292756692)
  |}]

let%expect_test "Test Day7 errors on invalid input" =
  Harness.run_advanced ~timeout:1000 ~waves_config ~create:Day7.hierarchical (day7_testbench ".S\nA");
  [%expect {|
    (solver_done 0)
    (solver_error 1)
    (part_1 0)
    (part_2 0)
    |}]