# ShortKinds - 뉴스 숏츠 end-to-end 생성 시스템
BigKinds API로부터 뉴스를 수집하고, 크롤링, 요약, 이미지 생성, TTS, 영상 제작까지 End-to-End로 자동화

## 📁 프로젝트 구조

```
shortkinds/
├── .env          # API 키 설정 
├── config.py          # 설정 관리
├── main.py               # 메인 실행 파일
├── requirements.txt     # 패키지 
├── README.md             
│
├── modules/              
│   ├── __init__.py
│   ├── news_collector.py     # 1. 뉴스 이슈 수집
│   ├── crawler.py         # 2. 기사 크롤링
│   ├── summarizer.py     # 3. 기사 요약
│   ├── image_gen.py      # 4. 이미지 생성
│   ├── tts_gen.py        # 5. TTS 생성 
│   └── video_gen.py      # 6. 영상 생성 
│
└── outputs/              # 결과물 저장 
    ├── articles/         # 수집된 기사 텍스트
    ├── images/           # 생성된 이미지
    ├── tts/              # TTS 음성 파일
    └── videos/           # 최종 영상 파일
```

## 🚀 Start

### 1. 환경 설정

```bash
# 패키지 설치
pip install -r requirements.txt

# .env 파일 생성
cp ..env .env
```

### 2. API 키 설정

`.env` 파일을 열어 각 API 키를 입력:

```env
# BigKinds API
KINDS_ACCESS_KEY=your_kinds_api_key_here

# OpenAI API
OPENAI_API_KEY=your_openai_api_key_here

# Google Cloud TTS
GOOGLE_APPLICATION_CREDENTIALS=path/to/service-account-key.json

# Hugging Face 
HUGGINGFACE_TOKEN=your_huggingface_token_here
```

### 3. 실행

```bash
# 기본 실행 (예시: 오늘 날짜, 5개 토픽, 토픽당 1개 기사)
python main.py

# 옵션 지정
python main.py --date 2025-02-06 --max-topics 10 --per-topic-docs 2

# 상단 자막 추가
python main.py --top-text "오늘의 뉴스"

# 특정 단계로 스킵
python main.py --skip-to video
```
