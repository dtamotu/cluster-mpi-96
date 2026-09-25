// Regla del trapecio con MPI: aproxima  integral_0^1 4/(1+x^2) dx = pi
// sumando n trapecios. Cada proceso calcula un tramo contiguo de trapecios
// sin comunicarse; al final MPI_Reduce suma un solo número por proceso.
//
// Uso: trapecio <n>          (n puede ser muy grande, p. ej. 100000000000)
// Salida: RESULT_TRAP: n=..., Procs=..., T_Calc=..., T_CalcMin=..., T_Reduce=..., T_Total=..., Integral=..., Error=...
#include <mpi.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>

static inline double f(double x) { return 4.0 / (1.0 + x * x); }

int main(int argc, char **argv) {
    MPI_Init(&argc, &argv);
    int rank, P;
    MPI_Comm_rank(MPI_COMM_WORLD, &rank);
    MPI_Comm_size(MPI_COMM_WORLD, &P);

    const long long n = argc > 1 ? atoll(argv[1]) : 1000000LL;
    const double a = 0.0, b = 1.0, h = (b - a) / (double)n;

    // Reparto de trapecios: los primeros (n % P) procesos reciben uno más.
    const long long base = n / P, resto = n % P;
    const long long local_n = base + (rank < resto ? 1 : 0);
    const long long inicio = rank * base + (rank < resto ? rank : resto);

    MPI_Barrier(MPI_COMM_WORLD);
    const double t0 = MPI_Wtime();

    // Trapecios [inicio, inicio + local_n): extremos a la mitad, puntos interiores completos.
    const double xa = a + inicio * h, xb = a + (inicio + local_n) * h;
    double suma = (f(xa) + f(xb)) / 2.0;
    for (long long i = 1; i < local_n; i++)
        suma += f(xa + i * h);
    const double local = suma * h;
    const double t_calc = MPI_Wtime() - t0;

    const double t1 = MPI_Wtime();
    double total = 0.0;
    MPI_Reduce(&local, &total, 1, MPI_DOUBLE, MPI_SUM, 0, MPI_COMM_WORLD);
    const double t_reduce = MPI_Wtime() - t1;
    const double t_total = MPI_Wtime() - t0;

    double calc_max, calc_min, reduce_max, total_max;
    MPI_Reduce(&t_calc, &calc_max, 1, MPI_DOUBLE, MPI_MAX, 0, MPI_COMM_WORLD);
    MPI_Reduce(&t_calc, &calc_min, 1, MPI_DOUBLE, MPI_MIN, 0, MPI_COMM_WORLD);
    MPI_Reduce(&t_reduce, &reduce_max, 1, MPI_DOUBLE, MPI_MAX, 0, MPI_COMM_WORLD);
    MPI_Reduce(&t_total, &total_max, 1, MPI_DOUBLE, MPI_MAX, 0, MPI_COMM_WORLD);

    if (rank == 0)
        printf("RESULT_TRAP: n=%lld, Procs=%d, T_Calc=%.6f, T_CalcMin=%.6f, T_Reduce=%.6f, T_Total=%.6f, "
               "Integral=%.15f, Error=%.3e\n",
               n, P, calc_max, calc_min, reduce_max, total_max, total, fabs(total - M_PI));

    MPI_Finalize();
    return 0;
}
