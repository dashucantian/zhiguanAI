# -*- coding: utf-8 -*-
"""Read-only npz structure audit. Does NOT modify any audited file."""
import io, json, os, sys, zipfile, traceback
import numpy as np

STAGING = r"D:\Project\zhiguanAI\muse2-repo\muse2-master\report"
RAW = r"D:\Project\Zen-EEG\02_raw"
QC = r"D:\Project\Zen-EEG\03_quality_control"

def npy_header(zf, member):
    """Read only the .npy header of a zip member -> (shape, dtype, fortran_order)."""
    with zf.open(member) as f:
        version = np.lib.format.read_magic(f)
        shape, fortran, dtype = np.lib.format._read_array_header(f, version)
    return shape, str(dtype), fortran

def load_meta(path):
    """Load only the 'meta' member and return it as a dict (or None)."""
    try:
        with np.load(path, allow_pickle=True) as z:
            if 'meta' not in z.files:
                return None, None
            m = z['meta']
            if isinstance(m, np.ndarray):
                m = m[()] if m.shape == () else m.tolist()
            if hasattr(m, 'item') and not isinstance(m, dict):
                try:
                    m = m.item()
                except Exception:
                    pass
            return m, None
    except Exception as e:
        return None, "%s: %s" % (type(e).__name__, e)

def probe(path):
    rec = {"path": path, "size": os.path.getsize(path), "error": None,
           "keys": None, "arrays": {}, "meta": None, "meta_error": None,
           "n_members": None}
    try:
        with zipfile.ZipFile(path, 'r') as zf:
            members = [n for n in zf.namelist() if n.endswith('.npy')]
            rec["n_members"] = len(members)
            rec["keys"] = sorted(os.path.basename(m)[:-4] for m in members)
            for m in members:
                k = os.path.basename(m)[:-4]
                try:
                    shape, dt, fortran = npy_header(zf, m)
                    rec["arrays"][k] = {"shape": list(shape), "dtype": dt,
                                        "fortran": fortran,
                                        "uncompressed_bytes": zf.getinfo(m).file_size}
                except Exception as e:
                    rec["arrays"][k] = {"error": "%s: %s" % (type(e).__name__, e)}
    except Exception as e:
        rec["error"] = "%s: %s" % (type(e).__name__, e)
        return rec
    meta, merr = load_meta(path)
    rec["meta"] = meta
    rec["meta_error"] = merr
    return rec

def collect(root, label, recursive=True):
    out = []
    if recursive:
        for dp, dn, fn in os.walk(root):
            for f in fn:
                if f.lower().endswith('.npz'):
                    out.append((label, os.path.join(dp, f)))
    else:
        for f in os.listdir(root):
            if f.lower().endswith('.npz'):
                out.append((label, os.path.join(root, f)))
    return out

items = []
items += collect(RAW, "02_raw")
items += collect(QC, "03_qc")
items += collect(STAGING, "staging", recursive=False)
items.sort(key=lambda x: (x[0], x[1]))

print("=" * 100)
print("NPZ INVENTORY  (total found: %d)" % len(items))
print("=" * 100)
from collections import Counter
print("by source:", dict(Counter(l for l, _ in items)))
print()

results = []
for label, p in items:
    r = probe(p)
    r["source"] = label
    results.append(r)

with open(r"D:\Project\zhiguanAI\_analysis_tmp\npz_scan.json", "w", encoding="utf-8") as fh:
    json.dump(results, fh, ensure_ascii=False, indent=1, default=str)

# ---- key signature table ----
print("=" * 100)
print("KEY SIGNATURE DISTRIBUTION")
print("=" * 100)
sig = Counter()
for r in results:
    if r["keys"] is None:
        sig["ERROR:" + str(r["error"])] += 1
    else:
        sig[",".join(r["keys"])] += 1
for k, v in sig.most_common():
    print("  %-60s x%d" % (k, v))
print()

print("=" * 100)
print("PER-FILE DETAIL (arrays: shape/dtype)")
print("=" * 100)
for r in results:
    rel = r["path"]
    print("-" * 100)
    print("[%s] %s" % (r["source"], rel))
    print("    size=%d bytes  members=%s  keys=%s" % (r["size"], r["n_members"], r["keys"]))
    if r["error"]:
        print("    ZIP ERROR: %s" % r["error"])
    for k, v in sorted(r["arrays"].items()):
        print("      %-18s %s" % (k, v))
    if r["meta_error"]:
        print("    META ERROR: %s" % r["meta_error"])
    if isinstance(r["meta"], dict):
        print("    meta (%d fields):" % len(r["meta"]))
        for k in sorted(r["meta"].keys()):
            print("        %-28s = %r" % (k, r["meta"][k]))
    elif r["meta"] is not None:
        print("    meta (non-dict %s): %r" % (type(r["meta"]).__name__, r["meta"]))
    else:
        print("    meta: ABSENT")
print()
print("DONE. wrote npz_scan.json")
