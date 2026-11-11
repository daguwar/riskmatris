"""Regression guard: every ESM named import in static/ must resolve to a real
export in the target module.

A mismatched import (e.g. importing a non-exported helper) is a module *link*
error: the browser refuses to execute the whole module graph, so every event
handler dies silently and forms fall back to native submits. pytest cannot see
this – this test can.
"""

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "static"

IMPORT_RE = re.compile(r"import\s*\{([^}]*)\}\s*from\s*[\"']([^\"']+)[\"']", re.S)
EXPORT_DECL_RE = re.compile(r"export\s+(?:async\s+)?(?:function|const|let|var|class)\s+([A-Za-z0-9_]+)")
EXPORT_LIST_RE = re.compile(r"export\s*\{([^}]*)\}", re.S)


def _exports_of(path: Path) -> set[str]:
    src = path.read_text(encoding="utf-8")
    names = set(EXPORT_DECL_RE.findall(src))
    for m in EXPORT_LIST_RE.finditer(src):
        names |= {x.strip() for x in m.group(1).split(",") if x.strip()}
    return names


def test_all_named_imports_resolve():
    js_files = sorted(STATIC.rglob("*.js"))
    assert js_files, "no JS files found under static/"
    exports = {f.resolve(): _exports_of(f) for f in js_files}
    problems = []
    for f in js_files:
        src = f.read_text(encoding="utf-8")
        for m in IMPORT_RE.finditer(src):
            names = [n.strip().split(" as ")[0].strip() for n in m.group(1).split(",") if n.strip()]
            target = (f.parent / m.group(2)).resolve()
            if target not in exports:
                problems.append(f"{f.relative_to(STATIC)}: cannot resolve {m.group(2)}")
                continue
            for n in names:
                if n not in exports[target]:
                    problems.append(f"{f.relative_to(STATIC)}: '{n}' is not exported by {target.name}")
    assert not problems, "Unresolved ESM imports:\n" + "\n".join(problems)
