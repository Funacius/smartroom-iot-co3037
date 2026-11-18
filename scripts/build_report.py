"""Generate current facts from metadata/evidence, then compile LaTeX twice."""

import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path
import pymupdf

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
report = ROOT / "report"
build = report / "build"
build.mkdir(exist_ok=True)


def escape(s):
    replace = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replace.get(c, c) for c in str(s))


meta = json.loads((report / "metadata.json").read_text(encoding="utf-8"))
ai = json.loads((ROOT / "evidence/ai_metrics.json").read_text(encoding="utf-8"))
bench = json.loads((ROOT / "evidence/software_metrics.json").read_text(encoding="utf-8"))
suite = ET.parse(ROOT / "evidence/pytest.xml").getroot().find("testsuite")
macros = {
    "ClassCode": meta["class_code"],
    "GroupCode": meta["group_code"],
    "Instructor": meta["instructor"],
    "ReportDate": meta["report_date"],
    "VideoLink": meta["video"],
    "DashboardLink": meta["dashboard"],
    "RepoURL": meta["repository"],
    "TestCount": suite.get("tests"),
    "TestFailures": suite.get("failures"),
    "AIAccuracy": f"{100 * ai['classification']['accuracy']:.2f}",
    "AIPrecision": f"{100 * ai['classification']['1']['precision']:.2f}",
    "AIRecall": f"{100 * ai['classification']['1']['recall']:.2f}",
    "AIFone": f"{ai['classification']['1']['f1-score']:.4f}",
    "AITrainCount": ai["training_normal_samples"],
    "AITestCount": ai["test_samples"],
}
for i, member in enumerate(meta["members"], 1):
    for key, suffix in [("name", "Name"), ("student_id", "ID"), ("email", "Email")]:
        macros[f"Member{'One' if i == 1 else 'Two'}{suffix}"] = member[key]
for prefix, data in [
    ("Ingest", bench["metrics"]["ingest_sqlite_ms"]),
    ("Snapshot", bench["metrics"]["snapshot_ms"]),
    ("Inference", ai["inference_ms"]),
]:
    for key in ["n", "mean", "min", "max", "p95"]:
        macros[prefix + key.capitalize().replace("95", "NinetyFive")] = (
            str(data[key]) if key == "n" else f"{data[key]:.3f}"
        )
cm = ai["confusion_matrix"]
for name, value in zip(
    ["TrueNegative", "FalsePositive", "FalseNegative", "TruePositive"],
    [cm[0][0], cm[0][1], cm[1][0], cm[1][1]],
):
    macros[name] = value
(report / "generated.tex").write_text(
    "\n".join("\\newcommand{\\" + name + "}{" + escape(value) + "}" for name, value in macros.items()) + "\n",
    encoding="utf-8",
)
subprocess.run([sys.executable, "scripts/make_figures.py"], check=True)
engine = shutil.which("xelatex")
if not engine:
    raise SystemExit("XeLaTeX not found; install MiKTeX or TeX Live")
for iteration in (1, 2):
    run = subprocess.run(
        [
            engine,
            "-interaction=nonstopmode",
            "-halt-on-error",
            "-file-line-error",
            "-output-directory=build",
            "main.tex",
        ],
        cwd=report,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    (ROOT / f"evidence/xelatex_pass{iteration}.log").write_text(run.stdout + run.stderr, encoding="utf-8")
    if run.returncode:
        print(run.stdout[-7000:])
        raise SystemExit(f"XeLaTeX pass {iteration} failed; see evidence log")
group = (
    "CHUA_CAP_MA_NHOM"
    if meta["group_code"] == "Chưa được cấp"
    else re.sub(
        r"[^A-Za-z0-9_-]+",
        "_",
        unicodedata.normalize("NFKD", meta["group_code"]).encode("ascii", "ignore").decode(),
    ).strip("_")
)
filename = f"{meta['class_code']}_{group}_IoTReport.pdf"
destination = report / filename
shutil.copy2(build / "main.pdf", destination)
document = pymupdf.open(destination)
text = re.sub(r"\s+", "", "\n".join(page.get_text() for page in document))
for expected in [meta["instructor"], meta["class_code"]] + [
    m[k] for m in meta["members"] for k in ("name", "student_id", "email")
]:
    if re.sub(r"\s+", "", expected) not in text:
        raise SystemExit(f"PDF is missing metadata: {expected}")
log = (build / "main.log").read_text(encoding="utf-8", errors="replace")
issues = [
    line
    for line in log.splitlines()
    if any(
        word in line for word in ("Overfull", "Missing character", "undefined", "ignored error", "Warning:")
    )
]
(ROOT / "evidence/report_check.json").write_text(
    json.dumps(
        {
            "pages": len(document),
            "latex_issues": issues,
            "metadata_checked": True,
            "source": "report/main.tex",
        },
        indent=2,
    ),
    encoding="utf-8",
)
if issues:
    raise SystemExit("PDF built but layout/references need attention: " + "; ".join(issues))
print(destination)
