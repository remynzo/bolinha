#!/usr/bin/env python3
"""Bolinha — Ajustes: perfis visuais com prévia ao vivo, e os ajustes de Claude, voz e microfone.
Tudo é salvo sozinho em ~/.config/bolinha/config.json."""
import math, os, random, subprocess, sys, threading, time
import numpy as np
from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QGuiApplication, QIcon, QImage, QLinearGradient, QPainter, QPixmap, QRadialGradient
from PyQt6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QColorDialog, QFontComboBox, QFrame, QGridLayout,
                             QHBoxLayout, QInputDialog, QLabel, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton,
                             QScrollArea, QSizePolicy, QSlider, QStackedWidget, QToolButton, QVBoxLayout, QWidget)

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import config  # noqa: E402
import visual  # noqa: E402

PERGUNTA = "quanto tempo leva pra ferver um ovo?"
RESPOSTA = ("Uns 6 a 7 minutos pra gema mole e 9 a 10 pra gema dura, contando a partir da água já fervendo. "
            "Depois joga na água gelada que descasca fácil.")

# paleta da janela de ajustes
FUNDO, LATERAL, SUPERFICIE, LINHA = "#131316", "#18181c", "#1f1f25", "#2b2b33"
TEXTO, APAGADO = "#ececf1", "#8a8a96"

ESTILO = f"""
* {{ font-family: 'Instrument Sans'; font-size: 10.5pt; color: {TEXTO}; }}
QWidget#raiz, QScrollArea, QScrollArea > QWidget > QWidget {{ background: {FUNDO}; }}
QWidget#lateral {{ background: {LATERAL}; border-right: 1px solid {LINHA}; }}
QLabel#marca {{ font-size: 17pt; font-weight: 600; padding: 4px 0 18px 6px; }}
QPushButton#nav {{ text-align: left; padding: 9px 12px; border: none; border-radius: 9px; color: {APAGADO}; background: transparent; }}
QPushButton#nav:hover {{ color: {TEXTO}; background: {SUPERFICIE}; }}
QPushButton#nav:checked {{ color: {TEXTO}; background: {SUPERFICIE}; }}
QLabel#secao {{ color: {APAGADO}; font-size: 9pt; padding: 14px 0 2px 6px; }}
QLabel#titulo {{ font-size: 15pt; font-weight: 600; }}
QLabel#dica, QLabel#status {{ color: {APAGADO}; font-size: 9pt; }}
QLabel#valor {{ color: {APAGADO}; min-width: 56px; }}
QPushButton, QToolButton {{ background: {SUPERFICIE}; border: 1px solid {LINHA}; border-radius: 9px; padding: 7px 14px; }}
QPushButton:hover, QToolButton:hover {{ border-color: #4a4a55; }}
QPushButton:checked, QToolButton:checked {{ border: 1.5px solid ACENTO; background: #26262e; }}
QPushButton#seg {{ padding: 7px 12px; }}
QToolButton#tile {{ padding: 8px; border-radius: 12px; }}
QPlainTextEdit {{ background: {SUPERFICIE}; border: 1px solid {LINHA}; border-radius: 9px; padding: 6px; }}
QFontComboBox {{ background: {SUPERFICIE}; border: 1px solid {LINHA}; border-radius: 9px; padding: 6px 10px; }}
QFontComboBox QAbstractItemView {{ background: {SUPERFICIE}; selection-background-color: #33333d; }}
QSlider::groove:horizontal {{ height: 4px; background: {LINHA}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: ACENTO; border-radius: 2px; }}
QSlider::handle:horizontal {{ width: 16px; height: 16px; margin: -6px 0; border-radius: 8px; background: {TEXTO}; }}
QCheckBox {{ spacing: 10px; }}
QCheckBox::indicator {{ width: 34px; height: 18px; border-radius: 9px; background: {LINHA}; }}
QCheckBox::indicator:checked {{ background: ACENTO; }}
QProgressBar {{ background: {LINHA}; border: none; border-radius: 3px; }}
QProgressBar::chunk {{ background: ACENTO; border-radius: 3px; }}
QScrollBar:vertical {{ background: transparent; width: 8px; }}
QScrollBar::handle:vertical {{ background: {LINHA}; border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
"""


def rotulo(texto, nome=None):
    l = QLabel(texto)
    if nome:
        l.setObjectName(nome)
    l.setWordWrap(nome in ("dica", None))
    l.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
    return l


# ---------- prévia ao vivo ----------
class Palco(QWidget):
    """Mostra a bolinha do perfil ativo num ciclo: ouvindo → pensando → resposta."""
    def __init__(self, cfg):
        super().__init__()
        self.setMinimumHeight(250)
        self.cfg = cfg
        self.modo = "ciclo"
        self.reiniciar()
        t = QTimer(self, interval=16); t.timeout.connect(self.passo); t.start()

    def reiniciar(self):
        self.cena = visual.Cena(self.cfg)
        self.inicio = time.monotonic()
        if self.modo == "pensando":
            self.cena.muda("pensando")
        elif self.modo == "resposta":
            self._resposta()

    def _resposta(self):
        self.cena.pergunta, self.cena.resposta = PERGUNTA, RESPOSTA
        self.cena.muda("pronto")

    def usar(self, cfg):
        self.cfg = cfg
        self.cena.usar(cfg)

    def fixar(self, modo):
        self.modo = modo
        self.reiniciar()

    def passo(self):
        c, x = self.cena, time.monotonic() - self.inicio
        if self.modo in ("ciclo", "ouvindo") and c.estado == "ouvindo":
            env = max(0, math.sin(x * 6)) * random.uniform(0.6, 1)
            c.bandas = [env * (0.6 + 0.4 * math.sin(x * 2)), env * 0.9, env * random.uniform(0.2, 0.8)]
        if self.modo == "ciclo":
            if x > 3.2 and c.estado == "ouvindo":
                c.bandas = [0, 0, 0]; c.muda("pensando")
            elif x > 4.8 and c.estado == "pensando":
                self._resposta()
            elif x > 11 and c.fechando is None:
                c.fechar()
            elif c.fechando and time.monotonic() - c.fechando > c.duracao_fechar() + 0.4:
                self.reiniciar()
        elif self.modo == "resposta" and x > 9:
            self.reiniciar()   # repete a abertura do cartão
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        # um "desktop" de mentira atrás, pra ver contraste e sombra
        g = QLinearGradient(r.topLeft(), r.bottomRight())
        g.setColorAt(0, QColor("#2a2d3a")); g.setColorAt(0.55, QColor("#1a1b22")); g.setColorAt(1, QColor("#2b2026"))
        p.setPen(QColor(LINHA)); p.setBrush(g)
        p.drawRoundedRect(r, 16, 16)
        luz = QRadialGradient(QPointF(r.width() * 0.8, r.height() * 0.1), r.width() * 0.5)
        luz.setColorAt(0, QColor(255, 255, 255, 18)); luz.setColorAt(1, QColor(255, 255, 255, 0))
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(luz); p.drawRoundedRect(r, 16, 16)
        c = self.cena
        esc = min(self.width() / c.W, self.height() / (c.H * 0.78))
        p.setClipRect(r)
        p.translate(self.width() / 2, self.height() / 2); p.scale(esc, esc); p.translate(-c.W / 2, -c.H / 2)
        c.pintar(p)


def icone_bolinha(cfg, estilo, lado=56):
    cena = visual.Cena({**cfg, "bolinha": estilo})
    cena.bs = cena.bandas = [0.45, 0.6, 0.35]
    cena.nv = 0.47
    img = QImage(lado * 2, lado * 2, QImage.Format.Format_ARGB32_Premultiplied); img.fill(0)
    p = QPainter(img); p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor("#22232b")); p.setPen(Qt.PenStyle.NoPen); p.drawRoundedRect(0, 0, lado * 2, lado * 2, 22, 22)
    cena.bolinha(p, QPointF(lado, lado), lado * 0.42, 1, 1.3)
    p.end()
    return QIcon(QPixmap.fromImage(img))


def icone_cartao(cfg, estilo, w=150, h=96):
    img = visual.miniatura({**cfg, "cartao": estilo}, w * 2, h * 2, "pergunta", "Uma resposta curta pra ver o estilo do cartão.")
    fundo = QImage(w * 2, h * 2, QImage.Format.Format_ARGB32_Premultiplied); fundo.fill(QColor("#22232b"))
    p = QPainter(fundo); p.drawImage(0, 0, img); p.end()
    return QIcon(QPixmap.fromImage(fundo))


# ---------- controles ----------
class Segmentos(QWidget):
    """Botões lado a lado, um marcado."""
    mudou = pyqtSignal(str)

    def __init__(self, opcoes, atual):
        super().__init__()
        lay = QHBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(6)
        self.grupo = QButtonGroup(self)
        self.botoes = {}
        for v, nome in opcoes.items():
            b = QPushButton(nome); b.setObjectName("seg"); b.setCheckable(True)
            b.clicked.connect(lambda _, v=v: self.mudou.emit(v))
            self.grupo.addButton(b); lay.addWidget(b); self.botoes[v] = b
        lay.addStretch()
        self.marcar(atual)

    def marcar(self, v):
        if v in self.botoes:
            self.botoes[v].setChecked(True)


class Tiles(QWidget):
    """Grade de botões com imagem (estilos de bolinha e de cartão)."""
    mudou = pyqtSignal(str)

    def __init__(self, opcoes, colunas, tamanho):
        super().__init__()
        grade = QGridLayout(self); grade.setContentsMargins(0, 0, 0, 0); grade.setSpacing(8)
        self.grupo = QButtonGroup(self)
        self.botoes = {}
        for i, (v, nome) in enumerate(opcoes.items()):
            b = QToolButton(); b.setObjectName("tile"); b.setCheckable(True); b.setText(nome)
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon); b.setIconSize(tamanho)
            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            b.clicked.connect(lambda _, v=v: self.mudou.emit(v))
            self.grupo.addButton(b); grade.addWidget(b, i // colunas, i % colunas); self.botoes[v] = b

    def icones(self, fazer):
        for v, b in self.botoes.items():
            b.setIcon(fazer(v))

    def marcar(self, v):
        if v in self.botoes:
            self.botoes[v].setChecked(True)


class Deslizante(QWidget):
    mudou = pyqtSignal(float)

    def __init__(self, lo, hi, val, passo=1.0, fmt="{:.0f}"):
        super().__init__()
        self.passo, self.fmt = passo, fmt
        lay = QHBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0)
        self.s = QSlider(Qt.Orientation.Horizontal)
        self.s.setRange(round(lo / passo), round(hi / passo))
        self.v = rotulo("", "valor"); self.v.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(self.s, 1); lay.addWidget(self.v)
        self.s.valueChanged.connect(self._mudou)
        self.definir(val)

    def _mudou(self, i):
        x = round(i * self.passo, 3)
        self.v.setText(self.fmt.format(x))
        self.mudou.emit(x)

    def definir(self, val):
        self.s.blockSignals(True); self.s.setValue(round(float(val) / self.passo)); self.s.blockSignals(False)
        self.v.setText(self.fmt.format(float(val)))


class BotaoCor(QPushButton):
    mudou = pyqtSignal(str)

    def __init__(self, hexa):
        super().__init__()
        self.clicked.connect(self.escolher)
        self.definir(hexa)

    def definir(self, hexa):
        self.hexa = hexa
        pm = QPixmap(18, 18); pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor(hexa)); p.setPen(QColor(255, 255, 255, 60)); p.drawEllipse(1, 1, 16, 16); p.end()
        self.setIcon(QIcon(pm)); self.setText(hexa)

    def escolher(self):
        c = QColorDialog.getColor(QColor(self.hexa), self)
        if c.isValid():
            self.definir(c.name()); self.mudou.emit(c.name())


# ---------- janela ----------
class Ajustes(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("raiz")
        self.setWindowTitle("Bolinha — Ajustes")
        self.resize(1000, 720)
        self.tudo = config.carregar_tudo()
        self.mic = None
        self.cores, self.deslizantes, self.segmentos = {}, {}, {}
        self.timer_salvar = QTimer(self); self.timer_salvar.setSingleShot(True); self.timer_salvar.setInterval(350)
        self.timer_salvar.timeout.connect(self.salvar)

        # lateral
        lateral = QWidget(); lateral.setObjectName("lateral"); lateral.setFixedWidth(200)
        lv = QVBoxLayout(lateral); lv.setContentsMargins(14, 18, 14, 14); lv.setSpacing(2)
        lv.addWidget(rotulo("bolinha", "marca"))
        self.pilha = QStackedWidget()
        self.nav = QButtonGroup(self)
        paginas = [("Visual", None), ("Perfis", self.pag_perfis), ("Bolinha", self.pag_bolinha), ("Cartão", self.pag_cartao),
                   ("Animação", self.pag_animacao), ("Comportamento", None), ("Claude", self.pag_claude),
                   ("Voz", self.pag_voz), ("Microfone", self.pag_microfone)]
        self.visuais = set()
        for nome, fazer in paginas:
            if fazer is None:
                lv.addWidget(rotulo(nome, "secao")); continue
            b = QPushButton(nome); b.setObjectName("nav"); b.setCheckable(True)
            i = self.pilha.addWidget(self.rolavel(fazer()))
            if nome in ("Perfis", "Bolinha", "Cartão", "Animação"):
                self.visuais.add(i)
            b.clicked.connect(lambda _, i=i: self.ir(i))
            self.nav.addButton(b, i); lv.addWidget(b)
        lv.addStretch()
        self.status = rotulo("", "status"); lv.addWidget(self.status)

        # palco + controles da prévia
        self.palco = Palco(self.visual())
        self.barra_previa = QWidget()
        bp = QHBoxLayout(self.barra_previa); bp.setContentsMargins(0, 0, 0, 0)
        self.seg_previa = Segmentos({"ciclo": "Ciclo", "ouvindo": "Ouvindo", "pensando": "Pensando", "resposta": "Resposta"}, "ciclo")
        self.seg_previa.mudou.connect(self.palco.fixar)
        testar = QPushButton("Abrir de verdade"); testar.clicked.connect(self.testar)
        bp.addWidget(self.seg_previa, 1); bp.addWidget(testar)

        direita = QVBoxLayout(); direita.setContentsMargins(22, 18, 22, 10); direita.setSpacing(10)
        direita.addWidget(self.palco, 0); direita.addWidget(self.barra_previa); direita.addWidget(self.pilha, 1)
        raiz = QHBoxLayout(self); raiz.setContentsMargins(0, 0, 0, 0); raiz.setSpacing(0)
        raiz.addWidget(lateral); raiz.addLayout(direita, 1)

        self.atualizar_tema()
        self.ir(0)

    # ---------- dados ----------
    def visual(self):
        return self.tudo["perfis"][self.tudo["perfil"]]

    def muda_visual(self, chave, valor):
        self.visual()[chave] = valor
        self.palco.usar(self.visual())
        if chave == "cor_destaque":
            self.atualizar_tema()
        if chave in ("cor_bolinha", "cor_destaque"):
            self.tiles_bolinha.icones(lambda v: icone_bolinha(self.visual(), v))
        if chave in ("cor_cartao", "cor_texto", "cor_destaque", "cantos", "fonte"):
            self.tiles_cartao.icones(lambda v: icone_cartao(self.visual(), v))
        self.agendar()

    def muda_geral(self, chave, valor):
        self.tudo[chave] = valor
        self.agendar()

    def agendar(self):
        self.status.setText("Salvando…")
        self.timer_salvar.start()

    def salvar(self):
        config.salvar(self.tudo)
        self.status.setText("Salvo")

    def atualizar_tema(self):
        acento = self.visual()["cor_destaque"]
        if not 0.12 < QColor(acento).lightnessF() < 0.92:
            acento = "#9db4ff"   # branco/preto puro não funcionam como destaque da janela
        QApplication.instance().setStyleSheet(ESTILO.replace("ACENTO", acento))

    # ---------- navegação ----------
    def ir(self, i):
        self.nav.button(i).setChecked(True)
        self.pilha.setCurrentIndex(i)
        mostrar = i in self.visuais
        self.palco.setVisible(mostrar); self.barra_previa.setVisible(mostrar)
        if i == 0:
            self.montar_galeria()

    def rolavel(self, w):
        s = QScrollArea(); s.setWidgetResizable(True); s.setFrameShape(QFrame.Shape.NoFrame)
        s.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        s.setWidget(w)
        return s

    def pagina(self, titulo, linhas):
        """Página = título + linhas (rótulo, controle, dica opcional)."""
        w = QWidget()
        v = QVBoxLayout(w); v.setContentsMargins(2, 6, 8, 12); v.setSpacing(14)
        if titulo:
            v.addWidget(rotulo(titulo, "titulo"))
        for nome, ctrl, *dica in linhas:
            bloco = QVBoxLayout(); bloco.setSpacing(6)
            if nome:
                bloco.addWidget(rotulo(nome))
            bloco.addWidget(ctrl) if isinstance(ctrl, QWidget) else bloco.addLayout(ctrl)
            if dica:
                bloco.addWidget(rotulo(dica[0], "dica"))
            v.addLayout(bloco)
        v.addStretch()
        return w

    # ---------- perfis ----------
    def pag_perfis(self):
        self.galeria = QGridLayout(); self.galeria.setSpacing(10)
        caixa = QWidget(); caixa.setLayout(self.galeria)
        acoes = QHBoxLayout()
        for nome, f in (("Duplicar", self.duplicar), ("Renomear", self.renomear), ("Restaurar original", self.restaurar),
                        ("Excluir", self.excluir)):
            b = QPushButton(nome); b.clicked.connect(f); acoes.addWidget(b)
        acoes.addStretch()
        return self.pagina(None, [("Cada perfil guarda uma bolinha, um cartão e um jeito de animar. Escolha um e ajuste "
                                   "nas outras abas: as mudanças ficam salvas nele.", caixa), ("", acoes)])

    def montar_galeria(self):
        while self.galeria.count():
            self.galeria.takeAt(0).widget().deleteLater()
        self.grupo_perfis = QButtonGroup(self)
        for i, (nome, v) in enumerate(self.tudo["perfis"].items()):
            b = QToolButton(); b.setObjectName("tile"); b.setCheckable(True); b.setText(nome)
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon); b.setIconSize(QSize(176, 112))
            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            img = visual.miniatura(v, 352, 224, PERGUNTA, "Uns 6 a 7 minutos pra gema mole e 9 a 10 pra gema dura.")
            fundo = QImage(352, 224, QImage.Format.Format_ARGB32_Premultiplied); fundo.fill(QColor("#22232b"))
            p = QPainter(fundo); p.drawImage(0, 0, img); p.end()
            b.setIcon(QIcon(QPixmap.fromImage(fundo)))
            b.setChecked(nome == self.tudo["perfil"])
            b.clicked.connect(lambda _, n=nome: self.escolher_perfil(n))
            self.grupo_perfis.addButton(b); self.galeria.addWidget(b, i // 3, i % 3)

    def escolher_perfil(self, nome):
        self.tudo["perfil"] = nome
        self.carregar_controles()
        self.agendar()

    def carregar_controles(self):
        v = self.visual()
        self.palco.usar(v); self.palco.reiniciar()
        self.atualizar_tema()
        self.tiles_bolinha.marcar(v["bolinha"]); self.tiles_cartao.marcar(v["cartao"])
        self.tiles_bolinha.icones(lambda x: icone_bolinha(v, x)); self.tiles_cartao.icones(lambda x: icone_cartao(v, x))
        for k, w in self.cores.items():
            w.definir(v[k])
        for k, w in self.deslizantes.items():
            w.definir(v[k])
        for k, w in self.segmentos.items():
            w.marcar(v[k])
        self.fonte.blockSignals(True); self.fonte.setCurrentFont(QFont(v["fonte"])); self.fonte.blockSignals(False)
        self.mostrar_perg.blockSignals(True); self.mostrar_perg.setChecked(v["mostrar_pergunta"]); self.mostrar_perg.blockSignals(False)

    def nome_livre(self, base):
        n, i = base, 2
        while n in self.tudo["perfis"]:
            n, i = f"{base} {i}", i + 1
        return n

    def duplicar(self):
        nome = self.nome_livre(self.tudo["perfil"])
        self.tudo["perfis"][nome] = dict(self.visual())
        self.escolher_perfil(nome); self.montar_galeria()

    def renomear(self):
        atual = self.tudo["perfil"]
        if atual in config.PERFIS_PRONTOS:
            return QMessageBox.information(self, "Renomear", "Os perfis que vêm com a bolinha não mudam de nome. Duplique pra criar o seu.")
        novo, ok = QInputDialog.getText(self, "Renomear perfil", "Nome:", text=atual)
        novo = novo.strip()
        if ok and novo and novo not in self.tudo["perfis"]:
            self.tudo["perfis"] = {(novo if k == atual else k): v for k, v in self.tudo["perfis"].items()}
            self.escolher_perfil(novo); self.montar_galeria()

    def restaurar(self):
        atual = self.tudo["perfil"]
        if atual not in config.PERFIS_PRONTOS:
            return QMessageBox.information(self, "Restaurar", "Só os perfis que vêm com a bolinha têm versão original.")
        self.tudo["perfis"][atual] = config.perfil_pronto(atual)
        self.escolher_perfil(atual); self.montar_galeria()

    def excluir(self):
        atual = self.tudo["perfil"]
        if atual in config.PERFIS_PRONTOS:
            return QMessageBox.information(self, "Excluir", "Os perfis que vêm com a bolinha não podem ser excluídos.")
        if QMessageBox.question(self, "Excluir perfil", f"Excluir o perfil “{atual}”?") == QMessageBox.StandardButton.Yes:
            del self.tudo["perfis"][atual]
            self.escolher_perfil("Minimal"); self.montar_galeria()

    # ---------- bolinha, cartão, animação ----------
    def linha_cores(self, pares):
        cores = QHBoxLayout()
        for chave, nome in pares:
            b = BotaoCor(self.visual()[chave]); b.mudou.connect(lambda x, k=chave: self.muda_visual(k, x))
            self.cores[chave] = b
            col = QVBoxLayout(); col.addWidget(rotulo(nome, "dica")); col.addWidget(b); cores.addLayout(col)
        cores.addStretch()
        return cores

    def deslizante(self, chave, lo, hi, passo, fmt):
        d = Deslizante(lo, hi, self.visual()[chave], passo, fmt)
        d.mudou.connect(lambda x: self.muda_visual(chave, int(x) if passo >= 1 else x))
        self.deslizantes[chave] = d
        return d

    def pag_bolinha(self):
        v = self.visual()
        self.tiles_bolinha = Tiles(visual.BOLINHAS, 4, QSize(56, 56))
        self.tiles_bolinha.mudou.connect(lambda x: self.muda_visual("bolinha", x))
        self.tiles_bolinha.icones(lambda x: icone_bolinha(v, x)); self.tiles_bolinha.marcar(v["bolinha"])
        return self.pagina(None, [
            ("Estilo", self.tiles_bolinha),
            ("", self.linha_cores((("cor_bolinha", "Cor"), ("cor_destaque", "Destaque"))),
             "O destaque colore os anéis que saem com a sua voz, o brilho e o pontinho do cartão."),
            ("Tamanho", self.deslizante("tamanho", 16, 60, 1, "{:.0f} px"))])

    def pag_cartao(self):
        v = self.visual()
        self.tiles_cartao = Tiles(visual.CARTOES, 3, QSize(150, 96))
        self.tiles_cartao.mudou.connect(lambda x: self.muda_visual("cartao", x))
        self.tiles_cartao.icones(lambda x: icone_cartao(v, x)); self.tiles_cartao.marcar(v["cartao"])
        self.fonte = QFontComboBox(); self.fonte.setCurrentFont(QFont(v["fonte"]))
        self.fonte.currentFontChanged.connect(lambda f: self.muda_visual("fonte", f.family()))
        self.mostrar_perg = QCheckBox("Mostrar minha pergunta em cima da resposta"); self.mostrar_perg.setChecked(v["mostrar_pergunta"])
        self.mostrar_perg.toggled.connect(lambda x: self.muda_visual("mostrar_pergunta", x))
        return self.pagina(None, [
            ("Estilo", self.tiles_cartao), ("", self.linha_cores((("cor_cartao", "Fundo"), ("cor_texto", "Texto")))),
            ("Cantos", self.deslizante("cantos", 0, 40, 1, "{:.0f} px")),
            ("Largura", self.deslizante("largura_cartao", 300, 760, 10, "{:.0f} px")),
            ("Fonte", self.fonte), ("Tamanho do texto", self.deslizante("tamanho_fonte", 10, 26, 0.5, "{:.1f} pt")),
            ("", self.mostrar_perg)])

    def pag_animacao(self):
        linhas = []
        for chave, nome, opcoes, dica in (
                ("entrada", "Como ela aparece", visual.ENTRADAS, None),
                ("transformacao", "Como vira cartão", visual.TRANSFORMACOES, None),
                ("revelar", "Como o texto aparece", visual.REVELAR, "Quando ela fala em voz alta, o texto acompanha o ritmo da voz.")):
            s = Segmentos(opcoes, self.visual()[chave])
            s.mudou.connect(lambda x, k=chave: (self.muda_visual(k, x), self.palco.reiniciar()))
            self.segmentos[chave] = s
            linhas.append((nome, s, dica) if dica else (nome, s))
        linhas.append(("Velocidade", self.deslizante("velocidade_animacao", 0.5, 2.0, 0.1, "{:.1f}×")))
        return self.pagina(None, linhas)

    # ---------- comportamento ----------
    def chave(self, nome, chave):
        c = QCheckBox(nome); c.setChecked(self.tudo[chave])
        c.toggled.connect(lambda x: self.muda_geral(chave, x))
        return c

    def seg_geral(self, chave, opcoes):
        s = Segmentos(opcoes, self.tudo[chave]); s.mudou.connect(lambda x: self.muda_geral(chave, x))
        return s

    def desl_geral(self, chave, lo, hi, passo, fmt, conv=lambda x: x, desconv=lambda x: x):
        d = Deslizante(lo, hi, desconv(self.tudo[chave]), passo, fmt)
        d.mudou.connect(lambda x: self.muda_geral(chave, conv(x)))
        return d

    def pag_claude(self):
        instr = QPlainTextEdit(self.tudo["instrucoes_extras"]); instr.setFixedHeight(90)
        instr.setPlaceholderText("Ex.: me chama pelo meu apelido; responde com gírias; prefiro respostas de uma frase…")
        instr.textChanged.connect(lambda: self.muda_geral("instrucoes_extras", instr.toPlainText()))
        return self.pagina("Claude", [
            ("Modelo", self.seg_geral("modelo_claude", {"haiku": "Haiku", "sonnet": "Sonnet", "opus": "Opus"}),
             "Haiku responde em ~2s. Sonnet pensa melhor (~5s). Opus é o mais capaz e o mais lento."),
            ("", self.chave("Deixar o Claude agir no PC", "permitir_acoes"),
             "Abrir apps, rodar comandos… No modo automático do Claude Code, que bloqueia o que for destrutivo."),
            ("", self.chave("Seguir ouvindo com o cartão aberto", "continuar_ouvindo"),
             "Fale de novo enquanto a resposta está na tela e vira a próxima pergunta, com o contexto da conversa."),
            ("Cartão fica aberto mais", self.desl_geral("tempo_extra_cartao", 0, 30, 0.5, "{:.1f} s")),
            ("Instruções extras", instr)])

    def pag_voz(self):
        ouvir = QPushButton("Ouvir"); ouvir.clicked.connect(self.ouvir_voz)
        vel = self.desl_geral("velocidade_voz", 0.6, 1.6, 0.05, "{:.2f}×", conv=lambda x: round(1 / x, 3), desconv=lambda x: 1 / x)
        linha = QHBoxLayout(); linha.addWidget(vel, 1); linha.addWidget(ouvir)
        return self.pagina("Voz", [
            ("Responder falando", self.seg_geral("voz", {"nunca": "Nunca", "quando_pedir": "Quando eu pedir", "sempre": "Sempre"}),
             "“Quando eu pedir”: ela fala se você disser algo como “lê pra mim” ou “responde em voz alta”."),
            ("Velocidade da fala", linha)])

    def pag_microfone(self):
        self.medidor = QProgressBar(); self.medidor.setRange(0, 3000); self.medidor.setTextVisible(False); self.medidor.setFixedHeight(6)
        self.nivel_txt = rotulo("", "valor")
        self.btn_mic = QPushButton("Testar microfone"); self.btn_mic.setCheckable(True); self.btn_mic.toggled.connect(self.testar_mic)
        linha = QHBoxLayout(); linha.addWidget(self.medidor, 1); linha.addWidget(self.nivel_txt); linha.addWidget(self.btn_mic)
        return self.pagina("Microfone", [
            ("Transcrição", self.seg_geral("modelo_whisper", {"small": "Small", "medium": "Medium", "large-v3-turbo": "Large v3 turbo"}),
             "Large v3 turbo entende melhor; Small carrega mais rápido em PC sem placa de vídeo."),
            ("", self.chave("Transcrever na placa de vídeo", "usar_gpu")),
            ("Limiar de fala", self.desl_geral("silencio_rms", 50, 3000, 25, "{:.0f}"),
             "Ligue o teste e fale: o limiar tem que ficar acima do silêncio e abaixo da sua voz. "
             "Se ela te corta no meio, diminua; se não para de ouvir, aumente."),
            ("", linha),
            ("Pausa pra encerrar", self.desl_geral("silencio_seg", 0.3, 3.0, 0.1, "{:.1f} s")),
            ("Tempo máximo de fala", self.desl_geral("max_seg", 5, 60, 1, "{:.0f} s", conv=int))])

    # ---------- ações ----------
    def testar(self):
        self.salvar()
        subprocess.Popen([sys.executable, os.path.join(AQUI, "bolinha.py"), "--demo"], start_new_session=True)

    def ouvir_voz(self):
        vel = self.tudo["velocidade_voz"]

        def tocar():
            try:
                from piper import PiperVoice, SynthesisConfig
                v = PiperVoice.load(os.path.join(config.PASTA_DADOS, "voz", "pt_BR-dii.onnx"))
                pcm = b"".join(c.audio_int16_bytes for c in v.synthesize(
                    "Oi! É assim que eu vou falar com você.", SynthesisConfig(length_scale=vel)))
                subprocess.run(["pw-play", "--raw", "--rate", str(v.config.sample_rate), "--channels", "1",
                                "--format", "s16", "-"], input=pcm, stderr=subprocess.DEVNULL)
            except Exception as e:
                print("voz:", e, file=sys.stderr)
        threading.Thread(target=tocar, daemon=True).start()

    def testar_mic(self, ligado):
        if not ligado:
            if self.mic:
                self.mic.terminate(); self.mic = None
            self.medidor.setValue(0); self.nivel_txt.setText(""); self.btn_mic.setText("Testar microfone")
            return
        self.btn_mic.setText("Parar")
        self.mic = subprocess.Popen(["pw-record", "--raw", "--rate", "16000", "--channels", "1", "--format", "s16", "-"],
                                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self.nivel = 0

        def ler(proc):
            while proc.poll() is None:
                b = proc.stdout.read(1600)
                if not b:
                    break
                s = np.frombuffer(b, np.int16).astype(np.float32)
                self.nivel = int(math.sqrt(float((s ** 2).mean()) or 0))
        threading.Thread(target=ler, args=(self.mic,), daemon=True).start()

        def atualizar():
            if not self.mic:
                return
            self.medidor.setValue(min(3000, self.nivel))
            self.nivel_txt.setText(f"{self.nivel} · {'fala' if self.nivel > self.tudo['silencio_rms'] else 'silêncio'}")
            QTimer.singleShot(60, atualizar)
        atualizar()

    def closeEvent(self, e):
        if self.mic:
            self.mic.terminate()
        if self.timer_salvar.isActive():
            self.salvar()
        super().closeEvent(e)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    QGuiApplication.setDesktopFileName("bolinha-ajustes")
    visual.registrar_fontes()
    app.setFont(QFont("Instrument Sans", 10))
    w = Ajustes()
    if "--pagina" in sys.argv:   # abre direto numa aba (0 = Perfis … 6 = Microfone)
        w.ir(int(sys.argv[sys.argv.index("--pagina") + 1]))
    w.show()
    sys.exit(app.exec())
