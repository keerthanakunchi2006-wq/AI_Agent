// Chart helpers wrapping Chart.js (loaded via CDN in index.html).
const CHART = {
  _store: {},
  palette: ['#3b82f6', '#8b5cf6', '#22c55e', '#f59e0b', '#ef4444', '#14b8a6', '#ec4899', '#06b6d4'],

  _commonOpts() {
    return {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { labels: { color: '#cbd5e1' } }, tooltip: { mode: 'index', intersect: false } },
      scales: {
        x: { ticks: { color: '#94a3b8' }, grid: { color: 'rgba(148,163,184,0.1)' } },
        y: { ticks: { color: '#94a3b8' }, grid: { color: 'rgba(148,163,184,0.1)' } },
      },
    };
  },

  line(canvasId, labels, datasets, opts = {}) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;
    if (this._store[canvasId]) this._store[canvasId].destroy();
    const cfg = {
      type: 'line',
      data: { labels, datasets: datasets.map((d, i) => ({
        label: d.label, data: d.data,
        borderColor: d.color || this.palette[i % this.palette.length],
        backgroundColor: (d.color || this.palette[i % this.palette.length]) + '22',
        tension: 0.35, fill: !!d.fill, pointRadius: 2,
      })) },
      options: this._commonOpts(),
    };
    if (opts.stacked) cfg.options.scales.y.stacked = true;
    this._store[canvasId] = new Chart(ctx, cfg);
  },

  bar(canvasId, labels, datasets, opts = {}) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;
    if (this._store[canvasId]) this._store[canvasId].destroy();
    const cfg = {
      type: 'bar',
      data: { labels, datasets: datasets.map((d, i) => ({
        label: d.label, data: d.data,
        backgroundColor: (d.color || this.palette[i % this.palette.length]) + 'cc',
        borderColor: d.color || this.palette[i % this.palette.length],
        borderWidth: 1, borderRadius: 6,
      })) },
      options: this._commonOpts(),
    };
    if (opts.horizontal) { cfg.options.indexAxis = 'y'; }
    this._store[canvasId] = new Chart(ctx, cfg);
  },

  doughnut(canvasId, labels, data, colors) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;
    if (this._store[canvasId]) this._store[canvasId].destroy();
    this._store[canvasId] = new Chart(ctx, {
      type: 'doughnut',
      data: { labels, datasets: [{ data, backgroundColor: colors || this.palette, borderWidth: 0 }] },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { position: 'right', labels: { color: '#cbd5e1' } } },
      },
    });
  },

  destroy(canvasId) {
    if (this._store[canvasId]) { this._store[canvasId].destroy(); delete this._store[canvasId]; }
  },
};
