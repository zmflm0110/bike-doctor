"""작품 소개 웹사이트(site/) 만들기 — web/data 의 시연 자료를 가볍게 줄여 site/data 로, 앱 화면 사진을 site/img 로,
CHANGELOG.md 를 진행 기록 쪽(site/releases.html)으로.

    python tools/build_site.py                 # site/ 갱신
    python tools/build_site.py --out _site     # + 올릴 묶음: site/ 전체 + 웹앱(web/ → app/) — GitHub Pages 가 이걸 올린다
"""
import html, json, pathlib, re, shutil, sys
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


def md_inline(t):
    t = html.escape(t.replace("\\~", "~"), quote=False)   # 마크다운 취소선을 막으려 쓴 \~ 는 그냥 ~
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", lambda m: f'<a href="{m.group(2) if m.group(2).startswith("http") else "https://github.com/zmflm0110/bike-doctor/blob/master/" + m.group(2)}">{m.group(1)}</a>', t)


def releases():
    """CHANGELOG.md → site/releases.html (머리·꼬리·글꼴·색은 index.html 과 같은 style.css)"""
    body, in_list = [], False
    for line in (ROOT / "CHANGELOG.md").read_text().splitlines():
        if line.startswith("- "):
            if not in_list:
                body.append("<ul>"); in_list = True
            body.append(f"<li>{md_inline(line[2:])}</li>")
            continue
        if in_list:
            body.append("</ul>"); in_list = False
        if line.startswith("## "):
            m = re.match(r"## \[(.+?)\] - (\S+)", line)
            body.append(f"<h2>{html.escape(m.group(1))}<small>{m.group(2)}</small></h2>" if m else f"<h2>{md_inline(line[3:])}</h2>")
        elif line.startswith("# ") or not line.strip():
            continue
        else:
            body.append(f'<p class="lede">{md_inline(line)}</p>')
    if in_list:
        body.append("</ul>")
    idx = (S / "index.html").read_text()
    head = idx[:idx.index("</head>")].replace("<title>헛걸음 제로 — 빌리기 전에, 고장 난 따릉이를 먼저 알려 줍니다</title>", "<title>진행 기록 — 헛걸음 제로</title>")
    header = idx[idx.index('<header class="top"'):idx.index("</header>") + len("</header>")].replace('href="#results"', 'href="./#results"').replace('href="#start"', 'href="./#start"')
    footer = idx[idx.index("<footer>"):idx.index("</footer>") + len("</footer>")]
    theme = """<script>
(() => { const r = document.documentElement;
  try { const t = localStorage.getItem("hz-theme"); if (t) r.dataset.theme = t; } catch {}
  document.getElementById("theme").addEventListener("click", () => {
    const dark = r.dataset.theme ? r.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
    r.dataset.theme = dark ? "light" : "dark"; try { localStorage.setItem("hz-theme", r.dataset.theme); } catch {} });
  addEventListener("scroll", () => document.getElementById("top").classList.toggle("scrolled", scrollY > 8), { passive: true });
})();
</script>"""
    page = f"""{head}</head>
<body>
{header}
<main class="doc">
<h1>진행 기록</h1>
{chr(10).join(body)}
</main>
{footer}
{theme}
</body>
</html>
"""
    (S / "releases.html").write_text(page)
    print("site/releases.html", f"{len(page) / 1024:.0f}KB")


releases()

if "--out" in sys.argv:
    out = pathlib.Path(sys.argv[sys.argv.index("--out") + 1])
    shutil.rmtree(out, ignore_errors=True)
    shutil.copytree(S, out)
    # 시연용 웹앱: 운영 자료(live.json·ops)는 맥 서버에만 — 올리지 않음
    shutil.copytree(ROOT / "web", out / "app", ignore=shutil.ignore_patterns("live.json", "live.tmp", "ops", "status.json"))
    n = sum(1 for _ in out.rglob("*") if _.is_file())
    print(f"{out}/ 묶음: 파일 {n}개 (웹앱은 {out}/app/)")
