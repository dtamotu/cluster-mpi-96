# Informe actualizado: 96 núcleos, Ethernet y Wi-Fi

Repositorio: [github.com/dtamotu/cluster-mpi-96](https://github.com/dtamotu/cluster-mpi-96) (privado).

Abrir `main.pdf`. El documento conserva el diseño de carátula, integrantes, curso,
profesor y estructura narrativa de `informe_alumno_completo/main.tex`; adapta el
título para incorporar trapecio, Ethernet y dos baterías de hasta 96 procesos.

## Reconstrucción

```bash
cd /home/alumno16/informe_actual_96
./compilar.sh
```

Requiere Python 3 con matplotlib/numpy, pdflatex y los paquetes LaTeX del informe
de referencia. La reconstrucción solo lee las copias de evidencia; no ejecuta MPI.

- `main.tex`: portada, estilo y estructura.
- `contenido.tex` y `ampliacion.tex`: metodología, resultados e interpretación.
- `anexos.tex`: configuración, comandos, scripts y fuentes.
- `generar_datos.py`: tablas, métricas, figuras y verificaciones de consistencia.
- `datos/`: CSV, logs y JSON originales de ambas baterías; procedencia y SHA-256.
- `fuentes/INFORME_ANALISIS_EXPANDIDO_96.md`: borrador preservado para contraste;
  los resultados citados en el PDF se cotejaron con CSV y logs.
- `src/` y `scripts/`: copias de código y lanzadores de las pruebas.
- `medir_trafico.sh`: herramienta opcional para una ejecución futura con contadores
  TX. No se ejecutó para generar los resultados del informe.

Las dos baterías tienen una sola ejecución por configuración. La segunda suma
75 ejecuciones y registra TX+RX solo de la interfaz del servidor. Los MB de 1112
y 357–358 proceden de series históricas con otra medición de tráfico y no se
atribuyen a las baterías de 96 procesos. El caso de 906.351 s corresponde a
8 procesos, de los cuales 889.744 s se registraron en `MPI_Bcast(B)`.
Las seis figuras usan colores sobrios para Ethernet, Wi-Fi y la variante 2D;
cada punto o barra muestra su valor medido.

Referencias primarias: [FAQ Open MPI 4.x](https://www.open-mpi.org/faq/?category=tcp)
y [decisión fija de Bcast en Open MPI 4.1.6](https://github.com/open-mpi/ompi/blob/v4.1.6/ompi/mca/coll/tuned/coll_tuned_decision_fixed.c).
