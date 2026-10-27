#!/usr/bin/env python3
"""Native-expression linter for OMR report chapters.

Detects translationese: expressions that are grammatical but read as translated
rather than composed in the report language. Complements `report_lint.py`
(publication safety) and the Consistency & Polish pass.

Checks (zh rule pack):
  - article_calque     headings opening with 一个/一次/一条/一种/一项 (English "a/an/the")
  - calqued_metaphor   English metaphors carried over literally (问题的形状, 攻击面, 承重假设…)
  - side_calque        "X侧" coined from English "X-side" outside established terms
  - measure_word       wrong measure word (条机制, 条选项…)
  - de_chain           ≥4 "的" inside one clause (hallmark of translated Chinese)
  - passive_stack      ≥3 "被" in one paragraph
  - dash_stack         ≥3 "——" in one paragraph (English em-dash habit)
  - long_sentence      sentence over --max-sentence chars (English sentence rhythm)

Checks (en rule pack):
  - heading_article    headings opening with A/An/The
  - long_sentence      same threshold logic

Severities: high (clear calque) and medium (density/collocation).
Exit codes: 0 = clean or warnings only, 1 = high findings (or any with --strict),
2 = usage error.

Usage:
  python3 scripts/prose_lint.py --mode report --workspace .
  python3 scripts/prose_lint.py --file deliverables/report-zh-CN.md
  python3 scripts/prose_lint.py --mode report --json
  python3 scripts/prose_lint.py --mode report --allow .omr/prose-lint-allow.txt
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

# --- Rule data -------------------------------------------------------------

# English metaphors and coinages that read as translated when carried into
# Chinese literally. Extend per project via --allow for deliberate usage.
ZH_CALQUES: list[tuple[str, str]] = [
    ("问题的形状", "问题的本质 / 问题全貌"),
    ("的形状是", "的本质是"),
    ("攻击面", "着力点 / 优化对象（非安全语境）"),
    ("承重假设", "关键前提 / 支撑性假设"),
    ("判决性", "决定性 / 关键"),
    ("可核性", "可核查性"),
    ("成本会计", "成本核算 / 成本账"),
    ("机制地图", "机制全景 / 技术格局"),
    ("评测场", "评测环境 / 评测口径"),
    ("干净证据", "干净的对照 / 无混杂的证据"),
    ("干净的证据", "干净的对照 / 无混杂的证据"),
    ("可被投机", "可被钻空子 / 可被刷高"),
    ("被投机", "被钻空子 / 被刷高"),
    ("房间里的大象", "明摆着却没人提的问题"),
    ("低垂的果实", "唾手可得的收益"),
    ("银弹", "万能解法"),
    ("甜蜜点", "最佳平衡点"),
    ("移动的目标", "不断变化的目标"),
    ("在一天结束时", "归根结底"),
    ("更多的是关于", "更在于"),
    ("不是关于", "问题不在于"),
    ("需要读出来的", "必须点明的"),
    ("读出来的结论", "必须点明的结论"),
]

# "X侧" is idiomatic only for a closed set; anything else is an English
# "X-side" calque.
ZH_SIDE_OK = {
    "端",
    "云",
    "服务",
    "客户",
    "用户",
    "供给",
    "需求",
    "输入",
    "输出",
    "发送",
    "接收",
    "左",
    "右",
    "两",
    "单",
    "双",
    "内",
    "外",
    "前",
    "后",
    "上",
    "下",
    "同",
    "对",
    "一",
    "另",
    "这",
    "那",
}

# Wrong measure-word pairings common in translated Chinese.
ZH_MEASURE_WORDS: list[tuple[str, str]] = [
    (
        r"[一二三四五六七八九十数几这那两]条(机制|选项|假设|证据|模型|方法|能力)",
        "改用「类」「个」「项」",
    ),
    (r"[一二三四五六七八九十数几]次(会计|核算|盘点)", "改为「一笔…账」或去掉量词"),
    (r"[一二三四五六七八九十数几]条(工作|论文|团队)", "改用「项」「篇」「个」"),
]

ZH_HEADING_ARTICLE_RE = re.compile(r"^(一个|一次|一条|一种|一项|一份)[^，。：]")
EN_HEADING_ARTICLE_RE = re.compile(r"^(A|An|The)\s+\w", re.IGNORECASE)

ZH_SIDE_RE = re.compile(r"([\u4e00-\u9fff]{1,4})侧")
ZH_SENTENCE_SPLIT_RE = re.compile(r"[。！？；]")
EN_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
CLAUSE_SPLIT_RE = re.compile(r"[，。！？；：、()（）]")
CJK_RE = re.compile(r"[\u4e00-\u9fff]")


# --- Extraction ------------------------------------------------------------


def extract_prose(text: str) -> tuple[list[tuple[int, str]], list[tuple[int, str]]]:
    """Split Markdown into (headings, prose_paragraphs).

    Skips YAML front matter, fenced code (including Mermaid), and table rows.
    Each paragraph is returned as (first_line_number, joined_text).
    """
    lines = text.split("\n")
    start = 0
    if lines and lines[0].strip() == "---":
        for idx in range(1, len(lines)):
            if lines[idx].strip() == "---":
                start = idx + 1
                break

    headings: list[tuple[int, str]] = []
    prose: list[tuple[int, str]] = []
    in_fence = False
    buffer: list[str] = []
    buffer_line = 0

    def flush() -> None:
        nonlocal buffer, buffer_line
        if buffer:
            prose.append((buffer_line, "".join(buffer)))
            buffer = []
            buffer_line = 0

    for offset, raw in enumerate(lines[start:], start=start + 1):
        stripped = raw.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            flush()
            continue
        if in_fence:
            continue
        if not stripped or stripped == "---":
            flush()
            continue
        if stripped.startswith("#"):
            flush()
            headings.append((offset, stripped.lstrip("#").strip()))
            continue
        if stripped.startswith("|"):
            flush()
            continue
        if not buffer:
            buffer_line = offset
        buffer.append(stripped)

    flush()
    return headings, prose


def detect_language(text: str) -> str:
    cjk = len(CJK_RE.findall(text))
    return "zh" if cjk > max(40, len(text) * 0.05) else "en"


# --- Checks ----------------------------------------------------------------


def _finding(
    kind: str, severity: str, line: int, match: str, hint: str, context: str
) -> dict[str, Any]:
    return {
        "type": kind,
        "severity": severity,
        "line": line,
        "match": match,
        "hint": hint,
        "context": context[:120],
    }


def check_headings(headings: list[tuple[int, str]], lang: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for line, title in headings:
        if lang == "zh":
            hit = ZH_HEADING_ARTICLE_RE.match(title)
            if hit:
                out.append(
                    _finding(
                        "article_calque",
                        "high",
                        line,
                        hit.group(1),
                        "中文标题不需要英文冠词结构，去掉数量词直接命名主题",
                        title,
                    )
                )
        else:
            hit = EN_HEADING_ARTICLE_RE.match(title)
            if hit:
                out.append(
                    _finding(
                        "heading_article",
                        "medium",
                        line,
                        hit.group(1),
                        "Drop the leading article in section titles",
                        title,
                    )
                )
    return out


def check_zh_prose(paragraphs: list[tuple[int, str]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    for line, para in paragraphs:
        for needle, suggestion in ZH_CALQUES:
            if needle in para:
                out.append(
                    _finding(
                        "calqued_metaphor",
                        "high",
                        line,
                        needle,
                        f"英文隐喻直译，改为：{suggestion}",
                        para,
                    )
                )

        for prefix in {m.group(1) for m in ZH_SIDE_RE.finditer(para)}:
            if prefix and prefix[-1:] not in ZH_SIDE_OK and prefix not in ZH_SIDE_OK:
                out.append(
                    _finding(
                        "side_calque",
                        "medium",
                        line,
                        f"{prefix}侧",
                        "英文 -side 直译，改为「在…方面」「从…出发」或直接点明主体",
                        para,
                    )
                )

        for pattern, suggestion in ZH_MEASURE_WORDS:
            hit = re.search(pattern, para)
            if hit:
                out.append(
                    _finding(
                        "measure_word",
                        "medium",
                        line,
                        hit.group(0),
                        f"量词搭配不当，{suggestion}",
                        para,
                    )
                )

        for clause in CLAUSE_SPLIT_RE.split(para):
            if clause.count("的") >= 4:
                out.append(
                    _finding(
                        "de_chain",
                        "medium",
                        line,
                        clause[:40],
                        "「的」连环修饰是译文腔，拆句或改用动词结构",
                        para,
                    )
                )
                break

        if para.count("被") >= 3:
            out.append(
                _finding(
                    "passive_stack",
                    "medium",
                    line,
                    f"被×{para.count('被')}",
                    "被动句堆叠，改为主动叙述或点明施动者",
                    para,
                )
            )

        if para.count("——") >= 3:
            out.append(
                _finding(
                    "dash_stack",
                    "medium",
                    line,
                    f"——×{para.count('——')}",
                    "破折号过密是英文行文习惯，改用逗号、分号、冒号或拆句",
                    para,
                )
            )

    return out


def check_sentence_length(
    paragraphs: list[tuple[int, str]], lang: str, limit: int
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    splitter = ZH_SENTENCE_SPLIT_RE if lang == "zh" else EN_SENTENCE_SPLIT_RE
    for line, para in paragraphs:
        for sentence in splitter.split(para):
            text = sentence.strip()
            if not text:
                continue
            length = len(text) if lang == "zh" else len(text.split())
            if length > limit:
                out.append(
                    _finding(
                        "long_sentence",
                        "medium",
                        line,
                        f"{length} 字" if lang == "zh" else f"{length} words",
                        "句子过长，按语义拆成短句",
                        text,
                    )
                )
    return out


def compute_stats(paragraphs: list[tuple[int, str]], lang: str) -> dict[str, Any]:
    body = "".join(p for _, p in paragraphs)
    total = max(1, len(body))
    splitter = ZH_SENTENCE_SPLIT_RE if lang == "zh" else EN_SENTENCE_SPLIT_RE
    sentences = [s for s in splitter.split(body) if s.strip()]
    return {
        "chars": len(body),
        "sentences": len(sentences),
        "avg_sentence_chars": round(len(body) / max(1, len(sentences)), 1),
        "dash_per_1k": round(body.count("——") / total * 1000, 1),
        "passive_per_1k": round(body.count("被") / total * 1000, 1),
    }


def lint_text(text: str, lang: str, limit: int) -> tuple[list[dict[str, Any]], dict]:
    headings, paragraphs = extract_prose(text)
    findings = check_headings(headings, lang)
    if lang == "zh":
        findings += check_zh_prose(paragraphs)
    findings += check_sentence_length(paragraphs, lang, limit)
    findings.sort(key=lambda f: (f["line"], f["type"]))
    return findings, compute_stats(paragraphs, lang)


# --- File discovery --------------------------------------------------------


def find_files(workspace: Path, mode: str | None, file_path: Path | None) -> list[Path]:
    if file_path is not None:
        return [file_path] if file_path.exists() else []

    modes = [mode] if mode else ["survey", "report", "manuscript", "brief"]
    files: list[Path] = []
    for m in modes:
        mode_dir = workspace / "docs" / str(m)
        if not mode_dir.exists():
            continue
        chapters = mode_dir / "chapters"
        if chapters.exists():
            files.extend(sorted(chapters.glob("*.md")))
        else:
            files.extend(
                f for f in sorted(mode_dir.glob("*.md")) if not f.name.startswith("_")
            )
    return files


def load_allowlist(workspace: Path, explicit: Path | None) -> list[str]:
    candidates = (
        [explicit] if explicit else [workspace / ".omr" / "prose-lint-allow.txt"]
    )
    for path in candidates:
        if path and path.exists():
            return [
                line.strip()
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.startswith("#")
            ]
    return []


# --- CLI -------------------------------------------------------------------


def main() -> int:
    p = argparse.ArgumentParser(description="OMR native-expression linter")
    p.add_argument("--workspace", type=Path, default=Path.cwd())
    p.add_argument("--mode", default=None, help="survey/report/manuscript/brief")
    p.add_argument("--file", type=Path, default=None, help="lint a specific file")
    p.add_argument("--lang", default=None, help="zh or en (default: auto-detect)")
    p.add_argument("--max-sentence", type=int, default=100, help="sentence length cap")
    p.add_argument("--allow", type=Path, default=None, help="allowlist file")
    p.add_argument("--strict", action="store_true", help="fail on medium findings too")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    args = p.parse_args()

    ws = args.workspace.resolve()
    files = find_files(ws, args.mode, args.file)
    if not files:
        if args.json:
            print(json.dumps({"files": [], "total_findings": 0, "clean": True}))
        else:
            print("No report files found to lint.")
        return 0

    allow = load_allowlist(ws, args.allow)
    results: list[dict[str, Any]] = []
    high = medium = 0

    for path in files:
        text = path.read_text(encoding="utf-8", errors="ignore")
        lang = args.lang or detect_language(text)
        findings, stats = lint_text(text, lang, args.max_sentence)
        findings = [
            f
            for f in findings
            if not any(term and term in f["context"] for term in allow)
        ]
        high += sum(1 for f in findings if f["severity"] == "high")
        medium += sum(1 for f in findings if f["severity"] == "medium")
        rel = str(path.relative_to(ws)) if path.is_relative_to(ws) else str(path)
        results.append(
            {"file": rel, "language": lang, "stats": stats, "findings": findings}
        )

    total = high + medium
    failed = high > 0 or (args.strict and total > 0)

    if args.json:
        print(
            json.dumps(
                {
                    "files": results,
                    "high": high,
                    "medium": medium,
                    "total_findings": total,
                    "clean": total == 0,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1 if failed else 0

    if total == 0:
        print(f"✓ {len(files)} file(s) scanned — no translationese findings.")
        return 0

    mark = "✗" if failed else "!"
    print(f"{mark} {len(files)} file(s) scanned — {high} high, {medium} medium:\n")
    for item in results:
        if not item["findings"]:
            continue
        st = item["stats"]
        print(
            f"  {item['file']} [{item['language']}] "
            f"avg_sentence={st['avg_sentence_chars']} "
            f"dash/1k={st['dash_per_1k']} passive/1k={st['passive_per_1k']}"
        )
        for f in item["findings"]:
            print(f"    L{f['line']} [{f['severity']}/{f['type']}] {f['match']}")
            print(f"      → {f['hint']}")
        print()

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
