"""檢查「四段防護可以各自整段註解掉」：

對每一段防護，複製一份程式、把那一段（開始～結束標記之間）註解掉，然後
1. 確認程式還能 import、其他測試照常通過（程式不會因為少一段防護就壞掉）
2. 確認對應的防護測試「變成失敗」（證明那一段真的是防護，而且關掉就有差）

用法：uv run python scripts/check_defence_toggle.py
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "gas_agent"

# 防護編號 -> 預期會失敗的測試關鍵字
EXPECT_FAIL = {
    1: ["test_defence_1"],
    2: ["test_defence_2"],
    3: ["test_store_photo_non_target_description_cannot_escape", "test_malicious_description_is_neutralized"],
    4: ["test_formula_injection_is_neutralized", "test_malicious_description_is_neutralized"],
}
START = re.compile(r"# ===== 防護 (\d)：.* 開始 =====")


def comment_out(n: int, target_pkg: Path) -> int:
    count = 0
    for py in target_pkg.glob("*.py"):
        lines = py.read_text(encoding="utf-8").split("\n")
        inside = False
        for i, line in enumerate(lines):
            m = START.search(line)
            if m and int(m.group(1)) == n:
                inside = True
                continue
            if inside and f"# ===== 防護 {n} 結束 =====" in line:
                inside = False
                continue
            if inside and line.strip():
                indent = len(line) - len(line.lstrip())
                lines[i] = line[:indent] + "# " + line[indent:]
                count += 1
        py.write_text("\n".join(lines), encoding="utf-8")
    return count


def run_pytest(src_root: Path) -> tuple[set[str], str]:
    env = {**os.environ, "PYTHONPATH": str(src_root)}
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--no-header", "-rf", str(ROOT / "tests")],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, cwd=ROOT,
    )
    failed = set(re.findall(r"^FAILED [^:]+::(\S+)", proc.stdout, re.M))
    failed = {re.sub(r"\[.*", "", name) for name in failed}
    return failed, proc.stdout


def main() -> int:
    ok = True
    for n in (1, 2, 3, 4):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_src = Path(tmp) / "src"
            shutil.copytree(SRC, tmp_src / "gas_agent", ignore=shutil.ignore_patterns("__pycache__"))
            lines = comment_out(n, tmp_src / "gas_agent")
            failed, out = run_pytest(tmp_src)
            others = {f for f in failed if not any(k in f for k in EXPECT_FAIL[n])}
            expected_hit = {f for f in failed if any(k in f for k in EXPECT_FAIL[n])}
            good = lines > 0 and expected_hit and not others and "error" not in out.lower().split("passed")[-1]
            ok &= bool(good)
            print(f"防護 {n} 註解掉（{lines} 行）：預期失敗 {sorted(expected_hit)}；非預期失敗 {sorted(others)} -> {'OK' if good else 'NG'}")
            if not good:
                print(out[-1500:])
    print("全部通過" if ok else "有問題")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
