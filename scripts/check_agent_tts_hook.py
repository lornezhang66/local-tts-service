from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hooks.agent_tts_hook import clean_markdown_for_speech


sample = """# 标题

这里有 [file.py (line 12)](/tmp/file.py:12) 和 ![图](x.png)。

```python
print("不要读")
```

```text
这段要朗读
第二行也要
```

- [x] 已完成 **重点** `term`
| a | b |
|---|---|
| 一 | 二 |
https://example.com
> 引用内容
/Users/lorne/a.py:12
"""

out = clean_markdown_for_speech(sample)
assert "这段要朗读" in out
assert "第二行也要" in out
assert "不要读" not in out
assert "line 12" not in out
assert "example.com" not in out
assert "图" not in out
assert "已完成 重点 term" in out
assert "引用内容" in out
assert "。。" not in out
print("agent hook markdown filter ok")
