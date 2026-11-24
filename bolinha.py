#!/usr/bin/env python3
"""Bolinha: aperta o atalho, fala, e o Claude responde numa bolinha flutuante.

Clique ou Esc fecha. Apertar o atalho de novo com ela aberta também fecha.
--demo simula pergunta e resposta (pra testar o visual sem mic nem Claude); --demo-voz responde falando.
Ajustes em ~/.config/bolinha/config.json (ou pelo app "Bolinha — Ajustes")."""
import json, math, os, random, signal, subprocess, sys, tempfile, threading, time
import numpy as np
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QGuiApplication, QPainter
from PyQt6.QtWidgets import QApplication, QWidget

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import config  # noqa: E402
import fala  # noqa: E402
import visual  # noqa: E402

CFG = config.carregar()
RATE = 16000
DEMO = "--demo-voz" if "--demo-voz" in sys.argv else "--demo" if "--demo" in sys.argv else None
LOCK = os.path.join(tempfile.gettempdir(), f"bolinha-{os.getuid()}.pid")
DEMO_PERGUNTA = "quanto tempo leva pra ferver um ovo?"
DEMO_RESPOSTA = ("Uns 6 a 7 minutos pra gema mole e 9 a 10 pra gema dura, contando a partir da água já fervendo. "
                 "Depois joga na água gelada pra parar o cozimento e descascar fácil.")


def montar_prompt():
    p = ("Você está respondendo por uma bolinha flutuante de assistente de voz no desktop Linux do usuário. "
         "A pergunta veio de transcrição de voz, pode ter erros. Responda em português, curto e direto "
         "(no máximo ~4 frases), texto puro, sem markdown, sem listas.")
    if CFG["permitir_acoes"]:
        p += (" Você pode executar ações no computador dele quando ele pedir. No Hyprland, pra abrir programas use "
              "`hyprctl dispatch exec <comando>` (assim o app não morre quando você terminar). Depois de agir, diga "
              "em uma frase o que fez.")
    if CFG["voz"] == "quando_pedir":
        p += (" A resposta aparece só escrita, a menos que ele peça pra você falar/responder em voz alta/ler pra ele: "
              "só nesse caso comece a resposta exatamente com [voz].")
    elif CFG["voz"] == "sempre":
        p += " A resposta vai ser lida em voz alta."
    if CFG["instrucoes_extras"].strip():
        p += " " + CFG["instrucoes_extras"].strip()
    return p


def bandas(amostras, sr, offset=2.2):
    """(grave, médio, agudo) 0..1 de um pedaço de áudio int16."""
    a = amostras.astype(np.float32)
    rms = math.sqrt(float((a ** 2).mean()) or 1)
    nivel = min(1, max(0, (math.log10(rms) - offset) / 1.5))
    f = np.abs(np.fft.rfft(a)) ** 2
    hz = np.fft.rfftfreq(len(a), 1 / sr)
    e = [f[(hz >= lo) & (hz < hi)].sum() for lo, hi in ((60, 300), (300, 2000), (2000, 7000))]
    tot = sum(e) or 1
    return [min(1, nivel * (0.35 + 1.9 * x / tot)) for x in e]


class Bolha(QWidget):
    def __init__(self):
        super().__init__(flags=Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("bolinha")
        self.cena = visual.Cena(CFG)
        self.setFixedSize(int(self.cena.W), int(self.cena.H))
        self.duracao = 0
        self.player = None
        self.com_voz = False
        self.sessao = None                         # id da conversa no Claude, pra lembrar o contexto
        self.parar = threading.Event()
        t = QTimer(self, interval=16)
        t.timeout.connect(self.update)
        t.start()
        threading.Thread(target=self.trabalho, daemon=True).start()

    # a thread de trabalho só troca valores da cena; o paint lê
    def muda(self, estado):
        self.cena.muda(estado)
        if estado == "pronto":
            self.duracao = max(7, self.cena.n_chars / 18 + 2) + CFG["tempo_extra_cartao"]   # tempo pra ler

    @property
    def fechando(self):
        return self.cena.fechando

    def fechar(self):
        if self.cena.fechando is None:
            self.cena.fechar()
            if self.player:
                self.player.kill()
            QTimer.singleShot(int(self.cena.duracao_fechar() * 1000), QApplication.quit)

    def mousePressEvent(self, _):
        # clicar enquanto ouve = "terminei de falar"; depois disso, fecha
        if self.cena.estado == "ouvindo" and not self.parar.is_set():
            self.parar.set()
        else:
            self.fechar()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.fechar()

    def paintEvent(self, _):
        c = self.cena
        if c.estado == "pronto" and not c.falando and time.monotonic() - c.t_estado > self.duracao:
            self.fechar()
        p = QPainter(self)
        c.pintar(p)
        p.end()

    # ---------- trabalho ----------
    def trabalho(self):
        try:
            if CFG["voz"] != "nunca" and (not DEMO or DEMO == "--demo-voz"):
                fala.acordar(CFG["motor_voz"], CFG["manter_voz_min"])   # voz neural carrega enquanto você fala
            if DEMO:
                return self.demo()
            threading.Thread(target=carrega_whisper, daemon=True).start()  # carrega enquanto você fala
            audio = self.gravar()
            primeira = True
            while audio is not None and not self.fechando:
                self.responder(audio, primeira)
                primeira = False
                if not CFG["continuar_ouvindo"]:
                    break
                # cartão aberto: continua ouvindo; se você falar, vira pergunta nova (até o cartão fechar sozinho)
                self.parar = threading.Event()
                audio = self.gravar(esperar_ate=self.cena.t_estado + self.duracao)
        except Exception as e:
            self.cena.resposta, self.com_voz = f"Erro: {e}", False
            self.muda("pronto")

    def responder(self, audio, primeira):
        self.cena.bandas = [0, 0, 0]
        self.muda("pensando")
        pergunta = transcrever(audio)
        if not pergunta:
            if primeira:
                self.cena.pergunta = "…"
                self.cena.resposta = "Não ouvi nada. Aperta de novo e fala mais perto do microfone."
            self.com_voz = False
            return self.muda("pronto")   # na conversa, ruído só volta pro cartão anterior
        cmd = ["claude", "-p", "--model", CFG["modelo_claude"], "--output-format", "json",
               "--append-system-prompt", montar_prompt()]
        if CFG["permitir_acoes"]:
            cmd += ["--permission-mode", "auto"]
        if self.sessao:
            cmd += ["--resume", self.sessao]
        r = subprocess.run(cmd + [pergunta], stdin=subprocess.DEVNULL, capture_output=True, text=True,
                           cwd=os.path.expanduser("~"), timeout=300)
        try:
            j = json.loads(r.stdout)
            self.sessao = j.get("session_id") or self.sessao
            resposta = (j.get("result") or "").strip() or "Sem resposta."
        except ValueError:
            resposta = (r.stdout or r.stderr).strip() or "Sem resposta."
        marcou = resposta.lower().startswith("[voz]")
        if marcou:
            resposta = resposta[5:].strip()
        self.com_voz = CFG["voz"] == "sempre" or (CFG["voz"] == "quando_pedir" and marcou)
        self.cena.pergunta, self.cena.resposta = pergunta, resposta
        self.muda("pronto")
        if self.com_voz:
            self.falar(resposta)

    def falar(self, texto):
        c = self.cena
        if self.fechando:
            return
        c.falando = True
        sincronizar = fala.pronto(CFG["motor_voz"])
        if sincronizar:
            c.rev_inicio = float("inf")   # segura o texto até a voz começar
        else:
            c.revelar()   # motor de voz ainda carregando: mostra o texto já e a voz entra quando der
        try:
            pedacos = fala.sintetizar(texto, CFG)
            sr, audio, frase = next(pedacos)
            if self.fechando:
                return
            self.player = subprocess.Popen(["pw-play", "--raw", "--rate", str(sr), "--channels", "1", "--format", "s16", "-"],
                                           stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
            env = []   # nível da voz a cada 50ms, cresce conforme as frases chegam
            threading.Thread(target=self._toca, args=(sr, audio, pedacos, env), daemon=True).start()
            inicio = time.monotonic()
            # ritmo do texto pela primeira frase, um tiquinho à frente da voz
            if sincronizar:
                c.revelar(inicio, len(frase) / max(len(audio) / sr, 0.3) * 1.06)
            while self.player.poll() is None:
                i = int((time.monotonic() - inicio) * 20)
                c.bandas = env[i] if i < len(env) else [0, 0, 0]
                time.sleep(0.025)
        except Exception:
            if sincronizar:
                c.revelar()  # sem voz: revela no ritmo padrão
        finally:
            c.bandas, c.falando = [0, 0, 0], False
            self.duracao = max(self.duracao, time.monotonic() - c.t_estado + 3.5)

    def _toca(self, sr, audio, pedacos, env):
        passo = sr // 20
        try:
            while True:
                env.extend(bandas(audio[i:i + passo], sr, 2.5) for i in range(0, len(audio) - passo, passo))
                self.player.stdin.write(audio.tobytes()); self.player.stdin.flush()
                if self.fechando:
                    break
                _, audio, _ = next(pedacos)
        except (StopIteration, OSError):
            pass  # acabou, ou fechou no meio da fala
        finally:
            try:
                self.player.stdin.close()
            except OSError:
                pass

    def demo(self):
        c = self.cena
        fim = time.monotonic() + 3.5
        while time.monotonic() < fim and not self.fechando:
            c.bandas = voz_falsa(time.monotonic())
            time.sleep(0.05)
        c.bandas = [0, 0, 0]
        self.muda("pensando")
        time.sleep(2)
        c.pergunta, c.resposta = DEMO_PERGUNTA, DEMO_RESPOSTA
        self.com_voz = DEMO == "--demo-voz"
        self.muda("pronto")
        if self.com_voz:
            self.falar(c.resposta)

    def gravar(self, esperar_ate=None):
        """Sem esperar_ate: grava já (primeira pergunta). Com esperar_ate: fica de ouvido até essa hora;
        só vira pergunta se você falar por ~0,25s seguidos (ignora clique de teclado e barulho curto)."""
        rec = subprocess.Popen(["pw-record", "--raw", "--rate", str(RATE), "--channels", "1", "--format", "s16", "-"],
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        bloco, dados, falou, calado, seguidos = RATE // 20, bytearray(), False, 0, 0
        try:
            while not self.parar.is_set() and not self.fechando and len(dados) < CFG["max_seg"] * RATE * 2:
                b = rec.stdout.read(bloco * 2)
                if not b:
                    break
                dados += b
                s = np.frombuffer(b, np.int16)
                self.cena.bandas = bandas(s, RATE)
                alto = math.sqrt(float((s.astype(np.float32) ** 2).mean())) > CFG["silencio_rms"]
                seguidos = seguidos + 1 if alto else 0
                if not falou:
                    if seguidos >= (5 if esperar_ate else 1):
                        falou = True
                        if esperar_ate:
                            self.muda("ouvindo")
                    elif esperar_ate:
                        dados = dados[-RATE * 2:]          # guarda só o último segundo enquanto espera
                        if time.monotonic() > esperar_ate:
                            return None
                elif alto:
                    calado = 0
                else:
                    calado += 1
                    if calado >= CFG["silencio_seg"] * 20:
                        break
        finally:
            rec.terminate()
            self.cena.bandas = [0, 0, 0]
        if esperar_ate and not falou:
            return None
        return bytes(dados)


def voz_falsa(x):
    """Níveis de áudio de mentira, pra demo e pra prévia dos ajustes."""
    env = max(0, math.sin(x * 6)) * random.uniform(0.6, 1)
    return [env * (0.6 + 0.4 * math.sin(x * 2)), env * 0.9, env * random.uniform(0.2, 0.8)]


_whisper, _voz, _lock = None, None, threading.Lock()


def carrega_whisper():
    global _whisper
    with _lock:
        if _whisper is None:
            import ctypes, glob
            from faster_whisper import WhisperModel
            # Chatterbox numa placa de menos de 8 GB ocupa quase tudo: o Whisper fica no processador
            chatterbox = CFG["voz"] != "nunca" and CFG["motor_voz"] == "chatterbox" and 0 < fala.vram_gb() < 8
            if CFG["usar_gpu"] and not chatterbox:
                # cuBLAS/cuDNN vêm do pip (pacotes nvidia-*); pré-carrega pro CTranslate2 achar
                for lib in ("cublasLt.so.12", "cublas.so.12", "cudnn*.so.9"):
                    for f in sorted(glob.glob(os.path.join(sys.prefix, "lib/python3*/site-packages/nvidia/*/lib/lib" + lib))):
                        try:
                            ctypes.CDLL(f, mode=ctypes.RTLD_GLOBAL)
                        except OSError:
                            pass
                try:
                    _whisper = WhisperModel(CFG["modelo_whisper"], device="cuda", compute_type="float16")
                except Exception:
                    pass
            if _whisper is None:
                _whisper = WhisperModel(CFG["modelo_whisper"], device="cpu", compute_type="int8")
    return _whisper


def transcrever(pcm):
    global _whisper
    audio = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768  # array direto, sem passar pelo PyAV
    try:
        segs, _ = carrega_whisper().transcribe(audio, language="pt", vad_filter=True, beam_size=1)
        return " ".join(s.text.strip() for s in segs).strip()
    except RuntimeError as e:
        if "out of memory" not in str(e).lower():
            raise
        # placa cheia (ex.: Chatterbox carregado numa placa de 6 GB): transcreve no processador
        from faster_whisper import WhisperModel
        with _lock:
            _whisper = WhisperModel(CFG["modelo_whisper"], device="cpu", compute_type="int8")
        segs, _ = _whisper.transcribe(audio, language="pt", vad_filter=True, beam_size=1)
        return " ".join(s.text.strip() for s in segs).strip()


if __name__ == "__main__":
    # segundo toque no atalho: fecha a que está aberta
    try:
        pid = int(open(LOCK).read())
        if b"bolinha.py" in open(f"/proc/{pid}/cmdline", "rb").read():
            os.kill(pid, signal.SIGTERM)
            sys.exit()
        raise OSError
    except (OSError, ValueError):
        open(LOCK, "w").write(str(os.getpid()))
    app = QApplication(sys.argv)
    QGuiApplication.setDesktopFileName("bolinha")
    visual.registrar_fontes()
    b = Bolha()
    signal.signal(signal.SIGTERM, lambda *_: b.fechar())   # atalho de novo = fecha animado (app.quit direto dava segfault no Wayland)
    b.show()
    app.exec()
    os.unlink(LOCK)
    os._exit(0)   # sai direto: threads de áudio/whisper ainda vivas fariam o Qt dar segfault na desmontagem
