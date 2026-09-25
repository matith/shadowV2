# -*- coding: utf-8 -*-
"""Extract P0 module contracts from BBM canonical (read-only)."""
import json
import os
import sys

ROOT = r"D:\LIB\mimo\shadowV2\blackbox\generations\g000259"
OUT = r"D:\LIB\mimo\shadowV2\tmp_extract"
os.makedirs(OUT, exist_ok=True)

plan = json.load(open(os.path.join(ROOT, "planning", "plan-versions", "plan-p0-v3.json"), encoding="utf-8"))
mods = plan["affected_module_ids"]
print("P0 modules:", len(mods))

# load all module summaries + latest revision
payload = []
for m in mods:
    sp = os.path.join(ROOT, "modules", m, "summary.json")
    rp_dir = os.path.join(ROOT, "modules", m, "revisions")
    item = {"id": m}
    if os.path.exists(sp):
        item["summary"] = json.load(open(sp, encoding="utf-8"))
    revs = sorted(os.listdir(rp_dir)) if os.path.isdir(rp_dir) else []
    if revs:
        item["revision"] = json.load(open(os.path.join(rp_dir, revs[-1]), encoding="utf-8"))
    payload.append(item)

# boundary contracts
bc_dir = os.path.join(ROOT, "boundary")
contracts = []
if os.path.isdir(bc_dir):
    for name in sorted(os.listdir(bc_dir)):
        cur = os.path.join(bc_dir, name, "current.json")
        if os.path.exists(cur):
            contracts.append(json.load(open(cur, encoding="utf-8")))

# acceptance criteria
ac_dir = os.path.join(ROOT, "planning", "acceptance", "criteria")
acs = {}
for name in sorted(os.listdir(ac_dir)):
    if name.endswith(".json") and name != "index.json":
        acs[name[:-5]] = json.load(open(os.path.join(ac_dir, name), encoding="utf-8"))

# decisions
dec_dir = os.path.join(ROOT, "planning", "decisions")
decs = {}
for name in sorted(os.listdir(dec_dir)):
    if name.endswith(".json") and name != "index.json":
        decs[name[:-5]] = json.load(open(os.path.join(dec_dir, name), encoding="utf-8"))

out = {
    "plan": plan,
    "modules": payload,
    "boundary_contracts": contracts,
    "acceptance": acs,
    "decisions": decs,
}
path = os.path.join(OUT, "p0_contracts.json")
with open(path, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print("wrote", path)

# compact console digest
for item in payload:
    m = item["id"]
    s = item.get("summary") or {}
    r = item.get("revision") or {}
    print("\n===", m, "===")
    for k in ("name", "title", "display_name", "status", "purpose", "responsibility"):
        if k in s:
            print(f"  {k}: {str(s[k])[:200]}")
        elif k in r:
            print(f"  {k}: {str(r[k])[:200]}")
    # interfaces often nested
    for k in ("interfaces", "inputs", "outputs", "contract", "contracts", "acceptance_ids", "notes"):
        src = s if k in s else (r if k in r else None)
        if src is not None:
            v = src[k]
            print(f"  {k}:", json.dumps(v, ensure_ascii=False)[:400])
print("\nboundary contracts:", len(contracts))
for c in contracts[:20]:
    print(" -", c.get("id") or c.get("name"), c.get("relation_type") or c.get("type"))
print("\nacceptance:", list(acs.keys()))
print("decisions:", list(decs.keys()))
