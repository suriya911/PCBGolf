#!/bin/sh
# Rebuild all three boards for a given size: floorplan -> generate -> place -> render.
# usage: tools/stack.sh <side_mm> <netlist>
set -e
S=$1; NET=${2:-scratch/cur.net}
KP="$LOCALAPPDATA/Programs/KiCad/10.0/bin/python.exe"
CLI="$LOCALAPPDATA/Programs/KiCad/10.0/bin/kicad-cli.exe"
python tools/floorplan.py "$S"
"$KP" tools/plan_risers.py "$NET" "$S" 2>/dev/null | grep -E "^P[0-9]: |no room" | sed "s/^/  riser /"
for b in B0 B1 B2; do
  "$KP" tools/build_board.py "$NET" $b placement/$b.json pcbgolf_$b.kicad_pcb 0.6 placement/risers.json > /dev/null
  printf "%s: " $b; "$KP" tools/place.py pcbgolf_$b.kicad_pcb placement/$b.json
  "$CLI" pcb render -o scratch/${b}_top.png -w 900 -h 900 --side top pcbgolf_$b.kicad_pcb > /dev/null 2>&1 || true
done
