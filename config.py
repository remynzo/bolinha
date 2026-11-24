"""Configuração da bolinha: ~/.config/bolinha/config.json.

Dois níveis:
- ajustes gerais (Claude, voz, microfone), iguais pra todos os perfis;
- perfis visuais (bolinha, cartão, animação), um ativo por vez.
"""
import copy
import json
import os

PASTA_CONFIG = os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")), "bolinha")
ARQUIVO = os.path.join(PASTA_CONFIG, "config.json")
# venv, modelo de voz e afins (fora do git)
PASTA_DADOS = os.path.join(os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")), "bolinha")

GERAL = {
    "modelo_claude": "haiku",     # haiku | sonnet | opus
    "permitir_acoes": True,       # deixa o Claude rodar comandos (modo auto, bloqueia o que for perigoso)
    "instrucoes_extras": "",
    "continuar_ouvindo": True,    # com o cartão aberto, se você falar vira pergunta nova
    "tempo_extra_cartao": 2.0,    # segundos a mais antes do cartão fechar sozinho
    "voz": "quando_pedir",        # nunca | quando_pedir | sempre
    "velocidade_voz": 0.95,       # menor = mais rápido
    "motor_voz": "piper",         # piper | xtts | chatterbox (os dois últimos: ./install.sh --vozes-neurais)
    "voz_nome": "francisca",      # francisca | antonio (só nos motores neurais)
    "manter_voz_min": 15,         # minutos que a voz neural fica carregada na GPU depois do último uso; 0 = sempre
    "modelo_whisper": "large-v3-turbo",
    "usar_gpu": True,
    "silencio_rms": 300,          # limiar de fala; desça se cortar você, suba se não parar de ouvir
    "silencio_seg": 0.8,
    "max_seg": 20,
}

# o que um perfil visual guarda
VISUAL = {
    "bolinha": "disco",           # disco | anel | orbe | gota | barras | pontos | halo
    "cor_bolinha": "#ffffff",
    "cor_destaque": "#ffffff",    # anéis, brilho, pontinho de voz
    "tamanho": 30,
    "cartao": "solido",           # solido | vidro | contorno | balao | flutuante
    "cor_cartao": "#ffffff",
    "cor_texto": "#161616",
    "cantos": 22,
    "largura_cartao": 440,
    "fonte": "Instrument Sans",
    "tamanho_fonte": 15,
    "mostrar_pergunta": True,
    "entrada": "pop",             # pop | fade | queda | zoom
    "transformacao": "mola",      # mola | suave | elastica | direta
    "revelar": "palavra",         # palavra | maquina | linha | inteiro
    "velocidade_animacao": 1.0,
}

PERFIS_PRONTOS = {
    "Minimal": {},
    "Grafite": {"bolinha": "disco", "cor_bolinha": "#26262b", "cor_destaque": "#9db4ff", "cartao": "solido",
                "cor_cartao": "#1f1f24", "cor_texto": "#ececef", "entrada": "fade", "transformacao": "suave"},
    "Anel": {"bolinha": "anel", "cor_bolinha": "#f4f4f4", "cor_destaque": "#f4f4f4", "cartao": "contorno",
             "cor_cartao": "#101014", "cor_texto": "#f0f0f0", "cantos": 18, "revelar": "maquina",
             "fonte": "JetBrains Mono", "tamanho_fonte": 13},
    "Orbe": {"bolinha": "orbe", "cor_bolinha": "#cc4a2a", "cor_destaque": "#ecdbb1", "cartao": "vidro",
             "cor_cartao": "#1c1b1a", "cor_texto": "#f4efe3", "tamanho": 36, "transformacao": "elastica"},
    "Neon": {"bolinha": "barras", "cor_bolinha": "#3df5d0", "cor_destaque": "#ff4fd8", "cartao": "contorno",
             "cor_cartao": "#0b0614", "cor_texto": "#e9fffb", "cantos": 14, "entrada": "zoom", "revelar": "linha",
             "transformacao": "direta"},
    "Papel": {"bolinha": "gota", "cor_bolinha": "#2b2622", "cor_destaque": "#b8492f", "cartao": "balao",
              "cor_cartao": "#f3ecdf", "cor_texto": "#2b2622", "fonte": "Instrument Serif", "tamanho_fonte": 18,
              "cantos": 16, "entrada": "queda"},
    "Pontos": {"bolinha": "pontos", "cor_bolinha": "#ffffff", "cor_destaque": "#ffd166", "cartao": "flutuante",
               "cor_cartao": "#000000", "cor_texto": "#ffffff", "tamanho_fonte": 17, "revelar": "palavra",
               "entrada": "fade", "transformacao": "suave"},
    "Halo": {"bolinha": "halo", "cor_bolinha": "#7cf3ff", "cor_destaque": "#b18cff", "cartao": "vidro",
             "cor_cartao": "#12121a", "cor_texto": "#eef0ff", "tamanho": 34, "revelar": "inteiro",
             "transformacao": "suave"},
}


def perfil_pronto(nome):
    return {**VISUAL, **PERFIS_PRONTOS.get(nome, {})}


def carregar_tudo():
    """{'perfil': nome ativo, 'perfis': {nome: visual}, **GERAL}"""
    try:
        with open(ARQUIVO) as f:
            salvo = json.load(f)
    except (OSError, ValueError):
        salvo = {}
    c = {**GERAL, **{k: v for k, v in salvo.items() if k in GERAL}}
    perfis = {n: perfil_pronto(n) for n in PERFIS_PRONTOS}
    for nome, v in (salvo.get("perfis") or {}).items():
        perfis[nome] = {**perfil_pronto(nome), **{k: x for k, x in v.items() if k in VISUAL}}
    if "perfis" not in salvo and "estilo" in salvo:
        # config antiga (sem perfis): vira "Meu perfil" com o que dá pra aproveitar
        antigo = {"escuro": "Grafite", "anel": "Anel", "orbe": "Orbe"}.get(salvo["estilo"], "Minimal")
        perfis["Meu perfil"] = {**perfil_pronto(antigo), **{k: salvo[k] for k in ("tamanho", "largura_cartao", "fonte",
                                "tamanho_fonte", "velocidade_animacao", "mostrar_pergunta", "cor_destaque") if k in salvo}}
        salvo["perfil"] = "Meu perfil"
    c["perfis"] = perfis
    c["perfil"] = salvo.get("perfil") if salvo.get("perfil") in perfis else "Minimal"
    return c


def carregar():
    """Config pronta pra usar: gerais + visual do perfil ativo, num dict só."""
    tudo = carregar_tudo()
    return {**{k: tudo[k] for k in GERAL}, **tudo["perfis"][tudo["perfil"]], "perfil": tudo["perfil"]}


def salvar(tudo):
    os.makedirs(PASTA_CONFIG, exist_ok=True)
    dados = {k: tudo[k] for k in GERAL}
    dados["perfil"] = tudo["perfil"]
    dados["perfis"] = copy.deepcopy(tudo["perfis"])
    tmp = ARQUIVO + ".tmp"
    with open(tmp, "w") as f:
        json.dump(dados, f, indent=2, ensure_ascii=False)
    os.replace(tmp, ARQUIVO)
