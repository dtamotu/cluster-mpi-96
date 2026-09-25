#!/usr/bin/env python3
"""Regenera tablas y figuras desde las copias de evidencia; no ejecuta MPI."""
from pathlib import Path
import csv
import json
import re
import statistics
import hashlib
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, MaxNLocator
import numpy as np

ROOT = Path(__file__).resolve().parent
P = [1, 24, 48, 72, 96]
plt.rcParams.update({'font.size': 10, 'axes.titlesize': 11,
                     'font.family': 'DejaVu Sans', 'pdf.fonttype': 42})
data = {}
logs = {}
for network in ['ethernet', 'wifi']:
    rows = list(csv.DictReader((ROOT / 'datos' / network / 'tiempos.csv').open()))
    assert len(rows) == 25
    for r in rows:
        key = (r['experimento'], int(r['tamano']), int(r['procesos']))
        t = float(r['T_Total'])
        log = ROOT / 'datos' / network / f'{key[0]}_{key[1]}_{key[2]}.log'
        found = re.findall(r'^RESULT_(?:TRAP|2D): (.*)$', log.read_text(), re.M)
        assert len(found) == 1, log
        fields = dict(x.strip().split('=', 1) for x in found[0].split(','))
        assert t == float(fields['T_Total']) and key[2] == int(fields['Procs'])
        data[(network, *key)] = t
        logs[(network, *key)] = fields

def t(net, exp, n, p):
    return data[(net, exp, n, p)]

def table(name, header, body, cols=None):
    cols = cols or ('r' * len(header))
    text = '\\begin{center}\n\\small\n\\begin{tabular}{' + cols + '}\n\\toprule\n'
    text += ' & '.join(header) + ' \\\\\n\\midrule\n'
    for row in body:
        if row is None:
            text += '\\midrule\n'
        else:
            text += ' & '.join(map(str, row)) + ' \\\\\n'
    text += '\\bottomrule\n\\end{tabular}\n\\end{center}\n'
    (ROOT / 'tablas' / (name + '.tex')).write_text(text)

combined = []
for exp, sizes in [('trapecio', [10**8, 10**11]), ('matrices', [1024, 2048, 3072])]:
    for n in sizes:
        rows = []
        for p in P:
            e, w = t('ethernet', exp, n, p), t('wifi', exp, n, p)
            se, sw = t('ethernet', exp, n, 1)/e, t('wifi', exp, n, 1)/w
            rows.append([p, f'{e:.6f}', f'{w:.6f}', f'{se:.2f}', f'{sw:.2f}', f'{w/e:.2f}'])
            combined.append([exp, n, p, e, w, se, sw, 100*se/p, 100*sw/p, w/e])
        table(f'{exp}_{n}', ['$P$', '$T_E$ (s)', '$T_W$ (s)', '$S_E$', '$S_W$', '$T_W/T_E$'], rows)
with (ROOT / 'datos' / 'metricas_informe.csv').open('w') as f:
    writer = csv.writer(f)
    writer.writerow(['experimento','tamano','procesos','T_E','T_W','S_E','S_W','E_E_pct','E_W_pct','T_W_sobre_T_E'])
    writer.writerows(combined)

def axes_style(ax, ylabel):
    ax.set_ylabel(ylabel)
    ax.grid(axis='y', color='0.88', linewidth=.65)
    ax.set_axisbelow(True)
    ax.spines[['top', 'right']].set_visible(False)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f'{v:g}'))
    ax.yaxis.set_major_locator(MaxNLocator(6))

def save(fig, name):
    fig.savefig(ROOT / 'img' / f'{name}.pdf', bbox_inches='tight')
    fig.savefig(ROOT / 'img' / f'{name}.png', dpi=180, bbox_inches='tight')
    plt.close(fig)

def times_plot(exp, n, filename):
    fig, axs = plt.subplots(1, 2, figsize=(10.5, 3.9), layout='constrained')
    for ax, net, title in zip(axs, ['ethernet','wifi'], ['Ethernet', 'Wi-Fi']):
        vals = [t(net,exp,n,p) for p in P]
        bars = ax.bar(np.arange(5), vals, color='white', edgecolor='black', hatch='///' if net=='wifi' else None, width=.6)
        ax.bar_label(bars, labels=[f'{v:.6f}'.rstrip('0').rstrip('.') for v in vals], padding=5, fontsize=9)
        ax.set_xticks(np.arange(5), P)
        ax.set_xlabel('Procesos MPI')
        ax.set_title(title + ' (escala propia)')
        ax.set_ylim(0, max(vals)*1.22)
        axes_style(ax, 'Tiempo total (s)')
    save(fig, filename)

times_plot('matrices',3072,'matrices_tiempo')
times_plot('trapecio',10**8,'trapecio_pequeno')

def metrics_plot(exp,n,filename):
    fig, axs = plt.subplots(1,2,figsize=(10.5,4),layout='constrained')
    for ax, metric in zip(axs, ['speedup','eficiencia']):
        for net, label, marker, ls, offset in [('ethernet','Ethernet','o','-',9),('wifi','Wi-Fi','s','--',-16)]:
            vals = [t(net,exp,n,1)/t(net,exp,n,p) for p in P]
            if metric == 'eficiencia': vals=[100*v/p for v,p in zip(vals,P)]
            ax.plot(P,vals,marker=marker,linestyle=ls,color='black',markerfacecolor='white',label=label)
            for p,v in zip(P,vals):
                if p==1 and net=='wifi':continue
                ax.annotate(f'{v:.2f}',(p,v),xytext=(0,offset),textcoords='offset points',ha='center',fontsize=8)
        ax.set_xticks(P)
        ax.set_xlim(-5,103)
        ax.set_xlabel('Procesos MPI')
        ax.legend(loc='upper right' if exp=='matrices' or metric=='eficiencia' else 'upper left',fontsize=9)
        axes_style(ax, 'Speedup T(1)/T(P)' if metric=='speedup' else 'Eficiencia (%)')
        ax.set_ylim(bottom=-15 if metric=='eficiencia' else (-1.5 if exp=='matrices' else -8),top=120 if metric=='eficiencia' else (10 if exp=='matrices' else 82))
    save(fig,filename)

metrics_plot('trapecio',10**11,'trapecio_metricas')
metrics_plot('matrices',3072,'matrices_metricas')

night = json.loads((ROOT/'datos/historicos/resultados_bloques.json').read_text())
midday = json.loads((ROOT/'datos/historicos/resultados_matrices_eth_vs_wifi.json').read_text())
early = json.loads((ROOT/'datos/historicos/resultados_profiling_repeticion.json').read_text())
rows=[]
for p in [1,4,8,16,24]:
    row=[p]
    for algo,kernel in [('1d','ikj'),('1d','tiled'),('2d','tiled')]:
        sample=[r['T_Total'] for r in night['local'] if r['N']==3072 and r['Procs']==p and r['Algo']==algo and r['Kernel']==kernel]
        assert len(sample) in (0,3)
        row.append(f'{statistics.median(sample):.6f}' if sample else '--')
    rows.append(row)
table('local_historico',['$P$','1D-ikj (s)','1D-tiled (s)','2D-tiled (s)'],rows)

rows=[]
for p in [4,8,16]:
    for r in early['3072'][f'cluster_{p}p']['reps']:
        rows.append([p,r['rep'],r['inicio'].split('T')[1],f"{r['bcast']:.3f}",f"{r['calc']:.3f}",f"{r['total']:.3f}"])
table('madrugada_original',['$P$','Rep.','Inicio','$T_{Bcast}$ (s)','$T_{Calc}$ (s)','$T_{Total}$ (s)'],rows,'rrlrrr')

rows=[]
for p in [4,16]:
    for algo,kernel in [('1d','ikj'),('2d','tiled')]:
        for r in night['cluster']:
            if r['N']==3072 and r['Procs']==p and r['Algo']==algo and r['Kernel']==kernel:
                rows.append([p,algo.upper()+'-'+kernel,r['rep'],f"{r['T_Total']:.3f}",f"{r['tx_MB_total']:.2f}",f"{r['tx_MB_total']/r['T_Total']:.2f}"])
table('madrugada_mb',['$P$','Versión','Rep.','Total (s)','MB TX','MB/s$^{*}$'],rows,'rlrrrr')

fig,axs=plt.subplots(1,2,figsize=(10.5,4.0),layout='constrained')
for ax,key,ylabel in zip(axs,['T_Total','tx_MB_total'],['Tiempo total (s)','MB transmitidos (suma de 4 nodos)']):
    for j,(algo,kernel,hatch) in enumerate([('1d','ikj',''),('2d','tiled','///')]):
        med=[]; lo=[]; hi=[]
        for p in [4,16]:
            v=[r[key] for r in night['cluster'] if r['N']==3072 and r['Procs']==p and r['Algo']==algo and r['Kernel']==kernel]
            m=statistics.median(v); med.append(m);lo.append(m-min(v));hi.append(max(v)-m)
        bars=ax.bar(np.arange(2)+(j-.5)*.35,med,width=.33,color='white',edgecolor='black',hatch=hatch,label=algo.upper()+'-'+kernel,yerr=[lo,hi],capsize=4)
        for b,m,h in zip(bars,med,hi):ax.annotate(f'{m:.2f}',(b.get_x()+b.get_width()/2,m+h),xytext=(0,5),textcoords='offset points',ha='center',fontsize=9)
    ax.set_xticks(np.arange(2),['4 procesos','16 procesos']);ax.set_ylim(0,440 if key=='T_Total' else 1450)
    axes_style(ax,ylabel);ax.legend(loc='upper left',fontsize=9)
save(fig,'madrugada_comparacion')

rows=[]
for p in [4,16,64]:
    for algo,kernel in [('1d','ikj'),('1d','tiled'),('2d','tiled')]:
        row=[p,algo.upper()+'-'+kernel]
        for net in ['ethernet','wifi']:
            sample=[r for r in midday['cluster'] if r['N']==3072 and r['Procs']==p and r['Algo']==algo and r['Kernel']==kernel and r['red']==net]
            row.extend([f"{statistics.median(r['T_Total'] for r in sample):.3f}",f"{statistics.median(r['tx_MB_total'] for r in sample):.2f}"] if sample else ['--','--'])
        rows.append(row)
table('mediodia',['$P$','Versión','Cable (s)','Cable MB','Wi-Fi (s)','Wi-Fi MB'],rows,'rlrrrr')

rows=[]
for p in [24,96]:
    for net,label in [('ethernet','Ethernet'),('wifi','Wi-Fi')]:
        f=logs[(net,'matrices',3072,p)]
        rows.append([p,label,*[f'{float(f[k]):.6f}' for k in ['T_Dist','T_Calc','T_Gather','T_Total']]])
table('fases',['$P$','Red','Distribuir (s)','Calcular (s)','Reunir (s)','Total (s)'],rows,'rlrrrr')

checkrows=[]
for n in [1024,2048,3072]:
    fs=[f for key,f in logs.items() if key[1]=='matrices' and key[2]==n]
    checks={f['Checksum'] for f in fs};ws={f['WSum'] for f in fs}
    assert len(checks)==len(ws)==1 and len(fs)==10
    checkrows.append([n,next(iter(checks)),next(iter(ws)).replace('e+',r'\,e+'),'10/10'])
table('checksums',['$N$','Suma diagonal','Suma ponderada','Coinciden'],checkrows,'rrrl')
errs=[float(f['Error']) for key,f in logs.items() if key[1]=='trapecio']

with (ROOT/'datos/validacion.json').open('w') as f:
    json.dump({'logs_coinciden_con_csv':50,'matrices_checksums_consistentes':30,'trapecio_error_absoluto_maximo':max(errs),'nota':'Consistencia a la precisión impresa; no equivale a validación elemento a elemento.'},f,indent=2)
for entry in json.loads((ROOT/'datos/procedencia.json').read_text()):
    assert hashlib.sha256((ROOT/entry['copia']).read_bytes()).hexdigest()==entry['sha256']
print('50 resultados coinciden con los logs. 30 checksums de matrices consistentes.')
print('Error absoluto máximo trapecio:',max(errs))
print('5 figuras y tablas regeneradas; evidencias SHA-256 verificadas.')
