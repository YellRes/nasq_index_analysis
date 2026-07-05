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
