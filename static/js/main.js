/* ============================================================
   Global UI utilities, chart helpers, NLP command bar
   ============================================================ */

/* ── UI Utilities ──────────────────────────────────────────── */
const UI = {

  // ── Toast notifications ────────────────────────────────────
  toast(message, level = 'info', duration = 5000) {
    const container = document.getElementById('toastContainer');
    if (!container) return;

    const icons = { success: '✓', error: '✕', warning: '⚠', info: 'ℹ' };
    const toast  = document.createElement('div');
    toast.className = `toast toast-${level}`;
    toast.innerHTML = `
      <span style="color:var(--${level === 'info' ? 'accent' : level})">${icons[level] || 'ℹ'}</span>
      <span class="toast-msg">${message}</span>
      <button class="toast-close" onclick="this.parentElement.remove()">×</button>
    `;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), duration);
  },

  // ── Handle incoming trade alert ────────────────────────────
  handleTradeAlert(data) {
    const event  = data.event || '';
    const symbol = data.symbol || '';
    const pnl    = data.pnl || 0;
    if (event === 'trade_opened') {
      this.toast(`Trade opened: ${data.order_type?.toUpperCase()} ${symbol}`, 'info');
    } else if (event === 'trade_closed') {
      const level = pnl >= 0 ? 'success' : 'warning';
      const sign  = pnl >= 0 ? '+' : '';
      this.toast(`Trade closed: ${symbol} P&L=${sign}${pnl.toFixed(2)}`, level);
    }
  },

  // ── Handle NLP result ──────────────────────────────────────
  handleNLPResult(data) {
    const el = document.getElementById('nlpResultBox');
    if (el) {
      el.textContent  = JSON.stringify(data, null, 2);
      el.style.display = 'block';
    }
    if (data.success) {
      this.toast(`Command executed: ${data.explanation || data.action}`, 'success');
    } else {
      this.toast(`Command failed: ${data.reason || 'Unknown error'}`, 'error');
    }
  },

  // ── Format helpers ─────────────────────────────────────────
  formatPnl(val) {
    const n    = parseFloat(val) || 0;
    const sign = n >= 0 ? '+' : '';
    const cls  = n >= 0 ? 'positive' : 'negative';
    return `<span class="${cls}">${sign}${n.toFixed(2)}</span>`;
  },

  formatPct(val) {
    const n   = parseFloat(val) || 0;
    const cls = n >= 0 ? 'positive' : 'negative';
    return `<span class="${cls}">${n.toFixed(2)}%</span>`;
  },

  statusBadge(status) {
    const labels = {
      running:     'Running',
      idle:        'Idle',
      paused:      'Paused',
      stopped:     'Stopped',
      error:       'Error',
      backtesting: 'Backtesting',
    };
    return `<span class="badge badge-${status}">${labels[status] || status}</span>`;
  },

  formatDate(iso) {
    if (!iso) return '—';
    return new Date(iso).toLocaleString([], {
      month:'short', day:'numeric',
      hour:'2-digit', minute:'2-digit',
    });
  },
};

/* ── NLP Command Bar ───────────────────────────────────────── */
async function sendNLPCommand() {
  const input = document.getElementById('nlpInput');
  if (!input) return;

  const cmd = input.value.trim();
  if (!cmd) return;

  input.value = '';
  input.disabled = true;

  // Optimistic feedback
  UI.toast(`Processing: "${cmd.substring(0, 40)}…"`, 'info', 2000);

  try {
    const activeBotId = window.ACTIVE_BOT_ID || null;
    const res = await API.sendCommand(cmd, activeBotId);

    if (res?.success) {
      UI.toast('Command queued for processing ✓', 'success', 3000);
    } else {
      UI.toast(`Error: ${res?.message || 'Command failed'}`, 'error');
    }
  } catch(e) {
    UI.toast(`Error: ${e.message}`, 'error');
  } finally {
    input.disabled = false;
    input.focus();
  }
}

// Allow Enter key in NLP input
document.addEventListener('DOMContentLoaded', () => {
  const input = document.getElementById('nlpInput');
  if (input) {
    input.addEventListener('keypress', (e) => {
      if (e.key === 'Enter') sendNLPCommand();
    });
  }

  // Load user info
  API.getMe().then(data => {
    const badge = document.getElementById('userBadge');
    if (badge && data?.user) {
      badge.textContent = data.user.first_name || data.user.email;
    }
  }).catch(() => {});
});

/* ── Sidebar toggle ────────────────────────────────────────── */
function toggleSidebar() {
  document.getElementById('sidebar')?.classList.toggle('open');
}

/* ── Chart Helpers ─────────────────────────────────────────── */
const Charts = {

  DEFAULTS: {
    responsive:    true,
    maintainAspectRatio: false,
    animation:     { duration: 300 },
    plugins: {
      legend:  { display: false },
      tooltip: {
        backgroundColor: '#131929',
        borderColor:     '#1e2d4a',
        borderWidth:     1,
        titleColor:      '#e2e8f8',
        bodyColor:       '#7a8db0',
        padding:         10,
      },
    },
    scales: {
      x: {
        grid:  { color: '#1e2d4a' },
        ticks: { color: '#4a5a7a', font: { size: 11 } },
      },
      y: {
        grid:  { color: '#1e2d4a' },
        ticks: { color: '#4a5a7a', font: { size: 11 } },
      },
    },
  },

  // Equity curve line chart
  equity(canvasId, labels, values, label = 'Equity') {
    const ctx    = document.getElementById(canvasId);
    if (!ctx) return null;
    const isProfit = values.length > 1 && values[values.length-1] >= values[0];
    const color  = isProfit ? '#10b981' : '#ef4444';

    return new Chart(ctx, {
      type: 'line',
      data: {
        labels,
        datasets: [{
          label,
          data:            values,
          borderColor:     color,
          backgroundColor: `${color}15`,
          borderWidth:     2,
          fill:            true,
          tension:         0.3,
          pointRadius:     0,
          pointHoverRadius:4,
        }],
      },
      options: {
        ...this.DEFAULTS,
        scales: {
          ...this.DEFAULTS.scales,
          y: {
            ...this.DEFAULTS.scales.y,
            ticks: {
              ...this.DEFAULTS.scales.y.ticks,
              callback: v => `$${v.toLocaleString()}`,
            },
          },
        },
      },
    });
  },

  // Candlestick price chart using line chart (simplified)
  price(canvasId, labels, prices) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return null;

    return new Chart(ctx, {
      type: 'line',
      data: {
        labels,
        datasets: [{
          label:           'Close',
          data:            prices,
          borderColor:     '#3b82f6',
          backgroundColor: 'rgba(59,130,246,0.08)',
          borderWidth:     1.5,
          fill:            true,
          tension:         0.1,
          pointRadius:     0,
        }],
      },
      options: {
        ...this.DEFAULTS,
        scales: {
          ...this.DEFAULTS.scales,
          y: {
            ...this.DEFAULTS.scales.y,
            ticks: { ...this.DEFAULTS.scales.y.ticks, callback: v => v.toFixed(5) },
          },
        },
      },
    });
  },

  // Win/loss bar chart
  winLoss(canvasId, wins, losses) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return null;

    return new Chart(ctx, {
      type: 'bar',
      data: {
        labels: ['Wins', 'Losses'],
        datasets: [{
          data:            [wins, losses],
          backgroundColor: ['rgba(16,185,129,0.3)', 'rgba(239,68,68,0.3)'],
          borderColor:     ['#10b981', '#ef4444'],
          borderWidth:     1,
          borderRadius:    4,
        }],
      },
      options: { ...this.DEFAULTS },
    });
  },
};

/* ── Live price strip updater ──────────────────────────────── */
function updatePriceStrip(symbol, data) {
  const el = document.getElementById(`price_${symbol}`);
  if (!el) return;

  const bid   = parseFloat(data.bid || 0);
  const prev  = parseFloat(el.dataset.prevBid || bid);
  const dir   = bid >= prev ? 'price-up' : 'price-down';

  el.querySelector('.price-bid').className = `price-bid ${dir}`;
  el.querySelector('.price-bid').textContent = bid.toFixed(5);
  el.querySelector('.price-spread').textContent = `Spread: ${(data.spread * 10000).toFixed(1)}p`;
  el.dataset.prevBid = bid;
}