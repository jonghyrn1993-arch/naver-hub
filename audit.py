# -*- coding: utf-8 -*-
"""네이버 블로그 전수 감사: 공개 설정과 검색 허용 상태를 훑는다.

구글 노출이 안 되는 원인 중 블로그 쪽 설정 문제를 먼저 걸러내는 용도.
"""
import collections
import json

from naverblog import fetch_post_list

if __name__ == "__main__":
    posts = fetch_post_list()

    print("\n총 글: %d편" % len(posts))
    print("공개설정(openType): %s   (2=전체공개)"
          % dict(collections.Counter(p.get("openType") for p in posts)))
    print("검색허용(searchYn): %s"
          % dict(collections.Counter(str(p.get("searchYn")).lower() for p in posts)))

    bad = [p for p in posts if str(p.get("searchYn")).lower() != "true"]
    print("\n검색 허용이 꺼진 글: %d편" % len(bad))
    for p in bad[:40]:
        print("  - %s  (%s)" % (p["title"], p["logNo"]))

    priv = [p for p in posts if str(p.get("openType")) != "2"]
    print("\n전체공개가 아닌 글: %d편" % len(priv))
    for p in priv[:20]:
        print("  - %s  (openType=%s)" % (p["title"], p.get("openType")))

    with open("posts.json", "w", encoding="utf-8") as f:
        json.dump(posts, f, ensure_ascii=False, indent=1)
    print("\n-> posts.json 저장 (%d편)" % len(posts))
