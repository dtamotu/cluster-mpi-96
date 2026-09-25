import subprocess
import json
import re
import time
import datetime
import numpy as np

# Configuraciones de clúster que en resultados_profiling.json quedaron
# con una sola medición o en NaN (ver análisis del 2026-09-24).
PENDIENTES = [
    (2048, 'cluster_4p'),
    (1536, 'cluster_16p'),
    (2048, 'cluster_8p'),
    (2048, 'cluster_16p'),
    (3072, 'cluster_4p'),
    (3072, 'cluster_8p'),
    (3072, 'cluster_16p'),
]
REPS = 2
TIMEOUT_S = None  # sin límite de tiempo por ejecución
SALIDA = '/home/alumno16/resultados_profiling_repeticion.json'
WORKERS = ['workers1', 'workers2', 'workers4']
BIN = '/tmp/mpi_matrix_profiling'

CONFIGS = {
    'cluster_4p':  (4,  'servidor:1,workers1:1,workers2:1,workers4:1', 'Clúster 4 Nodos (1 proc/nodo)'),
    'cluster_8p':  (8,  'servidor:2,workers1:2,workers2:2,workers4:2', 'Clúster 4 Nodos (2 procs/nodo)'),
    'cluster_16p': (16, 'servidor:4,workers1:4,workers2:4,workers4:4', 'Clúster 4 Nodos (4 procs/nodo)'),
}


def comando(cfg_id, n):
    procs, hosts, _ = CONFIGS[cfg_id]
    return ['mpirun', '-H', hosts, '-np', str(procs),
            '--mca', 'btl_tcp_if_include', '10.7.134.0/23',
            '--mca', 'oob_tcp_if_include', '10.7.134.0/23',
            BIN, str(n)]


def ping_medio():
    """RTT medio (ms) desde el servidor a cada worker justo antes de la ejecución."""
    res = {}
    for h in WORKERS:
        p = subprocess.run(['ping', '-c', '3', '-W', '2', h], capture_output=True, text=True)
        m = re.search(r'= [\d.]+/([\d.]+)/', p.stdout)
        res[h] = float(m.group(1)) if m else None
    return res


def limpiar_restos():
    for h in WORKERS:
        subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=6', h,
                        f'pkill -f {BIN}'], capture_output=True)
    subprocess.run(['pkill', '-f', BIN], capture_output=True)


def parsear(stdout):
    for line in stdout.splitlines():
        if 'RESULT_PROF:' in line:
            campos = dict(kv.strip().split('=') for kv in line.split(':', 1)[1].split(','))
            return {
                'scatter': float(campos['T_Scatter']),
                'bcast': float(campos['T_Bcast']),
                'calc': float(campos['T_Calc']),
                'gather': float(campos['T_Gather']),
                'total': float(campos['T_Total']),
                'gflops': float(campos['GFLOPS']),
                'checksum': float(campos['Checksum']),
            }
    return None


def resumir(reps):
    ok = [r for r in reps if r.get('ok')]
    if not ok:
        return {'n_ok': 0}
    media = lambda k: float(np.mean([r[k] for r in ok]))
    comm = media('scatter') + media('bcast') + media('gather')
    return {
        'n_ok': len(ok),
        'avg_total': media('total'),
        'avg_scatter': media('scatter'),
        'avg_bcast': media('bcast'),
        'avg_calc': media('calc'),
        'avg_gather': media('gather'),
        'avg_comm': comm,
        'avg_gflops': media('gflops'),
        'min_total': float(min(r['total'] for r in ok)),
        'max_total': float(max(r['total'] for r in ok)),
    }


def main():
    datos = {}
    for n, cfg_id in PENDIENTES:
        procs, _, label = CONFIGS[cfg_id]
        datos.setdefault(str(n), {})[cfg_id] = {
            'procs': procs, 'label': label, 'type': 'cluster', 'reps': [], 'resumen': {}}

    for rep in range(1, REPS + 1):
        for n, cfg_id in PENDIENTES:
            entrada = datos[str(n)][cfg_id]
            inicio = datetime.datetime.now().isoformat(timespec='seconds')
            ping = ping_medio()
            print(f'[{inicio}] rep {rep}/{REPS}  N={n}  {cfg_id}  ping={ping} ...', flush=True)

            t0 = time.time()
            registro = {'rep': rep, 'inicio': inicio, 'ping_ms': ping}
            try:
                p = subprocess.run(comando(cfg_id, n), capture_output=True, text=True, timeout=TIMEOUT_S)
                res = parsear(p.stdout) if p.returncode == 0 else None
                if res:
                    registro.update(res, ok=True)
                else:
                    registro.update(ok=False, error=f'returncode={p.returncode}: {p.stderr[-500:]}')
            except subprocess.TimeoutExpired:
                registro.update(ok=False, error=f'timeout > {TIMEOUT_S}s')
                limpiar_restos()
            registro['duracion_pared'] = round(time.time() - t0, 1)

            entrada['reps'].append(registro)
            entrada['resumen'] = resumir(entrada['reps'])
            if registro['ok']:
                print(f'    -> Total={registro["total"]:.2f}s  Calc={registro["calc"]:.2f}s  '
                      f'Bcast={registro["bcast"]:.2f}s  Checksum={registro["checksum"]:.2f}', flush=True)
            else:
                print(f'    -> FALLO: {registro["error"]}', flush=True)

            with open(SALIDA, 'w') as f:
                json.dump(datos, f, indent=2)

    print('Finalizado.', flush=True)


if __name__ == '__main__':
    main()
