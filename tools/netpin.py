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
        ips = _public_ips(host) if h == host else []
        return _real(ips[0] if ips else h, *a, **k)
    socket.getaddrinfo = getaddrinfo
