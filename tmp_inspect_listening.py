from pathlib import Path
import re

p = Path(r"D:\BCL-Bhuiyan\bcl_bhuiyan\listening\listening-mock-22.html")
data = p.read_bytes()
# find body start by scanning for b'<body'
idx = data.find(b"<body")
print("body at", idx)
chunk = data[idx:idx + 25000].decode("utf-8", "replace")
print(chunk[:12000])
print("\n---MORE KEYS---")
blob = data[:400000] + data[-120000:]
text = blob.decode("utf-8", "replace")
for k in ["theme", "Night", "fullscreen", "text-size", "A+", "hlToolbar", "transcript", "checkAnswers", "toggleTheme"]:
    print(k, k.encode() in data[:500000] or k.encode() in data[-200000:])
