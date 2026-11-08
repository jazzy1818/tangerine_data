"""Tangerine ETF & Dynamic Market Intelligence Service.

Fetches dynamic, real-time market quotes and historical candlestick data
from the live Yahoo Finance API (query1.finance.yahoo.com) across Canadian
(TSX) and US (NYSE/NASDAQ) exchanges. Supports any arbitrary ticker input.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
import pandas as pd
import yfinance as yf

# Curated catalog of leading Canadian index ETFs suited for banking & wealth management
ETF_CATALOG: Dict[str, Dict[str, Any]] = {
    "CASH.TO": {
        "name": "Global X High Interest Savings ETF",
        "category": "Cash Equivalent / Ultra-Low Risk",
        "benchmark": "Canadian Overnight Repo Rate",
        "mer": 0.11,
        "yield_est": 4.5,
        "purpose": "Short-Term Emergency Reserve & Down Payment (< 2 yrs)",
        "suitability": "Capital preservation, high liquidity, zero stock market risk.",
        "risk_level": "Low",
    },
    "XBAL.TO": {
        "name": "iShares Core Balanced ETF Portfolio (60/40)",
        "category": "Balanced Multi-Asset (60% Equities / 40% Bonds)",
        "benchmark": "Global Multi-Asset Index",
        "mer": 0.20,
        "yield_est": 3.1,
        "purpose": "Medium-Term Down Payment & Wealth Cushion (2–5 yrs)",
        "suitability": "Smooth compounding with built-in bond downside protection.",
        "risk_level": "Moderate",
    },
    "VFV.TO": {
        "name": "Vanguard S&P 500 Index ETF (CAD)",
        "category": "US Large-Cap Equity",
        "benchmark": "S&P 500 Index (CAD)",
        "mer": 0.09,
        "yield_est": 1.4,
        "purpose": "Long-Term Growth & Financial Freedom (5+ yrs)",
        "suitability": "Maximum compounding power tracking top 500 US companies.",
        "risk_level": "High Growth",
    },
    "XEQT.TO": {
        "name": "iShares Core Equity All-Cap ETF",
        "category": "100% Global Equity (Canada, US, Intl, Emerging)",
        "benchmark": "MSCI All Country World Index",
        "mer": 0.20,
        "yield_est": 2.2,
        "purpose": "Long-Term All-Weather Global Equity (5+ yrs)",
        "suitability": "Ultimate global diversification in a single Canadian dollar ticker.",
        "risk_level": "High Growth",
    },
    "XIU.TO": {
        "name": "iShares S&P/TSX 60 Index ETF",
        "category": "Canadian Large-Cap Blue Chip",
        "benchmark": "S&P/TSX 60 Index",
        "mer": 0.18,
        "yield_est": 3.4,
        "purpose": "Canadian Dividend & Domestic Large-Cap Stability",
        "suitability": "Exposure to Canada's largest banks, energy, and telecom giants.",
        "risk_level": "Moderate-High",
    },
}


def fetch_live_ticker_details(symbol: str, period: str = "1y") -> Dict[str, Any]:
    """Fetch live real-time price, metrics, and historical series for ANY ticker dynamically."""
    cleaned_symbol = symbol.strip().upper()
    ticker = yf.Ticker(cleaned_symbol)

    try:
        hist = ticker.history(period=period)
        if hist.empty:
            raise ValueError(f"No price data found for ticker '{cleaned_symbol}'. Check symbol format.")

        last_price = float(hist["Close"].iloc[-1])
        prev_close = float(hist["Close"].iloc[-2]) if len(hist) > 1 else last_price
        day_change = last_price - prev_close
        day_change_pct = (day_change / prev_close) * 100.0 if prev_close > 0 else 0.0

        period_start = float(hist["Close"].iloc[0])
        period_change_pct = ((last_price / period_start) - 1.0) * 100.0 if period_start > 0 else 0.0

        day_high = float(hist["High"].iloc[-1])
        day_low = float(hist["Low"].iloc[-1])
        volume = int(hist["Volume"].iloc[-1])

        high_52w = float(hist["High"].max())
        low_52w = float(hist["Low"].min())

        # Fast info metadata
        fast = getattr(ticker, "fast_info", None)
        currency = getattr(fast, "currency", "CAD" if cleaned_symbol.endswith(".TO") else "USD")
        exchange = getattr(fast, "exchange", "TOR" if cleaned_symbol.endswith(".TO") else "US")

        # Format history dataframe for charting
        chart_df = hist[["Close"]].copy()
        chart_df.index = chart_df.index.strftime("%Y-%m-%d")
        chart_df.rename(columns={"Close": f"{cleaned_symbol} Close ({currency})"}, inplace=True)

        return {
            "success": True,
            "symbol": cleaned_symbol,
            "last_price": round(last_price, 2),
            "prev_close": round(prev_close, 2),
            "day_change": round(day_change, 2),
            "day_change_pct": round(day_change_pct, 2),
            "period_change_pct": round(period_change_pct, 2),
            "day_high": round(day_high, 2),
            "day_low": round(day_low, 2),
            "volume": volume,
            "52w_high": round(high_52w, 2),
            "52w_low": round(low_52w, 2),
            "currency": currency,
            "exchange": exchange,
            "as_of": datetime.now().strftime("%Y-%m-%d %H:%M:%S EST"),
            "chart_df": chart_df,
        }
    except Exception as e:
        return {
            "success": False,
            "symbol": cleaned_symbol,
            "error": str(e),
        }


def get_etf_summary(period: str = "1y") -> List[Dict[str, Any]]:
    """Fetch live market metrics and performance for all catalog ETFs.
    
    If market feeds are unreachable or offline, returns None for dynamic values
    rather than fabricating synthetic prices.
    """
    results = []
    for ticker, meta in ETF_CATALOG.items():
        last_price = None
        return_pct = None
        momentum_5d = None
        is_live = False

        try:
            t = yf.Ticker(ticker)
            hist = t.history(period=period)
            if not hist.empty and len(hist) > 5:
                last_price = round(float(hist["Close"].iloc[-1]), 2)
                first_price = round(float(hist["Close"].iloc[0]), 2)
                return_pct = round(((last_price / first_price) - 1.0) * 100.0, 1)

                five_day_ago = float(hist["Close"].iloc[-min(5, len(hist))])
                momentum_5d = round(((last_price / five_day_ago) - 1.0) * 100.0, 1)
                is_live = True
        except Exception:
            last_price = None
            return_pct = None
            momentum_5d = None
            is_live = False

        item = {
            "ticker": ticker,
            "name": meta["name"],
            "category": meta["category"],
            "last_price": last_price,
            "return_pct": return_pct,
            "momentum_5d": momentum_5d,
            "is_live": is_live,
            "mer": meta["mer"],
            "yield_est": meta["yield_est"],
            "risk_level": meta["risk_level"],
            "purpose": meta["purpose"],
            "suitability": meta["suitability"],
        }
        results.append(item)

    return results


def get_etf_historical_trends(tickers: Optional[List[str]] = None, period: str = "1y") -> pd.DataFrame:
    """Fetch normalized historical percentage return trajectories for comparison charts."""
    if tickers is None:
        tickers = list(ETF_CATALOG.keys())

    df_dict = {}
    for ticker in tickers:
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period=period)
            if not hist.empty:
                norm_series = (hist["Close"] / hist["Close"].iloc[0]) * 100.0
                norm_series.index = norm_series.index.strftime("%Y-%m-%d")
                df_dict[ticker] = norm_series
        except Exception:
            pass

    if df_dict:
        combined_df = pd.DataFrame(df_dict).ffill().bfill()
        return combined_df
    return pd.DataFrame()


def recommend_etf_for_customer(
    months_to_downpayment: Optional[float],
    emergency_funded: bool,
    age: Optional[int] = None,
) -> Dict[str, Any]:
    """Recommends the optimal ETF based on the customer's specific life stage and time horizon."""
    if not emergency_funded:
        return {
            "recommended_ticker": "CASH.TO",
            "name": "Global X High Interest Savings ETF (CASH.TO)",
            "rationale": "Priority 1 is completing your emergency reserve. CASH.TO provides liquid, daily interest with zero market volatility.",
            "recommended_allocation_pct": 100,
        }

    if months_to_downpayment is not None and months_to_downpayment <= 24:
        return {
            "recommended_ticker": "CASH.TO",
            "name": "Global X High Interest Savings ETF (CASH.TO)",
            "rationale": f"Your down payment goal is only {months_to_downpayment:.1f} months away. Never risk down payment money in volatile stocks. CASH.TO preserves every dollar while generating ~4.5% yield.",
            "recommended_allocation_pct": 80,
            "secondary_ticker": "XBAL.TO",
            "secondary_allocation_pct": 20,
        }
    elif months_to_downpayment is not None and months_to_downpayment <= 60:
        return {
            "recommended_ticker": "XBAL.TO",
            "name": "iShares Core Balanced ETF (XBAL.TO)",
            "rationale": f"With a {months_to_downpayment:.1f}-month horizon, a 60/40 balanced portfolio gives you stock upside with bond buffers to protect against sudden market drops before purchase.",
            "recommended_allocation_pct": 70,
            "secondary_ticker": "VFV.TO",
            "secondary_allocation_pct": 30,
        }
    else:
        return {
            "recommended_ticker": "XEQT.TO",
            "name": "iShares Core Equity All-Cap ETF (XEQT.TO)",
            "rationale": "With long-term financial runway, 100% global equity indexing provides the highest expected historical compound return (7-10% annually) to build true generational wealth.",
            "recommended_allocation_pct": 70,
            "secondary_ticker": "VFV.TO",
            "secondary_allocation_pct": 30,
        }
