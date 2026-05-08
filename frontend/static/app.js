'use strict';

const CLASSES = ['pedestrian', 'car', 'motorcycle', 'bus', 'truck', 'bicycle'];
const WS_RECONNECT_BASE = 1000;  // ms
const HISTORY_WINDOW = 60;       // pontos no gráfico (cada ponto = 500ms)

// Estado global
const streamCards = {};     // {stream_id: {el, chart, history}}
let wsReconnectDelay = WS_RECONNECT_BASE;

// ---------------------------------------------------------------------------
// WebSocket
// ---------------------------------------------------------------------------
function connectWS() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const ws = new WebSocket(`${proto}://${location.host}/ws/counts`);

  ws.onopen = () => {
    setWsStatus(true);
    wsReconnectDelay = WS_RECONNECT_BASE;
  };

  ws.onmessage = (ev) => {
    try {
      const data = JSON.parse(ev.data);
      renderAll(data);
    } catch (_) {}
  };

  ws.onclose = ws.onerror = () => {
    setWsStatus(false);
    setTimeout(connectWS, wsReconnectDelay);
    wsReconnectDelay = Math.min(wsReconnectDelay * 2, 30000);
  };
}

function setWsStatus(online) {
  const dot = document.getElementById('ws-indicator');
  const lbl = document.getElementById('ws-label');
  dot.className = 'dot ' + (online ? 'online' : 'offline');
  lbl.textContent = online ? 'Conectado' : 'Desconectado';
}

// ---------------------------------------------------------------------------
// Render
// ---------------------------------------------------------------------------
function renderAll(data) {
  const grid = document.getElementById('streams-grid');
  const empty = document.getElementById('empty-state');
  const ids = Object.keys(data);

  if (ids.length === 0) { empty.style.display = ''; return; }
  empty.style.display = 'none';

  ids.forEach(sid => updateCard(grid, sid, data[sid]));

  // Remove cards de streams que desapareceram
  Object.keys(streamCards).forEach(sid => {
    if (!data[sid]) {
      streamCards[sid].el.remove();
      delete streamCards[sid];
    }
  });
}

function updateCard(grid, sid, streamData) {
  const { counts = {}, fps = 0, online = false } = streamData;

  if (!streamCards[sid]) {
    streamCards[sid] = createCard(grid, sid);
  }

  const { el, chart, history } = streamCards[sid];

  // Header
  el.querySelector('.dot').className = 'dot ' + (online ? 'online' : 'offline');
  el.querySelector('.fps-badge').textContent = fps.toFixed(1) + ' fps';

  // Count table
  const tbody = el.querySelector('tbody');
  tbody.innerHTML = buildTableRows(counts);

  // Chart — total crossings per tick
  const total = sumCounts(counts);
  history.push(total);
  if (history.length > HISTORY_WINDOW) history.shift();

  chart.data.labels = history.map((_, i) => i);
  chart.data.datasets[0].data = [...history];
  chart.update('none');  // 'none' = no animation for performance
}

function buildTableRows(counts) {
  // counts: {zone_name: {class_name: {in: N, out: N}}}
  const rows = [];
  Object.entries(counts).forEach(([zone, classCounts]) => {
    rows.push(`<tr><td colspan="3" style="color:var(--muted);font-size:.75rem;padding-top:.5rem">${zone}</td></tr>`);
    CLASSES.forEach(cls => {
      const dirs = (classCounts[cls] || {});
      const inN = dirs.in ?? 0;
      const outN = dirs.out ?? 0;
      if (inN === 0 && outN === 0) return;
      rows.push(`
        <tr>
          <td class="cls-${cls}">${cls}</td>
          <td class="num in">${inN}</td>
          <td class="num out">${outN}</td>
        </tr>`);
    });
  });
  return rows.join('');
}

function sumCounts(counts) {
  let total = 0;
  Object.values(counts).forEach(classCounts => {
    Object.values(classCounts).forEach(dirs => {
      total += (dirs.in ?? 0) + (dirs.out ?? 0);
    });
  });
  return total;
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
      <div class="card-meta">
        <span class="fps-badge">0.0 fps</span>
      </div>
    </div>
    <table class="count-table">
      <thead>
        <tr>
          <th>Classe</th>
          <th class="in">Entrada</th>
          <th class="out">Saída</th>
        </tr>
      </thead>
      <tbody></tbody>
    </table>
    <canvas height="80"></canvas>
  `;
  grid.appendChild(el);

  const ctx = el.querySelector('canvas').getContext('2d');
  const history = Array(HISTORY_WINDOW).fill(0);

  const chart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: history.map((_, i) => i),
      datasets: [{
        label: 'Cruzamentos',
        data: [...history],
        borderColor: '#3b82f6',
        backgroundColor: 'rgba(59,130,246,.15)',
        borderWidth: 1.5,
        pointRadius: 0,
        fill: true,
        tension: 0.3,
      }],
    },
    options: {
      animation: false,
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        x: { display: false },
        y: {
          display: true,
          beginAtZero: true,
          ticks: { color: '#94a3b8', maxTicksLimit: 4 },
          grid: { color: '#1e293b' },
        },
      },
    },
  });

  return { el, chart, history };
}

// ---------------------------------------------------------------------------
// Bootstrap
// ---------------------------------------------------------------------------
document.addEventListener('DOMContentLoaded', () => {
  // Fetch initial state before WS connects
  fetch('/api/counts')
    .then(r => r.json())
    .then(data => renderAll(data))
    .catch(() => {});

  connectWS();
});
