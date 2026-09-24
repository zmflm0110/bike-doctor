"""발표용 그림: 연쇄 수 → 다음 사람 헛걸음 확률, 도시·달별 (docs/fig_chain.png)."""
import pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from engine.core import Rule, load_seoul, load_tashu, mark, next_dud_table

plt.rcParams["font.family"] = "AppleGothic"
plt.rcParams["axes.unicode_minus"] = False
RAW = ROOT / "data" / "raw"
rule = Rule(max_sec=180, max_m=300, alarm_k=2)
sets = [("서울 1월", load_seoul, RAW / "rent_2601.csv"), ("서울 3월", load_seoul, RAW / "rent_2603.csv"),
        ("서울 6월", load_seoul, RAW / "rent_2606.csv"), ("대전 5월", load_tashu, RAW / "tashu" / "tashu_2505.csv"),
        ("대전 10월", load_tashu, RAW / "tashu" / "tashu_2510.csv")]
fig, ax = plt.subplots(figsize=(8, 5), dpi=150)
for name, loader, path in sets:
    T = next_dud_table(mark(loader(path), rule), max_k=4)
    ax.plot(T["k"], T["next_dud_%"], marker="o", label=name, linestyle="-" if "서울" in name else "--")
ax.set_xticks(range(5))
ax.set_xticklabels(["0", "1명", "2명", "3명", "4명"])
ax.set_xlabel("앞서 이 자전거를 빌리자마자 반납한 서로 다른 사람 수")
ax.set_ylabel("다음 사람도 빌리자마자 반납할 확률 (%)")
ax.set_title("앞사람들이 포기한 자전거는 다음 사람도 포기한다")
ax.axhline(2.5, color="gray", lw=0.8)
ax.text(3.2, 4.5, "평소 약 2.5%", color="gray")
ax.grid(alpha=0.3)
ax.legend()
fig.tight_layout()
fig.savefig(ROOT / "docs" / "fig_chain.png")
print("docs/fig_chain.png")
