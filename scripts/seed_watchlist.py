"""Seed the 16 watchlist stocks via the API."""
import httpx
import sys

SYMBOLS = [
    "AROC", "AZZ", "BITO", "CASH", "FAF", "FBIN", "FOUR", "INTC",
    "KN", "NVDA", "PATH", "PDLB", "QCOM", "STNE", "UFPI", "UVE",
]

base = "http://localhost:8000"
ok = 0
fail = 0

for sym in SYMBOLS:
    try:
        r = httpx.post(f"{base}/api/stocks", json={"symbol": sym}, timeout=15)
        if r.status_code < 300:
            data = r.json()
            print(f"  OK  {sym:6s} - {data.get('name', '?')}")
            ok += 1
        else:
            print(f" ERR  {sym:6s} - {r.status_code}: {r.text[:80]}")
            fail += 1
    except Exception as e:
        print(f" ERR  {sym:6s} - {e}")
        fail += 1

print(f"\nDone: {ok} added, {fail} failed")
