"""원본 데이터를 처음부터 받는다 (인증키 불필요). data/raw 에 저장.

    python data/download.py            # 서울 2026-01·03·06, 고장신고, 대여소, 대전 타슈 2025-05·10

서울 열린데이터광장 파일은 목록 페이지의 downloadFile(seq) 값으로 받는다. seq 는 파일이 갱신되면 바뀔 수 있다 —
바뀌면 목록 페이지(https://data.seoul.go.kr/dataList/<ID>/F/1/datasetView.do)에서 다시 확인.
"""
import pathlib, subprocess, zipfile

RAW = pathlib.Path(__file__).resolve().parent / "raw"
SEOUL = "https://datafile.seoul.go.kr/bigfile/iot/inf/nio_download.do?&useCache=false"
FILES = [  # (저장 이름, 데이터셋 ID, seq, infSeq)
    ("rent_2601.csv", "OA-15182", 144, 1),
    ("rent_2603.csv", "OA-15182", 147, 1),
    ("rent_2606.csv", "OA-15182", 150, 1),
    ("fault_2601-2606.csv", "OA-15644", 21, 1),
    ("stations_2606.xlsx", "OA-13252", 24, 2),
]
TASHU = ("tashu/tashu.zip", "FILE_000000003632730", 1)   # 공공데이터포털 15137219 (24.08~26.03 월별 csv 묶음)
TASHU_MONTHS = {"tashu/tashu_2505.csv": "25년05월", "tashu/tashu_2510.csv": "25년10월"}


def curl(args, out):
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["curl", "-s", "-L", "-A", "Mozilla/5.0", "-o", str(out)] + args, check=True)
    print(f"{out.name}: {out.stat().st_size/1e6:.1f}MB")


def main():
    for name, inf, seq, infseq in FILES:
        if not (RAW / name).exists():
            curl(["-X", "POST", SEOUL, "-d", f"infId={inf}&seq={seq}&infSeq={infseq}"], RAW / name)
    z = RAW / TASHU[0]
    if not z.exists():
        cj = "/tmp/datagokr_cookies.txt"
        subprocess.run(["curl", "-s", "-A", "Mozilla/5.0", "-c", cj, "-b", cj, "-X", "POST",
                        "https://www.data.go.kr/cmm/cmm/check-limit.json", "-d", f"atchFileId={TASHU[1]}&fileDetailSn={TASHU[2]}"], check=True)
        curl(["-c", cj, "-b", cj, f"https://www.data.go.kr/cmm/cmm/fileDownload.do?atchFileId={TASHU[1]}&fileDetailSn={TASHU[2]}&dataNm=tashu"], z)
    zf = zipfile.ZipFile(z)
    for out, tag in TASHU_MONTHS.items():
        if (RAW / out).exists():
            continue
        for info in zf.infolist():
            try:
                name = info.filename.encode("cp437").decode("cp949")
            except UnicodeError:
                name = info.filename
            if tag in name:
                (RAW / out).write_bytes(zf.read(info))
                print(f"{out}: {tag}")
                break


if __name__ == "__main__":
    main()
