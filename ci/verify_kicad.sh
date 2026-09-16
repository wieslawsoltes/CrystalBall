#!/usr/bin/env bash
set -euo pipefail
mkdir -p verification/kicad manufacturing/cam-native
kicad-cli version | tee verification/kicad/version.txt
grep -E '^9\.0\.9' verification/kicad/version.txt
git -c safe.directory="$PWD" rev-parse HEAD >verification/kicad/COMMIT.txt
set +e
kicad-cli sch erc --format json --severity-all --exit-code-violations -o verification/kicad/erc.json hardware/aether-carrier.kicad_sch >verification/kicad/erc.log 2>&1
ERC=$?
kicad-cli pcb drc --format json --severity-all --schematic-parity --exit-code-violations -o verification/kicad/drc.json hardware/aether-carrier.kicad_pcb >verification/kicad/drc.log 2>&1
DRC=$?
kicad-cli sch export netlist -o verification/kicad/kicad.net hardware/aether-carrier.kicad_sch >verification/kicad/netlist.log 2>&1
NET=$?
set -e
printf 'ERC=%s\nDRC=%s\nNETLIST=%s\n' "$ERC" "$DRC" "$NET" | tee verification/kicad/exit-codes.txt
test "$ERC" = 0 && test "$DRC" = 0 && test "$NET" = 0
B=hardware/aether-carrier.kicad_pcb
O=manufacturing/cam-native
kicad-cli pcb export gerbers -l F.Cu,B.Cu,F.Mask,B.Mask,F.SilkS,Edge.Cuts -o "$O/" "$B"
kicad-cli pcb export drill --format excellon --excellon-separate-th --generate-map --map-format pdf -o "$O/" "$B"
kicad-cli pcb export ipcd356 -o "$O/aether-carrier.d356" "$B"
kicad-cli pcb export pos --format csv --units mm --side front --exclude-dnp -o "$O/positions-reference.csv" "$B"
kicad-cli sch export pdf -o "$O/schematics.pdf" hardware/aether-carrier.kicad_sch
kicad-cli pcb export svg -l F.SilkS,F.Fab,Edge.Cuts --page-size-mode 2 -o "$O/component-side.svg" "$B"
printf 'ENGINEERING CAM CANDIDATE. NOT RELEASED FOR PRODUCTION.\nNative KiCad exports: do not mix with hardware/fabrication custom exports.\nHand assembly only. Position data is a reference, not a qualified placement recipe.\nVerify supplier footprints, copper weight, polarity, drill plating, legend and tolerances.\n' >"$O/READ-BEFORE-ORDERING.txt"
find "$O" -type f -print0 | sort -z | xargs -0 sha256sum >verification/kicad/CAM-SHA256.txt
