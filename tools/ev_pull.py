"""클라우드 DB 가 5분마다 모은 충전기 상태(supabase/ev.sql)를 맥의 data/ev.sqlite 로 내려받는다 → analysis/ev_validate.py 가 그대로 읽음.

    python tools/ev_pull.py && python analysis/ev_validate.py      # → docs/ev_validation.md

클라우드에 남아 있는 가장 이른 시각(ev_runs, 클라우드는 4일만 둔다)부터는 클라우드 것으로 바꿔 넣는다(여러 번 돌려도 같음). 그 전은 맥에 받아 둔 기록 그대로 —
**4일 안에 한 번씩** 돌려야 빈틈이 없다.
DB 비밀번호는 키체인 'supabase-db'.
"""
import csv, io, pathlib, sqlite3, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.supabase_live_load import psql
from server.ev_collect import db as ev_db, FIELDS


def main():
    start = psql("select to_char(min(at), 'YYYY-MM-DD\"T\"HH24:MI:SS') from live.ev_runs").strip()
    if not start:
        print("클라우드에 아직 찍은 기록이 없어요."); return 1
    runs = list(csv.reader(io.StringIO(psql("copy (select to_char(at, 'YYYY-MM-DD\"T\"HH24:MI:SS'), items from live.ev_runs order by at) to stdout with csv"))))
    snap = list(csv.reader(io.StringIO(psql("copy (select to_char(at, 'YYYY-MM-DD\"T\"HH24:MI:SS'), charger, stat, stat_upd, ts, te, now_ts "
                                             "from live.ev_snap order by at) to stdout with csv"))))
    c = ev_db()   # 표가 없으면 만든다 (예전 맥 기록에는 runs 표가 없었음)
    with c:
        c.execute("delete from snap where at >= ?", (start,))
        c.execute("delete from runs where at >= ?", (start,))
        rows = []
        for at, charger, stat, upd, ts, te, now_ts in snap:
            stat_id, _, chger_id = charger.rpartition("-")
            rows.append((at, stat_id, chger_id, stat, upd, ts, te, now_ts))
        c.executemany(f"insert into snap(at, {', '.join(FIELDS)}) values (?, {', '.join('?' * len(FIELDS))})", rows)
        c.executemany("insert or replace into runs values (?, ?)", [(at, int(n)) for at, n in runs])
    print(f"클라우드 {start} 부터: 찍은 때 {len(runs)}번, 바뀐 상태 {len(snap):,}줄 → {c.execute('pragma database_list').fetchone()[2]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
