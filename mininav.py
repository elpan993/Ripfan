import sys
from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QApplication, QMainWindow, QToolBar, QLineEdit, QMessageBox
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage

# True = bloquea TODAS las descargas sin preguntar
# False = pregunta antes de cada descarga
BLOQUEAR_TODO = False


class MiniNav(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MiniNav")
        self.resize(1100, 750)

        # Perfil sin nombre = modo privado: no guarda cookies ni sesiones en disco
        self.perfil = QWebEngineProfile(self)
        self.perfil.downloadRequested.connect(self.descarga)

        self.web = QWebEngineView()
        self.web.setPage(QWebEnginePage(self.perfil, self.web))
        self.setCentralWidget(self.web)

        barra = QToolBar()
        self.addToolBar(barra)
        for txt, fn in (("◀", self.web.back), ("▶", self.web.forward), ("⟳", self.web.reload)):
            a = QAction(txt, self)
            a.triggered.connect(fn)
            barra.addAction(a)

        self.url = QLineEdit()
        self.url.returnPressed.connect(self.ir)
        barra.addWidget(self.url)
        self.web.urlChanged.connect(lambda u: self.url.setText(u.toString()))

        self.web.setUrl(QUrl("https://duckduckgo.com"))

    def ir(self):
        t = self.url.text().strip()
        if " " in t or "." not in t:
            q = QUrl.toPercentEncoding(t).data().decode()
            self.web.setUrl(QUrl("https://duckduckgo.com/?q=" + q))
        else:
            self.web.setUrl(QUrl.fromUserInput(t))

    def descarga(self, d):
        if BLOQUEAR_TODO:
            d.cancel()
            return
        r = QMessageBox.question(
            self, "Descarga detectada",
            f"¿Permitir esta descarga?\n\nArchivo: {d.downloadFileName()}\nDesde: {d.url().host()}"
        )
        if r == QMessageBox.StandardButton.Yes:
            d.accept()
        else:
            d.cancel()


app = QApplication(sys.argv)
ventana = MiniNav()
ventana.show()
sys.exit(app.exec())
