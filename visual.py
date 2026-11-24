"""Desenho da bolinha: estilos de bolinha, de cartão, de entrada, de transformação e de texto.

`Cena` guarda o estado (ouvindo / pensando / pronto, nível do áudio, texto) e pinta tudo num QPainter.
A janela da bolinha e a prévia dos ajustes usam a mesma Cena.
"""
import math
import os
import time

from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import (QBrush, QColor, QConicalGradient, QFont, QFontDatabase, QFontMetricsF, QLinearGradient,
                         QPainter, QPainterPath, QPen, QRadialGradient)

AQUI = os.path.dirname(os.path.abspath(__file__))
PAD = 28
W_EXTRA, H_CENA = 160, 600   # a cena tem a largura do cartão + margem, e altura fixa

BOLINHAS = {"disco": "Disco", "anel": "Anel", "orbe": "Orbe", "gota": "Gota", "barras": "Barras", "pontos": "Pontos",
            "halo": "Halo"}
CARTOES = {"solido": "Sólido", "vidro": "Vidro", "contorno": "Contorno neon", "balao": "Balão", "flutuante": "Só o texto"}
ENTRADAS = {"pop": "Pop", "fade": "Aparecer", "queda": "Cair", "zoom": "Zoom"}
TRANSFORMACOES = {"mola": "Mola", "suave": "Suave", "elastica": "Elástica", "direta": "Direta"}
REVELAR = {"palavra": "Palavra por palavra", "maquina": "Máquina de escrever", "linha": "Linha por linha",
           "inteiro": "Tudo de uma vez"}
COM_ONDAS = {"disco", "anel", "gota", "halo"}   # bolinhas que soltam anéis nos picos de voz
DOCA = {"balao", "flutuante"}                  # cartões em que a bolinha fica encaixada em cima


def registrar_fontes():
    for f in os.listdir(os.path.join(AQUI, "fontes")):
        if f.endswith(".ttf"):
            QFontDatabase.addApplicationFont(os.path.join(AQUI, "fontes", f))


# ---------- curvas ----------
def clamp(x):
    return min(1.0, max(0.0, x))


def ease_out(x):
    return 1 - (1 - clamp(x)) ** 3


def ease_in_out(x):
    x = clamp(x)
    return 4 * x ** 3 if x < .5 else 1 - (-2 * x + 2) ** 3 / 2


def ease_out_back(x, s=1.5):
    x = clamp(x) - 1
    return 1 + x * x * ((s + 1) * x + s)


def elastico(x):
    x = clamp(x)
    if x in (0, 1):
        return x
    return 2 ** (-10 * x) * math.sin((x * 10 - 0.75) * 2 * math.pi / 3) + 1


def quique(x):
    x = clamp(x); n, d = 7.5625, 2.75
    if x < 1 / d:
        return n * x * x
    if x < 2 / d:
        x -= 1.5 / d; return n * x * x + .75
    if x < 2.5 / d:
        x -= 2.25 / d; return n * x * x + .9375
    x -= 2.625 / d; return n * x * x + .984375


# (duração em s, curva da largura, curva da altura)
CURVAS = {
    "mola": (0.65, lambda x: ease_out_back(x, 1.1), ease_out),
    "suave": (0.55, ease_in_out, ease_in_out),
    "elastica": (1.0, elastico, lambda x: ease_out(x * 1.4)),
    "direta": (0.28, ease_out, ease_out),
}


def mix(a, b, t):
    return a + (b - a) * t


def alfa(cor, a):
    c = QColor(cor); c.setAlphaF(clamp(a)); return c


def escuro(cor):
    return QColor(cor).lightnessF() < 0.5


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


class Cena:
    def __init__(self, cfg):
        self.t0 = self.ultimo = time.monotonic()
        self.estado, self.t_estado = "ouvindo", self.t0
        self.bandas = [0.0, 0.0, 0.0]   # alvo (mic ou voz), 0..1 em grave/médio/agudo
        self.bs = [0.0, 0.0, 0.0]       # suavizado
        self.nv = 0.0
        self.fase = [0.0, 2.1, 4.2]
        self.ondas = []
        self.pergunta = self.resposta = ""
        self.rev_inicio, self.rev_vel = None, 45.0
        self.card_saindo = None         # cartão encolhendo de volta pra bolinha
        self.fechando = None
        self.falando = False
        self.card_h = 0
        self.l_perg, self.l_resp, self.h_perg = [], [], 0
        self.usar(cfg)

    # ---------- configuração ----------
    def usar(self, cfg):
        self.c = dict(cfg)
        self.va = max(0.2, float(self.c["velocidade_animacao"]))
        self.R = float(self.c["tamanho"])
        self.CW = float(self.c["largura_cartao"])
        self.W, self.H = self.CW + W_EXTRA, H_CENA
        self.f_resp = QFont(self.c["fonte"]); self.f_resp.setPointSizeF(float(self.c["tamanho_fonte"]))
        self.f_perg = QFont(self.f_resp); self.f_perg.setPointSizeF(float(self.c["tamanho_fonte"]) * 0.73)
        self.cb, self.cd = QColor(self.c["cor_bolinha"]), QColor(self.c["cor_destaque"])
        self.cc, self.ct = QColor(self.c["cor_cartao"]), QColor(self.c["cor_texto"])
        if self.estado == "pronto" or self.card_saindo:
            self._layout()

    @property
    def doca(self):
        return self.c["cartao"] in DOCA

    def _layout(self):
        if self.c["mostrar_pergunta"] and self.pergunta:
            self.l_perg, self.h_perg = quebra(self.pergunta, self.f_perg, self.CW - 2 * PAD - 24, max_linhas=2)
            self.h_perg += 10
        else:
            self.l_perg, self.h_perg = [], 0
        self.l_resp, h_resp = quebra(self.resposta, self.f_resp, self.CW - 2 * PAD)
        livre = self.H - 50 - (self.R * 1.4 + 26 if self.doca else 0)
        self.card_h = min(livre, 2 * PAD - 10 + self.h_perg + h_resp)
        self.n_chars = len(self.resposta) + 1

    # ---------- estado ----------
    def muda(self, estado, agora=None):
        agora = agora or time.monotonic()
        if self.estado == "pronto" and estado == "ouvindo":
            self.card_saindo = agora
        if estado == "pronto":
            self._layout()
            self.rev_inicio = None
        self.estado, self.t_estado = estado, agora

    def revelar(self, inicio=None, chars_por_seg=None):
        """Começa a mostrar as palavras (no ritmo da voz, se vier a velocidade)."""
        self.rev_inicio = inicio or time.monotonic() + 0.35 / self.va
        self.rev_vel = chars_por_seg or 45.0 * self.va

    def fechar(self, agora=None):
        if self.fechando is None:
            self.fechando = agora or time.monotonic()

    def duracao_fechar(self):
        return 0.56 / self.va

    # ---------- pintura ----------
    def pintar(self, p, agora=None):
        agora = agora or time.monotonic()
        dt, self.ultimo = max(0.0, agora - self.ultimo), agora
        t, de = agora - self.t0, agora - self.t_estado
        for i in range(3):
            self.bs[i] += (self.bandas[i] - self.bs[i]) * (0.4 if self.bandas[i] > self.bs[i] else 0.12)
        self.nv = sum(self.bs) / 3
        giro = 3.2 if self.estado == "pensando" else 0.6 + 3 * self.nv
        for i in range(3):
            self.fase[i] += dt * giro * (1 + 0.37 * i) * (-1 if i == 1 else 1)
        va = self.va
        ta, da = t * va, de * va

        fecha_card = fecha_bol = 0.0
        if self.fechando:
            x = (agora - self.fechando) * va
            fecha_card, fecha_bol = ease_in_out(x / 0.3), ease_in_out((x - 0.25) / 0.28)

        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        c = QPointF(self.W / 2, self.H / 2)
        p.save()
        self._entrada(p, c, ta, fecha_bol)

        r_ouve = self.R * (0.62 + 0.5 * self.nv + 0.02 * math.sin(t * 2))
        r_pensa = self.R * (0.5 + 0.05 * math.sin(t * 3.4))
        if self.estado == "ouvindo":
            if self.card_saindo and (agora - self.card_saindo) * va < 0.4:
                k = 1 - ease_in_out((agora - self.card_saindo) * va / 0.4)
                self._pronto(p, c, k, k, r_ouve, t, sem_texto=True)
            else:
                if self.c["bolinha"] in COM_ONDAS:
                    self._ondas(p, c, r_ouve, t)
                self.bolinha(p, c, r_ouve, 1, t)
        elif self.estado == "pensando":
            self.bolinha(p, c, r_pensa, 1, t)
        else:
            dur, cw, ch = CURVAS.get(self.c["transformacao"], CURVAS["mola"])
            x = da / dur
            kw, kh = cw(x) * (1 - fecha_card), ch(x) * (1 - fecha_card)
            self._pronto(p, c, kw, kh, r_pensa, t)
            if kh > 0.75 and self.rev_inicio is None:
                self.revelar()
        p.restore()

    def _entrada(self, p, c, ta, fecha_bol):
        modo = self.c["entrada"]
        esc, op, dy = 1.0, 1.0, 0.0
        if modo == "pop":
            esc = ease_out_back(ta / 0.5, 1.4)
        elif modo == "fade":
            op, esc = ease_out(ta / 0.45), mix(0.9, 1, ease_out(ta / 0.45))
        elif modo == "queda":
            dy, op = -(1 - quique(ta / 0.8)) * 90, ease_out(ta / 0.2)
        elif modo == "zoom":
            esc, op = mix(2.4, 1, ease_out(ta / 0.45)), ease_out(ta / 0.3)
        esc *= 1 - fecha_bol
        op *= 1 - fecha_bol * 0.6
        p.setOpacity(op)
        p.translate(c.x(), c.y() + dy)
        p.scale(max(esc, 0.001), max(esc, 0.001))
        p.translate(-c.x(), -c.y())

    def _pronto(self, p, c, kw, kh, r0, t, sem_texto=False):
        """Bolinha virando cartão (kw/kh de 0 a 1)."""
        cw, chh = self.CW, self.card_h
        if self.doca:
            rd = self.R * 0.7
            gap = 26 if self.c["cartao"] == "balao" else 16
            topo0 = (self.H - (2 * rd + gap + chh)) / 2
            bc = QPointF(c.x(), mix(c.y(), topo0 + rd, ease_in_out(kh * 1.3)))
            rect = QRectF(c.x() - mix(rd, cw / 2, kw), topo0 + 2 * rd + gap, mix(2 * rd, cw, kw), mix(0, chh, kh))
            self.cartao(p, rect, mix(rd, self.c["cantos"], kh), clamp(kh * 2.2), bc)
            self.bolinha(p, bc, mix(r0, rd * (1 + 0.35 * self.nv), clamp(kh * 1.3)), 1, t)
        else:
            w, h = mix(2 * r0, cw, kw), mix(2 * r0, chh, kh)
            rect = QRectF(c.x() - w / 2, c.y() - h / 2, w, h)
            self.cartao(p, rect, mix(r0, self.c["cantos"], kh), ease_out(kh * 2.5), None)
            if kh < 1:
                self.bolinha(p, c, r0 * (1 - kh), 1 - kh, t)
        if not sem_texto and kh > 0.75:
            self.conteudo(p, rect, ease_out((kh - 0.75) / 0.25))

    # ---------- bolinhas ----------
    def bolinha(self, p, c, r, op, t):
        if r < 0.5 or op <= 0.01:
            return
        p.save()
        p.setOpacity(p.opacity() * op)
        getattr(self, "_b_" + self.c["bolinha"], self._b_disco)(p, c, r, t)
        p.restore()

    def _sombra_circ(self, p, c, r):
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(4):
            p.setBrush(QColor(0, 0, 0, 16 - 3 * i))
            p.drawEllipse(QPointF(c.x(), c.y() + 3), r + i, r + i)

    def _b_disco(self, p, c, r, t):
        self._sombra_circ(p, c, r)
        p.setBrush(self.cb)
        if escuro(self.cb):
            p.setPen(QPen(QColor(255, 255, 255, 40), 1))
        p.drawEllipse(c, r, r)

    def _b_anel(self, p, c, r, t):
        p.setBrush(alfa(self.cb, 0.06))
        p.setPen(QPen(self.cb, 2.2 + 4 * self.nv))
        p.drawEllipse(c, r, r)

    def _b_gota(self, p, c, r, t):
        b = self.bs
        amp = (0.05 + 0.25 * self.nv) if self.estado != "pensando" else 0.09
        vel = 1.0 if self.estado != "pensando" else 2.2
        forma = QPainterPath()
        for i in range(121):
            a = 2 * math.pi * i / 120
            rr = r * (1 + amp * (0.55 * math.sin(2 * a + t * 1.9 * vel) * (0.6 + b[0])
                                 + 0.35 * math.sin(3 * a - t * 2.7 * vel) * (0.5 + b[1])
                                 + 0.25 * math.sin(5 * a + t * 3.6 * vel) * (0.4 + b[2])))
            pt = QPointF(c.x() + rr * math.cos(a), c.y() + rr * math.sin(a))
            forma.moveTo(pt) if i == 0 else forma.lineTo(pt)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 30)); p.drawPath(forma.translated(0, 4))
        p.setBrush(self.cb); p.drawPath(forma)
        hl = QRadialGradient(QPointF(c.x() - r * 0.35, c.y() - r * 0.4), r * 0.6)
        hl.setColorAt(0, QColor(255, 255, 255, 70)); hl.setColorAt(1, QColor(255, 255, 255, 0))
        p.setBrush(QBrush(hl)); p.drawPath(forma)

    def _b_orbe(self, p, c, r, t):
        b, nv = self.bs, self.nv
        principal, brilho = self.cb, self.cd
        fundo = principal.darker(400)
        forma = QPainterPath()
        amp = 0.01 + 0.05 * nv
        for i in range(97):
            a = 2 * math.pi * i / 96
            rr = r * (1 + amp * (math.sin(3 * a + t * 2.3) * (0.4 + b[0]) + math.sin(5 * a - t * 3.1) * (0.3 + b[2])))
            pt = QPointF(c.x() + rr * math.cos(a), c.y() + rr * math.sin(a))
            forma.moveTo(pt) if i == 0 else forma.lineTo(pt)
        g = QRadialGradient(c, r * 2.6)
        g.setColorAt(0, alfa(principal, 0.3 + 0.4 * nv)); g.setColorAt(1, alfa(principal, 0))
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QBrush(g)); p.drawEllipse(c, r * 2.6, r * 2.6)
        p.save()
        p.setClipPath(forma)
        base = QRadialGradient(QPointF(c.x(), c.y() + r * 0.3), r * 1.3)
        base.setColorAt(0, principal.darker(250)); base.setColorAt(1, fundo)
        p.setBrush(QBrush(base)); p.drawEllipse(c, r * 1.2, r * 1.2)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)
        for i, cor in enumerate((principal, principal.darker(150), brilho)):
            orbita = r * (0.42 + (0.18 if self.estado == "pensando" else 0) - 0.15 * b[i])
            pc = QPointF(c.x() + orbita * math.cos(self.fase[i]), c.y() + orbita * math.sin(self.fase[i]) * 0.85)
            rr = r * ((0.75, 0.85, 0.38)[i] + 0.5 * b[i])
            lg = QRadialGradient(pc, rr)
            lg.setColorAt(0, alfa(cor, (1, 0.9, 0.75)[i])); lg.setColorAt(0.6, alfa(cor, 0.3)); lg.setColorAt(1, alfa(cor, 0))
            p.setBrush(QBrush(lg)); p.drawEllipse(pc, rr, rr)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        hl = QRadialGradient(QPointF(c.x() - r * 0.32, c.y() - r * 0.42), r * 0.55)
        hl.setColorAt(0, QColor(255, 255, 255, 150)); hl.setColorAt(1, QColor(255, 255, 255, 0))
        p.setBrush(QBrush(hl)); p.drawEllipse(c, r, r)
        p.restore()

    def _b_barras(self, p, c, r, t):
        n, b = 5, self.bs
        lw, gap = r * 0.26, r * 0.15
        total = n * lw + (n - 1) * gap
        g = QRadialGradient(c, r * 2.2)
        g.setColorAt(0, alfa(self.cd, 0.18 + 0.25 * self.nv)); g.setColorAt(1, alfa(self.cd, 0))
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QBrush(g)); p.drawEllipse(c, r * 2.2, r * 2.2)
        nivel = [b[0], (b[0] + b[1]) / 2, b[1], (b[1] + b[2]) / 2, b[2]]
        for i in range(n):
            if self.estado == "pensando":
                h = r * (0.3 + 0.75 * max(0.0, math.sin(t * 6 - i * 0.75)))
            else:
                h = r * (0.3 + 1.6 * nivel[i] * (0.8 + 0.2 * math.sin(t * 9 + i * 2)) + 0.04 * math.sin(t * 2 + i))
            x = c.x() - total / 2 + i * (lw + gap)
            lg = QLinearGradient(0, c.y() - h, 0, c.y() + h)
            lg.setColorAt(0, self.cd); lg.setColorAt(0.5, self.cb); lg.setColorAt(1, self.cd)
            p.setBrush(QBrush(lg))
            p.drawRoundedRect(QRectF(x, c.y() - h, lw, 2 * h), lw / 2, lw / 2)

    def _b_pontos(self, p, c, r, t):
        b = self.bs
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(3):
            x = c.x() + (i - 1) * r * 0.75
            if self.estado == "pensando":
                y, rr = c.y() - r * 0.45 * max(0.0, math.sin(t * 7 - i * 0.9)), r * 0.2
            else:
                y, rr = c.y() - r * 0.25 * b[i], r * (0.2 + 0.2 * b[i])
            p.setBrush(QColor(0, 0, 0, 40)); p.drawEllipse(QPointF(x, y + 2), rr, rr)
            p.setBrush(self.cd if (self.estado == "ouvindo" and b[i] > 0.4) else self.cb)
            p.drawEllipse(QPointF(x, y), rr, rr)

    def _b_halo(self, p, c, r, t):
        giro = t * (220 if self.estado == "pensando" else 50)
        g = QRadialGradient(c, r * 2.1)
        g.setColorAt(0, alfa(self.cd, 0.22 + 0.3 * self.nv)); g.setColorAt(1, alfa(self.cd, 0))
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QBrush(g)); p.drawEllipse(c, r * 2.1, r * 2.1)
        cg = QConicalGradient(c, -giro)
        cg.setColorAt(0, self.cb); cg.setColorAt(0.5, self.cd); cg.setColorAt(1, self.cb)
        esp = r * (0.16 + 0.3 * self.nv)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QBrush(cg), esp))
        p.drawEllipse(c, r - esp / 2, r - esp / 2)

    def _ondas(self, p, c, r, t):
        # um anel fino sai da bolinha a cada pico de voz
        if self.nv > 0.3 and (not self.ondas or t - self.ondas[-1][0] > 0.35):
            self.ondas.append((t, self.nv))
        vivos = []
        p.setBrush(Qt.BrushStyle.NoBrush)
        for nasc, forca in self.ondas:
            k = (t - nasc) * self.va
            if k < 1:
                vivos.append((nasc, forca))
                p.setPen(QPen(alfa(self.cd, 0.6 * (1 - k) * forca), 1.5))
                rr = r + ease_out(k) * (26 + 40 * forca)
                p.drawEllipse(c, rr, rr)
        self.ondas = vivos

    # ---------- cartões ----------
    def cartao(self, p, rect, rad, op, bc):
        if op <= 0.01 or rect.width() < 1:
            return
        estilo = self.c["cartao"]
        p.save()
        p.setOpacity(p.opacity() * op)
        forma = QPainterPath()
        forma.addRoundedRect(rect, rad, rad)
        if estilo == "balao" and bc is not None:
            cauda = QPainterPath()
            x, y = rect.center().x(), rect.top()
            cauda.moveTo(x - 11, y + 2); cauda.lineTo(x, y - 12); cauda.lineTo(x + 11, y + 2); cauda.closeSubpath()
            forma = forma.united(cauda)
        if estilo != "flutuante":
            p.setPen(Qt.PenStyle.NoPen)
            for i in range(6):
                p.setBrush(QColor(0, 0, 0, 13 - 2 * i))
                p.drawPath(forma.translated(0, 4 + i * 0.8))
        if estilo == "solido" or estilo == "balao":
            p.setBrush(self.cc)
            p.setPen(QPen(QColor(255, 255, 255, 22), 1) if escuro(self.cc) else Qt.PenStyle.NoPen)
            p.drawPath(forma)
        elif estilo == "vidro":
            p.setBrush(alfa(self.cc, 0.93)); p.setPen(Qt.PenStyle.NoPen); p.drawPath(forma)
            brilho = QLinearGradient(rect.topLeft(), QPointF(rect.left(), rect.top() + min(rect.height(), 90)))
            brilho.setColorAt(0, QColor(255, 255, 255, 26)); brilho.setColorAt(1, QColor(255, 255, 255, 0))
            p.setBrush(QBrush(brilho)); p.drawPath(forma)
            luz = QRadialGradient(rect.topLeft(), rect.width() * 0.7)
            luz.setColorAt(0, alfa(self.cd, 0.16)); luz.setColorAt(1, alfa(self.cd, 0))
            p.setBrush(QBrush(luz)); p.drawPath(forma)
            p.setBrush(Qt.BrushStyle.NoBrush); p.setPen(QPen(QColor(255, 255, 255, 34), 1)); p.drawPath(forma)
        elif estilo == "contorno":
            p.setBrush(alfa(self.cc, 0.72)); p.setPen(Qt.PenStyle.NoPen); p.drawPath(forma)
            p.setBrush(Qt.BrushStyle.NoBrush)
            for larg, a in ((9, 0.05), (5, 0.12), (2.5, 0.35), (1.2, 1.0)):
                p.setPen(QPen(alfa(self.cd, a), larg)); p.drawPath(forma)
        elif estilo == "flutuante":
            # sem caixa: só uma sombra difusa atrás do texto pra ele ler em qualquer fundo
            fora = rect.adjusted(-50, -40, 50, 40)
            g = QRadialGradient(rect.center(), max(fora.width(), fora.height()) * 0.55)
            g.setColorAt(0, alfa(self.cc, 0.78)); g.setColorAt(0.6, alfa(self.cc, 0.55)); g.setColorAt(1, alfa(self.cc, 0))
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(QBrush(g)); p.drawRect(fora)
        p.restore()

    # ---------- texto ----------
    def cor_ponto(self):
        """Destaque, a não ser que ele suma no fundo do cartão (aí usa a cor do texto)."""
        return self.cd if abs(self.cd.lightnessF() - self.cc.lightnessF()) > 0.25 else self.ct

    def conteudo(self, p, rect, a0):
        esq, y = rect.left() + PAD, rect.top() + PAD - 8
        sombra = self.c["cartao"] == "flutuante"

        def texto(pt, s, cor):
            if sombra:
                p.setPen(QColor(0, 0, 0, int(170 * cor.alphaF())))
                p.drawText(QPointF(pt.x(), pt.y() + 1.5), s)
            p.setPen(cor)
            p.drawText(pt, s)

        p.setFont(self.f_perg)
        fm = QFontMetricsF(self.f_perg)
        for w_, x, yy, _ in self.l_perg:
            texto(QPointF(esq + x, y + yy + fm.ascent()), w_, alfa(self.ct, 0.5 * a0))
        if not self.doca and (self.falando or self.nv > 0.02):   # pontinho que pulsa com a voz
            rr = 3.5 + 5 * self.nv
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(alfa(self.cor_ponto(), a0))
            p.drawEllipse(QPointF(rect.right() - PAD + 6, y + fm.ascent() * 0.62), rr, rr)

        y += self.h_perg
        p.setFont(self.f_resp)
        fm = QFontMetricsF(self.f_resp)
        agora = time.monotonic()
        prog = (agora - self.rev_inicio) * self.rev_vel if self.rev_inicio else -1
        modo = self.c["revelar"]
        base = lambda yy: y + yy + fm.ascent()
        if modo == "inteiro":
            a = ease_out((agora - self.rev_inicio) * self.va / 0.5) if self.rev_inicio else 0
            for w_, x, yy, _ in self.l_resp:
                texto(QPointF(esq + x, base(yy) + 6 * (1 - a)), w_, alfa(self.ct, a * a0))
        elif modo == "linha":
            inicio_linha = {}
            for w_, x, yy, pos in self.l_resp:
                inicio_linha.setdefault(yy, pos)
            for w_, x, yy, pos in self.l_resp:
                a = ease_out((prog - inicio_linha[yy]) / 30)
                if a <= 0:
                    break
                texto(QPointF(esq + x, base(yy) + 10 * (1 - a)), w_, alfa(self.ct, a * a0))
        elif modo == "maquina":
            fim = None
            for w_, x, yy, pos in self.l_resp:
                if prog <= pos:
                    break
                parte = w_ if prog >= pos + len(w_) else w_[:int(prog - pos)]
                texto(QPointF(esq + x, base(yy)), parte, alfa(self.ct, a0))
                fim = (esq + x + fm.horizontalAdvance(parte), base(yy))
            if fim and prog < self.n_chars and int(agora * 2.5) % 2 == 0:
                p.setPen(Qt.PenStyle.NoPen); p.setBrush(alfa(self.cor_ponto(), a0))
                p.drawRect(QRectF(fim[0] + 2, fim[1] - fm.ascent() * 0.8, fm.averageCharWidth() * 0.6, fm.ascent()))
        else:  # palavra
            for w_, x, yy, pos in self.l_resp:
                a = clamp((prog - pos) / 8)
                if a <= 0:
                    break
                texto(QPointF(esq + x, base(yy)), w_, alfa(self.ct, a * a0))


def miniatura(cfg, largura, altura, pergunta, resposta):
    """Imagem estática do cartão pronto (pra galeria de perfis)."""
    from PyQt6.QtGui import QImage
    cena = Cena(cfg)
    cena.pergunta, cena.resposta = pergunta, resposta
    longe = time.monotonic() - 60
    cena.t0 = cena.ultimo = longe
    cena.muda("pronto", longe)
    cena.revelar(longe, 1e6)
    img = QImage(int(largura), int(altura), QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    p = QPainter(img)
    # enquadra o cartão (e a bolinha em cima, no modo doca), não a cena inteira
    fw, fh = (1.5, 2.3) if cena.doca else (1.12, 1.35)
    esc = min(largura / (cena.CW * fw), altura / ((cena.card_h or 120) * fh))
    p.translate(largura / 2, altura / 2); p.scale(esc, esc); p.translate(-cena.W / 2, -cena.H / 2)
    cena.pintar(p)
    p.end()
    return img
