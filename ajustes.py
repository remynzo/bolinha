#!/usr/bin/env python3
"""Bolinha — Ajustes: janela pra configurar a bolinha (salva em ~/.config/bolinha/config.json)."""
import math, os, subprocess, sys, threading
import numpy as np
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication
from PyQt6.QtWidgets import (QApplication, QCheckBox, QColorDialog, QComboBox, QDoubleSpinBox, QFontComboBox,
                             QFormLayout, QGroupBox, QHBoxLayout, QLabel, QPlainTextEdit, QProgressBar, QPushButton,
                             QScrollArea, QSpinBox, QVBoxLayout, QWidget)

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import config  # noqa: E402

ESTILOS = [("claro", "Claro"), ("escuro", "Escuro"), ("anel", "Anel"), ("orbe", "Orbe (cores do papel de parede)")]
MODELOS = [("haiku", "Haiku (rápido, ~2s)"), ("sonnet", "Sonnet (mais esperto, ~5s)"), ("opus", "Opus (o mais capaz)")]
VOZES = [("nunca", "Nunca"), ("quando_pedir", "Só quando eu pedir"), ("sempre", "Sempre")]
WHISPER = [("small", "Small (leve)"), ("medium", "Medium"), ("large-v3-turbo", "Large v3 turbo (entende melhor)")]


def combo(opcoes, atual):
    c = QComboBox()
    for v, rotulo in opcoes:
        c.addItem(rotulo, v)
    c.setCurrentIndex(max(0, [v for v, _ in opcoes].index(atual) if atual in [v for v, _ in opcoes] else 0))
    return c


def spin(lo, hi, val, passo=1, sufixo="", decimais=None):
    s = QDoubleSpinBox() if decimais is not None else QSpinBox()
    if decimais is not None:
        s.setDecimals(decimais)
    s.setRange(lo, hi); s.setSingleStep(passo); s.setValue(val); s.setSuffix(sufixo)
    return s


def dica(texto):
    l = QLabel(texto); l.setWordWrap(True)
    l.setStyleSheet("color: palette(placeholder-text); font-size: 9pt;")
    return l


class Ajustes(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Bolinha — Ajustes")
        self.resize(560, 760)
        self.c = config.carregar()
        self.mic = None
        c = self.c

        # aparência
        self.estilo = combo(ESTILOS, c["estilo"])
        self.cor = QPushButton(); self.cor.clicked.connect(self.escolher_cor); self.pinta_cor(c["cor_destaque"])
        self.tamanho = spin(16, 60, c["tamanho"], sufixo=" px")
        self.largura = spin(300, 800, c["largura_cartao"], 10, " px")
        self.fonte = QFontComboBox(); self.fonte.setCurrentFont(QFont(c["fonte"]))
        self.tam_fonte = spin(10, 24, c["tamanho_fonte"], 0.5, " pt", 1)
        self.vel_anim = spin(0.5, 2.0, c["velocidade_animacao"], 0.1, "×", 1)
        self.mostrar_perg = QCheckBox("Mostrar minha pergunta no cartão"); self.mostrar_perg.setChecked(c["mostrar_pergunta"])

        # claude
        self.modelo = combo(MODELOS, c["modelo_claude"])
        self.acoes = QCheckBox("Deixar o Claude agir no PC"); self.acoes.setChecked(c["permitir_acoes"])
        self.continuar = QCheckBox("Seguir ouvindo com o cartão aberto"); self.continuar.setChecked(c["continuar_ouvindo"])
        self.extra_cartao = spin(0, 30, c["tempo_extra_cartao"], 0.5, " s", 1)
        self.instrucoes = QPlainTextEdit(c["instrucoes_extras"]); self.instrucoes.setFixedHeight(70)
        self.instrucoes.setPlaceholderText("Ex.: me chama pelo meu apelido; responde com gírias; prefiro respostas de uma frase…")

        # voz
        self.voz = combo(VOZES, c["voz"])
        self.vel_voz = spin(0.6, 1.6, round(1 / c["velocidade_voz"], 2), 0.05, "×", 2)
        ouvir = QPushButton("Ouvir"); ouvir.clicked.connect(self.ouvir_voz)

        # microfone
        self.whisper = combo(WHISPER, c["modelo_whisper"])
        self.gpu = QCheckBox("Transcrever na placa de vídeo"); self.gpu.setChecked(c["usar_gpu"])
        self.limiar = spin(50, 4000, c["silencio_rms"], 25)
        self.pausa = spin(0.3, 3.0, c["silencio_seg"], 0.1, " s", 1)
        self.max_seg = spin(5, 60, c["max_seg"], 1, " s")
        self.medidor = QProgressBar(); self.medidor.setRange(0, 4000); self.medidor.setTextVisible(False); self.medidor.setFixedHeight(8)
        self.nivel_txt = QLabel("")
        self.btn_mic = QPushButton("Testar microfone"); self.btn_mic.setCheckable(True); self.btn_mic.toggled.connect(self.testar_mic)

        corpo = QVBoxLayout()
        corpo.addWidget(self.grupo("Aparência", [
            ("Estilo", self.estilo), ("Cor de destaque", self.cor), ("Tamanho da bolinha", self.tamanho),
            ("Largura do cartão", self.largura), ("Fonte", self.fonte), ("Tamanho do texto", self.tam_fonte),
            ("Velocidade das animações", self.vel_anim), (None, self.mostrar_perg)]))
        corpo.addWidget(self.grupo("Claude", [
            ("Modelo", self.modelo), (None, self.acoes),
            (None, dica("Abrir apps, rodar comandos… No modo automático do Claude Code, que bloqueia o que for destrutivo.")),
            (None, self.continuar), ("Cartão fica aberto mais", self.extra_cartao), ("Instruções extras", self.instrucoes)]))
        linha_voz = QHBoxLayout(); linha_voz.addWidget(self.vel_voz, 1); linha_voz.addWidget(ouvir)
        corpo.addWidget(self.grupo("Voz", [("Responder falando", self.voz), ("Velocidade da fala", linha_voz)]))
        linha_mic = QHBoxLayout(); linha_mic.addWidget(self.medidor, 1); linha_mic.addWidget(self.nivel_txt); linha_mic.addWidget(self.btn_mic)
        corpo.addWidget(self.grupo("Microfone", [
            ("Transcrição", self.whisper), (None, self.gpu), ("Limiar de fala", self.limiar),
            (None, dica("Fale com o teste ligado: o limiar tem que ficar acima do silêncio e abaixo da sua voz. "
                        "Se ela te corta no meio, diminua; se não para de ouvir, aumente.")),
            (None, linha_mic), ("Pausa pra encerrar", self.pausa), ("Tempo máximo de fala", self.max_seg)]))
        corpo.addWidget(self.grupo("Atalho", [(None, dica(
            "Super + C abre a bolinha (e fecha, se apertar de novo). O atalho fica no Hyprland; "
            "o README mostra a linha pra trocar a tecla."))]))
        corpo.addStretch()

        conteudo = QWidget(); conteudo.setLayout(corpo)
        rolagem = QScrollArea(); rolagem.setWidgetResizable(True); rolagem.setWidget(conteudo)
        rolagem.setFrameShape(QScrollArea.Shape.NoFrame)
        rolagem.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.rolagem = rolagem
        for w in conteudo.findChildren(QComboBox):
            w.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            w.setMinimumContentsLength(8)
        for w in conteudo.findChildren((QComboBox, QSpinBox, QDoubleSpinBox)):
            w.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            w.installEventFilter(self)

        padrao = QPushButton("Restaurar padrão"); padrao.clicked.connect(self.restaurar)
        testar = QPushButton("Ver como fica"); testar.clicked.connect(self.testar)
        self.salvar_btn = QPushButton("Salvar"); self.salvar_btn.setDefault(True); self.salvar_btn.clicked.connect(self.salvar)
        self.status = QLabel("")
        botoes = QHBoxLayout()
        botoes.addWidget(padrao); botoes.addWidget(self.status, 1); botoes.addWidget(testar); botoes.addWidget(self.salvar_btn)

        raiz = QVBoxLayout(self)
        raiz.addWidget(rolagem, 1)
        raiz.addLayout(botoes)

    def eventFilter(self, obj, ev):
        # rolar a página por cima de um campo não muda o valor (só se ele estiver focado)
        if ev.type() == ev.Type.Wheel and not obj.hasFocus():
            QApplication.sendEvent(self.rolagem.verticalScrollBar(), ev)
            return True
        return super().eventFilter(obj, ev)

    def grupo(self, titulo, linhas):
        g = QGroupBox(titulo)
        f = QFormLayout(g)
        f.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        for rotulo, w in linhas:
            if rotulo is None:
                f.addRow(w)
            else:
                f.addRow(rotulo, w)
        return g

    def pinta_cor(self, hexa):
        self.cor_hex = hexa
        txt = "#000" if QColor(hexa).lightness() > 140 else "#fff"
        self.cor.setText(hexa)
        self.cor.setStyleSheet(f"background:{hexa}; color:{txt}; border-radius:6px; padding:6px;")

    def escolher_cor(self):
        c = QColorDialog.getColor(QColor(self.cor_hex), self, "Cor de destaque")
        if c.isValid():
            self.pinta_cor(c.name())

    def ler(self):
        return {
            "estilo": self.estilo.currentData(), "cor_destaque": self.cor_hex, "tamanho": self.tamanho.value(),
            "largura_cartao": self.largura.value(), "fonte": self.fonte.currentFont().family(),
            "tamanho_fonte": self.tam_fonte.value(), "velocidade_animacao": self.vel_anim.value(),
            "mostrar_pergunta": self.mostrar_perg.isChecked(), "modelo_claude": self.modelo.currentData(),
            "permitir_acoes": self.acoes.isChecked(), "instrucoes_extras": self.instrucoes.toPlainText(),
            "continuar_ouvindo": self.continuar.isChecked(), "tempo_extra_cartao": self.extra_cartao.value(),
            "voz": self.voz.currentData(), "velocidade_voz": round(1 / self.vel_voz.value(), 3),
            "modelo_whisper": self.whisper.currentData(), "usar_gpu": self.gpu.isChecked(),
            "silencio_rms": self.limiar.value(), "silencio_seg": self.pausa.value(), "max_seg": self.max_seg.value(),
        }

    def salvar(self):
        config.salvar(self.ler())
        self.status.setText("Salvo.")
        QTimer.singleShot(2500, lambda: self.status.setText(""))

    def restaurar(self):
        config.salvar(dict(config.PADRAO))
        app = QApplication.instance()
        app.janela = Ajustes()  # reabre com os padrões
        app.janela.show()
        self.close()

    def testar(self):
        self.salvar()
        subprocess.Popen([sys.executable, os.path.join(AQUI, "bolinha.py"), "--demo"], start_new_session=True)

    def ouvir_voz(self):
        vel = 1 / self.vel_voz.value()

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
            self.medidor.setValue(min(4000, self.nivel))
            acima = self.nivel > self.limiar.value()
            self.nivel_txt.setText(f"{self.nivel:>4} {'fala' if acima else 'silêncio'}")
            QTimer.singleShot(60, atualizar)
        atualizar()

    def closeEvent(self, e):
        if self.mic:
            self.mic.terminate()
        super().closeEvent(e)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    QGuiApplication.setDesktopFileName("bolinha-ajustes")
    QFontDatabase.addApplicationFont(os.path.join(AQUI, "fontes", "InstrumentSans.ttf"))
    app.setFont(QFont("Instrument Sans", 11))
    app.setStyleSheet("QWidget { font-family: 'Instrument Sans'; font-size: 11pt; }")  # o tema do sistema pode forçar outra fonte
    w = Ajustes()
    w.show()
    sys.exit(app.exec())
