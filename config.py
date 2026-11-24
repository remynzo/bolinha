"""Configuração da bolinha: um JSON em ~/.config/bolinha/config.json, com padrões aqui."""
import json
import os

PASTA_CONFIG = os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")), "bolinha")
ARQUIVO = os.path.join(PASTA_CONFIG, "config.json")
# venv, modelo de voz e afins (fora do git)
PASTA_DADOS = os.path.join(os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")), "bolinha")

PADRAO = {
    # aparência
    "estilo": "claro",            # claro | escuro | anel | orbe
    "cor_destaque": "#ffffff",    # anéis e pontinho de voz (no estilo claro o pontinho fica escuro)
    "tamanho": 30,                # raio base do disco, em px
    "largura_cartao": 440,
    "fonte": "Instrument Sans",
    "tamanho_fonte": 15,
    "velocidade_animacao": 1.0,   # 2 = tudo duas vezes mais rápido
    "mostrar_pergunta": True,
    # comportamento
    "modelo_claude": "haiku",     # haiku | sonnet | opus
    "permitir_acoes": True,       # deixa o Claude rodar comandos (modo auto, bloqueia o que for perigoso)
    "instrucoes_extras": "",
    "continuar_ouvindo": True,    # com o cartão aberto, se você falar vira pergunta nova
    "tempo_extra_cartao": 2.0,    # segundos a mais antes do cartão fechar sozinho
    # voz
    "voz": "quando_pedir",        # nunca | quando_pedir | sempre
    "velocidade_voz": 0.95,       # length_scale do Piper: menor = mais rápido
    # microfone
    "modelo_whisper": "large-v3-turbo",
    "usar_gpu": True,
    "silencio_rms": 300,          # limiar de fala; desça se cortar você, suba se não parar de ouvir
    "silencio_seg": 0.8,
    "max_seg": 20,
}


def carregar():
    c = dict(PADRAO)
    try:
        with open(ARQUIVO) as f:
            c.update({k: v for k, v in json.load(f).items() if k in PADRAO})
    except (OSError, ValueError):
        pass
    return c


def salvar(c):
    os.makedirs(PASTA_CONFIG, exist_ok=True)
    tmp = ARQUIVO + ".tmp"
    with open(tmp, "w") as f:
        json.dump({k: c[k] for k in PADRAO}, f, indent=2, ensure_ascii=False)
    os.replace(tmp, ARQUIVO)
