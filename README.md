# naver-hub — 네이버 블로그 구글 노출용 크롤 진입점

네이버 블로그(`blog.naver.com/100755`)는 `<head>` 수정이 막혀 있어 **구글 서치콘솔 소유권 확인이
불가능**하다. 그래서 색인 요청도, 사이트맵 제출도, 검색 성과 확인도 못 한다.

이 프로젝트는 내 소유 도메인(GitHub Pages)에 **글 목록 사이트**를 세워 그 자리를 대신한다.
서치콘솔에는 이 사이트를 등록하고, 구글은 여기 걸린 링크를 따라 네이버 원문을 발견한다.

본문을 통째로 옮기면 중복 콘텐츠가 되므로 **개별 글 페이지는 만들지 않는다.**
만드는 것은 목록 페이지(최신 · 카테고리별 · 월별)뿐이다.

## 파일

| 파일 | 하는 일 |
|---|---|
| `naverblog.py` | 네이버에서 글 목록과 RSS 요약을 긁어오는 공용 모듈 |
| `audit.py` | 전체 글의 공개 설정 / 검색 허용 상태 점검 |
| `build.py` | `docs/` 에 정적 사이트 + `sitemap.xml` 생성 |
| `publish.py` | 다시 빌드하고 바뀐 게 있으면 커밋·푸시 |
| `run_scheduled_naver_hub.bat` | 작업 스케줄러가 매일 부르는 진입점 |
| `config.json` | `base_url`, 사이트 제목·설명, 서치콘솔 인증 코드 |

## 쓰는 법

```
python audit.py                  # 블로그 설정 점검
python build.py                  # 전수 수집 후 빌드
python build.py --incremental    # 앞 5페이지만 보고 새 글만 반영
python publish.py                # 증분 빌드 + 커밋 + 푸시
python publish.py --full         # 전수 수집으로 빌드 + 커밋 + 푸시
```

## 처음 세팅

1. GitHub 저장소를 만들고 `config.json` 의 `base_url` 을
   `https://<계정>.github.io/<저장소>` 로 고친다.
2. `python build.py` 로 다시 빌드하고 푸시한다.
3. 저장소 Settings → Pages → Source 를 `main` 브랜치의 `/docs` 로 지정한다.
4. 구글 서치콘솔에 `base_url` 을 URL 접두어 속성으로 등록한다.
   HTML 태그 방식으로 받은 코드를 `config.json` 의 `google_verification` 에 넣고
   다시 빌드·푸시하면 인증된다.
5. 서치콘솔 → Sitemaps 에 `sitemap.xml` 을 제출한다.
6. 작업 스케줄러에 `run_scheduled_naver_hub.bat` 을 매일 한 번 등록한다.

## 한계

이 사이트는 구글이 새 글을 **더 빨리 발견하게** 만든다. 순위를 만들어주지는 않는다.
순위는 결국 네이버 원문의 제목·본문이 검색어와 얼마나 맞느냐로 갈린다.
