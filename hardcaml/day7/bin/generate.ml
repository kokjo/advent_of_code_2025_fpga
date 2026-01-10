open! Core
open! Hardcaml
open! Advent_of_code_2025_day_7

let generate_day7_rtl () =
  let module C = Circuit.With_interface (Day7.I) (Day7.O) in
  let scope = Scope.create ~auto_label_hierarchical_ports:true () in
  let circuit = C.create_exn ~name:"day7_top" (Day7.hierarchical scope) in
  let rtl_circuits =
    Rtl.create ~database:(Scope.circuit_database scope) Verilog [ circuit ]
  in
  let rtl = Rtl.full_hierarchy rtl_circuits |> Rope.to_string in
  print_endline rtl
;;

let day7_rtl_command =
  Command.basic
    ~summary:""
    [%map_open.Command
      let () = return () in
      fun () -> generate_day7_rtl ()]
;;

let () =
  Command_unix.run
    (Command.group ~summary:"" [ "day7", day7_rtl_command ])
;;