"""따릉이 고장 예보 — 대여이력의 "빌리자마자 반납" 이 고장 신고를 얼마나 앞서 알려 주나.

데이터 (서울 열린데이터광장, 2026년 3월):
  대여이력 OA-15182 (자전거번호·대여/반납 일시·대여소·이용시간·거리), 고장신고 OA-15644 (자전거번호·등록일시·구분)

"헛대여": 같은 대여소에 2분 안에, 200m 도 안 가고 반납. 사람이 타 보려다 포기한 흔적.
"""
import json
import numpy as np, pandas as pd

R = pd.read_csv("data/rent_2603.csv", usecols=["자전거번호", "대여일시", "대여 대여소번호", "반납일시", "반납대여소번호", "이용시간(분)", "이용거리(M)"],
                dtype={"대여 대여소번호": str, "반납대여소번호": str}, encoding="cp949")
R.columns = ["bike", "t0", "st0", "t1", "st1", "mins", "dist"]
R["t0"] = pd.to_datetime(R["t0"]); R["t1"] = pd.to_datetime(R["t1"], errors="coerce")
R = R.dropna(subset=["t1"]).sort_values(["bike", "t0"]).reset_index(drop=True)
secs = (R["t1"] - R["t0"]).dt.total_seconds()
R["dud"] = (R["st0"] == R["st1"]) & (secs <= 120) & (R["dist"].fillna(0) < 200)

F = pd.read_csv("data/fault_2601-2606.csv", encoding="cp949")
F.columns = ["bike", "t", "kind"]
F["t"] = pd.to_datetime(F["t"]); F["kind"] = F["kind"].str.strip()
F = F[(F["t"] >= "2026-03-01") & (F["t"] < "2026-04-01")].drop_duplicates(["bike", "t"])

out = {"rentals": len(R), "bikes": R["bike"].nunique(), "dud_rate_%": round(100 * R["dud"].mean(), 2),
       "fault_reports_march": len(F), "fault_kinds": F["kind"].value_counts().head(8).to_dict()}
print(json.dumps(out, ensure_ascii=False, indent=1))

# 1) 헛대여 뒤 24시간 안에 그 자전거에 고장 신고가 들어올 확률 vs 보통 대여 뒤
fault_times = F.groupby("bike")["t"].apply(lambda s: np.sort(s.values)).to_dict()


def next_fault_within(bike, t, hours=24):
    ts = fault_times.get(bike)
    if ts is None:
        return False
    i = np.searchsorted(ts, np.datetime64(t))
    return i < len(ts) and (ts[i] - np.datetime64(t)) <= np.timedelta64(hours, "h")


# 신고 자체가 헛대여 직후에 일어나는 경우(신고하고 반납)가 많아 "같은 순간" 은 빼고 본다: 반납 후 10분 뒤부터
R["t_after"] = R["t1"] + pd.Timedelta(minutes=10)
sample = pd.concat([R[R["dud"]], R[~R["dud"]].sample(min(300_000, (~R["dud"]).sum()), random_state=0)])
sample["fault24"] = [next_fault_within(b, t) for b, t in zip(sample["bike"], sample["t_after"])]
p_dud = sample.loc[sample["dud"], "fault24"].mean()
p_norm = sample.loc[~sample["dud"], "fault24"].mean()
print(f"\n헛대여 뒤 24시간 안 고장 신고 {100*p_dud:.2f}%  vs 보통 대여 뒤 {100*p_norm:.2f}%  → {p_dud/p_norm:.1f}배")

# 2) 연속 헛대여: 한 자전거에서 헛대여가 k번 연달아(다른 대여 없이) 나오면?
R["prev_dud_streak"] = 0
streak = np.zeros(len(R), dtype=int)
bikes = R["bike"].values; duds = R["dud"].values
for i in range(1, len(R)):
    if bikes[i] == bikes[i - 1]:
        streak[i] = streak[i - 1] + 1 if duds[i - 1] else 0
R["prev_dud_streak"] = streak  # 이번 대여 직전까지 연속 헛대여 수
rows = []
for k in range(0, 5):
    sel = R[R["prev_dud_streak"] == k]
    if len(sel) < 50:
        break
    rows.append({"직전 연속 헛대여": k, "대여 수": len(sel), "이번에도 헛대여 %": round(100 * sel["dud"].mean(), 1)})
print("\n직전 연속 헛대여 수 → 이번 사람도 헛걸음할 확률")
print(pd.DataFrame(rows).to_string(index=False))

# 3) 신고 전 피해자: 고장 신고가 들어온 자전거에서, 신고 전 48시간 안 헛대여를 겪은 사람 수
victims = []
g = R.groupby("bike")
for b, ts in list(fault_times.items()):
    if b not in g.groups:
        continue
    rb = g.get_group(b)
    for t in ts:
        t = pd.Timestamp(t)
        w = rb[(rb["t1"] <= t - pd.Timedelta(minutes=10)) & (rb["t1"] > t - pd.Timedelta(hours=48))]
        victims.append({"duds_before": int(w["dud"].sum()), "rentals_before": len(w)})
V = pd.DataFrame(victims)
print(f"\n고장 신고 {len(V)}건 중 신고 전 48시간 안에 헛대여가 1번 이상 있던 비율 {100*(V['duds_before']>0).mean():.1f}%,"
      f" 그런 경우 평균 헛대여 {V.loc[V['duds_before']>0,'duds_before'].mean():.2f}명")

# 4) 신고 없는 헛대여 연쇄: 연속 헛대여 2번 이상인데 이후 7일 안에 신고가 없음
chain_end = R[(R["prev_dud_streak"] >= 1) & R["dud"]]
unreported = [not next_fault_within(b, t, hours=24 * 7) for b, t in zip(chain_end["bike"], chain_end["t_after"])]
print(f"연속 헛대여(2번 이상) {len(chain_end)}건 중 7일 안에 고장 신고가 없는 비율 {100*np.mean(unreported):.1f}%")

# 5) 예보 규칙 평가 (3/1~15 로 규칙 확인, 3/16~31 로 시험): 자전거가 반납된 순간 "위험" 경보를 낼지
test = R[R["t1"] >= "2026-03-16"].copy()
test["fault24"] = [next_fault_within(b, t) for b, t in zip(test["bike"], test["t_after"])]
base = test["fault24"].mean()
print(f"\n[시험 구간 3/16~31] 반납 순간 기준 24시간 안 신고 기본 확률 {100*base:.2f}% (반납 {len(test)}건)")
for name, rule in [("이번이 헛대여", test["dud"]),
                   ("헛대여 2연속", test["dud"] & (test["prev_dud_streak"] >= 1)),
                   ("헛대여 3연속", test["dud"] & (test["prev_dud_streak"] >= 2))]:
    hit = test.loc[rule, "fault24"]
    recall = rule[test["fault24"]].mean()
    print(f"  {name:<10} 경보 {rule.sum():6d}건  정밀도 {100*hit.mean():5.1f}% ({hit.mean()/base:4.1f}배)  재현율 {100*recall:5.1f}%")
