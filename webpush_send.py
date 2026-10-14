# -*- coding: utf-8 -*-
"""网页推送发送端（v101.50）：只依赖 cryptography（不用 pywebpush），实现 RFC 8291(aes128gcm) 加密 + RFC 8292(VAPID, ES256)。
浏览器在设置里「开启本设备推送」后，订阅信息登记在 data/push_subs.json；notify_alert.py 发提醒时对每个订阅发一条。
VAPID 私钥放 GitHub Secrets 的 VAPID_PRIVATE_KEY（在页面设置里点「生成推送密钥」得到，base64url 的 32 字节）。
网络层可注入（post），测试用假的；加解密在测试里用订阅方私钥解一遍验证。"""
import base64, json, os, time, urllib.parse, urllib.request, urllib.error

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


def b64u(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def b64d(s):
    s = str(s).strip(); return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _pub_raw(pub):
    return pub.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)


def gen_vapid():
    """生成一对 VAPID 密钥：返回 (私钥base64url 32字节, 公钥base64url 65字节)。"""
    k = ec.generate_private_key(ec.SECP256R1())
    return b64u(k.private_numbers().private_value.to_bytes(32, "big")), b64u(_pub_raw(k.public_key()))


def vapid_private(priv_b64):
    return ec.derive_private_key(int.from_bytes(b64d(priv_b64), "big"), ec.SECP256R1())


def vapid_public_b64(priv_b64):
    return b64u(_pub_raw(vapid_private(priv_b64).public_key()))


def vapid_auth(endpoint, priv_b64, subject, now=None):
    u = urllib.parse.urlparse(endpoint); aud = f"{u.scheme}://{u.netloc}"
    h = b64u(json.dumps({"typ": "JWT", "alg": "ES256"}, separators=(",", ":")).encode())
    c = b64u(json.dumps({"aud": aud, "exp": int(now or time.time()) + 12 * 3600, "sub": subject}, separators=(",", ":")).encode())
    der = vapid_private(priv_b64).sign(f"{h}.{c}".encode(), ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    return f"vapid t={h}.{c}.{b64u(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}, k={vapid_public_b64(priv_b64)}"


def encrypt(payload, p256dh, auth, salt=None, eph=None):
    """aes128gcm 加密（单记录）。返回完整请求体。"""
    ua_pub = b64d(p256dh); auth_s = b64d(auth)
    eph = eph or ec.generate_private_key(ec.SECP256R1()); as_pub = _pub_raw(eph.public_key())
    shared = eph.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_pub))
    ikm = HKDF(algorithm=hashes.SHA256(), length=32, salt=auth_s, info=b"WebPush: info\x00" + ua_pub + as_pub).derive(shared)
    salt = salt or os.urandom(16)
    cek = HKDF(algorithm=hashes.SHA256(), length=16, salt=salt, info=b"Content-Encoding: aes128gcm\x00").derive(ikm)
    nonce = HKDF(algorithm=hashes.SHA256(), length=12, salt=salt, info=b"Content-Encoding: nonce\x00").derive(ikm)
    ct = AESGCM(cek).encrypt(nonce, payload + b"\x02", None)
    return salt + (4096).to_bytes(4, "big") + bytes([len(as_pub)]) + as_pub + ct


def decrypt(body, ua_priv, auth):
    """订阅方解密（测试用）：ua_priv 是订阅方的 EC 私钥对象。"""
    salt, idlen = body[:16], body[20]; as_pub = body[21:21 + idlen]; ct = body[21 + idlen:]
    ua_pub = _pub_raw(ua_priv.public_key())
    shared = ua_priv.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), as_pub))
    ikm = HKDF(algorithm=hashes.SHA256(), length=32, salt=b64d(auth), info=b"WebPush: info\x00" + ua_pub + as_pub).derive(shared)
    cek = HKDF(algorithm=hashes.SHA256(), length=16, salt=salt, info=b"Content-Encoding: aes128gcm\x00").derive(ikm)
    nonce = HKDF(algorithm=hashes.SHA256(), length=12, salt=salt, info=b"Content-Encoding: nonce\x00").derive(ikm)
    pt = AESGCM(cek).decrypt(nonce, ct, None)
    return pt.rstrip(b"\x00")[:-1] if pt.endswith(b"\x02") else pt


def _http_post(url, data, headers, timeout=20):
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def send_one_ex(sub, payload, priv_b64, subject, post=_http_post, now=None):
    """给一个订阅发一条。返回 (HTTP 状态码, 响应正文)：201 成功；404/410 = 订阅已失效应删除；其它的正文里有推送服务给的原因。"""
    body = encrypt(json.dumps(payload, ensure_ascii=False).encode("utf-8"), sub["keys"]["p256dh"], sub["keys"]["auth"])
    st, txt = post(sub["endpoint"], body, {"Content-Encoding": "aes128gcm", "Content-Type": "application/octet-stream", "TTL": "86400", "Urgency": "high",
                                           "Authorization": vapid_auth(sub["endpoint"], priv_b64, subject, now)})
    return st, txt


def send_one(sub, payload, priv_b64, subject, post=_http_post, now=None):
    """同 send_one_ex，只返回状态码（兼容旧调用）。"""
    return send_one_ex(sub, payload, priv_b64, subject, post, now)[0]


def load_subs(path):
    try:
        j = json.load(open(path, encoding="utf-8"))
        return [s for s in (j.get("subs") or []) if isinstance(s, dict) and s.get("endpoint") and (s.get("keys") or {}).get("p256dh") and (s.get("keys") or {}).get("auth")]
    except Exception:  # noqa: BLE001
        return []


def send_all(path, payload, priv_b64, subject, post=_http_post):
    """发给文件里的全部订阅；失效的（404/410）从文件里删掉。返回 (成功数, 失败说明列表, 删除数)。"""
    subs = load_subs(path); ok, bad, dead = 0, [], []
    for s in subs:
        try:
            st, txt = send_one_ex(s, payload, priv_b64, subject, post)
        except Exception as ex:  # noqa: BLE001
            bad.append(f"{type(ex).__name__}: {str(ex)[:80]}"); continue
        if 200 <= st < 300:
            ok += 1
        elif st in (404, 410):
            dead.append(s["endpoint"])
        else:
            bad.append(f"HTTP {st}（{urllib.parse.urlparse(s['endpoint']).netloc}）{str(txt or '').strip()[:120]}")
    if dead:
        keep = [s for s in subs if s["endpoint"] not in dead]
        json.dump({"subs": keep, "updated": time.strftime("%Y-%m-%d %H:%M", time.gmtime()) + " UTC"}, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return ok, bad, len(dead)


def diagnose(priv_b64, vapid_path, subs_path):
    """逐项检查网页推送为什么发不出去，返回「问题说明」列表（空列表 = 配置没毛病）。
    检查：私钥在不在、格式对不对；仓库里有没有公钥；私钥和公钥是不是一对；有没有登记的设备；设备登记时用的公钥是不是现在这一把。"""
    out = []
    pub = None
    try:
        pub = (json.load(open(vapid_path, encoding="utf-8")) or {}).get("publicKey")
    except Exception:  # noqa: BLE001
        pub = None
    mine = None
    if not (priv_b64 or "").strip():
        out.append("Actions 里没有拿到私钥：GitHub 仓库 → Settings → Secrets and variables → Actions → 「Repository secrets」里要有名字恰好是 VAPID_PRIVATE_KEY 的一项（不是 Variables，也不是 Environment/Dependabot 里的）。已经有同名的就点它右边的铅笔改值（Update），不能再新建。")
    else:
        try:
            raw = b64d(priv_b64)
            if len(raw) != 32:
                raise ValueError(f"长度 {len(raw)} 字节，应是 32 字节")
            mine = vapid_public_b64(priv_b64)
        except Exception as ex:  # noqa: BLE001
            out.append(f"Secret 里的私钥格式不对（{type(ex).__name__}: {str(ex)[:60]}）：应该是页面生成时显示的那一整串（约 43 个字符），前后不能有空格、引号或换行。")
    if not pub:
        out.append("仓库里没有 data/push_vapid.json（页面还没生成过推送密钥，或写入仓库失败）。")
    elif mine and mine != pub:
        out.append("Secret 里的私钥和仓库里的公钥不是一对（多半是在两台设备上各生成了一次密钥，后一次覆盖了公钥）。解决：只留一对——在页面点「重新生成密钥」，把新私钥更新进 Secret，再让每台设备重新「开启本设备推送」。")
    subs = load_subs(subs_path)
    if not subs:
        out.append("data/push_subs.json 里没有登记任何设备：在每台设备的页面上点「开启本设备推送」并看到“已开启并登记到云端”；iPhone 要先「添加到主屏幕」再从图标打开。")
    else:
        stale = [x for x in subs if x.get("pub") and pub and x.get("pub") != pub]
        if stale and len(stale) == len(subs):
            out.append(f"已登记的 {len(subs)} 台设备都是用旧公钥订阅的，现在的公钥换过了，它们收不到：每台设备先「关闭本设备推送」再「开启本设备推送」。")
    return out


if __name__ == "__main__":
    p, q = gen_vapid(); print("私钥(放 Secrets VAPID_PRIVATE_KEY):", p); print("公钥(放 data/push_vapid.json):", q)
