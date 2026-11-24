# bolinha

Um assistente de voz que parece parte do sistema. Você aperta um atalho, uma bolinha aparece no meio da tela e ouve o que você fala. A resposta vem do [Claude Code](https://claude.com/claude-code): a bolinha estica, vira um cartão e o texto aparece palavra por palavra.

- **Reage à sua voz:** a bolinha cresce enquanto você fala e solta um anel fino a cada pico.
- **Conversa de verdade:** com o cartão aberto, é só voltar a falar. Ela ouve de novo e lembra do que vocês estavam falando.
- **Fala quando você pede:** "lê pra mim", "responde em voz alta"… Aí a resposta sai falada: na voz da Dii (Piper, instantânea) ou, com as vozes neurais, na da Francisca ou do Antonio (XTTS ou Chatterbox, bem mais naturais).
- **Age no PC:** "abre a Steam", "quanto espaço livre eu tenho?". O Claude roda no modo automático do Claude Code, que bloqueia comandos destrutivos.
- **Perfis visuais:** 8 prontos (Minimal, Grafite, Anel, Orbe, Neon, Papel, Pontos, Halo), e você cria os seus. Cada um combina um jeito de bolinha, um cartão e uma animação.

Feito pra Linux com Hyprland, mas roda em qualquer desktop Wayland/X11 com PipeWire.

## Requisitos

- Linux com **PipeWire** (`pw-record` e `pw-play`)
- **Claude Code** instalado e logado (`claude auth login`)
- **Python 3** com PyQt6 (o instalador instala se faltar)
- Opcional: GPU NVIDIA, pra transcrever em ~0,3s em vez de ~1s

## Instalar

```bash
git clone https://github.com/remynzo/bolinha.git
cd bolinha
./install.sh
```

O instalador:

- cria um ambiente Python em `~/.local/share/bolinha`;
- baixa a voz (60 MB) e, se tiver NVIDIA, as bibliotecas CUDA (~2 GB);
- coloca **Bolinha** e **Bolinha — Ajustes** no menu de apps (rofi, wofi, fuzzel…).

Pra vozes mais naturais (precisa de placa NVIDIA, Python 3.11 e ffmpeg):

```bash
./install.sh --vozes-neurais
```

Ele pergunta se você aceita a licença do XTTS (só uso não comercial) e se quer também o Chatterbox. O motor escolhido fica carregado na placa de vídeo entre uma pergunta e outra e se desliga sozinho quando fica parado.

Por último, ele mostra as linhas pra colar no Hyprland, pro atalho (Super + C) e pra janela flutuar sem borda.

## Usar

| | |
|---|---|
| Super + C | abre a bolinha (de novo: fecha) |
| falar | ela para de ouvir sozinha quando você faz uma pausa |
| clicar na bolinha | "terminei de falar" |
| clicar no cartão / Esc | fecha |
| falar com o cartão aberto | pergunta seguinte, com contexto |

## Ajustes

Abra **Bolinha — Ajustes** pelo menu. Tem uma prévia ao vivo no topo e tudo se salva sozinho em `~/.config/bolinha/config.json`.

- **Perfis:** galeria com os perfis prontos e os seus. Dá pra duplicar, renomear, excluir ou restaurar o original.
- **Bolinha:** disco, anel, orbe, gota, barras, pontos ou halo; cor, cor de destaque e tamanho.
- **Cartão:** sólido, vidro, contorno neon, balão ou só o texto; cores, cantos, largura, fonte e tamanho do texto.
- **Animação:** como ela aparece (pop, aparecer, cair, zoom), como vira cartão (mola, suave, elástica, direta), como o texto surge (palavra por palavra, máquina de escrever, linha por linha, tudo de uma vez) e a velocidade.
- **Claude:** modelo (Haiku, Sonnet ou Opus), se ele pode agir no PC, se segue ouvindo com o cartão aberto e instruções extras.
- **Voz:** nunca, só quando você pedir ou sempre; motor (Piper, XTTS ou Chatterbox), voz (Francisca ou Antonio), quanto tempo a voz neural fica carregada e a velocidade da fala.
- **Microfone:** modelo de transcrição, GPU ou CPU, limiar de fala (com medidor ao vivo), pausa que encerra a gravação e tempo máximo.

O botão **Abrir de verdade** mostra a bolinha real com o perfil atual.

Pra testar o visual pelo terminal, sem microfone e sem Claude:

```bash
~/.local/share/bolinha/venv/bin/python bolinha.py --demo       # só texto
~/.local/share/bolinha/venv/bin/python bolinha.py --demo-voz   # com voz
```

## Privacidade

- O áudio é transcrito **no seu computador** (faster-whisper) e nunca sai dele.
- A voz também é gerada localmente (Piper, XTTS ou Chatterbox). As vozes de referência da Francisca e do Antonio são geradas uma vez na instalação com as vozes neurais da Microsoft (edge-tts); depois disso nada sai do PC.
- Só o **texto** da pergunta vai pro Claude, pela sua conta do Claude Code.

## Créditos e licenças

- Código: [PolyForm Noncommercial 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0) (veja `LICENSE`). Pode usar, estudar, modificar e compartilhar à vontade, mas **não pode vender nem usar comercialmente**.
- Fontes [Instrument Sans](https://github.com/Instrument/instrument-sans) e [Instrument Serif](https://github.com/Instrument/instrument-serif): SIL Open Font License (`fontes/OFL-*.txt`).
- Voz [Dii pt-BR](https://huggingface.co/Phoonnx/pipertts_pt-BR_dii), do OpenVoiceOS: CC BY-NC-ND 4.0, só pra uso não comercial. É baixada pelo instalador, não vem no repositório.
- Transcrição: [faster-whisper](https://github.com/SYSTRAN/faster-whisper). Voz: [Piper](https://github.com/OHF-Voice/piper1-gpl), [XTTS-v2](https://github.com/idiap/coqui-ai-TTS) (Coqui Public Model License, não comercial) e [Chatterbox](https://github.com/resemble-ai/chatterbox) (MIT).
