#!/usr/bin/env bash
# Medición automatizada en Wi-Fi: ./medir_wifi.sh [todos|trapecio|matrices] [--plan]
set -euo pipefail
export LC_ALL=C
cd -- "$(dirname -- "$0")"

seleccion=${1:-todos}
plan=${2:-}
if [[ $seleccion == --plan ]]; then seleccion=todos; plan=--plan; fi
case "$seleccion" in
    todos) experimentos=(trapecio matrices) ;;
    trapecio|matrices) experimentos=("$seleccion") ;;
    *) echo 'Uso: ./medir_wifi.sh [todos|trapecio|matrices] [--plan]' >&2; exit 2 ;;
esac
[[ $# -le 2 && ( -z $plan || $plan == --plan ) ]] || exit 2

if [[ $plan != --plan ]]; then
    mkdir -p resultados_wifi
    salida=$(mktemp -d "resultados_wifi/$(date +%Y%m%d_%H%M%S)_XXXXXX")
    echo 'experimento,tamano,procesos,T_Total' > "$salida/tiempos.csv"
    echo "Resultados Wi-Fi: $PWD/$salida"
fi

for experimento in "${experimentos[@]}"; do
    if [[ $experimento == trapecio ]]; then
        tamanos=(100000000 100000000000)
    else
        tamanos=(1024 2048 3072)
    fi
    for n in "${tamanos[@]}"; do
        for p in 1 24 48 72 96; do
            echo "./lanzar_wifi.sh $experimento $n $p"
            [[ $plan == --plan ]] && continue
            log="$salida/${experimento}_${n}_${p}.log"
            if ! ./lanzar_wifi.sh "$experimento" "$n" "$p" > "$log" 2>&1; then
                echo "Falló la ejecución Wi-Fi. Revisa $log" >&2; exit 1
            fi
            tiempo=$(sed -nE '/^RESULT_(TRAP|2D):/s/.*T_Total=([0-9]+\.[0-9]+),.*/\1/p' "$log")
            if [[ ! $tiempo =~ ^[0-9]+\.[0-9]+$ || ! $tiempo =~ [1-9] ]]; then
                echo "Tiempo ausente o inválido. Revisa $log" >&2; exit 1
            fi
            echo "$experimento,$n,$p,$tiempo" >> "$salida/tiempos.csv"
            echo "T_Total (Wi-Fi) = $tiempo segundos"
        done
    done
done

if [[ $plan != --plan ]]; then
    python3 graficar.py --red Wi-Fi "$salida/tiempos.csv"
fi
