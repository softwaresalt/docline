---
date: 2026-08-29
category: cgnat-explicit-membership-check-and-ipv4-mapped-normalization
keywords: [ssrf, cgnat, rfc6598, ipaddress, ip_network, ipv4_mapped, pyright, isinstance, sitemap, fetch, cve-2024-4032]
confidence: high
evidence: 056-S / 065-F Ship session 2026-08-29 — sitemap _is_unsafe_address accepted 100.64.0.0/10 (six ipaddress flags miss CGNAT on Python 3.12.10); fixed with explicit IPv4Network membership + guarded IPv4-mapped normalization; pyright rejected ip_network union typing; merged PR #167 (9560d48)
---

# CGNAT 100.64.0.0/10 needs an explicit membership check — no ipaddress flag catches it

**Date:** 2026-08-29
**Context:** Shipping `056-S` / `065-F` — closing a CGNAT (RFC 6598
`100.64.0.0/10`) SSRF gap in `src/docline/fetch/sitemap.py`
`_is_unsafe_address`.

## Symptom

An SSRF address classifier that rejects private/loopback/link-local/
multicast/reserved/unspecified via the six `ipaddress` boolean flags
still **accepts** Carrier-grade NAT shared space `100.64.0.0/10`. On
Python 3.12.x, `ipaddress.ip_address("100.64.0.1")` reports
`is_private`, `is_reserved`, `is_global` **all effectively miss it** —
none of the six flags return True — so CGNAT slips through.

## Fix

Add an explicit network-membership check:

```python
_CGNAT_NETWORK: ipaddress.IPv4Network = ipaddress.IPv4Network("100.64.0.0/10")
...
return isinstance(ip, ipaddress.IPv4Address) and ip in _CGNAT_NETWORK
```

## Two non-obvious gotchas

1. **`ip_network()` breaks pyright.** `ipaddress.ip_network("100.64.0.0/10")`
   is typed `IPv4Network | IPv6Network`. Annotating the constant as
   `IPv4Network` fails `pyright` (assignment), and `addr in union_network`
   fails too (IPv6Network.__contains__ expects IPv6Address). Use the
   concrete `ipaddress.IPv4Network("…")` constructor and narrow the address
   with `isinstance(ip, ipaddress.IPv4Address)` (functionally identical to
   `ip.version == 4`, but pyright narrows on `isinstance`, not `.version`).

2. **IPv4-mapped IPv6 must be normalized BEFORE classification**, guarded
   for IPv6 only — `IPv4Address` has no `.ipv4_mapped`:

   ```python
   if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
       ip = ip.ipv4_mapped
   ```

   An unguarded `ip = ip.ipv4_mapped or ip` raises `AttributeError` on plain
   IPv4 input. Only `::ffff:0:0/96` maps; the deprecated IPv4-compatible
   `::a.b.c.d` form has `.ipv4_mapped is None` and is already rejected as
   IPv6 `is_reserved` (member of `::/8`) — a tempting "bypass" that is
   actually fail-closed.

## Test discipline

Pin the **classifier result** (`assert _is_unsafe_address(addr) is True`),
NOT the `ipaddress` special-use flag table — those tables are
Python-patch-dependent (CVE-2024-4032). Cover both `/10` boundaries
(`100.64.0.0`, `100.127.255.255`) and just-outside accepts
(`100.63.255.255`, `100.128.0.0`) to prove no over-rejection.

## Related

Mirrors the §H6 fetch-path fix (064-F / `url_policy`). The two SSRF
classifiers (`url_policy` and `sitemap._is_unsafe_address`) are now
independent copies — consolidation onto one predicate is a tracked
deliberation-Option-B follow-up.
