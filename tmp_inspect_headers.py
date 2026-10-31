from pathlib import Path
import re

d = Path(r"D:\BCL-Bhuiyan\bcl_bhuiyan\listening")
for n in range(2, 30):
    p = d / f"listening-mock-{n}.html"
    data = p.read_bytes()
    # find first header-like snippet in first 80k or after <body
    body = data.find(b"<body")
    chunk = data[body:body + 8000].decode("utf-8", "replace") if body != -1 else data[:8000].decode("utf-8", "replace")
    # collapse whitespace
    m = re.search(r'<div class="header[\s\S]{0,900}', chunk)
    m2 = re.search(r'<header class="header"[\s\S]{0,900}', chunk)
    snippet = (m or m2)
    print("=" * 60)
    print("MOCK", n, "body", body)
    if snippet:
        print(snippet.group(0)[:700])
    else:
        print(chunk[:400])
