#!/usr/bin/env bash
# Una prueba: ./lanzar.sh trapecio 100000000 96
#            ./lanzar.sh matrices 3072 96
set -euo pipefail
export LC_ALL=C
# Las pruebas no usan ventanas; evita avisos de autorización gráfica de MPI.
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

# Se añade una computadora completa en cada configuración.
case "$procesos" in
     1) hosts='10.7.50.202:1' ;;
    24) hosts='10.7.50.202:24' ;;
    48) hosts='10.7.50.202:24,10.7.50.203:24' ;;
    72) hosts='10.7.50.202:24,10.7.50.203:24,10.7.50.201:24' ;;
    96) hosts='10.7.50.202:24,10.7.50.203:24,10.7.50.201:24,10.7.50.204:24' ;;
     *) echo "Procesos permitidos: 1, 24, 48, 72, 96" >&2; exit 2 ;;
esac

# Evita tramos vacíos en el programa actual del trapecio.
if (( tamano < procesos )); then
    echo "El tamaño debe ser al menos igual al número de procesos." >&2
    exit 2
fi
case "$experimento" in
    trapecio) programa=(/var/tmp/mpi_trapecio/trapecio "$tamano") ;;
    matrices) programa=(/var/tmp/mpi_bloques/mpi_matrix_2d "$tamano" 1d tiled 64) ;;
    *) echo "Experimento permitido: trapecio o matrices" >&2; exit 2 ;;
esac

# Un proceso por núcleo, llenando cada nodo antes del siguiente.
# SSH y comunicaciones MPI utilizan Ethernet. La afinidad queda en la salida.
comando=(mpirun -H "$hosts" -np "$procesos"
    --map-by slot --rank-by slot --bind-to core --report-bindings
    --mca plm_rsh_agent "ssh -F $DIR/ssh_config"
    --mca btl self,vader,tcp
    --mca btl_tcp_if_include 10.7.50.0/24
    --mca oob_tcp_if_include 10.7.50.0/24
    "${programa[@]}")

printf 'COMANDO: '; printf '%q ' "${comando[@]}"; printf '\n'
# T_Total lo mide el programa C con MPI_Wtime.
exec "${comando[@]}"
