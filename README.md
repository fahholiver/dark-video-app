# Dark Moody Classical — Gerador de Roteiro

App Streamlit que gera pacotes completos de vídeo (título, roteiro de
narração, timeline de cenas e prompt mestre pra IA de vídeo) no estilo
"Dark Moody Classical / Masculine Resilience", a partir de uma ideia e uma
duração alvo.

## Como rodar localmente

```bash
git clone <seu-repo>
cd dark-video-app
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

pip install -r requirements.txt
streamlit run app.py
```

Abre em `http://localhost:8501`.

## Como publicar no Streamlit Community Cloud (grátis, via GitHub)

1. Crie um repositório no GitHub e suba estes arquivos (a estrutura toda,
   incluindo a pasta `.streamlit/`).
2. Em [share.streamlit.io](https://share.streamlit.io), clique em **"New app"**,
   escolha o repositório, a branch e aponte o **Main file path** pra `app.py`.
3. Antes de rodar (ou depois, em qualquer momento), configure sua chave da
   Groq em **Settings → Secrets** do próprio Streamlit Cloud (veja a seção
   abaixo) — assim você não precisa colar a chave na interface toda vez.
4. Clique em **Deploy**. Em ~1-2 minutos o app está no ar com uma URL tipo
   `https://seu-app.streamlit.app`.

## Configurando a chave da Groq

Duas formas:

1. **Colar na interface** (campo de senha dentro de "⚙️ Configuração de IA")
   — mais simples pra testar.
2. **Streamlit Cloud → Settings → Secrets** (recomendado pra não digitar
   toda vez): copie o conteúdo de `.streamlit/secrets.toml.example` e cole
   lá, preenchendo sua chave:
   ```toml
   GROQ_API_KEY = "sua_chave_aqui"
   ```
   Se estiver rodando local, copie esse mesmo conteúdo pra um arquivo real
   `.streamlit/secrets.toml` (já está no `.gitignore`, não sobe pro GitHub).

- **Groq** (grátis, sem cartão): https://console.groq.com/keys — veja
  também a conversa anterior pra passo a passo com prints.
- **Ollama** (alternativa 100% local e gratuita): só funciona se você
  rodar o app na sua própria máquina (não funciona no Streamlit Cloud,
  já que o servidor deles não tem acesso ao seu Ollama local). Instale em
  [ollama.com](https://ollama.com) e rode `ollama pull llama3.1`.

## Estrutura do projeto

```
dark-video-app/
├── app.py                          # app Streamlit (toda a lógica)
├── requirements.txt                # dependências Python
├── .gitignore
└── .streamlit/
    └── secrets.toml.example        # modelo pra configurar sua chave
```

## Sobre o app

- O `SYSTEM_PROMPT` dentro de `app.py` contém TODAS as regras fixas do
  estilo (tom, estrutura do roteiro, specs de áudio/vídeo, formato de
  saída) — isso não muda entre gerações.
- Você digita a ideia + escolhe a duração (30/60/90s ou personalizada); o
  app calcula a faixa de palavras alvo (130–150 palavras por minuto) e
  manda pra IA gerar as 4 seções: título, roteiro, timeline de cenas e o
  prompt mestre pra ferramenta de geração de vídeo.
- Cada geração fica salva num histórico da sessão (expansível), com botão
  pra baixar em `.md`.
