"""launchd 작업 정의: 맥이 읽을 수 있는 plist 인지, 키가 들어가지 않는지."""
import pathlib, plistlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from server.schedule import plists, ROOT


def test_plists():
    P = plists(api_url="https://example.org/rent?x=1", ev=True)
    assert set(P) == {"kr.bikedoctor.morning", "kr.bikedoctor.web", "kr.bikedoctor.ev"}
    for label, pl in P.items():
        back = plistlib.loads(plistlib.dumps(pl))            # 맥 형식으로 쓰고 다시 읽힘
        assert back["Label"] == label and back["WorkingDirectory"] == str(ROOT)
        assert pathlib.Path(back["ProgramArguments"][1]).exists()
        assert not any(k in back["EnvironmentVariables"] for k in ("DATAGOKR_KEY", "SEOUL_OPENAPI_KEY"))   # 키는 키체인에서
    m = P["kr.bikedoctor.morning"]
    assert m["StartCalendarInterval"] == {"Hour": 6, "Minute": 10} and m["ProgramArguments"][-2:] == ["--source", "api"]
    assert m["EnvironmentVariables"]["RENT_API_URL"] == "https://example.org/rent?x=1"
    assert P["kr.bikedoctor.web"]["KeepAlive"] is True
    assert "kr.bikedoctor.ev" not in plists()
