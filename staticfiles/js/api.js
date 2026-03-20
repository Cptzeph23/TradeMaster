/* ============================================================
   REST API client — all HTTP calls go through this module
   ============================================================ */

const API = {
  BASE: '/api/v1',
  token: null,

  // ── Auth ────────────────────────────────────────────────────
  setToken(t)  { this.token = t; localStorage.setItem('access_token', t); },
  getToken()   { return this.token || localStorage.getItem('access_token'); },
  clearToken() { this.token = null; localStorage.removeItem('access_token'); localStorage.removeItem('refresh_token'); },

  async _request(method, path, body = null) {
    const headers = { 'Content-Type': 'application/json' };
    const token   = this.getToken();
    if (token) headers['Authorization'] = `Bearer ${token}`;

    const opts = { method, headers };
    if (body)  opts.body = JSON.stringify(body);

    let res = await fetch(`${this.BASE}${path}`, opts);

    // Auto-refresh expired token
    if (res.status === 401) {
      const refreshed = await this.refreshToken();
      if (refreshed) {
        headers['Authorization'] = `Bearer ${this.getToken()}`;
        res = await fetch(`${this.BASE}${path}`, { ...opts, headers });
      } else {
        this.clearToken();
        window.location.href = '/accounts/login/';
        return null;
      }
    }
    if (!res.ok && res.status !== 400) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.message || `HTTP ${res.status}`);
    }
    return res.json();
  },

  async refreshToken() {
    const refresh = localStorage.getItem('refresh_token');
    if (!refresh) return false;
    try {
      const res = await fetch(`${this.BASE}/auth/token/refresh/`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ refresh }),
      });
      if (!res.ok) return false;
      const data = await res.json();
      if (data.access) {
        this.setToken(data.access);
        if (data.refresh) localStorage.setItem('refresh_token', data.refresh);
        return true;
      }
      return false;
    } catch { return false; }
  },

  get:    (p)    => API._request('GET',    p),
  post:   (p, b) => API._request('POST',   p, b),
  patch:  (p, b) => API._request('PATCH',  p, b),
  put:    (p, b) => API._request('PUT',    p, b),
  delete: (p)    => API._request('DELETE', p),

  // ── Auth endpoints ─────────────────────────────────────────
  async login(email, password) {
    const data = await this.post('/auth/login/', { email, password });
    if (data?.success) {
      this.setToken(data.tokens.access);
      localStorage.setItem('refresh_token', data.tokens.refresh);
    }
    return data;
  },
  async logout() {
    const refresh = localStorage.getItem('refresh_token');
    if (refresh) await this.post('/auth/logout/', { refresh }).catch(() => {});
    this.clearToken();
    window.location.href = '/accounts/login/';
  },
  getMe:     ()         => API.get('/auth/me/'),
  getAccounts: ()       => API.get('/auth/trading-accounts/'),

  // ── Bots ───────────────────────────────────────────────────
  getBots:      ()      => API.get('/trading/bots/'),
  getBot:       (id)    => API.get(`/trading/bots/${id}/`),
  createBot:    (b)     => API.post('/trading/bots/', b),
  updateBot:    (id, b) => API.patch(`/trading/bots/${id}/`, b),
  deleteBot:    (id)    => API.delete(`/trading/bots/${id}/`),
  startBot:     (id)    => API.post(`/trading/bots/${id}/start/`),
  stopBot:      (id)    => API.post(`/trading/bots/${id}/stop/`),
  pauseBot:     (id)    => API.post(`/trading/bots/${id}/pause/`),
  resumeBot:    (id)    => API.post(`/trading/bots/${id}/resume/`),
  getBotTrades: (id)    => API.get(`/trading/bots/${id}/trades/`),
  getBotLogs:   (id)    => API.get(`/trading/bots/${id}/logs/`),

  // ── NLP Commands ───────────────────────────────────────────
  sendCommand: (cmd, botId = null) => API.post('/trading/command/', {
    command: cmd, ...(botId && { bot_id: botId })
  }),
  getCommandHistory: () => API.get('/trading/commands/'),

  // ── Strategies ─────────────────────────────────────────────
  getStrategies:     ()      => API.get('/strategies/'),
  getPlugins:        ()      => API.get('/strategies/plugins/'),
  createStrategy:    (s)     => API.post('/strategies/', s),
  updateStrategy:    (id, s) => API.patch(`/strategies/${id}/`, s),
  deleteStrategy:    (id)    => API.delete(`/strategies/${id}/`),
  previewStrategy:   (id, b) => API.post(`/strategies/${id}/preview/`, b),

  // ── Market Data ────────────────────────────────────────────
  getCandles: (sym, tf, cnt = 200) =>
    API.get(`/market-data/candles/?symbol=${sym}&timeframe=${tf}&count=${cnt}`),
  getPrice:   (sym)  => API.get(`/market-data/price/?symbol=${sym}`),
  getPairs:   ()     => API.get('/market-data/pairs/'),

  // ── Risk ───────────────────────────────────────────────────
  getRiskRules:    (botId) => API.get(`/risk/bots/${botId}/rules/`),
  updateRiskRules: (botId, d) => API.patch(`/risk/bots/${botId}/rules/`, d),
  getRiskAnalysis: (botId) => API.get(`/risk/bots/${botId}/analysis/`),
  getPerformance:  (botId) => API.get(`/risk/bots/${botId}/performance/`),
  calcLotSize:     (d)     => API.post('/risk/calculate/lot-size/', d),

  // ── Backtesting ────────────────────────────────────────────
  getBacktests:     ()      => API.get('/backtesting/'),
  createBacktest:   (b)     => API.post('/backtesting/', b),
  getBacktest:      (id)    => API.get(`/backtesting/${id}/`),
  getBacktestStatus:(id)    => API.get(`/backtesting/${id}/status/`),
  cancelBacktest:   (id)    => API.post(`/backtesting/${id}/cancel/`),
  quickBacktest:    (b)     => API.post('/backtesting/quick-run/', b),
  getBacktestTrades:(id)    => API.get(`/backtesting/${id}/trades/`),
};