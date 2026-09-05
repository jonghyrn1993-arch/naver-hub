# -*- coding: utf-8 -*-
"""네이버 블로그(blog.naver.com/100755)에서 글 목록과 RSS 요약을 긁어온다.

audit.py 와 build.py 가 같이 쓰는 공용 모듈.
"""
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

BLOG_ID = "100755"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")

# 네이버 응답은 JSON 스펙에 없는 이스케이프(\' 등)를 섞어 보낸다. 유효한 것만 남긴다.
BAD_ESCAPE = re.compile(r'\\(?!["\\/bfnrtu])')
TAG_RE = re.compile(r"<[^>]+>")
IMG_RE = re.compile(r'<img[^>]+src="([^"]+)"', re.I)


def get(url, timeout=25):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Referer": "https://blog.naver.com/" + BLOG_ID,
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def fetch_post_list(blog_id=BLOG_ID, max_pages=300, verbose=True):
    """블로그의 전체 글 목록. logNo/제목/카테고리/공개여부/검색허용여부를 준다."""
    posts, page = [], 1
    while page <= max_pages:
        url = ("https://blog.naver.com/PostTitleListAsync.naver"
               "?blogId=%s&viewdate=&currentPage=%d"
               "&categoryNo=0&parentCategoryNo=&countPerPage=30" % (blog_id, page))
        data = json.loads(BAD_ESCAPE.sub("", get(url)))
        chunk = data.get("postList") or []
        if not chunk:
            break
        for p in chunk:
            p["title"] = urllib.parse.unquote_plus(p.get("title", ""))
            p["url"] = "https://blog.naver.com/%s/%s" % (blog_id, p["logNo"])
        posts.extend(chunk)
        if verbose:
            sys.stderr.write("  page %d: +%d (누적 %d)\n" % (page, len(chunk), len(posts)))
        page += 1
        time.sleep(0.4)
    return posts


def fetch_rss(blog_id=BLOG_ID):
    """RSS에서 최근 50편의 요약문·썸네일·태그·카테고리를 얻는다."""
    root = ET.fromstring(get("https://rss.blog.naver.com/%s.xml" % blog_id))
    out = {}
    for item in root.findall("./channel/item"):
        link = (item.findtext("link") or "").split("?")[0]
        log_no = link.rstrip("/").rsplit("/", 1)[-1]
        if not log_no.isdigit():
            continue
        desc = item.findtext("description") or ""
        thumb_m = IMG_RE.search(desc)
        text = html.unescape(TAG_RE.sub(" ", desc))
        text = re.sub(r"\s+", " ", text).strip()
        text = re.sub(r"\.{3,}\s*$", "", text).strip()
        out[log_no] = {
            "excerpt": text,
            "thumb": thumb_m.group(1) if thumb_m else "",
            "category": item.findtext("category") or "",
            "tags": [t.strip() for t in (item.findtext("tag") or "").split(",") if t.strip()],
            "pub_date": item.findtext("pubDate") or "",
        }
    return out
