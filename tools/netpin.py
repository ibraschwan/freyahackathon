"""Resolve one host through a public resolver, for networks whose DNS answers with a block page for *.workers.dev.

Off unless FREYA_BANK_PIN_DNS=1 (see env.example). Only the host given to pin() is affected, and TLS still
verifies the real hostname: only the address lookup changes.
"""
import json, socket, urllib.request

_real = socket.getaddrinfo
_cache = {}

def _public_ips(host):
    """A records for `host` from Cloudflare's resolver, then Google's. Asked over HTTPS by IP, so no local DNS is involved."""
    if host not in _cache:
        ips = []
        for url in ("https://1.1.1.1/dns-query?type=A&name=", "https://8.8.8.8/resolve?type=A&name="):
            try:
                req = urllib.request.Request(url + host, headers={"accept": "application/dns-json"})
                ips = [a["data"] for a in json.load(urllib.request.urlopen(req, timeout=10)).get("Answer") or [] if a.get("type") == 1]
            except Exception: ips = []
            if ips: break
        _cache[host] = ips
    return _cache[host]

def pin(host):
    def getaddrinfo(h, *a, **k):
        if h != host: return _real(h, *a, **k)
        ips = _public_ips(host)
        try: local = _real(h, *a, **k)
        except Exception: local = []
        # the local answer is used whenever it is the real one (it may also offer IPv6, which some networks need)
        if local and (not ips or any(r[4][0] in ips or ":" in r[4][0] for r in local)):
            return sorted(local, key=lambda r: ":" not in r[4][0])      # IPv6 first: without an IPv6 route it fails at once, and one network here resets IPv4 to this host
        return _real(ips[0], *a, **k) if ips else local
    socket.getaddrinfo = getaddrinfo
