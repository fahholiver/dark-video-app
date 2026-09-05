import os
import re
import json
import streamlit as st
import requests

st.set_page_config(page_title="Dark Moody Classical — Gerador de Roteiro", page_icon="🗿", layout="centered")
st.title("🗿 Gerador de Roteiro — Dark Moody Classical")
st.caption(
    "Manda uma ideia + duração, e a IA gera o pacote completo: título, roteiro "
    "de narração, quebra de cenas com timestamps, e o prompt mestre pra ferramenta "
    "de geração de vídeo."
)

# ---------------------------------------------------------------------------
# System prompt — encapsula TODAS as regras fixas do estilo. Isso nunca muda
# entre gerações, só a ideia/duração do usuário mudam a cada chamada.
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You generate short-form video creation packages in the strict
"Dark Moody Classical / Masculine Resilience" aesthetic (TikTok/Reels style
featuring historical oil paintings, deep philosophy, and dramatic power themes).

## SCRIPT RULES
- Language: English only.
- Tone: solemn, authoritative, dark, philosophical, unyielding.
- Word count MUST match the target duration given to you (you will be told the
  exact target word range in the user message) — count your words and stay
  inside that range.
- Structure, in this order:
  1. Hook: a brutal, thought-provoking statement about power, truth, or human nature.
  2. Core Argument: a philosophical breakdown contrasting strength vs. weakness,
     or reality vs. illusion.
  3. Call to Action / Outro: encourages self-reliance, discipline, and mastery,
     and rejects weak / dependent mindsets. Frame this as personal discipline and
     stoic self-reliance (owning your mind, your standards, your effort) — never
     as literal advice to isolate from other people, cut off relationships, or
     avoid seeking help. Keep the tone unyielding without crossing into advice
     that could read as encouraging real-world isolation.

## FIXED AUDIO SPEC (include verbatim, adapted only in wording if needed)
- Intro SFX: deep cinematic sub-bass boom / heavy low-end impact.
- Voiceover Style: deep, gravelly, slow-paced masculine AI voice with dramatic pauses.
- Background Music: dark cinematic ambient / slow dark phonk with heavy bass and low drones.

## FIXED VISUAL SPEC (include verbatim, adapted only in wording if needed)
- Imagery: classic Renaissance, Baroque, and Neoclassical oil paintings (historical
  figures like Napoleon Bonaparte, Machiavelli, Roman emperors, stoic philosophers,
  or allegories with lions).
- Color grading: dark moody, high contrast (chiaroscuro), desaturated tones, deep
  shadows (#000000 background), subtle warm gold/crimson accents.
- Transitions & effects: slow Ken Burns effect (gentle zoom in/out on static
  artwork), clean cuts on dramatic voice pauses, black screen flashes between scenes.
- Typography: bold white sans-serif font, ALL CAPS, centered, 1-3 words at a time,
  synced to narration.

## OUTPUT FORMAT — always exactly these four sections, in this order, in English,
using this exact markdown structure:

**[VIDEO TITLE]**
<a punchy title>

**[VOICEOVER SCRIPT]**
<the full narration script, word count matching the target range>

**[TIMELINE & VISUAL SCENE BREAKDOWN]**
<scene-by-scene with timestamps (e.g. 0:00-0:04), specific classical artwork/artist
suggestions, camera movement, and the on-screen text for that scene>

**[MASTER AI VIDEO GENERATION PROMPT]**
<one consolidated English paragraph combining art style, lighting, color palette,
motion/camera, typography and mood into a single prompt ready to paste into a
video generation tool>

Respond with ONLY those four sections, nothing before or after."""


def estimate_word_range(seconds: int) -> tuple[int, int]:
    """~130-150 wpm de narração -> converte duração em faixa de palavras alvo."""
    low = round(seconds / 60 * 130)
    high = round(seconds / 60 * 150)
    return max(5, low), max(8, high)


def build_user_message(idea: str, seconds: int) -> str:
    low, high = estimate_word_range(seconds)
    return (
        f'Idea: "{idea}"\n'
        f"Target duration: {seconds} seconds\n"
        f"Target voiceover word count: between {low} and {high} words "
        f"(130-150 wpm pacing). Count your words before answering and make sure "
        f"the voiceover script lands inside that range."
    )


def call_groq(system_prompt: str, user_message: str, api_key: str,
              model: str = "openai/gpt-oss-120b") -> str:
    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        },
        timeout=60,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Groq API respondeu {resp.status_code}: {resp.text[:400]}")
    return resp.json()["choices"][0]["message"]["content"]


def call_ollama(system_prompt: str, user_message: str, model: str = "llama3.1") -> str:
    resp = requests.post(
        "http://localhost:11434/api/generate",
        json={"model": model, "prompt": f"{system_prompt}\n\n{user_message}", "stream": False},
        timeout=180,
    )
    resp.raise_for_status()
    return resp.json()["response"]


def is_ollama_available() -> bool:
    try:
        requests.get("http://localhost:11434", timeout=1.5)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Configuração de IA
# ---------------------------------------------------------------------------
with st.expander("⚙️ Configuração de IA", expanded=not st.session_state.get("configured", False)):
    groq_api_key_input = st.text_input(
        "Chave da API Groq (grátis)", type="password",
        help="Crie de graça em https://console.groq.com/keys",
    )
    try:
        groq_api_key = groq_api_key_input or st.secrets.get("GROQ_API_KEY", "")
    except Exception:
        groq_api_key = groq_api_key_input

    ollama_ok = is_ollama_available()
    ollama_model = st.text_input("Modelo do Ollama (usado só se não houver chave da Groq)", "llama3.1")

    if groq_api_key:
        st.success("✅ Groq configurado.")
        st.session_state.configured = True
    elif ollama_ok:
        st.success("✅ Ollama detectado rodando localmente.")
        st.session_state.configured = True
    else:
        st.warning("⚠️ Configure a Groq (ou tenha o Ollama rodando local) pra gerar os roteiros.")

st.divider()

# ---------------------------------------------------------------------------
# Inputs do vídeo
# ---------------------------------------------------------------------------
st.subheader("1. Ideia e duração")
idea = st.text_input("Ideia / tema do vídeo", "Why discipline beats motivation")

duration_choice = st.radio("Duração", ["30 segundos", "60 segundos", "90 segundos", "Personalizada"], horizontal=True)
if duration_choice == "Personalizada":
    duration_seconds = st.number_input("Duração em segundos", min_value=10, max_value=300, value=45, step=5)
else:
    duration_seconds = int(duration_choice.split()[0])

low, high = estimate_word_range(duration_seconds)
st.caption(f"Faixa de palavras alvo pra narração: **{low}–{high} palavras** (~130–150 wpm).")

if "history" not in st.session_state:
    st.session_state.history = []

if st.button("🎬 Gerar pacote de vídeo", type="primary"):
    if not idea.strip():
        st.error("Escreve uma ideia primeiro.")
    else:
        user_message = build_user_message(idea, duration_seconds)
        with st.spinner("Gerando roteiro e prompts..."):
            try:
                if groq_api_key:
                    output = call_groq(SYSTEM_PROMPT, user_message, groq_api_key)
                elif ollama_ok:
                    output = call_ollama(SYSTEM_PROMPT, user_message, ollama_model)
                else:
                    st.error("Configure a Groq ou o Ollama primeiro (seção acima).")
                    output = None
            except Exception as e:
                st.error(f"Deu erro chamando a IA: {e}")
                output = None

        if output:
            st.session_state.history.insert(0, {"idea": idea, "duration": duration_seconds, "output": output})

# ---------------------------------------------------------------------------
# Resultado(s)
# ---------------------------------------------------------------------------
if st.session_state.history:
    st.divider()
    st.subheader("2. Resultado")
    for i, item in enumerate(st.session_state.history):
        label = f"{item['idea']} — {item['duration']}s"
        with st.expander(label, expanded=(i == 0)):
            st.markdown(item["output"])
            st.download_button(
                "⬇️ Baixar como .md", item["output"],
                file_name=f"video_{re.sub(r'[^a-zA-Z0-9]+', '_', item['idea'])[:40]}.md",
                key=f"dl_{i}",
            )
