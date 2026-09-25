# Entorno de ejecución: procesador, memoria y red

**Complementa:** [INFORME_BLOQUES.md](INFORME_BLOQUES.md) (pruebas del 2026-09-24, 01:37–02:18)
**Datos recogidos:** 2026-09-24 06:46, por SSH y sin `sudo`, con `lscpu`, `lspci`, `nmcli`, `udevadm` (tablas DMI), `/sys` y `/proc`, en los 4 nodos. El hardware y el software son los mismos que durante las pruebas. El estado de la red (señal, ocupación) cambia con la hora; las cifras de red medidas **durante** las pruebas están en §3.3.

---

## 1. Resumen: los 4 nodos son idénticos

| | servidor | workers1 | workers2 | workers4 |
| :--- | :---: | :---: | :---: | :---: |
| IP (Wi-Fi) | 10.7.134.117 | 10.7.134.58 | 10.7.134.59 | 10.7.134.51 |
| Usuario SSH | alumno16 | alumno22 | alumno21 | alumno6 |
| Equipo (DMI) | Lenovo 30K6S5XY00 (placa 337A) | ídem | ídem | ídem |
| CPU | Intel Core Ultra 9 285 | ídem | ídem | ídem |
| RAM | 32 GB DDR5-5600, **1 módulo** | ídem | ídem | ídem |
| SO / kernel | Ubuntu 24.04.4 LTS / 6.17.0-1032-oem | ídem | ídem | ídem |
| Perfil de energía | performance | **balanced** | performance | performance |
| Señal Wi-Fi | 74 % | 74 % | 79 % | 78 % |

La única diferencia es el **perfil de energía de workers1** (`balanced`, con EPP `balance_performance`), que puede bajarle la frecuencia. No afecta a las conclusiones: en el clúster el cálculo es como mucho el 3 % del tiempo.

`workers3` (10.7.135.176, Ubuntu 20.04) no participó: estaba apagado y su versión de PMIx es incompatible.

---

## 2. Procesador y memoria

### 2.1 CPU: Intel Core Ultra 9 285 (arquitectura híbrida)

| Característica | Valor |
| :--- | :--- |
| Núcleos | **24** (sin Hyper-Threading): **8 P** (CPU 0–7) + **16 E** (CPU 8–23) |
| Frecuencia máxima por núcleo (`lscpu -e`) | P: 5.4–5.6 GHz · E: 4.7 GHz |
| Instrucciones vectoriales | **AVX2, FMA**, AVX-VNNI. **No tiene AVX-512.** |
| Gobernador de frecuencia | `intel_pstate` en modo `powersave` (dinámico) con EPP `performance` |
| NUMA | 1 nodo |

`lscpu` indica un máximo de 6500 MHz y lo asigna a las CPU 16–17, que son núcleos E. Es un error de lo que informa el firmware. La frecuencia máxima oficial del 285 es de 5.6 GHz.

### 2.2 Jerarquía de caché

| Nivel | Tamaño | Compartida por | Asociatividad | Línea |
| :--- | :--- | :--- | :---: | :---: |
| L1 datos | **48 KB** por núcleo (768 KB en total) | 1 núcleo | 12 vías | 64 B |
| L1 instrucciones | 64 KB por núcleo | 1 núcleo | 16 vías | 64 B |
| **L2** | **3 MB** | cada núcleo P tiene la suya; los E la comparten de 4 en 4 (40 MB en total) | 12 vías | 64 B |
| **L3** | **36 MB** | todo el chip | 12 vías | 64 B |

**Relación con los resultados:** el bucle original pierde más de la mitad de su rendimiento cuando la matriz B supera **3 MB** (N ≈ 627, sale de L2) y vuelve a bajar al superar **36 MB** (N ≈ 2172, sale de L3). Ver §3 del informe.

### 2.3 Memoria RAM

| Característica | Valor |
| :--- | :--- |
| Capacidad | 32 GB (30 GiB visibles) + 18.6 GB de swap |
| Módulo | **1 × SK Hynix HMCG88AGBSA095N**, SODIMM **DDR5-5600** (configurado a 5600 MT/s) |
| Ranuras | **2, una vacía** → funciona en **un solo canal** |
| **Ancho de banda teórico** | 5600 MT/s × 8 bytes = **44.8 GB/s** |

**Relación con los resultados:** es el dato que explica el techo de ~11 GFLOPS del programa original. Su bucle lee ~232 GB de la RAM con N=3072, a 0.25 operaciones por byte. Con 16 procesos se midió un ancho de banda implícito de **43.5 GB/s**, prácticamente el máximo teórico de este único canal. **El bucle original satura la memoria**, así que añadir núcleos no lo acelera. Con un segundo módulo (doble canal, 89.6 GB/s), el original podría acercarse al doble. La versión por bloques casi no depende de esto, porque lee unas 60 veces menos memoria.

---

## 3. Red

### 3.1 Hardware de red de cada nodo

| Interfaz | Hardware | Estado |
| :--- | :--- | :--- |
| `wlp129s0f0` (Wi-Fi) | Intel Wi-Fi 7 (802.11be) BE200/BE201, 2×2 | **En uso** |
| `enp128s31f6` (Ethernet) | Intel Ethernet (ID PCI 550c), integrada | **Sin cable (down)** |

Los 4 nodos tienen un **puerto Ethernet sin usar**. Conectarlos a un switch Gigabit no requeriría comprar tarjetas.

### 3.2 Configuración de la Wi-Fi

| Parámetro | Valor (igual en los 4 nodos) |
| :--- | :--- |
| Red / seguridad | `CsComputacion` (conexión `wifi-CsComputacion`) / WPA2 |
| Banda / canal | **5 GHz, canal 161 (5805 MHz)**: los 4 nodos en el **mismo canal** |
| Velocidad máxima anunciada por el punto de acceso | **130 Mbit/s** (≈ 16 MB/s físicos, antes de cabeceras y reintentos) |
| Subred / puerta de enlace | 10.7.134.0/23 / 10.7.134.1 |
| DNS | 10.0.0.7, 10.0.0.70 |
| MTU | 1500 |

Aunque las tarjetas son Wi-Fi 7, **el límite lo pone el punto de acceso de la universidad**, con 130 Mbit/s. Además, en Wi-Fi:
- el canal es **compartido y semidúplex**: solo transmite un equipo a la vez, contando los 4 nodos **y todos los demás dispositivos** del canal 161;
- el tráfico entre dos nodos pasa por el punto de acceso, así que **ocupa el aire dos veces**.

### 3.3 Red medida durante las pruebas (24/09, 01:45–02:18)

| Medida | Mínimo | Mediana | Máximo |
| :--- | ---: | ---: | ---: |
| Ping con la red en reposo (72 mediciones, antes de cada ejecución) | 21 ms | **56 ms** | 121 ms |
| Ping con la red cargada (medido a las 00:44, durante una prueba) | 23 ms | 125–340 ms | 725 ms |
| **Rendimiento efectivo de MPI** (bytes enviados ÷ tiempo, 24 ejecuciones) | 2.4 MB/s | **5.3 MB/s** | 6.5 MB/s |

- 5.3 MB/s son unos **42 Mbit/s**, apenas un tercio de los 130 Mbit/s anunciados. La diferencia se va en cabeceras, reintentos, el doble paso por el punto de acceso y el tráfico de otros dispositivos.
- Como referencia: un ping de 56 ms en una red local es muy alto (en cable sería menor de 1 ms). El registro del 23/09 anotó unos 10 ms. **El estado de la red varía mucho con la hora.**
- Un Gigabit Ethernet daría ~117 MB/s, unas **22 veces** más que lo medido.

---

## 4. Software

| Componente | Versión |
| :--- | :--- |
| MPI | Open MPI 4.1.6 (transporte TCP; `--mca btl_tcp_if_include 10.7.134.0/23`) |
| Compilador | GCC 13.3.0 (`mpicc`) |
| Flags de las pruebas del 24/09 | `-O3 -march=native -funroll-loops` → usa AVX2 + FMA (verificado con `objdump`) |
| Flags de los binarios del 23/09 (`/tmp/mpi_matrix_block`, `/tmp/mpi_matrix_profiling`) | **solo `-O3`**, sin AVX (verificado byte a byte recompilando) |
| Python | 3.12.3 |
| Lanzamiento remoto | SSH con clave Ed25519, sin contraseña |

---

## 5. Qué recurso limita cada caso

| Escenario | Recurso que limita | Evidencia |
| :--- | :--- | :--- |
| Servidor, bucle original, N ≥ 768 | **Ancho de banda de la RAM (un solo canal, 44.8 GB/s)** | Se estanca en ~11 GFLOPS con cualquier número de procesos; se usan 43.5 GB/s implícitos. |
| Servidor, bucle por bloques | **Núcleos de CPU** (hasta 16) y la mezcla de núcleos P y E | Escala hasta 152 GFLOPS; con 24 procesos rinde menos que con 16. |
| Clúster, cualquier versión | **Wi-Fi compartida (130 Mbit/s anunciados, ~42 Mbit/s efectivos)** | Más del 97 % del tiempo es comunicación; el tiempo sigue al volumen de datos. |

## 6. Datos que no se pudieron obtener

- **Detalles del enlace Wi-Fi negociado** (ancho de canal, velocidad por estación, reintentos): `iw` no devolvió datos sin permisos. Los 130 Mbit/s son lo que anuncia el punto de acceso, no la velocidad negociada.
- **Contadores de hardware** (fallos de caché, ancho de banda de memoria real): `perf` no está disponible (`perf_event_paranoid = 4` y faltan las herramientas del kernel 6.17).
- **Ancho de banda real de memoria y de red con herramientas estándar** (STREAM, `iperf3`): no se ejecutaron. El ancho de banda de memoria se dedujo del modelo de tráfico, y el de red de los bytes enviados por MPI.
