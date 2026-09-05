# -*- coding: utf-8 -*-
"""네이버 블로그 글 목록을 구글이 크롤할 수 있는 정적 사이트로 만든다.

네이버 블로그는 <head> 수정이 안 돼서 구글 서치콘솔 소유권 확인이 불가능하다.
그래서 내 소유 도메인(GitHub Pages)에 '목록 사이트'를 세우고 서치콘솔에 등록한 뒤,
거기 걸린 링크를 따라 구글이 네이버 원문을 발견하게 만든다.

본문을 통째로 옮기면 중복 콘텐츠가 되므로 개별 글 페이지는 만들지 않는다.
만드는 건 목록 페이지(최신·카테고리·월별)뿐이다.
"""
import html as html_mod
import json
import os
import re
import shutil
import sys
import time
import urllib.parse
from collections import OrderedDict, defaultdict
from datetime import datetime, date, timedelta

from naverblog import BLOG_ID, fetch_post_list, fetch_rss, get

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "docs")
CONFIG_PATH = os.path.join(HERE, "config.json")

PER_PAGE = 100          # 목록 페이지당 글 수
HOME_RECENT = 60        # 첫 화면에 노출할 최근 글 수

DEFAULT_CONFIG = {
    "base_url": "https://EXAMPLE.github.io/naver-hub",
    "site_title": "솔직함이 육체를 지배한 현STJ — 글 목록",
    "site_desc": ("국내외 여행기와 맛집·호텔 후기를 쓴다. "
                  "네이버 블로그에 올린 글 전체를 한 곳에서 찾아볼 수 있게 정리한 목록이다."),
    "author": "현STJ",
    "google_verification": "",
    # 서치콘솔이 준 확인용 파일명. 빌드 때마다 docs/ 를 새로 만들기 때문에
    # 여기 적어두면 매번 같이 생성된다. 지우면 소유권 확인이 풀린다.
    "google_verification_file": "",
    "naver_blog_url": "https://blog.naver.com/" + BLOG_ID,
}


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg.update(json.load(f))
    else:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    cfg["base_url"] = cfg["base_url"].rstrip("/")
    return cfg


# ---------------------------------------------------------------- 데이터 수집

REL_HOUR = re.compile(r"(\d+)\s*시간")
REL_DAY = re.compile(r"(\d+)\s*일")
ABS_DATE = re.compile(r"(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})")


def parse_add_date(text, today=None):
    """'2026. 9. 3.' / '2시간 전' / '3일 전' 을 date 로 바꾼다."""
    today = today or date.today()
    m = ABS_DATE.search(text or "")
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return today
    if REL_HOUR.search(text or "") or "분" in (text or ""):
        return today
    m = REL_DAY.search(text or "")
    if m:
        return today - timedelta(days=int(m.group(1)))
    return today


CAT_CACHE = os.path.join(HERE, "cache_categories.json")
POSTS_CACHE = os.path.join(HERE, "posts.json")


def resolve_category_names(posts):
    """카테고리 번호마다 대표 글을 하나 열어 이름을 알아낸다. 한 번 알아낸 건 캐시한다."""
    names, seen = {}, OrderedDict()
    if os.path.exists(CAT_CACHE):
        with open(CAT_CACHE, encoding="utf-8") as f:
            names.update(json.load(f))
    for p in posts:
        seen.setdefault(p["categoryNo"], p["logNo"])
    for cat_no, log_no in list(seen.items()):
        if cat_no in names:
            continue
        try:
            page = get("https://blog.naver.com/PostView.naver?blogId=%s&logNo=%s"
                       % (BLOG_ID, log_no))
            m = re.search(r'categoryName\s*=\s*["\']([^"\']+)["\']', page)
            # 같은 변수가 퍼센트 인코딩된 채로도 박혀 있어서 반드시 디코딩한다.
            raw = m.group(1).strip() if m else ""
            name = urllib.parse.unquote_plus(raw).strip()
            names[cat_no] = name or ("카테고리 " + cat_no)
        except Exception as exc:                      # 이름을 못 얻어도 빌드는 계속
            sys.stderr.write("  카테고리 %s 이름 실패: %s\n" % (cat_no, exc))
            names[cat_no] = "카테고리 " + cat_no
        sys.stderr.write("  카테고리 %s = %s\n" % (cat_no, names[cat_no]))
        time.sleep(0.4)
    with open(CAT_CACHE, "w", encoding="utf-8") as f:
        json.dump(names, f, ensure_ascii=False, indent=1)
    return names


def load_posts(incremental):
    """전수 수집하거나, 캐시에 새 글만 얹는다.

    매일 도는 자동 갱신이 매번 50페이지를 긁으면 네이버에 부담이라
    평소에는 앞쪽 몇 페이지만 보고 이미 아는 글이 연달아 나오면 멈춘다.
    """
    if not incremental or not os.path.exists(POSTS_CACHE):
        return fetch_post_list()

    with open(POSTS_CACHE, encoding="utf-8") as f:
        cached = json.load(f)
    known = {p["logNo"] for p in cached}
    fresh = fetch_post_list(max_pages=5)
    added = [p for p in fresh if p["logNo"] not in known]
    sys.stderr.write("  증분 갱신: 새 글 %d편 (캐시 %d편)\n" % (len(added), len(cached)))
    if len(added) >= 140:                    # 앞 5페이지가 거의 다 새 글이면 전수로 다시
        sys.stderr.write("  새 글이 너무 많다. 전수 수집으로 전환한다.\n")
        return fetch_post_list()

    merged = {p["logNo"]: p for p in cached}
    for p in fresh:                          # 제목·카테고리 변경분도 최신으로 덮어쓴다
        merged[p["logNo"]] = p
    return list(merged.values())


def collect(incremental=False):
    sys.stderr.write("글 목록 수집...\n")
    posts = load_posts(incremental)
    with open(POSTS_CACHE, "w", encoding="utf-8") as f:
        json.dump(posts, f, ensure_ascii=False, indent=1)
    sys.stderr.write("RSS 요약 수집...\n")
    rss = fetch_rss()
    sys.stderr.write("카테고리 이름 확인...\n")
    cat_names = resolve_category_names(posts)

    for p in posts:
        extra = rss.get(p["logNo"], {})
        p["date"] = parse_add_date(p.get("addDate", ""))
        p["excerpt"] = extra.get("excerpt", "")
        p["thumb"] = extra.get("thumb", "")
        p["tags"] = extra.get("tags", [])
        p["cat_name"] = cat_names.get(p["categoryNo"], "기타")
    posts.sort(key=lambda x: (x["date"], x["logNo"]), reverse=True)
    return posts, cat_names


# ---------------------------------------------------------------- HTML 조립

def esc(text):
    return html_mod.escape(text or "", quote=True)


def slug_cat(cat_no):
    return "c/%s" % cat_no


CSS = """
:root{--bg:#fbfaf8;--fg:#1c1a17;--muted:#6b655d;--line:#e5e0d8;--accent:#1a6b4a;--card:#fff}
@media (prefers-color-scheme:dark){:root{--bg:#14130f;--fg:#eceae5;--muted:#9c958a;--line:#2e2b25;--accent:#6fd0a1;--card:#1c1a16}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.7 -apple-system,BlinkMacSystemFont,"Segoe UI","Malgun Gothic","Apple SD Gothic Neo",sans-serif}
.wrap{max-width:820px;margin:0 auto;padding:0 20px 72px}
header{border-bottom:1px solid var(--line);margin-bottom:28px;padding:34px 0 22px}
header h1{margin:0 0 8px;font-size:25px;letter-spacing:-.02em}
header h1 a{color:var(--fg);text-decoration:none}
header p{margin:0;color:var(--muted);font-size:14.5px}
nav{margin-top:18px;display:flex;flex-wrap:wrap;gap:8px}
nav a{font-size:13.5px;color:var(--fg);text-decoration:none;border:1px solid var(--line);border-radius:999px;padding:5px 13px;background:var(--card)}
nav a:hover,nav a[aria-current]{border-color:var(--accent);color:var(--accent)}
h2.sec{font-size:15px;color:var(--muted);font-weight:600;margin:38px 0 14px;letter-spacing:.02em}
ul.posts{list-style:none;margin:0;padding:0}
ul.posts li{border-bottom:1px solid var(--line);padding:16px 0}
ul.posts a.t{color:var(--fg);text-decoration:none;font-weight:600;font-size:17px;letter-spacing:-.01em}
ul.posts a.t:hover{color:var(--accent)}
.meta{color:var(--muted);font-size:13px;margin-top:5px}
.meta a{color:var(--muted)}
.ex{color:var(--muted);font-size:14.5px;margin-top:8px}
.row{display:flex;gap:15px;align-items:flex-start}
.row img{width:104px;height:78px;object-fit:cover;border-radius:7px;flex:none;background:var(--line)}
.row .b{min-width:0;flex:1}
.pager{display:flex;flex-wrap:wrap;gap:7px;margin:30px 0 0}
.pager a,.pager span{font-size:13.5px;padding:5px 11px;border:1px solid var(--line);border-radius:6px;text-decoration:none;color:var(--fg)}
.pager span{color:var(--muted);border-color:transparent}
footer{border-top:1px solid var(--line);margin-top:46px;padding-top:20px;color:var(--muted);font-size:13.5px}
footer a{color:var(--accent)}
.lede{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:15px 17px;color:var(--muted);font-size:14.5px}
@media(max-width:520px){.row img{width:78px;height:60px}header h1{font-size:21px}}
"""


def page(cfg, *, path, title, desc, body, extra_head=""):
    """정적 페이지 한 장을 만들어 저장한다."""
    canon = cfg["base_url"] + "/" + path.lstrip("/")
    canon = re.sub(r"/index\.html$", "/", canon)
    verify = ('\n<meta name="google-site-verification" content="%s">' % esc(cfg["google_verification"])) \
        if cfg["google_verification"] else ""
    doc = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>%(title)s</title>
<meta name="description" content="%(desc)s">
<link rel="canonical" href="%(canon)s">
<meta name="robots" content="index,follow">
<meta property="og:type" content="website">
<meta property="og:title" content="%(title)s">
<meta property="og:description" content="%(desc)s">
<meta property="og:url" content="%(canon)s">%(verify)s
<style>%(css)s</style>%(extra)s
</head>
<body>
<div class="wrap">
<header>
<h1><a href="%(base)s/">%(site)s</a></h1>
<p>%(sitedesc)s</p>
<nav>%(nav)s</nav>
</header>
%(body)s
<footer>
글 원문은 모두 <a href="%(naver)s" rel="noopener">네이버 블로그</a>에 있다.
이 페이지는 그 글들을 찾아보기 쉽게 정리한 목록이다.
</footer>
</div>
</body>
</html>
""" % {
        "title": esc(title), "desc": esc(desc), "canon": esc(canon),
        "verify": verify, "css": CSS, "extra": extra_head,
        "base": esc(cfg["base_url"]), "site": esc(cfg["author"]),
        "sitedesc": esc(cfg["site_desc"]), "nav": cfg["_nav"],
        "body": body, "naver": esc(cfg["naver_blog_url"]),
    }
    full = os.path.join(OUT, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(doc)


def render_list(posts, *, with_excerpt=False):
    out = ['<ul class="posts">']
    for p in posts:
        thumb = ('<img src="%s" alt="" loading="lazy" referrerpolicy="no-referrer">' % esc(p["thumb"])) \
            if (with_excerpt and p["thumb"]) else ""
        ex = ('<div class="ex">%s</div>' % esc(p["excerpt"][:180])) if (with_excerpt and p["excerpt"]) else ""
        body = (
            '<div class="b">'
            '<a class="t" href="%(url)s" rel="noopener">%(title)s</a>'
            '<div class="meta">%(date)s · <a href="%(base)s/%(cat)s/1.html">%(catname)s</a></div>'
            '%(ex)s</div>'
        )
        out.append('<li><div class="row">%s%s</div></li>' % (
            thumb,
            body % {"url": esc(p["url"]), "title": esc(p["title"]),
                    "date": p["date"].strftime("%Y.%m.%d"),
                    "base": esc(p["_base"]), "cat": slug_cat(p["categoryNo"]),
                    "catname": esc(p["cat_name"]), "ex": ex},
        ))
    out.append("</ul>")
    return "\n".join(out)


def render_pager(base_url, prefix, page_no, total_pages):
    if total_pages <= 1:
        return ""
    bits = ['<div class="pager">']
    for n in range(1, total_pages + 1):
        if abs(n - page_no) > 3 and n not in (1, total_pages):
            continue
        if n == page_no:
            bits.append("<span>%d</span>" % n)
        else:
            bits.append('<a href="%s/%s/%d.html">%d</a>' % (base_url, prefix, n, n))
    bits.append("</div>")
    return "".join(bits)


def item_list_ld(cfg, posts):
    data = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "itemListElement": [
            {"@type": "ListItem", "position": i + 1,
             "url": p["url"], "name": p["title"]}
            for i, p in enumerate(posts)
        ],
    }
    return '\n<script type="application/ld+json">%s</script>' % json.dumps(data, ensure_ascii=False)


# ---------------------------------------------------------------- 빌드

def build(incremental=False):
    cfg = load_config()
    posts, cat_names = collect(incremental)
    for p in posts:
        p["_base"] = cfg["base_url"]

    by_cat = defaultdict(list)
    by_month = defaultdict(list)
    for p in posts:
        by_cat[p["categoryNo"]].append(p)
        by_month[p["date"].strftime("%Y-%m")].append(p)

    cat_order = sorted(by_cat, key=lambda c: len(by_cat[c]), reverse=True)
    nav = ['<a href="%s/">최신 글</a>' % esc(cfg["base_url"])]
    for c in cat_order:
        nav.append('<a href="%s/%s/1.html">%s</a>'
                   % (esc(cfg["base_url"]), slug_cat(c), esc(cat_names.get(c, c))))
    nav.append('<a href="%s/archive.html">전체 보기</a>' % esc(cfg["base_url"]))
    cfg["_nav"] = "".join(nav)

    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)
    urls = []

    # 첫 화면 -------------------------------------------------------------
    recent = posts[:HOME_RECENT]
    body = (
        '<div class="lede">%s 편의 글을 썼다. 최근 글부터 아래에 정리했고, '
        '위 메뉴에서 주제별로도 볼 수 있다. 제목을 누르면 네이버 블로그 원문으로 간다.</div>'
        '<h2 class="sec">최근 글</h2>%s'
    ) % (len(posts), render_list(recent, with_excerpt=True))
    page(cfg, path="index.html", title=cfg["site_title"], desc=cfg["site_desc"],
         body=body, extra_head=item_list_ld(cfg, recent))
    urls.append((cfg["base_url"] + "/", posts[0]["date"], "daily", "1.0"))

    # 카테고리별 ----------------------------------------------------------
    for c in cat_order:
        items = by_cat[c]
        name = cat_names.get(c, c)
        total_pages = max(1, (len(items) + PER_PAGE - 1) // PER_PAGE)
        for n in range(1, total_pages + 1):
            chunk = items[(n - 1) * PER_PAGE: n * PER_PAGE]
            title = "%s 글 목록 (%d/%d) — %s" % (name, n, total_pages, cfg["author"]) \
                if total_pages > 1 else "%s 글 목록 — %s" % (name, cfg["author"])
            desc = "%s 카테고리에 쓴 글 %d편의 목록이다." % (name, len(items))
            body = ('<div class="lede">%s</div><h2 class="sec">%s · %d편</h2>%s%s'
                    % (esc(desc), esc(name), len(items),
                       render_list(chunk, with_excerpt=(n == 1)),
                       render_pager(cfg["base_url"], slug_cat(c), n, total_pages)))
            path = "%s/%d.html" % (slug_cat(c), n)
            page(cfg, path=path, title=title, desc=desc, body=body,
                 extra_head=item_list_ld(cfg, chunk))
            urls.append((cfg["base_url"] + "/" + path, chunk[0]["date"], "weekly", "0.8"))

    # 월별 아카이브 --------------------------------------------------------
    months = sorted(by_month, reverse=True)
    rows = []
    for mkey in months:
        items = by_month[mkey]
        y, m = mkey.split("-")
        rows.append('<li><div class="row"><div class="b">'
                    '<a class="t" href="%s/a/%s.html">%s년 %s월</a>'
                    '<div class="meta">%d편</div></div></div></li>'
                    % (esc(cfg["base_url"]), mkey, y, int(m), len(items)))
        body = ('<div class="lede">%s년 %s월에 쓴 글 %d편이다.</div>'
                '<h2 class="sec">%s년 %s월</h2>%s'
                % (y, int(m), len(items), y, int(m), render_list(items)))
        page(cfg, path="a/%s.html" % mkey,
             title="%s년 %s월 글 목록 — %s" % (y, int(m), cfg["author"]),
             desc="%s년 %s월에 쓴 글 %d편의 목록이다." % (y, int(m), len(items)),
             body=body, extra_head=item_list_ld(cfg, items))
        urls.append((cfg["base_url"] + "/a/%s.html" % mkey, items[0]["date"], "monthly", "0.6"))

    page(cfg, path="archive.html", title="전체 글 목록 — " + cfg["author"],
         desc="%d편의 글을 쓴 달을 기준으로 모두 모았다." % len(posts),
         body='<div class="lede">%d편을 쓴 달 기준으로 모았다.</div>'
              '<h2 class="sec">월별</h2><ul class="posts">%s</ul>'
              % (len(posts), "".join(rows)))
    urls.append((cfg["base_url"] + "/archive.html", posts[0]["date"], "weekly", "0.7"))

    # sitemap / robots ----------------------------------------------------
    sm = ['<?xml version="1.0" encoding="UTF-8"?>',
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc, lastmod, freq, prio in urls:
        sm.append("<url><loc>%s</loc><lastmod>%s</lastmod>"
                  "<changefreq>%s</changefreq><priority>%s</priority></url>"
                  % (esc(loc), lastmod.isoformat(), freq, prio))
    sm.append("</urlset>")
    with open(os.path.join(OUT, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write("\n".join(sm))

    with open(os.path.join(OUT, "robots.txt"), "w", encoding="utf-8") as f:
        f.write("User-agent: *\nAllow: /\n\nSitemap: %s/sitemap.xml\n" % cfg["base_url"])

    with open(os.path.join(OUT, ".nojekyll"), "w", encoding="utf-8") as f:
        f.write("")

    vfile = cfg.get("google_verification_file", "").strip()
    if vfile:
        with open(os.path.join(OUT, vfile), "w", encoding="utf-8") as f:
            f.write("google-site-verification: %s" % vfile)
        sys.stderr.write("서치콘솔 확인 파일 생성: %s\n" % vfile)

    sys.stderr.write("\n빌드 완료: %d편 -> 페이지 %d장\n" % (len(posts), len(urls)))
    sys.stderr.write("출력: %s\n" % OUT)
    sys.stderr.write("base_url: %s  (config.json 에서 바꾼다)\n" % cfg["base_url"])
    return len(posts), len(urls)


if __name__ == "__main__":
    build(incremental="--incremental" in sys.argv)
