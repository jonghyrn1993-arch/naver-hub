# -*- coding: utf-8 -*-
"""허브를 다시 만들고 바뀐 게 있으면 GitHub 에 올린다.

매일 한 번 작업 스케줄러가 이걸 부른다. 새 글이 없으면 아무것도 하지 않는다.
"""
import os
import subprocess
import sys
from datetime import datetime

import build

HERE = os.path.dirname(os.path.abspath(__file__))


def git(*args, check=True):
    r = subprocess.run(["git"] + list(args), cwd=HERE,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        raise RuntimeError("git %s 실패:\n%s\n%s" % (" ".join(args), r.stdout, r.stderr))
    return r


def main():
    n_posts, n_pages = build.build(incremental="--full" not in sys.argv)

    if not os.path.isdir(os.path.join(HERE, ".git")):
        print("git 저장소가 아직 없다. 빌드만 하고 끝낸다.")
        return

    if not git("status", "--porcelain").stdout.strip():
        print("바뀐 게 없다. 올리지 않는다.")
        return

    git("add", "-A")
    msg = "글 목록 갱신 %s (%d편)" % (datetime.now().strftime("%Y-%m-%d"), n_posts)
    git("commit", "-m", msg)

    if git("remote", check=False).stdout.strip():
        push = git("push", check=False)
        if push.returncode != 0:
            print("push 실패:\n%s" % (push.stderr or push.stdout))
            sys.exit(1)
        print("올렸다: %s" % msg)
    else:
        print("커밋만 했다 (remote 미설정): %s" % msg)


if __name__ == "__main__":
    main()
