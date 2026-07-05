def fetch_qqq_pe() -> float | None:
    try:
        import yfinance as yf
        pe = yf.Ticker("QQQ").info.get("trailingPE")
        return float(pe) if pe and 5 < float(pe) < 100 else None   # 合理性护栏
    except Exception:
        return None
