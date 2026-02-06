"""
뉴스 기사 크롤링 및 본문 추출
"""

import os
import re
import time
import random
import unicodedata
import requests
import json
from typing import List, Dict, Optional, Tuple
from urllib.parse import urlparse, parse_qs, urlunparse
from bs4 import BeautifulSoup, UnicodeDammit
from dateutil import parser
from config import Config

# ─────────────────────────────────────────────────────────────
# 설정 및 상수
# ─────────────────────────────────────────────────────────────

SAVE_ONLY_PROVIDERS = set(Config.ISSUE_PROVIDERS_FILTER)

NOISY_PATTERNS = re.compile(
    r"(ad|ads|advert|sponsor|banner|promo|related|recommend|rec-|"
    r"share|social|subscribe|footer|copyright|notice|policy|"
    r"widget|sidebar|nav|breadcrumb|comment|emoji|btn|login|"
    r"headline_list|breaking|hot|most|popular)", re.I
)

BAN_SUBSTRINGS = [
    "all rights reserved", "무단 전재", "무단전재", "재배포 금지", "ai학습 이용 금지",
    "저작권", "copyright",
    "구독", "앱에서 보기", "앱에서만", "뉴스레터", "알림 설정", "프리미엄", "유료회원",
    "공유하기", "페이스북", "트위터", "카카오", "인스타그램", "유튜브",
    "속보", "많이 본", "추천 기사", "연관 기사", "관련 기사",
    "문의:", "문의 ‧ 제보", "제보:", "광고 문의", "후원하기",
    "사진=", "영상="
]

DOMAIN_SELECTORS = {
    # 국민일보
    "www.kmib.co.kr": [
        "#articleBody", "div#articleBody", ".article-body", ".art_body", ".news_view", "article",
        "[itemprop='articleBody']"
    ],
    "m.kmib.co.kr": [
        "#articleBody", ".article-body", ".art_body", ".news_view", "article",
        "[itemprop='articleBody']"
    ],
    "amp.kmib.co.kr": [
        "[itemprop='articleBody']", "article", "#articleBody"
    ],
    # SBS
    "news.sbs.co.kr": [
        "[itemprop='articleBody']", "article", "#news_body_area", ".article_cont", ".news_cnt",
        ".news_text", ".text_area", ".viewer"
    ],
    # KBS
    "news.kbs.co.kr": [
        "[itemprop='articleBody']",
        "article .detail-body", "article .content", "article",
        "#cont_newstext", ".detailContent", ".detail_body",
        "#news_textArea", "#newsContent", ".news_body", "#content", "#contents"
    ],
    # MBC
    "imnews.imbc.com": [
        ".news_txt", "[itemprop='articleBody']", "article .news_txt",
    ],
    # 조선
    "www.chosun.com": [
        "[itemprop='articleBody']", "article .article-body", "article .content", "article",
        "div#news_item", "div#content", "div#contents", ".article-body__content"
    ],
    "news.chosun.com": [
        "[itemprop='articleBody']", "article", "#news_body_id", ".article-body", ".par", "#news_content"
    ],
    "amp.chosun.com": [
        "[itemprop='articleBody']", "article", ".article-body", ".content", "#content"
    ],
    # 중앙
    "www.joongang.co.kr": [
        "[itemprop='articleBody']", "article .article-body", "article .content", "article",
        "#article_body", ".article-body", ".ab_sub",
    ],
    "news.joins.com": [
        "[itemprop='articleBody']", "article", "#article_body", ".article_body", ".content"
    ],
    # 동아
    "www.donga.com": [
        "[itemprop='articleBody']", "article .article_body", "article .article_txt", "article",
        "#content", ".content", ".article_txt", ".article_body"
    ],
    "news.donga.com": [
        "[itemprop='articleBody']", "article .article_txt", "article .article_body", "article",
        "#content", ".content"
    ],
    # 한겨레
    "www.hani.co.kr": [
        "[itemprop='articleBody']", "article .article-text", "article .text", "article",
        ".article-text", ".text", "#contents", "#content"
    ],
    "m.hani.co.kr": [
        "[itemprop='articleBody']", "article .text", "article", ".text", ".article-text", "#content", "#contents"
    ],
    # 경향
    "www.khan.co.kr": [
        "[itemprop='articleBody']", "article .article-body", "article .article_txt", "article",
        "#articleBody", ".art_body", ".scroll-article", "#article", ".article_txt",
        "article[role='article']", ".amp-article-body", "main article", "main .article-body", "#contents"
    ],
    "m.khan.co.kr": [
        "[itemprop='articleBody']", "#articleBody", ".article-body", "article",
        ".art_body", ".article_txt", "#content"
    ],
}

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
URL_RE = re.compile(r"https?://\S+")
MULTIDASH_RE = re.compile(r"[-–—]{3,}")
SENTENCE_END_RE = re.compile(r"[\.!?…]|[다요죠]\s*$|["']\s*$")

REQ_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/122.0.0.0 Safari/537.36"),
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8"
}

DENY_FALLBACK_HOSTS = set()

KINDS_HEADERS = {"Content-Type": "application/json"}

# ─────────────────────────────────────────────────────────────
# 유틸리티 함수
# ─────────────────────────────────────────────────────────────

def clean_date(raw_date: str) -> str:
    """ISO8601 날짜를 YYYY-MM-DD로 변환"""
    try:
        dt = parser.parse(raw_date)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return raw_date

def normalize_text(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("\r\n", "\n")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s.strip())
    return s

def safe_filename(name: str, maxlen: int = 80) -> str:
    name = name or "article"
    name = re.sub(r"[^\w가-힣\-_. ]", "_", name)
    return name[:maxlen].strip() or "article"

def _line_is_noise(line: str) -> bool:
    s = line.strip()
    if not s:
        return True
    low = s.lower()
    if EMAIL_RE.search(s) and len(s) < 80:
        return True
    if URL_RE.search(s) and (len(s) < 80 or (sum(len(x) for x in URL_RE.findall(s))/max(1,len(s)) > 0.3)):
        return True
    if MULTIDASH_RE.search(s):
        return True
    for bad in BAN_SUBSTRINGS:
        if bad.lower() in low:
            return True
    if len(s) < 15:
        return True
    return False

def _strip_noisy_nodes(soup: BeautifulSoup) -> None:
    for tag in soup.select("script, style, noscript, iframe, form, aside, nav, header, footer"):
        try:
            tag.decompose()
        except Exception:
            pass
    for node in list(soup.find_all(True)):
        try:
            node_id = node.get("id") or ""
            cls = node.get("class") or []
            role = (node.get("role") or "").lower()
            id_ok = bool(NOISY_PATTERNS.search(str(node_id)))
            cls_ok = any(NOISY_PATTERNS.search(str(c)) for c in cls)
            role_ok = role in {"banner", "complementary", "navigation"}
            text_len = len(node.get_text(strip=True) or "")
            link_len = sum(len(a.get_text(strip=True) or "") for a in node.find_all("a"))
            link_dense = (link_len / max(1, text_len)) if text_len else 0.0
            if id_ok or cls_ok or role_ok or link_dense > 0.5:
                node.decompose()
        except Exception:
            continue

def _get_text_from_container(node: BeautifulSoup) -> str:
    ps = node.find_all("p")
    if ps:
        parts = [p.get_text(" ", strip=True) for p in ps]
        parts = [t for t in parts if t and len(t) > 3]
        return " ".join(parts)
    for br in node.find_all("br"):
        br.replace_with("\n")
    return node.get_text(" ", strip=True)

def post_cleanup_text(text: str) -> str:
    text = text.replace("\xa0", " ").replace("\u200b", "")
    text = re.sub(r"\s+\n", "\n", text)
    lines = [ln.strip() for ln in text.splitlines()]
    kept: List[str] = []
    for ln in lines:
        if _line_is_noise(ln):
            continue
        ln = EMAIL_RE.sub("", ln)
        ln = URL_RE.sub("", ln)
        ln = re.sub(r"\s{2,}", " ", ln).strip()
        if ln:
            kept.append(ln)
    out = "\n\n".join(kept)
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return out

def post_cleanup_text_broadcast(text: str) -> str:
    text = text.replace("\xa0", " ").replace("\u200b", "")
    text = re.sub(r"\s+\n", "\n", text)
    lines = []
    for ln in text.splitlines():
        ln = EMAIL_RE.sub("", ln)
        ln = URL_RE.sub("", ln)
        ln = re.sub(r"\s{2,}", " ", ln).strip()
        lines.append(ln)
    out = "\n".join([x for x in lines if x is not None])
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return out

def post_cleanup_text_light(text: str) -> str:
    text = text.replace("\xa0", " ").replace("\u200b", "")
    text = re.sub(r"\s+\n", "\n", text)
    lines = []
    for ln in text.splitlines():
        if not ln.strip():
            lines.append("")
            continue
        ln = EMAIL_RE.sub("", ln)
        ln = URL_RE.sub("", ln)
        ln = re.sub(r"\s{2,}", " ", ln).strip()
        lines.append(ln)
    out = "\n".join(lines)
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return out


# ─────────────────────────────────────────────────────────────
# 제목 추출 & 유사도
# ─────────────────────────────────────────────────────────────

GENERIC_TITLE_PATTERNS = [
    r"^\s*경향\s*신문\s*$", r"^\s*경향신문\s*$", r"^\s*The\s+Kyunghyang\s+Shinmun\s*$",
    r"^\s*한겨레\s*$", r"^\s*Hankyoreh\s*$",
    r"^\s*SBS\s*뉴스\s*$", r"^\s*KBS\s*뉴스\s*$", r"^\s*MBC\s*뉴스\s*$",
    r"^\s*조선일보\s*$", r"^\s*중앙일보\s*$", r"^\s*동아일보\s*$",
    r"^\s*국민일보\s*$", r"^\s*Chosun\s*Ilbo\s*$", r"^\s*JoongAng\s*Ilbo\s*$",
    r"^\s*Donga\s*Ilbo\s*$",
]
GENERIC_TITLE_RE = re.compile("|".join(GENERIC_TITLE_PATTERNS), re.IGNORECASE)

def is_generic_title(title: str, provider: str) -> bool:
    t = (title or "").strip()
    if not t:
        return True
    if GENERIC_TITLE_RE.match(t):
        return True
    if re.sub(r"\s+", "", t) == re.sub(r"\s+", "", provider or ""):
        return True
    if len(t) < 4:
        return True
    return False

def _extract_title_from_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    # JSON-LD headline
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = tag.string or tag.text
            if not data:
                continue
            jd = json.loads(data)
            objs = [jd] if isinstance(jd, dict) else (jd if isinstance(jd, list) else [])
            if isinstance(jd, dict) and "@graph" in jd and isinstance(jd["@graph"], list):
                objs += jd["@graph"]
            for obj in objs:
                if isinstance(obj, dict):
                    headline = obj.get("headline")
                    if isinstance(headline, str) and headline.strip():
                        return normalize_text(headline)
        except Exception:
            continue
    # twitter:title
    tw = soup.find("meta", attrs={"name": "twitter:title"})
    if tw and tw.get("content"):
        return normalize_text(tw["content"])
    # og:title
    og = soup.find("meta", attrs={"property": "og:title"}) or soup.find("meta", attrs={"name": "og:title"})
    if og and og.get("content"):
        return normalize_text(og["content"])
    # h1
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        return normalize_text(h1.get_text(" ", strip=True))
    # <title>
    if soup.title and soup.title.get_text(strip=True):
        return normalize_text(soup.title.get_text(" ", strip=True))
    return ""

def _title_similarity(a: str, b: str) -> float:
    def toks(x: str) -> set:
        x = re.sub(r"[^0-9A-Za-z가-힣 ]", " ", x or "")
        return set([t for t in x.lower().split() if t])
    A, B = toks(a), toks(b)
    if not A or not B:
        return 0.0
    return len(A & B) / len(A | B)

# ─────────────────────────────────────────────────────────────
# HTML 파싱
# ─────────────────────────────────────────────────────────────

def _decode_bytes_safely(content: bytes, headers: dict) -> str:
    ct = (headers.get("Content-Type") or headers.get("content-type") or "").lower()
    if "charset=" in ct:
        enc = ct.split("charset=")[-1].split(";")[0].strip()
        try:
            return content.decode(enc, errors="replace")
        except Exception:
            pass
    dammit = UnicodeDammit(content, is_html=True)
    if dammit.unicode_markup:
        return dammit.unicode_markup
    for enc in ("utf-8", "euc-kr", "cp949", "iso-8859-1"):
        try:
            return content.decode(enc, errors="replace")
        except Exception:
            continue
    return content.decode("utf-8", errors="replace")

def _extract_from_html(html: str, url_hint: str = "") -> Optional[str]:
    soup = BeautifulSoup(html, "html.parser")
    _strip_noisy_nodes(soup)
    host = urlparse(url_hint).netloc.lower()

    def _clean(txt: str) -> str:
        if "imnews.imbc.com" in host or "news.kbs.co.kr" in host:
            return post_cleanup_text_broadcast(txt)
        if "khan.co.kr" in host and "/amp" in url_hint:
            return post_cleanup_text_light(txt)
        return post_cleanup_text(txt)

    # JSON-LD
    try:
        for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
            data = tag.string or tag.text
            if not data:
                continue
            jd = json.loads(data)
            objs = [jd] if isinstance(jd, dict) else (jd if isinstance(jd, list) else [])
            if isinstance(jd, dict) and "@graph" in jd and isinstance(jd["@graph"], list):
                objs += jd["@graph"]
            for obj in objs:
                if not isinstance(obj, dict):
                    continue
                tp = obj.get("@type") or obj.get("type") or ""
                if isinstance(tp, list):
                    tp = " ".join(tp)
                if "NewsArticle" in tp or "Article" in tp:
                    body = obj.get("articleBody") or obj.get("body")
                    if body and len(body) > 180:
                        return post_cleanup_text(normalize_text(body))
    except Exception:
        pass

    # 도메인 전용
    if host in DOMAIN_SELECTORS:
        for sel in DOMAIN_SELECTORS[host]:
            node = soup.select_one(sel)
            if node and node.get_text(strip=True):
                _strip_noisy_nodes(node)
                txt = _get_text_from_container(node)
                txt = _clean(txt)
                if len(txt) > 180:
                    return txt

    # itemprop
    node = soup.select_one('[itemprop="articleBody"]')
    if node and node.get_text(strip=True):
        _strip_noisy_nodes(node)
        txt = _get_text_from_container(node)
        txt = _clean(txt)
        if len(txt) > 180:
            return txt

    # article
    art = soup.find("article")
    if art and art.get_text(strip=True):
        _strip_noisy_nodes(art)
        txt = _get_text_from_container(art)
        txt = _clean(txt)
        if len(txt) > 180:
            return txt

    # 범용 후보
    for sel in [
        "div#articleBodyContents", "div#newsEndContents",
        "div.article_body", "div#articeBody", "div.article",
        "div#content", "div#contents", ".article-body", ".content"
    ]:
        node = soup.select_one(sel)
        if node and node.get_text(strip=True):
            _strip_noisy_nodes(node)
            txt = _get_text_from_container(node)
            txt = _clean(txt)
            if len(txt) > 180:
                return txt

    # 2차: html5lib
    try:
        soup_h5 = BeautifulSoup(html, "html5lib")
        _strip_noisy_nodes(soup_h5)

        if host in DOMAIN_SELECTORS:
            for sel in DOMAIN_SELECTORS[host]:
                node = soup_h5.select_one(sel)
                if node and node.get_text(strip=True):
                    _strip_noisy_nodes(node)
                    txt = _get_text_from_container(node)
                    txt = _clean(txt)
                    if len(txt) > 180:
                        return txt

        node = soup_h5.select_one('[itemprop="articleBody"]')
        if node and node.get_text(strip=True):
            _strip_noisy_nodes(node)
            txt = _get_text_from_container(node)
            txt = _clean(txt)
            if len(txt) > 180:
                return txt

        art = soup_h5.find("article")
        if art and art.get_text(strip=True):
            _strip_noisy_nodes(art)
            txt = _get_text_from_container(art)
            txt = _clean(txt)
            if len(txt) > 180:
                return txt
    except Exception:
        pass

    return None

# ─────────────────────────────────────────────────────────────
# URL 리라이트
# ─────────────────────────────────────────────────────────────

def make_rewrite_candidates(url: str) -> List[str]:
    cand = [url]
    try:
        p = urlparse(url)
        host = p.netloc.lower()
        path = p.path
        query = p.query

        def _with(host_new=None, path_new=None, query_new=None):
            return urlunparse((
                p.scheme, host_new or host, path_new if path_new is not None else path,
                p.params, query_new if query_new is not None else query, p.fragment
            ))

        # SBS AMP
        if "news.sbs.co.kr" in host:
            q = parse_qs(query)
            nid = (q.get("news_id") or [None])[0]
            if nid:
                cand.append(f"https://news.sbs.co.kr/amp/news.amp?news_id={nid}")

        # 중앙 AMP
        if "joongang.co.kr" in host or "joins.com" in host:
            q_amp = query + ("&" if query else "") + "view=amp"
            cand.append(_with(query_new=q_amp))

        # KMIB
        if "kmib.co.kr" in host:
            cand.append(_with(host_new="m.kmib.co.kr"))
            cand.append(_with(host_new="news.kmib.co.kr"))
            cand.append(_with(host_new="amp.kmib.co.kr"))
            q_amp = query + ("&" if query else "") + "view=amp"
            cand.append(_with(query_new=q_amp))

        # 조선
        if "chosun.com" in host:
            if not path.endswith("/amp/"):
                cand.append(_with(path_new=(path.rstrip("/") + "/amp/")))
            cand.append(_with(host_new="news.chosun.com"))

        # 동아
        if "donga.com" in host:
            if "news.donga.com" in host:
                if "/all/" in path and "/amp/" not in path:
                    cand.append(_with(path_new=path.replace("/all/", "/amp/all/")))
                cand.append(_with(host_new="www.donga.com"))
            else:
                cand.append(_with(host_new="news.donga.com"))
                if "/all/" in path and "/amp/" not in path:
                    cand.append(_with(host_new="news.donga.com", path_new=path.replace("/all/", "/amp/all/")))

        # 한겨레
        if "hani.co.kr" in host:
            cand.append(_with(host_new="m.hani.co.kr"))
            q_m = query + ("&" if query else "") + "m=1"
            cand.append(_with(query_new=q_m))

        # 경향
        if "khan.co.kr" in host:
            if not path.endswith("/amp"):
                cand.append(_with(path_new=(path.rstrip("/") + "/amp")))
            cand.append(_with(host_new="m.khan.co.kr"))
            q_amp = query + ("&" if query else "") + "output=amp"
            cand.append(_with(query_new=q_amp))

    except Exception:
        pass

    # 중복 제거
    uniq, seen = [], set()
    for c in cand:
        if c and c not in seen:
            uniq.append(c); seen.add(c)
    return uniq

# ─────────────────────────────────────────────────────────────
# 원문 크롤링
# ─────────────────────────────────────────────────────────────

def crawl_article(url: str, timeout: int = 15) -> Optional[Tuple[str, str]]:
    """성공 시 (본문, 페이지제목) 반환"""
    try:
        candidates = make_rewrite_candidates(url)

        for i, u in enumerate(candidates):
            if i > 0:
                print(f"  ↳ REWRITE TRY[{i}]: {u}")
            time.sleep(random.uniform(0.6, 1.2))

            if urlparse(u).netloc.lower() in DENY_FALLBACK_HOSTS:
                print(f"  ↳ FALLBACK DISABLED for host={urlparse(u).netloc}")
                continue

            r = requests.get(u, headers=REQ_HEADERS, timeout=timeout)
            print(f"  ↳ GET {u} status={r.status_code}")
            if r.status_code != 200 or not r.content:
                continue
            html = _decode_bytes_safely(r.content, r.headers)

            # MBC 방어
            if "imnews.imbc.com" in urlparse(u).netloc.lower():
                low = html.lower()
                if ("요청하신 페이지를 찾을 수 없습니다" in html) or ("class=\"error\"" in low and "mbc" in low):
                    continue

            body = _extract_from_html(html, url_hint=u)
            if body:
                page_title = _extract_title_from_html(html)
                print(f"  ↳ EXTRACT OK len={len(body)}")
                return body, page_title

            # AMP 재시도
            try:
                soup_tmp = BeautifulSoup(html, "html.parser")
                amp = soup_tmp.find("link", rel=lambda v: v and "amphtml" in v.lower())
                if amp and amp.get("href"):
                    amp_url = requests.compat.urljoin(u, amp["href"])
                    print(f"  ↳ AMP TRY: {amp_url}")
                    time.sleep(random.uniform(0.5, 1.0))
                    r2 = requests.get(amp_url, headers=REQ_HEADERS, timeout=timeout)
                    if r2.status_code == 200 and r2.content:
                        html2 = _decode_bytes_safely(r2.content, r2.headers)
                        body2 = _extract_from_html(html2, url_hint=amp_url)
                        if body2:
                            page_title2 = _extract_title_from_html(html2)
                            print(f"  ↳ EXTRACT OK (AMP) len={len(body2)}")
                            return body2, page_title2
            except Exception:
                pass

        return None

    except requests.RequestException as e:
        print(f"  ↳ GET ERROR: {e}")
        return None

# ─────────────────────────────────────────────────────────────
# KINDS API
# ─────────────────────────────────────────────────────────────

def kinds_fetch_news_detail(news_ids: List[str], fields: Optional[List[str]] = None) -> Dict:
    url = "https://tools.kinds.or.kr/search/news"
    argument = {"news_ids": news_ids}
    if fields:
        argument["fields"] = fields
    payload = {"access_key": Config.KINDS_ACCESS_KEY, "argument": argument}
    r = requests.post(url, json=payload, headers=KINDS_HEADERS, timeout=20)
    r.raise_for_status()
    return r.json()

def looks_truncated(text: str) -> bool:
    if not text:
        return True
    if len(text) < Config.MIN_REASONABLE_LEN:
        return True
    tail = text.strip()[-40:]
    if not SENTENCE_END_RE.search(tail):
        return True
    return False

# ─────────────────────────────────────────────────────────────
# 메인: 기사 크롤링
# ─────────────────────────────────────────────────────────────

def crawl_articles(issue_obj: Dict[str, Any], per_topic_docs: int = 1) -> List[Dict]:
    """
    이슈 데이터에서 뉴스 기사 크롤링
    
    Args:
        issue_obj: collect_news_issues() 반환값
        per_topic_docs: 토픽당 수집할 기사 개수
    
    Returns:
        기사 데이터 리스트
    """
    print(f"\n📝 기사 크롤링 시작...")
    
    topics = issue_obj.get("topics", [])
    out: List[Dict] = []

    for t in topics:
        topic_name = t.get("topic")
        topic_rank = t.get("topic_rank")
        cluster = (t.get("news_cluster") or [])[:per_topic_docs]
        
        if not cluster:
            continue

        detail = kinds_fetch_news_detail(
            news_ids=cluster,
            fields=["news_id","title","content","content_original","provider",
                   "published_at","provider_link_page","url","link","byline","category"]
        )
        
        docs = (detail.get("return_object", {}) or {}).get("documents", [])
        if not docs:
            continue

        for d in docs:
            title = d.get("title","") or ""
            provider = d.get("provider","") or ""
            
            if SAVE_ONLY_PROVIDERS and provider not in SAVE_ONLY_PROVIDERS:
                print(f"  ↳ SKIP: provider={provider}")
                continue
                
            category = d.get("category","") or ""
            published_at = d.get("published_at","") or ""
            url = d.get("provider_link_page") or d.get("url") or d.get("link") or ""

            # KINDS 본문
            body_kinds_raw = d.get("content_original") or d.get("content") or ""
            body_kinds = normalize_text(body_kinds_raw)

            final_body = body_kinds
            final_title = title
            used_fallback = False

            # 잘림 감지 → 폴백
            if looks_truncated(final_body):
                if url and urlparse(url).netloc.lower() not in DENY_FALLBACK_HOSTS:
                    crawled = crawl_article(url)
                    if crawled:
                        crawled_body, crawled_title = crawled
                        if len(crawled_body) > len(final_body) or \
                           (len(final_body) <= 250 and len(crawled_body) >= 400):
                            used_fallback = True
                            final_body = normalize_text(crawled_body)

                            sim = _title_similarity(title, crawled_title or "")
                            if sim < 0.35 and is_generic_title(crawled_title or "", provider):
                                print(f"  ↳ SKIP: 제목 미스매치 & 폴백 제목이 매체명")
                                continue
                            
                            if crawled_title and not is_generic_title(crawled_title, provider) and sim < 0.35:
                                final_title = crawled_title

            # 폴백 실패 & 본문 짧음 → 스킵
            if not used_fallback and len(final_body) <= Config.MIN_KINDS_LEN_TO_SAVE_IF_NO_FALLBACK:
                print(f"  ↳ SKIP: 폴백 실패 & 본문 짧음")
                continue

            print(f"[{topic_name}] '{final_title[:30]}...' ({provider}) ✅")

            out.append({
                "topic": topic_name,
                "topic_rank": topic_rank,
                "news_id": d.get("news_id",""),
                "title": final_title,
                "provider": provider,
                "category": category,
                "published_at": clean_date(published_at),
                "url": url,
                "content": final_body,
                "source": "fallback" if used_fallback else "kinds"
            })

    print(f"✅ 크롤링 완료: {len(out)}개 기사")
    return out

