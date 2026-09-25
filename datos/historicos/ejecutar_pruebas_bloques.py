"""Batería de pruebas de la versión por bloques.

Fase A - caché: microbenchmark secuencial en un núcleo P (CPU 4), barriendo N y el tamaño de tesela.
Fase B - servidor local: 1D-ikj (original) vs 1D-tiled vs 2D-tiled con P = 1, 4, 8, 16, 24.
Fase C - clúster Wi-Fi: 1D-ikj (original) vs 2D-tiled, ejecuciones pareadas e intercaladas,
         midiendo ping y bytes enviados por la Wi-Fi en los 4 nodos.

Antes de empezar espera a que termine la repetición del profiling (../repetir_profiling_cluster.py)
para no mezclar mediciones.
"""
import datetime
import json
import os
import re
import subprocess
import time

DIR = '/home/alumno16/bloques_2d'
SALIDA = os.environ.get('SALIDA', f'{DIR}/resultados_bloques.json')   # SALIDA=otro.json para no pisar los datos
BIN_REMOTO = '/var/tmp/mpi_bloques/mpi_matrix_2d'   # sobrevive a reinicios (a diferencia de /tmp)
NODOS = ['servidor', 'workers1', 'workers2', 'workers4']
WORKERS = NODOS[1:]
IFACE = 'wlp129s0f0'
MCA = ['--mca', 'btl_tcp_if_include', '10.7.134.0/23', '--mca', 'oob_tcp_if_include', '10.7.134.0/23']
BS = 64
TIMEOUT_CLUSTER = None   # sin límite de tiempo por ejecución

datos = {'meta': {}, 'cache': [], 'local': [], 'cluster': []}


def log(msg):
    print(f'[{datetime.datetime.now():%H:%M:%S}] {msg}', flush=True)


def guardar():
    with open(SALIDA, 'w') as f:
        json.dump(datos, f, indent=2)


def parse(line_prefix, stdout):
    for line in stdout.splitlines():
        if line.startswith(line_prefix):
            out = {}
            for kv in line.split(':', 1)[1].split(','):
                k, v = kv.strip().split('=')
                try:
                    out[k] = float(v)
                except ValueError:
                    out[k] = v
            return out
    return None


def esperar_repeticion():
    while subprocess.run(['pgrep', '-f', 'repetir_profiling_cluster.py'], capture_output=True).returncode == 0:
        log('Esperando a que termine repetir_profiling_cluster.py ...')
        time.sleep(60)


def ssh(host, cmd, timeout=30):
    if host == 'servidor':
        return subprocess.run(['bash', '-c', cmd], capture_output=True, text=True, timeout=timeout)
    return subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8', host, cmd],
                          capture_output=True, text=True, timeout=timeout)


def desplegar():
    subprocess.run(['mkdir', '-p', '/var/tmp/mpi_bloques'], check=True)
    subprocess.run(['cp', f'{DIR}/mpi_matrix_2d', BIN_REMOTO], check=True)
    md5 = {}
    for h in WORKERS:
        ssh(h, 'mkdir -p /var/tmp/mpi_bloques')
        subprocess.run(['scp', '-q', BIN_REMOTO, f'{h}:{BIN_REMOTO}'], check=True)
    for h in NODOS:
        md5[h] = ssh(h, f'md5sum {BIN_REMOTO}').stdout.split()[0]
    datos['meta']['md5_binario'] = md5
    if len(set(md5.values())) != 1:
        raise SystemExit(f'Binarios distintos: {md5}')
    log(f'Binario desplegado en {BIN_REMOTO} (md5 {md5["servidor"]})')


def bytes_tx():
    """Bytes transmitidos por la interfaz Wi-Fi de cada nodo."""
    res = {}
    for h in NODOS:
        out = ssh(h, f'cat /sys/class/net/{IFACE}/statistics/tx_bytes').stdout.strip()
        res[h] = int(out) if out.isdigit() else None
    return res


def ping():
    res = {}
    for h in WORKERS:
        p = subprocess.run(['ping', '-c', '3', '-W', '2', h], capture_output=True, text=True)
        m = re.search(r'= [\d.]+/([\d.]+)/', p.stdout)
        res[h] = float(m.group(1)) if m else None
    return res


def limpiar_restos():
    for h in NODOS:
        ssh(h, f'pkill -f {BIN_REMOTO}')


# ---------------------------------------------------------------- Fase A
def fase_cache():
    log('=== Fase A: caché (1 núcleo P, CPU 4) ===')
    bench = f'{DIR}/bench_cache'
    tamanos = [256, 384, 512, 640, 768, 1024, 1280, 1536, 1792, 2048, 2304, 2560, 3072]
    casos = [('ikj', 0), ('tiled', 32), ('tiled', 64), ('tiled', 128)]
    for n in tamanos:
        for kernel, bs in casos:
            reps = 3 if n <= 2048 else 2
            cmd = ['taskset', '-c', '4', bench, kernel, str(n), str(reps)] + ([str(bs)] if bs else [])
            r = parse('RESULT_CACHE', subprocess.run(cmd, capture_output=True, text=True).stdout)
            datos['cache'].append(r)
            log(f'  N={n:5d} {kernel:5s} bs={bs:3d}: {r["GFLOPS"]:.2f} GFLOPS')
        guardar()
    # i-j-k de libro solo en tamaños moderados (es muy lento)
    for n in [256, 512, 768, 1024, 1536, 2048]:
        r = parse('RESULT_CACHE', subprocess.run(['taskset', '-c', '4', bench, 'ijk', str(n), '1'],
                                                 capture_output=True, text=True).stdout)
        datos['cache'].append(r)
        log(f'  N={n:5d} ijk: {r["GFLOPS"]:.2f} GFLOPS')
        guardar()


# ---------------------------------------------------------------- Fase B
def fase_local():
    log('=== Fase B: servidor local ===')
    tamanos = [512, 1024, 1536, 2048, 3072]
    variantes = [('1d', 'ikj'), ('1d', 'tiled'), ('2d', 'tiled')]
    for n in tamanos:
        for p in [1, 4, 8, 16, 24]:
            for algo, kernel in variantes:
                if algo == '2d' and p not in (1, 4, 16):
                    continue
                tiempos = []
                for rep in range(3):
                    cmd = ['mpirun', '-H', f'localhost:{p}', '-np', str(p), BIN_REMOTO, str(n), algo, kernel, str(BS)]
                    pr = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
                    r = parse('RESULT_2D', pr.stdout)
                    if r is None:
                        log(f'  FALLO {n} {p} {algo} {kernel}: {pr.stderr[-300:]}')
                        continue
                    r['rep'] = rep + 1
                    datos['local'].append(r)
                    tiempos.append(r['T_Total'])
                if tiempos:
                    log(f'  N={n:5d} P={p:2d} {algo}-{kernel:5s}: {min(tiempos):.4f}s (mín de {len(tiempos)})')
            guardar()


# ---------------------------------------------------------------- Fase C
def fase_cluster():
    log('=== Fase C: clúster Wi-Fi (pareado e intercalado) ===')
    tamanos = [1024, 2048, 3072]
    procs = [4, 16]
    variantes = [('1d', 'ikj'), ('2d', 'tiled')]
    for rep in (1, 2):
        for n in tamanos:
            for p in procs:
                k = p // 4
                hosts = ','.join(f'{h}:{k}' for h in NODOS)
                orden = variantes if rep == 1 else variantes[::-1]   # alterna quién va primero
                for algo, kernel in orden:
                    reg = {'rep': rep, 'N': n, 'Procs': p, 'Algo': algo, 'Kernel': kernel,
                           'inicio': datetime.datetime.now().isoformat(timespec='seconds'), 'ping_ms': ping()}
                    tx0 = bytes_tx()
                    t0 = time.time()
                    cmd = ['mpirun', '-H', hosts, '-np', str(p)] + MCA + [BIN_REMOTO, str(n), algo, kernel, str(BS)]
                    try:
                        pr = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_CLUSTER)
                        r = parse('RESULT_2D', pr.stdout)
                        if r:
                            reg.update(r, ok=True)
                        else:
                            reg.update(ok=False, error=pr.stderr[-400:])
                    except subprocess.TimeoutExpired:
                        reg.update(ok=False, error=f'timeout > {TIMEOUT_CLUSTER}s')
                        limpiar_restos()
                    reg['duracion_pared'] = round(time.time() - t0, 1)
                    tx1 = bytes_tx()
                    reg['tx_MB'] = {h: round((tx1[h] - tx0[h]) / 1e6, 2) if tx0[h] is not None and tx1[h] is not None else None
                                    for h in NODOS}
                    reg['tx_MB_total'] = round(sum(v for v in reg['tx_MB'].values() if v is not None), 2)
                    datos['cluster'].append(reg)
                    guardar()
                    if reg['ok']:
                        log(f'  rep{rep} N={n} P={p:2d} {algo}-{kernel:5s}: Total={reg["T_Total"]:.1f}s '
                            f'Calc={reg["T_Calc"]:.2f}s  Wi-Fi={reg["tx_MB_total"]:.0f} MB  ping={reg["ping_ms"]}')
                    else:
                        log(f'  rep{rep} N={n} P={p:2d} {algo}-{kernel}: FALLO {reg["error"][:200]}')


if __name__ == '__main__':
    esperar_repeticion()
    datos['meta']['inicio'] = datetime.datetime.now().isoformat(timespec='seconds')
    desplegar()
    # Comprobación de ubicación de rangos: en 16p, cada fila de la malla 4x4 debe quedar en un nodo
    pr = subprocess.run(['mpirun', '-H', ','.join(f'{h}:4' for h in NODOS), '-np', '16', '-x', 'MAP_DEBUG=1'] + MCA +
                        [BIN_REMOTO, '256', '2d', 'tiled', '64'], capture_output=True, text=True, timeout=300)
    datos['meta']['mapa_16p'] = [l for l in pr.stdout.splitlines() if l.startswith('MAP:')]
    log('Mapa 16p: ' + '; '.join(datos['meta']['mapa_16p']))
    guardar()
    fase_cache()
    fase_local()
    fase_cluster()
    datos['meta']['fin'] = datetime.datetime.now().isoformat(timespec='seconds')
    guardar()
    log('Finalizado.')
