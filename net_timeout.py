# -*- coding: utf-8 -*-
"""给 requests 补默认超时（v101.56）。
akshare 内部调用 requests.get/post 时不传 timeout（等价 None=永不超时），
`socket.setdefaulttimeout` 对它无效 → 某个源挂住会一直卡到 Actions 超时。
这里把 Session.request 包一层：调用方没传 timeout（或为 None）时补 (10, 30) 秒。"""
DEFAULT = (10, 30)
_done = False


def install(default=DEFAULT):
    global _done
    if _done:
        return True
    try:
        import requests
    except Exception:
        return False
    orig = requests.sessions.Session.request

    def request(self, method, url, **kw):
        if kw.get("timeout") is None:
            kw["timeout"] = default
        return orig(self, method, url, **kw)

    request._orig = orig
    requests.sessions.Session.request = request
    _done = True
    return True
