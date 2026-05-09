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

  ws.onopen = () => {
    setWsStatus(true);
    wsReconnectDelay = WS_RECONNECT_BASE;
  };
  ws.onmessage = (ev) => {
    try { renderAll(JSON.parse(ev.data)); } catch (_) {}
  };
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
// Render
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

  // Summary totals
  const { totalIn, totalOut } = sumCounts(counts);
  el.querySelector('.stat-in .stat-num').textContent = totalIn;
  el.querySelector('.stat-out .stat-num').textContent = totalOut;

  // Breakdown table
  el.querySelector('tbody').innerHTML = buildTableRows(counts);

  // Recent events
  el.querySelector('.events-list').innerHTML = buildRecentEvents(recent_events);

  // Sparkline
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
      rows.push(`
        <tr>
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
  if (!events || !events.length) {
    return '<div class="no-events">Sem eventos recentes</div>';
  }
  // mostrar os 10 mais recentes (já estão ordenados do mais antigo ao mais novo)
  return [...events].reverse().slice(0, 10).map(ev => {
    const t = formatTime(ev.occurred_at);
    const dir = ev.direction === 'in' ? '↑' : '↓';
    const dirCls = ev.direction === 'in' ? 'in' : 'out';
    const label = CLASS_LABELS[ev.class_name] || ev.class_name;
    return `
      <div class="event-row">
        <span class="event-time">${t}</span>
        <span class="event-cls cls-${ev.class_name}">${label}</span>
        <span class="event-zone">${ev.zone_name}</span>
        <span class="event-dir ${dirCls}">${dir}</span>
      </div>`;
  }).join('');
}

function formatTime(iso) {
  if (!iso) return '--:--:--';
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch (_) { return '--:--:--'; }
}

function sumCounts(counts) {
  let totalIn = 0, totalOut = 0;
  Object.values(counts).forEach(classCounts => {
    Object.values(classCounts).forEach(dirs => {
      totalIn  += dirs.in  ?? 0;
      totalOut += dirs.out ?? 0;
    });
  });
  return { totalIn, totalOut };
}

// ---------------------------------------------------------------------------
// Card factory
// ---------------------------------------------------------------------------
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
      <span class="fps-badge">0.0 fps</span>
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
      <thead>
        <tr>
          <th>Tipo</th>
          <th class="in">Entrada</th>
          <th class="out">Saída</th>
        </tr>
      </thead>
      <tbody></tbody>
    </table>

    <canvas height="55"></canvas>

    <div class="events-section">
      <div class="events-title">Eventos recentes</div>
      <div class="events-list"></div>
    </div>
  `;
  grid.appendChild(el);

  const ctx = el.querySelector('canvas').getContext('2d');
  const history = Array(HISTORY_WINDOW).fill(0);

  const chart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: history.map((_, i) => i),
      datasets: [{
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
          ticks: { color: '#94a3b8', maxTicksLimit: 3 },
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
  fetch('/api/counts').then(r => r.json()).then(renderAll).catch(() => {});
  connectWS();
});
