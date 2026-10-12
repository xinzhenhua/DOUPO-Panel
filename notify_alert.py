# -*- coding: utf-8 -*-
"""交易提醒发送(v101.31)：读 scripts/plan_alert.js 的输出，把「新出现」的事件发到你配置的渠道，并在 data/alert_state.json 里记账防重复。
渠道（哪个配了 Secrets 就发哪个，可同时多个）：
  GitHub Issue   不用配任何密钥：在本仓库开一个 Issue 并 @你，GitHub 会给你发邮件（和 GitHub 手机 App 推送）。ALERT_ISSUE=0 可关
  Server酱       SERVERCHAN_KEY（sct.ftqq.com 的 SendKey）→ 推到微信
  PushPlus       PUSHPLUS_TOKEN（pushplus.plus 的 token）→ 推到微信
  邮件(SMTP)     SMTP_HOST / SMTP_PORT(默认465) / SMTP_USER / SMTP_PASS / SMTP_TO(默认=SMTP_USER)
防重复规则：
  入场信号 —— 只在「信号从无变有、或方向变了」时发一次；信号一直持续不重复发，信号消失后再出现会再发
  离场/数据不足 —— 同一个 key（价格日+持仓+动作）只发一次；持仓没在仓库里平掉，第二天价格日变了会再提醒一次（催你记录持仓）
  事件对应的价格日超过 3 天前不发（刚配好密钥时不会补发旧事件）
网络层全部可注入（send 函数），测试用假的；发送失败不记账，下一小时再试。"""
import json, os, sys, urllib.request, urllib.parse, smtplib, datetime
from email.mime.text import MIMEText

STATE_KEEP = 60


def _post(url, data=None, js=None, headers=None, timeout=20):
    h = dict(headers or {})
    if js is not None:
        body = json.dumps(js).encode("utf-8"); h.setdefault("Content-Type", "application/json")
    elif data is not None:
        body = urllib.parse.urlencode(data).encode("utf-8")
    else:
        body = b""
    req = urllib.request.Request(url, data=body, headers=h, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read().decode("utf-8", "replace")


def send_issue(env, title, body, post=_post):
    repo, tok = env.get("GITHUB_REPOSITORY"), env.get("GITHUB_TOKEN")
    if not (repo and tok) or env.get("ALERT_ISSUE", "1") == "0":
        return None
    owner = env.get("GITHUB_REPOSITORY_OWNER") or repo.split("/")[0]
    st, _ = post(f"https://api.github.com/repos/{repo}/issues", js={"title": title, "body": f"@{owner}\n\n{body}", "labels": ["提醒"]},
                 headers={"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})
    return 200 <= st < 300


def send_serverchan(env, title, body, post=_post):
    k = env.get("SERVERCHAN_KEY")
    if not k:
        return None
    st, txt = post(f"https://sctapi.ftqq.com/{k}.send", data={"title": title[:100], "desp": body})
    return 200 <= st < 300 and '"code":0' in txt.replace(" ", "")


def send_pushplus(env, title, body, post=_post):
    t = env.get("PUSHPLUS_TOKEN")
    if not t:
        return None
    st, txt = post("http://www.pushplus.plus/send", js={"token": t, "title": title[:100], "content": body.replace("\n", "<br>"), "template": "html"})
    return 200 <= st < 300 and '"code":200' in txt.replace(" ", "")


def send_smtp(env, title, body, smtp=smtplib.SMTP_SSL):
    host, user, pw = env.get("SMTP_HOST"), env.get("SMTP_USER"), env.get("SMTP_PASS")
    if not (host and user and pw):
        return None
    m = MIMEText(body, "plain", "utf-8"); m["Subject"] = title; m["From"] = user; m["To"] = env.get("SMTP_TO") or user
    with smtp(host, int(env.get("SMTP_PORT") or 465), timeout=20) as s:
        s.login(user, pw); s.sendmail(user, [m["To"]], m.as_string())
    return True


CHANNELS = {"issue": send_issue, "serverchan": send_serverchan, "pushplus": send_pushplus, "smtp": send_smtp}


def select_events(alert, state, today):
    """返回 (要发的事件, 新状态)。state = {sent:[key...], lastSide:int|None, lastSideDate}"""
    state = dict(state or {}); sent = list(state.get("sent") or [])
    out, pd = [], alert.get("priceDate")
    def fresh(d):
        try:
            return (datetime.date.fromisoformat(today) - datetime.date.fromisoformat(d)).days <= 3
        except Exception:  # noqa: BLE001
            return False
    new_side = alert.get("side") or 0
    for e in alert.get("events") or []:
        if e["key"] in sent:
            continue
        if e["type"] == "entry":
            if state.get("lastSide") == e.get("side"):
                continue               # 信号还是同一个，已经发过（lastSide 只在发送成功后更新）
            if not fresh(pd or ""):
                continue
        elif e["type"] == "exit" and not fresh(pd or ""):
            continue
        out.append(e)
    return out, state, new_side


def run(alert, state, env, today, senders=None):
    """发送并返回新状态与报告。senders 可注入 {名字: fn(env,title,body)->True/False/None}。"""
    senders = senders or CHANNELS
    events, st, new_side = select_events(alert, state, today)
    report = {"sent": [], "failed": [], "skipped": 0, "channels": []}
    sent = list(st.get("sent") or [])
    for e in events:
        oks = []
        for name, fn in senders.items():
            try:
                r = fn(env, e["title"], e["body"])
            except Exception as ex:  # noqa: BLE001
                r = False; report["failed"].append(f"{name}: {type(ex).__name__}: {str(ex)[:100]}")
            if r is None:
                continue
            if name not in report["channels"]:
                report["channels"].append(name)
            oks.append(bool(r))
            if not r:
                report["failed"].append(f"{name} 发送失败：{e['key']}")
        if oks and any(oks):
            sent.append(e["key"]); report["sent"].append(e["key"])
            if e["type"] == "entry":
                st["lastSide"] = e.get("side")
        else:
            report["skipped"] += 1
    # 信号消失(价格日有效且数据可用)后复位，下次再出现会再发
    if alert.get("gate", {}).get("ok") and new_side == 0:
        st["lastSide"] = 0
    st["sent"] = sent[-STATE_KEEP:]; st["updated"] = today
    return st, report


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument("--alert", required=True); ap.add_argument("--state", default="data/alert_state.json"); ap.add_argument("--today", default="")
    a = ap.parse_args(argv)
    alert = json.load(open(a.alert, encoding="utf-8"))
    try:
        state = json.load(open(a.state, encoding="utf-8"))
    except Exception:  # noqa: BLE001
        state = {}
    today = a.today or (datetime.datetime.utcnow() + datetime.timedelta(hours=8)).date().isoformat()
    st, rep = run(alert, state, dict(os.environ), today)
    os.makedirs(os.path.dirname(os.path.abspath(a.state)), exist_ok=True)
    with open(a.state, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)
    print("[提醒发送]", json.dumps(rep, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
