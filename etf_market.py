"""Public-only market requests. No account, shock, balance or goal inputs."""
from datetime import date
import json
from pathlib import Path
import numpy as np
import pandas as pd
import streamlit as st

CATALOG=json.loads((Path(__file__).resolve().parent/'market_data/etf_catalog.json').read_text())
SYMBOLS=tuple(e['symbol'] for e in CATALOG['entries'])


class MarketUnavailable(ValueError):
    pass


def normalize_history(raw):
    if not isinstance(raw,pd.DataFrame) or raw.empty:raise MarketUnavailable('The provider returned no trading history.')
    if isinstance(raw.columns,pd.MultiIndex):raise MarketUnavailable('Unexpected multi-symbol history; no prices displayed.')
    if 'Adj Close' not in raw:raise MarketUnavailable('Adjusted prices are missing. Raw closes are not substituted for adjusted history.')
    if isinstance(raw.index,pd.DatetimeIndex):dates=raw.index
    elif 'Date' in raw:dates=pd.to_datetime(raw['Date'],errors='coerce')
    else:raise MarketUnavailable('Trading dates are missing.')
    dates=pd.DatetimeIndex(dates)
    if dates.tz is not None:dates=dates.tz_localize(None)
    frame=pd.DataFrame({'date':dates.normalize(),'adjusted_price':pd.to_numeric(raw['Adj Close'],errors='coerce').to_numpy()})
    valid=frame['date'].notna()&np.isfinite(frame['adjusted_price'])&(frame['adjusted_price']>0)
    removed=int((~valid).sum());frame=frame.loc[valid].sort_values('date',kind='stable')
    if frame.groupby('date')['adjusted_price'].nunique().gt(1).any():
        raise MarketUnavailable('Conflicting adjusted prices for the same trading date.')
    duplicates=int(frame.duplicated('date').sum());frame=frame.drop_duplicates('date').reset_index(drop=True)
    if len(frame)<2:raise MarketUnavailable('At least two valid trading dates are required.')
    frame.attrs.update(discarded_rows=removed,duplicate_dates=duplicates)
    return frame


def _download(symbol,start,end):
    try:import yfinance as yf
    except ImportError as exc:raise MarketUnavailable('Optional history dependency missing. Install requirements-etf.txt; the local contribution view remains available.') from exc
    try:
        return yf.Ticker(symbol).history(start=start,end=end,interval='1d',auto_adjust=False,
            actions=False,timeout=8,raise_errors=True)
    except Exception as exc:
        raise MarketUnavailable('Yahoo adjusted-price history is unavailable. Check network access or try later; the local contribution view remains available.') from exc


@st.cache_data(ttl=3600,max_entries=12,show_spinner=False)
def get_history(symbol,start,end):
    if symbol not in SYMBOLS:raise MarketUnavailable('Select a symbol from the curated market list.')
    start_date,end_date=date.fromisoformat(start),date.fromisoformat(end)
    if start_date>=end_date or (end_date-start_date).days>1120:raise MarketUnavailable('Invalid source date range.')
    frame=normalize_history(_download(symbol,start,end))
    frame=frame.loc[(frame['date']>=pd.Timestamp(start))&(frame['date']<pd.Timestamp(end))].copy()
    if len(frame)<2:raise MarketUnavailable('Insufficient valid history in the requested source window.')
    return frame
