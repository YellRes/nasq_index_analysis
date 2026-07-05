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
