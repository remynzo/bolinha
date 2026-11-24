"""Servidor de voz neural (XTTS ou Chatterbox) que fica carregado entre uma pergunta e outra.

Roda no Python do motor (~/.local/share/bolinha/motores/<motor>), não no da bolinha:
    motores/xtts/bin/python voz_servidor.py xtts
Escuta num socket Unix e se desliga sozinho depois de OCIOSO segundos sem uso, pra soltar a VRAM.

Protocolo: o cliente manda uma linha JSON {"frases": [...], "voz": "francisca", "vel": 1.0}.
O servidor responde a taxa de amostragem (uint32) e, pra cada frase, o tamanho em bytes (uint32)
seguido do áudio int16 mono. Tamanho 0 = fim.
"""
import fcntl
import json
import os
import socket
import struct
import sys
import threading

import numpy as np

MOTOR = sys.argv[1]
OCIOSO = int(sys.argv[2]) if len(sys.argv) > 2 else 15 * 60   # 0 = nunca desliga
DADOS = os.path.join(os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")), "bolinha")
SOCK = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), f"bolinha-voz-{MOTOR}.sock")


def referencia(nome):
    return os.path.join(DADOS, "voz", f"{nome}.wav")


class Xtts:
    sr = 24000

    def __init__(self):
        os.environ["COQUI_TOS_AGREED"] = "1"   # licença CPML (não comercial), aceita pelo usuário no instalador
        from TTS.api import TTS
        self.m = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to("cuda").synthesizer.tts_model
        self.vozes = {}

    def falar(self, frase, voz, vel):
        if voz not in self.vozes:
            self.vozes[voz] = self.m.get_conditioning_latents(audio_path=[referencia(voz)])
        lat, emb = self.vozes[voz]
        return np.asarray(self.m.inference(frase, "pt", lat, emb, speed=vel, enable_text_splitting=False)["wav"])


class Chatterbox:
    def __init__(self):
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS
        self.m = ChatterboxMultilingualTTS.from_pretrained(device="cuda")
        self.sr, self.voz = self.m.sr, None

    def falar(self, frase, voz, vel):   # Chatterbox não tem controle de velocidade
        if voz != self.voz:
            self.m.prepare_conditionals(referencia(voz))
            self.voz = voz
        return self.m.generate(frase, language_id="pt").squeeze(0).cpu().numpy()


def atender(con, motor, trava):
    with con, con.makefile("rb") as f:
        pedido = json.loads(f.readline())
        if pedido.get("sair"):   # outro motor vai subir e precisa da VRAM
            os.unlink(SOCK)
            os._exit(0)
        con.sendall(struct.pack("<I", motor.sr))
        for frase in pedido["frases"]:
            with trava:   # uma frase por vez na GPU
                wav = motor.falar(frase, pedido.get("voz", "francisca"), pedido.get("vel", 1.0))
            dados = (np.clip(wav, -1, 1) * 32767).astype("<i2").tobytes()
            con.sendall(struct.pack("<I", len(dados)) + dados)
        con.sendall(struct.pack("<I", 0))


def main():
    motor = {"xtts": Xtts, "chatterbox": Chatterbox}[MOTOR]()
    if os.path.exists(SOCK):
        os.unlink(SOCK)
    s = socket.socket(socket.AF_UNIX)
    s.bind(SOCK)
    s.listen()
    s.settimeout(OCIOSO or None)
    trava = threading.Lock()
    try:
        while True:
            try:
                con, _ = s.accept()
            except socket.timeout:
                break   # ninguém pediu nada faz tempo: libera a placa de vídeo
            con.settimeout(None)
            threading.Thread(target=lambda: _seguro(atender, con, motor, trava), daemon=True).start()
    finally:
        os.unlink(SOCK)


def _seguro(f, *a):
    try:
        f(*a)
    except Exception as e:   # cliente fechou no meio, falta de VRAM…: a bolinha cai pro texto sem voz
        print("voz:", e, file=sys.stderr)


if __name__ == "__main__":
    # um servidor por motor: se outro já está subindo ou rodando, sai
    trava_arq = open(SOCK + ".lock", "w")
    try:
        fcntl.flock(trava_arq, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        sys.exit(0)
    main()
