"""
MoviePy를 이용한 숏츠 영상 생성
"""

import os
import re
import textwrap
import numpy as np
from moviepy.editor import *
from PIL import Image, ImageDraw, ImageFont
from typing import List, Dict, Optional
from config import Config

def contain_resize_size(w, h, box_w, box_h):
    """비율 유지하며 박스 안에 맞추기"""
    s = min(box_w / w, box_h / h)
    return int(w * s), int(h * s)

def split_image_2x2(image_path: str) -> List[np.ndarray]:
    """
    이미지를 2x2 (4컷)로 분할
    
    Returns:
        [좌상, 우상, 좌하, 우하] numpy 배열
    """
    im = Image.open(image_path).convert("RGB")
    W, H = im.size
    w = W // 2
    h = H // 2
    
    tl = im.crop((0, 0, w, h))
    tr = im.crop((w, 0, W, h))
    bl = im.crop((0, h, w, H))
    br = im.crop((w, h, W, H))
    
    return [np.array(tl), np.array(tr), np.array(bl), np.array(br)]

def render_caption_exact(
    text: str, box_w: int, box_h: int, font_path: str, fs: int,
    PAD_X: int = 16, PAD_Y: int = 12,
    STROKE_RATIO: float = 0.06, BG_ALPHA: int = 0,
    align: str = "left", ellipsis: bool = True,
    margin_px: int = 0, return_meta: bool = False,
):
    """자막 렌더링 (실측 줄바꿈)"""
    box_w = max(40, int(box_w))
    box_h = max(40, int(box_h))
    inner_w = max(10, box_w - 2*PAD_X) - margin_px
    inner_h = max(10, box_h - 2*PAD_Y)

    font = ImageFont.truetype(font_path, fs)
    stroke = max(1, int(fs * STROKE_RATIO))
    line_gap = int(fs * 0.30)

    _dummy = Image.new("RGBA", (10, 10))
    _draw = ImageDraw.Draw(_dummy)
    
    def width_px(s: str) -> int:
        b = _draw.textbbox((0,0), s if s else " ", font=font, stroke_width=stroke)
        return b[2] - b[0]

    CJK = r"[\u4E00-\u9FFF\u3040-\u30FF\uAC00-\uD7AF]"
    token_re = re.compile(rf"(\s+|[A-Za-z0-9_.,;:/\\\-+*=?@#%^&(){{}}<>\[\]'\"`~]+|{CJK})")

    lines, cur, cur_w = [], "", 0
    for para in (text or "").replace("\r","").split("\n"):
        para = para.rstrip("\n")
        if para == "":
            lines.append(cur)
            cur, cur_w = "", 0
            lines.append("")
            continue
        
        for tok in token_re.findall(para):
            if width_px(tok) > inner_w:
                if cur:
                    lines.append(cur)
                    cur, cur_w = "", 0
                for ch in tok:
                    wch = width_px(ch)
                    if cur == "":
                        if wch <= inner_w:
                            cur, cur_w = ch, wch
                        else:
                            lines.append(ch)
                            cur, cur_w = "", 0
                    else:
                        if cur_w + wch <= inner_w:
                            cur += ch
                            cur_w += wch
                        else:
                            lines.append(cur)
                            cur, cur_w = ch, wch
                continue
            
            if cur == "":
                cur, cur_w = tok, width_px(tok)
            else:
                cand = cur + tok
                if width_px(cand) <= inner_w:
                    cur, cur_w = cand, width_px(cand)
                else:
                    lines.append(cur)
                    cur, cur_w = tok, width_px(tok)
    
    if cur != "" or (not lines):
        lines.append(cur)

    fitted, h, overflowed = [], 0, False
    for ln in lines:
        bb = _draw.textbbox((0,0), ln if ln else " ", font=font, stroke_width=stroke)
        line_height = bb[3] - bb[1]
        next_h = h + line_height + (line_gap if fitted else 0)
        if next_h <= inner_h:
            fitted.append(ln)
            h = next_h
        else:
            overflowed = True
            if ellipsis and fitted:
                last = fitted[-1]
                ell = "…"
                def fits(txt):
                    b = _draw.textbbox((0,0), txt if txt else " ", font=font, stroke_width=stroke)
                    return (b[2]-b[0]) <= inner_w
                cand = last
                while cand and not fits(cand + ell):
                    cand = cand[:-1]
                fitted[-1] = (cand + ell) if cand else ell
            break

    tot_h, line_sizes = 0, []
    for ln in (fitted or [" "]):
        b = _draw.textbbox((0,0), ln if ln else " ", font=font, stroke_width=stroke)
        lw, lh = b[2]-b[0], b[3]-b[1]
        line_sizes.append((lw, lh))
        tot_h += lh + line_gap
    if fitted:
        tot_h -= line_gap

    cap_w = box_w
    cap_h = min(box_h, max(1, tot_h + 2*PAD_Y))
    img = Image.new("RGBA", (cap_w, cap_h), (0,0,0,0))
    
    if BG_ALPHA > 0:
        img.alpha_composite(Image.new("RGBA", (cap_w, cap_h), (0,0,0,BG_ALPHA)), (0,0))
    
    draw = ImageDraw.Draw(img)

    y = PAD_Y
    for (ln, (lw, lh)) in zip(fitted or [" "], line_sizes):
        x = max(PAD_X, (cap_w - lw)//2) if align=="center" else PAD_X
        draw.text((x, y), ln if ln else " ", font=font,
                  fill=(255,255,255,255), stroke_width=stroke, stroke_fill=(0,0,0,255))
        y += lh + line_gap

    if return_meta:
        return np.array(img), {"overflow": overflowed, "cap_w": cap_w, "cap_h": cap_h}
    return np.array(img)

def render_caption_autofit(text, box_w, box_h, font_path, fs_start, fs_min=28, **kwargs):
    """폰트 사이즈를 줄여가며 자동 맞춤"""
    ABS_MIN = 18
    cur_min = min(fs_min, ABS_MIN)
    fs = fs_start
    
    while fs >= cur_min:
        img_np, meta = render_caption_exact(
            text, box_w, box_h, font_path, fs=fs,
            ellipsis=False, return_meta=True, **kwargs
        )
        if not meta["overflow"]:
            meta["used_fs"] = fs
            return img_np, meta
        fs -= 2
    
    img_np, meta = render_caption_exact(
        text, box_w, box_h, font_path, fs=cur_min,
        ellipsis=False, return_meta=True, **kwargs
    )
    meta["used_fs"] = cur_min
    return img_np, meta

def generate_video_from_parts(
    image_tiles: List[np.ndarray],
    text_parts: List[str],
    audio_paths: List[str],
    output_path: str,
    top_text: Optional[str] = None,
    width: int = 720,
    height: int = 1280,
    fps: int = 24
):
    """
    4개 파트로 영상 생성
    
    Args:
        image_tiles: [TL, TR, BL, BR] numpy arrays
        text_parts: ["파트 1: ...", "파트 2: ...", ...]
        audio_paths: [path1.mp3, path2.mp3, ...]
        output_path: 저장할 영상 경로
        top_text: 공통 상단 자막
    """
    W, H = width, height
    FPS = fps
    
    # 설정
    FIXED_FS = 32
    FIXED_FS_TOP = 68
    PAD_X, PAD_Y = 16, 12
    BG_ALPHA = 0
    STROKE_RATIO = 0.06
    
    TOP_Y = 55
    BOTTOM_Y = 45
    CAP_W_RATIO = 0.94
    TOP_H_RATIO = 0.22
    BOT_H_RATIO = 0.30
    
    CAP_W = int(W * CAP_W_RATIO)
    TOP_H = int(H * TOP_H_RATIO)
    BOT_H = int(H * BOT_H_RATIO)
    
    # 파트별 처리
    shots = []
    for img_tile, text_part, audio_path in zip(image_tiles, text_parts, audio_paths):
        audio = AudioFileClip(audio_path)
        dur = audio.duration
        
        # 하단 자막
        bot_np, bot_meta = render_caption_autofit(
            text_part, CAP_W, BOT_H, Config.FONT_PATH,
            fs_start=FIXED_FS, fs_min=30,
            align="left", PAD_X=PAD_X, PAD_Y=PAD_Y,
            STROKE_RATIO=STROKE_RATIO, BG_ALPHA=BG_ALPHA
        )
        bot_clip = ImageClip(bot_np).set_duration(dur)
        bot_h_used = int(bot_meta["cap_h"])
        
        # 상단 자막
        top_clip = None
        top_h_used = 0
        if top_text:
            top_np, top_meta = render_caption_autofit(
                top_text, CAP_W, TOP_H, Config.FONT_TOP_PATH,
                fs_start=FIXED_FS_TOP, fs_min=40,
                align="center", PAD_X=PAD_X, PAD_Y=PAD_Y,
                STROKE_RATIO=STROKE_RATIO, BG_ALPHA=BG_ALPHA
            )
            top_clip = ImageClip(top_np).set_duration(dur)
            top_h_used = int(top_meta["cap_h"])
        
        # 이미지 배치 공간
        free_top_y = TOP_Y + top_h_used
        free_bot_y = H - (bot_h_used + BOTTOM_Y)
        free_h = max(50, free_bot_y - free_top_y)
        
        base = ColorClip(size=(W, H), color=(0, 0, 0)).set_duration(dur)
        
        # 이미지 리사이즈 & 배치
        raw = ImageClip(img_tile)
        new_w, new_h = contain_resize_size(raw.w, raw.h, W, free_h)
        img_y = int(free_top_y + (free_h - new_h) // 2)
        img = raw.resize(newsize=(new_w, new_h)).set_duration(dur)
        
        layers = [base, img.set_position(("center", img_y))]
        
        if top_clip is not None:
            layers.append(top_clip.set_position(((W - top_clip.w)//2, int(TOP_Y))))
        
        bottom_y = H - bot_clip.h - BOTTOM_Y
        layers.append(bot_clip.set_position(((W - bot_clip.w)//2, int(bottom_y))))
        
        shot = CompositeVideoClip(layers, size=(W, H)).set_duration(dur).set_audio(audio)
        shots.append(shot)
    
    # 최종 병합
    final = concatenate_videoclips(shots, method="compose")
    final.write_videofile(
        output_path,
        fps=FPS, codec="libx264",
        audio=True, audio_codec="aac",
        ffmpeg_params=["-pix_fmt", "yuv420p", "-movflags", "faststart", "-g", str(FPS)],
    )
    
    print(f"✅ 영상 저장: {output_path}")

def generate_video(articles: List[Dict], top_text: Optional[str] = None) -> List[Dict]:
    """
    기사별로 영상 생성
    
    Args:
        articles: generate_tts() 반환값
        top_text: 공통 상단 자막 (옵션)
    
    Returns:
        영상 경로가 추가된 기사 리스트
    """
    print(f"\n🎬 영상 생성 시작...")
    
    for art_idx, art in enumerate(articles, 1):
        image_path = art.get("image_path")
        summaries = art.get("summaries", [])
        tts_files = art.get("tts_files", [])
        
        if not image_path or not summaries or not tts_files:
            print(f"  [{art_idx}] SKIP: 필수 데이터 없음")
            art["video_path"] = None
            continue
        
        if len(summaries) != len(tts_files):
            print(f"  [{art_idx}] SKIP: 요약과 TTS 개수 불일치")
            art["video_path"] = None
            continue
        
        print(f"  [{art_idx}] {art.get('title', '')[:40]}...")
        
        # 이미지 분할
        tiles = split_image_2x2(image_path)
        
        # 영상 생성
        output_path = os.path.join(
            Config.VIDEOS_DIR,
            f"video_{art_idx:03d}_{art.get('news_id', 'unknown')}.mp4"
        )
        
        generate_video_from_parts(
            image_tiles=tiles,
            text_parts=summaries,
            audio_paths=tts_files,
            output_path=output_path,
            top_text=top_text,
            width=Config.VIDEO_WIDTH,
            height=Config.VIDEO_HEIGHT,
            fps=Config.VIDEO_FPS
        )
        
        art["video_path"] = output_path
    
    print(f"✅ 영상 생성 완료: {len(articles)}개 기사")
    return articles
