#include <mpi.h>
#include <stdio.h>
#include <stdlib.h>
#include <math.h>

static inline double f(double x) {
    return 4.0 / (1.0 + x * x);
}

int main(int argc, char** argv) {
    MPI_Init(&argc, &argv);

    int rank, P;
    MPI_Comm_rank(MPI_COMM_WORLD, &rank);
    MPI_Comm_size(MPI_COMM_WORLD, &P);

    long long n = 100000000000LL; // 10^11 por defecto
    int modo = 1; // 0 = simetrico (clasico), 1 = asimetrico (ponderado P vs E)
    if (argc > 1) n = atoll(argv[1]);
    if (argc > 2) modo = atoi(argv[2]);

    const double h = 1.0 / (double)n;

    long long inicio = 0;
    long long local_n = 0;

    if (modo == 0 || P % 24 != 0) {
        // --- Reparto Simetrico Clasico ---
        const long long base = n / P;
        const long long resto = n % P;
        local_n = base + (rank < resto ? 1 : 0);
        inicio = rank * base + (rank < resto ? rank : resto);
    } else {
        // --- Reparto Asimetrico Ponderado (Lion Cove vs Skymont) ---
        // Ratio calibrado: V_P / V_E = 1.2658
        // Para cada nodo de 24 nucleos: 8 P-cores (w_p = 1.2658 * w_e) + 16 E-cores (w_e)
        // Suma de pesos por nodo = 8*1.2658 + 16 = 26.1264
        // Peso relativo de un P-core = 1.2658 / (26.1264 * num_nodos)
        // Peso relativo de un E-core = 1.0000 / (26.1264 * num_nodos)
        int num_nodos = P / 24;
        double W_nodo = 8.0 * 1.2658 + 16.0 * 1.0; // 26.1264
        double W_total = W_nodo * (double)num_nodos;

        // Calcular peso de cada rank
        double *weights = malloc(P * sizeof(double));
        for (int r = 0; r < P; r++) {
            int core_in_node = r % 24;
            double w = (core_in_node < 8) ? 1.2658 : 1.0000;
            weights[r] = w / W_total;
        }

        // Asignar rangos acumulativos exactos
        double cum_start = 0.0;
        for (int r = 0; r < rank; r++) {
            cum_start += weights[r];
        }
        double cum_end = cum_start + weights[rank];

        inicio = (long long)round(cum_start * (double)n);
        long long fin = (rank == P - 1) ? n : (long long)round(cum_end * (double)n);
        local_n = fin - inicio;

        free(weights);
    }

    MPI_Barrier(MPI_COMM_WORLD);
    const double t0_total = MPI_Wtime();

    // 1. Calculo local del trapecio
    const double t0_calc = MPI_Wtime();
    double local_sum = 0.0;

    for (long long i = 0; i < local_n; i++) {
        long long global_i = inicio + i;
        double x = (double)global_i * h;
        if (global_i == 0 || global_i == n) {
            local_sum += 0.5 * f(x);
        } else {
            local_sum += f(x);
        }
    }
    const double t1_calc = MPI_Wtime();
    const double t_calc = t1_calc - t0_calc;

    // 2. Reduccion del resultado y tiempos
    const double t0_red = MPI_Wtime();
    double global_sum = 0.0;
    MPI_Reduce(&local_sum, &global_sum, 1, MPI_DOUBLE, MPI_SUM, 0, MPI_COMM_WORLD);
    const double t1_red = MPI_Wtime();
    const double t_reduce = t1_red - t0_red;

    const double t1_total = MPI_Wtime();
    const double t_total = t1_total - t0_total;

    // Metricas de tiempo maximas y minimas entre procesos
    double t_calc_max = 0.0, t_calc_min = 0.0, t_reduce_max = 0.0, t_total_max = 0.0;
    MPI_Reduce(&t_calc, &t_calc_max, 1, MPI_DOUBLE, MPI_MAX, 0, MPI_COMM_WORLD);
    MPI_Reduce(&t_calc, &t_calc_min, 1, MPI_DOUBLE, MPI_MIN, 0, MPI_COMM_WORLD);
    MPI_Reduce(&t_reduce, &t_reduce_max, 1, MPI_DOUBLE, MPI_MAX, 0, MPI_COMM_WORLD);
    MPI_Reduce(&t_total, &t_total_max, 1, MPI_DOUBLE, MPI_MAX, 0, MPI_COMM_WORLD);

    if (rank == 0) {
        double pi_aprox = global_sum * h;
        double error = fabs(pi_aprox - 3.14159265358979323846);
        double desbalance = t_calc_max / (t_calc_min > 0.0 ? t_calc_min : 1e-9);

        printf("RESULT_ASYM: N=%lld, Procs=%d, Modo=%s, T_CalcMax=%.6f, T_CalcMin=%.6f, Desbalance=%.3f, T_Reduce=%.6f, T_Total=%.6f, Error=%.2e, Pi=%.14f\n",
               n, P, modo == 1 ? "Asimetrico" : "Simetrico",
               t_calc_max, t_calc_min, desbalance, t_reduce_max, t_total_max, error, pi_aprox);
    }

    MPI_Finalize();
    return 0;
}
