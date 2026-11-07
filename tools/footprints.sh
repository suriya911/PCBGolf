#!/bin/sh
# Regenerate the connector/part footprints and re-align their 3D models.
# usage: tools/footprints.sh <easyeda download dir>
set -e
SRC=${1:-scratch/cand}
KP="$LOCALAPPDATA/Programs/KiCad/10.0/bin/python.exe"
python tools/make_footprints.py "$SRC"
"$KP" tools/align_models.py \
  USB_C_Receptacle_ShouHan_TYPE-C-24P-QT "$SRC"/lib_C2681555.3dshapes/USB-C-SMD_TYPE-C-24P-QT.wrl \
  microSD_Hirose_DM3D-SF "$SRC"/lib_C719027.3dshapes/TF-SMD_DM3D-SF.wrl \
  LED_Bicolor_Kingbright_APTB1612 "$(ls "$SRC"/lib_C6506889.3dshapes/*.wrl)" \
  SOT-563_DMG1026UV "$(ls "$SRC"/lib_C508194.3dshapes/*.wrl)" \
  SW_Panasonic_EVQ-P7B01P "$(ls "$SRC"/lib_C485515.3dshapes/*.wrl)"
