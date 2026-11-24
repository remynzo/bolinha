"""Transforma texto em fala, frase por frase, com o motor escolhido nos ajustes.

- piper: voz Dii, roda aqui mesmo na CPU, instantâneo.
- xtts / chatterbox: vozes neurais (Francisca, Antonio) num processo à parte (voz_servidor.py),
  que fica carregado na placa de vídeo e se desliga sozinho quando fica parado.
"""
import json
import os
import re
import socket
import struct
import subprocess
import time

import numpy as np

import config

MOTORES = {"piper": "Piper (Dii)", "xtts": "XTTS", "chatterbox": "Chatterbox"}
VOZES = {"francisca": "Francisca", "antonio": "Antonio"}
DII = os.path.join(config.PASTA_DADOS, "voz", "pt_BR-dii.onnx")
SERVIDOR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "voz_servidor.py")


def python_do_motor(motor):
    return os.path.join(config.PASTA_DADOS, "motores", motor, "bin", "python")


def instalado(motor):
    return motor == "piper" or os.path.exists(python_do_motor(motor))


def sock(motor):
    return os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), f"bolinha-voz-{motor}.sock")


def pronto(motor):
    if motor == "piper" or not instalado(motor):
        return True
    try:
        with socket.socket(socket.AF_UNIX) as s:
            s.connect(sock(motor))
        return True
    except OSError:
        return False


def acordar(motor, manter_min=15):
    """Sobe o servidor do motor se ele não estiver rodando (carregar leva ~12s, então chame cedo).
    manter_min: minutos parado até ele se desligar; 0 = nunca."""
    if pronto(motor):
        return
    for outro in MOTORES:   # dois motores neurais juntos não cabem numa placa de 6 GB
        if outro not in ("piper", motor):
            try:
                with socket.socket(socket.AF_UNIX) as s:
                    s.connect(sock(outro)); s.sendall(b'{"sair": true}\n')
            except OSError:
                pass
    # se já estiver subindo, a trava do servidor faz esse segundo sair na hora
    subprocess.Popen([python_do_motor(motor), "-I", SERVIDOR, motor, str(int(manter_min * 60))], start_new_session=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def frases(texto):
    texto = texto.replace("`", "").replace("*", "").replace("#", "")
    return [f for f in re.split(r"(?<=[.!?…:;])\s+|\n+", texto) if f.strip()]


_dii = None


def _piper(lista, vel):
    global _dii
    from piper import PiperVoice, SynthesisConfig
    if _dii is None:
        _dii = PiperVoice.load(DII)
    for f in lista:
        audio = np.concatenate([x.audio_int16_array for x in _dii.synthesize(f, SynthesisConfig(length_scale=vel))])
        yield _dii.config.sample_rate, audio, f


def _ler(arq, n):
    dados = arq.read(n)
    if len(dados) < n:
        raise OSError("servidor de voz caiu")
    return dados


def _servidor(motor, lista, voz, vel, espera, manter_min):
    acordar(motor, manter_min)
    limite = time.monotonic() + espera
    while True:
        try:
            con = socket.socket(socket.AF_UNIX)
            con.connect(sock(motor))
            break
        except OSError:
            con.close()
            if time.monotonic() > limite:
                raise
            time.sleep(0.2)
    with con, con.makefile("rb") as arq:
        # velocidade_voz é o length_scale do Piper (menor = mais rápido); o XTTS quer o contrário
        con.sendall((json.dumps({"frases": lista, "voz": voz, "vel": 1 / vel}) + "\n").encode())
        sr = struct.unpack("<I", _ler(arq, 4))[0]
        for f in lista:
            n = struct.unpack("<I", _ler(arq, 4))[0]
            yield sr, np.frombuffer(_ler(arq, n), "<i2"), f


def sintetizar(texto, cfg, espera=40):
    """Gera (taxa, áudio int16, frase) pra cada frase, assim que cada uma fica pronta."""
    lista = frases(texto)
    motor = cfg.get("motor_voz", "piper")
    if not instalado(motor):
        motor = "piper"
    if motor == "piper":
        yield from _piper(lista, cfg["velocidade_voz"])
    else:
        yield from _servidor(motor, lista, cfg.get("voz_nome", "francisca"), cfg["velocidade_voz"], espera,
                              cfg.get("manter_voz_min", 15))


if __name__ == "__main__":
    assert frases("Oi! Tudo bem? Sim.\nOutra linha") == ["Oi!", "Tudo bem?", "Sim.", "Outra linha"]
    assert frases("**3.5** graus") == ["3.5 graus"]
    print("ok")
