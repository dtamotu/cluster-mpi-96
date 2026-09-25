#!/usr/bin/env bash
# Lanzador por Wi-Fi (interfaz wlp129s0f0, red 10.7.134.0/23)
# Uso: ./lanzar_wifi.sh <trapecio|matrices> <tamaño> <1|24|48|72|96>
set -euo pipefail
export LC_ALL=C
unset DISPLAY
DIR=$(cd -- "$(dirname -- "$0")" && pwd)

if [[ $# != 3 ]]; then
    echo "Uso: $0 <trapecio|matrices> <tamaño> <1|24|48|72|96>" >&2
    exit 2
fi
experimento=$1
tamano=$2
procesos=$3
if [[ ! $tamano =~ ^[1-9][0-9]*$ ]]; then
    echo "El tamaño debe ser un entero positivo." >&2
    exit 2
fi

# Mapeo de hosts por Wi-Fi (IPs 10.7.134.x)
case "$procesos" in
     1) hosts='10.7.134.117:1' ;;
    24) hosts='10.7.134.117:24' ;;
    48) hosts='10.7.134.117:24,10.7.134.58:24' ;;
    72) hosts='10.7.134.117:24,10.7.134.58:24,10.7.134.59:24' ;;
    96) hosts='10.7.134.117:24,10.7.134.58:24,10.7.134.59:24,10.7.134.51:24' ;;
     *) echo "Procesos permitidos: 1, 24, 48, 72, 96" >&2; exit 2 ;;
esac

if (( tamano < procesos )); then
    echo "El tamaño debe ser al menos igual al número de procesos." >&2
    exit 2
fi
case "$experimento" in
    trapecio) programa=(/var/tmp/mpi_trapecio/trapecio "$tamano") ;;
    matrices) programa=(/var/tmp/mpi_bloques/mpi_matrix_2d "$tamano" 1d tiled 64) ;;
    *) echo "Experimento permitido: trapecio o matrices" >&2; exit 2 ;;
esac

# OpenMPI forzado a la subred Wi-Fi
comando=(mpirun -H "$hosts" -np "$procesos"
    --map-by slot --rank-by slot --bind-to core --report-bindings
    --mca plm_rsh_agent "ssh -F $DIR/ssh_config_wifi"
    --mca btl self,vader,tcp
    --mca btl_tcp_if_include 10.7.134.0/23
    --mca oob_tcp_if_include 10.7.134.0/23
    "${programa[@]}")

printf 'COMANDO (Wi-Fi): '; printf '%q ' "${comando[@]}"; printf '\n'
exec "${comando[@]}"
