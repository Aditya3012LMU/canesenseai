/**
 * CANESENSE NIR — Shared Dashboard Utilities
 * Colour helpers, number formatting, and Chart.js theme defaults.
 */

// ── Global Chart.js theme ──────────────────────────────────────────────────
if (typeof Chart !== 'undefined') {
  Chart.defaults.color       = '#707070';
  Chart.defaults.borderColor = '#1a1a1a';
  Chart.defaults.font.family = "'Courier New', monospace";

  // Register a global plugin that draws a dark background on every canvas
  Chart.register({
    id: 'darkBackground',
    beforeDraw(chart) {
      const { ctx, chartArea } = chart;
      if (!chartArea) return;
      ctx.save();
      ctx.fillStyle = '#0b0b0b';
      ctx.fillRect(chartArea.left, chartArea.top,
        chartArea.right  - chartArea.left,
        chartArea.bottom - chartArea.top);
      ctx.restore();
    },
  });
}

// ── Colour constants ───────────────────────────────────────────────────────
const COLORS = {
  green:  '#00ff41',
  yellow: '#ffd600',
  red:    '#ff3b3b',
  blue:   '#4fc3f7',
  purple: '#ce93d8',
  teal:   '#26c6da',
};

function qualityToColor(quality, alpha = 0.75) {
  const map = { High: `rgba(0,255,65,${alpha})`, Medium: `rgba(255,214,0,${alpha})`, Low: `rgba(255,59,59,${alpha})` };
  return map[quality] || `rgba(100,100,100,${alpha})`;
}

function qualityBadge(quality) {
  const cls = { High: 'badge-high', Medium: 'badge-medium', Low: 'badge-low' };
  return `<span class="badge ${cls[quality] || ''}">${quality}</span>`;
}

// ── Number helpers ─────────────────────────────────────────────────────────
function fmt(n, decimals = 2) {
  return typeof n === 'number' ? n.toFixed(decimals) : '—';
}

function fmtCurrency(n, symbol = '₹') {
  if (typeof n !== 'number') return '—';
  return symbol + n.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function average(arr) {
  if (!arr || !arr.length) return 0;
  return arr.reduce((a, b) => a + b, 0) / arr.length;
}

// ── Toast ──────────────────────────────────────────────────────────────────
function showToast(msg, duration = 3500) {
  const el = document.getElementById('toast');
  if (!el) return;
  el.textContent = msg;
  el.classList.add('show');
  clearTimeout(el._tid);
  el._tid = setTimeout(() => el.classList.remove('show'), duration);
}

// ── Standard chart options factory ────────────────────────────────────────
function chartDefaults(overrides = {}) {
  return Object.assign({
    responsive:          true,
    maintainAspectRatio: false,
    animation:           { duration: 400 },
    plugins: {
      legend: { labels: { color: '#888', boxWidth: 12, font: { size: 11 } } },
    },
    scales: {
      x: { ticks: { color: '#666' }, grid: { color: '#111' } },
      y: { ticks: { color: '#888' }, grid: { color: '#1a1a1a' } },
    },
  }, overrides);
}

// ── Batch summary computation ──────────────────────────────────────────────
function summariseSamples(samples) {
  if (!samples || !samples.length) return null;
  const pick = key => samples.map(s => parseFloat(s[key]) || 0);
  const qc   = { High: 0, Medium: 0, Low: 0 };
  samples.forEach(s => { if (qc[s.quality] !== undefined) qc[s.quality]++; });
  return {
    average_TS:      parseFloat(average(pick('TS')).toFixed(2)),
    average_ADF:     parseFloat(average(pick('ADF')).toFixed(2)),
    average_CP:      parseFloat(average(pick('CP')).toFixed(2)),
    average_IVOMD:   parseFloat(average(pick('IVOMD')).toFixed(2)),
    predicted_pol:   parseFloat(average(pick('Pol')).toFixed(2)),
    samples_scanned: samples.length,
    quality_counts:  qc,
  };
}

// ── CSV download helper ────────────────────────────────────────────────────
function downloadCSV(rows, filename, headers) {
  const headerRow = headers.join(',') + '\n';
  const body      = rows.map(r => headers.map(h => `"${r[h] ?? ''}"`).join(',')).join('\n');
  const blob      = new Blob([headerRow + body], { type: 'text/csv' });
  const a         = document.createElement('a');
  a.href          = URL.createObjectURL(blob);
  a.download      = filename;
  a.click();
}

// ── Expose globals ─────────────────────────────────────────────────────────
window.COLORS          = COLORS;
window.qualityToColor  = qualityToColor;
window.qualityBadge    = qualityBadge;
window.fmt             = fmt;
window.fmtCurrency     = fmtCurrency;
window.average         = average;
window.showToast       = showToast;
window.chartDefaults   = chartDefaults;
window.summariseSamples = summariseSamples;
window.downloadCSV     = downloadCSV;
