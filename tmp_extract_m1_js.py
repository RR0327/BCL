from pathlib import Path

p = Path(r"D:\BCL-Bhuiyan\bcl_bhuiyan\listening\listening-mock-1.html")
text = p.read_text(encoding="utf-8", errors="replace")
js = text[text.rfind("<script>") :]
# drop correctAnswers bulky? it's small
out = Path(r"D:\BCL-Bhuiyan\tmp_mock1_script.js")
out.write_text(js, encoding="utf-8")
print("wrote", out, "len", len(js))
# print function names
import re
print("\n".join(re.findall(r"function ([A-Za-z0-9_]+)", js)))
