"""
BigKinds API를 통한 뉴스 이슈 수집
"""

import json
import requests
from typing import List, Dict, Any, Optional
from config import Config


def kinds_issue_request(date: str, providers: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    KINDS 오늘의 이슈 API 호출
    
    Args:
        date: 'YYYY-MM-DD' 형식
        providers: 언론사 필터 (없으면 전체)
    
    Returns:
        API 응답 데이터
    """
    API_URL = "https://tools.kinds.or.kr/issue_ranking"
    
    payload = {
        "access_key": Config.KINDS_ACCESS_KEY,
        "argument": {
            "date": date,
            "provider": providers or Config.ISSUE_PROVIDERS_FILTER
        }
    }
    
    headers = {
        "Content-Type": "application/json; charset=UTF-8",
        "Accept": "application/json",
    }
    
    resp = requests.post(API_URL, headers=headers, data=json.dumps(payload))
    resp.raise_for_status()
    data = resp.json()

    if isinstance(data, dict) and data.get("error"):
        raise RuntimeError(f"KINDS API error: {data['error']}")
    
    return data


def parse_issue_response(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    API 응답 파싱
    
    Returns:
        {
            'date': 'YYYY-MM-DD',
            'topics': [
                {
                    'topic': str, 
                    'topic_rank': int, 
                    'topic_keyword': str, 
                    'news_cluster': [str, ...]
                },
                ...
            ]
        }
    """
    ro = data.get("return_object", {}) if isinstance(data, dict) else {}
    date = ro.get("date") or data.get("date")
    topics = ro.get("topics") or data.get("topics") or []
    
    norm_topics = []
    for t in topics if isinstance(topics, list) else []:
        norm_topics.append({
            "topic": t.get("topic"),
            "topic_rank": t.get("topic_rank"),
            "topic_keyword": t.get("topic_keyword"),
            "news_cluster": t.get("news_cluster") or [],
        })
    
    return {"date": date, "topics": norm_topics}


def collect_news_issues(date: str, max_topics: int = 10) -> Dict[str, Any]:
    """
    뉴스 이슈 수집 (메인 함수)
    
    Args:
        date: 수집할 날짜 (YYYY-MM-DD)
        max_topics: 최대 토픽 개수
    
    Returns:
        파싱된 이슈 데이터
    """
    print(f"📰 {date} 뉴스 이슈 수집 중...")
    
    data = kinds_issue_request(date=date)
    issue_obj = parse_issue_response(data)
    
    # 상위 N개만 추출
    issue_obj["topics"] = issue_obj["topics"][:max_topics]
    
    print(f"✅ {len(issue_obj['topics'])}개 이슈 수집 완료")
    
    return issue_obj
