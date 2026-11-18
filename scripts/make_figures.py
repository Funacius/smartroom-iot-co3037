"""Create report-native diagrams; these depict proposed wiring, not board photos."""

from pathlib import Path
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "report/figures"
OUT.mkdir(parents=True, exist_ok=True)


def box(ax, x, y, w, h, text, color="#e4efe8"):
    patch = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle="round,pad=0.02,rounding_size=0.08",
        facecolor=color,
        edgecolor="#34614c",
        linewidth=1.4,
    )
    ax.add_patch(patch)
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=10, color="#153e2b")


def arrow(ax, start, end, label="", bi=True):
    ax.add_patch(
        FancyArrowPatch(
            start, end, arrowstyle="<->" if bi else "->", mutation_scale=14, color="#366a51", linewidth=1.5
        )
    )
    ax.text(
        (start[0] + end[0]) / 2,
        (start[1] + end[1]) / 2 + 0.16,
        label,
        ha="center",
        fontsize=9,
        color="#355249",
    )


fig, ax = plt.subplots(figsize=(10, 5.5))
ax.set(xlim=(0, 12), ylim=(0, 6))
ax.axis("off")
box(ax, 0.2, 3.6, 2, 1.5, "Node A / YoloUNO\nDHT20 (I2C)\nFan driver (GPIO)")
box(ax, 3.4, 3.6, 2, 1.5, "Node B / YoloUNO\nESP-NOW bridge\nLocal web server")
box(ax, 6.7, 3.6, 2, 1.5, "PC gateway\nPython + SQLite\nIsolation Forest")
box(ax, 9.8, 3.6, 2, 1.5, "CoreIOT\nGateway + child\nDashboard / alarms")
arrow(ax, (2.25, 4.35), (3.35, 4.35), "ESP-NOW")
arrow(ax, (5.45, 4.35), (6.65, 4.35), "USB JSONL")
arrow(ax, (8.75, 4.35), (9.75, 4.35), "MQTT/TLS")
box(ax, 3.4, 0.8, 2, 1.2, "Browser on AP\n192.168.4.1", "#f0f3e4")
box(ax, 6.7, 0.8, 2, 1.2, "Local dashboard\n127.0.0.1:8080", "#f0f3e4")
arrow(ax, (4.4, 2.05), (4.4, 3.55), "HTTP")
arrow(ax, (7.7, 2.05), (7.7, 3.55), "HTTP")
ax.text(
    6,
    0.25,
    "Telemetry: A -> B -> PC -> CoreIOT   |   Control + device ACK: reverse path",
    ha="center",
    fontsize=10,
)
fig.tight_layout()
fig.savefig(OUT / "architecture.png", dpi=200)
plt.close(fig)

fig, ax = plt.subplots(figsize=(10, 5))
ax.set(xlim=(0, 12), ylim=(0, 6))
ax.axis("off")
box(ax, 4.4, 4.6, 3.2, 1, "SmartRoom")
for x, title, detail in [
    (0.1, "F01: acquisition", "DHT20 -> validate -> radio"),
    (3.15, "F02: monitoring", "USB -> SQLite -> chart"),
    (6.2, "F03/F04: events", "AI + threshold -> journal"),
    (9.25, "F05/F06: remote", "RPC -> ACK -> cloud"),
]:
    box(ax, x, 2.6, 2.65, 1, title)
    box(ax, x, 0.7, 2.65, 1.15, detail)
    arrow(ax, (6, 4.55), (x + 1.325, 3.65), bi=False)
    arrow(ax, (x + 1.325, 2.55), (x + 1.325, 1.9), bi=False)
fig.tight_layout()
fig.savefig(OUT / "decomposition.png", dpi=200)
plt.close(fig)

fig, ax = plt.subplots(figsize=(10, 5))
ax.set(xlim=(0, 12), ylim=(0, 6))
ax.axis("off")
box(
    ax,
    0.4,
    2.3,
    2.7,
    2.3,
    "YoloUNO Node A\n\nGPIO11 (proposed SDA)\nGPIO12 (proposed SCL)\nGPIO6 (driver input)\nGND",
)
box(ax, 5, 3.7, 2.7, 1.1, "DHT20 module\nSDA / SCL / 3V3 / GND")
box(ax, 5, 1.7, 2.7, 1.1, "3.3 V logic driver\nIN / GND / DC supply")
box(ax, 9, 1.7, 2.3, 1.1, "Low-voltage fan\nDC supply via driver")
arrow(ax, (3.15, 4.25), (4.95, 4.25), "I2C", bi=False)
arrow(ax, (3.15, 2.7), (4.95, 2.25), "GPIO", bi=False)
arrow(ax, (7.75, 2.25), (8.95, 2.25), "Power", bi=False)
ax.text(
    6,
    0.6,
    "PROPOSED WIRING — verify actual board pinout/revision and module supply.\nNot a photograph or verified physical assembly. Fan is never powered from GPIO.",
    ha="center",
    fontsize=10,
    color="#8c5221",
)
fig.tight_layout()
fig.savefig(OUT / "wiring_proposed.png", dpi=200)
plt.close(fig)

fig, ax = plt.subplots(figsize=(10, 3.4))
ax.set(xlim=(0, 12), ylim=(0, 4))
ax.axis("off")
box(ax, 0.3, 1.6, 2.2, 1, "PENDING")
box(ax, 4.6, 2.5, 2.3, 1, "APPLIED")
box(ax, 4.6, 0.3, 2.3, 1, "FAILED / unknown")
arrow(ax, (2.55, 2.15), (4.55, 3), "Matching ACK", False)
arrow(ax, (2.55, 1.95), (4.55, 0.85), "TTL expired", False)
box(ax, 9, 1.6, 2.5, 1, "Journal + RPC reply")
arrow(ax, (6.95, 3), (8.95, 2.25), bi=False)
arrow(ax, (6.95, 0.85), (8.95, 1.95), bi=False)
fig.tight_layout()
fig.savefig(OUT / "command_state.png", dpi=200)
plt.close(fig)
print(OUT)
