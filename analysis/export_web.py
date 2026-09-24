"""웹앱 데이터 만들기 (web/data/*.json). 인증키 없이 월별 파일로 — Phase 3 서버가 매일 같은 형식을 만든다.

  stations.json          대여소 (번호, 이름, 구, 위도, 경도)
  morning/<날짜>.json    그날 아침 목록: 어제 자정까지 '서로 다른 사람 헛대여' 연쇄가 끊기지 않은 자전거
  replay_<날짜>.json     시연용 하루: 헛대여·경보·막을 수 있던 헛걸음·고장 신고를 시간순으로
"""
import json, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np, pandas as pd
from engine.core import Rule, load_seoul, load_faults, mark
from engine.morning import morning_lists

RULE = Rule(max_sec=180, max_m=300, alarm_k=2)
OUT = ROOT / "web" / "data"


def stations():
    S = pd.read_excel(ROOT / "data" / "raw" / "stations_2606.xlsx", header=None, skiprows=5, engine="openpyxl").iloc[:, [0, 1, 2, 4, 5]]
    S.columns = ["no", "name", "gu", "lat", "lon"]
    S = S.dropna(subset=["lat", "lon", "no"])
    S["id"] = S["no"].astype(int).astype(str).str.zfill(5)
    return S


def main(ym="2606", replay_day="2026-06-15"):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "morning").mkdir(exist_ok=True)
    S = stations()
    st_name = dict(zip(S["id"], S["name"].astype(str)))
    json.dump([{"id": r.id, "name": str(r.name), "gu": str(r.gu), "lat": round(float(r.lat), 6), "lon": round(float(r.lon), 6)}
               for r in S.itertuples()], open(OUT / "stations.json", "w"), ensure_ascii=False)

    base = load_seoul(ROOT / "data" / "raw" / f"rent_{ym}.csv")
    F = load_faults(ROOT / "data" / "raw" / "fault_2601-2606.csv")
    days = morning_lists(base, F, RULE, st_name)
    for day, items in days.items():
        json.dump({"date": day, "rule": "서로 다른 사람이 3분·300m 안 반납을 2번 이상 이어서 한 뒤 아직 정상 이용이 없는 자전거",
                   "bikes": items}, open(OUT / "morning" / f"{day}.json", "w"), ensure_ascii=False)
    R = mark(base, RULE)
    json.dump(sorted(days), open(OUT / "morning" / "index.json", "w"))

    # 시연용 하루
    day0 = pd.Timestamp(replay_day)
    D = R[(R["t0"] >= day0) & (R["t0"] < day0 + pd.Timedelta(days=1))]
    ev = []
    for r in D[D["dud"]].itertuples():
        kind = "막을 수 있던 헛걸음" if (not r.retry and r.streak >= RULE.alarm_k) else ("경보" if r.alarm else "헛대여")
        ev.append({"s": int((r.t1 - day0).total_seconds()), "t": r.t1.strftime("%H:%M:%S"), "type": kind, "bike": r.bike, "station": r.st0,
                   "chain": int(r.streak) + (0 if r.retry else 1)})
    FD = F[(F["t"] >= day0) & (F["t"] < day0 + pd.Timedelta(days=2))]
    alarmed = {e["bike"] for e in ev if e["type"] == "경보"}
    for f in FD.itertuples():
        if f.bike in alarmed:
            ev.append({"s": int((f.t - day0).total_seconds()),
                       "t": f.t.strftime("%H:%M:%S") if f.t < day0 + pd.Timedelta(days=1) else "다음 날 " + f.t.strftime("%H:%M"),
                       "type": "고장 신고", "bike": f.bike, "kind": f.kind})
    ev.sort(key=lambda e: e["s"])   # 글자순이면 "다음 날" 이 앞에 와서 재생이 막힌다 — 숫자로
    json.dump({"date": replay_day, "events": ev}, open(OUT / f"replay_{replay_day}.json", "w"), ensure_ascii=False)
    print(f"대여소 {len(S)}, 아침 목록 {len(days)}일(평균 {np.mean([len(v) for v in days.values()]):.0f}대), 시연 이벤트 {len(ev)}")


if __name__ == "__main__":
    main()
