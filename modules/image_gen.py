"""
이미지 생성 (OpenAI GPT-Image + Llama 프롬프트 생성)
"""

import os
import json
import base64
import torch
from openai import OpenAI
from transformers import AutoTokenizer, AutoModelForCausalLM
from typing import List, Dict
from config import Config

# Llama 모델 초기화 (싱글톤)
_llama_model = None
_llama_tokenizer = None

def get_llama_model():
    global _llama_model, _llama_tokenizer
    if _llama_model is None:
        from huggingface_hub import login
        
        if Config.HUGGINGFACE_TOKEN:
            try:
                login(Config.HUGGINGFACE_TOKEN)
            except Exception:
                pass
        
        model_id = "meta-llama/Llama-3.1-8B-Instruct"
        print(f"🦙 Llama 모델 로딩 중...")
        
        _llama_tokenizer = AutoTokenizer.from_pretrained(
            model_id, 
            use_fast=True, 
            token=Config.HUGGINGFACE_TOKEN
        )
        
        if _llama_tokenizer.pad_token is None:
            _llama_tokenizer.pad_token = _llama_tokenizer.eos_token
        
        _llama_model = AutoModelForCausalLM.from_pretrained(
            model_id,
            torch_dtype=torch.float16,
            device_map="auto",
            token=Config.HUGGINGFACE_TOKEN
        )
    
    return _llama_model, _llama_tokenizer

def _safe_json_extract(s: str) -> str:
    """JSON 블록 추출"""
    start = s.find("{")
    end = s.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("JSON block not found in model output.")
    return s[start:end+1]

def generate_prompt_and_quiz(news_summaries: List[str]) -> Dict:
    """
    Llama로 이미지 프롬프트 + 퀴즈 생성
    
    Args:
        news_summaries: ["파트 1: ...", "파트 2: ...", ...]
    
    Returns:
        {
            "prompts": str (GPT-Image용 프롬프트),
            "quiz": {...}
        }
    """
    assert len(news_summaries) >= 1, "최소 1개 이상의 요약이 필요합니다"
    
    model, tokenizer = get_llama_model()
    torch.manual_seed(102)
    
    gen_kwargs = dict(
        do_sample=True,
        temperature=0.7,
        top_p=0.9,
        repetition_penalty=1.05,
        max_new_tokens=300,
        pad_token_id=tokenizer.pad_token_id,
        eos_token_id=tokenizer.eos_token_id,
    )
    
    gen_quiz_kwargs = dict(
        do_sample=True,
        temperature=0.7,
        top_p=0.9,
        repetition_penalty=1.05,
        max_new_tokens=350,
        pad_token_id=tokenizer.pad_token_id,
        eos_token_id=tokenizer.eos_token_id,
    )
    
    # ===== 프롬프트 생성 =====
    system_msg_prompt = (
        "You are an expert prompt engineer for image generation models.\n"
        "Write a single concise English prompt optimized for GPT-Image 1.\n"
        "Generate one 1024x1024 cartoon-style illustration arranged as a 2x2 four-panel comic.\n"
        "Panels must be seamlessly connected with absolutely no borders, gutters, or spacing.\n"
        "Style for all panels: clean simple backgrounds, consistent lighting, crisp details, "
        "smooth line art, realistic hand anatomy and face, no watermarks.\n"
        "Each panel must visually depict the meaning of its summary in a concrete, context-aware scene.\n"
        "No Unrealistic Face or hand, Natural FACE\n"
        "No text except for simple very clean logos or keywords such as 'HMMMME', 'KIA', 'AI', HYUNDAI\n"
        "Avoid generic clichés unless explicitly implied.\n"
        "Exclude all forms of written language or typographic marks.\n"
        "Maintain cohesive composition across all four panels.\n\n"
        f"Panel A (top-left): Visualize the essence of Summary 1. No text.\n"
        f"Summary 1:\n{news_summaries[0]}\n\n"
        f"Panel B (top-right): Visualize the essence of Summary 2. No text.\n"
        f"Summary 2:\n{news_summaries[1] if len(news_summaries) > 1 else news_summaries[0]}\n\n"
        f"Panel C (bottom-left): Visualize the essence of Summary 3. No text.\n"
        f"Summary 3:\n{news_summaries[2] if len(news_summaries) > 2 else news_summaries[0]}\n\n"
        f"Panel D (bottom-right): Visualize the essence of Summary 4. No text.\n"
        f"Summary 4:\n{news_summaries[3] if len(news_summaries) > 3 else news_summaries[0]}\n\n"
    )
    
    user_msg_prompt = (
        f"News summaries:\n{news_summaries}\n\n"
        "Write only the final optimized prompt.\n"
        "No extra fingers; realistic hand anatomy and face.\n"
    )
    
    messages = [
        {"role": "system", "content": system_msg_prompt},
        {"role": "user", "content": user_msg_prompt}
    ]
    
    chat = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(chat, return_tensors="pt", padding=True).to(model.device)
    
    with torch.no_grad():
        out = model.generate(**inputs, **gen_kwargs)
    
    new_tokens = out[0, inputs["input_ids"].shape[-1]:]
    prompt_text = tokenizer.decode(new_tokens, skip_special_tokens=True).strip()
    prompt_text = prompt_text.strip().strip('"').strip("'").strip()
    
    print(f"✅ 프롬프트 생성 완료: {prompt_text[:100]}...")
    
    # ===== 퀴즈 생성 =====
    combined_summary = "\n".join([f"{i+1}) {s}" for i, s in enumerate(news_summaries)])
    
    QUIZ_SYSTEM = (
        "You are a precise quiz generator. "
        "Create ONLY multiple-choice questions with exactly four options (A–D). "
        "Return STRICT JSON. No extra commentary."
    )
    
    QUIZ_SCHEMA = {
        "language": "ko",
        "topic": "string",
        "questions": [
            {
                "type": "mcq",
                "question": "string (Korean)",
                "options": ["A","B","C","D"],
                "answer": "A|B|C|D",
                "explanation": "1-2 sentences (Korean)"
            }
        ]
    }
    
    quiz_user = f"""
[Task]
Generate EXACTLY ONE multiple-choice quiz question in Korean that REQUIRES synthesizing 
information across ALL of the following news summaries.

[Summary]
{combined_summary}

[Hard Requirements]
- language: ko
- type: mcq ONLY
- The single question MUST combine information from at least two different summaries
- JSON must contain exactly one item in "questions" array
- Each "options" must contain exactly 4 items (A, B, C, D), single word only
- "answer" must be one of "A","B","C","D"
- Correct option must be placed randomly
- No text outside the JSON

[JSON Schema]
{json.dumps(QUIZ_SCHEMA, ensure_ascii=False, indent=2)}
""".strip()
    
    quiz_messages = [
        {"role": "system", "content": QUIZ_SYSTEM},
        {"role": "user", "content": quiz_user}
    ]
    
    quiz_chat = tokenizer.apply_chat_template(quiz_messages, tokenize=False, add_generation_prompt=True)
    quiz_inputs = tokenizer(quiz_chat, return_tensors="pt").to(model.device)
    
    with torch.no_grad():
        quiz_out = model.generate(**quiz_inputs, **gen_quiz_kwargs)
    
    quiz_new_tokens = quiz_out[0, quiz_inputs["input_ids"].shape[-1]:]
    quiz_text_raw = tokenizer.decode(quiz_new_tokens, skip_special_tokens=True).strip()
    
    try:
        quiz_json = _safe_json_extract(quiz_text_raw)
        quiz_data = json.loads(quiz_json)
    except Exception:
        cleaned = quiz_text_raw.strip().strip("`").strip()
        quiz_data = json.loads(_safe_json_extract(cleaned))
    
    # 퀴즈 후처리
    def _fix_one(q):
        q["type"] = "mcq"
        opts = q.get("options", [])
        if isinstance(opts, dict):
            opts = [opts.get("A",""), opts.get("B",""), opts.get("C",""), opts.get("D","")]
        opts = (list(opts) + [""]*4)[:4]
        q["options"] = [str(x).strip()[:160] for x in opts]
        ans = str(q.get("answer","A")).strip().upper()
        if ans not in ["A","B","C","D"]:
            ans = "A"
        q["answer"] = ans
        exp = q.get("explanation","")
        q["explanation"] = str(exp).strip()[:300]
        return q
    
    LETTERS = ["A", "B", "C", "D"]
    
    def _rebalance_answer(q, idx=None):
        opts = list(q.get("options", []))
        ans = q.get("answer", "A")
        if len(opts) != 4 or ans not in LETTERS:
            return q
        
        if idx is not None:
            desired = LETTERS[idx % 4]
        else:
            h = sum(ord(c) for c in q.get("question", ""))
            desired = LETTERS[h % 4]
        
        if desired == ans:
            return q
        
        i_cur = LETTERS.index(ans)
        i_des = LETTERS.index(desired)
        opts[i_cur], opts[i_des] = opts[i_des], opts[i_cur]
        q["options"] = opts
        q["answer"] = desired
        return q
    
    quiz_data["language"] = "ko"
    quiz_data["questions"] = [_fix_one(q) for q in quiz_data.get("questions", [])][:1]
    quiz_data["questions"] = [_rebalance_answer(q) for q in quiz_data.get("questions", [])][:1]
    
    print(f"✅ 퀴즈 생성 완료")
    
    return {"prompts": prompt_text, "quiz": quiz_data}

def gpt_image_generate(prompt: str, size: str = "1024x1024", quality: str = "standard") -> str:
    """
    OpenAI GPT-Image로 이미지 생성
    
    Args:
        prompt: 이미지 프롬프트
        size: 이미지 크기
        quality: 품질 (standard or hd)
    
    Returns:
        저장된 이미지 파일 경로
    """
    client = OpenAI(api_key=Config.OPENAI_API_KEY)
    
    print(f"🎨 이미지 생성 중... (quality: {quality})")
    
    result = client.images.generate(
        model="gpt-image-1",
        prompt=prompt,
        size=size,
        quality=quality,
    )
    
    image_base64 = result.data[0].b64_json
    image_bytes = base64.b64decode(image_base64)
    
    filename = os.path.join(Config.IMAGES_DIR, "generated_image.png")
    with open(filename, "wb") as f:
        f.write(image_bytes)
    
    print(f"✅ 이미지 저장: {filename}")
    return filename

def generate_images(articles: List[Dict]) -> List[Dict]:
    """
    요약된 기사로부터 이미지 생성
    
    Args:
        articles: summarize_articles() 반환값
    
    Returns:
        이미지 경로가 추가된 기사 리스트
    """
    print(f"\n🎨 이미지 생성 시작...")
    
    for i, art in enumerate(articles, 1):
        summaries = art.get("summaries", [])
        if len(summaries) < 1:
            print(f"  [{i}] SKIP: 요약 없음")
            art["image_path"] = None
            art["quiz"] = None
            continue
        
        print(f"  [{i}] {art.get('title', '')[:40]}...")
        
        # 프롬프트 + 퀴즈 생성
        result = generate_prompt_and_quiz(summaries)
        
        # 이미지 생성
        image_path = gpt_image_generate(
            result["prompts"],
            size=Config.IMAGE_SIZE,
            quality=Config.IMAGE_QUALITY
        )
        
        art["image_path"] = image_path
        art["quiz"] = result["quiz"]
        art["prompt"] = result["prompts"]
    
    print(f"✅ 이미지 생성 완료: {len(articles)}개 기사")
    return articles
