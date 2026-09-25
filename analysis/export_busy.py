"""웹앱 정비 동선용 자료 → web/data/busy.json (대여소별 하루 평균·시간대별 대여) + web/data/route_value.json (값 표).

    python analysis/export_busy.py 2606      # 시연 날짜(6월) 앞 7일로
값 표는 analysis/route_backtest.py 가 1·3월로 맞춘 것 (docs/route_backtest.md). 운영(실시간)에선 server/live.py 가 ops/busy.json 을 쓴다.
"""
import json, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pandas as pd
from engine.core import load_seoul
from engine.busy import station_busy

ym = sys.argv[1] if len(sys.argv) > 1 else "2606"
R = load_seoul(ROOT / "data" / "raw" / f"rent_{ym}.csv")
busy = station_busy(R, days=7, end=pd.Timestamp("2026-06-15"))   # 시연 날짜(6/15) 앞 7일
json.dump(busy, open(ROOT / "web" / "data" / "busy.json", "w"), separators=(",", ":"))
print("web/data/busy.json", len(busy), "대여소")
