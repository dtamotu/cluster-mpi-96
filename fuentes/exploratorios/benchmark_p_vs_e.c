#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <time.h>
#include <sched.h>
#include <unistd.h>
#include <immintrin.h>
#include <string.h>

static inline double get_time_sec(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC_RAW, &ts);
    return (double)ts.tv_sec + (double)ts.tv_nsec * 1e-9;
}

static inline uint64_t rdtsc(void) {
    unsigned int lo, hi;
    __asm__ __volatile__ ("rdtsc" : "=a" (lo), "=d" (hi));
    return ((uint64_t)hi << 32) | lo;
}

// -------------------------------------------------------------
// Test 1: Kernel de Trapecio (Aritmética matemática continua)
// -------------------------------------------------------------
double benchmark_trapecio(long long n) {
    const double h = 1.0 / (double)n;
    double suma = 0.5 * (4.0 + 2.0); // f(0)=4, f(1)=2
    for (long long i = 1; i < n; i++) {
        double x = (double)i * h;
        suma += 4.0 / (1.0 + x * x);
    }
    return suma * h;
}

// -------------------------------------------------------------
// Test 2: Pico Aritmético FMA (AVX2 - 256 bits)
// -------------------------------------------------------------
// Ejecuta bucle de operaciones FMA independientes para medir el techo de cómputo vectorial
double benchmark_fma_peak(long long iterations) {
    __m256d v0 = _mm256_set1_pd(1.0001);
    __m256d v1 = _mm256_set1_pd(1.0002);
    __m256d v2 = _mm256_set1_pd(1.0003);
    __m256d v3 = _mm256_set1_pd(1.0004);
    __m256d c0 = _mm256_set1_pd(0.9999);
    __m256d c1 = _mm256_set1_pd(0.9998);

    for (long long i = 0; i < iterations; i++) {
        // 4 vectores x 4 dobles x 2 ops (FMA = mul + add) = 32 ops por iteración
        v0 = _mm256_fmadd_pd(v0, c0, c1);
        v1 = _mm256_fmadd_pd(v1, c0, c1);
        v2 = _mm256_fmadd_pd(v2, c0, c1);
        v3 = _mm256_fmadd_pd(v3, c0, c1);
    }

    double res[4];
    _mm256_storeu_pd(res, _mm256_add_pd(_mm256_add_pd(v0, v1), _mm256_add_pd(v2, v3)));
    return res[0];
}

// -------------------------------------------------------------
// Test 3: Kernel de Multiplicación de Matrices por Bloques (Tiled 64)
// -------------------------------------------------------------
void benchmark_gemm_tiled(int N, int bs, const double *A, const double *B, double *C) {
    for (int jj = 0; jj < N; jj += bs) {
        int j_end = (jj + bs < N) ? jj + bs : N;
        for (int ii = 0; ii < N; ii += bs) {
            int i_end = (ii + bs < N) ? ii + bs : N;
            for (int kk = 0; kk < N; kk += bs) {
                int k_end = (kk + bs < N) ? kk + bs : N;
                for (int i = ii; i < i_end; i++) {
                    for (int k = kk; k < k_end; k++) {
                        double a_val = A[i * N + k];
                        for (int j = jj; j < j_end; j++) {
                            C[i * N + j] += a_val * B[k * N + j];
                        }
                    }
                }
            }
        }
    }
}

int main(int argc, char **argv) {
    int target_cpu = 0;
    if (argc > 1) {
        target_cpu = atoi(argv[1]);
    }

    // Fijar afinidad estricta al núcleo target
    cpu_set_t cpuset;
    CPU_ZERO(&cpuset);
    CPU_SET(target_cpu, &cpuset);
    if (sched_setaffinity(0, sizeof(cpuset), &cpuset) != 0) {
        perror("sched_setaffinity");
        return 1;
    }

    // Identificar tipo de núcleo
    const char *tipo = (target_cpu < 8) ? "P-Core (Lion Cove)" : "E-Core (Skymont)";

    printf("=================================================================\n");
    printf(" BENCHMARK NÚCLEO INDIVIDUAL: CPU %d [%s]\n", target_cpu, tipo);
    printf("=================================================================\n");

    // 1. Test FMA Peak
    long long fma_iters = 1000000000LL; // 1 billion iters -> 32 GFLOPs
    double t0 = get_time_sec();
    uint64_t c0 = rdtsc();
    double dummy_fma = benchmark_fma_peak(fma_iters);
    uint64_t c1 = rdtsc();
    double t1 = get_time_sec();
    double fma_time = t1 - t0;
    double fma_flops = (double)fma_iters * 32.0;
    double fma_gflops = (fma_flops / fma_time) / 1e9;
    double ghz_est = (double)(c1 - c0) / (fma_time * 1e9);

    printf("[1] Peak FMA AVX2:\n");
    printf("    Tiempo        : %.4f s\n", fma_time);
    printf("    GFLOPS        : %.2f GFLOPS\n", fma_gflops);
    printf("    Frecuencia est: %.3f GHz (RDTSC)\n", ghz_est);
    printf("    IPC FMA       : %.2f ops/ciclo\n", fma_flops / (double)(c1 - c0));

    // 2. Test Trapecio (n = 2 x 10^9)
    long long n_trap = 2000000000LL;
    t0 = get_time_sec();
    double pi_est = benchmark_trapecio(n_trap);
    t1 = get_time_sec();
    double trap_time = t1 - t0;
    double trap_mops = ((double)n_trap / trap_time) / 1e6;

    printf("\n[2] Regla del Trapecio (n = 2x10^9):\n");
    printf("    Tiempo        : %.4f s\n", trap_time);
    printf("    Rendimiento   : %.2f M puntos/s\n", trap_mops);
    printf("    Error pi      : %.2e (pi=%.14f)\n", pi_est - 3.141592653589793, pi_est);

    // 3. Test Matrices Tiled (N = 1024 y N = 2048)
    double gemm_gflops_1024 = 0, gemm_gflops_2048 = 0;
    for (int N = 1024; N <= 2048; N *= 2) {
        size_t nn = (size_t)N * N;
        double *A = malloc(nn * sizeof(double));
        double *B = malloc(nn * sizeof(double));
        double *C = calloc(nn, sizeof(double));
        for (size_t i = 0; i < nn; i++) {
            A[i] = 1.0 + (i % 7) * 0.1;
            B[i] = 2.0 - (i % 5) * 0.1;
        }

        t0 = get_time_sec();
        benchmark_gemm_tiled(N, 64, A, B, C);
        t1 = get_time_sec();
        double gemm_time = t1 - t0;
        double gemm_gflops = (2.0 * (double)N * (double)N * (double)N) / (gemm_time * 1e9);
        if (N == 1024) gemm_gflops_1024 = gemm_gflops;
        else gemm_gflops_2048 = gemm_gflops;

        printf("\n[3] Matrices GEMM Tiled 64 (N = %d):\n", N);
        printf("    Tiempo        : %.4f s\n", gemm_time);
        printf("    GFLOPS        : %.2f GFLOPS\n", gemm_gflops);

        free(A); free(B); free(C);
    }

    printf("=================================================================\n");
    printf("SUMMARY_ROW: CPU=%d,Tipo=%s,FMA_GFLOPS=%.2f,Trap_Time=%.4f,GEMM1024_GFLOPS=%.2f,GEMM2048_GFLOPS=%.2f,GHz=%.3f\n",
           target_cpu, target_cpu < 8 ? "P" : "E", fma_gflops, trap_time,
           gemm_gflops_1024, gemm_gflops_2048, ghz_est);

    return (int)dummy_fma;
}
