'use strict';
(function () {

// ── Constants ────────────────────────────────────────────────────────────────
const ALL_CLASSES = ['pedestrian', 'car', 'motorcycle', 'bus', 'truck', 'bicycle'];
const ZONE_COLORS = ['#3b82f6', '#22c55e', '#eab308', '#a855f7', '#f97316', '#06b6d4'];
const CANVAS_MAX_W = 640;

// ── State ────────────────────────────────────────────────────────────────────
const state = {
  streams: [],
  editId: null,       // null = create mode
  zones: [],          // committed zones: [{type, name, points, direction, track_classes}]

  // Canvas drawing state machine
  tool: 'line',
  drawing: false,
  pendingPts: [],     // image-space coordinates [[x,y], ...]
  mouseImgPt: null,   // current mouse pos in image coords

  // Canvas image info
  imgEl: null,
  imgW: 1,
  imgH: 1,
  canvasReady: false,

  // dblclick guard: browsers fire click×2 then dblclick
  dblclickFired: false,
};

// ── DOM refs ─────────────────────────────────────────────────────────────────
const streamModal  = document.getElementById('stream-modal');
const confirmModal = document.getElementById('confirm-modal');
const canvas       = document.getElementById('zone-canvas');
const ctx          = canvas.getContext('2d');
const canvasHint   = document.getElementById('canvas-hint');
const zonesList    = document.getElementById('zones-list');
const formError    = document.getElementById('form-error');
const btnCancelZone= document.getElementById('btn-cancel-zone');

// ── Utilities ─────────────────────────────────────────────────────────────────
function api(method, path, body) {
  return fetch(path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  }).then(async r => {
    if (!r.ok) {
      const err = await r.json().catch(() => ({ detail: r.statusText }));
      throw new Error(err.detail || 'Erro desconhecido');
    }
    return r.json().catch(() => null);
  });
}

// ── Stream list ───────────────────────────────────────────────────────────────
async function loadStreams() {
  try {
    state.streams = await api('GET', '/api/streams');
    renderTable();
  } catch (e) {
    console.error('Erro ao carregar streams:', e);
  }
}

function renderTable() {
  const tbody = document.getElementById('streams-tbody');
  const empty = document.getElementById('empty-state');

  if (!state.streams.length) {
    tbody.innerHTML = '';
    empty.style.display = 'block';
    return;
  }
  empty.style.display = 'none';

  tbody.innerHTML = state.streams.map(s => `
    <tr>
      <td class="mono">${esc(s.stream_id)}</td>
      <td>${esc(s.name)}</td>
      <td class="url-cell mono" title="${esc(s.rtsp_url)}">${esc(s.rtsp_url || '—')}</td>
      <td><span class="dot ${s.alive ? 'online' : 'offline'}" title="${s.alive ? 'Online' : 'Offline'}"></span></td>
      <td>${(s.fps || 0).toFixed(1)}</td>
      <td>${(s.counting_zones || []).length}</td>
      <td class="actions-cell">
        <button class="btn btn-xs btn-secondary" onclick="openEdit(${esc(JSON.stringify(s.stream_id))})">Editar</button>
        <button class="btn btn-xs btn-danger"    onclick="confirmDel(${esc(JSON.stringify(s.stream_id))},${esc(JSON.stringify(s.name))})">Excluir</button>
      </td>
    </tr>`).join('');
}

function esc(s) {
  return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ── Delete flow ───────────────────────────────────────────────────────────────
window.confirmDel = function(sid, name) {
  document.getElementById('confirm-msg').textContent =
    `Excluir "${name}" (${sid})? Esta ação não pode ser desfeita.`;
  document.getElementById('confirm-ok').onclick = async () => {
    confirmModal.classList.add('hidden');
    try {
      await api('DELETE', `/api/streams/${encodeURIComponent(sid)}`);
      await loadStreams();
    } catch (e) { alert('Erro ao excluir: ' + e.message); }
  };
  confirmModal.classList.remove('hidden');
};

document.getElementById('confirm-cancel').onclick = () => confirmModal.classList.add('hidden');

// ── Open / close modal ────────────────────────────────────────────────────────
function openModal() {
  formError.textContent = '';
  streamModal.classList.remove('hidden');
  document.body.style.overflow = 'hidden';
}

function closeModal() {
  streamModal.classList.add('hidden');
  document.body.style.overflow = '';
  resetZoneDraw();
  state.editId = null;
  state.zones  = [];
  state.imgEl  = null;
  state.canvasReady = false;
  clearCanvas();
  canvasHint.classList.remove('hidden');
  canvasHint.textContent = 'Informe a URL RTSP e clique "Carregar Preview"';
}

function clearCanvas() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = '#060b14';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
}

document.getElementById('btn-new').onclick = () => {
  state.editId = null;
  state.zones  = [];
  document.getElementById('modal-title').textContent = 'Novo Stream';
  document.getElementById('f-id').value      = '';
  document.getElementById('f-id').disabled   = false;
  document.getElementById('f-name').value    = '';
  document.getElementById('f-url').value     = '';
  document.getElementById('f-enabled').checked = true;
  document.getElementById('f-cores').value   = '';
  renderZoneList();
  openModal();
  clearCanvas();
};

document.getElementById('modal-close').onclick      = closeModal;
document.getElementById('btn-modal-cancel').onclick = closeModal;
streamModal.addEventListener('click', e => { if (e.target === streamModal) closeModal(); });

// ── Edit mode ─────────────────────────────────────────────────────────────────
window.openEdit = async function(sid) {
  try {
    const cfg = await api('GET', `/api/streams/${encodeURIComponent(sid)}`);
    state.editId = sid;
    state.zones  = (cfg.counting_zones || []).map(z => ({ ...z, points: z.points.map(p => [...p]) }));

    document.getElementById('modal-title').textContent = 'Editar Stream';
    document.getElementById('f-id').value      = cfg.stream_id;
    document.getElementById('f-id').disabled   = true;
    document.getElementById('f-name').value    = cfg.name || '';
    document.getElementById('f-url').value     = cfg.rtsp_url || '';
    document.getElementById('f-enabled').checked = cfg.enabled !== false;
    document.getElementById('f-cores').value   = (cfg.cpu_cores || []).join(',');

    renderZoneList();
    openModal();
    clearCanvas();
    renderCanvas();
  } catch (e) {
    alert('Erro ao carregar stream: ' + e.message);
  }
};

// ── Save ──────────────────────────────────────────────────────────────────────
document.getElementById('btn-save').onclick = async () => {
  formError.textContent = '';

  const sid   = document.getElementById('f-id').value.trim();
  const name  = document.getElementById('f-name').value.trim();
  const url   = document.getElementById('f-url').value.trim();
  const enabled = document.getElementById('f-enabled').checked;
  const coresRaw = document.getElementById('f-cores').value.trim();
  const cpu_cores = coresRaw
    ? coresRaw.split(',').map(s => parseInt(s.trim(), 10)).filter(n => !isNaN(n))
    : [];

  if (!sid)  { formError.textContent = 'ID é obrigatório.'; return; }
  if (!name) { formError.textContent = 'Nome é obrigatório.'; return; }
  if (!url)  { formError.textContent = 'URL RTSP é obrigatória.'; return; }

  const body = {
    stream_id: sid,
    name,
    rtsp_url: url,
    enabled,
    cpu_cores,
    counting_zones: state.zones.map(z => ({
      type: z.type,
      name: z.name,
      points: z.points,
      direction: z.direction || 'both',
      track_classes: z.track_classes || ALL_CLASSES.slice(),
    })),
  };

  const btn = document.getElementById('btn-save');
  btn.disabled = true;
  btn.textContent = 'Salvando...';

  try {
    if (state.editId) {
      await api('PUT', `/api/streams/${encodeURIComponent(state.editId)}`, body);
    } else {
      await api('POST', '/api/streams', body);
    }
    closeModal();
    await loadStreams();
  } catch (e) {
    formError.textContent = e.message;
  } finally {
    btn.disabled = false;
    btn.textContent = 'Salvar Stream';
  }
};

// ── Snapshot loader ───────────────────────────────────────────────────────────
document.getElementById('btn-snapshot').onclick = loadSnapshot;

async function loadSnapshot() {
  const url = document.getElementById('f-url').value.trim();
  const sid = state.editId;

  if (!url) { formError.textContent = 'Informe a URL RTSP antes de carregar o preview.'; return; }
  formError.textContent = '';

  canvasHint.textContent = 'Conectando ao stream...';
  canvasHint.classList.remove('hidden');

  const endpoint = sid
    ? `/api/streams/${encodeURIComponent(sid)}/snapshot`
    : `/api/streams/snapshot/preview?rtsp_url=${encodeURIComponent(url)}`;

  try {
    const resp = await fetch(endpoint);
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: resp.statusText }));
      throw new Error(err.detail || resp.statusText);
    }
    const blob = await resp.blob();
    const objUrl = URL.createObjectURL(blob);
    const img = new Image();
    img.onload = () => {
      fitCanvas(img);
      canvasHint.classList.add('hidden');
      state.canvasReady = true;
      renderCanvas();
    };
    img.onerror = () => { canvasHint.textContent = 'Falha ao exibir imagem.'; };
    img.src = objUrl;
  } catch (e) {
    canvasHint.textContent = 'Erro: ' + e.message;
  }
}

function fitCanvas(img) {
  const scale = CANVAS_MAX_W / img.naturalWidth;
  canvas.width  = CANVAS_MAX_W;
  canvas.height = Math.round(img.naturalHeight * scale);
  state.imgEl = img;
  state.imgW  = img.naturalWidth;
  state.imgH  = img.naturalHeight;
}

// ── Coordinate conversion ─────────────────────────────────────────────────────
function canvasToImg(cx, cy) {
  return [
    Math.round(cx * state.imgW / canvas.width),
    Math.round(cy * state.imgH / canvas.height),
  ];
}
function imgToCanvas(ix, iy) {
  return [ix * canvas.width / state.imgW, iy * canvas.height / state.imgH];
}
function eventToCanvas(e) {
  const r = canvas.getBoundingClientRect();
  return [e.clientX - r.left, e.clientY - r.top];
}

// ── Tool selector ─────────────────────────────────────────────────────────────
document.querySelectorAll('.btn-tool').forEach(btn => {
  btn.onclick = () => {
    document.querySelectorAll('.btn-tool').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    state.tool = btn.dataset.tool;
    resetZoneDraw();
  };
});

btnCancelZone.onclick = resetZoneDraw;

// ── Canvas event listeners ────────────────────────────────────────────────────
canvas.addEventListener('contextmenu', e => { e.preventDefault(); resetZoneDraw(); });
canvas.addEventListener('mousemove', e => {
  if (!state.drawing) return;
  const [cx, cy] = eventToCanvas(e);
  state.mouseImgPt = canvasToImg(cx, cy);
  renderCanvas();
});
canvas.addEventListener('mouseleave', () => { state.mouseImgPt = null; renderCanvas(); });

canvas.addEventListener('click', e => {
  if (!state.canvasReady) return;
  if (state.dblclickFired) { state.dblclickFired = false; return; } // skip extra click from dblclick

  const [cx, cy] = eventToCanvas(e);
  const pt = canvasToImg(cx, cy);

  if (!state.drawing) {
    state.drawing = true;
    state.pendingPts = [pt];
    btnCancelZone.classList.remove('hidden');
  } else {
    state.pendingPts.push(pt);
    if (state.tool === 'line' && state.pendingPts.length === 2) {
      commitZone();
      return;
    }
  }
  renderCanvas();
});

canvas.addEventListener('dblclick', e => {
  if (!state.drawing || state.tool !== 'polygon') return;
  state.dblclickFired = true;
  // Remove the spurious point added by the second click of this dblclick
  if (state.pendingPts.length > 0) state.pendingPts.pop();
  if (state.pendingPts.length >= 3) {
    commitZone();
  } else {
    showMsg('Um polígono precisa de pelo menos 3 pontos.');
    resetZoneDraw();
  }
});

// ── Zone state machine ────────────────────────────────────────────────────────
function commitZone() {
  const idx = state.zones.length;
  state.zones.push({
    type: state.tool === 'line' ? 'line' : 'polygon',
    name: `zona_${idx + 1}`,
    points: state.pendingPts.map(p => [...p]),
    direction: 'both',
    track_classes: ALL_CLASSES.slice(),
  });
  renderZoneList();
  resetZoneDraw();
  renderCanvas();
}

function resetZoneDraw() {
  state.drawing    = false;
  state.pendingPts = [];
  state.mouseImgPt = null;
  btnCancelZone.classList.add('hidden');
  renderCanvas();
}

// ── Canvas rendering ──────────────────────────────────────────────────────────
function renderCanvas() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  if (state.imgEl) {
    ctx.drawImage(state.imgEl, 0, 0, canvas.width, canvas.height);
  } else {
    ctx.fillStyle = '#060b14';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
  }

  // Draw committed zones
  state.zones.forEach((z, i) => drawZone(z, ZONE_COLORS[i % ZONE_COLORS.length]));

  // Draw in-progress zone
  if (state.drawing && state.pendingPts.length > 0) {
    ctx.save();
    ctx.strokeStyle = '#fff';
    ctx.lineWidth = 2;
    ctx.setLineDash([5, 4]);
    ctx.beginPath();
    const [sx, sy] = imgToCanvas(...state.pendingPts[0]);
    ctx.moveTo(sx, sy);
    for (let i = 1; i < state.pendingPts.length; i++) {
      ctx.lineTo(...imgToCanvas(...state.pendingPts[i]));
    }
    if (state.mouseImgPt) ctx.lineTo(...imgToCanvas(...state.mouseImgPt));
    ctx.stroke();
    ctx.setLineDash([]);

    // Dots on placed points
    ctx.fillStyle = '#fff';
    state.pendingPts.forEach(p => {
      ctx.beginPath();
      ctx.arc(...imgToCanvas(...p), 5, 0, Math.PI * 2);
      ctx.fill();
    });
    ctx.restore();
  }
}

function drawZone(zone, color) {
  if (!zone.points || zone.points.length < 2) return;
  const pts = zone.points.map(p => imgToCanvas(...p));

  ctx.save();
  ctx.strokeStyle = color;
  ctx.lineWidth = 2.5;
  ctx.beginPath();
  ctx.moveTo(...pts[0]);
  pts.slice(1).forEach(p => ctx.lineTo(...p));
  if (zone.type === 'polygon') ctx.closePath();
  ctx.stroke();

  if (zone.type === 'polygon') {
    ctx.fillStyle = color + '30';
    ctx.fill();
  }

  // Direction arrow on lines
  if (zone.type === 'line' && zone.direction !== 'both') {
    drawArrow(ctx, pts[0], pts[pts.length - 1], color, zone.direction === 'in');
  }

  // Label
  ctx.fillStyle = color;
  ctx.font = 'bold 13px system-ui, sans-serif';
  ctx.shadowColor = '#000';
  ctx.shadowBlur = 4;
  ctx.fillText(zone.name, pts[0][0] + 5, pts[0][1] - 6);
  ctx.shadowBlur = 0;
  ctx.restore();
}

function drawArrow(ctx, from, to, color, forward) {
  const dx = to[0] - from[0], dy = to[1] - from[1];
  const len = Math.sqrt(dx * dx + dy * dy);
  if (len === 0) return;
  const mx = (from[0] + to[0]) / 2, my = (from[1] + to[1]) / 2;
  const ux = dx / len, uy = dy / len;
  const sign = forward ? 1 : -1;
  const size = 10;
  ctx.save();
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.moveTo(mx + sign * ux * size, my + sign * uy * size);
  ctx.lineTo(mx - sign * ux * size + uy * size * .5, my - sign * uy * size - ux * size * .5);
  ctx.lineTo(mx - sign * ux * size - uy * size * .5, my - sign * uy * size + ux * size * .5);
  ctx.closePath();
  ctx.fill();
  ctx.restore();
}

// ── Zone list rendering ───────────────────────────────────────────────────────
function renderZoneList() {
  if (!state.zones.length) {
    zonesList.innerHTML = '<span class="no-zones-hint">Desenhe linhas ou polígonos no canvas ao lado →</span>';
    return;
  }

  zonesList.innerHTML = state.zones.map((z, i) => `
    <div class="zone-row" data-idx="${i}">
      <div class="zone-row-header">
        <span class="zone-color-dot" style="background:${ZONE_COLORS[i % ZONE_COLORS.length]}"></span>
        <input class="zone-name-input" type="text" value="${esc(z.name)}"
               data-idx="${i}" data-field="name" />
        <select class="zone-dir-select" data-idx="${i}" data-field="direction">
          <option value="both" ${z.direction === 'both' ? 'selected' : ''}>↔ Ambos</option>
          <option value="in"   ${z.direction === 'in'   ? 'selected' : ''}>→ Entrada</option>
          <option value="out"  ${z.direction === 'out'  ? 'selected' : ''}>← Saída</option>
        </select>
        <button type="button" class="btn btn-xs btn-danger" data-del="${i}">✕</button>
      </div>
      <div class="zone-classes">
        ${ALL_CLASSES.map(cls => `
          <label class="cls-label">
            <input type="checkbox" data-idx="${i}" data-cls="${cls}"
                   ${(z.track_classes || []).includes(cls) ? 'checked' : ''} />
            ${cls}
          </label>`).join('')}
      </div>
    </div>`).join('');
}

// Event delegation on zones list
zonesList.addEventListener('input', e => {
  const idx = e.target.dataset.idx;
  if (idx === undefined) return;
  const i = parseInt(idx, 10);
  if (e.target.dataset.field === 'name') {
    state.zones[i].name = e.target.value;
    renderCanvas();
  }
});
zonesList.addEventListener('change', e => {
  const idx = e.target.dataset.idx;
  if (idx === undefined) return;
  const i = parseInt(idx, 10);
  if (e.target.dataset.field === 'direction') {
    state.zones[i].direction = e.target.value;
    renderCanvas();
  }
  if (e.target.dataset.cls) {
    const cls = e.target.dataset.cls;
    const arr = state.zones[i].track_classes || [];
    if (e.target.checked) {
      if (!arr.includes(cls)) arr.push(cls);
    } else {
      state.zones[i].track_classes = arr.filter(c => c !== cls);
    }
  }
});
zonesList.addEventListener('click', e => {
  const del = e.target.dataset.del;
  if (del !== undefined) {
    state.zones.splice(parseInt(del, 10), 1);
    renderZoneList();
    renderCanvas();
  }
});

// ── Small helpers ─────────────────────────────────────────────────────────────
function showMsg(msg) {
  formError.textContent = msg;
  setTimeout(() => { if (formError.textContent === msg) formError.textContent = ''; }, 3000);
}

// ── Bootstrap ─────────────────────────────────────────────────────────────────
clearCanvas();
loadStreams();

})();
