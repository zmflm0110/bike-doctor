"""대여소가 얼마나 붐비나 — 정비 동선의 값(막을 헛걸음)에 쓴다: 하루 평균 대여, 시간대별 대여(24칸)."""
import numpy as np


def station_busy(R, days=7, end=None):
    """R(통일된 대여표)의 마지막 days 일(end 전)로: {대여소: [하루 평균, 0시…23시 대여 수]}."""
    end = end if end is not None else R["t0"].max().normalize() + np.timedelta64(1, "D")
    lo = end - np.timedelta64(days, "D")
    W = R[(R["t0"] >= lo) & (R["t0"] < end)]
    n_days = max(1, W["t0"].dt.normalize().nunique())
    h = W.groupby([W["st0"], W["t0"].dt.hour]).size().unstack(fill_value=0).reindex(columns=range(24), fill_value=0)
    return {st: [round(float(row.sum()) / n_days, 1), *map(int, row.tolist())] for st, row in h.iterrows()}
