// Multiplicación de matrices C = A x B con MPI, en dos descomposiciones:
//   1d : franjas de filas (igual que ../mpi_matrix_profiling.c): Scatterv(A) + Bcast(B completa) + Gatherv(C)
//   2d : bloques cuadrados en una malla q x q (algoritmo SUMMA). Requiere P = q*q y N % q == 0.
// y dos núcleos de cálculo local:
//   ikj   : bucle original
//   tiled : bucle por teselas de bs x bs (cache blocking)
//
// Uso: mpi_matrix_2d <N> <1d|2d> <ikj|tiled> [bs]
// Con MAP_DEBUG=1 en el entorno, imprime el nodo donde corre cada rango.
#include <mpi.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "kernels.h"

static void local_gemm(const char *kernel, int bs, int m, int n, int kd,
                       const double *A, int lda, const double *B, int ldb, double *C, int ldc) {
    if (strcmp(kernel, "tiled") == 0)
        gemm_tiled(m, n, kd, A, lda, B, ldb, C, ldc, bs);
    else
        gemm_ikj(m, n, kd, A, lda, B, ldb, C, ldc);
}

int main(int argc, char **argv) {
    MPI_Init(&argc, &argv);
    int rank, P;
    MPI_Comm_rank(MPI_COMM_WORLD, &rank);
    MPI_Comm_size(MPI_COMM_WORLD, &P);

    if (argc < 4) {
        if (rank == 0) fprintf(stderr, "uso: %s <N> <1d|2d> <ikj|tiled> [bs]\n", argv[0]);
        MPI_Abort(MPI_COMM_WORLD, 1);
    }
    const int N = atoi(argv[1]);
    const char *algo = argv[2];
    const char *kernel = argv[3];
    const int bs = argc > 4 ? atoi(argv[4]) : 64;
    const int is2d = strcmp(algo, "2d") == 0;

    int q = (int)lround(sqrt((double)P));
    if (is2d && (q * q != P || N % q != 0)) {
        if (rank == 0) fprintf(stderr, "2d requiere P cuadrado perfecto y N divisible por sqrt(P) (P=%d, N=%d)\n", P, N);
        MPI_Abort(MPI_COMM_WORLD, 2);
    }

    if (getenv("MAP_DEBUG")) {
        char name[MPI_MAX_PROCESSOR_NAME];
        int len;
        MPI_Get_processor_name(name, &len);
        char *all = rank == 0 ? malloc((size_t)P * MPI_MAX_PROCESSOR_NAME) : NULL;
        MPI_Gather(name, MPI_MAX_PROCESSOR_NAME, MPI_CHAR, all, MPI_MAX_PROCESSOR_NAME, MPI_CHAR, 0, MPI_COMM_WORLD);
        if (rank == 0) {
            for (int r = 0; r < P; r++)
                printf("MAP: rank=%d host=%s%s\n", r, all + (size_t)r * MPI_MAX_PROCESSOR_NAME,
                       is2d ? "" : "");
            free(all);
        }
    }

    // Matrices globales, solo en el rango 0.
    double *A = NULL, *B = NULL, *C = NULL;
    const size_t nn = (size_t)N * N;
    if (rank == 0) {
        A = malloc(nn * sizeof(double));
        C = malloc(nn * sizeof(double));
        B = malloc(nn * sizeof(double));
        for (size_t i = 0; i < nn; i++) {
            A[i] = 1.0 + (i % 7) * 0.1;
            B[i] = 2.0 - (i % 5) * 0.1;
        }
    }

    double t_dist = 0, t_summa = 0, t_calc = 0, t_gather = 0;
    double t0, t_total;

    if (!is2d) {
        // ---------------- 1D: franjas de filas ----------------
        int *counts = malloc(P * sizeof(int)), *displs = malloc(P * sizeof(int));
        for (int i = 0, off = 0; i < P; i++) {
            int r = N / P + (i < N % P ? 1 : 0);
            counts[i] = r * N;
            displs[i] = off;
            off += counts[i];
        }
        const int rows = counts[rank] / N;
        double *A_loc = malloc((size_t)counts[rank] * sizeof(double));
        double *C_loc = calloc((size_t)counts[rank], sizeof(double));
        if (rank != 0) B = malloc(nn * sizeof(double));

        MPI_Barrier(MPI_COMM_WORLD);
        t0 = MPI_Wtime();
        double t = MPI_Wtime();
        MPI_Scatterv(A, counts, displs, MPI_DOUBLE, A_loc, counts[rank], MPI_DOUBLE, 0, MPI_COMM_WORLD);
        MPI_Bcast(B, (int)nn, MPI_DOUBLE, 0, MPI_COMM_WORLD);
        t_dist = MPI_Wtime() - t;

        t = MPI_Wtime();
        local_gemm(kernel, bs, rows, N, N, A_loc, N, B, N, C_loc, N);
        t_calc = MPI_Wtime() - t;

        t = MPI_Wtime();
        MPI_Gatherv(C_loc, counts[rank], MPI_DOUBLE, C, counts, displs, MPI_DOUBLE, 0, MPI_COMM_WORLD);
        t_gather = MPI_Wtime() - t;
        MPI_Barrier(MPI_COMM_WORLD);
        t_total = MPI_Wtime() - t0;

        free(A_loc); free(C_loc); free(counts); free(displs);
        if (rank != 0) free(B);
    } else {
        // ---------------- 2D: SUMMA en malla q x q ----------------
        // Rango r -> fila r/q, columna r%q. Con "-H nodo:q" y q procesos por nodo,
        // cada fila de la malla queda dentro de un mismo nodo.
        const int nb = N / q;
        const size_t bsz = (size_t)nb * nb;
        const int myrow = rank / q, mycol = rank % q;
        MPI_Comm row_comm, col_comm;
        MPI_Comm_split(MPI_COMM_WORLD, myrow, mycol, &row_comm);  // mismo myrow; rango interno = mycol
        MPI_Comm_split(MPI_COMM_WORLD, mycol, myrow, &col_comm);  // misma mycol; rango interno = myrow

        double *A_loc = malloc(bsz * sizeof(double)), *B_loc = malloc(bsz * sizeof(double));
        double *A_tmp = malloc(bsz * sizeof(double)), *B_tmp = malloc(bsz * sizeof(double));
        double *C_loc = calloc(bsz, sizeof(double));
        double *pack = rank == 0 ? malloc(nn * sizeof(double)) : NULL;

        MPI_Barrier(MPI_COMM_WORLD);
        t0 = MPI_Wtime();

        // Reparto inicial: el rango 0 empaqueta cada bloque (nb x nb) contiguo y lo envía a su dueño.
        double t = MPI_Wtime();
        for (int pass = 0; pass < 2; pass++) {
            const double *M = pass == 0 ? A : B;
            double *dst = pass == 0 ? A_loc : B_loc;
            if (rank == 0)
                for (int br = 0; br < q; br++)
                    for (int bc = 0; bc < q; bc++)
                        for (int i = 0; i < nb; i++)
                            memcpy(pack + (size_t)(br * q + bc) * bsz + (size_t)i * nb,
                                   M + (size_t)(br * nb + i) * N + (size_t)bc * nb, nb * sizeof(double));
            MPI_Scatter(pack, (int)bsz, MPI_DOUBLE, dst, (int)bsz, MPI_DOUBLE, 0, MPI_COMM_WORLD);
        }
        t_dist = MPI_Wtime() - t;

        // SUMMA: en el paso k, la columna k difunde su bloque de A por su fila
        // y la fila k difunde su bloque de B por su columna; luego C_loc += A_k * B_k.
        for (int k = 0; k < q; k++) {
            double *Ak = mycol == k ? A_loc : A_tmp;
            double *Bk = myrow == k ? B_loc : B_tmp;
            t = MPI_Wtime();
            MPI_Bcast(Ak, (int)bsz, MPI_DOUBLE, k, row_comm);
            MPI_Bcast(Bk, (int)bsz, MPI_DOUBLE, k, col_comm);
            t_summa += MPI_Wtime() - t;

            t = MPI_Wtime();
            local_gemm(kernel, bs, nb, nb, nb, Ak, nb, Bk, nb, C_loc, nb);
            t_calc += MPI_Wtime() - t;
        }

        t = MPI_Wtime();
        MPI_Gather(C_loc, (int)bsz, MPI_DOUBLE, pack, (int)bsz, MPI_DOUBLE, 0, MPI_COMM_WORLD);
        if (rank == 0)
            for (int br = 0; br < q; br++)
                for (int bc = 0; bc < q; bc++)
                    for (int i = 0; i < nb; i++)
                        memcpy(C + (size_t)(br * nb + i) * N + (size_t)bc * nb,
                               pack + (size_t)(br * q + bc) * bsz + (size_t)i * nb, nb * sizeof(double));
        t_gather = MPI_Wtime() - t;
        MPI_Barrier(MPI_COMM_WORLD);
        t_total = MPI_Wtime() - t0;

        free(A_loc); free(B_loc); free(A_tmp); free(B_tmp); free(C_loc); free(pack);
        MPI_Comm_free(&row_comm);
        MPI_Comm_free(&col_comm);
    }

    // Máximos entre rangos (el proceso más lento marca el ritmo) y media del cálculo.
    double loc[5] = {t_dist, t_summa, t_calc, t_gather, t_total}, mx[5], calc_sum;
    MPI_Reduce(loc, mx, 5, MPI_DOUBLE, MPI_MAX, 0, MPI_COMM_WORLD);
    MPI_Reduce(&t_calc, &calc_sum, 1, MPI_DOUBLE, MPI_SUM, 0, MPI_COMM_WORLD);

    if (rank == 0) {
        // Traza + suma ponderada de todos los elementos (detecta bloques mal colocados).
        double trace = 0.0, wsum = 0.0;
        for (int i = 0; i < N; i++) trace += C[(size_t)i * N + i];
        for (int i = 0; i < N; i++)
            for (int j = 0; j < N; j++)
                wsum += C[(size_t)i * N + j] * (double)((i * 31 + j * 17) % 13 + 1);
        printf("RESULT_2D: N=%d, Procs=%d, Algo=%s, Kernel=%s, BS=%d, T_Dist=%.6f, T_Summa=%.6f, "
               "T_Calc=%.6f, T_CalcAvg=%.6f, T_Gather=%.6f, T_Total=%.6f, GFLOPS=%.4f, Checksum=%.2f, WSum=%.6e\n",
               N, P, algo, kernel, bs, mx[0], mx[1], mx[2], calc_sum / P, mx[3], mx[4],
               2.0 * N * (double)N * N / (mx[4] * 1e9), trace, wsum);
        free(A); free(B); free(C);
    }
    MPI_Finalize();
    return 0;
}
