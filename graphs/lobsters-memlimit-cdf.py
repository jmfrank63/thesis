#!/usr/bin/env python

import common
import matplotlib
import matplotlib.pyplot as plt
import pandas as pd
import sys, os
import re
from glob import glob

from hdrh.histogram import HdrHistogram
from hdrh.log import HistogramLogReader

plot_scale = 2000
plot_offset = 256000

data = pd.DataFrame()
limits = []
pcts = [1, 5] + [x for x in range(10, 74, 10)] + [x for x in range(74, 101, 2)]

lobsters_noria_fn = re.compile("lobsters-direct((?:_)\d+)?(_full)?-(\d+)-(\d+)m.log")
for path in glob(os.path.join(sys.argv[2], 'lobsters-direct*.log')):
    base = os.path.basename(path)
    match = lobsters_noria_fn.fullmatch(base)
    if match is None:
        print(match, path)
        continue
    if os.stat(path).st_size == 0:
        print("empty", path)
        continue

    shards = int(match.group(1)) if match.group(1) else 0
    partial = match.group(2) is None
    scale = int(match.group(3))
    memlimit = float(int(match.group(4)))

    if shards != 0 or scale != plot_scale:
        continue
    
    # check achieved load so we don't consider one that didn't keep up
    target = 0.0
    generated = 0.0
    with open(path, 'r') as f:
        for line in f.readlines():
            if line.startswith("#"):
                if "generated ops/s" in line:
                    generated += float(line.split()[-1])
                elif "target ops/s" in line:
                    target += float(line.split()[-1])
    if generated < 0.95 * target:
        continue
    if memlimit not in limits:
        limits.append(memlimit)

    # time to fetch the cdf
    hist_path = os.path.splitext(path)[0] + '.hist'
    hreader = HistogramLogReader(hist_path, HdrHistogram(1, 60000000, 3))
    histograms = {}
    last = 0
    while True:
        hist = hreader.get_next_interval_histogram()
        if hist is None:
            break
        if hist.get_start_time_stamp() < last:
            # next operation!
            # we're combining them all, so this doesn't matter
            pass
        last = hist.get_start_time_stamp()

        if hist.get_tag() != "sojourn":
            continue

        time = hist.get_end_time_stamp() - hreader.base_time_sec * 1000.0

        if time != plot_offset:
            # only consider steady-state
            continue

        # collapse latencies for all pages
        if time in histograms:
            histograms[time].add(hist)
        else:
            histograms[time] = hist

    df = pd.DataFrame()
    for time, hist in histograms.items():
        row = {
            "memlimit": memlimit,
            "partial": partial,
            "achieved": generated,
        }

        for pct in pcts:
            latency = hist.get_value_at_percentile(pct)
            row["pct"] = pct
            row["latency"] = latency / 1000.0
            df = df.append(row, ignore_index=True)

    data = pd.concat([data, df])

data = data.set_index(["memlimit", "pct"]).sort_index()

fig, ax = plt.subplots()
limits.sort()
print(limits)
limits = [256 * 1024 * 1024, 128 * 1024 * 1024, 64 * 1024 * 1024]
limits.sort()
colors = common.memlimit_colors(len(limits))
limits = limits + [0]
i = 0
for limit in limits:
    d = data.query('memlimit == %f' % limit).reset_index()
    lookup_limit = limit / 1024 / 1024 / 1024
    opmem = common.source['lobsters-noria'].query('until == 1 & op == "all" & partial == True & scale == %d & memlimit == %f' % (plot_scale, lookup_limit))['opmem'].max()
    if limit == 0:
        partial = d.query("partial == True")
        full = d.query("partial == False")
        ax.plot(partial["latency"], partial["pct"], color = 'black', ls = "-", label = 'no eviction (%s)' % (common.bts(opmem)))
        ax.plot(full["latency"], full["pct"], color = 'black', ls = "--", label = "no partial")
    else:
        ax.plot(d["latency"], d["pct"], color = colors[i], label = '%s limit (%s)' % (common.bts(limit), common.bts(opmem)))
        i += 1
ax.set_ylabel("CDF")
ax.set_xlabel("Latency [ms]")
ax.set_xscale('log')
ax.set_xlim(0.1, 10000)
ax.legend()

fig.tight_layout()
plt.savefig("{}.pdf".format(sys.argv[3]), format="pdf")
