import net_timeout, requests
assert net_timeout.install()
seen = {}
def fake(self, method, url, **kw):
    seen.update(kw); raise RuntimeError("stop")
orig = requests.sessions.Session.request._orig
requests.sessions.Session.request._orig  # exists
# 替换底层：重新包一层
net_timeout._done = False
requests.sessions.Session.request = orig
requests.sessions.Session.request = fake
net_timeout.install()
for kw, exp in (({}, net_timeout.DEFAULT), ({"timeout": None}, net_timeout.DEFAULT), ({"timeout": 3}, 3)):
    seen.clear()
    try: requests.get("http://x.invalid", **kw)
    except RuntimeError: pass
    assert seen["timeout"] == exp, (kw, seen)
print("net_timeout OK")
