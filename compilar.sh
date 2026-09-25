#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
export MPLCONFIGDIR="$PWD/tmp/matplotlib"
mkdir -p "$MPLCONFIGDIR"
python3 generar_datos.py
for pasada in 1 2 3; do
    pdflatex -interaction=nonstopmode -halt-on-error main.tex > "tmp/latex_${pasada}.log"
done
echo "PDF generado: $PWD/main.pdf"
