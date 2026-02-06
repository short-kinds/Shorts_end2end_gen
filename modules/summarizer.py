"""
뉴스 기사 요약 (T5 기반)
"""

import re
import torch
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
from typing import List, Dict
from config import Config

# 모델 초기화 (싱글톤)
_model = None
_tokenizer = None

def get_model():
    global _model, _tokenizer
    if _model is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"📚 요약 모델 로딩 중... (device: {device})")
        _tokenizer = AutoTokenizer.from_pretrained(Config.SUMMARY_MODEL)
        _model = AutoModelForSeq2SeqLM.from_pretrained(Config.SUMMARY_MODEL).to(device).eval()
    return _model, _tokenizer

def clean(x): 
    x = re.sub(r"\[[^\]]+\]", " ", x)
    x = re.sub(r"\([^)]+\)", " ", x)
    x = re.sub(r"무단 전재.*?금지", " ", x)
    x = re.sub(r"\s+", " ", x)
    return x.strip()

def postprocess(summary: str) -> str:
    summary = re.sub(r"[가-힣]{2,4}\s?기자", "", summary)
    summary = re.sub(r"연합뉴스", "", summary)
    summary = re.sub(r"\s+", " ", summary)
    return summary.strip()

@torch.inference_mode()
def summarize(text, max_in=1024, max_out=100, min_out=50,
              beams=5, lp=0.8, no_rep=3, rep_penalty=2.0):
    model, tokenizer = get_model()
    device = next(model.parameters()).device
    
    text = clean(text)
    inputs = tokenizer([text], truncation=True, max_length=max_in, return_tensors="pt").to(device)
    ids = model.generate(
        **inputs,
        num_beams=beams,
        max_length=max_out, 
        min_length=min_out,
        length_penalty=lp,
        no_repeat_ngram_size=no_rep,
        repetition_penalty=rep_penalty,
        early_stopping=True
    )
    return tokenizer.decode(ids[0], skip_special_tokens=True)

def chunk_text(text, n=4):
    """텍스트를 n개로 균등 분할"""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    k, m = divmod(len(sentences), n)
    chunks, start = [], 0
    for i in range(n):
        end = start + k + (1 if i < m else 0)
        chunks.append(" ".join(sentences[start:end]))
        start = end
    return chunks

def summarize_dynamic(text):
    """텍스트 길이에 따라 동적으로 요약"""
    tokenizer = get_model()[1]
    length = len(tokenizer.tokenize(text))
    
    if length < 100:
        min_out, max_out = 10, 80
    elif length < 300:
        min_out, max_out = 30, 100
    else:
        min_out, max_out = 50, 120
        
    return summarize(text, min_out=min_out, max_out=max_out)

def clean_for_prompt(text: str) -> str:
    """이미지 프롬프트용 안전 문자열"""
    remove_chars = ['"', "'", """, """, "'", "'"]
    for ch in remove_chars:
        text = text.replace(ch, "")
    return text.strip()

def summarize_in_parts(text, parts=4):
    """텍스트를 파트별로 나눠 요약"""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    
    # 파트 개수 자동 조정
    if len(sentences) < parts:
        parts = max(1, len(sentences))
    
    chunks = chunk_text(text, n=parts)
    summaries = []
    
    for i, chunk in enumerate(chunks, 1):
        if not chunk.strip():
            continue
        summary = summarize_dynamic(chunk)
        summary = clean_for_prompt(summary)
        summary = postprocess(summary)
        summaries.append(f"파트 {i}: {summary}")
    
    return summaries

def summarize_articles(articles: List[Dict]) -> List[Dict]:
    """
    기사 리스트를 요약
    
    Args:
        articles: crawl_articles() 반환값
    
    Returns:
        요약이 추가된 기사 리스트
    """
    print(f"\n✍️ 기사 요약 시작...")
    
    for i, art in enumerate(articles, 1):
        content = art.get("content", "")
        if not content.strip():
            print(f"  [{i}] SKIP: 본문 없음")
            art["summaries"] = []
            continue
        
        print(f"  [{i}] {art.get('title', '')[:40]}...")
        summaries = summarize_in_parts(content, parts=Config.SUMMARY_PARTS)
        art["summaries"] = summaries
        
        for s in summaries:
            print(f"    - {s}")
    
    print(f"✅ 요약 완료: {len(articles)}개 기사")
    return articles
