import pandas as pd


def compute_market_metrics(closes: pd.Series) -> dict:
    closes = closes.dropna()
    price = float(closes.iloc[-1])
    ath = float(closes.max())
    ma200 = float(closes.tail(200).mean()) if len(closes) >= 200 else None
    daily_change = (price / float(closes.iloc[-2]) - 1) * 100 if len(closes) >= 2 else 0.0
    return {
        "price": price,
        "ath": ath,
        "drawdown_pct": (ath - price) / ath * 100,
        "ma200": ma200,
        "above_ma200": (price >= ma200) if ma200 is not None else None,
        "daily_change_pct": daily_change,
    }


def _fetch_yf_closes(symbol: str, period: str) -> pd.Series:
    import yfinance as yf
    df = yf.download(symbol, period=period, progress=False, auto_adjust=True)
    if df is None or df.empty:
        raise RuntimeError(f"yfinance 拉取 {symbol} 失败：返回空数据")
    close = df["Close"]
    if isinstance(close, pd.DataFrame):  # yfinance 多级列兼容
        close = close.iloc[:, 0]
    return close.dropna()


def _fetch_yf_history(symbol: str, period: str) -> pd.Series:
    """yfinance 第二通道：Ticker.history 与 download 走不同调用路径，限流时互为备份。"""
    import yfinance as yf
    df = yf.Ticker(symbol).history(period=period, auto_adjust=True)
    if df is None or df.empty:
        raise RuntimeError(f"yfinance Ticker.history 拉取 {symbol} 失败")
    return df["Close"].dropna()


def _fetch_fred_fallback(series_id: str, start: str) -> pd.Series:
    import os
    from src.datasources.rates import fetch_fred_series, fetch_fredgraph_csv
    api_key = os.environ.get("FRED_API_KEY")
    if api_key:
        try:
            return fetch_fred_series(series_id, api_key, observation_start=start)
        except Exception:
            pass
    return fetch_fredgraph_csv(series_id)  # 无 key 公开端点兜底


def fetch_ndx_closes(period: str = "max") -> pd.Series:
    errors = []
    for fetch in (lambda: _fetch_yf_closes("^NDX", period),
                  lambda: _fetch_yf_history("^NDX", period),
                  lambda: _fetch_fred_fallback("NASDAQ100", "1990-01-01")):
        try:
            return fetch()
        except Exception as e:
            errors.append(str(e))
    raise RuntimeError("纳指数据源全部失败：" + " | ".join(errors))


def fetch_vix() -> float | None:
    for fetch in (lambda: _fetch_yf_closes("^VIX", "5d"),
                  lambda: _fetch_fred_fallback("VIXCLS", "2026-01-01")):
        try:
            return float(fetch().iloc[-1])
        except Exception:
            continue
    return None
