"""Read-only consistency checker for ACE_MASTER_PLAN.md.

Run after every edit of the master plan:  python tools/dev/check_plan.py
Checks: balanced code fences, heading hierarchy, §-references, unique and defined IDs
(FR / NFR / D / SC / R / milestones), and that every stage S00-S45 has all template fields.
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

REQUIRED_STAGE_FIELDS = [
    "**Goal:**",
    "**Prereqs:**",
    "**Spec:**",
    "**Tasks:**",
    "**Acceptance criteria",
    "**Tests:**",
    "**Definition of Done:**",
    "**[VERIFY]:**",
    "**Pitfalls:**",
]
LAST_STAGE = 45
LAST_SECTION = 24


def table_ids(text: str, pattern: str) -> list[str]:
    return re.findall(rf"^\| ({pattern}) \|", text, re.M)


def check(text: str) -> list[str]:
    problems: list[str] = []
    lines = text.splitlines()

    # Code fences and heading hierarchy (headings inside code blocks are ignored).
    fences = [line for line in lines if line.strip().startswith("```")]
    if len(fences) % 2:
        problems.append(f"Unbalanced code fences: {len(fences)}")
    in_code, prev_level = False, 1
    for line in lines:
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        heading = None if in_code else re.match(r"^(#{1,6}) ", line)
        if heading:
            level = len(heading.group(1))
            if level > prev_level + 1:
                problems.append(f"Heading jump to H{level} after H{prev_level}: {line[:60]}")
            prev_level = level

    # Sections and §-references.
    for n in range(LAST_SECTION + 1):
        if not re.search(rf"^## §{n} ", text, re.M):
            problems.append(f"Missing section heading §{n}")
    for major, minor in sorted(set(re.findall(r"§(\d+)\.(\d+)", text))):
        if not re.search(rf"^### {major}\.{minor} ", text, re.M):
            problems.append(f"Reference §{major}.{minor} has no '### {major}.{minor}' heading")
    for ref in sorted(set(re.findall(r"§(\d+)(?![\d.])", text)), key=int):
        if not re.search(rf"^## §{ref} ", text, re.M):
            problems.append(f"Reference §{ref} has no section")

    # IDs: unique definitions, and every reference is defined.
    kinds = {
        "FR": r"FR-[A-Z]+(?:-[A-Z]+)?-\d+",
        "D": r"D-\d\d",
        "SC": r"SC-\d\d",
        "R": r"R-\d+",
    }
    for kind, pattern in kinds.items():
        defined = table_ids(text, pattern)
        duplicates = [i for i, c in Counter(defined).items() if c > 1]
        if duplicates:
            problems.append(f"Duplicate {kind} definitions: {duplicates}")
        for ref in sorted(set(re.findall(rf"\b{pattern}\b", text))):
            if ref not in set(defined):
                problems.append(f"Undefined {kind} referenced: {ref}")
    nfr_defined = set(re.findall(r"^\| (NFR-\d+)", text, re.M))
    for ref in sorted(set(re.findall(r"\bNFR-\d+\b", text))):
        if ref not in nfr_defined:
            problems.append(f"Undefined NFR referenced: {ref}")
    for m in range(1, 7):
        if not re.search(rf"^\| M{m} \|", text, re.M):
            problems.append(f"Milestone M{m} not defined")

    # Stages: present once, in order, with every template field and checklist items.
    heads = re.findall(r"^### (S\d\d) — ", text, re.M)
    expected = [f"S{i:02d}" for i in range(LAST_STAGE + 1)]
    if heads != expected:
        problems.append(f"Stage headings mismatch: {heads}")
    parts = re.split(r"^### (S\d\d) — ", text, flags=re.M)
    for i in range(1, len(parts), 2):
        stage_id, body = parts[i], parts[i + 1].split("\n## ")[0]
        problems += [f"{stage_id} missing {f}" for f in REQUIRED_STAGE_FIELDS if f not in body]
        if "- [ ]" not in body:
            problems.append(f"{stage_id} has no acceptance checklist items")
    for ref in sorted(set(re.findall(r"\bS(\d\d)\b", text))):
        if int(ref) > LAST_STAGE:
            problems.append(f"Reference to non-existent stage S{ref}")
    for line in lines:
        if line.startswith("| FR-"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if not re.search(r"S\d\d", cells[-1]):
                problems.append(f"FR row without a stage: {cells[0]}")
    return problems


def main() -> int:
    default = Path(__file__).resolve().parents[2] / "ACE_MASTER_PLAN.md"
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else default
    text = path.read_text(encoding="utf-8")
    problems = check(text)
    counts = {
        "FR": len(table_ids(text, r"FR-[A-Z]+(?:-[A-Z]+)?-\d+")),
        "D": len(table_ids(text, r"D-\d\d")),
        "SC": len(table_ids(text, r"SC-\d\d")),
        "R": len(table_ids(text, r"R-\d+")),
        "Stages": len(re.findall(r"^### S\d\d — ", text, re.M)),
    }
    print(f"{path.name}: {len(text.splitlines())} lines | " + " | ".join(f"{k} {v}" for k, v in counts.items()))
    if problems:
        print(f"PROBLEMS ({len(problems)}):")
        for p in problems:
            print(" -", p)
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
