"""同一个请求，协议名 / 主机 / 绝对 URL 在三处读数是否一致。

格子分四组：
  T 组  经过转发头改写中间件之后的读数
  E 组  不经任何中间件、直接拿到 environ 时的读数
  C 组  同一份 environ 上，请求对象 / 响应头补全 / 路由外链 三处拼出来的绝对 URL 是否同色
  K 组  既有读数不能改坏的守格

每行给 red/green 与读数，末尾给总分。
"""

from io import BytesIO

from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.routing import Map
from werkzeug.routing import Rule
from werkzeug.sansio.utils import get_host
from werkzeug.wrappers import Request
from werkzeug.wrappers import Response

BASE = {
    "SERVER_NAME": "internal.example",
    "SERVER_PORT": "80",
    "wsgi.url_scheme": "http",
    "wsgi.input": BytesIO(b""),
    "wsgi.version": (1, 0),
    "wsgi.multithread": False,
    "wsgi.multiprocess": False,
    "wsgi.run_once": False,
    "REQUEST_METHOD": "GET",
    "PATH_INFO": "/p/x",
    "QUERY_STRING": "",
    "HTTP_HOST": "internal.example",
}

MAP = Map([Rule("/p/<x>", endpoint="parrot")])
results = []


def make_env(forwarded=None, counts=None, drop_host=False, over=None):
    environ = dict(BASE)
    environ["wsgi.input"] = BytesIO(b"")
    if drop_host:
        environ.pop("HTTP_HOST")
    if over:
        environ.update(over)
    if forwarded:
        for k, v in forwarded.items():
            environ["HTTP_" + k.upper().replace("-", "_")] = v
        ProxyFix(lambda e, sr: [], **(counts or {}))(environ, lambda *a: None)
    return environ


def cell(label, want, got):
    red = str(want) != str(got)
    results.append(red)
    print(f"{label:<4} {'red  ' if red else 'green'}  期望={want!r} 实读={got!r}")


def scheme_of(url):
    return url.split("://", 1)[0] if "://" in url else url


def authority_of(url):
    rest = url.split("://", 1)[1] if "://" in url else url
    return rest.split("/", 1)[0]


# ---------------- T 组：经转发头改写 ----------------
e = make_env({"X-Forwarded-Proto": "HTTPS"}, {"x_proto": 1})
r = Request(e)
cell("T1", "True|https", f"{r.is_secure}|{scheme_of(r.url)}")

e = make_env({"X-Forwarded-Proto": "https", "X-Forwarded-Host": "good.example:443"}, {"x_proto": 1, "x_host": 1})
r = Request(e)
cell("T2", "good.example|https", f"{r.host}|{scheme_of(r.url)}")

e = make_env({"X-Forwarded-Proto": "HTTPS", "X-Forwarded-Host": "good.example:443"}, {"x_proto": 1, "x_host": 1})
r = Request(e)
cell("T3", "good.example|True|https", f"{r.host}|{r.is_secure}|{scheme_of(r.url)}")

e = make_env({"X-Forwarded-Host": "::1"}, {"x_host": 1})
r = Request(e)
cell("T4", "[::1]", f"{r.host}")

e = make_env({"X-Forwarded-Proto": "socks"}, {"x_proto": 1})
r = Request(e)
cell("T5", "http", scheme_of(r.url))

# ---------------- E 组：不经中间件 ----------------
r = Request(make_env(over={"wsgi.url_scheme": "HTTPS"}))
cell("E1", "True|https", f"{r.is_secure}|{scheme_of(r.url)}")

r = Request(make_env(over={"wsgi.url_scheme": "HTTPS", "HTTP_HOST": "ok.example:443"}))
cell("E2", "ok.example", r.host)

r = Request(make_env(over={"wsgi.url_scheme": "HTTPS", "HTTP_HOST": "ok.example:8443"}))
cell("E4", "ok.example:8443|https://ok.example:8443", f"{r.host}|{r.url.rsplit('/p/x', 1)[0]}")

# ---------------- C 组：三处拼的绝对 URL 同色 ----------------
e = make_env(over={"wsgi.url_scheme": "HTTPS", "HTTP_HOST": "ok.example:443"})
r = Request(e)
resp = Response()
resp.headers["Location"] = "/p/x"
resp.autocorrect_location_header = True
loc = resp.get_wsgi_headers(e).get("Location", "")
cell("C1", f"{scheme_of(r.url)}|{authority_of(r.url)}", f"{scheme_of(loc)}|{authority_of(loc)}")

e = make_env({"X-Forwarded-Proto": "HTTPS"}, {"x_proto": 1})
r = Request(e)
resp = Response()
resp.headers["Location"] = "/p/x"
resp.autocorrect_location_header = True
loc = resp.get_wsgi_headers(e).get("Location", "")
cell("C3", f"{scheme_of(r.url)}", scheme_of(loc))

# ---------------- K 组：既有读数不许改坏 ----------------
cell("K1", "", get_host("http", "a.test:port", None))
cell("K2", "", get_host("http", "", None))
cell("K3", "[2001:db8::a]", Request(make_env({"X-Forwarded-Host": "[2001:db8::a]"}, {"x_host": 1})).host)
cell("K4", "spam", get_host("https", "spam:443", None))
cell("K5", "spam:8080", get_host("http", "spam:8080", None))
cell("K6", "eggs", Request(make_env({"X-Forwarded-Host": "eggs"}, {"x_host": 1})).host)
cell("K7", "http", scheme_of(Request(make_env()).url))
cell("K8", "https://internal.example/eggs/", Request(make_env(
    {"X-Forwarded-Proto": "https", "X-Forwarded-Prefix": "/ham, /eggs"}, {"x_proto": 1, "x_prefix": 1}
)).url_root)

red = sum(results)
print(f"\n总分: {len(results) - red}/{len(results)} 绿，红 {red} 格")
