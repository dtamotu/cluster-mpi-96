#!/usr/bin/env python3
"""Calcula speedup y eficiencia y dibuja los resultados de tiempos.csv."""
import argparse
import csv
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

PROCESOS = [1, 24, 48, 72, 96]
NOMBRES = {"trapecio": "Trapecio", "matrices": "Matrices 1D-tiled"}


def leer(csv_path):
    """Agrupa cada algoritmo y tamaño; exige una sola medida por configuración."""
    grupos = {}
    with csv_path.open(newline="") as archivo:
        lector = csv.DictReader(archivo)
        if not {"experimento", "tamano", "procesos", "T_Total"} <= set(lector.fieldnames or []):
            raise ValueError("El CSV necesita experimento,tamano,procesos,T_Total.")
        for numero, fila in enumerate(lector, 2):
            e = fila["experimento"]
            n, p = int(fila["tamano"]), int(fila["procesos"])
            t = float(fila["T_Total"])
            if e not in NOMBRES or n <= 0 or p not in PROCESOS or not math.isfinite(t) or t <= 0:
                raise ValueError(f"Fila {numero}: experimento, tamaño, procesos o tiempo inválido.")
            grupo = grupos.setdefault((e, n), {})
            if p in grupo:
                raise ValueError(f"Configuración duplicada: {e}, tamaño={n}, procesos={p}.")
            grupo[p] = t
    if not grupos:
        raise ValueError("El CSV no tiene mediciones.")
    for (e, n), tiempos in grupos.items():
        faltan = sorted(set(PROCESOS) - tiempos.keys())
        if faltan:
            raise ValueError(f"Mediciones incompletas en {e}, tamaño={n}: faltan procesos {faltan}.")
    return grupos


def calcular(grupos):
    filas = []
    for (e, n), tiempos in sorted(grupos.items()):
        for p in PROCESOS:
            speedup = tiempos[1] / tiempos[p]
            filas.append({
                "experimento": e, "tamano": n, "procesos": p,
                "T_Total": tiempos[p], "T_1": tiempos[1],
                "speedup": speedup,
                "eficiencia_pct": 100 * speedup / p,
                "ganancia_vs_24": tiempos[24] / tiempos[p],
            })
    return filas


def decimal(valor, posicion=None):
    # Valores decimales legibles con las magnitudes reales.
    if valor is None or not math.isfinite(valor) or valor == 0:
        return "0"
    if abs(valor) < 0.001:
        return f"{valor:.6f}".rstrip("0").rstrip(".")
    elif abs(valor) < 0.1:
        return f"{valor:.4f}".rstrip("0").rstrip(".")
    elif abs(valor) < 100:
        return f"{valor:.2f}".rstrip("0").rstrip(".")
    else:
        return f"{valor:.1f}".rstrip("0").rstrip(".")


def dibujar(filas, destino, red="Ethernet"):
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False,
                         "axes.spines.right": False, "axes.axisbelow": True})
    metricas = [
        ("T_Total", "Tiempo del algoritmo", "Segundos", "01_tiempo"),
        ("speedup", "Aceleración respecto a 1 proceso", "Speedup", "02_speedup"),
        ("eficiencia_pct", "Eficiencia respecto a 1 proceso", "Eficiencia (%)", "03_eficiencia"),
    ]
    for e in sorted({f["experimento"] for f in filas}):
        tamanos = sorted({f["tamano"] for f in filas if f["experimento"] == e})
        for campo, titulo, eje, nombre in metricas:
            fig, axes = plt.subplots(1, len(tamanos), figsize=(6 * len(tamanos), 5.4), squeeze=False)
            for ax, n in zip(axes[0], tamanos):
                datos = [f for f in filas if f["experimento"] == e and f["tamano"] == n]
                valores = [f[campo] for f in datos]
                ax.plot(PROCESOS, valores, "o-", color="black", linewidth=1.7,
                        markerfacecolor="white", label="Medición individual")
                if campo == "speedup":
                    ax.plot([1, 96], [1, 96], "--", color="0.55", label="Referencia lineal: S = p")
                    ax.axhline(1, color="0.65", linestyle=":", linewidth=1)
                    ax.set_ylim(0, max(96, max(valores)) * 1.08)
                elif campo == "eficiencia_pct":
                    ax.axhline(100, color="0.55", linestyle="--", label="Referencia: 100 %")
                    ax.set_ylim(0, max(100, max(valores)) * 1.15)
                else:
                    ax.set_ylim(0, max(valores) * 1.10)

                ticks_y = sorted(set(valores))
                ax.set_yticks(ticks_y)
                ax.set_yticklabels([decimal(v) for v in ticks_y], fontsize=8)

                for p, valor in zip(PROCESOS, valores):
                    etiqueta = decimal(valor)
                    alineacion = "left" if p == 1 else "right" if p == 96 else "center"
                    ax.annotate(etiqueta, (p, valor), xytext=(0, 8),
                                textcoords="offset points", ha=alineacion, fontsize=8)
                ax.set_xticks(PROCESOS)
                ax.set_xlabel("Procesos MPI (1 proceso por núcleo)")
                ax.set_ylabel(eje)
                detalle = f"n = {n:,} trapecios" if e == "trapecio" else f"N = {n} · matriz {n} × {n}"
                ax.set_title(detalle.replace(",", " "))
                ax.grid(axis="y", color="0.88", linewidth=0.7)
                ax.legend(fontsize=8, loc="best")
            fig.suptitle(f"{NOMBRES[e]} — {titulo}", fontweight="bold")
            nota = ("Se excluyen el arranque de MPI y la preparación inicial de datos."
                    if campo == "T_Total" else
                    "Núcleos P y E: la referencia lineal no es una predicción del rendimiento.")
            fig.text(0.5, 0.02,
                     f"{red} · una ejecución por configuración · 24 procesos por equipo completo\n"
                     + nota,
                     ha="center", fontsize=9)
            fig.tight_layout(rect=(0, 0.09, 1, 0.94))

            # Evita solapamiento visual entre etiquetas de marcas cercanas en el eje Y
            fig.canvas.draw()
            renderer = fig.canvas.get_renderer()
            for ax in axes[0]:
                labels = [lbl for lbl in ax.get_yticklabels() if lbl.get_text()]
                prev_bb = None
                for lbl in labels:
                    bb = lbl.get_window_extent(renderer)
                    if prev_bb is not None and bb.overlaps(prev_bb):
                        lbl.set_visible(False)
                    else:
                        prev_bb = bb

            fig.savefig(destino / f"{e}_{nombre}.png", dpi=160)
            plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path, help="ruta al tiempos.csv de una ejecución")
    parser.add_argument("--red", choices=["Ethernet", "Wi-Fi", "auto"], default="auto",
                        help="Nombre de la red para el pie de los gráficos (Ethernet, Wi-Fi o auto)")
    args = parser.parse_args()
    try:
        filas = calcular(leer(args.csv))
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"No se puede analizar: {error}\n")

    red = ("Wi-Fi" if "wifi" in str(args.csv).lower() else "Ethernet") if args.red == "auto" else args.red

    destino = args.csv.resolve().parent / "analisis"
    destino.mkdir(exist_ok=True)
    with (destino / "metricas.csv").open("w", newline="") as archivo:
        tabla = csv.DictWriter(archivo, fieldnames=list(filas[0]))
        tabla.writeheader()
        tabla.writerows(filas)
    dibujar(filas, destino, red=red)
    print(f"Análisis y gráficos ({red}): {destino}")
    for f in filas:
        if f["procesos"] == 96:
            print(f"{f['experimento']} tamaño={f['tamano']}: "
                  f"speedup={f['speedup']:.3f}x; eficiencia={f['eficiencia_pct']:.2f}%; "
                  f"ganancia frente a 24 procesos={f['ganancia_vs_24']:.3f}x")


if __name__ == "__main__":
    main()
