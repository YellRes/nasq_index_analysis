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
