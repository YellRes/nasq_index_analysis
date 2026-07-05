import os

import pandas as pd
import requests

FRED_URL = "https://api.stlouisfed.org/fred/series/observations"
TRADING_DAYS_3M = 63


def fetch_fred_series(series_id: str, api_key: str,
                      observation_start: str = "2024-01-01") -> pd.Series:
    """通用 FRED 序列拉取（rates 与 market 的回退共用）。"""
    resp = requests.get(FRED_URL, params={
        "series_id": series_id, "api_key": api_key,
        "file_type": "json", "observation_start": observation_start,
    }, timeout=30)
    resp.raise_for_status()
    obs = [o for o in resp.json()["observations"] if o["value"] != "."]
    if not obs:
        raise RuntimeError(f"FRED {series_id} 返回空数据")
    return pd.Series([float(o["value"]) for o in obs],
                     index=pd.to_datetime([o["date"] for o in obs]), dtype=float)


def fetch_fredgraph_csv(series_id: str) -> pd.Series:
    """FRED 公开 CSV 端点，无需 API key（fredgraph.csv）。"""
    import io
    resp = requests.get("https://fred.stlouisfed.org/graph/fredgraph.csv",
                        params={"id": series_id}, timeout=30,
                        headers={"User-Agent": "dca-monitor/1.0"})
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text))
    date_col, value_col = df.columns[0], df.columns[1]
    df[value_col] = pd.to_numeric(df[value_col], errors="coerce")
    series = pd.Series(df[value_col].values,
                       index=pd.to_datetime(df[date_col]), dtype=float).dropna()
    if series.empty:
        raise RuntimeError(f"fredgraph {series_id} 返回空数据")
    return series


def compute_rate_metrics(series: pd.Series) -> dict:
    series = series.dropna()
    latest = float(series.iloc[-1])
    change = (float(series.iloc[-1]) - float(series.iloc[-1 - TRADING_DAYS_3M])
              if len(series) > TRADING_DAYS_3M else None)
    return {"tnx_yield": latest, "tnx_change_3m": change}


def _fetch_tnx() -> pd.Series:
    import yfinance as yf
    df = yf.download("^TNX", period="1y", progress=False, auto_adjust=True)
    if df is None or df.empty:
        raise RuntimeError("yfinance 拉取 ^TNX 失败：返回空数据")
    close = df["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    close = close.dropna()
    if close.empty:
        raise RuntimeError("yfinance 拉取 ^TNX 失败：全为空值")
    return close


def fetch_10y(api_key: str | None = None) -> pd.Series:
    api_key = api_key or os.environ.get("FRED_API_KEY")
    if api_key:
        try:
            return fetch_fred_series("DGS10", api_key)
        except Exception:
            pass
    try:
        return _fetch_tnx()
    except Exception:
        pass
    try:
        return fetch_fredgraph_csv("DGS10")
    except Exception as e:
        raise RuntimeError(f"10Y 利率数据源全部失败: {e}") from e
