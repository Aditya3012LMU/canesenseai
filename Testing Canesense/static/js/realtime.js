/**
 * CANESENSE NIR — Real-Time Prediction Dashboard
 * Handles CSV upload, SSE streaming, live chart & KPI updates.
 */

// ── Chart defaults ─────────────────────────────────────────────────────────
Chart.defaults.color       = '#707070';
Chart.defaults.borderColor = '#1a1a1a';

const C_GREEN  = '#00ff41';
const C_YELLOW = '#ffd600';
const C_RED    = '#ff3b3b';
const C_BLUE   = '#4fc3f7';
const C_PURPLE = '#ce93d8';

function qualityColor(q, alpha = 0.75) {
  if (q === 'High')   return `rgba(0,255,65,${alpha})`;
  if (q === 'Medium') return `rgba(255,214,0,${alpha})`;
  return `rgba(255,59,59,${alpha})`;
}

// ── State ──────────────────────────────────────────────────────────────────
let sessionId   = null;
let evtSource   = null;
let predictions = [];
let totalRows   = 0;    // estimated from file before upload

// Running accumulators for KPIs
let sumTS = 0, sumADF = 0, sumCP = 0, sumIVOMD = 0, sumPol = 0;
let countHigh = 0, countMedium = 0, countLow = 0;

// Chart instances
let sugarChart, scatterChart, pieChart, avgLineChart;

// ── Chart initialisation ───────────────────────────────────────────────────
function initCharts() {
  const base = {
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: 400 },
    plugins: {
      legend: { labels: { color: '#888', boxWidth: 12, font: { size: 11 } } },
    },
  };

  // 1. Sugar distribution bar chart
  sugarChart = new Chart(document.getElementById('sugarBar'), {
    type: 'bar',
    data: {
      labels: [],
      datasets: [{
        label: 'Total Sugar (TS %)',
        data: [],
        backgroundColor: [],
        borderRadius: 3,
        borderWidth: 0,
      }],
    },
    options: {
      ...base,
      scales: {
        x: {
          ticks: { color: '#555', maxRotation: 70, font: { size: 9 } },
          grid:  { color: '#111' },
        },
        y: {
          ticks: { color: '#888' },
          grid:  { color: '#1a1a1a' },
          title: { display: true, text: 'TS %', color: '#555', font: { size: 11 } },
        },
      },
      plugins: {
        ...base.plugins,
        tooltip: { callbacks: { label: ctx => ` TS: ${ctx.parsed.y}%` } },
      },
    },
  });

  // 2. Scatter: Fiber vs Sugar
  scatterChart = new Chart(document.getElementById('scatterChart'), {
    type: 'scatter',
    data: {
      datasets: [{
        label: 'Samples',
        data: [],
        pointRadius: 6,
        pointHoverRadius: 8,
        backgroundColor: [],
      }],
    },
    options: {
      ...base,
      scales: {
        x: {
          ticks: { color: '#888' },
          grid:  { color: '#1a1a1a' },
          title: { display: true, text: 'ADF — Fiber %', color: '#666', font: { size: 11 } },
        },
        y: {
          ticks: { color: '#888' },
          grid:  { color: '#1a1a1a' },
          title: { display: true, text: 'TS — Sugar %', color: '#666', font: { size: 11 } },
        },
      },
      plugins: {
        ...base.plugins,
        tooltip: {
          callbacks: {
            label: ctx => [
              `Sample: ${ctx.raw.id}`,
              `ADF: ${ctx.raw.x}%`,
              `TS: ${ctx.raw.y}%`,
              `Quality: ${ctx.raw.quality}`,
            ],
          },
        },
      },
    },
  });

  // 3. Quality pie / doughnut
  pieChart = new Chart(document.getElementById('pieChart'), {
    type: 'doughnut',
    data: {
      labels: ['High', 'Medium', 'Low'],
      datasets: [{
        data: [0, 0, 0],
        backgroundColor: [
          'rgba(0,255,65,0.8)',
          'rgba(255,214,0,0.8)',
          'rgba(255,59,59,0.8)',
        ],
        borderColor: [C_GREEN, C_YELLOW, C_RED],
        borderWidth: 1,
      }],
    },
    options: {
      ...base,
      cutout: '60%',
      plugins: {
        legend: {
          position: 'bottom',
          labels: { color: '#888', font: { size: 11 } },
        },
      },
    },
  });

  // 4. Running average line chart
  avgLineChart = new Chart(document.getElementById('avgLine'), {
    type: 'line',
    data: {
      labels: [],
      datasets: [
        { label: 'Avg TS',    data: [], borderColor: C_GREEN,  tension: 0.4, borderWidth: 2, pointRadius: 3, fill: false },
        { label: 'Avg ADF',   data: [], borderColor: C_YELLOW, tension: 0.4, borderWidth: 2, pointRadius: 3, fill: false },
        { label: 'Avg CP',    data: [], borderColor: C_BLUE,   tension: 0.4, borderWidth: 2, pointRadius: 3, fill: false },
        { label: 'Avg IVOMD', data: [], borderColor: C_PURPLE, tension: 0.4, borderWidth: 2, pointRadius: 3, fill: false },
      ],
    },
    options: {
      ...base,
      scales: {
        x: { ticks: { color: '#555', font: { size: 9 }, maxTicksLimit: 12 }, grid: { color: '#111' } },
        y: { ticks: { color: '#888' }, grid: { color: '#1a1a1a' } },
      },
    },
  });
}

// ── File input ─────────────────────────────────────────────────────────────
document.getElementById('fileInput').addEventListener('change', e => {
  const f = e.target.files[0];
  if (!f) return;
  document.getElementById('fileName').textContent = f.name;
  document.getElementById('startBtn').disabled    = false;
  // Estimate row count from size (very rough)
  totalRows = Math.max(1, Math.round(f.size / 1500));
});

// ── Upload & start prediction ───────────────────────────────────────────────
async function startPrediction() {
  const fileInput = document.getElementById('fileInput');
  if (!fileInput.files.length) {
    showToast('⚠ Please select a CSV file first.');
    return;
  }

  const farmerId   = document.getElementById('farmerId').value.trim()   || `FARM-${Date.now()}`;
  const farmerName = document.getElementById('farmerName').value.trim() || 'Unknown Farmer';

  // Reset state
  predictions = [];
  sumTS = sumADF = sumCP = sumIVOMD = sumPol = 0;
  countHigh = countMedium = countLow = 0;
  resetCharts();
  resetTable();
  resetKPIs();
  document.getElementById('exportBtn').disabled = true;

  // UI: upload state
  setStatus('running', 'Uploading…');
  document.getElementById('progressSection').style.display = '';
  document.getElementById('startBtn').disabled = true;
  document.getElementById('stopBtn').style.display = '';

  // 1. Upload file
  const formData = new FormData();
  formData.append('file', fileInput.files[0]);

  let uploadRes;
  try {
    uploadRes = await fetch('/upload', { method: 'POST', body: formData });
    const uploadData = await uploadRes.json();
    if (!uploadRes.ok || uploadData.error) {
      showToast('Upload error: ' + (uploadData.error || 'Unknown'));
      resetUploadUI();
      return;
    }
    sessionId = uploadData.session_id;
  } catch (err) {
    showToast('Upload failed: ' + err.message);
    resetUploadUI();
    return;
  }

  setStatus('running', 'Predicting…');

  // 2. Open SSE stream
  const url = `/predict?session_id=${sessionId}&farmer_id=${encodeURIComponent(farmerId)}&farmer_name=${encodeURIComponent(farmerName)}`;
  evtSource = new EventSource(url);

  evtSource.onmessage = e => {
    const msg = JSON.parse(e.data);

    if (msg.type === 'error') {
      showToast('Error: ' + msg.message);
      evtSource.close();
      resetUploadUI();
      setStatus('error', 'Error occurred');
      return;
    }

    if (msg.type === 'prediction') {
      const p = msg.data;
      predictions.push(p);
      updateAccumulators(p);
      updateCharts(p);
      updateKPIs();
      updateTable(p);
      updateProgress();
      document.getElementById('currentSample').textContent =
        `Processing sample ${p.sample_id} — ${p.quality} quality  |  TS: ${p.TS}%  |  Pol: ${p.Pol}%`;
      return;
    }

    if (msg.type === 'done') {
      evtSource.close();
      evtSource = null;
      setStatus('done', 'Complete');
      document.getElementById('stopBtn').style.display = 'none';
      document.getElementById('startBtn').disabled = false;
      document.getElementById('exportBtn').disabled = false;
      document.getElementById('progressBar').style.width = '100%';
      document.getElementById('progressLabel').textContent =
        `${predictions.length} / ${predictions.length} samples`;
      document.getElementById('currentSample').textContent =
        `✓ Prediction complete — ${predictions.length} samples processed`;
      showToast(`✓ Done! ${predictions.length} samples predicted.`);
    }
  };

  evtSource.onerror = () => {
    if (evtSource) { evtSource.close(); evtSource = null; }
    if (predictions.length > 0) {
      setStatus('done', 'Complete');
      document.getElementById('exportBtn').disabled = false;
    } else {
      setStatus('error', 'Connection lost');
      showToast('Connection error. Please try again.');
    }
    document.getElementById('stopBtn').style.display = 'none';
    document.getElementById('startBtn').disabled = false;
  };
}

function stopPrediction() {
  if (evtSource) { evtSource.close(); evtSource = null; }
  setStatus('idle', 'Stopped');
  document.getElementById('stopBtn').style.display = 'none';
  document.getElementById('startBtn').disabled = false;
  if (predictions.length > 0) document.getElementById('exportBtn').disabled = false;
  showToast('Prediction stopped.');
}

// ── Accumulators ────────────────────────────────────────────────────────────
function updateAccumulators(p) {
  const n = predictions.length;
  sumTS    += p.TS;
  sumADF   += p.ADF;
  sumCP    += p.CP;
  sumIVOMD += p.IVOMD;
  sumPol   += p.Pol;
  if (p.quality === 'High')   countHigh++;
  else if (p.quality === 'Medium') countMedium++;
  else countLow++;
}

// ── KPI updates ─────────────────────────────────────────────────────────────
function updateKPIs() {
  const n = predictions.length;
  if (n === 0) return;
  animateValue('kpiTS',    sumTS    / n, 1);
  animateValue('kpiADF',   sumADF   / n, 1);
  animateValue('kpiCP',    sumCP    / n, 2);
  animateValue('kpiIVOMD', sumIVOMD / n, 1);
  animateValue('kpiPol',   sumPol   / n, 2);
  document.getElementById('kpiCount').textContent = n;
}

function animateValue(id, val, decimals) {
  document.getElementById(id).textContent = val.toFixed(decimals);
}

function resetKPIs() {
  ['kpiTS','kpiADF','kpiCP','kpiIVOMD','kpiPol'].forEach(id => {
    document.getElementById(id).textContent = '—';
  });
  document.getElementById('kpiCount').textContent = '0';
}

// ── Chart updates ────────────────────────────────────────────────────────────
function updateCharts(p) {
  const n = predictions.length;
  const qc = qualityColor(p.quality, 0.75);

  // Sugar bar
  sugarChart.data.labels.push(p.sample_id);
  sugarChart.data.datasets[0].data.push(p.TS);
  sugarChart.data.datasets[0].backgroundColor.push(qc);
  sugarChart.update('none');

  // Scatter
  scatterChart.data.datasets[0].data.push({ x: p.ADF, y: p.TS, quality: p.quality, id: p.sample_id });
  scatterChart.data.datasets[0].backgroundColor.push(qc);
  scatterChart.update('none');

  // Pie
  pieChart.data.datasets[0].data = [countHigh, countMedium, countLow];
  pieChart.update('none');

  // Running average line
  avgLineChart.data.labels.push(p.sample_id);
  avgLineChart.data.datasets[0].data.push(parseFloat((sumTS    / n).toFixed(2)));
  avgLineChart.data.datasets[1].data.push(parseFloat((sumADF   / n).toFixed(2)));
  avgLineChart.data.datasets[2].data.push(parseFloat((sumCP    / n).toFixed(2)));
  avgLineChart.data.datasets[3].data.push(parseFloat((sumIVOMD / n).toFixed(2)));
  avgLineChart.update('none');
}

function resetCharts() {
  [sugarChart, scatterChart, avgLineChart].forEach(c => {
    c.data.labels = [];
    c.data.datasets.forEach(d => { d.data = []; if (d.backgroundColor) d.backgroundColor = []; });
    c.update('none');
  });
  pieChart.data.datasets[0].data = [0, 0, 0];
  pieChart.update('none');
}

// ── Table ────────────────────────────────────────────────────────────────────
function updateTable(p) {
  const tbody = document.getElementById('resultsBody');
  // Remove placeholder row on first result
  if (predictions.length === 1) tbody.innerHTML = '';

  const badgeCls = p.quality.toLowerCase();
  const row = document.createElement('tr');
  row.innerHTML = `
    <td style="color:var(--green)">${p.sample_id}</td>
    <td>${p.TS}</td>
    <td style="color:var(--yellow)">${p.ADF}</td>
    <td style="color:#4fc3f7">${p.CP}</td>
    <td style="color:#ce93d8">${p.IVOMD}</td>
    <td style="font-weight:700">${p.Pol}%</td>
    <td><span class="badge badge-${badgeCls}">${p.quality}</span></td>`;
  tbody.prepend(row);
  row.style.animation = 'none';
  row.style.opacity   = '0';
  row.style.transform = 'translateY(-6px)';
  requestAnimationFrame(() => {
    row.style.transition = 'opacity 0.3s, transform 0.3s';
    row.style.opacity    = '1';
    row.style.transform  = 'translateY(0)';
  });
}

function resetTable() {
  document.getElementById('resultsBody').innerHTML =
    '<tr><td colspan="7" style="text-align:center;color:var(--text-lo);padding:30px;">Waiting for predictions…</td></tr>';
}

// ── Progress ──────────────────────────────────────────────────────────────────
function updateProgress() {
  const n   = predictions.length;
  const est = Math.max(n, totalRows);
  const pct = Math.min(99, Math.round((n / est) * 100));
  document.getElementById('progressBar').style.width  = pct + '%';
  document.getElementById('progressLabel').textContent = `${n} / ~${est} samples`;
}

// ── Status badge ─────────────────────────────────────────────────────────────
function setStatus(type, label) {
  const el = document.getElementById('statusBadge');
  el.className = `status-badge status-${type}`;
  if (type === 'running') {
    el.innerHTML = `<div class="pulse"></div> ${label.toUpperCase()}`;
  } else {
    const icons = { idle:'●', done:'✓', error:'✕' };
    el.innerHTML = `${icons[type] || '●'} ${label.toUpperCase()}`;
  }
}

// ── UI helpers ────────────────────────────────────────────────────────────────
function resetUploadUI() {
  document.getElementById('startBtn').disabled      = false;
  document.getElementById('stopBtn').style.display  = 'none';
}

function showToast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(t._timeout);
  t._timeout = setTimeout(() => t.classList.remove('show'), 3500);
}

// ── Export CSV ────────────────────────────────────────────────────────────────
function exportCSV() {
  if (!predictions.length) return;
  const header = 'sample_id,TS,ADF,CP,IVOMD,Pol,quality\n';
  const rows   = predictions.map(p =>
    `${p.sample_id},${p.TS},${p.ADF},${p.CP},${p.IVOMD},${p.Pol},${p.quality}`
  ).join('\n');
  const blob = new Blob([header + rows], { type: 'text/csv' });
  const a    = document.createElement('a');
  a.href     = URL.createObjectURL(blob);
  a.download = `predictions_${Date.now()}.csv`;
  a.click();
}

// ── Boot ───────────────────────────────────────────────────────────────────────
initCharts();
