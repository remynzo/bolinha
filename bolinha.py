#!/usr/bin/env python3
"""Bolinha: aperta o atalho, fala, e o Claude responde numa bolinha flutuante.

Clique ou Esc fecha. Apertar o atalho de novo com ela aberta também fecha.
--demo simula pergunta e resposta (pra testar o visual sem mic nem Claude); --demo-voz responde falando.
Ajustes em ~/.config/bolinha/config.json (ou pelo app "Bolinha — Ajustes")."""
import json, math, os, random, signal, subprocess, sys, tempfile, threading, time
import numpy as np
from PyQt6.QtCore import Qt, QPointF, QRectF, QTimer
from PyQt6.QtGui import (QBrush, QColor, QFont, QFontDatabase, QFontMetricsF, QGuiApplication, QPainter,
                         QPainterPath, QPen, QRadialGradient)
from PyQt6.QtWidgets import QApplication, QWidget

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import config  # noqa: E402

CFG = config.carregar()
VOZ = os.path.join(config.PASTA_DADOS, "voz", "pt_BR-dii.onnx")
RATE = 16000
DEMO = "--demo-voz" if "--demo-voz" in sys.argv else "--demo" if "--demo" in sys.argv else None
LOCK = os.path.join(tempfile.gettempdir(), f"bolinha-{os.getuid()}.pid")
WALLUST = os.path.expanduser("~/.config/hypr/wallust/wallust-hyprland.conf")


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


W, H = CFG["largura_cartao"] + 120, 560   # área transparente da janela; tudo é desenhado dentro dela
R = CFG["tamanho"]
CARD_W = CFG["largura_cartao"]
PAD = 28
VA = max(0.2, CFG["velocidade_animacao"])

# segundo toque no atalho: fecha a que está aberta
try:
    pid = int(open(LOCK).read())
    if b"bolinha" in open(f"/proc/{pid}/cmdline", "rb").read():
        os.kill(pid, signal.SIGTERM)
        sys.exit()
    raise OSError
except (OSError, ValueError):
    open(LOCK, "w").write(str(os.getpid()))


def ease_out_back(x, s=1.5):
    x = min(1, max(0, x)) - 1
    return 1 + x * x * ((s + 1) * x + s)


def ease_out(x):
    return 1 - (1 - min(1, max(0, x))) ** 3


def ease_in_out(x):
    x = min(1, max(0, x))
    return 4 * x ** 3 if x < .5 else 1 - (-2 * x + 2) ** 3 / 2


def mix(a, b, t):
    return a + (b - a) * t


def alfa(cor, a):
    c = QColor(cor); c.setAlphaF(max(0.0, min(1.0, a))); return c


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


def quebra(texto, fonte, largura, max_linhas=99):
    """Quebra em linhas e devolve [(palavra, x, y, pos_char)], altura."""
    m = QFontMetricsF(fonte)
    esp, lh = m.horizontalAdvance(" "), m.lineSpacing() * 1.18
    out, x, y, pos = [], 0.0, 0.0, 0
    for paragrafo in texto.split("\n"):
        for w in paragrafo.split():
            wl = m.horizontalAdvance(w)
            if x and x + wl > largura:
                x, y = 0.0, y + lh
            if y >= max_linhas * lh:
                out[-1] = (out[-1][0] + "…",) + out[-1][1:]
                return out, max_linhas * lh
            out.append((w, x, y, pos))
            x += wl + esp
            pos += len(w) + 1
        x, y = 0.0, y + lh
    return out, y


def wallust():
    """Cores do papel de parede (wallust), usadas no estilo orbe."""
    import re
    c = {"background": "1d1c1a", "color10": "cc4a2a", "color2": "8a2414", "color14": "ecdbb1"}
    try:
        c.update(re.findall(r"\$(\w+)\s*=\s*rgb\((\w{6})\)", open(WALLUST).read()))
    except OSError:
        pass
    return {k: QColor("#" + v) for k, v in c.items()}


def tema(estilo, destaque):
    d = QColor(destaque)
    claro = {"disco": QColor(255, 255, 255), "cartao": QColor(255, 255, 255), "borda": None,
             "texto": QColor(22, 22, 22), "pergunta": QColor(130, 130, 130), "ponto": QColor(20, 20, 20), "onda": d}
    escuro = {"disco": QColor(30, 30, 34), "cartao": QColor(30, 30, 34), "borda": QColor(255, 255, 255, 36),
              "texto": QColor(240, 240, 242), "pergunta": QColor(140, 140, 148), "ponto": d, "onda": d}
    return {"claro": claro, "escuro": escuro, "anel": escuro, "orbe": escuro}.get(estilo, claro)


class Bolha(QWidget):
    def __init__(self):
        super().__init__(flags=Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("bolinha")
        self.setFixedSize(W, H)
        QFontDatabase.addApplicationFont(os.path.join(AQUI, "fontes", "InstrumentSans.ttf"))
        self.f_resp = QFont(CFG["fonte"]); self.f_resp.setPointSizeF(CFG["tamanho_fonte"])
        self.f_perg = QFont(self.f_resp); self.f_perg.setPointSizeF(CFG["tamanho_fonte"] * 0.73)
        self.estilo = CFG["estilo"]
        self.T = tema(self.estilo, CFG["cor_destaque"])
        self.W_ = wallust() if self.estilo == "orbe" else None
        self.fase = [0.0, 2.1, 4.2]              # ângulo das luzes do orbe
        self.t0 = self.ultimo = time.monotonic()
        self.estado, self.t_estado = "ouvindo", self.t0
        self.bandas = [0.0, 0.0, 0.0]            # nível do áudio (mic ou voz)
        self.bs = [0.0, 0.0, 0.0]                # suavizado pro desenho
        self.nv = 0.0
        self.ondas = []                          # anéis que saem nos picos de voz
        self.pergunta = self.resposta = ""
        self.fechando = None
        self.duracao = 0
        self.falando, self.player = False, None
        self.com_voz = False
        self.sessao = None                       # id da conversa no Claude, pra lembrar o contexto
        self.card_saindo = None
        self.rev_inicio, self.rev_vel = None, 45.0   # revelação das palavras (chars/s)
        self.card_h = 0
        self.parar = threading.Event()
        t = QTimer(self, interval=16)
        t.timeout.connect(self.update)
        t.start()
        threading.Thread(target=self.trabalho, daemon=True).start()

    # ---------- estado (a thread de trabalho só troca valores; o paint lê) ----------
    def muda(self, estado):
        if self.estado == "pronto" and estado == "ouvindo":
            self.card_saindo = self.card_h          # cartão encolhe de volta pra disco
        if estado == "pronto":
            if CFG["mostrar_pergunta"]:
                self.l_perg, self.h_perg = quebra(self.pergunta, self.f_perg, CARD_W - 2 * PAD - 24, max_linhas=2)
                self.h_perg += 10
            else:
                self.l_perg, self.h_perg = [], 0
            self.l_resp, h_resp = quebra(self.resposta, self.f_resp, CARD_W - 2 * PAD)
            self.card_h = min(H - 40, 2 * PAD - 4 + self.h_perg + h_resp - 6)
            self.n_chars = len(self.resposta) + 1
            self.duracao = max(7, self.n_chars / 18 + 2) + CFG["tempo_extra_cartao"]   # tempo pra ler
            if not self.com_voz:
                self.rev_inicio = time.monotonic() + 0.4 / VA
        self.estado, self.t_estado = estado, time.monotonic()

    def fechar(self):
        if self.fechando is None:
            self.fechando = time.monotonic()
            if self.player:
                self.player.kill()
            QTimer.singleShot(int(560 / VA), QApplication.quit)

    def mousePressEvent(self, _):
        # clicar enquanto ouve = "terminei de falar"; depois disso, fecha
        if self.estado == "ouvindo" and not self.parar.is_set():
            self.parar.set()
        else:
            self.fechar()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.fechar()

    # ---------- desenho ----------
    def paintEvent(self, _):
        agora = time.monotonic()
        dt_frame, self.ultimo = agora - self.ultimo, agora
        t, de = agora - self.t0, agora - self.t_estado
        if self.estado == "pronto" and not self.falando and de > self.duracao:
            self.fechar()
        for i in range(3):
            self.bs[i] += (self.bandas[i] - self.bs[i]) * (0.4 if self.bandas[i] > self.bs[i] else 0.12)
        self.nv = sum(self.bs) / 3
        giro = 3.2 if self.estado == "pensando" else 0.6 + 3 * self.nv
        for i in range(3):
            self.fase[i] += dt_frame * giro * (1 + 0.37 * i) * (-1 if i == 1 else 1)
        ta, da = t * VA, de * VA   # tempos das animações (escalados pela velocidade escolhida)

        # saída: cartão volta a ser disco, disco some
        fecha_card = fecha_disco = 0.0
        if self.fechando:
            x = (agora - self.fechando) * VA
            fecha_card, fecha_disco = ease_in_out(x / 0.3), ease_in_out((x - 0.25) / 0.25)

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        c = QPointF(W / 2, H / 2)
        escala = ease_out_back(ta / 0.5, 1.4) * (1 - fecha_disco)
        r_pensa = R * (0.5 + 0.05 * math.sin(t * 3.4))
        disco = lambda r: QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r)

        if self.estado == "ouvindo":
            r = R * (0.62 + 0.5 * self.nv + 0.02 * math.sin(t * 2))
            if self.card_saindo and da < 0.4:
                k = 1 - ease_in_out(da / 0.4)
                w, h = mix(2 * r, CARD_W, k), mix(2 * r, self.card_saindo, k)
                self.forma(p, QRectF(c.x() - w / 2, c.y() - h / 2, w, h), mix(r, 22, k), escala, k, t)
                return
            self.anel(p, c, r, t)
            self.forma(p, disco(r), r, escala, 0, t)
        elif self.estado == "pensando":
            self.forma(p, disco(r_pensa), r_pensa, escala, 0, t)
        else:
            k = ease_out(da / 0.65) * (1 - fecha_card)
            kw = ease_out_back(da / 0.65, 1.1) * (1 - fecha_card)
            w, h = mix(2 * r_pensa, CARD_W, kw), mix(2 * r_pensa, self.card_h, k)
            rect = QRectF(c.x() - w / 2, c.y() - h / 2, w, h)
            self.forma(p, rect, mix(r_pensa, 22, k), escala, k, t)
            if k > 0.75:
                self.conteudo(p, rect, ease_out((k - 0.75) / 0.25))

    def forma(self, p, rect, rad, escala, k, t):
        """Desenha a bolinha (k=0) ou o cartão (k=1), e tudo no meio da transformação."""
        if escala <= 0.01:
            return
        T = self.T
        p.save()
        c = rect.center()
        p.translate(c); p.scale(escala, escala); p.translate(-c)
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(5):  # sombra curta, pra aparecer em janela clara também
            p.setBrush(QColor(0, 0, 0, int((14 - 2 * i) * (k if self.estilo == "anel" else 1))))
            p.drawRoundedRect(rect.adjusted(-i, -i + 4, i, i + 4), rad + i, rad + i)

        if self.estilo == "anel":
            # aro que engrossa com a voz e vai ganhando fundo ao virar cartão
            p.setBrush(alfa(T["cartao"], mix(0.06, 1, k)))
            p.setPen(QPen(alfa(T["onda"], mix(1, 0.18, k)), mix(2.2 + 4 * self.nv, 1, k)))
            p.drawRoundedRect(rect, rad, rad)
        elif self.estilo == "orbe":
            if k > 0:
                p.setBrush(alfa(T["cartao"], k))
                p.setPen(QPen(alfa(T["borda"], T["borda"].alphaF() * k), 1))
                p.drawRoundedRect(rect, rad, rad)
            if k < 1:
                rr = min(rect.width(), rect.height()) / 2 * (1 - k)
                self.orbe(p, c, max(rr, 0.1), t, 1 - k)
        else:
            p.setBrush(T["cartao"] if k > 0 else T["disco"])
            p.setPen(QPen(T["borda"], 1) if T["borda"] else Qt.PenStyle.NoPen)
            p.drawRoundedRect(rect, rad, rad)
        p.restore()

    def orbe(self, p, c, raio, t, opac):
        """Esfera escura com três luzes (grave, médio, agudo) nas cores do papel de parede."""
        P, b = self.W_, self.bs
        p.save()
        p.setOpacity(opac)
        forma = QPainterPath()
        amp = 0.01 + 0.05 * self.nv
        for i in range(97):
            a = 2 * math.pi * i / 96
            r = raio * (1 + amp * (math.sin(3 * a + t * 2.3) * (0.4 + b[0]) + math.sin(5 * a - t * 3.1) * (0.3 + b[2])))
            pt = QPointF(c.x() + r * math.cos(a), c.y() + r * math.sin(a))
            forma.moveTo(pt) if i == 0 else forma.lineTo(pt)
        g = QRadialGradient(c, raio * 2.6)
        g.setColorAt(0, alfa(P["color10"], 0.3 + 0.4 * self.nv)); g.setColorAt(1, alfa(P["color10"], 0))
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QBrush(g)); p.drawEllipse(c, raio * 2.6, raio * 2.6)
        p.setClipPath(forma)
        base = QRadialGradient(QPointF(c.x(), c.y() + raio * 0.3), raio * 1.3)
        base.setColorAt(0, P["color2"].darker(170)); base.setColorAt(1, P["background"].darker(220))
        p.setBrush(QBrush(base)); p.drawEllipse(c, raio * 1.2, raio * 1.2)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)
        for i, cor in enumerate((P["color10"], P["color2"], P["color14"])):
            orbita = raio * (0.42 + (0.18 if self.estado == "pensando" else 0) - 0.15 * b[i])
            pc = QPointF(c.x() + orbita * math.cos(self.fase[i]), c.y() + orbita * math.sin(self.fase[i]) * 0.85)
            rr = raio * ((0.75, 0.85, 0.38)[i] + 0.5 * b[i])
            lg = QRadialGradient(pc, rr)
            lg.setColorAt(0, alfa(cor, (1, 0.9, 0.75)[i])); lg.setColorAt(0.6, alfa(cor, 0.3)); lg.setColorAt(1, alfa(cor, 0))
            p.setBrush(QBrush(lg)); p.drawEllipse(pc, rr, rr)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        hl = QRadialGradient(QPointF(c.x() - raio * 0.32, c.y() - raio * 0.42), raio * 0.55)
        hl.setColorAt(0, QColor(255, 255, 255, 150)); hl.setColorAt(1, QColor(255, 255, 255, 0))
        p.setBrush(QBrush(hl)); p.drawEllipse(c, raio, raio)
        p.restore()

    def anel(self, p, c, r, t):
        # um anel fino sai da bolinha a cada pico de voz
        if self.nv > 0.3 and (not self.ondas or t - self.ondas[-1][0] > 0.35):
            self.ondas.append((t, self.nv))
        vivos = []
        p.setBrush(Qt.BrushStyle.NoBrush)
        for nasc, forca in self.ondas:
            k = (t - nasc) * VA
            if k < 1:
                vivos.append((nasc, forca))
                p.setPen(QPen(alfa(self.T["onda"], 0.6 * (1 - k) * forca), 1.5))
                rr = r + ease_out(k) * (26 + 40 * forca)
                p.drawEllipse(c, rr, rr)
        self.ondas = vivos

    def conteudo(self, p, rect, a0):
        T = self.T
        esq, y = rect.left() + PAD, rect.top() + PAD - 4
        p.setFont(self.f_perg)
        fm = QFontMetricsF(self.f_perg)
        p.setPen(alfa(T["pergunta"], a0))
        for w_, x, yy, _ in self.l_perg:
            p.drawText(QPointF(esq + x, y + yy + fm.ascent()), w_)
        # pontinho que pulsa com a voz (sua ou da Dii)
        if self.falando or self.nv > 0.02:
            rr = 3.5 + 5 * self.nv
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(alfa(T["ponto"], a0))
            p.drawEllipse(QPointF(rect.right() - PAD + 6, y + fm.ascent() * 0.62), rr, rr)
        # resposta: cada palavra aparece no ritmo da fala
        y += self.h_perg
        p.setFont(self.f_resp)
        fm = QFontMetricsF(self.f_resp)
        prog = (time.monotonic() - self.rev_inicio) * self.rev_vel if self.rev_inicio else -1
        for w_, x, yy, pos in self.l_resp:
            a = max(0, min(1, (prog - pos) / 8)) * a0
            if a <= 0:
                break
            p.setPen(alfa(T["texto"], a))
            p.drawText(QPointF(esq + x, y + yy + fm.ascent()), w_)

    # ---------- trabalho ----------
    def trabalho(self):
        try:
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
                audio = self.gravar(esperar_ate=self.t_estado + self.duracao)
        except Exception as e:
            self.resposta, self.com_voz = f"Erro: {e}", False
            self.muda("pronto")

    def responder(self, audio, primeira):
        self.bandas = [0, 0, 0]
        self.muda("pensando")
        pergunta = transcrever(audio)
        if not pergunta:
            if primeira:
                self.pergunta, self.resposta = "…", "Não ouvi nada. Aperta de novo e fala mais perto do microfone."
            self.com_voz = False
            return self.muda("pronto")   # na conversa, ruído só volta pro cartão anterior
        self.pergunta = pergunta
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
            self.resposta = (j.get("result") or "").strip() or "Sem resposta."
        except ValueError:
            self.resposta = (r.stdout or r.stderr).strip() or "Sem resposta."
        marcou = self.resposta.lower().startswith("[voz]")
        if marcou:
            self.resposta = self.resposta[5:].strip()
        self.com_voz = CFG["voz"] == "sempre" or (CFG["voz"] == "quando_pedir" and marcou)
        self.muda("pronto")
        if self.com_voz:
            self.falar(self.resposta)

    def falar(self, texto):
        if self.fechando:
            return
        self.falando = True
        try:
            from piper import SynthesisConfig
            voz = carrega_voz()
            sr = voz.config.sample_rate
            audio = np.concatenate([c.audio_int16_array for c in voz.synthesize(
                texto.replace("`", "").replace("*", ""), SynthesisConfig(length_scale=CFG["velocidade_voz"]))])
            passo = sr // 20
            env = [bandas(audio[i:i + passo], sr, 2.5) for i in range(0, len(audio) - passo, passo)]
            if self.fechando:
                return
            self.player = subprocess.Popen(["pw-play", "--raw", "--rate", str(sr), "--channels", "1", "--format", "s16", "-"],
                                           stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
            threading.Thread(target=self._toca, args=(audio.tobytes(),), daemon=True).start()
            inicio = time.monotonic()
            self.rev_inicio, self.rev_vel = inicio, self.n_chars / (len(audio) / sr) * 1.06  # texto um tiquinho à frente da voz
            while self.player.poll() is None:
                i = int((time.monotonic() - inicio) * 20)
                self.bandas = env[i] if i < len(env) else [0, 0, 0]
                time.sleep(0.025)
        except Exception:
            self.rev_inicio = self.rev_inicio or time.monotonic()  # sem voz: revela no ritmo padrão
        finally:
            self.bandas, self.falando = [0, 0, 0], False
            self.duracao = max(self.duracao, time.monotonic() - self.t_estado + 3.5)

    def _toca(self, dados):
        try:
            self.player.stdin.write(dados); self.player.stdin.close()
        except OSError:
            pass  # fechou no meio da fala

    def demo(self):
        fim = time.monotonic() + 3.5
        while time.monotonic() < fim and not self.fechando:
            x = time.monotonic()
            env = max(0, math.sin(x * 6)) * random.uniform(0.6, 1)
            self.bandas = [env * (0.6 + 0.4 * math.sin(x * 2)), env * 0.9, env * random.uniform(0.2, 0.8)]
            time.sleep(0.05)
        self.bandas = [0, 0, 0]
        self.muda("pensando")
        time.sleep(2)
        self.pergunta = "quanto tempo leva pra ferver um ovo?"
        self.resposta = ("Uns 6 a 7 minutos pra gema mole e 9 a 10 pra gema dura, contando a partir da água já "
                         "fervendo. Depois joga na água gelada pra parar o cozimento e descascar fácil.")
        self.com_voz = DEMO == "--demo-voz"
        self.muda("pronto")
        if self.com_voz:
            self.falar(self.resposta)

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
                self.bandas = bandas(s, RATE)
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
            self.bandas = [0, 0, 0]
        if esperar_ate and not falou:
            return None
        return bytes(dados)


_whisper, _voz, _lock = None, None, threading.Lock()


def carrega_whisper():
    global _whisper
    with _lock:
        if _whisper is None:
            import ctypes, glob
            from faster_whisper import WhisperModel
            if CFG["usar_gpu"]:
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


def carrega_voz():
    global _voz
    if _voz is None:
        from piper import PiperVoice
        _voz = PiperVoice.load(VOZ)
    return _voz


def transcrever(pcm):
    audio = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768  # array direto, sem passar pelo PyAV
    segs, _ = carrega_whisper().transcribe(audio, language="pt", vad_filter=True, beam_size=1)
    return " ".join(s.text.strip() for s in segs).strip()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    QGuiApplication.setDesktopFileName("bolinha")
    b = Bolha()
    signal.signal(signal.SIGTERM, lambda *_: b.fechar())   # atalho de novo = fecha animado (app.quit direto dava segfault no Wayland)
    b.show()
    app.exec()
    os.unlink(LOCK)
    os._exit(0)   # sai direto: threads de áudio/whisper ainda vivas fariam o Qt dar segfault na desmontagem
