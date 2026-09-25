#!/usr/bin/env python3
"""Compara dos archivos tiempos.csv: uno de Ethernet y uno de Wi-Fi."""
import argparse
import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

PROCESOS = [1, 24, 48, 72, 96]


def cargar(csv_path):
    datos = {}
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for fila in reader:
            e = fila["experimento"]
            n = int(fila["tamano"])
            p = int(fila["procesos"])
            t = float(fila["T_Total"])
            datos[(e, n, p)] = t
    return datos


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_eth", type=Path, help="CSV de resultados por Ethernet")
    parser.add_argument("csv_wifi", type=Path, help="CSV de resultados por Wi-Fi")
    parser.add_argument("--salida", type=Path, default=Path("comparacion_eth_vs_wifi"),
                        help="Directorio donde guardar tablas y gráficos")
    args = parser.parse_args()

    eth = cargar(args.csv_eth)
    wifi = cargar(args.csv_wifi)
    args.salida.mkdir(exist_ok=True, parents=True)

    claves = sorted(set(eth.keys()) & set(wifi.keys()))
    if not claves:
        print("No hay configuraciones coincidentes entre ambos CSV.")
        return

    # Generar tabla CSV comparativa
    tabla_csv = args.salida / "comparativa_tiempos.csv"
    with open(tabla_csv, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["experimento", "tamano", "procesos", "T_Ethernet_s", "T_WiFi_s", "Aceleracion_Eth_vs_WiFi"])
        for e, n, p in claves:
            t_eth = eth[(e, n, p)]
            t_wifi = wifi[(e, n, p)]
            ratio = t_wifi / t_eth if t_eth > 0 else 0
            writer.writerow([e, n, p, f"{t_eth:.6f}", f"{t_wifi:.6f}", f"{ratio:.2f}x"])

    print(f"Tabla comparativa guardada en: {tabla_csv}")

    # Generar gráfico comparativo por experimento
    experimentos = sorted({e for e, n, p in claves})
    for exp in experimentos:
        tamanos = sorted({n for e, n, p in claves if e == exp})
        fig, axes = plt.subplots(1, len(tamanos), figsize=(6 * len(tamanos), 5.4), squeeze=False)
        for ax, n in zip(axes[0], tamanos):
            ps = [p for p in PROCESOS if (exp, n, p) in eth and (exp, n, p) in wifi]
            ts_eth = [eth[(exp, n, p)] for p in ps]
            ts_wifi = [wifi[(exp, n, p)] for p in ps]

            ax.plot(ps, ts_eth, "o-", color="black", linewidth=1.8, markerfacecolor="white", label="Ethernet (Cable)")
            ax.plot(ps, ts_wifi, "s--", color="#555555", linewidth=1.8, markerfacecolor="#555555", label="Wi-Fi")

            for p, te, tw in zip(ps, ts_eth, ts_wifi):
                ax.annotate(f"{te:.2f}s", (p, te), xytext=(0, -12), textcoords="offset points",
                            ha="center", fontsize=8, color="black")
                ax.annotate(f"{tw:.2f}s", (p, tw), xytext=(0, 8), textcoords="offset points",
                            ha="center", fontsize=8, color="#333333")

            ax.set_xticks(ps)
            ax.set_xlabel("Procesos MPI")
            ax.set_ylabel("Tiempo Total (Segundos)")
            detalle = f"n = {n:,} trapecios" if exp == "trapecio" else f"N = {n} · matriz {n} × {n}"
            ax.set_title(detalle.replace(",", " "))
            ax.grid(axis="y", color="0.88", linewidth=0.7)
            ax.legend(fontsize=9)

        fig.suptitle(f"Comparativa Ethernet vs Wi-Fi — {exp.capitalize()}", fontweight="bold")
        fig.tight_layout()
        grafico_path = args.salida / f"comparativa_{exp}.png"
        fig.savefig(grafico_path, dpi=160)
        plt.close(fig)
        print(f"Gráfico comparativo generado: {grafico_path}")


if __name__ == "__main__":
    main()
