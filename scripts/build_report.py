"""Generate current facts from metadata/evidence, then compile LaTeX twice."""

import hashlib
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
extended_ai = json.loads((ROOT / "evidence/ai_evaluation.json").read_text(encoding="utf-8"))
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
    "AIShiftFalseAlarm": f"{100 * extended_ai['datasets']['shifted_normal']['isolation_forest']['false_positive_rate']:.2f}",
    "AIRarePrecision": f"{100 * extended_ai['datasets']['rare_anomaly']['isolation_forest']['precision']:.2f}",
    "AIExtendedMean": f"{extended_ai['inference_ms']['mean']:.3f}",
    "AIExtendedPninetyFive": f"{extended_ai['inference_ms']['p95']:.3f}",
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
comparison = [
    r"\begin{longtable}{P{3.9cm}P{2.7cm}r r r r}",
    r"\caption{Model cố định so với luật ngưỡng; toàn bộ là dữ liệu sinh}\label{tab:ai-comparison}\\",
    r"\toprule Tập đánh giá & Phương pháp & Acc. (\%) & Recall (\%) & FPR (\%) & F1 \\ \midrule",
    r"\endfirsthead",
    r"\toprule Tập đánh giá & Phương pháp & Acc. (\%) & Recall (\%) & FPR (\%) & F1 \\ \midrule",
    r"\endhead",
]
for key, label in [
    ("reference", "Gốc, 1.200 mẫu"),
    ("fresh_same_distribution", "Năm seed mới, 6.000 mẫu"),
    ("rare_anomaly", "Bất thường hiếm, 2.040 mẫu"),
    ("shifted_normal", "Normal dịch phân bố, 1.000 mẫu"),
    ("unseen_cold", "Lạnh bất thường, 300 mẫu"),
]:
    for method, name in [("isolation_forest", "Isolation Forest"), ("threshold", "Ngưỡng 32/80")]:
        m = extended_ai["datasets"][key][method]
        recall = f"{100*m['recall']:.2f}" if m["anomalous"] else "---"
        fpr = f"{100*m['false_positive_rate']:.2f}" if m["normal"] else "---"
        f1 = f"{m['f1']:.4f}" if m["anomalous"] else "---"
        comparison.append(f"{label} & {name} & {100*m['accuracy']:.2f} & {recall} & {fpr} & {f1}" + r" \\")
comparison.extend([r"\bottomrule", r"\end{longtable}"])
(report / "ai_evaluation.tex").write_text("\n".join(comparison) + "\n", encoding="utf-8")
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
coreiot_image_files = [
    "SmartRoom_Dashboard.png",
    "Rule_chains_root.png",
    "Rule_chains_SmartRoom_alarms.png",
    "Notification.png",
    "SmartRoom_Dashboard_20261126.png",
]
embedded_sizes = {(item[2], item[3]) for page in document for item in page.get_images()}
coreiot_images = {}
for name in coreiot_image_files:
    path = ROOT / "evidence/coreiot" / name
    if path.exists():
        pixmap = pymupdf.Pixmap(str(path))
        coreiot_images[name] = (pixmap.width, pixmap.height) in embedded_sizes
if not all(coreiot_images.values()):
    raise SystemExit("A supplied CoreIOT screenshot is missing from the compiled PDF")
new_images = {}
for name in ["dashboard_current_desktop.png", "ai_comparison.png", "ai_decision_regions.png"]:
    pixmap = pymupdf.Pixmap(str(ROOT / "evidence" / name))
    new_images[name] = (pixmap.width, pixmap.height) in embedded_sizes
if not all(new_images.values()):
    raise SystemExit("A current switch/AI figure is missing from the compiled PDF")
ai_card_titles = ["AI Availability", "Anomaly Score", "Anomaly Detection", "Inference Time", "Data Source"]
ai_cards_documented = {title: re.sub(r"\s+", "", title) in text for title in ai_card_titles}
if not all(ai_cards_documented.values()):
    raise SystemExit("Updated CoreIOT AI cards are missing from the PDF")
dashboard_audit = json.loads((ROOT / "evidence/coreiot_dashboard_ai_check.json").read_text(encoding="utf-8"))
dashboard_export = ROOT / "evidence/coreiot/smartroom_dashboard_20261126.json"
if dashboard_audit["failed"] or hashlib.sha256(dashboard_export.read_bytes()).hexdigest() != dashboard_audit["source_sha256"]:
    raise SystemExit("Current dashboard export does not match its successful configuration audit")
(ROOT / "evidence/report_check.json").write_text(
    json.dumps(
        {
            "pages": len(document),
            "latex_issues": issues,
            "metadata_checked": True,
            "source": "report/main.tex",
            "coreiot_images_embedded": coreiot_images,
            "updated_figures_embedded": new_images,
            "report_date": meta["report_date"],
            "test_count": int(suite.get("tests")),
            "ai_model_sha256": extended_ai["model_sha256"],
            "coreiot_ai_cards_documented": ai_cards_documented,
            "latest_coreiot_screenshot_available": "SmartRoom_Dashboard_20261126.png" in coreiot_images,
            "latest_coreiot_export_verified": True,
            "latest_coreiot_config_checks_passed": dashboard_audit["passed"],
        },
        indent=2,
    ),
    encoding="utf-8",
)
if issues:
    raise SystemExit("PDF built but layout/references need attention: " + "; ".join(issues))
print(destination)
