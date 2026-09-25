# -*- coding: utf-8 -*-
"""Dump compact P0 interface digest for implementation."""
import json
import os

ROOT = r"D:\LIB\mimo\shadowV2\blackbox\generations\g000259"
OUT = r"D:\LIB\mimo\shadowV2\tmp_extract\p0_digest.md"

plan = json.load(open(os.path.join(ROOT, "planning", "plan-versions", "plan-p0-v3.json"), encoding="utf-8"))
mods = plan["affected_module_ids"]

lines = ["# P0 Digest\n", "## Acceptance\n"]
for ac_id in ["ac-a", "ac-c", "ac-e", "ac-x1", "ac-x2", "ac-x3", "ac-x4", "ac-x5", "ac-x6", "ac-x7", "ac-x8"]:
    p = os.path.join(ROOT, "planning", "acceptance", "criteria", ac_id + ".json")
    if os.path.exists(p):
        ac = json.load(open(p, encoding="utf-8"))
        lines.append(f"### {ac_id}\n{ac.get('description','')}\nstatus={ac.get('status')}\n")

lines.append("\n## Decisions\n")
dec_dir = os.path.join(ROOT, "planning", "decisions")
for name in sorted(os.listdir(dec_dir)):
    if name.endswith(".json") and name != "index.json":
        d = json.load(open(os.path.join(dec_dir, name), encoding="utf-8"))
        lines.append(f"### {name[:-5]}\n")
        for k, v in d.items():
            if k in ("id", "title", "decision", "statement", "rationale", "consequences", "status"):
                lines.append(f"- **{k}**: {json.dumps(v, ensure_ascii=False)[:500]}")
        lines.append("")

lines.append("\n## Modules\n")
for m in mods:
    lines.append(f"\n## {m}\n")
    sp = os.path.join(ROOT, "modules", m, "summary.json")
    if os.path.exists(sp):
        s = json.load(open(sp, encoding="utf-8"))
        lines.append(f"summary: {s.get('text','')}\n")
    rp_dir = os.path.join(ROOT, "modules", m, "revisions")
    if not os.path.isdir(rp_dir):
        continue
    revs = sorted(os.listdir(rp_dir))
    r = json.load(open(os.path.join(rp_dir, revs[-1]), encoding="utf-8"))
    spec = r.get("spec") or {}
    lines.append(f"revision={r.get('revision')}\n")
    if "purpose" in spec:
        lines.append(f"purpose: {spec['purpose']}\n")
    custom = spec.get("custom") or {}
    for k in ("responsibilities", "actions", "in_scope", "out_of_scope", "real_scenarios", "interfaces", "io", "invariants", "failure_modes", "notes"):
        if k in custom:
            lines.append(f"{k}: {json.dumps(custom[k], ensure_ascii=False)}\n")
    for k in ("constraints",):
        if k in spec:
            lines.append(f"{k}: {json.dumps(spec[k], ensure_ascii=False)[:600]}\n")

# boundary relations content
lines.append("\n## Boundary Relations\n")
rel_dir = os.path.join(ROOT, "relations")
for name in sorted(os.listdir(rel_dir)):
    if not name.endswith(".json"):
        continue
    rel = json.load(open(os.path.join(rel_dir, name), encoding="utf-8"))
    lines.append(f"- {name}: {json.dumps(rel, ensure_ascii=False)[:400]}\n")

# boundary contract files
lines.append("\n## Boundary Contracts (current)\n")
bc = os.path.join(ROOT, "boundary")
for name in sorted(os.listdir(bc)):
    cur = os.path.join(bc, name, "current.json")
    revs_dir = os.path.join(bc, name, "revisions")
    content = {}
    if os.path.exists(cur):
        content["current"] = json.load(open(cur, encoding="utf-8"))
    if os.path.isdir(revs_dir):
        rs = sorted(os.listdir(revs_dir))
        if rs:
            content["revision"] = json.load(open(os.path.join(revs_dir, rs[-1]), encoding="utf-8"))
    lines.append(f"\n### {name}\n{json.dumps(content, ensure_ascii=False)[:800]}\n")

with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print("wrote", OUT, "lines", len(lines))
