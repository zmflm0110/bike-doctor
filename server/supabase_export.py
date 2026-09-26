"""클라우드 DB(Supabase)의 현장 조사·구조대 확인을 내려받는다 → data/survey.csv, data/rescue.csv
(analysis/field_validation.py 가 그대로 읽는 모양 — 맥 서버의 /api/survey.csv 와 같은 열, 시각은 서울 시각).

    python server/supabase_export.py            # CSV 두 개 (photo 열 = 저장소 survey-photos 안 이름)
    python analysis/field_validation.py data/survey.csv live
사진은 Supabase 대시보드 → Storage → survey-photos 에서 본다(비공개 — 앱 키로는 올리기만 된다).

DB 비밀번호는 맥 키체인에만(코드·git 에 없음): security add-generic-password -a bike-doctor -s supabase-db -w
접속은 세션 풀러(IPv4) — 프로젝트는 ap-southeast-1.
"""
import argparse, csv, io, os, pathlib, subprocess, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from server.seoul_api import key

REF = "iqvquwvoljzuvdgtbpnu"
DSN = f"host=aws-0-ap-southeast-1.pooler.supabase.com port=5432 dbname=postgres user=postgres.{REF} sslmode=require"


def psql_csv(sql):
    pw = key("supabase-db")
    if not pw:
        raise SystemExit("Supabase DB 비밀번호가 키체인에 없습니다: security add-generic-password -a bike-doctor -s supabase-db -w")
    out = subprocess.run(["psql", DSN, "-X", "-q", "-c", f"\\copy ({sql}) to stdout with csv header"],
                         env={**os.environ, "PGPASSWORD": pw}, capture_output=True, text=True, check=True).stdout
    return list(csv.reader(io.StringIO(out)))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "data"))
    a = ap.parse_args(argv)
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    kst = "to_char(at at time zone 'Asia/Seoul', 'YYYY-MM-DD HH24:MI:SS')"
    for name, sql in [("survey", f"select {kst} as at, station, bike, status, note, lat, lon, photo from public.survey order by id"),
                      ("rescue", f"select {kst} as at, bike, verdict, day from public.rescue order by id")]:
        rows = psql_csv(sql)
        with open(out / f"{name}.csv", "w", newline="", encoding="utf-8-sig") as f:
            csv.writer(f).writerows(rows)
        print(f"{name}: {len(rows) - 1}건 → {out / f'{name}.csv'}")


if __name__ == "__main__":
    main()
