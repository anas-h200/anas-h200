"""Generate transparent, font-embedded GitHub stat cards as SVG.

Usage:
  GITHUB_TOKEN=... python scripts/generate_cards.py            # live data
  python scripts/generate_cards.py --demo [--no-embed]         # offline sample data
"""
import base64, io, json, os, sys, urllib.request
from xml.sax.saxutils import escape

USER = os.environ.get("GH_USER", "anas-h200")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets")
FONT_URL = "https://raw.githubusercontent.com/google/fonts/main/ofl/poppins/Poppins-{}.ttf"

# Mid-tone palette: stays readable on both white and dark GitHub backgrounds.
TITLE, LABEL, VALUE, RULE = "#2f81f7", "#6e7681", "#2f81f7", "#6e7681"
W, H = 420, 170


# ---------- data ----------
def _call(req):
    return json.load(urllib.request.urlopen(req))


def gql(query):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query}).encode(),
        headers={"Authorization": f"bearer {os.environ['GITHUB_TOKEN']}"},
    )
    return _call(req)["data"]["user"]


def rest(url):
    req = urllib.request.Request(
        url, headers={"Authorization": f"bearer {os.environ['GITHUB_TOKEN']}",
                      "Accept": "application/vnd.github+json"})
    return _call(req)


def fetch_live():
    u = gql(f'''{{ user(login: "{USER}") {{
      pullRequests {{ totalCount }}
      issues {{ totalCount }}
      repositoriesContributedTo(first: 1, contributionTypes: [COMMIT, ISSUE, PULL_REQUEST, REPOSITORY]) {{ totalCount }}
      repositories(ownerAffiliations: OWNER, isFork: false, first: 100) {{ nodes {{
        stargazerCount
        languages(first: 10, orderBy: {{field: SIZE, direction: DESC}}) {{ edges {{ size node {{ name color }} }} }}
      }} }}
    }} }}''')
    commits = rest(f"https://api.github.com/search/commits?q=author:{USER}&per_page=1")["total_count"]
    stars, langs = 0, {}
    for r in u["repositories"]["nodes"]:
        stars += r["stargazerCount"]
        for e in r["languages"]["edges"]:
            n = e["node"]["name"]
            cur = langs.setdefault(n, [0, e["node"]["color"] or "#8b949e"])
            cur[0] += e["size"]
    total = sum(v[0] for v in langs.values()) or 1
    top = sorted(langs.items(), key=lambda kv: -kv[1][0])[:6]
    return {
        "stats": [("Total Stars", stars), ("Total Commits", commits),
                  ("Total PRs", u["pullRequests"]["totalCount"]),
                  ("Total Issues", u["issues"]["totalCount"]),
                  ("Contributed to", u["repositoriesContributedTo"]["totalCount"])],
        "langs": [(n, v[0] / total * 100, v[1]) for n, v in top],
    }


DEMO = {
    "stats": [("Total Stars", 10), ("Total Commits", 354), ("Total PRs", 5),
              ("Total Issues", 0), ("Contributed to", 4)],
    "langs": [("Jupyter Notebook", 44.67, "#DA5B0B"), ("Python", 27.79, "#3572A5"),
              ("TypeScript", 16.02, "#3178C6"), ("JavaScript", 6.15, "#f1e05a"),
              ("CSS", 5.23, "#563d7c"), ("HTML", 0.15, "#e34c26")],
}


# ---------- font ----------
def font_css(embed=True):
    if not embed:
        return "text{font-family:'Poppins',sans-serif}"
    from fontTools import subset
    from fontTools.ttLib import TTFont
    css = ""
    for weight, name in ((400, "Regular"), (600, "SemiBold")):
        raw = urllib.request.urlopen(FONT_URL.format(name)).read()
        opts = subset.Options()
        opts.flavor = "woff2"
        font = TTFont(io.BytesIO(raw))
        sub = subset.Subsetter(opts)
        sub.populate(unicodes=list(range(0x20, 0x7F)))
        sub.subset(font)
        font.flavor = "woff2"
        buf = io.BytesIO()
        font.save(buf)
        b64 = base64.b64encode(buf.getvalue()).decode()
        css += ("@font-face{font-family:'Poppins';font-weight:%d;"
                "src:url(data:font/woff2;base64,%s) format('woff2')}" % (weight, b64))
    return css + "text{font-family:'Poppins',sans-serif}"


# ---------- render ----------
def svg(title, body, css):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="{escape(title)}">
<style>{css}
.t{{font-weight:600;font-size:17px;fill:{TITLE}}}
.l{{font-weight:400;font-size:13px;fill:{LABEL}}}
.v{{font-weight:600;font-size:13px;fill:{VALUE}}}
</style>
<text class="t" x="20" y="28">{escape(title)}</text>
<line x1="20" y1="40" x2="{W-20}" y2="40" stroke="{RULE}" stroke-opacity=".35"/>
{body}
</svg>'''


def stats_card(stats, css):
    rows = ""
    for i, (label, val) in enumerate(stats):
        y = 66 + i * 22
        rows += (f'<text class="l" x="20" y="{y}">{escape(label)}</text>'
                 f'<text class="v" x="{W-20}" y="{y}" text-anchor="end">{val:,}</text>\n')
    return svg("GitHub Stats", rows, css)


def langs_card(langs, css):
    bar_w, x, bar = W - 40, 20, ""
    tot = sum(p for _, p, _ in langs)
    for name, pct, color in langs:
        w = bar_w * pct / tot
        bar += f'<rect x="{x:.2f}" y="52" width="{w:.2f}" height="10" fill="{color}"/>'
        x += w
    body = (f'<clipPath id="r"><rect x="20" y="52" width="{bar_w}" height="10" rx="5"/></clipPath>'
            f'<g clip-path="url(#r)">{bar}</g>\n')
    for i, (name, pct, color) in enumerate(langs):
        cx, cy = 20 + (i % 2) * 195, 92 + (i // 2) * 24
        body += (f'<circle cx="{cx+5}" cy="{cy-4}" r="5" fill="{color}"/>'
                 f'<text class="l" x="{cx+16}" y="{cy}">{escape(name)} '
                 f'<tspan class="v">{pct:.1f}%</tspan></text>\n')
    return svg("Top Languages", body, css)


if __name__ == "__main__":
    demo = "--demo" in sys.argv
    css = font_css(embed="--no-embed" not in sys.argv)
    data = DEMO if demo else fetch_live()
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "stats.svg"), "w") as f:
        f.write(stats_card(data["stats"], css))
    with open(os.path.join(OUT, "langs.svg"), "w") as f:
        f.write(langs_card(data["langs"], css))
    print("done")
