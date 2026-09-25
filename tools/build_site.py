"""작품 소개 웹사이트(site/) 자료 만들기 — web/data 의 시연 자료를 가볍게 줄여 site/data 로, 앱 화면 사진을 site/img 로.

    python tools/build_site.py
"""
import json, pathlib, shutil
ROOT = pathlib.Path(__file__).resolve().parents[1]
W, S = ROOT / "web" / "data", ROOT / "site"
(S / "data").mkdir(parents=True, exist_ok=True); (S / "img").mkdir(exist_ok=True)

st = json.load(open(W / "stations.json"))
json.dump([[s["id"], s["name"].strip(), s["gu"], round(s["lat"], 5), round(s["lon"], 5)] for s in st],
          open(S / "data" / "stations.json", "w"), ensure_ascii=False, separators=(",", ":"))
code = {"헛대여": 0, "경보": 1, "막을 수 있던 헛걸음": 2, "고장 신고": 3}
rp = json.load(open(W / "replay_2026-06-15.json"))
json.dump({"date": rp["date"], "events": [[e["s"], code[e["type"]], e.get("station") or "", e["bike"], e.get("chain", 0)] for e in rp["events"]]},
          open(S / "data" / "replay.json", "w"), ensure_ascii=False, separators=(",", ":"))
m = json.load(open(W / "morning" / "2026-06-15.json"))
json.dump({"date": m["date"], "bikes": [[b["bike"], b["station_name"].strip(), b["chain"], b["level"], b["last_dud"]] for b in m["bikes"]]},
          open(S / "data" / "morning.json", "w"), ensure_ascii=False, separators=(",", ":"))
for n in ("1_morning", "2_lookup", "3_rescue", "4_replay"):
    shutil.copy(ROOT / "docs" / "shots" / f"{n}.png", S / "img" / f"{n}.png")
for p in sorted((S / "data").iterdir()) + sorted((S / "img").iterdir()):
    print(f"{p.relative_to(ROOT)}  {p.stat().st_size / 1024:.0f}KB")
