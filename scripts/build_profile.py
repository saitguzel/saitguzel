#!/usr/bin/env python3
"""Builds the GitHub profile README, STATS.md and SVG cards for github.com/saitguzel.

Data sources (all public): GitHub REST API and the public contribution calendar.
No third-party services, no dependencies. Run locally or from GitHub Actions:

    python3 scripts/build_profile.py            # GITHUB_TOKEN is optional (higher rate limit)
"""
import base64
import html
import json
import os
import re
import urllib.request
from collections import Counter, OrderedDict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

USER = "saitguzel"
ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
CARDS = ASSETS / "cards"

LINKS = {
    "website": "https://saitguzel.github.io",
    "website_en": "https://saitguzel.github.io/en/",
    "linkedin": "https://www.linkedin.com/in/saitguzel/",
    "coffee": "https://buymeacoffee.com/saitguzel",
    "email": "saitguzel90@hotmail.com",
    "cv_en": "https://saitguzel.github.io/cv/sait-guzel-cv-2026-en.pdf",
}

# Öne çıkan public repolar (sıra önemli). Açıklamalar repo açıklamasından daha anlatıcı.
FEATURED = OrderedDict([
    ("world-tv", ("Meridyen", "Android TV live TV & radio app: three-tier stream health engine, silent failover, streaming XMLTV guide parser, 100 unit tests.")),
    ("saitguzel.github.io", ("Portfolio", "Bilingual (TR/EN) portfolio generated from the same data as my CV. Light/dark theme, SEO, zero build step.")),
    ("youtube_oynatma_listesi_mp3_olarak_indirme", ("YouTube Playlist → MP3", "Desktop app (Flet) that downloads whole playlists as MP3 with parallel downloads, retries and duplicate detection.")),
    ("NetPgCodeGenerator", ("NetPgCodeGenerator", "Generates .NET data-access code from PostgreSQL schemas to skip repetitive boilerplate.")),
    ("MultiFactorAuthentication", ("MultiFactorAuthentication", "Two-factor authentication with Google / Microsoft Authenticator (TOTP) in a .NET web app.")),
    ("Azure.Signalr.MVC", ("Azure.Signalr.MVC", "Real-time messaging with ASP.NET MVC on top of Azure SignalR Service.")),
])

LANG_COLORS = {
    "C#": "#178600", "Kotlin": "#A97BFF", "Python": "#3572A5", "TypeScript": "#3178c6", "JavaScript": "#f1e05a",
    "HTML": "#e34c26", "CSS": "#663399", "PHP": "#4F5D95", "Rust": "#dea584", "Dart": "#00B4AB", "Go": "#00ADD8",
    "ASP": "#6a40fd", "TSQL": "#e38c00", "Dockerfile": "#384d54", "Shell": "#89e051", "Java": "#b07219",
}

FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"
THEME_CSS = """
.bg{fill:#ffffff;stroke:#d0d7de}.t{fill:#1f2328}.m{fill:#59636e}.a{fill:#0e7c86}.grid{stroke:#eaeef2}
.l0{fill:#ebedf0}.l1{fill:#9be9e0}.l2{fill:#40c4b4}.l3{fill:#0e9488}.l4{fill:#0b5f63}
@media (prefers-color-scheme:dark){.bg{fill:#0d1117;stroke:#30363d}.t{fill:#e6edf3}.m{fill:#9198a1}.a{fill:#2dd4bf}.grid{stroke:#21262d}
.l0{fill:#161b22}.l1{fill:#0e4d4a}.l2{fill:#11756d}.l3{fill:#1aa394}.l4{fill:#2dd4bf}}
"""


# ---------------------------------------------------------------- data

def get_json(url):
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": USER})
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def get_text(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8")


def fetch():
    user = get_json(f"https://api.github.com/users/{USER}")
    repos = [r for r in get_json(f"https://api.github.com/users/{USER}/repos?per_page=100&type=owner")
             if not r["fork"] and r["name"] != USER]
    for r in repos:
        r["languages"] = get_json(r["languages_url"])
    return user, repos


def fetch_contributions():
    page = get_text(f"https://github.com/users/{USER}/contributions")
    days = {}
    for m in re.finditer(r'<td[^>]*data-date="([\d-]+)"[^>]*id="([^"]+)"[^>]*data-level="(\d)"', page):
        days[m.group(2)] = {"date": date.fromisoformat(m.group(1)), "level": int(m.group(3)), "count": 0}
    for m in re.finditer(r'<tool-tip[^>]*for="([^"]+)"[^>]*>([^<]*)</tool-tip>', page):
        if m.group(1) in days:
            n = re.match(r"(\d+) contribution", m.group(2))
            days[m.group(1)]["count"] = int(n.group(1)) if n else 0
    return sorted(days.values(), key=lambda d: d["date"])


def contribution_summary(days):
    total = sum(d["count"] for d in days)
    active = sum(1 for d in days if d["count"])
    best = max(days, key=lambda d: d["count"])
    longest = run = 0
    for d in days:
        run = run + 1 if d["count"] else 0
        longest = max(longest, run)
    current, i = 0, len(days) - 1
    if days and days[i]["count"] == 0:  # bugün henüz katkı yoksa seriyi dünden say
        i -= 1
    while i >= 0 and days[i]["count"]:
        current, i = current + 1, i - 1
    monthly = OrderedDict()
    for d in days:
        key = d["date"].strftime("%Y-%m")
        monthly[key] = monthly.get(key, 0) + d["count"]
    return {"total": total, "active": active, "best": best, "longest": longest, "current": current,
            "monthly": list(monthly.items())[-12:]}


def language_share(repos):
    """Her repo toplamda eşit ağırlık taşır; büyük (ör. vendored) repolar dağılımı ezmesin."""
    share = Counter()
    for r in repos:
        total = sum(r["languages"].values())
        for lang, n in r["languages"].items():
            share[lang] += n / total if total else 0
    s = sum(share.values()) or 1
    return [(lang, v / s * 100) for lang, v in share.most_common()]


# ---------------------------------------------------------------- svg

def esc(s):
    return html.escape(str(s), quote=True)


def svg(w, h, body, title):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" '
            f'aria-label="{esc(title)}"><title>{esc(title)}</title><style>{THEME_CSS}text{{font-family:{FONT}}}</style>'
            f'<rect class="bg" x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="10"/>{body}</svg>\n')


def wrap(text, width):
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    lines.append(cur)
    return lines


def repo_card(repo, title, desc):
    langs = sorted(repo["languages"].items(), key=lambda kv: -kv[1])
    lang = langs[0][0] if langs else (repo["language"] or "")
    lines = wrap(desc, 58)[:3]
    body = [f'<text x="20" y="34" class="a" font-size="15" font-weight="700">{esc(title)}</text>',
            f'<text x="20" y="52" class="m" font-size="11">{esc(USER)}/{esc(repo["name"])}</text>']
    for i, line in enumerate(lines):
        body.append(f'<text x="20" y="{78 + i * 17}" class="t" font-size="12.5">{esc(line)}</text>')
    y = 148
    if lang:
        body.append(f'<circle cx="26" cy="{y - 4}" r="5" fill="{LANG_COLORS.get(lang, "#8b949e")}"/>'
                    f'<text x="37" y="{y}" class="m" font-size="12">{esc(lang)}</text>')
    pushed = datetime.fromisoformat(repo["pushed_at"].replace("Z", "+00:00")).strftime("%b %Y")
    body.append(f'<text x="380" y="{y}" class="m" font-size="12" text-anchor="end">★ {repo["stargazers_count"]} · updated {pushed}</text>')
    return svg(400, 170, "".join(body), f"{title} repository")


def overview_card(user, repos, summary):
    stars = sum(r["stargazers_count"] for r in repos)
    items = [("Contributions (last year)", summary["total"]), ("Active days", summary["active"]),
             ("Current streak", f'{summary["current"]} days'), ("Longest streak", f'{summary["longest"]} days'),
             ("Public repositories", len(repos)), ("Stars earned", stars),
             ("Followers", user["followers"]), ("On GitHub since", user["created_at"][:4])]
    body = ['<text x="24" y="38" class="t" font-size="17" font-weight="700">GitHub overview</text>']
    for i, (label, value) in enumerate(items):
        col, row = i % 2, i // 2
        x, y = 24 + col * 236, 76 + row * 34
        body.append(f'<text x="{x}" y="{y}" class="m" font-size="12.5">{esc(label)}</text>'
                    f'<text x="{x + 210}" y="{y}" class="t" font-size="13.5" font-weight="700" text-anchor="end">{esc(value)}</text>')
    return svg(484, 220, "".join(body), "GitHub overview")


def languages_card(shares):
    top = shares[:6]
    other = 100 - sum(p for _, p in top)
    if other > 0.5:
        top.append(("Other", other))
    body = ['<text x="24" y="38" class="t" font-size="17" font-weight="700">Languages</text>',
            '<text x="336" y="38" class="m" font-size="11" text-anchor="end">weighted by repository</text>',
            '<clipPath id="bar"><rect x="24" y="54" width="312" height="10" rx="5"/></clipPath><g clip-path="url(#bar)">']
    x = 24.0
    for lang, pct in top:
        w = 312 * pct / 100
        body.append(f'<rect x="{x:.2f}" y="54" width="{w + 0.5:.2f}" height="10" fill="{LANG_COLORS.get(lang, "#8b949e")}"/>')
        x += w
    body.append("</g>")
    for i, (lang, pct) in enumerate(top):
        col, row = i % 2, i // 2
        cx, cy = 30 + col * 160, 92 + row * 28
        body.append(f'<circle cx="{cx}" cy="{cy - 4}" r="5" fill="{LANG_COLORS.get(lang, "#8b949e")}"/>'
                    f'<text x="{cx + 12}" y="{cy}" class="t" font-size="12.5">{esc(lang)} '
                    f'<tspan class="m">{pct:.1f}%</tspan></text>')
    return svg(360, 220, "".join(body), "Languages")


def monthly_card(summary):
    data = summary["monthly"]
    peak = max((v for _, v in data), default=1) or 1
    w, h, left, bottom, top = 720, 220, 40, 180, 56
    step = (w - left - 24) / max(len(data), 1)
    body = [f'<text x="24" y="36" class="t" font-size="17" font-weight="700">Contributions per month</text>',
            f'<text x="{w - 24}" y="36" class="m" font-size="12" text-anchor="end">{summary["total"]} in the last year</text>']
    for frac in (0, .5, 1):
        y = bottom - (bottom - top) * frac
        body.append(f'<line x1="{left}" x2="{w - 24}" y1="{y}" y2="{y}" class="grid"/>'
                    f'<text x="{left - 8}" y="{y + 4}" class="m" font-size="10" text-anchor="end">{round(peak * frac)}</text>')
    for i, (month, value) in enumerate(data):
        bh = (bottom - top) * value / peak
        x = left + i * step + step * .2
        label = datetime.strptime(month, "%Y-%m").strftime("%b")
        body.append(f'<rect x="{x:.1f}" y="{bottom - bh:.1f}" width="{step * .6:.1f}" height="{max(bh, 1):.1f}" rx="3" class="a"/>'
                    f'<text x="{x + step * .3:.1f}" y="{bottom + 16}" class="m" font-size="10.5" text-anchor="middle">{label}</text>')
    return svg(w, h, "".join(body), "Contributions per month")


def heatmap_card(days, summary):
    if not days:
        return svg(720, 60, '<text x="24" y="36" class="m" font-size="13">No data</text>', "Contribution calendar")
    start = days[0]["date"] - timedelta(days=(days[0]["date"].weekday() + 1) % 7)  # haftalar pazar başlar
    cell, gap, left, top = 10, 2.5, 40, 66
    body = ['<text x="24" y="34" class="t" font-size="17" font-weight="700">Contribution calendar</text>',
            f'<text x="720" y="34" class="m" font-size="12" text-anchor="end" dx="-24">best day: {summary["best"]["count"]} on {summary["best"]["date"]:%d %b %Y}</text>']
    last_month = None
    for d in days:
        week = (d["date"] - start).days // 7
        dow = (d["date"].weekday() + 1) % 7
        x, y = left + week * (cell + gap), top + dow * (cell + gap)
        body.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{cell}" height="{cell}" rx="2" class="l{d["level"]}">'
                    f'<title>{d["count"]} on {d["date"]:%d %b %Y}</title></rect>')
        if d["date"].day <= 7 and dow == 0 and d["date"].month != last_month:
            last_month = d["date"].month
            body.append(f'<text x="{x:.1f}" y="{top - 6}" class="m" font-size="10">{d["date"]:%b}</text>')
    for i, label in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        body.append(f'<text x="{left - 6}" y="{top + i * (cell + gap) + 9}" class="m" font-size="9.5" text-anchor="end">{label}</text>')
    lx = 720 - 24 - 5 * (cell + gap) - 70
    body.append(f'<text x="{lx}" y="{top + 7 * (cell + gap) + 16}" class="m" font-size="10">Less</text>')
    for lvl in range(5):
        body.append(f'<rect x="{lx + 28 + lvl * (cell + gap):.1f}" y="{top + 7 * (cell + gap) + 6}" width="{cell}" height="{cell}" rx="2" class="l{lvl}"/>')
    body.append(f'<text x="{lx + 28 + 5 * (cell + gap) + 4:.1f}" y="{top + 7 * (cell + gap) + 16}" class="m" font-size="10">More</text>')
    return svg(720, 190, "".join(body), "Contribution calendar")


def banner():
    cover = base64.b64encode((ASSETS / "cover.jpg").read_bytes()).decode()
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="300" viewBox="0 0 1200 300" role="img" aria-label="Sait Güzel, Full Stack .NET Developer">
<title>Sait Güzel · Full Stack .NET Developer</title>
<defs>
  <clipPath id="r"><rect width="1200" height="300" rx="18"/></clipPath>
  <linearGradient id="shade" x1="0" x2="1"><stop offset="0" stop-color="#06121f" stop-opacity=".92"/><stop offset=".6" stop-color="#06121f" stop-opacity=".55"/><stop offset="1" stop-color="#06121f" stop-opacity=".1"/></linearGradient>
  <linearGradient id="accent" x1="0" x2="1"><stop offset="0" stop-color="#2dd4bf"/><stop offset="1" stop-color="#60a5fa"/></linearGradient>
</defs>
<g clip-path="url(#r)">
  <image href="data:image/jpeg;base64,{cover}" width="1200" height="400" y="-50" preserveAspectRatio="xMidYMid slice"/>
  <rect width="1200" height="300" fill="url(#shade)"/>
</g>
<g font-family="{FONT}">
  <text x="64" y="118" fill="#ffffff" font-size="58" font-weight="800" letter-spacing="-1">Sait Güzel</text>
  <rect x="66" y="138" width="92" height="5" rx="2.5" fill="url(#accent)"/>
  <text x="64" y="186" fill="#e2e8f0" font-size="26" font-weight="600">Full Stack .NET Developer · Former Team Lead</text>
  <text x="64" y="226" fill="#94a3b8" font-size="19">ERP integrations · Cloud SaaS on Azure · AI-powered services · İzmir, Türkiye</text>
</g>
</svg>
'''


# ---------------------------------------------------------------- markdown

def badges():
    b = [
        ("Website", "saitguzel.github.io", "0e7c86", "googlechrome", LINKS["website"]),
        ("LinkedIn", "saitguzel", "0A66C2", "linkedin", LINKS["linkedin"]),
        ("Buy Me a Coffee", "support", "FFDD00", "buymeacoffee", LINKS["coffee"]),
        ("Email", "contact", "0f172a", "maildotru", f'mailto:{LINKS["email"]}'),
    ]
    out = []
    for label, msg, color, logo, url in b:
        label_q, msg_q = label.replace(" ", "%20"), msg.replace(" ", "%20")
        logo_color = "000000" if color == "FFDD00" else "white"
        out.append(f'<a href="{url}"><img alt="{label}" src="https://img.shields.io/badge/{label_q}-{msg_q}-{color}?style=for-the-badge&logo={logo}&logoColor={logo_color}"></a>')
    return "\n  ".join(out)


def tech_badges():
    groups = [
        ("Languages", [("C%23", "239120", "dotnet"), ("Python", "3776AB", "python"), ("TypeScript", "3178C6", "typescript"), ("JavaScript", "F7DF1E", "javascript"), ("Kotlin", "7F52FF", "kotlin"), ("Dart", "0175C2", "dart"), ("Rust", "000000", "rust"), ("SQL", "CC2927", "databricks")]),
        ("Backend", [(".NET", "512BD4", "dotnet"), ("ASP.NET Core", "512BD4", "dotnet"), ("FastAPI", "009688", "fastapi"), ("Node.js", "339933", "nodedotjs"), ("SignalR", "512BD4", "dotnet"), ("RabbitMQ", "FF6600", "rabbitmq")]),
        ("Frontend & Mobile", [("React", "20232A", "react"), ("Vue.js", "4FC08D", "vuedotjs"), ("Angular", "DD0031", "angular"), ("Flutter", "02569B", "flutter"), ("Jetpack Compose", "4285F4", "jetpackcompose"), ("Tauri", "24C8DB", "tauri")]),
        ("Data", [("SQL Server", "CC2927", "microsoftsqlserver"), ("PostgreSQL", "4169E1", "postgresql"), ("MongoDB", "47A248", "mongodb"), ("Redis", "DC382D", "redis"), ("Neo4j", "4581C3", "neo4j"), ("Power BI", "F2C811", "powerbi")]),
        ("Cloud & DevOps", [("Azure", "0078D4", "microsoftazure"), ("Azure DevOps", "0078D7", "azuredevops"), ("Docker", "2496ED", "docker"), ("GitHub Actions", "2088FF", "githubactions"), ("DigitalOcean", "0080FF", "digitalocean"), ("n8n", "EA4B71", "n8n")]),
        ("AI", [("Claude", "D97757", "anthropic"), ("OpenAI", "412991", "openai"), ("Whisper", "412991", "openai"), ("Qwen VL", "615CED", "alibabacloud")]),
    ]
    rows = []
    for name, items in groups:
        imgs = " ".join(
            f'<img alt="{html.unescape(label.replace("%23", "#"))}" src="https://img.shields.io/badge/{label.replace(" ", "%20")}-{color}?style=flat-square&logo={logo}&logoColor=white">'
            for label, color, logo in items
        )
        rows.append(f"| **{name}** | {imgs} |")
    return "| | |\n|---|---|\n" + "\n".join(rows)


def featured_grid(repos_by_name):
    cells = []
    for name, (title, _) in FEATURED.items():
        if name in repos_by_name:
            cells.append(f'<a href="https://github.com/{USER}/{name}"><img src="assets/cards/{name}.svg" alt="{esc(title)}" width="400"></a>')
    rows = ["<tr>" + "".join(f'<td>{c}</td>' for c in cells[i:i + 2]) + "</tr>" for i in range(0, len(cells), 2)]
    return "<table>\n" + "\n".join(rows) + "\n</table>"


def build_readme(repos_by_name, summary, updated):
    return f"""<p align="center">
  <img src="assets/banner.svg" alt="Sait Güzel · Full Stack .NET Developer" width="100%">
</p>

<p align="center">
  {badges()}
</p>

<p align="center">
  <a href="{LINKS['website_en']}"><b>Portfolio</b></a> ·
  <a href="{LINKS['cv_en']}"><b>CV (PDF)</b></a> ·
  <a href="STATS.md"><b>Detailed GitHub statistics</b></a> ·
  <a href="#-türkçe"><b>Türkçe</b></a>
</p>

## 👋 About me

I'm **Sait**, a full stack developer from İzmir, Türkiye, building end-to-end products on the **.NET ecosystem since 2015**. Over the years I have worked across **logistics, education, manufacturing, healthcare, fintech and media**: from ERP integrations and microservice architectures to enterprise SaaS platforms on Azure, ETL/reporting pipelines and AI-powered services.

I spent **four years as Software Development Team Lead** at Monovi, leading a 5–8 person team's technical direction, architecture decisions and delivery. What I enjoy most is rewriting legacy systems with modern stacks and turning complex business rules into simple, scalable software.

- 🔭 **Now:** Software Specialist at **Code35** (remote), building a middleware API on top of the **Netsis ERP** database, a real-time unit cost model and LLM-based document automation.
- 🎙️ **Recently:** backend and AI services for a karaoke platform at **Mergenova**: .NET 9 microservices, a trained **Whisper** model for timestamped lyrics, pitch analysis and **Claude API** feedback.
- 🌱 **Side projects:** .NET 10, Flutter, Rust and Kotlin products (see below), and vision-LLM pipelines with human-in-the-loop validation.
- 📚 **Learning:** agentic AI architectures, Databricks, advanced PostgreSQL.
- 💬 **Ask me about:** .NET & Azure architecture, ERP integrations, PostgreSQL, turning a messy process into software.

## 🧰 Tech stack

{tech_badges()}

## ⭐ Featured public projects

{featured_grid(repos_by_name)}

## 🔒 Private work & products

Some of my most substantial work lives in private repositories. Highlights:

| Project | What it is | Stack |
|---|---|---|
| **Yerel Yemcim** | Turns cooperatives' paper price lists into structured data from a photo; vision-LLM output passes 8 deterministic validators and mandatory human approval. In pilot use. | .NET 10, EF Core, PostgreSQL, Flutter, Qwen VL, Docker |
| **Local LMS** | Self-hosted, privacy-by-design modular LMS & HR platform with 13 modules; web, desktop and mobile clients from one React codebase. | .NET 10, React, Tauri v2, PostgreSQL, MinIO, Playwright |
| **PlayZone Hub** | Multi-tenant SaaS for playgrounds and kids' activity centers: 9 microservices behind a YARP gateway. | .NET 10, RabbitMQ, Redis, SignalR, React, Flutter |
| **EnterpriseForge CodeGen** | ABP Suite-style code generator producing Rust backends, Angular front-ends and Flutter apps from entity definitions. | Rust, Actix Web, SQLx, Angular, Flutter |
| **Netsis ERP middleware** · Code35 | Middleware API over the ERP database, real-time unit cost model, LLM document automation (invoices, bank statements). | Node.js, SQL Server, PostgreSQL, n8n, Docker |
| **TonTon** · Mergenova | Karaoke platform backend: microservices, timestamped lyrics with a trained Whisper model, pitch analysis, LLM feedback. | .NET 9, FastAPI, PostgreSQL, MongoDB, Neo4j, RabbitMQ |
| **monligo.com** · Monovi | Enterprise application platform with social sign-in and multilingual content. | .NET 8, Azure App Service, Key Vault, PostgreSQL, Azure AI |
| **emlaklira.com** · Monovi | Real-estate tokenization and trading platform. | .NET 6, Solidity, Azure SQL Ledger, APIM, Functions |
| **Monovi Trace & ICS2** · Monovi | EU ICS2-compliant data submission for logistics companies. | .NET 6, SQL Server, EF Core |
| **okulsis.net** · Bilsa | Modular school management system with PHP API, Cordova mobile app and Selenium test automation. | ASP.NET, .NET Core, SQL Server, SignalR |

## 💼 Experience

| Period | Role | Company |
|---|---|---|
| Aug 2026 – present | Software Specialist (remote) | Code35 |
| Sep 2025 – Jun 2026 | Software Specialist | Mergenova Yazılım |
| Aug 2021 – Jul 2025 | **Software Development Team Lead** | Monovi Information Technology |
| Mar 2021 – Aug 2021 | Software Specialist | Monovi Information Technology |
| 2016 – 2021 | Software Developer | Bilsa Yazılım |
| Dec 2015 – Jun 2016 | Software Developer | Çağdaş Eczacılık Bilgi İşlem |

🎓 B.Sc. Computer Engineering, Pamukkale University (2010 – 2015)

## 📊 GitHub stats

<p>
  <img src="assets/cards/overview.svg" alt="GitHub overview" height="195">
  <img src="assets/cards/languages.svg" alt="Languages" height="195">
</p>
<img src="assets/cards/contributions-monthly.svg" alt="Contributions per month" width="720">

➡️ **[See the detailed statistics page](STATS.md)**: contribution calendar, streaks, language breakdown and every public repository.

<details>
<summary><b>🏅 Certifications (17)</b></summary>

- Advanced PostgreSQL · Developing CI/CD Solutions with Azure DevOps · Agentic AI Fundamentals (LinkedIn Learning, 2025)
- Complete Guide to Databricks for Data Engineering · Microsoft Azure Synapse for Developers (LinkedIn Learning, 2025)
- Azure Key Vault for Developers · Azure Front Door · Power BI Essential Training (LinkedIn Learning, 2025)
- Building an Enterprise API for Advanced Azure Developers · ASP.NET Core Advanced Security: Data Protection
- Azure Data Lake for Developers · Kubernetes: Essential Tools (LinkedIn Learning)
- ASP.NET Core + Docker (Udemy) · SQL Server In Depth · Database Attacks and Security (BTK Akademi)
- CCNA R&S: Introduction to Networks · Routing and Switching Essentials (Cisco)

</details>

## 🇹🇷 Türkçe

<details>
<summary><b>Kısaca ben</b></summary>

İzmirliyim; **2015'ten bu yana .NET ekosisteminde** uçtan uca ürün geliştiriyorum. Lojistik, eğitim, üretim, sağlık, fintech ve medya sektörlerinde ERP entegrasyonlarından mikroservis mimarilerine, Azure üzerindeki kurumsal SaaS ürünlerinden yapay zekâ destekli servislere kadar pek çok projede sorumluluk aldım. **Monovi'de 4 yıl yazılım geliştirme takım liderliği** yaptım.

Şu anda **Code35**'te uzaktan çalışıyor; Netsis ERP üzerine ara katman API, anlık birim maliyet modeli ve LLM ile belge otomasyonu geliştiriyorum. Kişisel projelerimde .NET 10, Flutter, Rust ve Kotlin kullanıyorum.

🌐 Türkçe portfolyo: **[saitguzel.github.io]({LINKS['website']})**

</details>

## ☕ Support

If my open-source work saved you some time, you can support me here:

<a href="{LINKS['coffee']}"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me a Coffee" height="48"></a>

---

<sub>Stats and cards are generated from public GitHub data by <a href="scripts/build_profile.py">scripts/build_profile.py</a> and refreshed daily by GitHub Actions. Last update: {updated}.</sub>
"""


def build_stats(user, repos, summary, shares, updated):
    repo_rows = []
    for r in sorted(repos, key=lambda r: r["pushed_at"], reverse=True):
        langs = sorted(r["languages"].items(), key=lambda kv: -kv[1])
        lang = langs[0][0] if langs else (r["language"] or "—")
        desc = FEATURED.get(r["name"], (None, r["description"] or ""))[1].replace("|", "\\|")
        repo_rows.append(f'| [{r["name"]}]({r["html_url"]}) | {desc} | {lang} | {r["stargazers_count"]} | {r["forks_count"]} | {r["pushed_at"][:10]} |')
    lang_rows = [f"| {lang} | {pct:.1f}% | {'█' * max(1, round(pct / 4))} |" for lang, pct in shares[:10]]
    month_rows = [f"| {datetime.strptime(m, '%Y-%m'):%B %Y} | {v} |" for m, v in reversed(summary["monthly"])]
    best = summary["best"]
    return f"""# 📊 GitHub statistics · {user['name'] or USER}

[← Back to profile](README.md) · Last update: **{updated}** · Data: public GitHub API and contribution calendar

<img src="assets/cards/overview.svg" alt="GitHub overview" height="195"> <img src="assets/cards/languages.svg" alt="Languages" height="195">

<img src="assets/cards/contributions-calendar.svg" alt="Contribution calendar" width="720">

<img src="assets/cards/contributions-monthly.svg" alt="Contributions per month" width="720">

## Last 12 months

| Metric | Value |
|---|---|
| Total contributions | **{summary['total']}** |
| Active days | {summary['active']} |
| Current streak | {summary['current']} days |
| Longest streak | {summary['longest']} days |
| Best day | {best['count']} contributions on {best['date']:%d %B %Y} |
| Public repositories (own, non-fork) | {len(repos)} |
| Stars earned | {sum(r['stargazers_count'] for r in repos)} |
| Followers / following | {user['followers']} / {user['following']} |
| Public gists | {user['public_gists']} |
| On GitHub since | {user['created_at'][:10]} |

> Contribution counts include private work only when "private contributions" is enabled on the profile.

<details>
<summary><b>Contributions by month</b></summary>

| Month | Contributions |
|---|---|
{chr(10).join(month_rows)}

</details>

## Languages

Share of code across my own public repositories. Every repository has equal weight, so one large repo cannot dominate the chart.

| Language | Share | |
|---|---|---|
{chr(10).join(lang_rows)}

## Public repositories

| Repository | Description | Language | ★ | Forks | Last push |
|---|---|---|---|---|---|
{chr(10).join(repo_rows)}
"""


def main():
    user, repos = fetch()
    days = fetch_contributions()
    summary = contribution_summary(days)
    shares = language_share(repos)
    by_name = {r["name"]: r for r in repos}
    updated = datetime.now(timezone.utc).strftime("%d %b %Y")

    CARDS.mkdir(parents=True, exist_ok=True)
    (ASSETS / "banner.svg").write_text(banner(), encoding="utf-8")
    for name, (title, desc) in FEATURED.items():
        if name in by_name:
            (CARDS / f"{name}.svg").write_text(repo_card(by_name[name], title, desc), encoding="utf-8")
    (CARDS / "overview.svg").write_text(overview_card(user, repos, summary), encoding="utf-8")
    (CARDS / "languages.svg").write_text(languages_card(shares), encoding="utf-8")
    (CARDS / "contributions-monthly.svg").write_text(monthly_card(summary), encoding="utf-8")
    (CARDS / "contributions-calendar.svg").write_text(heatmap_card(days, summary), encoding="utf-8")
    (ROOT / "README.md").write_text(build_readme(by_name, summary, updated), encoding="utf-8")
    (ROOT / "STATS.md").write_text(build_stats(user, repos, summary, shares, updated), encoding="utf-8")
    print(f"repos={len(repos)} contributions={summary['total']} streak={summary['current']}/{summary['longest']} "
          f"top={', '.join(f'{l} {p:.0f}%' for l, p in shares[:4])}")


if __name__ == "__main__":
    main()
