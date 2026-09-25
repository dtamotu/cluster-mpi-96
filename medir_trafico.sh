#!/usr/bin/env bash
# Una prueba opcional. No se ejecuto para generar los datos de este informe.
set -euo pipefail
export LC_ALL=C
if [[ $# != 4 ]]; then
    echo "Uso: $0 <ethernet|wifi> <trapecio|matrices> <tamano> <1|24|48|72|96>" >&2
    exit 2
fi
red=$1
experimento=$2
tamano=$3
procesos=$4
proyecto=/home/alumno16/experimentos_96
case "$red" in
    ethernet) interfaz=enp128s31f6; lanzador=lanzar.sh ;;
    wifi) interfaz=wlp129s0f0; lanzador=lanzar_wifi.sh ;;
    *) echo "Red no valida" >&2; exit 2 ;;
esac
[[ $experimento == trapecio || $experimento == matrices ]] || exit 2
[[ $tamano =~ ^[1-9][0-9]*$ ]] || exit 2
case "$procesos" in 1|24|48|72|96) ;; *) exit 2 ;; esac
salida=$(mktemp -d "$proyecto/trafico_${red}_$(date +%Y%m%d_%H%M%S)_XXXXXX")
snapshot() {
    local nombre ip valor
    valor=$(cat "/sys/class/net/$interfaz/statistics/tx_bytes")
    [[ $valor =~ ^[0-9]+$ ]] || return 1
    printf 'servidor\t%s\n' "$valor"
    for nombre_ip in workers1:10.7.50.203 workers2:10.7.50.201 workers4:10.7.50.204; do
        nombre=${nombre_ip%%:*}
        ip=${nombre_ip#*:}
        valor=$(ssh -F "$proyecto/ssh_config" "$ip" \
            "cat /sys/class/net/$interfaz/statistics/tx_bytes")
        [[ $valor =~ ^[0-9]+$ ]] || return 1
        printf '%s\t%s\n' "$nombre" "$valor"
    done
}
snapshot > "$salida/antes.tsv"
"$proyecto/$lanzador" "$experimento" "$tamano" "$procesos" \
    > "$salida/ejecucion.log" 2>&1
snapshot > "$salida/despues.tsv"
awk 'BEGIN { OFS=","; print "nodo,tx_bytes,tx_MB" }
     NR==FNR { antes[$1]=$2; next }
     { d=$2-antes[$1]; if(d<0) { exit 2 }; total+=d;
       printf "%s,%.0f,%.6f\n", $1,d,d/1000000 }
     END { printf "TOTAL,%.0f,%.6f\n",total,total/1000000 }' \
    "$salida/antes.tsv" "$salida/despues.tsv" > "$salida/trafico.csv"
echo "Datos de esta nueva ejecucion: $salida"
cat "$salida/trafico.csv"
