// Main app: auth, routing, view rendering.
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

function fmtMoney(n) {
  if (n == null || isNaN(n)) return '—';
  return '$' + Number(n).toLocaleString(undefined, { maximumFractionDigits: 0 });
}
function fmtNum(n, d = 0) { return n == null || isNaN(n) ? '—' : Number(n).toLocaleString(undefined, { maximumFractionDigits: d }); }
function fmtDate(s) { if (!s) return '—'; const d = new Date(s); return isNaN(d) ? s : d.toLocaleDateString(); }
function fmtDateTime(s) { if (!s) return '—'; const d = new Date(s); return isNaN(d) ? s : d.toLocaleString(); }
function pct(n) { return n == null || isNaN(n) ? '—' : (n * 100).toFixed(1) + '%'; }

function toast(msg, type = 'info') {
  const t = document.createElement('div');
  t.className = 'toast ' + type;
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 3800);
}

function badgeFor(status) {
  const s = String(status || '').toLowerCase();
  let cls = 'badge-gray';
  if (['delivered', 'fulfilled', 'approved', 'resolved', 'completed', 'auto_approved', 'on_time'].includes(s)) cls = 'badge-green';
  else if (['delayed', 'pending', 'pending_approval', 'backordered', 'in_progress', 'recovering', 'planned', 'analyzing', 'medium'].includes(s)) cls = 'badge-amber';
  else if (['failed', 'cancelled', 'rejected', 'critical', 'expired', 'high', 'error'].includes(s)) cls = 'badge-red';
  else if (['open', 'in_transit', 'detected', 'requested', 'draft'].includes(s)) cls = 'badge-blue';
  return `<span class="badge ${cls}">${status || '—'}</span>`;
}

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

// ---------- Routing ----------
const ROUTES = [
  { id: 'dashboard', label: 'Dashboard', icon: '📊', group: 'Overview' },
  { id: 'suppliers', label: 'Suppliers', icon: '🏭', group: 'Master Data' },
  { id: 'inventory', label: 'Inventory', icon: '📦', group: 'Master Data' },
  { id: 'orders', label: 'Purchase Orders', icon: '🧾', group: 'Master Data' },
  { id: 'forecasting', label: 'Demand Forecasting', icon: '📈', group: 'Intelligence' },
  { id: 'simulation', label: 'Disruption Simulation', icon: '🧪', group: 'Intelligence' },
  { id: 'alternatives', label: 'Supplier Comparison', icon: '⚖️', group: 'Intelligence' },
  { id: 'recovery', label: 'Recovery Plans', icon: '🛠️', group: 'Recovery' },
  { id: 'approvals', label: 'Human Approval', icon: '✅', group: 'Recovery' },
  { id: 'tracking', label: 'Decision Tracking', icon: '📜', group: 'Recovery' },
];

function buildNav() {
  const nav = $('#nav');
  nav.innerHTML = '';
  let lastGroup = '';
  ROUTES.forEach(r => {
    if (r.group !== lastGroup) {
      const sec = document.createElement('div');
      sec.className = 'nav-section';
      sec.textContent = r.group;
      nav.appendChild(sec);
      lastGroup = r.group;
    }
    const item = document.createElement('div');
    item.className = 'nav-item' + (r.id === currentRoute ? ' active' : '');
    item.dataset.route = r.id;
    item.innerHTML = `<span class="ico">${r.icon}</span><span>${r.label}</span>`;
    item.onclick = () => navigate(r.id);
    nav.appendChild(item);
  });
}

let currentRoute = 'dashboard';
function navigate(route) {
  currentRoute = route;
  $$('.view').forEach(v => v.classList.toggle('active', v.id === 'view-' + route));
  $$('.nav-item').forEach(n => n.classList.toggle('active', n.dataset.route === route));
  const meta = ROUTES.find(r => r.id === route);
  $('#page-title').textContent = meta ? meta.label : route;
  $('#view-' + route).querySelector('.content-area')?.scrollTo?.(0, 0);
  loadView(route);
}

async function loadView(route) {
  try {
    switch (route) {
      case 'dashboard': return loadDashboard();
      case 'suppliers': return loadSuppliers();
      case 'inventory': return loadInventory();
      case 'orders': return loadOrders();
      case 'forecasting': return loadForecasting();
      case 'simulation': return loadSimulation();
      case 'alternatives': return loadAlternatives();
      case 'recovery': return loadRecovery();
      case 'approvals': return loadApprovals();
      case 'tracking': return loadTracking();
    }
  } catch (e) {
    toast('Error: ' + e.message, 'error');
  }
}

// ---------- Auth ----------
function showLogin() {
  $('#app-shell').classList.add('hidden');
  $('#login-view').classList.remove('hidden');
}
function showApp() {
  $('#login-view').classList.add('hidden');
  $('#app-shell').classList.remove('hidden');
  buildNav();
  navigate('dashboard');
  const u = getUser();
  if (u) { $('#user-name').textContent = u.username; $('#user-role').textContent = u.role; $('#avatar').textContent = (u.username[0] || 'U').toUpperCase(); }
}

async function doLogin(e) {
  e.preventDefault();
  const u = $('#login-user').value.trim();
  const p = $('#login-pass').value;
  try {
    const t = await API.login(u, p);
    setToken(t.access_token);
    setUser({ username: t.username, role: t.role, full_name: t.full_name });
    showApp();
  } catch (err) { toast(err.message, 'error'); }
}

function doLogout() { clearToken(); showLogin(); }

// ---------- Dashboard ----------
async function loadDashboard() {
  $('#dash-status').textContent = 'Loading…';
  try {
    const [summary, alerts, perf, forecast] = await Promise.all([
      API.summary(), API.riskAlerts(), API.supplierPerformance(), API.demandForecast(),
    ]);
    const kpis = [
      { label: 'Total Suppliers', value: fmtNum(summary.total_suppliers), icon: '🏭', cls: 't-blue' },
      { label: 'Total Products', value: fmtNum(summary.total_products), icon: '📦', cls: 't-purple' },
      { label: 'Active POs', value: fmtNum(summary.active_purchase_orders), icon: '🧾', cls: 't-teal' },
      { label: 'Delayed Shipments', value: fmtNum(summary.delayed_shipments), icon: '⚠️', cls: 't-red' },
      { label: 'Low Inventory', value: fmtNum(summary.low_inventory_count), icon: '📉', cls: 't-amber' },
      { label: 'Open Disruptions', value: fmtNum(summary.open_disruptions), icon: '🚨', cls: 't-red' },
      { label: 'Pending Approvals', value: fmtNum(summary.pending_approvals), icon: '✅', cls: 't-amber' },
      { label: 'Inventory Value', value: fmtMoney(summary.total_inventory_value), icon: '💰', cls: 't-green' },
      { label: 'On-Time Rate', value: pct(summary.on_time_delivery_rate), icon: '🎯', cls: 't-green' },
    ];
    $('#kpi-grid').innerHTML = kpis.map(k => `
      <div class="card kpi"><div class="icon ${k.cls}">${k.icon}</div>
      <div class="label">${k.label}</div><div class="value">${k.value}</div></div>`).join('');

    // risk alerts
    if (!alerts.length) { $('#risk-list').innerHTML = '<div class="empty">No active risk alerts 🎉</div>'; }
    else {
      $('#risk-list').innerHTML = alerts.map(a => `
        <div class="alert ${a.level}">
          <div class="ai">${a.level === 'high' ? '🔥' : a.level === 'medium' ? '⚠️' : '✓'}</div>
          <div><div class="at-title">${esc(a.title)}</div>
          <div class="at">${esc(a.category)} · ${esc(a.description)}</div></div>
        </div>`).join('');
    }

    // supplier performance chart (avg on-time rate by period, top suppliers)
    const bySup = {};
    perf.forEach(p => { (bySup[p.supplier_name] = bySup[p.supplier_name] || []).push(p); });
    const periods = [...new Set(perf.map(p => p.period))].sort();
    const topSuppliers = Object.entries(bySup).sort((a, b) => b[1].length - a[1].length).slice(0, 5).map(x => x[0]);
    const datasets = topSuppliers.map((name, i) => ({
      label: name,
      data: periods.map(per => {
        const rec = bySup[name].find(r => r.period === per);
        return rec ? +(rec.on_time_rate * 100).toFixed(1) : null;
      }),
      color: CHART.palette[i % CHART.palette.length],
    }));
    CHART.line('chart-supplier-perf', periods, datasets);

    // demand forecast chart (total predicted demand by period)
    const fcByPeriod = {};
    forecast.forEach(f => { fcByPeriod[f.period] = (fcByPeriod[f.period] || 0) + f.predicted_demand; });
    const fPeriods = Object.keys(fcByPeriod).sort();
    CHART.bar('chart-demand', fPeriods, [
      { label: 'Predicted Demand (units)', data: fPeriods.map(p => +fcByPeriod[p].toFixed(0)), color: '#8b5cf6' },
    ]);

    $('#dash-status').textContent = '';
  } catch (e) { $('#dash-status').textContent = 'Error: ' + e.message; toast(e.message, 'error'); }
}

// ---------- Suppliers ----------
async function loadSuppliers(search = '') {
  let q = '?limit=200';
  if (search) q += '&search=' + encodeURIComponent(search);
  const rows = await API.suppliers(q);
  $('#suppliers-table tbody').innerHTML = rows.map(s => `
    <tr><td>${s.code}</td><td>${esc(s.name)}</td><td>${esc(s.country)}</td>
    <td>${esc(s.region)}</td><td>${s.rating.toFixed(1)}★</td>
    <td>${pct(s.on_time_rate)}</td><td>${fmtNum(s.avg_lead_time_days, 0)}d</td>
    <td>${s.active ? badgeFor('active') : badgeFor('inactive')}</td></tr>`).join('') ||
    '<tr><td colspan="8" class="empty">No suppliers</td></tr>';
  $('#suppliers-count').textContent = `${rows.length} suppliers`;
}

// ---------- Inventory ----------
async function loadInventory() {
  const [inv, low] = await Promise.all([API.inventory('?limit=300'), API.lowInventory()]);
  $('#inv-table tbody').innerHTML = inv.slice(0, 60).map(i => {
    const avail = Math.max(0, i.on_hand - i.reserved);
    const low = avail < i.reorder_point;
    return `<tr><td>${i.product_id}</td><td>${esc(i.warehouse)}</td>
      <td>${fmtNum(i.on_hand, 0)}</td><td>${fmtNum(i.safety_stock, 0)}</td>
      <td>${fmtNum(i.reorder_point, 0)}</td><td>${low ? badgeFor('low') : badgeFor('ok')}</td></tr>`;
  }).join('') || '<tr><td colspan="6" class="empty">No inventory</td></tr>';
  $('#inv-count').textContent = `${inv.length} records · ${low.length} low`;
}

// ---------- Orders ----------
async function loadOrders(status = '') {
  let q = '?limit=100';
  if (status) q += '&status=' + status;
  const pos = await API.purchaseOrders(q);
  $('#orders-table tbody').innerHTML = pos.map(p => `
    <tr><td>${p.po_number}</td><td>${p.supplier_id}</td><td>${badgeFor(p.status)}</td>
    <td>${fmtDate(p.order_date)}</td><td>${fmtDate(p.expected_delivery)}</td>
    <td>${fmtDate(p.actual_delivery)}</td><td>${fmtMoney(p.total_cost)}</td>
    <td>${fmtMoney(p.transport_cost)}</td><td>${p.items.length}</td></tr>`).join('') ||
    '<tr><td colspan="9" class="empty">No purchase orders</td></tr>';
  $('#orders-count').textContent = `${pos.length} orders`;
}

// ---------- Forecasting ----------
async function loadForecasting() {
  const [forecast, shortages] = await Promise.all([API.demandForecasting(3), API.shortages(3)]);
  // group by product for a few top products
  const byProd = {};
  forecast.forEach(f => { (byProd[f.product_id] = byProd[f.product_id] || { name: f.product_name, pts: [] }).pts.push(f); });
  const topProducts = Object.entries(byProd).slice(0, 6);
  const periods = [...new Set(forecast.map(f => f.period))].sort();
  const datasets = topProducts.map(([pid, obj], i) => ({
    label: obj.name || ('P' + pid), data: periods.map(per => {
      const rec = obj.pts.find(p => p.period === per); return rec ? rec.predicted_demand : null;
    }), color: CHART.palette[i % CHART.palette.length],
  }));
  CHART.bar('chart-forecast', periods, datasets);
  $('#shortage-list').innerHTML = shortages.length ? shortages.slice(0, 12).map(s => `
    <div class="alert high"><div class="ai">⚠️</div>
    <div><div class="at-title">${esc(s.product_name)}</div>
    <div class="at">Period ${s.period}: demand ${fmtNum(s.predicted_demand, 0)} vs on-hand ${fmtNum(s.on_hand, 0)}</div></div></div>`).join('')
    : '<div class="empty">No shortage risks predicted</div>';
  $('#forecast-count').textContent = `${forecast.length} forecast points · ${shortages.length} at risk`;
}

// ---------- Simulation ----------
let simResult = null;
async function loadSimulation() {
  if (!$('#sim-type option').length) {
    const types = ['supplier_delay', 'supplier_unavailable', 'demand_spike', 'inventory_shortage', 'transport_disruption'];
    $('#sim-type').innerHTML = types.map(t => `<option value="${t}">${t.replace(/_/g, ' ')}</option>`).join('');
    const severities = ['low', 'medium', 'high', 'critical'];
    $('#sim-severity').innerHTML = severities.map(s => `<option value="${s}">${s}</option>`).join('');
  }
}

async function runSimulation() {
  const btn = $('#sim-run'); btn.disabled = true; btn.textContent = 'Simulating…';
  try {
    const payload = {
      type: $('#sim-type').value,
      severity: $('#sim-severity').value,
      supplier_id: +$('#sim-supplier').value || null,
      product_id: +$('#sim-product').value || null,
      estimated_delay_days: +$('#sim-delay').value || 0,
      description: $('#sim-desc').value,
    };
    simResult = await API.whatIf(payload);
    renderSimulationResult(simResult);
  } catch (e) { toast(e.message, 'error'); }
  finally { btn.disabled = false; btn.textContent = 'Run Simulation'; }
}

function renderSimulationResult(r) {
  $('#sim-output').classList.remove('hidden');
  $('#sim-summary').innerHTML = `
    <div class="kpi-grid">
      <div class="card kpi"><div class="label">Affected Orders</div><div class="value">${fmtNum(r.affected_orders)}</div></div>
      <div class="card kpi"><div class="label">Affected Products</div><div class="value">${fmtNum(r.affected_products)}</div></div>
      <div class="card kpi"><div class="label">Inventory Gap</div><div class="value">${fmtNum(r.inventory_gap, 0)}</div></div>
      <div class="card kpi"><div class="label">Original Cost</div><div class="value">${fmtMoney(r.original_plan_cost)}</div></div>
      <div class="card kpi"><div class="label">Optimized Cost</div><div class="value">${fmtMoney(r.optimized_plan_cost)}</div></div>
      <div class="card kpi"><div class="label">Cost Savings</div><div class="value">${fmtMoney(r.original_plan_cost - r.optimized_plan_cost)}</div></div>
    </div>`;
  $('#sim-compare').innerHTML = `
    <div class="compare-grid">
      <div class="card"><div class="card-head"><h3>Original Plan</h3></div>
        <div class="stat-line">Total cost: <b>${fmtMoney(r.original_plan_cost)}</b></div>
        <div class="stat-line">Delay: <b>${fmtNum(r.original_plan_delay_days, 1)} days</b></div></div>
      <div class="card"><div class="card-head"><h3>Optimized Plan</h3></div>
        <div class="stat-line">Total cost: <b>${fmtMoney(r.optimized_plan_cost)}</b></div>
        <div class="stat-line">Delay: <b>${fmtNum(r.optimized_plan_delay_days, 1)} days</b></div></div>
    </div>`;
  // alternatives table
  $('#sim-alts').innerHTML = `<table><thead><tr><th>Supplier</th><th>Country</th><th>Rating</th><th>On-time</th>
    <th>Lead</th><th>Unit Cost</th><th>Transport</th><th>Total</th><th>Delivery</th><th>Score</th></tr></thead>
    <tbody>${r.alternatives.map(a => `<tr><td>${esc(a.supplier_name)}</td><td>${esc(a.country)}</td>
    <td>${a.rating.toFixed(1)}★</td><td>${pct(a.on_time_rate)}</td><td>${fmtNum(a.lead_time_days, 0)}d</td>
    <td>${fmtMoney(a.unit_cost)}</td><td>${fmtMoney(a.transport_cost)}</td><td>${fmtMoney(a.total_cost)}</td>
    <td>${fmtNum(a.delivery_days, 0)}d</td><td>${a.score.toFixed(3)}</td></tr>`).join('') || '<tr><td colspan="10" class="empty">No alternatives</td></tr>'}</tbody></table>`;
  // plan items
  if (r.recovery_plan && r.recovery_plan.items) {
    $('#sim-plan-items').innerHTML = `<table><thead><tr><th>Product</th><th>Supplier</th><th>Qty</th>
      <th>Unit Cost</th><th>Transport</th><th>Delay</th><th>Line Total</th></tr></thead><tbody>
      ${r.recovery_plan.items.map(it => `<tr><td>${it.product_id}</td><td>${it.supplier_id}</td>
      <td>${fmtNum(it.quantity, 0)}</td><td>${fmtMoney(it.unit_cost)}</td><td>${fmtMoney(it.transport_cost)}</td>
      <td>${fmtNum(it.delay_days, 1)}d</td><td>${fmtMoney(it.line_total)}</td></tr>`).join('')}</tbody></table>`;
  }
}

// ---------- Alternatives comparison ----------
async function loadAlternatives() {
  // populate product selector with first batch
  if (!$('#alt-product option').length) {
    const products = await API.products('?limit=200');
    $('#alt-product').innerHTML = products.map(p => `<option value="${p.id}">${esc(p.sku)} — ${esc(p.name)}</option>`).join('');
  }
}
async function compareSuppliers() {
  const pid = +$('#alt-product').value;
  const qty = +$('#alt-qty').value || 200;
  const exclude = +$('#alt-exclude').value || null;
  if (!pid) return toast('Select a product', 'error');
  try {
    const alts = await API.alternatives(pid, qty, exclude);
    $('#alt-table tbody').innerHTML = alts.map(a => `<tr>
      <td>${esc(a.supplier_name)}</td><td>${esc(a.country)}</td><td>${a.rating.toFixed(1)}★</td>
      <td>${pct(a.on_time_rate)}</td><td>${fmtNum(a.lead_time_days, 0)}d</td>
      <td>${fmtMoney(a.unit_cost)}</td><td>${fmtMoney(a.transport_cost)}</td>
      <td>${fmtMoney(a.total_cost)}</td><td>${fmtNum(a.delivery_days, 0)}d</td>
      <td>${fmtNum(a.delay_vs_original, 1)}d</td><td>${a.score.toFixed(3)}</td></tr>`).join('') ||
      '<tr><td colspan="11" class="empty">No alternatives</td></tr>';
    // bar chart of total cost
    CHART.bar('alt-chart', alts.map(a => a.supplier_name), [
      { label: 'Total Cost', data: alts.map(a => a.total_cost), color: '#3b82f6' },
    ], { horizontal: true });
  } catch (e) { toast(e.message, 'error'); }
}

// ---------- Recovery ----------
async function loadRecovery() {
  const [plans, decisions] = await Promise.all([API.listPlans('?limit=100'), API.decisions('?limit=20')]);
  $('#plan-table tbody').innerHTML = plans.map(p => `
    <tr><td>${p.id}</td><td>${p.disruption_id}</td><td>${badgeFor(p.plan_type)}</td>
    <td>${fmtMoney(p.total_cost)}</td><td>${fmtMoney(p.total_transport_cost)}</td>
    <td>${fmtNum(p.total_delay_days, 1)}d</td><td>${p.supplier_count}</td>
    <td>${badgeFor(p.status)}</td><td>${fmtDate(p.created_at)}</td>
    <td><button class="btn btn-ghost btn-sm" onclick="viewPlan(${p.id})">View</button>
    <button class="btn btn-sm" onclick="completePlan(${p.id})">Complete</button></td></tr>`).join('') ||
    '<tr><td colspan="10" class="empty">No recovery plans yet. Run a disruption workflow.</td></tr>';
}
async function viewPlan(id) {
  try {
    const [plan, cmp] = await Promise.all([API.getPlan(id), API.comparePlan(id)]);
    let html = `<h3>Recovery Plan #${plan.id}</h3><p class="muted">${esc(plan.summary)}</p>`;
    if (cmp.original) {
      html += `<div class="compare-grid mt">
        <div class="card"><div class="card-head"><h3>Original Plan</h3></div>
          <div class="stat-line">Cost: <b>${fmtMoney(cmp.original.total_cost)}</b></div>
          <div class="stat-line">Delay: <b>${fmtNum(cmp.original.delay_days,1)}d</b></div>
          <div class="stat-line">Suppliers: <b>${cmp.original.suppliers}</b></div></div>
        <div class="card"><div class="card-head"><h3>Optimized Plan</h3></div>
          <div class="stat-line">Cost: <b>${fmtMoney(cmp.optimized.total_cost)}</b></div>
          <div class="stat-line">Delay: <b>${fmtNum(cmp.optimized.delay_days,1)}d</b></div>
          <div class="stat-line">Suppliers: <b>${cmp.optimized.suppliers}</b></div></div></div>`;
      html += `<div class="card mt"><div class="card-head"><h3>Comparison</h3></div>
        <div class="stat-line">Cost savings: <b>${fmtMoney(cmp.cost_savings)}</b></div>
        <div class="stat-line">Delay savings: <b>${fmtNum(cmp.delay_savings_days,1)} days</b></div></div>`;
    }
    html += `<div class="card mt"><div class="card-head"><h3>Line Items (${plan.items.length})</h3></div>
      <div class="table-wrap"><table><thead><tr><th>Product</th><th>Supplier</th><th>Qty</th>
      <th>Unit Cost</th><th>Transport</th><th>Delivery</th><th>Delay</th><th>Line Total</th></tr></thead><tbody>
      ${plan.items.map(it => `<tr><td>${it.product_id}</td><td>${it.supplier_id}</td><td>${fmtNum(it.quantity,0)}</td>
      <td>${fmtMoney(it.unit_cost)}</td><td>${fmtMoney(it.transport_cost)}</td><td>${fmtDate(it.delivery_date)}</td>
      <td>${fmtNum(it.delay_days,1)}d</td><td>${fmtMoney(it.line_total)}</td></tr>`).join('')}</tbody></table></div></div>`;
    $('#plan-detail').innerHTML = html;
    $('#plan-detail').classList.remove('hidden');
  } catch (e) { toast(e.message, 'error'); }
}
async function completePlan(id) {
  if (!confirm('Mark recovery plan ' + id + ' as completed?')) return;
  try { await API.completePlan(id); toast('Recovery completed', 'success'); loadRecovery(); }
  catch (e) { toast(e.message, 'error'); }
}

// ---------- Approvals ----------
async function loadApprovals() {
  const pending = await API.pendingApprovals();
  $('#pending-table tbody').innerHTML = pending.map(a => `
    <tr><td>${a.id}</td><td>${a.recovery_plan_id}</td><td>${a.requester}</td>
    <td>${fmtMoney(a.total_cost)}</td><td>${fmtNum(a.total_delay_days,1)}d</td>
    <td>${fmtDateTime(a.requested_at)}</td><td>${badgeFor(a.status)}</td>
    <td><button class="btn btn-green btn-sm" onclick="decide(${a.id},'approved')">Approve</button>
    <button class="btn btn-red btn-sm" onclick="decide(${a.id},'rejected')">Reject</button></td></tr>`).join('') ||
    '<tr><td colspan="8" class="empty">No pending approvals 🎉</td></tr>';
  const all = await API.approvals('?limit=50');
  $('#approval-history tbody').innerHTML = all.map(a => `
    <tr><td>${a.id}</td><td>${a.recovery_plan_id}</td><td>${fmtMoney(a.total_cost)}</td>
    <td>${badgeFor(a.status)}</td><td>${esc(a.decided_by || '—')}</td>
    <td>${fmtDateTime(a.decided_at)}</td><td>${esc(a.decision_note || '—')}</td></tr>`).join('');
  $('#approval-count').textContent = `${pending.length} pending`;
}
async function decide(id, status) {
  const note = prompt(`Note for ${status} of approval #${id}:`, '') ?? '';
  try {
    const u = getUser();
    await API.decideApproval(id, { status, decided_by: u ? u.username : 'approver', decision_note: note });
    toast(`Approval ${id} ${status}`, 'success'); loadApprovals();
  } catch (e) { toast(e.message, 'error'); }
}

// ---------- Tracking ----------
async function loadTracking() {
  const decisions = await API.decisions('?limit=100');
  $('#track-table tbody').innerHTML = decisions.map(d => `
    <tr><td>${d.id}</td><td>${esc(d.entity_type)}</td><td>${d.entity_id}</td>
    <td>${badgeFor(d.action)}</td><td>${esc(d.actor)}</td>
    <td>${esc(d.details)}</td><td>${fmtDateTime(d.timestamp)}</td></tr>`).join('') ||
    '<tr><td colspan="7" class="empty">No decisions recorded yet</td></tr>';
  $('#track-count').textContent = `${decisions.length} records`;
}

// ---------- Init ----------
function init() {
  $('#login-form').addEventListener('submit', doLogin);
  $('#logout-btn').addEventListener('click', doLogout);
  $('#nav-toggle')?.addEventListener('click', () => $('#nav').classList.toggle('hidden'));
  // search + filters
  $('#sup-search')?.addEventListener('input', e => loadSuppliers(e.target.value));
  $('#order-status-filter')?.addEventListener('change', e => loadOrders(e.target.value));
  $('#sim-run')?.addEventListener('click', runSimulation);
  $('#alt-compare')?.addEventListener('click', compareSuppliers);

  if (getToken()) {
    API.me().then(() => showApp()).catch(() => { clearToken(); showLogin(); });
  } else {
    showLogin();
  }
}

document.addEventListener('DOMContentLoaded', init);
