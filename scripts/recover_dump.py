# Recover pg_dump file that was corrupted by PowerShell UTF-16 LE encoding
# PowerShell's > operator: reads binary as cp437, splits on \n, writes as UTF-16 LE with \r\n

import sys

src = r"c:\projects\trader\backups\backup-20260410-011504\trader.dump"
dst = r"c:\projects\trader\backups\backup-20260410-011504\trader_recovered2.dump"

with open(src, "rb") as f:
    raw = f.read()

# Decode UTF-16 LE (skip BOM ff fe)
text = raw[2:].decode("utf-16-le")

# Count newline patterns
crlf = text.count("\r\n")
lone_cr = text.count("\r") - crlf
lone_lf = text.count("\n") - crlf
print(f"CRLF: {crlf}, lone CR: {lone_cr}, lone LF: {lone_lf}")

# PowerShell converted \n to \r\n, so reverse: \r\n -> \n
text_fixed = text.replace("\r\n", "\n")

# Strip trailing newline that Out-File adds
if text_fixed.endswith("\n"):
    text_fixed = text_fixed[:-1]

# Encode back to cp437
recovered = text_fixed.encode("cp437")
print(f"Recovered size: {len(recovered)} bytes")
print(f"First 10 bytes hex: {recovered[:10].hex()}")
has_pgdmp = recovered[:5] == b"PGDMP"
print(f"PGDMP header: {has_pgdmp}")

with open(dst, "wb") as out:
    out.write(recovered)
print(f"Saved to {dst}")
