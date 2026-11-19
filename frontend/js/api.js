// API client with JWT token handling. Base URL is the FastAPI origin.
const API_BASE = window.location.origin;
const API_V1 = '/api/v1';

function getToken() { return localStorage.getItem('sc_token'); }
function setToken(t) { localStorage.setItem('sc_token', t); }
function clearToken() { localStorage.removeItem('sc_token'); localStorage.removeItem('sc_user'); }
function getUser() { try { return JSON.parse(localStorage.getItem('sc_user') || 'null'); } catch { return null; } }
function setUser(u) { localStorage.setItem('sc_user', JSON.stringify(u)); }

async function api(path, { method = 'GET', body, isForm = false } = {}) {
  const headers = {};
  const token = getToken();
  if (token) headers['Authorization'] = 'Bearer ' + token;
  if (body && !isForm) headers['Content-Type'] = 'application/json';
  const opts = { method, headers };
  if (body !== undefined) opts.body = isForm ? body : JSON.stringify(body);
  const res = await fetch(API_BASE + API_V1 + path, opts);
  if (res.status === 204) return null;
  let data = null;
  const text = await res.text();
  if (text) { try { data = JSON.parse(text); } catch { data = text; } }
  if (!res.ok) {
    const msg = (data && data.detail) ? (typeof data.detail === 'object' ? JSON.stringify(data.detail) : data.detail) : res.statusText;
    throw new Error(msg);
  }
  return data;
}

const API = {
  login: async (username, password) => {
    const form = new URLSearchParams();
    form.append('username', username);
    form.append('password', password);
    const res = await fetch(API_BASE + API_V1 + '/auth/login', {
      method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body: form,
    });
    if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || 'Login failed'); }
    return res.json();
  },
  register: (payload) => api('/auth/register', { method: 'POST', body: payload }),
  me: () => api('/auth/me'),

  // dashboard
  summary: () => api('/dashboard/summary'),
  riskAlerts: () => api('/dashboard/risk-alerts'),
  supplierPerformance: () => api('/dashboard/supplier-performance'),
  demandForecast: () => api('/dashboard/demand-forecast'),
  lowInventory: () => api('/dashboard/low-inventory'),

  // master data
  suppliers: (q = '') => api('/master/suppliers' + q),
  products: (q = '') => api('/master/products' + q),
  inventory: (q = '') => api('/master/inventory' + q),
  customers: (q = '') => api('/master/customers' + q),
  purchaseOrders: (q = '') => api('/master/purchase-orders' + q),
  deliveries: (q = '') => api('/master/deliveries' + q),
  transportation: () => api('/master/transportation'),

  // disruptions + agents
  listDisruptions: (q = '') => api('/disruptions' + q),
  runWorkflow: (payload) => api('/disruptions/run', { method: 'POST', body: payload }),
  monitorDelays: () => api('/disruptions/delays/monitor'),

  // simulation
  whatIf: (payload) => api('/simulations/what-if', { method: 'POST', body: payload }),

  // recovery
  listPlans: (q = '') => api('/recovery/plans' + q),
  getPlan: (id) => api('/recovery/plans/' + id),
  comparePlan: (id) => api('/recovery/plans/' + id + '/compare'),
  alternatives: (pid, qty, exclude) => {
    let q = `?product_id=${pid}&quantity=${qty}`;
    if (exclude) q += `&exclude_supplier_id=${exclude}`;
    return api('/recovery/alternatives' + q);
  },
  progressPlan: (id, status) => api(`/recovery/plans/${id}/progress?status=${status}`, { method: 'POST' }),
  completePlan: (id) => api('/recovery/plans/' + id + '/complete', { method: 'POST' }),
  decisions: (q = '') => api('/recovery/decisions' + q),

  // approvals
  approvals: (q = '') => api('/approvals' + q),
  pendingApprovals: () => api('/approvals/pending'),
  decideApproval: (id, payload) => api('/approvals/' + id + '/decide', { method: 'POST', body: payload }),
  approvalPlan: (id) => api('/approvals/' + id + '/plan'),

  // forecasting
  demandForecasting: (h = 3) => api('/forecasting/demand?horizon_months=' + h),
  shortages: (h = 3) => api('/forecasting/shortages?horizon_months=' + h),
};
