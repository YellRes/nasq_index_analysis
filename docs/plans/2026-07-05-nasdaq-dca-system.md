# 纳指定投监控系统 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 每月定时产出"纳指该投多少"的规则化建议报告并邮件推送，大跌时即时提醒。

**Architecture:** GitHub Actions 两条定时流水线（月度必发 / 每日触发才发）→ Python 拉取信号（yfinance + FRED）→ 纯函数规则引擎算定投倍数 → Jinja2 渲染 HTML 报告 → QQ 邮箱 SMTP 推送。每期结果 JSON 存回仓库。

**Tech Stack:** Python 3.11+、yfinance、pandas、requests、Jinja2、matplotlib、PyYAML、pytest、openai SDK（DeepSeek 兼容）、GitHub Actions。

## Global Constraints

- 月度基准 **1000 元**；回撤档位 10/20/30% → 倍数 **1.25/1.5/2.0**；利率修正 ×0.8 / ×1.2；四舍五入到 **0.25** 档；**上限 2.0x**（全部参数只写在 `config.yaml`，代码零硬编码）。
- 规则引擎必须是**纯函数**：不碰网络、不碰 IO、不读环境变量。
- 任何数据源失败必须**降级**而非崩溃：主信号（^NDX）失败才允许整体失败；辅助信号（VIX/利率/PE）失败时报告标注"缺失"。
- AI 点评失败不阻塞报告发送。
- 凭据只从环境变量读取（本地 `.env` 不入库；线上 GitHub Secrets：`SMTP_USER`、`SMTP_PASS`、`MAIL_TO`、`FRED_API_KEY`、`DEEPSEEK_API_KEY`）。
- **git 纪律（用户特殊要求）**：执行者不得擅自 commit。每个任务的 Commit 步骤执行前需用户确认；用户可在会话开始时一次性授权"本次会话允许 commit"。禁止 push。
- 所有面向用户的文案（报告、邮件）使用中文。
- Windows 环境：命令用 PowerShell 语法；Python 虚拟环境在 `.venv\`。

---

## File Structure（全景）

```
stock-analysis/
├── .github/workflows/
│   ├── monthly-report.yml      # Task 10
│   └── daily-check.yml         # Task 11
├── src/
│   ├── __init__.py
│   ├── models.py               # Task 2  信号/决策数据类
│   ├── rules.py                # Task 2,3 规则引擎（纯函数）
│   ├── datasources/
│   │   ├── __init__.py
│   │   ├── market.py           # Task 4  ^NDX/^VIX 计算（纯函数）+ yfinance 拉取
│   │   ├── rates.py            # Task 5  FRED 10Y + ^TNX 备用
│   │   └── valuation.py        # Task 13 QQQ trailingPE 尽力而为
│   ├── pipeline.py             # Task 6  信号采集编排（含降级）
│   ├── history.py              # Task 7  history/ JSON 读写
│   ├── report.py               # Task 8  Jinja2 渲染 + matplotlib 迷你图
│   ├── notify.py               # Task 9  QQ SMTP 发送
│   ├── alerts.py               # Task 11 每日触发判定 + 去重状态
│   └── commentary.py           # Task 12 DeepSeek 点评
├── templates/report.html.j2    # Task 8
├── tests/
│   ├── test_rules.py           # Task 2,3
│   ├── test_market.py          # Task 4
│   ├── test_rates.py           # Task 5
│   ├── test_scenarios.py       # Task 6  历史场景快照
│   ├── test_history.py         # Task 7
│   ├── test_report.py          # Task 8
│   └── test_alerts.py          # Task 11
├── main.py                     # Task 7  CLI 入口
├── config.yaml                 # Task 1
├── requirements.txt            # Task 1
├── .gitignore                  # Task 1
└── history/                    # 运行时生成
```

---

### Task 1: 项目脚手架

**Files:**
- Create: `requirements.txt`, `config.yaml`, `.gitignore`, `src/__init__.py`, `src/datasources/__init__.py`, `tests/__init__.py`, `pytest.ini`

**Interfaces:**
- Produces: `config.yaml` 的结构被后续所有任务消费（键名见下方，不得更改）。

- [ ] **Step 1: 询问用户 git 授权**

向用户确认："是否 `git init` 并允许本会话内按任务提交 commit？（不会 push）"。得到肯定答复后执行 `git init`；否则跳过所有 Commit 步骤，其余照常。

- [ ] **Step 2: 创建虚拟环境并写依赖**

```powershell
cd D:\AI\stock-analysis
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

`requirements.txt`：

```
yfinance>=0.2.40
pandas>=2.0
requests>=2.31
Jinja2>=3.1
matplotlib>=3.8
PyYAML>=6.0
openai>=1.30
python-dotenv>=1.0
pytest>=8.0
```

```powershell
pip install -r requirements.txt
```

- [ ] **Step 3: 写 config.yaml（唯一参数源）**

```yaml
base_amount: 1000          # 月度基准（元）
tiers:                     # 自上而下取第一条命中
  - { min_drawdown: 30, multiplier: 2.0 }
  - { min_drawdown: 20, multiplier: 1.5 }
  - { min_drawdown: 10, multiplier: 1.25 }
default_multiplier: 1.0
rate_adjust:
  enabled: true
  high_yield: 4.5          # 10Y > 4.5% 且 3 个月上行 → ×tighten_factor
  easing_drop: 0.5         # 3 个月下行 > 0.5pp → ×easing_factor
  tighten_factor: 0.8
  easing_factor: 1.2
round_step: 0.25
cap: 2.0
alerts:
  drawdown_levels: [10, 20, 30]
  level_dedup_days: 30
  daily_drop_pct: 4.0
  daily_drop_dedup_days: 7
mail:
  smtp_host: smtp.qq.com
  smtp_port: 465
  subject_monthly: "【纳指定投】{month} 月度报告：本期 {multiplier}x（{amount} 元）"
  subject_alert: "【纳指提醒】{title}"
commentary:
  enabled: true
  provider: deepseek
  model: deepseek-chat
  base_url: https://api.deepseek.com
```

- [ ] **Step 4: .gitignore 与 pytest.ini**

`.gitignore`：

```
.venv/
__pycache__/
*.pyc
.env
out/
```

`pytest.ini`：

```ini
[pytest]
testpaths = tests
```

- [ ] **Step 5: 空包文件 + 验证**

创建空的 `src/__init__.py`、`src/datasources/__init__.py`、`tests/__init__.py`。

Run: `python -c "import yfinance, jinja2, matplotlib, yaml, openai; print('ok')"`
Expected: `ok`

- [ ] **Step 6: Commit（需已获用户授权）**

```powershell
git add -A; git commit -m "chore: scaffold project with config and dependencies"
```

---

### Task 2: 数据模型 + 规则引擎档位逻辑

**Files:**
- Create: `src/models.py`, `src/rules.py`
- Test: `tests/test_rules.py`

**Interfaces:**
- Produces:
  - `models.Signals(price: float, ath: float, ma200: float | None, vix: float | None, tnx_yield: float | None, tnx_change_3m: float | None, pe: float | None)`，属性 `drawdown_pct: float`（正数表示回撤百分比，如 23.5）
  - `models.Decision(multiplier: float, amount: int, base_multiplier: float, tier_hit: str, adjustments: list[str])`
  - `rules.compute_decision(signals: Signals, cfg: dict) -> Decision`（cfg 即 config.yaml 解析出的 dict）

- [ ] **Step 1: 写失败测试（档位边界）**

`tests/test_rules.py`：

```python
import yaml
from src.models import Signals
from src.rules import compute_decision

CFG = yaml.safe_load(open("config.yaml", encoding="utf-8"))


def sig(drawdown_pct: float, **kw) -> Signals:
    ath = 10000.0
    defaults = dict(ath=ath, price=ath * (1 - drawdown_pct / 100),
                    ma200=None, vix=None, tnx_yield=None, tnx_change_3m=None, pe=None)
    defaults.update(kw)
    return Signals(**defaults)


def test_default_tier_below_10():
    d = compute_decision(sig(9.9), CFG)
    assert d.multiplier == 1.0
    assert d.amount == 1000


def test_tier_boundary_exactly_10():
    d = compute_decision(sig(10.0), CFG)
    assert d.multiplier == 1.25
    assert d.amount == 1250


def test_tier_20():
    assert compute_decision(sig(23.0), CFG).multiplier == 1.5


def test_tier_30_is_cap():
    d = compute_decision(sig(36.0), CFG)
    assert d.multiplier == 2.0
    assert d.amount == 2000


def test_decision_records_tier_hit():
    d = compute_decision(sig(23.0), CFG)
    assert "20" in d.tier_hit
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_rules.py -v`
Expected: FAIL（`ModuleNotFoundError: src.models`）

- [ ] **Step 3: 实现 models.py 与 rules.py 档位部分**

`src/models.py`：

```python
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Signals:
    price: float
    ath: float
    ma200: float | None = None
    vix: float | None = None
    tnx_yield: float | None = None
    tnx_change_3m: float | None = None
    pe: float | None = None

    @property
    def drawdown_pct(self) -> float:
        return (self.ath - self.price) / self.ath * 100


@dataclass(frozen=True)
class Decision:
    multiplier: float
    amount: int
    base_multiplier: float
    tier_hit: str
    adjustments: list[str] = field(default_factory=list)
```

`src/rules.py`：

```python
from src.models import Signals, Decision


def _base_tier(dd: float, cfg: dict) -> tuple[float, str]:
    for tier in cfg["tiers"]:
        if dd >= tier["min_drawdown"]:
            return tier["multiplier"], f"回撤 ≥ {tier['min_drawdown']}%"
    return cfg["default_multiplier"], "回撤 < 10%（默认档）"


def compute_decision(signals: Signals, cfg: dict) -> Decision:
    base, tier_hit = _base_tier(signals.drawdown_pct, cfg)
    multiplier = base
    adjustments: list[str] = []
    amount = int(round(multiplier * cfg["base_amount"]))
    return Decision(multiplier=multiplier, amount=amount,
                    base_multiplier=base, tier_hit=tier_hit,
                    adjustments=adjustments)
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_rules.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```powershell
git add src/models.py src/rules.py tests/test_rules.py
git commit -m "feat: signals/decision models and drawdown tier rules"
```

---

### Task 3: 利率修正 + 取整 + 上限

**Files:**
- Modify: `src/rules.py`
- Test: `tests/test_rules.py`（追加）

**Interfaces:**
- Consumes/Produces: `compute_decision` 签名不变；`Decision.adjustments` 填入如 `"高利率环境 ×0.8"` 的说明文本。

- [ ] **Step 1: 追加失败测试**

追加到 `tests/test_rules.py`：

```python
def test_high_rate_tightens():
    # 回撤 23% 基础 1.5x；10Y=4.8 且 3 个月上行 → ×0.8 = 1.2 → 取整 0.25 档 → 1.25
    d = compute_decision(sig(23.0, tnx_yield=4.8, tnx_change_3m=0.3), CFG)
    assert d.multiplier == 1.25
    assert any("×0.8" in a for a in d.adjustments)


def test_easing_boosts_but_capped():
    # 回撤 36% 基础 2.0x；3 个月下行 0.8pp → ×1.2 = 2.4 → 上限 2.0
    d = compute_decision(sig(36.0, tnx_yield=3.0, tnx_change_3m=-0.8), CFG)
    assert d.multiplier == 2.0


def test_easing_boost_applies():
    # 基础 1.0x；宽松 → 1.2 → 取整 → 1.25
    d = compute_decision(sig(5.0, tnx_yield=3.0, tnx_change_3m=-0.8), CFG)
    assert d.multiplier == 1.25


def test_missing_rate_data_no_adjust():
    d = compute_decision(sig(23.0, tnx_yield=None, tnx_change_3m=None), CFG)
    assert d.multiplier == 1.5
    assert d.adjustments == []


def test_rate_adjust_can_be_disabled():
    cfg = {**CFG, "rate_adjust": {**CFG["rate_adjust"], "enabled": False}}
    d = compute_decision(sig(23.0, tnx_yield=4.8, tnx_change_3m=0.3), cfg)
    assert d.multiplier == 1.5
```

- [ ] **Step 2: 运行确认新用例失败**

Run: `python -m pytest tests/test_rules.py -v`
Expected: 前 5 个 pass，新 5 个 FAIL

- [ ] **Step 3: 实现修正逻辑**

`src/rules.py` 的 `compute_decision` 改为：

```python
def _round_step(x: float, step: float) -> float:
    return round(x / step) * step


def compute_decision(signals: Signals, cfg: dict) -> Decision:
    base, tier_hit = _base_tier(signals.drawdown_pct, cfg)
    multiplier = base
    adjustments: list[str] = []

    ra = cfg["rate_adjust"]
    if ra["enabled"] and signals.tnx_yield is not None and signals.tnx_change_3m is not None:
        if signals.tnx_yield > ra["high_yield"] and signals.tnx_change_3m > 0:
            multiplier *= ra["tighten_factor"]
            adjustments.append(f"高利率且上行（10Y={signals.tnx_yield:.2f}%）×{ra['tighten_factor']}")
        elif signals.tnx_change_3m < -ra["easing_drop"]:
            multiplier *= ra["easing_factor"]
            adjustments.append(f"利率快速下行（3个月 {signals.tnx_change_3m:+.2f}pp）×{ra['easing_factor']}")

    multiplier = min(_round_step(multiplier, cfg["round_step"]), cfg["cap"])
    amount = int(round(multiplier * cfg["base_amount"]))
    return Decision(multiplier=multiplier, amount=amount,
                    base_multiplier=base, tier_hit=tier_hit,
                    adjustments=adjustments)
```

- [ ] **Step 4: 运行确认全部通过**

Run: `python -m pytest tests/test_rules.py -v`
Expected: 10 passed

- [ ] **Step 5: Commit**

```powershell
git add src/rules.py tests/test_rules.py
git commit -m "feat: rate adjustment, rounding and cap in rules engine"
```

---

### Task 4: 行情数据源（^NDX / ^VIX）

**Files:**
- Create: `src/datasources/market.py`
- Test: `tests/test_market.py`

**Interfaces:**
- Produces:
  - `market.compute_market_metrics(closes: pandas.Series) -> dict`（纯函数）返回键：`price, ath, drawdown_pct, ma200, above_ma200(bool), daily_change_pct`
  - `market.fetch_ndx_closes(period="max") -> pandas.Series`、`market.fetch_vix() -> float | None`（网络层，薄封装）
- 测试只测纯函数，不碰网络。

- [ ] **Step 1: 写失败测试**

`tests/test_market.py`：

```python
import pandas as pd
from src.datasources.market import compute_market_metrics


def make_series(values):
    idx = pd.date_range("2024-01-01", periods=len(values), freq="B")
    return pd.Series(values, index=idx, dtype=float)


def test_drawdown_and_ath():
    closes = make_series([100, 200, 150])
    m = compute_market_metrics(closes)
    assert m["ath"] == 200
    assert m["price"] == 150
    assert abs(m["drawdown_pct"] - 25.0) < 1e-9


def test_ma200_none_when_short():
    m = compute_market_metrics(make_series([100] * 50))
    assert m["ma200"] is None


def test_ma200_and_above_flag():
    closes = make_series([100] * 200 + [150])
    m = compute_market_metrics(closes)
    assert m["ma200"] is not None
    assert m["above_ma200"] is True


def test_daily_change():
    m = compute_market_metrics(make_series([100, 96]))
    assert abs(m["daily_change_pct"] - (-4.0)) < 1e-9
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_market.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现**

`src/datasources/market.py`：

```python
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


def fetch_ndx_closes(period: str = "max") -> pd.Series:
    import yfinance as yf
    df = yf.download("^NDX", period=period, progress=False, auto_adjust=True)
    if df is None or df.empty:
        raise RuntimeError("yfinance 拉取 ^NDX 失败：返回空数据")
    close = df["Close"]
    if isinstance(close, pd.DataFrame):  # yfinance 多级列兼容
        close = close.iloc[:, 0]
    return close


def fetch_vix() -> float | None:
    import yfinance as yf
    try:
        df = yf.download("^VIX", period="5d", progress=False, auto_adjust=True)
        close = df["Close"]
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]
        return float(close.dropna().iloc[-1])
    except Exception:
        return None
```

- [ ] **Step 4: 运行确认通过 + 一次真实拉取冒烟**

Run: `python -m pytest tests/test_market.py -v` → Expected: 4 passed
Run: `python -c "from src.datasources.market import fetch_ndx_closes, compute_market_metrics; import json; print(json.dumps(compute_market_metrics(fetch_ndx_closes()), indent=2, default=str))"`
Expected: 打印真实的 price/ath/drawdown_pct（人工核对回撤数量级是否合理）

- [ ] **Step 5: Commit**

```powershell
git add src/datasources/market.py tests/test_market.py
git commit -m "feat: NDX/VIX market datasource with pure metric computation"
```

---

### Task 5: 利率数据源（FRED 主 + ^TNX 备）

**Files:**
- Create: `src/datasources/rates.py`
- Test: `tests/test_rates.py`

**Interfaces:**
- Produces: `rates.compute_rate_metrics(series: pandas.Series) -> dict`（纯函数，键：`tnx_yield, tnx_change_3m`）；`rates.fetch_10y(api_key: str | None) -> pandas.Series`（有 key 走 FRED DGS10，无 key 或失败回退 yfinance ^TNX，再失败抛 RuntimeError 由上层降级）。

- [ ] **Step 1: 写失败测试**

`tests/test_rates.py`：

```python
import pandas as pd
from src.datasources.rates import compute_rate_metrics


def test_change_3m():
    idx = pd.date_range("2026-01-01", periods=70, freq="B")
    vals = [4.0] * 63 + [4.5] * 7          # 63 个交易日前 4.0，现在 4.5
    m = compute_rate_metrics(pd.Series(vals, index=idx, dtype=float))
    assert abs(m["tnx_yield"] - 4.5) < 1e-9
    assert abs(m["tnx_change_3m"] - 0.5) < 1e-9


def test_short_series_change_none():
    idx = pd.date_range("2026-01-01", periods=10, freq="B")
    m = compute_rate_metrics(pd.Series([4.0] * 10, index=idx, dtype=float))
    assert m["tnx_yield"] == 4.0
    assert m["tnx_change_3m"] is None
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_rates.py -v` → Expected: FAIL

- [ ] **Step 3: 实现**

`src/datasources/rates.py`：

```python
import os
import pandas as pd
import requests

FRED_URL = "https://api.stlouisfed.org/fred/series/observations"
TRADING_DAYS_3M = 63


def compute_rate_metrics(series: pd.Series) -> dict:
    series = series.dropna()
    latest = float(series.iloc[-1])
    change = (float(series.iloc[-1]) - float(series.iloc[-1 - TRADING_DAYS_3M])
              if len(series) > TRADING_DAYS_3M else None)
    return {"tnx_yield": latest, "tnx_change_3m": change}


def _fetch_fred(api_key: str) -> pd.Series:
    resp = requests.get(FRED_URL, params={
        "series_id": "DGS10", "api_key": api_key,
        "file_type": "json", "observation_start": "2024-01-01",
    }, timeout=30)
    resp.raise_for_status()
    obs = [o for o in resp.json()["observations"] if o["value"] != "."]
    return pd.Series([float(o["value"]) for o in obs],
                     index=pd.to_datetime([o["date"] for o in obs]), dtype=float)


def _fetch_tnx() -> pd.Series:
    import yfinance as yf
    df = yf.download("^TNX", period="1y", progress=False, auto_adjust=True)
    close = df["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    return close.dropna()


def fetch_10y(api_key: str | None = None) -> pd.Series:
    api_key = api_key or os.environ.get("FRED_API_KEY")
    if api_key:
        try:
            return _fetch_fred(api_key)
        except Exception:
            pass
    try:
        return _fetch_tnx()
    except Exception as e:
        raise RuntimeError(f"10Y 利率数据源全部失败: {e}") from e
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_rates.py -v` → Expected: 2 passed
Run（冒烟，无 FRED key 走 ^TNX 回退）: `python -c "from src.datasources.rates import fetch_10y, compute_rate_metrics; print(compute_rate_metrics(fetch_10y()))"`
Expected: 打印当前 10Y 收益率（约 3-5 区间）

- [ ] **Step 5: Commit**

```powershell
git add src/datasources/rates.py tests/test_rates.py
git commit -m "feat: 10Y rate datasource with FRED primary and TNX fallback"
```

---

### Task 6: 信号采集编排 + 历史场景快照测试

**Files:**
- Create: `src/pipeline.py`
- Test: `tests/test_scenarios.py`

**Interfaces:**
- Produces: `pipeline.collect_signals(cfg: dict) -> tuple[Signals, list[str]]` —— 第二个返回值是"数据源警告"列表（如"VIX 缺失"）；^NDX 失败则抛 RuntimeError。
- Consumes: Task 4/5 的 fetch/compute 函数、Task 2 的 `Signals`。

- [ ] **Step 1: 写失败测试（历史场景，数值冻结为 fixture）**

`tests/test_scenarios.py`：

```python
"""用三个真实历史时点验证规则合理性（数值为当时快照，冻结不变）。"""
import yaml
from src.models import Signals
from src.rules import compute_decision

CFG = yaml.safe_load(open("config.yaml", encoding="utf-8"))


def test_2020_03_covid_crash():
    # 2020-03-23 疫情底：NDX≈6994，ATH≈9736（回撤≈28%），10Y=0.76 且 3 个月暴跌
    s = Signals(price=6994.0, ath=9736.0, tnx_yield=0.76, tnx_change_3m=-1.05)
    d = compute_decision(s, CFG)
    assert d.base_multiplier == 1.5          # 回撤 20-30% 档
    assert d.multiplier == 1.75              # 1.5 × 1.2 = 1.8 → 取整 1.75
    assert d.amount == 1750


def test_2022_12_rate_hike_bear_bottom():
    # 2022-12-28 加息熊底：NDX≈10679，ATH≈16765（回撤≈36%），10Y=3.88 高位盘整
    s = Signals(price=10679.0, ath=16765.0, tnx_yield=3.88, tnx_change_3m=0.1)
    d = compute_decision(s, CFG)
    assert d.base_multiplier == 2.0
    assert d.multiplier == 2.0               # 3.88 < 4.5 不触发收紧，维持上限
    assert d.amount == 2000


def test_2024_07_at_high():
    # 2024-07-10 历史高位附近：回撤≈0，10Y=4.28 温和回落
    s = Signals(price=20675.0, ath=20675.0, tnx_yield=4.28, tnx_change_3m=-0.1)
    d = compute_decision(s, CFG)
    assert d.multiplier == 1.0
    assert d.amount == 1000
```

- [ ] **Step 2: 运行**

Run: `python -m pytest tests/test_scenarios.py -v`
Expected: 3 passed（若失败说明规则实现与设计不符——修 rules.py 而不是改断言）

- [ ] **Step 3: 实现 pipeline.py**

```python
"""采集全部信号，辅助信号失败降级，主信号失败抛错。"""
import os
from src.models import Signals
from src.datasources import market, rates


def collect_signals(cfg: dict) -> tuple[Signals, list[str]]:
    warnings: list[str] = []

    closes = market.fetch_ndx_closes()          # 失败自然抛 RuntimeError
    m = market.compute_market_metrics(closes)

    vix = market.fetch_vix()
    if vix is None:
        warnings.append("VIX 数据缺失")

    tnx_yield = tnx_change = None
    try:
        r = rates.compute_rate_metrics(rates.fetch_10y(os.environ.get("FRED_API_KEY")))
        tnx_yield, tnx_change = r["tnx_yield"], r["tnx_change_3m"]
    except RuntimeError:
        warnings.append("10Y 利率数据缺失（利率修正未生效）")

    signals = Signals(price=m["price"], ath=m["ath"], ma200=m["ma200"],
                      vix=vix, tnx_yield=tnx_yield, tnx_change_3m=tnx_change)
    return signals, warnings
```

- [ ] **Step 4: 全量测试**

Run: `python -m pytest -v`
Expected: 全部通过（此时应有 19 个用例）

- [ ] **Step 5: Commit**

```powershell
git add src/pipeline.py tests/test_scenarios.py
git commit -m "feat: signal collection pipeline and historical scenario tests"
```

---

### Task 7: CLI 入口 + 历史存档

**Files:**
- Create: `main.py`, `src/history.py`
- Test: `tests/test_history.py`

**Interfaces:**
- Produces:
  - `history.save_monthly(record: dict, month: str, root: str = "history") -> pathlib.Path`（写 `history/YYYY-MM.json`）
  - `history.load_recent(n: int = 12, root: str = "history") -> list[dict]`（按月份倒序）
  - CLI：`python main.py --mode monthly --dry-run`（打印决策 JSON 并写 `out/report-preview.html` 于 Task 8 后）
- Consumes: `pipeline.collect_signals`、`rules.compute_decision`。

- [ ] **Step 1: 写失败测试**

`tests/test_history.py`：

```python
import json
from src.history import save_monthly, load_recent


def test_save_and_load_roundtrip(tmp_path):
    root = str(tmp_path)
    save_monthly({"multiplier": 1.5, "amount": 1500}, "2026-06", root=root)
    save_monthly({"multiplier": 1.0, "amount": 1000}, "2026-07", root=root)
    recent = load_recent(12, root=root)
    assert [r["month"] for r in recent] == ["2026-07", "2026-06"]
    assert recent[1]["amount"] == 1500


def test_save_is_valid_json(tmp_path):
    p = save_monthly({"multiplier": 2.0}, "2026-05", root=str(tmp_path))
    assert json.loads(p.read_text(encoding="utf-8"))["multiplier"] == 2.0
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_history.py -v` → Expected: FAIL

- [ ] **Step 3: 实现 history.py**

```python
import json
from pathlib import Path


def save_monthly(record: dict, month: str, root: str = "history") -> Path:
    d = Path(root)
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{month}.json"
    p.write_text(json.dumps({**record, "month": month}, ensure_ascii=False, indent=2),
                 encoding="utf-8")
    return p


def load_recent(n: int = 12, root: str = "history") -> list[dict]:
    d = Path(root)
    if not d.exists():
        return []
    files = sorted(d.glob("????-??.json"), reverse=True)[:n]
    return [json.loads(p.read_text(encoding="utf-8")) for p in files]
```

- [ ] **Step 4: 实现 main.py（monthly dry-run 骨架）**

```python
import argparse
import dataclasses
import json
import os
from datetime import date

import yaml
from dotenv import load_dotenv

from src import history
from src.pipeline import collect_signals
from src.rules import compute_decision


def load_config() -> dict:
    with open("config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_monthly(cfg: dict, dry_run: bool) -> dict:
    signals, warnings = collect_signals(cfg)
    decision = compute_decision(signals, cfg)
    month = date.today().strftime("%Y-%m")
    record = {
        "signals": {**dataclasses.asdict(signals), "drawdown_pct": signals.drawdown_pct},
        "decision": dataclasses.asdict(decision),
        "warnings": warnings,
    }
    print(json.dumps(record, ensure_ascii=False, indent=2))
    if not dry_run:
        history.save_monthly(record, month)
    return record


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="纳指定投监控系统")
    parser.add_argument("--mode", choices=["monthly", "daily"], required=True)
    parser.add_argument("--dry-run", action="store_true", help="不发邮件不写历史")
    args = parser.parse_args()
    cfg = load_config()
    if args.mode == "monthly":
        run_monthly(cfg, args.dry_run)
    else:
        raise SystemExit("daily 模式在 Task 11 实现")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: 端到端 dry-run 冒烟**

Run: `python -m pytest -v` → Expected: 全部通过
Run: `python main.py --mode monthly --dry-run`
Expected: 打印含真实回撤与倍数的 JSON，`history/` 无新文件

- [ ] **Step 6: Commit**

```powershell
git add main.py src/history.py tests/test_history.py
git commit -m "feat: CLI entry with monthly dry-run and history persistence"
```

**✅ P1 里程碑：本地跑 `--dry-run` 输出正确倍数，测试全绿。**

---

### Task 8: HTML 报告渲染

**Files:**
- Create: `src/report.py`, `templates/report.html.j2`
- Modify: `main.py`（dry-run 时把报告写到 `out/report-preview.html`）
- Test: `tests/test_report.py`

**Interfaces:**
- Produces: `report.render_monthly(record: dict, recent: list[dict], charts: dict[str, str], commentary: str | None) -> str`（返回完整 HTML 字符串）；`report.sparkline_b64(series: pandas.Series, title: str) -> str`（返回 `data:image/png;base64,...`）。
- `charts` 键约定：`ndx`（近一年走势）、`tnx`（近一年利率）。缺失的键模板中跳过。

- [ ] **Step 1: 写失败测试**

`tests/test_report.py`：

```python
import pandas as pd
from src.report import render_monthly, sparkline_b64

RECORD = {
    "month": "2026-07",
    "signals": {"price": 20000.0, "ath": 23000.0, "drawdown_pct": 13.04,
                "ma200": 19500.0, "vix": 18.5, "tnx_yield": 4.1, "tnx_change_3m": -0.2,
                "pe": None},
    "decision": {"multiplier": 1.25, "amount": 1250, "base_multiplier": 1.25,
                 "tier_hit": "回撤 ≥ 10%", "adjustments": []},
    "warnings": ["PE 数据缺失"],
}


def test_render_contains_conclusion_and_warning():
    html = render_monthly(RECORD, recent=[], charts={}, commentary=None)
    assert "1.25x" in html and "1250" in html
    assert "回撤 ≥ 10%" in html
    assert "PE 数据缺失" in html


def test_render_with_commentary_and_history():
    html = render_monthly(RECORD, recent=[{"month": "2026-06",
                          "decision": {"multiplier": 1.0, "amount": 1000}}],
                          charts={}, commentary="宏观点评正文")
    assert "宏观点评正文" in html and "2026-06" in html


def test_sparkline_is_data_uri():
    s = pd.Series(range(50), index=pd.date_range("2026-01-01", periods=50))
    assert sparkline_b64(s, "NDX").startswith("data:image/png;base64,")
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_report.py -v` → Expected: FAIL

- [ ] **Step 3: 实现 report.py**

```python
import base64
import io

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape

_env = Environment(loader=FileSystemLoader("templates"),
                   autoescape=select_autoescape(["html"]))


def sparkline_b64(series: pd.Series, title: str) -> str:
    fig, ax = plt.subplots(figsize=(4.6, 1.4), dpi=110)
    ax.plot(series.index, series.values, linewidth=1.4, color="#2563eb")
    ax.set_title(title, fontsize=8, loc="left")
    ax.tick_params(labelsize=6)
    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)
    fig.tight_layout(pad=0.4)
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def render_monthly(record: dict, recent: list[dict],
                   charts: dict[str, str], commentary: str | None) -> str:
    tpl = _env.get_template("report.html.j2")
    return tpl.render(r=record, recent=recent, charts=charts, commentary=commentary)
```

- [ ] **Step 4: 写模板 templates/report.html.j2**

```html
<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<style>
  body{font-family:"Microsoft YaHei",sans-serif;max-width:640px;margin:0 auto;
       padding:16px;color:#1f2329;line-height:1.7}
  .hero{background:#eff6ff;border:1px solid #bfdbfe;border-radius:10px;
        padding:18px 22px;margin-bottom:18px}
  .hero .mult{font-size:30px;font-weight:700;color:#2563eb}
  table{width:100%;border-collapse:collapse;font-size:14px;margin:10px 0}
  th,td{border:1px solid #e5e7eb;padding:6px 10px;text-align:left}
  th{background:#f8fafc}
  .warn{background:#fffbeb;border:1px solid #fde68a;border-radius:8px;
        padding:8px 14px;font-size:13px;margin:10px 0}
  .muted{color:#6b7280;font-size:12px}
  h3{margin:18px 0 6px;font-size:15px}
  img{max-width:100%}
</style></head><body>

<div class="hero">
  <div>{{ r.month }} 定投建议</div>
  <div class="mult">{{ r.decision.multiplier }}x —— {{ r.decision.amount }} 元</div>
  <div>{{ r.decision.tier_hit }}{% for a in r.decision.adjustments %}；{{ a }}{% endfor %}</div>
</div>

{% if r.warnings %}<div class="warn">⚠️ {{ r.warnings | join("；") }}</div>{% endif %}

{# 设计 §4：环境偏热提示（不改变倍数，仅提示） #}
{% if r.signals.vix is not none and r.signals.vix < 13
      and r.signals.drawdown_pct < 1
      and r.signals.tnx_change_3m is not none and r.signals.tnx_change_3m > 0 %}
<div class="warn">🌡️ 环境偏热：VIX 极低 + 指数新高 + 利率上行同时出现，可考虑本期只投基准、不加码（倍数建议仍以上方规则为准）</div>
{% endif %}

<h3>信号面板</h3>
<table>
  <tr><th>指标</th><th>数值</th></tr>
  <tr><td>纳指100 收盘</td><td>{{ "%.0f" | format(r.signals.price) }}（距高点 -{{ "%.1f" | format(r.signals.drawdown_pct) }}%）</td></tr>
  <tr><td>200 日均线</td><td>{{ "%.0f" | format(r.signals.ma200) if r.signals.ma200 else "数据不足" }}</td></tr>
  <tr><td>10Y 美债</td><td>{{ "%.2f%%" | format(r.signals.tnx_yield) if r.signals.tnx_yield is not none else "缺失" }}
      {% if r.signals.tnx_change_3m is not none %}（3个月 {{ "%+.2f" | format(r.signals.tnx_change_3m) }}pp）{% endif %}</td></tr>
  <tr><td>VIX</td><td>{{ "%.1f" | format(r.signals.vix) if r.signals.vix is not none else "缺失" }}</td></tr>
  <tr><td>QQQ PE</td><td>{{ "%.1f" | format(r.signals.pe) if r.signals.pe is not none else "缺失（辅助信号）" }}</td></tr>
</table>

{% for key, uri in charts.items() %}<img src="{{ uri }}" alt="{{ key }}">{% endfor %}

{% if commentary %}
<h3>AI 宏观点评</h3>
<p>{{ commentary }}</p>
<p class="muted">以上为 AI 生成的参考信息，不构成规则输出，倍数建议只由规则引擎决定。</p>
{% endif %}

{% if recent %}
<h3>历史记录（近 12 期）</h3>
<table><tr><th>月份</th><th>倍数</th><th>金额</th></tr>
{% for h in recent %}<tr><td>{{ h.month }}</td><td>{{ h.decision.multiplier }}x</td><td>{{ h.decision.amount }} 元</td></tr>{% endfor %}
</table>
{% endif %}

<p class="muted">规则引擎自动生成 · 标的无关（可执行于 513100 / QQQ 碎股 / 3086.HK）</p>
</body></html>
```

- [ ] **Step 5: 接入 main.py dry-run 预览**

`main.py` 的 `run_monthly` 在 `print` 之后追加：

```python
    from src.report import render_monthly, sparkline_b64
    from src.datasources.market import fetch_ndx_closes
    from pathlib import Path

    charts = {}
    try:
        charts["ndx"] = sparkline_b64(fetch_ndx_closes(period="1y"), "纳指100 近一年")
    except Exception:
        pass
    html = render_monthly({**record, "month": month},
                          history.load_recent(12), charts, commentary=None)
    if dry_run:
        Path("out").mkdir(exist_ok=True)
        Path("out/report-preview.html").write_text(html, encoding="utf-8")
        print("预览已写入 out/report-preview.html")
    record["_html"] = html
```

- [ ] **Step 6: 测试 + 人工看预览**

Run: `python -m pytest -v` → Expected: 全部通过
Run: `python main.py --mode monthly --dry-run`，浏览器打开 `out/report-preview.html`
Expected: 结论区大字倍数、信号表、纳指走势图齐全

- [ ] **Step 7: Commit**

```powershell
git add src/report.py templates/ tests/test_report.py main.py
git commit -m "feat: HTML monthly report rendering with sparkline charts"
```

---

### Task 9: 邮件推送

**Files:**
- Create: `src/notify.py`
- Modify: `main.py`（非 dry-run 时发送）

**Interfaces:**
- Produces: `notify.send_html(subject: str, html: str, cfg: dict) -> None`——从环境变量读 `SMTP_USER`（发件 QQ 邮箱）、`SMTP_PASS`（授权码）、`MAIL_TO`（收件人，缺省同发件人）；缺任一凭据抛 `RuntimeError`。
- 无单测（纯 IO 薄层），用手动冒烟验收。

- [ ] **Step 1: 实现 notify.py**

```python
import os
import smtplib
from email.mime.text import MIMEText
from email.header import Header


def send_html(subject: str, html: str, cfg: dict) -> None:
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASS")
    to = os.environ.get("MAIL_TO", user)
    if not user or not password:
        raise RuntimeError("缺少 SMTP_USER / SMTP_PASS 环境变量")

    msg = MIMEText(html, "html", "utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = user
    msg["To"] = to

    mail_cfg = cfg["mail"]
    with smtplib.SMTP_SSL(mail_cfg["smtp_host"], mail_cfg["smtp_port"], timeout=30) as s:
        s.login(user, password)
        s.sendmail(user, [to], msg.as_string())
```

- [ ] **Step 2: 接入 main.py**

`run_monthly` 末尾（dry_run 为 False 分支）追加：

```python
    if not dry_run:
        from src.notify import send_html
        subject = cfg["mail"]["subject_monthly"].format(
            month=month, multiplier=record["decision"]["multiplier"],
            amount=record["decision"]["amount"])
        send_html(subject, html, cfg)
        print(f"报告已发送：{subject}")
```

- [ ] **Step 3: 手动冒烟（需用户提供 QQ 邮箱授权码）**

本地建 `.env`（已在 .gitignore）：

```
SMTP_USER=xxx@qq.com
SMTP_PASS=<QQ邮箱SMTP授权码>
MAIL_TO=xxx@qq.com
```

Run: `python main.py --mode monthly`
Expected: 终端打印"报告已发送"，用户邮箱收到 HTML 报告，`history/2026-XX.json` 生成

- [ ] **Step 4: Commit**

```powershell
git add src/notify.py main.py
git commit -m "feat: QQ SMTP email delivery for monthly report"
```

---

### Task 10: GitHub Actions 月度工作流

**Files:**
- Create: `.github/workflows/monthly-report.yml`

**Interfaces:**
- Consumes: `python main.py --mode monthly`；Secrets：`SMTP_USER, SMTP_PASS, MAIL_TO, FRED_API_KEY, DEEPSEEK_API_KEY`。
- 注意：工作流内的 commit 是 Actions 机器人在**远端仓库**提交 history 文件，不适用"本地不擅自 commit"规则（设计文档 §7 已批准该机制）。

- [ ] **Step 1: 写工作流**

```yaml
name: monthly-report
on:
  schedule:
    - cron: "30 22 1 * *"     # 每月 1 日 22:30 UTC ≈ 美东盘后（月度报告对时效不敏感）
  workflow_dispatch: {}

permissions:
  contents: write

jobs:
  report:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
      - run: pip install -r requirements.txt
      - name: Run monthly report
        env:
          SMTP_USER: ${{ secrets.SMTP_USER }}
          SMTP_PASS: ${{ secrets.SMTP_PASS }}
          MAIL_TO: ${{ secrets.MAIL_TO }}
          FRED_API_KEY: ${{ secrets.FRED_API_KEY }}
          DEEPSEEK_API_KEY: ${{ secrets.DEEPSEEK_API_KEY }}
        run: python main.py --mode monthly
      - name: Commit history
        run: |
          git config user.name "dca-bot"
          git config user.email "actions@github.com"
          git add history/
          git diff --cached --quiet || git commit -m "chore: record $(date +%Y-%m) decision"
          git push
```

- [ ] **Step 2: 用户操作项（执行者引导，不代办）**

引导用户完成：① GitHub 建**私有**仓库并推送代码（push 由用户执行）；② 仓库 Settings → Secrets and variables → Actions 添加上述 5 个 secrets；③ Actions 页手动触发 `monthly-report` 一次。

Expected: Actions 全绿，邮箱收到报告，仓库出现 bot 提交的 `history/2026-XX.json`

- [ ] **Step 3: Commit（本地）**

```powershell
git add .github/workflows/monthly-report.yml
git commit -m "ci: monthly report workflow with history commit-back"
```

**✅ P2 里程碑：手动触发 Actions，邮箱收到完整报告。**

---

### Task 11: 每日触发检查 + 去重

**Files:**
- Create: `src/alerts.py`, `.github/workflows/daily-check.yml`
- Modify: `main.py`（实现 daily 分支）
- Test: `tests/test_alerts.py`

**Interfaces:**
- Produces:
  - `alerts.check(metrics: dict, state: dict, cfg: dict, today: datetime.date) -> tuple[list[str], dict]`（纯函数）——输入 Task 4 的 `compute_market_metrics` 结果与上次状态，返回（本次要发的提醒标题列表, 新状态）。
  - 状态文件 `history/alerts_state.json` 结构：`{"levels": {"10": "2026-07-01"}, "daily_drop": "2026-07-03"}`（值为上次提醒日期 ISO 字符串）。
- Consumes: `market.compute_market_metrics`、`notify.send_html`。

- [ ] **Step 1: 写失败测试**

`tests/test_alerts.py`：

```python
import yaml
from datetime import date
from src.alerts import check

CFG = yaml.safe_load(open("config.yaml", encoding="utf-8"))
TODAY = date(2026, 7, 5)


def metrics(dd, daily=0.0):
    return {"drawdown_pct": dd, "daily_change_pct": daily}


def test_crossing_level_alerts():
    msgs, state = check(metrics(21.0), {}, CFG, TODAY)
    assert any("20%" in m for m in msgs)
    assert state["levels"]["20"] == "2026-07-05"
    assert "10" in state["levels"]          # 一次跌穿两档都记录


def test_dedup_within_30_days():
    state = {"levels": {"20": "2026-06-20", "10": "2026-06-20"}}
    msgs, _ = check(metrics(22.0), state, CFG, TODAY)
    assert msgs == []


def test_realert_after_30_days():
    state = {"levels": {"20": "2026-05-01", "10": "2026-05-01"}}
    msgs, _ = check(metrics(22.0), state, CFG, TODAY)
    assert len(msgs) == 1


def test_daily_big_drop():
    msgs, state = check(metrics(5.0, daily=-4.5), {}, CFG, TODAY)
    assert any("单日" in m for m in msgs)
    assert state["daily_drop"] == "2026-07-05"


def test_daily_drop_dedup_7_days():
    state = {"daily_drop": "2026-07-01"}
    msgs, _ = check(metrics(5.0, daily=-4.5), state, CFG, TODAY)
    assert msgs == []


def test_no_alert_quiet_market():
    msgs, _ = check(metrics(5.0, daily=-0.5), {}, CFG, TODAY)
    assert msgs == []
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_alerts.py -v` → Expected: FAIL

- [ ] **Step 3: 实现 alerts.py**

```python
from datetime import date, timedelta


def _stale(last_iso: str | None, days: int, today: date) -> bool:
    if not last_iso:
        return True
    return (today - date.fromisoformat(last_iso)) >= timedelta(days=days)


def check(metrics: dict, state: dict, cfg: dict, today: date) -> tuple[list[str], dict]:
    a = cfg["alerts"]
    msgs: list[str] = []
    new_state = {"levels": dict(state.get("levels", {})),
                 "daily_drop": state.get("daily_drop")}

    dd = metrics["drawdown_pct"]
    for level in sorted(a["drawdown_levels"], reverse=True):
        if dd >= level:
            key = str(level)
            if _stale(new_state["levels"].get(key), a["level_dedup_days"], today):
                msgs.append(f"纳指回撤达 -{level}% 档（当前 -{dd:.1f}%），进入对应加仓区")
            # 覆盖式记录：更深档位触发时同时刷新浅档位，避免回撤缓慢加深时重复提醒
            for shallower in a["drawdown_levels"]:
                if shallower <= level:
                    new_state["levels"][str(shallower)] = today.isoformat()
            break

    if metrics["daily_change_pct"] <= -a["daily_drop_pct"]:
        if _stale(new_state["daily_drop"], a["daily_drop_dedup_days"], today):
            msgs.append(f"纳指单日 {metrics['daily_change_pct']:.1f}%，大幅波动")
            new_state["daily_drop"] = today.isoformat()

    return msgs, new_state
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_alerts.py -v` → Expected: 6 passed

- [ ] **Step 5: main.py 实现 daily 分支**

替换 `main.py` 中 `raise SystemExit("daily 模式在 Task 11 实现")` 为 `run_daily(cfg, args.dry_run)`，并新增：

```python
def run_daily(cfg: dict, dry_run: bool) -> None:
    import json
    from datetime import date as _date
    from pathlib import Path
    from src.alerts import check
    from src.datasources.market import fetch_ndx_closes, compute_market_metrics

    metrics = compute_market_metrics(fetch_ndx_closes())
    state_path = Path("history/alerts_state.json")
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    msgs, new_state = check(metrics, state, cfg, _date.today())

    if not msgs:
        print("无触发，静默退出")
        return
    body = "<br>".join(msgs) + f"<p>当前回撤 -{metrics['drawdown_pct']:.1f}%，收盘 {metrics['price']:.0f}</p>"
    print("\n".join(msgs))
    if not dry_run:
        from src.notify import send_html
        send_html(cfg["mail"]["subject_alert"].format(title=msgs[0]), body, cfg)
        state_path.parent.mkdir(exist_ok=True)
        state_path.write_text(json.dumps(new_state, ensure_ascii=False, indent=2),
                              encoding="utf-8")
```

- [ ] **Step 6: 写 daily-check.yml**

```yaml
name: daily-check
on:
  schedule:
    - cron: "0 22 * * 2-6"    # 美股收盘（美东 16-17 点）后，UTC 周二至周六
  workflow_dispatch: {}

permissions:
  contents: write

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
      - run: pip install -r requirements.txt
      - name: Run daily check
        env:
          SMTP_USER: ${{ secrets.SMTP_USER }}
          SMTP_PASS: ${{ secrets.SMTP_PASS }}
          MAIL_TO: ${{ secrets.MAIL_TO }}
        run: python main.py --mode daily
      - name: Commit alert state
        run: |
          git config user.name "dca-bot"
          git config user.email "actions@github.com"
          git add history/alerts_state.json
          git diff --cached --quiet || git commit -m "chore: update alert state"
          git push
```

- [ ] **Step 7: 冒烟 + 全量测试**

Run: `python -m pytest -v` → Expected: 全部通过
Run: `python main.py --mode daily --dry-run`
Expected: 当前市况下大概率打印"无触发，静默退出"

- [ ] **Step 8: Commit**

```powershell
git add src/alerts.py tests/test_alerts.py main.py .github/workflows/daily-check.yml
git commit -m "feat: daily drawdown alerts with dedup and workflow"
```

**✅ P3 里程碑：触发判定有测试覆盖，静默/提醒/去重三态行为正确。**

---

### Task 12: DeepSeek AI 点评

**Files:**
- Create: `src/commentary.py`
- Modify: `main.py`（monthly 流程接入，失败降级）

**Interfaces:**
- Produces: `commentary.generate(record: dict, cfg: dict) -> str | None`——环境变量 `DEEPSEEK_API_KEY` 缺失、`commentary.enabled` 为 false、或调用异常时一律返回 `None`（上层把 None 渲染为无点评区块）。

- [ ] **Step 1: 实现 commentary.py**

```python
import os


PROMPT = """你是一名宏观分析助手。以下是本月纳指定投系统采集的信号（JSON）：
{signals}

请用 300 字以内的中文，解释当前市场环境（估值、利率、波动率各处于什么状态、\
近期为什么会这样）。只做解释和背景说明，禁止给出任何买卖、加仓、减仓建议，\
禁止评价定投倍数是否合理。"""


def generate(record: dict, cfg: dict) -> str | None:
    c = cfg["commentary"]
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not c["enabled"] or not api_key:
        return None
    try:
        import json
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url=c["base_url"])
        resp = client.chat.completions.create(
            model=c["model"],
            messages=[{"role": "user", "content": PROMPT.format(
                signals=json.dumps(record["signals"], ensure_ascii=False))}],
            max_tokens=600, temperature=0.3, timeout=60,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"AI 点评生成失败（已降级）：{e}")
        return None
```

- [ ] **Step 2: 接入 main.py**

`run_monthly` 中渲染报告一行改为：

```python
    from src.commentary import generate
    commentary = generate(record, cfg)
    html = render_monthly({**record, "month": month},
                          history.load_recent(12), charts, commentary=commentary)
```

- [ ] **Step 3: 冒烟（需用户 DeepSeek key 在 .env：`DEEPSEEK_API_KEY=sk-...`）**

Run: `python main.py --mode monthly --dry-run`
Expected: `out/report-preview.html` 出现"AI 宏观点评"区块；把 `.env` 中 key 临时改错重跑，报告照常生成、点评区消失（验证降级）

- [ ] **Step 4: Commit**

```powershell
git add src/commentary.py main.py
git commit -m "feat: DeepSeek macro commentary with graceful degradation"
```

---

### Task 13: PE 估值信号（尽力而为）

**Files:**
- Create: `src/datasources/valuation.py`
- Modify: `src/pipeline.py`（采集 PE，失败加 warning）

**Interfaces:**
- Produces: `valuation.fetch_qqq_pe() -> float | None`（任何异常返回 None，永不抛错）。
- Consumes: `Signals.pe` 字段（Task 2 已定义），报告模板已支持缺失展示（Task 8）。

- [ ] **Step 1: 实现 valuation.py**

```python
def fetch_qqq_pe() -> float | None:
    try:
        import yfinance as yf
        pe = yf.Ticker("QQQ").info.get("trailingPE")
        return float(pe) if pe and 5 < float(pe) < 100 else None   # 合理性护栏
    except Exception:
        return None
```

- [ ] **Step 2: 接入 pipeline.py**

`collect_signals` 中构造 `Signals` 前追加：

```python
    from src.datasources.valuation import fetch_qqq_pe
    pe = fetch_qqq_pe()
    if pe is None:
        warnings.append("QQQ PE 数据缺失（估值为辅助信号，不影响倍数）")
```

并在 `Signals(...)` 调用中加入 `pe=pe`。

- [ ] **Step 3: 全量回归 + 端到端验收**

Run: `python -m pytest -v` → Expected: 全部通过
Run: `python main.py --mode monthly --dry-run` → 报告 PE 行显示数值或"缺失（辅助信号）"

- [ ] **Step 4: Commit**

```powershell
git add src/datasources/valuation.py src/pipeline.py
git commit -m "feat: best-effort QQQ PE valuation signal"
```

**✅ P4 里程碑（全部完成）：AI 点评可降级、利率修正生效、PE 尽力展示。最终由用户在 GitHub 手动触发一次 monthly 工作流做上线验收。**
