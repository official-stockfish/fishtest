"""Gate anonymous UI traffic behind a stateless proof-of-work challenge.

Anonymous browsers must solve a small SHA-256 puzzle before the app does any
real work for them. Solving it once yields a signed pass cookie, so the cost is
paid once per ``FISHTEST_POW_TTL_SECONDS`` rather than per request.

Never challenged:

- authenticated UI sessions (``session["user"]`` is set),
- ``/api/*`` (worker protocol authenticates with credentials in the body, and
  scripted API clients cannot execute JavaScript),
- static assets, ``robots.txt`` and ``favicon.ico``.

Issuing a challenge and checking a pass cookie only cost an HMAC; neither
touches MongoDB.

Configuration (environment):

- ``FISHTEST_POW_DIFFICULTY``: required leading zero bits of
  ``sha256(challenge + ":" + nonce)``. Default 18 (~260k hashes on average).
  ``0`` disables the middleware entirely.
- ``FISHTEST_POW_TTL_SECONDS``: lifetime of the pass cookie. Default 86400.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from typing import TYPE_CHECKING, Final
from urllib.parse import parse_qs, quote

import itsdangerous
from itsdangerous.exc import BadSignature
from starlette.requests import HTTPConnection
from starlette.responses import HTMLResponse, PlainTextResponse, RedirectResponse

from fishtest.http.cookie_session import authenticated_user_from_data
from fishtest.http.settings import env_int

if TYPE_CHECKING:
    from collections.abc import Callable

    from starlette.responses import Response
    from starlette.types import ASGIApp, Receive, Scope, Send

POW_COOKIE_NAME: Final[str] = "fishtest_pow"
POW_VERIFY_PATH: Final[str] = "/__pow/verify"
DEFAULT_DIFFICULTY: Final[int] = 22
MAX_DIFFICULTY: Final[int] = 32
DEFAULT_PASS_TTL_SECONDS: Final[int] = 60 * 60 * 24
CHALLENGE_TTL_SECONDS: Final[int] = 10 * 60

_EXEMPT_PREFIXES: Final[tuple[str, ...]] = ("/api/", "/static/")
_EXEMPT_PATHS: Final[frozenset[str]] = frozenset({"/robots.txt", "/favicon.ico"})
_MAX_VERIFY_BODY_BYTES: Final[int] = 4096
_MAX_NONCE_DIGITS: Final[int] = 20
_DEFAULT_NEXT: Final[str] = "/tests"


def _leading_zero_bits_ok(digest: bytes, difficulty: int) -> bool:
    return int.from_bytes(digest, "big") >> (256 - difficulty) == 0


def _safe_next(value: str | None) -> str:
    """Only allow same-origin relative redirects."""
    if (
        not value
        or not value.startswith("/")
        or value.startswith(("//", "/\\"))
        or any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value)  # noqa: PLR2004
    ):
        return _DEFAULT_NEXT
    return value


def _is_https(scope: Scope) -> bool:
    headers = dict(scope.get("headers") or [])
    forwarded = headers.get(b"x-forwarded-proto", b"").split(b",", 1)[0].strip()
    if forwarded:
        return forwarded == b"https"
    return scope.get("scheme") == "https"


class ProofOfWorkMiddleware:
    """Challenge anonymous, non-API requests with a proof-of-work page.

    Must run inside the session middleware so ``scope["session"]`` is loaded.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        secret_key: str | Callable[[], str],
        difficulty: int | None = None,
        pass_ttl_seconds: int | None = None,
    ) -> None:
        """Configure the middleware; unset options are read from the env."""
        self.app = app
        self._secret_key = secret_key
        if difficulty is None:
            difficulty = env_int("FISHTEST_POW_DIFFICULTY", default=DEFAULT_DIFFICULTY)
        self.difficulty = max(0, min(MAX_DIFFICULTY, difficulty))
        if pass_ttl_seconds is None:
            pass_ttl_seconds = env_int(
                "FISHTEST_POW_TTL_SECONDS", default=DEFAULT_PASS_TTL_SECONDS
            )
        self.pass_ttl_seconds = max(60, pass_ttl_seconds)
        self._challenge_signer: itsdangerous.TimestampSigner | None = None
        self._pass_signer: itsdangerous.TimestampSigner | None = None

    # -- signing -----------------------------------------------------------

    def _signers(
        self,
    ) -> tuple[itsdangerous.TimestampSigner, itsdangerous.TimestampSigner]:
        if self._challenge_signer is None or self._pass_signer is None:
            key = self._secret_key() if callable(self._secret_key) else self._secret_key
            self._challenge_signer = itsdangerous.TimestampSigner(
                key, salt="fishtest-pow-challenge"
            )
            self._pass_signer = itsdangerous.TimestampSigner(
                key, salt="fishtest-pow-pass"
            )
        return self._challenge_signer, self._pass_signer

    @staticmethod
    def _client_binding(scope: Scope) -> str:
        """Bind tokens to the client IP so one solution cannot serve a botnet."""
        client = scope.get("client")
        host = client[0] if client else ""
        return hashlib.sha256(host.encode()).hexdigest()[:16]

    def _issue_challenge(self, scope: Scope) -> str:
        challenge_signer, _ = self._signers()
        payload = (
            f"{secrets.token_hex(12)}.{self.difficulty}.{self._client_binding(scope)}"
        )
        return challenge_signer.sign(payload).decode("ascii")

    def _has_valid_pass(self, scope: Scope) -> bool:
        raw = HTTPConnection(scope).cookies.get(POW_COOKIE_NAME)
        if not raw:
            return False
        _, pass_signer = self._signers()
        try:
            value = pass_signer.unsign(raw, max_age=self.pass_ttl_seconds)
        except BadSignature:
            return False
        return hmac.compare_digest(value.decode("ascii"), self._client_binding(scope))

    # -- request handling --------------------------------------------------

    def _is_exempt(self, scope: Scope) -> bool:
        path = str(scope.get("path") or "")
        if path in _EXEMPT_PATHS or path.startswith(_EXEMPT_PREFIXES):
            return True
        session = scope.get("session")
        return isinstance(session, dict) and bool(authenticated_user_from_data(session))

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Pass through exempt/solved requests; challenge the rest."""
        if scope.get("type") != "http" or self.difficulty == 0:
            await self.app(scope, receive, send)
            return

        if scope.get("path") == POW_VERIFY_PATH:
            response = await self._handle_verify(scope, receive)
            await response(scope, receive, send)
            return

        if self._is_exempt(scope) or self._has_valid_pass(scope):
            await self.app(scope, receive, send)
            return

        response = self._challenge_response(scope)
        await response(scope, receive, send)

    def _challenge_response(self, scope: Scope) -> Response:
        method = scope.get("method", "GET")
        headers = {"Cache-Control": "no-store", "X-Robots-Tag": "noindex"}
        if method not in {"GET", "HEAD"}:
            return PlainTextResponse(
                "Verification required: reload the page in your browser.",
                status_code=403,
                headers=headers,
            )

        request_headers = dict(scope.get("headers") or [])
        if request_headers.get(b"hx-request") == b"true":
            # Partial htmx swap: force a full reload so the user sees the page.
            return PlainTextResponse("", headers={**headers, "HX-Refresh": "true"})

        path = str(scope.get("path") or "/")
        query = scope.get("query_string", b"").decode("latin-1")
        next_url = _safe_next(f"{path}?{query}" if query else path)
        # Status 200 keeps container healthchecks (curl -f / wget) green.
        return HTMLResponse(
            _render_challenge_page(
                self._issue_challenge(scope), self.difficulty, next_url
            ),
            headers=headers,
        )

    async def _read_body(self, receive: Receive) -> bytes | None:
        body = b""
        while True:
            message = await receive()
            if message["type"] != "http.request":
                return None
            body += message.get("body", b"")
            if len(body) > _MAX_VERIFY_BODY_BYTES:
                return None
            if not message.get("more_body", False):
                return body

    async def _handle_verify(self, scope: Scope, receive: Receive) -> Response:
        if scope.get("method") != "POST":
            return PlainTextResponse("Method not allowed", status_code=405)

        body = await self._read_body(receive)
        if body is None:
            return PlainTextResponse("Request too large", status_code=413)
        form = parse_qs(body.decode("ascii", errors="replace"), max_num_fields=8)
        challenge = form.get("challenge", [""])[0]
        nonce = form.get("nonce", [""])[0]
        next_url = _safe_next(form.get("next", [""])[0])
        retry = RedirectResponse(url=next_url, status_code=303)

        if not (nonce.isdigit() and len(nonce) <= _MAX_NONCE_DIGITS and challenge):
            return retry

        challenge_signer, pass_signer = self._signers()
        try:
            payload = challenge_signer.unsign(
                challenge, max_age=CHALLENGE_TTL_SECONDS
            ).decode("ascii")
            _, difficulty_raw, binding = payload.split(".")
            difficulty = int(difficulty_raw)
        except BadSignature, ValueError, UnicodeDecodeError:
            return retry

        digest = hashlib.sha256(f"{challenge}:{nonce}".encode("ascii")).digest()
        if (
            difficulty < self.difficulty
            or not hmac.compare_digest(binding, self._client_binding(scope))
            or not _leading_zero_bits_ok(digest, difficulty)
        ):
            return retry

        token = pass_signer.sign(binding).decode("ascii")
        retry.set_cookie(
            POW_COOKIE_NAME,
            token,
            max_age=self.pass_ttl_seconds,
            path="/",
            secure=_is_https(scope),
            httponly=True,
            samesite="lax",
        )
        return retry


# --------------------------------------------------------------------------
# Challenge page
# --------------------------------------------------------------------------

# Pure-JS SHA-256 (WebCrypto needs a secure context, so it is unusable on plain
# HTTP deployments). Runs in Web Workers, one per core, with a main-thread
# fallback. Hashes the ASCII string `challenge + ":" + nonce`.
_SOLVER_JS: Final[str] = r"""
function powSolve(prefix, difficulty, start, step, report) {
  var K = new Int32Array([
    0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
    0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
    0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
    0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
    0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
    0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
    0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
    0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2]);
  var w = new Int32Array(64);
  var plen = prefix.length;
  var maxLen = plen + 21;
  var buf = new Uint8Array(((maxLen + 9 + 63) >> 6) << 6);
  for (var p = 0; p < plen; p++) buf[p] = prefix.charCodeAt(p);

  function hashOk(len) {
    var nBlocks = (len + 9 + 63) >> 6, total = nBlocks << 6, i;
    for (i = len; i < total; i++) buf[i] = 0;
    buf[len] = 0x80;
    var bits = len * 8;
    buf[total - 4] = (bits >>> 24) & 255; buf[total - 3] = (bits >>> 16) & 255;
    buf[total - 2] = (bits >>> 8) & 255;  buf[total - 1] = bits & 255;
    var h0 = 0x6a09e667|0, h1 = 0xbb67ae85|0, h2 = 0x3c6ef372|0, h3 = 0xa54ff53a|0,
        h4 = 0x510e527f|0, h5 = 0x9b05688c|0, h6 = 0x1f83d9ab|0, h7 = 0x5be0cd19|0;
    for (var b = 0; b < nBlocks; b++) {
      var o = b << 6;
      for (i = 0; i < 16; i++) {
        var j = o + (i << 2);
        w[i] = (buf[j] << 24) | (buf[j+1] << 16) | (buf[j+2] << 8) | buf[j+3];
      }
      for (i = 16; i < 64; i++) {
        var x = w[i-15], y = w[i-2];
        var s0 = ((x >>> 7) | (x << 25)) ^ ((x >>> 18) | (x << 14)) ^ (x >>> 3);
        var s1 = ((y >>> 17) | (y << 15)) ^ ((y >>> 19) | (y << 13)) ^ (y >>> 10);
        w[i] = (w[i-16] + s0 + w[i-7] + s1) | 0;
      }
      var a = h0, c1 = h1, c2 = h2, d = h3, e = h4, f = h5, g = h6, h = h7;
      for (i = 0; i < 64; i++) {
        var S1 = ((e >>> 6) | (e << 26)) ^ ((e >>> 11) | (e << 21)) ^ ((e >>> 25) | (e << 7));
        var t1 = (h + S1 + ((e & f) ^ (~e & g)) + K[i] + w[i]) | 0;
        var S0 = ((a >>> 2) | (a << 30)) ^ ((a >>> 13) | (a << 19)) ^ ((a >>> 22) | (a << 10));
        var t2 = (S0 + ((a & c1) ^ (a & c2) ^ (c1 & c2))) | 0;
        h = g; g = f; f = e; e = (d + t1) | 0; d = c2; c2 = c1; c1 = a; a = (t1 + t2) | 0;
      }
      h0 = (h0 + a) | 0; h1 = (h1 + c1) | 0; h2 = (h2 + c2) | 0; h3 = (h3 + d) | 0;
      h4 = (h4 + e) | 0; h5 = (h5 + f) | 0; h6 = (h6 + g) | 0; h7 = (h7 + h) | 0;
    }
    var words = [h0, h1, h2, h3, h4, h5, h6, h7], need = difficulty;
    for (i = 0; i < 8 && need > 0; i++) {
      var z = Math.clz32(words[i]);
      if (need <= 32) return z >= need;
      if (z < 32) return false;
      need -= 32;
    }
    return true;
  }

  for (var n = start, count = 0; ; n += step, count++) {
    var s = String(n), len = plen;
    for (var k = 0; k < s.length; k++) buf[len++] = s.charCodeAt(k);
    if (hashOk(len)) return n;
    if (report && (count & 0xffff) === 0) report(count);
  }
}
"""

_PAGE_TEMPLATE: Final[str] = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>Checking your browser</title>
<style>
  :root {{ color-scheme: light dark; --bg: #f6f7f9; --fg: #1d2330; --muted: #5b6475; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg: #15181e; --fg: #e6e9ef; --muted: #9aa3b2; }}
  }}
  body {{ margin: 0; min-height: 100vh; display: grid; place-items: center;
         background: var(--bg); color: var(--fg);
         font: 16px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }}
  main {{ max-width: 28rem; padding: 2rem 1rem; text-align: center; }}
  h1 {{ font-size: 1.25rem; margin: 0 0 .5rem; }}
  p {{ color: var(--muted); margin: .25rem 0; }}
  .spinner {{ width: 2rem; height: 2rem; margin: 0 auto 1rem; border-radius: 50%;
             border: 3px solid var(--muted); border-top-color: transparent;
             animation: spin 1s linear infinite; }}
  @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
  @media (prefers-reduced-motion: reduce) {{ .spinner {{ animation: none; }} }}
</style>
</head>
<body>
<main>
  <div class="spinner" aria-hidden="true"></div>
  <h1>Checking your browser&hellip;</h1>
  <p id="status">This takes a moment and only happens once a day.</p>
  <p>Logged-in users skip this check.</p>
  <noscript><p>Please enable JavaScript to continue.</p></noscript>
  <form id="pow" method="post" action="{verify_path}" hidden>
    <input type="hidden" name="challenge" value="">
    <input type="hidden" name="nonce" value="">
    <input type="hidden" name="next" value="">
  </form>
</main>
<script>
{solver}
(function () {{
  var cfg = {config};
  var prefix = cfg.challenge + ":";
  var form = document.getElementById("pow");
  var done = false;
  function submit(nonce) {{
    if (done) return;
    done = true;
    form.elements.challenge.value = cfg.challenge;
    form.elements.nonce.value = String(nonce);
    form.elements.next.value = cfg.next;
    form.submit();
  }}
  var workers = [];
  try {{
    var n = Math.max(1, Math.min(navigator.hardwareConcurrency || 2, 8));
    var src = powSolve.toString() +
      "\\nonmessage=function(e){{var d=e.data;postMessage(powSolve(d.p,d.k,d.s,d.t,null));}};";
    var url = URL.createObjectURL(new Blob([src], {{ type: "text/javascript" }}));
    for (var i = 0; i < n; i++) {{
      var wk = new Worker(url);
      wk.onmessage = function (e) {{
        workers.forEach(function (x) {{ x.terminate(); }});
        submit(e.data);
      }};
      wk.postMessage({{ p: prefix, k: cfg.difficulty, s: i, t: n }});
      workers.push(wk);
    }}
  }} catch (err) {{
    workers.forEach(function (x) {{ x.terminate(); }});
    workers = [];
    setTimeout(function () {{ submit(powSolve(prefix, cfg.difficulty, 0, 1, null)); }}, 0);
  }}
}})();
</script>
</body>
</html>
"""


def _render_challenge_page(challenge: str, difficulty: int, next_url: str) -> str:
    config = (
        json.dumps({"challenge": challenge, "difficulty": difficulty, "next": next_url})
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
    return _PAGE_TEMPLATE.format(
        verify_path=quote(POW_VERIFY_PATH),
        solver=_SOLVER_JS,
        config=config,
    )


__all__ = [
    "POW_COOKIE_NAME",
    "POW_VERIFY_PATH",
    "ProofOfWorkMiddleware",
]
