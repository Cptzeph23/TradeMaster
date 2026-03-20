/* ============================================================
   FIXED: Stops reconnecting when server returns 404 (HTTP only mode)
          Detects manage.py runserver vs Daphne automatically
   ============================================================ */

const WS = {
  connections: {},
  handlers: {},
  reconnectDelays: {},
  disabled: false,          // set to true when WS not available
  MAX_RECONNECT_DELAY: 30000,

  // ── Check if WebSocket is available before connecting ──────
  async _checkAvailable() {
    if (this.disabled) return false;
    try {
      // Quick HTTP check on a WS path — if it returns 404 or 426
      // we know we're on runserver, not Daphne
      const res = await fetch('/ws/dashboard/', {
        method: 'GET',
        headers: { 'X-Check': '1' },
        signal: AbortSignal.timeout(2000),
      });
      // 426 = our ws_unavailable view (runserver with urls.py fix)
      // 404 = old urls.py without the fallback route
      if (res.status === 404 || res.status === 426) {
        console.warn(
          '[WS] WebSocket not available — running manage.py runserver. ' +
          'Switch to Daphne for live updates: ' +
          'daphne -b 127.0.0.1 -p 8001 config.asgi:application'
        );
        this.disabled = true;
        this._updateStatusIndicator(false, 'HTTP only');
        return false;
      }
      return true;
    } catch(e) {
      return true;  // timeout/error — try connecting anyway
    }
  },

  // ── Connect to a WebSocket endpoint ────────────────────────
  async connect(name, path, onMessage) {
    // Only check availability once
    if (this.disabled) return null;
    if (!this._availabilityChecked) {
      this._availabilityChecked = true;
      const available = await this._checkAvailable();
      if (!available) return null;
    }

    const token    = API.getToken();
    const protocol = location.protocol === 'https:' ? 'wss' : 'ws';
    const url      = `${protocol}://${location.host}${path}?token=${token}`;

    console.log(`[WS] Connecting: ${name}`);

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
      console.debug(`[WS] Error on ${name} (normal if using runserver)`);
    };

    ws.onclose = (event) => {
      console.log(`[WS] Closed: ${name} code=${event.code}`);

      // Don't reconnect on auth failure or explicit close
      if (event.code === 4001 || event.code === 4003 || event.code === 1000) return;

      // Don't reconnect if WS is disabled (HTTP-only mode)
      if (this.disabled) return;

      // Don't reconnect on HTTP 404/426 — wrong server type
      if (event.code === 1006) {
        // 1006 = abnormal closure, could be HTTP server rejecting WS
        // Check if we've failed too many times
        const delay = this.reconnectDelays[name];
        if (delay >= 16000) {
          console.warn(`[WS] ${name} keeps failing — likely running runserver not Daphne. Stopping reconnects.`);
          this.disabled = true;
          this._updateStatusIndicator(false, 'HTTP only — use Daphne');
          return;
        }
      }

      // Exponential backoff reconnect
      const delay = this.reconnectDelays[name];
      this.reconnectDelays[name] = Math.min(delay * 2, this.MAX_RECONNECT_DELAY);
      this._updateStatusIndicator(false);
      console.log(`[WS] Reconnecting ${name} in ${delay}ms…`);
      setTimeout(() => {
        if (this.handlers[name] && !this.disabled) {
          this.connect(name, path, this.handlers[name]);
        }
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
        case 'pong': break;
        default: console.debug('[WS dashboard]', msg.type);
      }
    });
  },

  // ── Bot-specific WebSocket ─────────────────────────────────
  connectBot(botId, callbacks = {}) {
    return this.connect(`bot_${botId}`, `/ws/bots/${botId}/`, (msg) => {
      switch(msg.type) {
        case 'bot_status':   callbacks.onStatus?.(msg.data);     break;
        case 'signal':       callbacks.onSignal?.(msg.data);     break;
        case 'trade_opened': callbacks.onTradeOpen?.(msg.data);  break;
        case 'trade_closed': callbacks.onTradeClosed?.(msg.data);break;
        case 'bot_log':      callbacks.onLog?.(msg.data);        break;
        case 'nlp_result':   callbacks.onNLP?.(msg.data);        break;
        case 'pong': break;
        default: console.debug('[WS bot]', msg.type);
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
  _updateStatusIndicator(connected, label = null) {
    const dot  = document.querySelector('.status-dot');
    const text = document.querySelector('.status-text');
    if (dot) {
      dot.className = `status-dot ${connected ? 'connected' : 'disconnected'}`;
    }
    if (text) {
      text.textContent = label || (connected ? 'Live' : 'Reconnecting…');
    }
  },
};