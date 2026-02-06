#!/usr/bin/env python3
"""
ShortKinds - 뉴스 숏츠 자동 생성 시스템

사용법:
    python main.py --date 2025-02-06 --max-topics 5 --per-topic-docs 1
"""

import argparse
import json
import os
from datetime import datetime
from config import Config
from modules import (
    collect_news_issues,
    crawl_articles,
    summarize_articles,
    generate_images,
    generate_tts,
    generate_video
)


def save_checkpoint(data: dict, filename: str):
    """중간 결과 저장 (체크포인트)"""
    path = os.path.join(Config.OUTPUT_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"💾 체크포인트 저장: {path}")


def load_checkpoint(filename: str):
    """체크포인트 불러오기"""
    path = os.path.join(Config.OUTPUT_DIR, filename)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def main(date: str, max_topics: int = 5, per_topic_docs: int = 1, 
         top_text: str = None, skip_to: str = None):
    """
    메인 파이프라인 실행
    
    Args:
        date: 수집할 날짜 (YYYY-MM-DD)
        max_topics: 최대 토픽 개수
        per_topic_docs: 토픽당 기사 개수
        top_text: 영상 상단 공통 자막
        skip_to: 특정 단계로 스킵 (collect, crawl, summarize, image, tts, video)
    """
    print("=" * 80)
    print("🎬 ShortKinds - 뉴스 숏츠 자동 생성 시작")
    print("=" * 80)
    print(f"날짜: {date}")
    print(f"최대 토픽: {max_topics}")
    print(f"토픽당 기사: {per_topic_docs}")
    print("=" * 80)
    
    # 설정 검증 및 디렉토리 생성
    Config.validate()
    Config.create_directories()
    
    # ===== 1. 뉴스 이슈 수집 =====
    if skip_to is None or skip_to == "collect":
        issues = collect_news_issues(date=date, max_topics=max_topics)
        save_checkpoint(issues, f"checkpoint_1_issues_{date}.json")
    else:
        issues = load_checkpoint(f"checkpoint_1_issues_{date}.json")
        if issues is None:
            raise ValueError("체크포인트 파일이 없습니다. skip_to를 사용할 수 없습니다.")
    
    if skip_to == "collect":
        return
    
    # ===== 2. 기사 크롤링 =====
    if skip_to is None or skip_to == "crawl":
        articles = crawl_articles(issues, per_topic_docs=per_topic_docs)
        save_checkpoint({"articles": articles}, f"checkpoint_2_articles_{date}.json")
    else:
        checkpoint = load_checkpoint(f"checkpoint_2_articles_{date}.json")
        articles = checkpoint["articles"] if checkpoint else []
    
    if skip_to == "crawl":
        return
    
    if not articles:
        print("❌ 수집된 기사가 없습니다.")
        return
    
    # ===== 3. 기사 요약 =====
    if skip_to is None or skip_to == "summarize":
        articles = summarize_articles(articles)
        save_checkpoint({"articles": articles}, f"checkpoint_3_summaries_{date}.json")
    else:
        checkpoint = load_checkpoint(f"checkpoint_3_summaries_{date}.json")
        articles = checkpoint["articles"] if checkpoint else []
    
    if skip_to == "summarize":
        return
    
    # ===== 4. 이미지 생성 =====
    if skip_to is None or skip_to == "image":
        articles = generate_images(articles)
        save_checkpoint({"articles": articles}, f"checkpoint_4_images_{date}.json")
    else:
        checkpoint = load_checkpoint(f"checkpoint_4_images_{date}.json")
        articles = checkpoint["articles"] if checkpoint else []
    
    if skip_to == "image":
        return
    
    # ===== 5. TTS 생성 =====
    if skip_to is None or skip_to == "tts":
        articles = generate_tts(articles)
        save_checkpoint({"articles": articles}, f"checkpoint_5_tts_{date}.json")
    else:
        checkpoint = load_checkpoint(f"checkpoint_5_tts_{date}.json")
        articles = checkpoint["articles"] if checkpoint else []
    
    if skip_to == "tts":
        return
    
    # ===== 6. 영상 생성 =====
    articles = generate_video(articles, top_text=top_text)
    
    # ===== 최종 결과 저장 =====
    final_output = {
        "date": date,
        "created_at": datetime.now().isoformat(),
        "total_articles": len(articles),
        "articles": articles
    }
    
    final_path = os.path.join(Config.OUTPUT_DIR, f"final_result_{date}.json")
    with open(final_path, "w", encoding="utf-8") as f:
        json.dump(final_output, f, ensure_ascii=False, indent=2)
    
    print("\n" + "=" * 80)
    print("✅ 전체 파이프라인 완료!")
    print("=" * 80)
    print(f"📊 총 {len(articles)}개 기사 처리")
    print(f"📁 결과 저장: {final_path}")
    print(f"📁 영상 저장: {Config.VIDEOS_DIR}")
    print("=" * 80)
    
    # 생성된 영상 목록 출력
    videos = [art.get("video_path") for art in articles if art.get("video_path")]
    if videos:
        print(f"\n🎥 생성된 영상 ({len(videos)}개):")
        for v in videos:
            print(f"  - {v}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="ShortKinds - 뉴스 숏츠 자동 생성 시스템"
    )
    
    parser.add_argument(
        "--date",
        type=str,
        default=datetime.now().strftime("%Y-%m-%d"),
        help="수집할 날짜 (YYYY-MM-DD, 기본값: 오늘)"
    )
    
    parser.add_argument(
        "--max-topics",
        type=int,
        default=5,
        help="최대 토픽 개수 (기본값: 5)"
    )
    
    parser.add_argument(
        "--per-topic-docs",
        type=int,
        default=1,
        help="토픽당 기사 개수 (기본값: 1)"
    )
    
    parser.add_argument(
        "--top-text",
        type=str,
        default=None,
        help="영상 상단 공통 자막 (옵션)"
    )
    
    parser.add_argument(
        "--skip-to",
        type=str,
        choices=["collect", "crawl", "summarize", "image", "tts", "video"],
        default=None,
        help="특정 단계로 스킵 (체크포인트 필요)"
    )
    
    args = parser.parse_args()
    
    try:
        main(
            date=args.date,
            max_topics=args.max_topics,
            per_topic_docs=args.per_topic_docs,
            top_text=args.top_text,
            skip_to=args.skip_to
        )
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
