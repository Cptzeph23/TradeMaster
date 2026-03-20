/* ============================================================
   WebSocket manager — handles all realtime connections
   ============================================================ */

const WS = {
  connections: {},
  handlers: {},
  reconnectDelays: {},
  MAX_RECONNECT_DELAY: 30000,

  // ── Connect to a WebSocket endpoint ────────────────────────
  connect(name, path, onMessage) {
    const token    = API.getToken();
    const protocol = location.protocol === 'https:' ? 'wss' : 'ws';
    const url      = `${protocol}://${location.host}${path}?token=${token}`;

    console.log(`[WS] Connecting: ${name} → ${path}`);

    const ws = new WebSocket(url);
    this.connections[name] = ws;
    this.handlers[name]    = onMessage;
    this.reconnectDelays[name] = this.reconnectDelays[name] || 1000;

    ws.onopen = () => {
      console.log(`[WS] Connected: ${name}`);
      this.reconnectDelays[name] = 1000;
      this._updateStatusIndicator(true);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        onMessage(data);
      } catch(e) {
        console.warn(`[WS] Parse error on ${name}:`, e);
      }
    };

    ws.onerror = (e) => {
      console.warn(`[WS] Error on ${name}:`, e);
    };

    ws.onclose = (event) => {
      console.log(`[WS] Closed: ${name} code=${event.code}`);
      this._updateStatusIndicator(false);

      // Don't reconnect on auth failure
      if (event.code === 4001 || event.code === 4003) return;

      // Exponential backoff reconnect
      const delay = this.reconnectDelays[name];
      this.reconnectDelays[name] = Math.min(delay * 2, this.MAX_RECONNECT_DELAY);
      console.log(`[WS] Reconnecting ${name} in ${delay}ms…`);
      setTimeout(() => {
        if (this.handlers[name]) this.connect(name, path, this.handlers[name]);
      }, delay);
    };

    return ws;
  },

  disconnect(name) {
    const ws = this.connections[name];
    if (ws) {
      delete this.handlers[name];
      ws.close(1000, 'Intentional disconnect');
      delete this.connections[name];
    }
  },

  disconnectAll() {
    Object.keys(this.connections).forEach(name => this.disconnect(name));
  },

  send(name, data) {
    const ws = this.connections[name];
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(data));
    }
  },

  // ── Dashboard WebSocket ────────────────────────────────────
  connectDashboard(onUpdate) {
    return this.connect('dashboard', '/ws/dashboard/', (msg) => {
      switch(msg.type) {
        case 'dashboard_update': onUpdate(msg.data); break;
        case 'notification':     UI.toast(msg.data.message, msg.data.level); break;
        case 'trade_alert':      UI.handleTradeAlert(msg.data); break;
        case 'nlp_result':       UI.handleNLPResult(msg.data); break;
        case 'pong':             break;
        default: console.log('[WS dashboard]', msg);
      }
    });
  },

  // ── Bot-specific WebSocket ─────────────────────────────────
  connectBot(botId, callbacks = {}) {
    return this.connect(`bot_${botId}`, `/ws/bots/${botId}/`, (msg) => {
      switch(msg.type) {
        case 'bot_status':   callbacks.onStatus?.(msg.data);    break;
        case 'signal':       callbacks.onSignal?.(msg.data);    break;
        case 'trade_opened': callbacks.onTradeOpen?.(msg.data); break;
        case 'trade_closed': callbacks.onTradeClosed?.(msg.data);break;
        case 'bot_log':      callbacks.onLog?.(msg.data);       break;
        case 'nlp_result':   callbacks.onNLP?.(msg.data);       break;
        case 'pong':         break;
        default: console.log('[WS bot]', msg);
      }
    });
  },

  // ── Price WebSocket ────────────────────────────────────────
  connectPrices(symbol, onTick) {
    return this.connect(
      `price_${symbol}`,
      `/ws/prices/${symbol}/`,
      (msg) => { if (msg.type === 'price_tick') onTick(msg.data); }
    );
  },

  // ── Status indicator ──────────────────────────────────────
  _updateStatusIndicator(connected) {
    const dot  = document.querySelector('.status-dot');
    const text = document.querySelector('.status-text');
    if (dot)  { dot.className  = `status-dot ${connected ? 'connected' : 'disconnected'}`; }
    if (text) { text.textContent = connected ? 'Live' : 'Reconnecting…'; }
  },
};