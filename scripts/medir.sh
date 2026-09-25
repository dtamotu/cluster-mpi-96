#!/usr/bin/env bash
# Uso: ./medir.sh [todos|trapecio|matrices] [--plan]
set -euo pipefail
export LC_ALL=C
cd -- "$(dirname -- "$0")"

seleccion=${1:-todos}
plan=${2:-}
if [[ $seleccion == --plan ]]; then seleccion=todos; plan=--plan; fi
case "$seleccion" in
    todos) experimentos=(trapecio matrices) ;;
    trapecio|matrices) experimentos=("$seleccion") ;;
    *) echo 'Uso: ./medir.sh [todos|trapecio|matrices] [--plan]' >&2; exit 2 ;;
esac
[[ $# -le 2 && ( -z $plan || $plan == --plan ) ]] || exit 2

if [[ $plan != --plan ]]; then
    mkdir -p resultados
    salida=$(mktemp -d "resultados/$(date +%Y%m%d_%H%M%S)_XXXXXX")
    echo 'experimento,tamano,procesos,T_Total' > "$salida/tiempos.csv"
    echo "Resultados: $PWD/$salida"
fi

for experimento in "${experimentos[@]}"; do
    if [[ $experimento == trapecio ]]; then
        tamanos=(100000000 100000000000)
    else
        tamanos=(1024 2048 3072)
    fi
    for n in "${tamanos[@]}"; do
        for p in 1 24 48 72 96; do
            echo "./lanzar.sh $experimento $n $p"
            [[ $plan == --plan ]] && continue
            log="$salida/${experimento}_${n}_${p}.log"
            if ! ./lanzar.sh "$experimento" "$n" "$p" > "$log" 2>&1; then
                echo "Falló la ejecución. Revisa $log" >&2; exit 1
            fi
            # Extrae T_Total de la línea RESULT que imprime el programa C.
            tiempo=$(sed -nE '/^RESULT_(TRAP|2D):/s/.*T_Total=([0-9]+\.[0-9]+),.*/\1/p' "$log")
            if [[ ! $tiempo =~ ^[0-9]+\.[0-9]+$ || ! $tiempo =~ [1-9] ]]; then
                echo "Tiempo ausente o inválido. Revisa $log" >&2; exit 1
            fi
            echo "$experimento,$n,$p,$tiempo" >> "$salida/tiempos.csv"
            echo "T_Total = $tiempo segundos"
        done
    done
done

# Al terminar correctamente, calcula las métricas y genera los gráficos.
if [[ $plan != --plan ]]; then
    python3 graficar.py "$salida/tiempos.csv"
fi
