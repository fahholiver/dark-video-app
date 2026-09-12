"""
video_builder.py — busca quadros clássicos (Met Museum, domínio público),
gera narração via edge-tts com timestamps por palavra, e monta um vídeo
vertical (Ken Burns + flashes pretos + legendas sincronizadas) no estilo
Dark Moody Classical.

Tudo aqui é gratuito e não precisa de chave de API:
- Imagens: The Met Museum Open Access API (obras em domínio público).
- Narração: edge-tts (vozes neurais da Microsoft, grátis).
"""

from __future__ import annotations

import io
import os
import random
import asyncio
import tempfile

import requests
import numpy as np
from PIL import Image, ImageDraw, ImageFont

import edge_tts

from moviepy.editor import (
    ImageClip,
    AudioFileClip,
    CompositeVideoClip,
    ColorClip,
    concatenate_videoclips,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
CANVAS_W, CANVAS_H = 1080, 1920

MET_SEARCH_URL = "https://collectionapi.metmuseum.org/public/collection/v1/search"
MET_OBJECT_URL = "https://collectionapi.metmuseum.org/public/collection/v1/objects/{}"

# Queries de busca — as mesmas linhas de pesquisa que você mandou, mais
# algumas variações pra garantir volume de imagens.
DEFAULT_QUERIES = [
    "15th century male portrait oil painting",
    "Italian Renaissance portrait black robe red sleeves",
    "chiaroscuro portrait oil on panel",
    "Perugino portrait male",
    "Antonello da Messina portrait",
    "Northern Renaissance male portrait",
    "Roman emperor portrait painting",
    "Machiavelli portrait painting",
    "Napoleon Bonaparte portrait painting",
    "stoic philosopher oil painting",
    "Renaissance nobleman dark background portrait",
]

VOICE_OPTIONS = {
    "Guy (US, grave)": "en-US-GuyNeural",
    "Christopher (US, autoritário)": "en-US-ChristopherNeural",
    "Ryan (UK, dramático)": "en-GB-RyanNeural",
    "William (AU, grave)": "en-AU-WilliamNeural",
}

FONT_PATH = os.path.join(os.path.dirname(__file__), "fonts", "Anton-Regular.ttf")


# ---------------------------------------------------------------------------
# 1. Buscar imagens (Met Museum Open Access)
# ---------------------------------------------------------------------------
def _search_object_ids(query: str, limit: int = 15) -> list:
    try:
        r = requests.get(
            MET_SEARCH_URL,
            params={"q": query, "hasImages": "true"},
            timeout=15,
        )
        r.raise_for_status()
        ids = r.json().get("objectIDs") or []
        return ids[:limit]
    except Exception:
        return []


def _fetch_object(object_id) -> dict | None:
    try:
        r = requests.get(MET_OBJECT_URL.format(object_id), timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def fetch_classical_images(num_images: int, extra_queries: list | None = None) -> list:
    """Retorna uma lista de URLs de imagens (domínio público) na estética
    dark/classical. Embaralha as queries e faz dedup por objectID pra não
    repetir o mesmo quadro dentro do vídeo."""
    queries = list(DEFAULT_QUERIES)
    if extra_queries:
        queries = list(extra_queries) + queries
    random.shuffle(queries)

    seen_ids = set()
    image_urls: list = []

    for query in queries:
        if len(image_urls) >= num_images:
            break
        for oid in _search_object_ids(query):
            if len(image_urls) >= num_images:
                break
            if oid in seen_ids:
                continue
            seen_ids.add(oid)
            obj = _fetch_object(oid)
            if not obj:
                continue
            img_url = obj.get("primaryImage") or obj.get("primaryImageSmall")
            if img_url:
                image_urls.append(img_url)

    return image_urls


def _download_image(url: str) -> Image.Image | None:
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        return Image.open(io.BytesIO(r.content)).convert("RGB")
    except Exception:
        return None


def _cover_resize(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """Redimensiona + crop central pra preencher o canvas (estilo 'cover')."""
    src_ratio = img.width / img.height
    target_ratio = target_w / target_h
    if src_ratio > target_ratio:
        new_h = target_h
        new_w = int(new_h * src_ratio)
    else:
        new_w = target_w
        new_h = int(new_w / src_ratio)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    return img.crop((left, top, left + target_w, top + target_h))


# ---------------------------------------------------------------------------
# 2. Narração (edge-tts, grátis) com timestamps por palavra
# ---------------------------------------------------------------------------
async def _synthesize_async(text: str, voice: str, rate: str, out_path: str) -> list:
    communicate = edge_tts.Communicate(text, voice=voice, rate=rate)
    word_boundaries = []
    with open(out_path, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                word_boundaries.append(
                    {
                        "text": chunk["text"],
                        "start": chunk["offset"] / 1e7,
                        "end": (chunk["offset"] + chunk["duration"]) / 1e7,
                    }
                )
    return word_boundaries


def synthesize_voiceover(text: str, voice: str = "en-US-GuyNeural", rate: str = "-10%"):
    """Gera o áudio da narração + timestamps por palavra.
    Retorna (caminho_mp3, word_boundaries)."""
    out_path = tempfile.mktemp(suffix=".mp3")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        word_boundaries = loop.run_until_complete(
            _synthesize_async(text, voice, rate, out_path)
        )
    finally:
        loop.close()
    return out_path, word_boundaries


def group_captions(word_boundaries: list, words_per_caption: int = 2) -> list:
    """Agrupa palavras em legendas de 1-3 palavras, ALL CAPS, com start/end
    reais vindos do áudio (sincronização de verdade, não estimada)."""
    captions = []
    for i in range(0, len(word_boundaries), words_per_caption):
        group = word_boundaries[i : i + words_per_caption]
        if not group:
            continue
        text = " ".join(w["text"] for w in group).upper()
        captions.append(
            {"text": text, "start": group[0]["start"], "end": group[-1]["end"]}
        )
    return captions


# ---------------------------------------------------------------------------
# 3. Legendas como imagens PNG (evita depender do ImageMagick)
# ---------------------------------------------------------------------------
def _load_font(size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except Exception:
        return ImageFont.load_default()


def _make_caption_image(text: str, size=(CANVAS_W, 300), font_size: int = 90) -> np.ndarray:
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = _load_font(font_size)

    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (size[0] - tw) / 2 - bbox[0]
    y = (size[1] - th) / 2 - bbox[1]

    # contorno preto grosso pra legibilidade sobre qualquer fundo
    outline = 4
    for dx in range(-outline, outline + 1):
        for dy in range(-outline, outline + 1):
            if dx or dy:
                draw.text((x + dx, y + dy), text, font=font, fill=(0, 0, 0, 255))
    draw.text((x, y), text, font=font, fill=(255, 255, 255, 255))
    return np.array(img)


# ---------------------------------------------------------------------------
# 4. Montagem do vídeo (Ken Burns + flashes pretos + legendas + narração)
# ---------------------------------------------------------------------------
def _ken_burns_clip(pil_img: Image.Image, duration: float, zoom_end: float = 1.15):
    frame = np.array(pil_img)
    clip = ImageClip(frame).set_duration(duration)

    def zoom(t):
        return 1 + (zoom_end - 1) * (t / duration)

    zoomed = clip.resize(zoom).set_position("center")
    return CompositeVideoClip([zoomed], size=(CANVAS_W, CANVAS_H)).set_duration(duration)


def build_video(
    image_urls: list,
    audio_path: str,
    captions: list,
    seconds_per_image: float = 2.5,
    out_path: str = "output.mp4",
    progress_callback=None,
) -> str:
    audio_clip = AudioFileClip(audio_path)
    total_duration = audio_clip.duration

    pil_images = []
    for i, url in enumerate(image_urls):
        img = _download_image(url)
        if img:
            pil_images.append(_cover_resize(img, CANVAS_W, CANVAS_H))
        if progress_callback:
            progress_callback(0.1 + 0.3 * (i + 1) / max(len(image_urls), 1))

    if not pil_images:
        raise RuntimeError(
            "Não consegui baixar nenhuma imagem do Met Museum. Tenta gerar de novo."
        )

    num_slots = max(1, round(total_duration / seconds_per_image))
    slots = [pil_images[i % len(pil_images)] for i in range(num_slots)]
    flash_dur = 0.12
    slot_dur = max(
        0.5, (total_duration - flash_dur * (num_slots - 1)) / num_slots
    )

    clips = []
    for i, img in enumerate(slots):
        clips.append(_ken_burns_clip(img, slot_dur))
        if i < num_slots - 1:
            clips.append(
                ColorClip((CANVAS_W, CANVAS_H), color=(0, 0, 0)).set_duration(flash_dur)
            )

    video = concatenate_videoclips(clips, method="compose")
    video = video.set_duration(min(video.duration, total_duration))

    caption_clips = []
    for cap in captions:
        cap_img = _make_caption_image(cap["text"])
        cc = (
            ImageClip(cap_img)
            .set_start(cap["start"])
            .set_duration(max(cap["end"] - cap["start"], 0.25))
            .set_position(("center", "center"))
        )
        caption_clips.append(cc)

    final = CompositeVideoClip([video, *caption_clips], size=(CANVAS_W, CANVAS_H))
    final = final.set_duration(total_duration).set_audio(audio_clip)

    if progress_callback:
        progress_callback(0.6)

    final.write_videofile(
        out_path,
        fps=30,
        codec="libx264",
        audio_codec="aac",
        threads=4,
        preset="medium",
        logger=None,
    )

    if progress_callback:
        progress_callback(1.0)

    return out_path
