# ============================================================
# UPDATED — all alerts now include pips, RRR, and account name
# Full replacement of Phase O messages.py
# ============================================================
from datetime import datetime, timezone


def _pnl_emoji(pnl: float) -> str:
    return '🟢' if pnl >= 0 else '🔴'


def _dir_emoji(order_type: str) -> str:
    return '📈' if str(order_type).lower() == 'buy' else '📉'


def _sign(value: float) -> str:
    return '+' if value >= 0 else ''


def trade_opened(trade_data: dict) -> str:
    """
    Alert sent when a trade is opened.
    Now includes: pips SL/TP, RRR, account name, funded firm.

    Example output:
    📈 BUY XAUUSD
    ━━━━━━━━━━━━━━━━━
    Bot:      My Gold Bot
    Account:  FTMO [funded]
    Entry:    2350.20
    SL:       2349.80  (40 pips)
    TP:       2350.60  (40 pips)
    RRR:      1:2
    Lots:     0.05
    Risk:     1.0% | $100.00
    """
    symbol      = trade_data.get('symbol', '?')
    order_type  = trade_data.get('order_type', '?').upper()
    entry       = trade_data.get('entry_price', 0)
    sl          = trade_data.get('stop_loss')
    tp          = trade_data.get('take_profit')
    sl_pips     = trade_data.get('sl_pips')
    tp_pips     = trade_data.get('tp_pips')
    rrr         = trade_data.get('rrr_used')
    lot         = trade_data.get('lot_size', '?')
    bot_name    = trade_data.get('bot_name', '?')
    acct_label  = trade_data.get('account_label', '')
    acct_type   = trade_data.get('account_type', '')
    funded_firm = trade_data.get('funded_firm', '')
    risk_pct    = trade_data.get('risk_percent')
    risk_usd    = trade_data.get('risk_amount')

    # Build account line
    acct_line = _account_line(acct_label, acct_type, funded_firm)

    # Build SL/TP lines with pip info
    sl_line = f"<code>{sl}</code>"
    tp_line = f"<code>{tp}</code>"
    if sl_pips is not None:
        sl_line += f"  <i>({sl_pips:.0f} pips)</i>"
    if tp_pips is not None:
        tp_line += f"  <i>({tp_pips:.0f} pips)</i>"

    rrr_line = f"<b>1:{rrr}</b>" if rrr else "—"

    risk_line = ""
    if risk_pct is not None and risk_usd is not None:
        risk_line = (
            f"\nRisk:     <code>{risk_pct:.1f}%</code> | "
            f"<code>${risk_usd:.2f}</code>"
        )

    return (
        f"{_dir_emoji(order_type)} <b>{order_type} {symbol}</b>\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"Bot:      <code>{bot_name}</code>\n"
        f"Account:  {acct_line}\n"
        f"Entry:    <code>{entry}</code>\n"
        f"SL:       {sl_line}\n"
        f"TP:       {tp_line}\n"
        f"RRR:      {rrr_line}\n"
        f"Lots:     <code>{lot}</code>"
        f"{risk_line}\n"
        f"Time:     <code>{_now_utc()}</code>"
    )


def trade_closed(trade_data: dict) -> str:
    """
    Alert sent when a trade is closed.
    Includes: pips gained/lost, RRR achieved vs planned, account.

    Example:
    🟢 TRADE CLOSED — XAUUSD
    ━━━━━━━━━━━━━━━━━
    Bot:      My Gold Bot
    Account:  FTMO [funded]
    Entry:    2350.20  →  Exit: 2350.60
    P&L:      +$40.00
    Pips:     +40 pips  🎯 TP HIT
    RRR:      Planned 1:2 | Achieved 1:2.0
    Reason:   take_profit
    """
    symbol      = trade_data.get('symbol', '?')
    order_type  = trade_data.get('order_type', '?')
    entry       = trade_data.get('entry_price', 0)
    exit_p      = trade_data.get('exit_price', 0)
    pnl         = float(trade_data.get('profit_loss', 0))
    pips        = trade_data.get('profit_pips')
    rrr_used    = trade_data.get('rrr_used')
    rrr_achvd   = trade_data.get('rrr_achieved')
    reason      = trade_data.get('exit_reason', '?')
    bot_name    = trade_data.get('bot_name', '?')
    acct_label  = trade_data.get('account_label', '')
    acct_type   = trade_data.get('account_type', '')
    funded_firm = trade_data.get('funded_firm', '')

    acct_line  = _account_line(acct_label, acct_type, funded_firm)
    pnl_emoji  = _pnl_emoji(pnl)
    sign       = _sign(pnl)

    # Pips line
    if pips is not None:
        pips_sign   = '+' if pips >= 0 else ''
        pip_outcome = _pip_outcome_label(reason, pips)
        pips_line   = f"<b>{pips_sign}{pips:.1f} pips</b>  {pip_outcome}"
    else:
        pips_line   = "—"

    # RRR line
    if rrr_used and rrr_achvd:
        rrr_line = (
            f"Planned <b>1:{rrr_used}</b> | "
            f"Achieved <b>1:{rrr_achvd:.1f}</b>"
        )
    elif rrr_used:
        rrr_line = f"Planned <b>1:{rrr_used}</b>"
    else:
        rrr_line = "—"

    return (
        f"{pnl_emoji} <b>TRADE CLOSED — {symbol}</b>\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"Bot:      <code>{bot_name}</code>\n"
        f"Account:  {acct_line}\n"
        f"Entry:    <code>{entry}</code>  →  "
        f"Exit: <code>{exit_p}</code>\n"
        f"P&L:      <b>{sign}{pnl:.2f} USD</b>\n"
        f"Pips:     {pips_line}\n"
        f"RRR:      {rrr_line}\n"
        f"Reason:   <code>{reason}</code>\n"
        f"Time:     <code>{_now_utc()}</code>"
    )


def bot_started(bot_name: str, symbols: list, timeframe: str,
                account_label: str = '', account_type: str = '') -> str:
    acct = f"\nAccount:  {_account_line(account_label, account_type)}" \
           if account_label else ''
    return (
        f"▶️ <b>BOT STARTED</b>\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"Bot:       <code>{bot_name}</code>{acct}\n"
        f"Pairs:     <code>{', '.join(symbols or ['?'])}</code>\n"
        f"Timeframe: <code>{timeframe or 'H1'}</code>\n"
        f"Time:      <code>{_now_utc()}</code>"
    )


def bot_stopped(bot_name: str, reason: str = '',
                account_label: str = '') -> str:
    acct = f"\nAccount:  <code>{account_label}</code>" if account_label else ''
    return (
        f"⏹ <b>BOT STOPPED</b>\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"Bot:    <code>{bot_name}</code>{acct}\n"
        f"Reason: <code>{reason or 'Manual stop'}</code>\n"
        f"Time:   <code>{_now_utc()}</code>"
    )


def bot_paused(bot_name: str, reason: str = '',
               account_label: str = '') -> str:
    acct = f"\nAccount:  <code>{account_label}</code>" if account_label else ''
    return (
        f"⏸ <b>BOT PAUSED</b>\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"Bot:    <code>{bot_name}</code>{acct}\n"
        f"Reason: <code>{reason or 'Manual pause'}</code>\n"
        f"Time:   <code>{_now_utc()}</code>"
    )


def drawdown_warning(
    bot_name:    str,
    drawdown:    float,
    threshold:   float,
    account_label: str = '',
    funded_firm:   str = '',
) -> str:
    severity   = '🚨' if drawdown >= threshold * 0.95 else '⚠️'
    acct_extra = ''
    if funded_firm:
        acct_extra = f"\nFirm:      <code>{funded_firm.upper()}</code>"
    if account_label:
        acct_extra += f"\nAccount:   <code>{account_label}</code>"

    return (
        f"{severity} <b>DRAWDOWN WARNING</b>\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"Bot:       <code>{bot_name}</code>{acct_extra}\n"
        f"Drawdown:  <b>{drawdown:.2f}%</b>\n"
        f"Threshold: <code>{threshold:.1f}%</code>\n"
        f"Time:      <code>{_now_utc()}</code>\n\n"
        + (
            "🚨 <b>CRITICAL</b> — bot may halt soon!"
            if drawdown >= threshold * 0.95
            else "⚠️ Approaching halt threshold"
        )
    )


def daily_report(
    date_str:     str,
    total_trades: int,
    win_rate:     float,
    total_pnl:    float,
    running_bots: int,
    top_bot:      str  = '',
    open_trades:  int  = 0,
    total_pips:   float = 0.0,
    best_symbol:  str  = '',
    avg_rrr:      float = 0.0,
) -> str:
    sign    = _sign(total_pnl)
    emoji   = '📈' if total_pnl >= 0 else '📉'
    wr_bar  = _progress_bar(win_rate, 100)

    pips_sign = _sign(total_pips)
    pips_line = f"\nPips:          <b>{pips_sign}{total_pips:.1f}</b>"

    rrr_line  = (
        f"\nAvg RRR:       <code>1:{avg_rrr:.1f}</code>"
        if avg_rrr else ''
    )
    sym_line  = (
        f"\nBest Symbol:   <code>{best_symbol}</code>"
        if best_symbol else ''
    )
    bot_line  = (
        f"\nBest Bot:      <code>{top_bot}</code>"
        if top_bot else ''
    )

    return (
        f"{emoji} <b>DAILY REPORT — {date_str}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Total Trades:  <b>{total_trades}</b>\n"
        f"Win Rate:      {wr_bar} <b>{win_rate:.1f}%</b>\n"
        f"Total P&L:     <b>{sign}{total_pnl:.2f} USD</b>"
        f"{pips_line}"
        f"{rrr_line}"
        f"\nOpen Trades:   <code>{open_trades}</code>\n"
        f"Running Bots:  <code>{running_bots}</code>"
        f"{sym_line}"
        f"{bot_line}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Generated: <code>{_now_utc()}</code>"
    )


def nlp_command_result(
    command:     str,
    action:      str,
    success:     bool,
    explanation: str,
) -> str:
    status = '✅' if success else '❌'
    return (
        f"{status} <b>NLP COMMAND {'EXECUTED' if success else 'FAILED'}</b>\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"Command: <code>{command[:80]}</code>\n"
        f"Action:  <code>{action}</code>\n"
        f"Result:  {explanation[:120]}"
    )


def welcome(username: str) -> str:
    return (
        f"👋 <b>Welcome to ForexBot, {username}!</b>\n\n"
        f"Telegram alerts are now active.\n\n"
        f"<b>Each alert includes:</b>\n"
        f"• Pips SL / TP at entry\n"
        f"• Risk:Reward ratio (RRR)\n"
        f"• Account / funded firm name\n"
        f"• Pips gained/lost at close\n\n"
        f"<b>Commands:</b>\n"
        f"/status   — bot statuses\n"
        f"/pnl      — today's P&L + pips\n"
        f"/pause    — pause all bots\n"
        f"/resume   — resume all bots\n"
        f"/stop     — stop all bots\n"
        f"/report   — generate daily report\n"
        f"/help     — this message"
    )


def help_message() -> str:
    return (
        f"🤖 <b>ForexBot Commands</b>\n\n"
        f"/status         — All bot statuses + P&L\n"
        f"/pnl            — Today's P&L + pips breakdown\n"
        f"/pause          — Pause all running bots\n"
        f"/resume         — Resume all paused bots\n"
        f"/stop           — Stop all bots (emergency)\n"
        f"/report         — Daily report now\n"
        f"/help           — This message\n\n"
        f"💡 Alerts include pips, RRR, and account details."
    )


# ── Helpers ───────────────────────────────────────────────────

def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')


def _progress_bar(value: float, max_val: float, width: int = 8) -> str:
    filled = int(round(value / max_val * width))
    return '█' * filled + '░' * (width - filled)


def _account_line(
    label:       str,
    acct_type:   str = '',
    funded_firm: str = '',
) -> str:
    """Build a compact account line for alerts."""
    if not label:
        return '—'
    parts = [f"<code>{label}</code>"]
    if funded_firm and funded_firm not in ('', 'none', 'N/A'):
        parts.append(f"[{funded_firm.upper()}]")
    elif acct_type:
        parts.append(f"[{acct_type}]")
    return ' '.join(parts)


def _pip_outcome_label(reason: str, pips: float) -> str:
    """Return a label showing trade outcome."""
    r = str(reason).lower()
    if 'take_profit' in r or 'tp' in r:
        return '🎯 TP HIT'
    elif 'stop_loss' in r or 'sl' in r:
        return '🛑 SL HIT'
    elif pips > 0:
        return '✅ Profit'
    elif pips < 0:
        return '❌ Loss'
    return ''