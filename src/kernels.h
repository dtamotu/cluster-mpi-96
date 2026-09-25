#ifndef KERNELS_H
#define KERNELS_H

#include <stddef.h>

// Todas las rutinas calculan C += A * B, con A (m x kd), B (kd x n), C (m x n),
// almacenadas por filas con "leading dimension" lda, ldb, ldc.

// Textbook i-j-k: recorre B por columnas (saltos de n elementos) -> pésimo uso de caché.
static inline void gemm_ijk(int m, int n, int kd,
                            const double *restrict A, int lda,
                            const double *restrict B, int ldb,
                            double *restrict C, int ldc) {
    for (int i = 0; i < m; i++)
        for (int j = 0; j < n; j++) {
            double s = C[(size_t)i * ldc + j];
            for (int k = 0; k < kd; k++)
                s += A[(size_t)i * lda + k] * B[(size_t)k * ldb + j];
            C[(size_t)i * ldc + j] = s;
        }
}

// i-k-j (el bucle del programa original): acceso contiguo a B y C, pero cada fila
// de A recorre B completa. Si B no cabe en caché, se relee desde la RAM m veces.
static inline void gemm_ikj(int m, int n, int kd,
                            const double *restrict A, int lda,
                            const double *restrict B, int ldb,
                            double *restrict C, int ldc) {
    for (int i = 0; i < m; i++) {
        double *c = C + (size_t)i * ldc;
        for (int k = 0; k < kd; k++) {
            const double a = A[(size_t)i * lda + k];
            const double *b = B + (size_t)k * ldb;
            for (int j = 0; j < n; j++)
                c[j] += a * b[j];
        }
    }
}

// i-k-j por bloques (cache tiling): el trabajo se divide en teselas de bs x bs.
// Orden jj -> ii -> kk: el panel de B (kd x bs) se reutiliza para todas las filas
// de A y la tesela de C (bs x bs) permanece en L1/L2 mientras se acumula.
static inline void gemm_tiled(int m, int n, int kd,
                              const double *restrict A, int lda,
                              const double *restrict B, int ldb,
                              double *restrict C, int ldc, int bs) {
    for (int jj = 0; jj < n; jj += bs) {
        const int je = jj + bs < n ? jj + bs : n;
        for (int ii = 0; ii < m; ii += bs) {
            const int ie = ii + bs < m ? ii + bs : m;
            for (int kk = 0; kk < kd; kk += bs) {
                const int ke = kk + bs < kd ? kk + bs : kd;
                for (int i = ii; i < ie; i++) {
                    double *c = C + (size_t)i * ldc;
                    for (int k = kk; k < ke; k++) {
                        const double a = A[(size_t)i * lda + k];
                        const double *b = B + (size_t)k * ldb;
                        for (int j = jj; j < je; j++)
                            c[j] += a * b[j];
                    }
                }
            }
        }
    }
}

#endif
