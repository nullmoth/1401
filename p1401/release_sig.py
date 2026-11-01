"""NullMoth release signatures: Ed25519 (RFC 8032) over the exact bytes of a release file.

The SHA-256 in a release's SHA256SUMS.txt only proves that the files of one release agree with each other: whoever can
replace the release's files can replace the list too. Every file that 1401 runs or puts on a stick from a newer release
(the 1401 Windows app, the NVIDIA driver package, the 1401 Mac app) carries a detached signature, <name>.sig (base64
of the 64-byte signature), made with the NullMoth release key. The public half is below and is the same key the Mac app
compiles in; the private half never leaves the signing host.

This module carries no third-party code and no dependency: the bundled Python has no cryptography package. It follows
the verification steps of RFC 8032 section 5.1.7 with the curve constants of section 5.1. sign() exists for the tests,
which make their own throwaway key; 1401 itself only verifies."""
import base64
import hashlib

PUBLIC_KEY = "ztPmcj+mcHYM1X2lrp24yjq0xBuzke7gh5XJ3E2fd4E="

_P = 2 ** 255 - 19
_L = 2 ** 252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _P - 2, _P) % _P
_I = pow(2, (_P - 1) // 4, _P)


def _inv(x):
    return pow(x, _P - 2, _P)


def _recover_x(y, sign):
    if y >= _P:
        return None
    x2 = (y * y - 1) * _inv(_D * y * y + 1)
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P != 0:
        x = x * _I % _P
    if (x * x - x2) % _P != 0:
        return None
    if (x & 1) != sign:
        x = _P - x
    return x


# points in extended coordinates (X, Y, Z, T), x = X/Z, y = Y/Z, x*y = T/Z
def _add(p, q):
    a = (p[1] - p[0]) * (q[1] - q[0]) % _P
    b = (p[1] + p[0]) * (q[1] + q[0]) % _P
    c = 2 * p[3] * q[3] * _D % _P
    d = 2 * p[2] * q[2] % _P
    e, f, g, h = b - a, d - c, d + c, b + a
    return (e * f % _P, g * h % _P, f * g % _P, e * h % _P)


def _mul(s, p):
    q = (0, 1, 1, 0)
    while s > 0:
        if s & 1:
            q = _add(q, p)
        p = _add(p, p)
        s >>= 1
    return q


def _equal(p, q):
    return (p[0] * q[2] - q[0] * p[2]) % _P == 0 and (p[1] * q[2] - q[1] * p[2]) % _P == 0


_GY = 4 * _inv(5) % _P
_GX = _recover_x(_GY, 0)
_G = (_GX, _GY, 1, _GX * _GY % _P)


def _compress(p):
    zi = _inv(p[2])
    x, y = p[0] * zi % _P, p[1] * zi % _P
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


def _decompress(s):
    if len(s) != 32:
        return None
    y = int.from_bytes(s, "little")
    sign = y >> 255
    y &= (1 << 255) - 1
    x = _recover_x(y, sign)
    if x is None:
        return None
    return (x, y, 1, x * y % _P)


def _h(m):
    return int.from_bytes(hashlib.sha512(m).digest(), "little")


def verify(data, signature, public_key=PUBLIC_KEY):
    """True only when `signature` (raw 64 bytes, or base64 text of them) is a valid Ed25519 signature of `data` by
    `public_key` (base64 of the raw 32 bytes). Anything malformed is False, never an exception."""
    return _verify(lambda h: h.update(data), signature, public_key)


def verify_file(path, signature, public_key=PUBLIC_KEY):
    """verify() over a file's bytes, read in 1 MB pieces (a release zip is a few hundred MB)."""
    def feed(h):
        with open(path, "rb") as fh:
            for b in iter(lambda: fh.read(1 << 20), b""):
                h.update(b)
    try:
        return _verify(feed, signature, public_key)
    except OSError:
        return False


def _verify(feed, signature, public_key):
    try:
        if isinstance(signature, str):
            signature = base64.b64decode(signature.strip(), validate=True)
        key = base64.b64decode(public_key, validate=True)
    except (ValueError, TypeError):
        return False
    if len(signature) != 64 or len(key) != 32:
        return False
    a = _decompress(key)
    r = _decompress(signature[:32])
    if a is None or r is None:
        return False
    s = int.from_bytes(signature[32:], "little")
    if s >= _L:
        return False
    h = hashlib.sha512(signature[:32] + key)
    feed(h)
    k = int.from_bytes(h.digest(), "little") % _L
    return _equal(_mul(8 * s, _G), _add(_mul(8, r), _mul(8 * k, a)))


def sign(data, seed):
    """Test helper: (signature, public key base64) for a 32-byte seed."""
    h = hashlib.sha512(seed).digest()
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    pub = _compress(_mul(a, _G))
    r = _h(h[32:] + data) % _L
    rb = _compress(_mul(r, _G))
    k = _h(rb + pub + data) % _L
    s = (r + k * a) % _L
    return rb + int.to_bytes(s, 32, "little"), base64.b64encode(pub).decode()
