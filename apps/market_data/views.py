# ============================================================
# Market data REST API endpoints
# ============================================================
import logging
from rest_framework import status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from django_ratelimit.decorators import ratelimit
from django.utils.decorators import method_decorator

from .models import MarketData, LiveTick, DataFetchLog
from .serializers import (
    MarketDataSerializer,
    LivePriceSerializer,
    DataFetchLogSerializer,
    CandleRequestSerializer,
)
from utils.constants import ALL_FOREX_PAIRS, Timeframe

logger = logging.getLogger('market_data')


def ok(data, code=status.HTTP_200_OK):
    return Response({'success': True, **data}, status=code)

def err(msg, code=status.HTTP_400_BAD_REQUEST):
    return Response({'success': False, 'message': msg}, status=code)


class CandleListView(APIView):
    """
    GET /api/v1/market-data/candles/
    Query params:
        symbol      EUR_USD         (required)
        timeframe   H1              (required)
        count       200             (default 200, max 5000)
        broker      oanda           (default oanda)
        refresh     false           (force re-fetch from broker)

    Returns normalised OHLCV candles from cache → DB → broker.
    """
    permission_classes = [permissions.IsAuthenticated]

    @method_decorator(ratelimit(key='user', rate='120/m', method='GET', block=True))
    def get(self, request):
        symbol    = request.query_params.get('symbol', '').upper().replace('/', '_')
        timeframe = request.query_params.get('timeframe', 'H1').upper()
        broker    = request.query_params.get('broker', 'oanda').lower()
        refresh   = request.query_params.get('refresh', 'false').lower() == 'true'

        try:
            count = int(request.query_params.get('count', 200))
            count = max(10, min(count, 5000))
        except ValueError:
            count = 200

        if not symbol:
            return err("'symbol' query parameter is required.")

        valid_tfs = [t.value for t in Timeframe]
        if timeframe not in valid_tfs:
            return err(f"Invalid timeframe '{timeframe}'. Valid: {valid_tfs}")

        if refresh:
            from apps.market_data.cache import invalidate_cache
            invalidate_cache(symbol, timeframe, count)

        from apps.market_data.cache import get_cached_candles
        df = get_cached_candles(symbol, timeframe, count, broker)

        if df is None or df.empty:
            return err(
                f"No market data available for {symbol}/{timeframe}. "
                f"Check your broker API key configuration.",
                code=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        # Convert to list for JSON response
        candles = []
        for ts, row in df.tail(count).iterrows():
            candles.append({
                'timestamp': ts.isoformat(),
                'open':      round(float(row['open']),  5),
                'high':      round(float(row['high']),  5),
                'low':       round(float(row['low']),   5),
                'close':     round(float(row['close']), 5),
                'volume':    int(row.get('volume', 0)),
            })

        return ok({
            'symbol':    symbol,
            'timeframe': timeframe,
            'broker':    broker,
            'count':     len(candles),
            'candles':   candles,
        })


class LivePriceView(APIView):
    """
    GET /api/v1/market-data/price/
    Query params:
        symbol    EUR_USD   (required)
        broker    oanda     (default)

    Returns current bid/ask/mid/spread.
    Rate limited to 60/min per user.
    """
    permission_classes = [permissions.IsAuthenticated]

    @method_decorator(ratelimit(key='user', rate='60/m', method='GET', block=True))
    def get(self, request):
        symbol = request.query_params.get('symbol', '').upper().replace('/', '_')
        broker = request.query_params.get('broker', 'oanda').lower()

        if not symbol:
            return err("'symbol' query parameter is required.")

        from services.data_feed.feed_manager import FeedManager
        price = FeedManager.fetch_live_price(symbol, broker)

        if not price:
            return err(
                f"Could not fetch live price for {symbol}.",
                code=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        return ok({'price': price})


class MultiPriceView(APIView):
    """
    POST /api/v1/market-data/prices/
    Body: {"symbols": ["EUR_USD", "GBP_USD", "USD_JPY"]}
    Returns prices for multiple symbols in one call.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        symbols = request.data.get('symbols', [])
        broker  = request.data.get('broker', 'oanda').lower()

        if not symbols or not isinstance(symbols, list):
            return err("'symbols' must be a non-empty list.")
        if len(symbols) > 20:
            return err("Maximum 20 symbols per request.")

        from services.data_feed.feed_manager import FeedManager
        prices = {}
        for symbol in symbols:
            sym = symbol.upper().replace('/', '_')
            p   = FeedManager.fetch_live_price(sym, broker)
            if p:
                prices[sym] = p

        return ok({'prices': prices, 'count': len(prices)})


class SupportedPairsView(APIView):
    """
    GET /api/v1/market-data/pairs/
    Returns all supported forex pairs and timeframes.
    No auth required — used by frontend dropdowns.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return ok({
            'pairs':      ALL_FOREX_PAIRS,
            'timeframes': [t.value for t in Timeframe],
        })


class FetchTriggerView(APIView):
    """
    POST /api/v1/market-data/fetch/
    Manually trigger a candle fetch task for a symbol.
    Body: {"symbol": "EUR_USD", "timeframe": "H1", "count": 500}
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        symbol    = request.data.get('symbol', '').upper()
        timeframe = request.data.get('timeframe', 'H1').upper()
        count     = int(request.data.get('count', 500))
        broker    = request.data.get('broker', 'oanda').lower()

        if not symbol:
            return err("'symbol' is required.")

        from apps.market_data.tasks import fetch_and_cache_candles
        task = fetch_and_cache_candles.apply_async(
            args=[symbol, timeframe, count, broker],
            queue='data',
        )

        return ok({
            'message':  f"Fetch task queued for {symbol}/{timeframe}",
            'task_id':  task.id,
            'symbol':   symbol,
            'timeframe':timeframe,
        }, code=status.HTTP_202_ACCEPTED)


class DataFetchLogView(APIView):
    """
    GET /api/v1/market-data/fetch-log/
    Returns recent data fetch history for debugging.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        logs = DataFetchLog.objects.order_by('-created_at')[:50]
        data = DataFetchLogSerializer(logs, many=True).data
        return ok({'logs': data, 'count': len(data)})