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
