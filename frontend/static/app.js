'use strict';

const CLASSES = ['pedestrian', 'car', 'motorcycle', 'bus', 'truck', 'bicycle'];
const CLASS_LABELS = {
  pedestrian: 'Pedestre',
  car: 'Carro',
  motorcycle: 'Moto',
  bus: 'Ônibus',
  truck: 'Caminhão',
  bicycle: 'Bicicleta',
};
const WS_RECONNECT_BASE = 1000;
const HISTORY_WINDOW = 60;

const streamCards = {};
let wsReconnectDelay = WS_RECONNECT_BASE;

// ---------------------------------------------------------------------------
// WebSocket
// ---------------------------------------------------------------------------
function connectWS() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const ws = new WebSocket(`${proto}://${location.host}/ws/counts`);
  ws.onopen = () => { setWsStatus(true); wsReconnectDelay = WS_RECONNECT_BASE; };
  ws.onmessage = (ev) => { try { renderAll(JSON.parse(ev.data)); } catch (_) {} };
  ws.onclose = ws.onerror = () => {
    setWsStatus(false);
    setTimeout(connectWS, wsReconnectDelay);
    wsReconnectDelay = Math.min(wsReconnectDelay * 2, 30000);
  };
}

function setWsStatus(online) {
  document.getElementById('ws-indicator').className = 'dot ' + (online ? 'online' : 'offline');
  document.getElementById('ws-label').textContent = online ? 'Conectado' : 'Desconectado';
}

// ---------------------------------------------------------------------------
// Live dashboard
// ---------------------------------------------------------------------------
function renderAll(data) {
  const grid = document.getElementById('streams-grid');
  const empty = document.getElementById('empty-state');
  const ids = Object.keys(data);
  if (!ids.length) { empty.style.display = ''; return; }
  empty.style.display = 'none';
  ids.forEach(sid => updateCard(grid, sid, data[sid]));
  Object.keys(streamCards).forEach(sid => {
    if (!data[sid]) { streamCards[sid].el.remove(); delete streamCards[sid]; }
  });
}

function updateCard(grid, sid, streamData) {
  const { counts = {}, fps = 0, online = false, recent_events = [] } = streamData;
  if (!streamCards[sid]) streamCards[sid] = createCard(grid, sid);
  const { el, chart, history } = streamCards[sid];

  el.querySelector('.dot').className = 'dot ' + (online ? 'online' : 'offline');
  el.querySelector('.fps-badge').textContent = fps.toFixed(1) + ' fps';

  const { totalIn, totalOut } = sumCounts(counts);
  el.querySelector('.stat-in .stat-num').textContent = totalIn;
  el.querySelector('.stat-out .stat-num').textContent = totalOut;

  el.querySelector('tbody').innerHTML = buildTableRows(counts);
  el.querySelector('.events-list').innerHTML = buildRecentEvents(recent_events);

  const total = totalIn + totalOut;
  history.push(total);
  if (history.length > HISTORY_WINDOW) history.shift();
  chart.data.labels = history.map((_, i) => i);
  chart.data.datasets[0].data = [...history];
  chart.update('none');
}

function buildTableRows(counts) {
  const rows = [];
  Object.entries(counts).forEach(([zone, classCounts]) => {
    rows.push(`<tr><td colspan="3" class="zone-label">${zone}</td></tr>`);
    CLASSES.forEach(cls => {
      const dirs = classCounts[cls] || {};
      const inN = dirs.in ?? 0;
      const outN = dirs.out ?? 0;
      if (inN === 0 && outN === 0) return;
      rows.push(`<tr>
        <td class="cls-${cls}">${CLASS_LABELS[cls] || cls}</td>
        <td class="num in">${inN}</td>
        <td class="num out">${outN}</td>
      </tr>`);
    });
  });
  if (!rows.length) rows.push(`<tr><td colspan="3" class="no-data">Aguardando cruzamentos...</td></tr>`);
  return rows.join('');
}

function buildRecentEvents(events) {
  if (!events || !events.length) return '<div class="no-events">Sem eventos recentes</div>';
  return [...events].reverse().slice(0, 8).map(ev => {
    const dir = ev.direction === 'in' ? '↑' : '↓';
    const dirCls = ev.direction === 'in' ? 'in' : 'out';
    return `<div class="event-row">
      <span class="event-time">${formatTime(ev.occurred_at)}</span>
      <span class="event-cls cls-${ev.class_name}">${CLASS_LABELS[ev.class_name] || ev.class_name}</span>
      <span class="event-zone">${ev.zone_name}</span>
      <span class="event-dir ${dirCls}">${dir}</span>
    </div>`;
  }).join('');
}

function sumCounts(counts) {
  let totalIn = 0, totalOut = 0;
  Object.values(counts).forEach(cc => Object.values(cc).forEach(d => {
    totalIn += d.in ?? 0; totalOut += d.out ?? 0;
  }));
  return { totalIn, totalOut };
}

function formatTime(iso) {
  if (!iso) return '--:--:--';
  try { return new Date(iso).toLocaleTimeString('pt-BR'); } catch (_) { return '--:--:--'; }
}

function formatDateTime(iso) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString('pt-BR', {
      day: '2-digit', month: '2-digit', year: 'numeric',
      hour: '2-digit', minute: '2-digit', second: '2-digit',
    });
  } catch (_) { return '—'; }
}

function createCard(grid, sid) {
  const el = document.createElement('div');
  el.className = 'card';
  el.dataset.sid = sid;
  el.innerHTML = `
    <div class="card-header">
      <div class="card-title">
        <span class="dot offline"></span>
        <span style="margin-left:.4rem">${sid}</span>
      </div>
      <div style="display:flex;align-items:center;gap:.5rem">
        <span class="fps-badge">0.0 fps</span>
        <button class="btn-detail" data-sid="${sid}">Relatório</button>
      </div>
    </div>

    <div class="summary-stats">
      <div class="stat-box stat-in">
        <span class="stat-num">0</span>
        <span class="stat-label">↑ Entrada</span>
      </div>
      <div class="stat-box stat-out">
        <span class="stat-num">0</span>
        <span class="stat-label">↓ Saída</span>
      </div>
    </div>

    <table class="count-table">
      <thead><tr><th>Tipo</th><th class="in">Entrada</th><th class="out">Saída</th></tr></thead>
      <tbody></tbody>
    </table>

    <canvas height="55"></canvas>

    <div class="events-section">
      <div class="events-title">Eventos recentes</div>
      <div class="events-list"></div>
    </div>
  `;
  grid.appendChild(el);

  el.querySelector('.btn-detail').addEventListener('click', () => openReport(sid));

  const ctx = el.querySelector('canvas').getContext('2d');
  const history = Array(HISTORY_WINDOW).fill(0);
  const chart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: history.map((_, i) => i),
      datasets: [{ data: [...history], borderColor: '#3b82f6', backgroundColor: 'rgba(59,130,246,.15)', borderWidth: 1.5, pointRadius: 0, fill: true, tension: 0.3 }],
    },
    options: {
      animation: false, responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        x: { display: false },
        y: { display: true, beginAtZero: true, ticks: { color: '#94a3b8', maxTicksLimit: 3 }, grid: { color: '#1e293b' } },
      },
    },
  });
  return { el, chart, history };
}

// ---------------------------------------------------------------------------
// Report modal
// ---------------------------------------------------------------------------
let reportChart = null;
let currentSid = null;

function openReport(sid) {
  currentSid = sid;
  document.getElementById('modal-stream-name').textContent = sid;
  document.getElementById('report-modal').classList.remove('hidden');
  document.body.style.overflow = 'hidden';

  // set default: today
  const now = new Date();
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  document.getElementById('filter-from').value = toLocalInput(todayStart);
  document.getElementById('filter-to').value = toLocalInput(now);

  fetchReport(sid);
}

function closeReport() {
  document.getElementById('report-modal').classList.add('hidden');
  document.body.style.overflow = '';
  currentSid = null;
}

function toLocalInput(d) {
  const pad = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

async function fetchReport(sid) {
  const from = document.getElementById('filter-from').value;
  const to   = document.getElementById('filter-to').value;
  const cls  = document.getElementById('filter-class').value;

  let url = `/api/history/${encodeURIComponent(sid)}?limit=1000`;
  if (from) url += `&from=${encodeURIComponent(new Date(from).toISOString())}`;
  if (to)   url += `&to=${encodeURIComponent(new Date(to).toISOString())}`;
  if (cls)  url += `&class=${encodeURIComponent(cls)}`;

  try {
    const rows = await fetch(url).then(r => r.json());
    renderReport(rows);
  } catch (e) {
    document.getElementById('report-tbody').innerHTML =
      `<tr><td colspan="4" style="color:var(--red);text-align:center">Erro ao carregar dados.</td></tr>`;
  }
}

function renderReport(rows) {
  const summaryEl = document.getElementById('report-summary');
  const totalsEl  = document.getElementById('report-totals');
  const tbody     = document.getElementById('report-tbody');
  const empty     = document.getElementById('report-empty');

  if (reportChart) { reportChart.destroy(); reportChart = null; }

  if (!rows.length) {
    summaryEl.classList.add('hidden');
    totalsEl.innerHTML = '<span style="color:var(--muted);font-size:.85rem">Sem dados no período.</span>';
    tbody.innerHTML = '';
    empty.classList.remove('hidden');
    return;
  }
  empty.classList.add('hidden');

  // --- totais por classe ---
  const totals = {};
  rows.forEach(r => {
    if (!totals[r.class_name]) totals[r.class_name] = { in: 0, out: 0 };
    totals[r.class_name][r.direction] = (totals[r.class_name][r.direction] || 0) + 1;
  });

  // --- contagens por hora (0-23) ---
  const hourCounts = Array(24).fill(0);
  rows.forEach(r => {
    const h = new Date(r.occurred_at).getHours();
    if (h >= 0 && h < 24) hourCounts[h]++;
  });

  const maxCount  = Math.max(...hourCounts);
  const peakHour  = maxCount > 0 ? hourCounts.indexOf(maxCount) : null;

  // tipo mais frequente
  const sorted = Object.entries(totals)
    .map(([k, v]) => [k, v.in + v.out])
    .sort((a, b) => b[1] - a[1]);
  const topEntry = sorted[0];

  // --- sumário ---
  summaryEl.classList.remove('hidden');
  summaryEl.innerHTML = `
    <div class="summary-item">
      <span class="summary-label">Total Impactos</span>
      <span class="summary-value">${rows.length}</span>
    </div>
    <div class="summary-item">
      <span class="summary-label">Horário de Pico</span>
      <span class="summary-value">${peakHour !== null ? peakHour + 'h' : '—'}</span>
      <span class="summary-sub">${maxCount > 0 ? maxCount + ' cruzamentos' : 'Sem dados'}</span>
    </div>
    <div class="summary-item">
      <span class="summary-label">Tipo mais frequente</span>
      <span class="summary-value cls-${topEntry ? topEntry[0] : ''}">${topEntry ? (CLASS_LABELS[topEntry[0]] || topEntry[0]) : '—'}</span>
      <span class="summary-sub">${topEntry ? topEntry[1] + ' detecções' : ''}</span>
    </div>`;

  // --- chips por tipo ---
  totalsEl.innerHTML = sorted.map(([cls, total]) => {
    const d = totals[cls];
    return `<div class="total-chip">
      <span class="cls-${cls}">${CLASS_LABELS[cls] || cls}</span>
      <span class="chip-count">${total}</span>
      <span class="chip-detail">↑${d.in} ↓${d.out}</span>
    </div>`;
  }).join('');

  // --- gráfico 24h ---
  const labels = Array.from({ length: 24 }, (_, i) => i + 'h');
  const bgColors = hourCounts.map((_, i) =>
    i === peakHour ? 'rgba(234,179,8,.8)' : 'rgba(59,130,246,.55)'
  );
  const borderColors = hourCounts.map((_, i) =>
    i === peakHour ? '#eab308' : '#3b82f6'
  );

  reportChart = new Chart(document.getElementById('report-chart').getContext('2d'), {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: 'Cruzamentos',
        data: hourCounts,
        backgroundColor: bgColors,
        borderColor: borderColors,
        borderWidth: 1,
      }],
    },
    options: {
      responsive: true,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: { label: ctx => `${ctx.parsed.y} cruzamentos` },
        },
      },
      scales: {
        x: { ticks: { color: '#94a3b8', font: { size: 10 } }, grid: { color: '#1e293b' } },
        y: { beginAtZero: true, ticks: { color: '#94a3b8', precision: 0 }, grid: { color: '#1e293b' } },
      },
    },
  });

  // --- tabela ---
  tbody.innerHTML = rows.map(r => {
    const dir    = r.direction === 'in' ? '↑ Entrada' : '↓ Saída';
    const dirCls = r.direction === 'in' ? 'in' : 'out';
    return `<tr>
      <td class="mono">${formatDateTime(r.occurred_at)}</td>
      <td class="cls-${r.class_name}">${CLASS_LABELS[r.class_name] || r.class_name}</td>
      <td style="color:var(--muted)">${r.zone_name}</td>
      <td class="${dirCls}" style="font-weight:600">${dir}</td>
    </tr>`;
  }).join('');
}

// Modal events
document.getElementById('btn-modal-close').addEventListener('click', closeReport);
document.getElementById('report-modal').addEventListener('click', e => {
  if (e.target === document.getElementById('report-modal')) closeReport();
});
document.getElementById('btn-filter').addEventListener('click', () => {
  if (currentSid) fetchReport(currentSid);
});
document.getElementById('btn-export').addEventListener('click', () => {
  if (!currentSid) return;
  const from = document.getElementById('filter-from').value;
  const to   = document.getElementById('filter-to').value;
  const cls  = document.getElementById('filter-class').value;
  let url = `/api/history/${encodeURIComponent(currentSid)}/export?format=csv`;
  if (from) url += `&from=${encodeURIComponent(new Date(from).toISOString())}`;
  if (to)   url += `&to=${encodeURIComponent(new Date(to).toISOString())}`;
  if (cls)  url += `&class=${encodeURIComponent(cls)}`;
  window.open(url, '_blank');
});

// ---------------------------------------------------------------------------
// Bootstrap
// ---------------------------------------------------------------------------
document.addEventListener('DOMContentLoaded', () => {
  fetch('/api/counts').then(r => r.json()).then(renderAll).catch(() => {});
  connectWS();
});
