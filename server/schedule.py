"""맥에서 자동으로 돌리기 (launchd) — 실시간 경보 상시, 매일 아침 목록, 웹 서버 상시, (선택) 충전기 수집.

    python server/schedule.py install --ev                                 # 실시간 경보(1분) + 06:10 아침 목록 + 웹 서버 + 충전기(5분)
    python server/schedule.py install --api-url '<공공데이터포털 요청주소>'   # 아침 목록을 공공데이터포털 API 로 (예전 방식)
    python server/schedule.py status                                       # 등록 상태·마지막 기록
    python server/schedule.py uninstall                                    # 모두 내리기
    python server/schedule.py print                                        # 만들 plist 만 보여 주기 (설치 안 함)

- 인증키는 키체인에서 읽는다(로그인한 사용자로 돌아서 키체인이 열려 있음). plist 에 키를 넣지 않는다.
- 맥이 잠들어 06:10 을 놓치면 깨어난 뒤 한 번 돈다(launchd 규칙). 덮개를 닫아 두면 안 돈다 — 충전기에 꽂고 열어 두기(PLAN 표 9번).
- 실시간 경보는 전원에 꽂혀 있을 때 맥이 잠들지 않게 한다(caffeinate -s — 배터리일 땐 평소처럼 잠듦).
- 기록: data/logs/<이름>.log
"""
import argparse, os, pathlib, plistlib, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
AGENTS = pathlib.Path.home() / "Library" / "LaunchAgents"
LOGS = ROOT / "data" / "logs"
PREFIX = "kr.bikedoctor"


def python():
    venv = ROOT / ".venv" / "bin" / "python"
    return str(venv if venv.exists() else pathlib.Path(sys.executable))


def plists(api_url=None, ev=False, port=8765, hour=6, minute=10):
    """{라벨: plist 딕셔너리}"""
    def job(name, args, **extra):
        env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "PYTHONUNBUFFERED": "1"}
        if api_url:
            env["RENT_API_URL"] = api_url
        return f"{PREFIX}.{name}", {"Label": f"{PREFIX}.{name}", "ProgramArguments": [python(), *args], "WorkingDirectory": str(ROOT),
                                    "EnvironmentVariables": env, "StandardOutPath": str(LOGS / f"{name}.log"),
                                    "StandardErrorPath": str(LOGS / f"{name}.log"), **extra}
    src = ["--source", "api"] if api_url else ["--source", "live"]   # live = 실시간 서버가 모은 서울 대여이력 (키 1 하나로)
    out = dict([
        job("live", [str(ROOT / "server" / "live.py")], RunAtLoad=True, KeepAlive=True),
        job("morning", [str(ROOT / "server" / "daily_job.py"), *src], StartCalendarInterval={"Hour": hour, "Minute": minute}),
        job("web", [str(ROOT / "server" / "app.py"), str(port)], RunAtLoad=True, KeepAlive=True),
    ])
    lab, pl = f"{PREFIX}.live", out[f"{PREFIX}.live"]
    pl["ProgramArguments"] = ["/usr/bin/caffeinate", "-s", *pl["ProgramArguments"]]
    if ev:
        out.update([job("ev", [str(ROOT / "server" / "ev_collect.py"), "--zcode", "11", "--every", "5"], RunAtLoad=True, KeepAlive=True)])
    return out


def launchctl(*args):
    return subprocess.run(["launchctl", *args], capture_output=True, text=True)


def install(a):
    AGENTS.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    for label, pl in plists(a.api_url, a.ev, a.port).items():
        path = AGENTS / f"{label}.plist"
        launchctl("unload", str(path))
        path.write_bytes(plistlib.dumps(pl))
        r = launchctl("load", str(path))
        print(f"{label}: {'등록' if r.returncode == 0 else '실패 ' + r.stderr.strip()} → {path}")


def uninstall(_):
    for path in sorted(AGENTS.glob(f"{PREFIX}.*.plist")):
        launchctl("unload", str(path))
        path.unlink()
        print("내림:", path.name)


def status(_):
    listed = launchctl("list").stdout
    for path in sorted(AGENTS.glob(f"{PREFIX}.*.plist")):
        label = path.stem
        line = next((l for l in listed.splitlines() if l.endswith(label)), None)
        log = LOGS / f"{label.split('.')[-1]}.log"
        tail = log.read_text(errors="replace").strip().splitlines()[-1:] if log.exists() else ["(기록 없음)"]
        print(f"{label}: {'등록됨 ' + line.split()[0] + '(pid) ' + line.split()[1] + '(마지막 종료 코드)' if line else '등록 안 됨'} | {tail[0][:100]}")
    if not any(AGENTS.glob(f"{PREFIX}.*.plist")):
        print("설치된 작업 없음 — python server/schedule.py install")


def show(a):
    for label, pl in plists(a.api_url, a.ev, a.port).items():
        print(f"--- {label}.plist")
        print(plistlib.dumps(pl).decode())


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["install", "uninstall", "status", "print"])
    ap.add_argument("--api-url", default=os.environ.get("RENT_API_URL"))
    ap.add_argument("--ev", action="store_true")
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args()
    if a.cmd != "print" and sys.platform != "darwin":
        raise SystemExit("launchd 는 맥 전용입니다. 리눅스 서버라면 cron: 10 6 * * * cd <폴더> && .venv/bin/python server/daily_job.py --source api")
    {"install": install, "uninstall": uninstall, "status": status, "print": show}[a.cmd](a)
