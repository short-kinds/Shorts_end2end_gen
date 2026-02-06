"""
Google Cloud TTS를 이용한 음성 생성
"""

import os
import re
from google.cloud import texttospeech
from typing import List, Dict
from config import Config

# TTS 클라이언트 초기화 (싱글톤)
_tts_client = None

def get_tts_client():
    global _tts_client
    if _tts_client is None:
        # 환경 변수 설정 확인
        if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = Config.GOOGLE_APPLICATION_CREDENTIALS
        
        print(f"🔊 TTS 클라이언트 초기화 중...")
        _tts_client = texttospeech.TextToSpeechClient()
    return _tts_client

PART_PREFIX = re.compile(r"^\s*파트\s*\d+\s*:\s*")

def strip_part_prefix(text: str) -> str:
    """'파트 N:' 접두어 제거"""
    return PART_PREFIX.sub("", text).strip()

def generate_tts_for_text(text: str, output_path: str) -> str:
    """
    단일 텍스트를 TTS로 변환
    
    Args:
        text: 변환할 텍스트
        output_path: 저장 경로
    
    Returns:
        저장된 파일 경로
    """
    client = get_tts_client()
    
    # 파트 접두어 제거
    clean_text = strip_part_prefix(text)
    
    synthesis_input = texttospeech.SynthesisInput(text=clean_text)
    
    voice = texttospeech.VoiceSelectionParams(
        language_code=Config.TTS_LANGUAGE_CODE,
        name=Config.TTS_VOICE_NAME,
    )
    
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3,
        speaking_rate=Config.TTS_SPEAKING_RATE,
        pitch=Config.TTS_PITCH,
    )
    
    response = client.synthesize_speech(
        input=synthesis_input,
        voice=voice,
        audio_config=audio_config
    )
    
    with open(output_path, "wb") as f:
        f.write(response.audio_content)
    
    return output_path

def generate_tts(articles: List[Dict]) -> List[Dict]:
    """
    요약문을 TTS로 변환
    
    Args:
        articles: summarize_articles() 또는 generate_images() 반환값
    
    Returns:
        TTS 파일 경로가 추가된 기사 리스트
    """
    print(f"\n🔊 TTS 생성 시작...")
    
    for art_idx, art in enumerate(articles, 1):
        summaries = art.get("summaries", [])
        if not summaries:
            print(f"  [{art_idx}] SKIP: 요약 없음")
            art["tts_files"] = []
            continue
        
        print(f"  [{art_idx}] {art.get('title', '')[:40]}...")
        
        tts_files = []
        for part_idx, summary in enumerate(summaries, 1):
            filename = f"{art_idx:03d}_{part_idx:02d}.mp3"
            filepath = os.path.join(Config.TTS_DIR, filename)
            
            generate_tts_for_text(summary, filepath)
            tts_files.append(filepath)
            print(f"    - 저장: {filename}")
        
        art["tts_files"] = tts_files
    
    print(f"✅ TTS 생성 완료: {len(articles)}개 기사")
    return articles
