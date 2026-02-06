import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

class Config:
    """전역 설정 관리"""
    
    # API Keys
    KINDS_ACCESS_KEY = os.getenv("KINDS_ACCESS_KEY", "")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
    HUGGINGFACE_TOKEN = os.getenv("HUGGINGFACE_TOKEN", "")
    
    # 뉴스 수집 설정
    ISSUE_PROVIDERS_FILTER = [
        "MBC", "KBS", "SBS", "국민일보",
        "조선일보", "중앙일보", "동아일보",
        "한겨레", "경향신문",
    ]
    
    # 크롤링 설정
    MIN_REASONABLE_LEN = 800
    MIN_KINDS_LEN_TO_SAVE_IF_NO_FALLBACK = 500
    
    # 요약 설정
    SUMMARY_PARTS = 4
    SUMMARY_MODEL = "lcw99/t5-base-korean-text-summary"
    
    # 이미지 생성 설정
    IMAGE_SIZE = "1024x1024"
    IMAGE_QUALITY = "standard"  # standard or hd
    
    # TTS 설정
    TTS_VOICE_NAME = "ko-KR-Chirp3-HD-Zephyr"
    TTS_LANGUAGE_CODE = "ko-KR"
    TTS_SPEAKING_RATE = 1.0
    TTS_PITCH = 0.0
    
    # 영상 설정
    VIDEO_WIDTH = 720
    VIDEO_HEIGHT = 1280
    VIDEO_FPS = 24
    FONT_PATH = r"C:\Windows\Fonts\NanumSquareR.ttf"
    FONT_TOP_PATH = r"C:\Windows\Fonts\H2HDRM.ttf"
    
    # 디렉토리
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")
    ARTICLES_DIR = os.path.join(OUTPUT_DIR, "articles")
    IMAGES_DIR = os.path.join(OUTPUT_DIR, "images")
    TTS_DIR = os.path.join(OUTPUT_DIR, "tts")
    VIDEOS_DIR = os.path.join(OUTPUT_DIR, "videos")
    
    @classmethod
    def create_directories(cls):
        """필요한 디렉토리 생성"""
        for dir_path in [cls.OUTPUT_DIR, cls.ARTICLES_DIR, 
                         cls.IMAGES_DIR, cls.TTS_DIR, cls.VIDEOS_DIR]:
            os.makedirs(dir_path, exist_ok=True)
    
    @classmethod
    def validate(cls):
        """필수 설정 검증"""
        errors = []
        
        if not cls.KINDS_ACCESS_KEY:
            errors.append("KINDS_ACCESS_KEY가 설정되지 않았습니다.")
        if not cls.OPENAI_API_KEY:
            errors.append("OPENAI_API_KEY가 설정되지 않았습니다.")
        if not cls.GOOGLE_APPLICATION_CREDENTIALS:
            errors.append("GOOGLE_APPLICATION_CREDENTIALS가 설정되지 않았습니다.")
            
        if errors:
            raise ValueError("설정 오류:\n" + "\n".join(f"- {e}" for e in errors))
        
        return True
