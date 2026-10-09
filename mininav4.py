import sys
import os
import json
import shutil
import getpass
from PyQt6.QtCore import QUrl, QTimer
from PyQt6.QtGui import QAction, QKeySequence, QCursor
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QToolBar, QLineEdit, QMessageBox, QTabWidget,
    QDialog, QVBoxLayout, QListWidget, QPushButton, QMenu,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import (
    QWebEngineProfile, QWebEnginePage, QWebEngineSettings,
    QWebEngineUrlRequestInterceptor,
)

# ---------------- Configuración ----------------
BLOQUEAR_DESCARGAS = False   # True = bloquea TODAS las descargas sin preguntar
MAX_PESTANAS = 8             # límite de pestañas abiertas (ahorra memoria)
MAX_HISTORIAL = 200
PERMITIR_WEBGL = False       # True = habilita WebGL (mapas 3D, juegos); gasta más
INICIO = "https://duckduckgo.com"

CARPETA = os.path.join(os.path.expanduser("~"), ".mininav")
RUTA_BLOQ = os.path.join(CARPETA, "bloqueados.txt")  # opcional: tu propia lista
ARCHIVOS = ("historial.json", "favoritos.json")

# Menos procesos y menos tráfico en segundo plano del motor Chromium
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
    "--renderer-process-limit=3 --disable-background-networking "
    "--disable-breakpad --no-pings --disable-features=Translate,MediaRouter"
)

# Lista base chica de publicidad/rastreo/malvertising conocido.
# Para más cobertura, pegá una lista (formato hosts o un dominio por línea) en bloqueados.txt
BLOQUEADOS_BASE = {
    "doubleclick.net", "googlesyndication.com", "googleadservices.com",
    "adservice.google.com", "adnxs.com", "taboola.com", "outbrain.com",
    "popads.net", "propellerads.com", "adsterra.com", "exoclick.com",
    "trafficjunky.com", "juicyads.com", "popcash.net", "clickadu.com",
    "hilltopads.net", "adcash.com", "revcontent.com", "mgid.com",
    "criteo.com", "scorecardresearch.com", "quantserve.com",
    "2mdn.net", "amazon-adsystem.com", "moatads.com", "adsrvr.org",
}


def cargar_bloqueados():
    dominios = set(BLOQUEADOS_BASE)
    if os.path.exists(RUTA_BLOQ):
        with open(RUTA_BLOQ, encoding="utf-8", errors="ignore") as f:
            for linea in f:
                linea = linea.split("#")[0].strip().lower()
                if not linea:
                    continue
                d = linea.split()[-1]
                if "." in d and d not in ("0.0.0.0", "127.0.0.1", "localhost"):
                    dominios.add(d)
    return dominios


def leer_json(ruta, defecto):
    try:
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return defecto


def guardar_json(ruta, datos):
    try:
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False)
    except Exception:
        pass


# ---------------- Perfil = usuario de Windows ----------------
def usuario_windows():
    try:
        u = getpass.getuser()
    except Exception:
        u = ""
    u = "".join(c for c in u if c.isalnum() or c in " -_.")[:40].strip(" .")
    return u or "usuario"


def carpeta_usuario(nombre):
    destino = os.path.join(CARPETA, "usuarios", nombre)
    if not os.path.isdir(destino):
        os.makedirs(destino, exist_ok=True)
        # trae datos de versiones anteriores, si existen
        for origen in (os.path.join(CARPETA, "perfiles", "Principal"), CARPETA):
            if any(os.path.exists(os.path.join(origen, f)) for f in ARCHIVOS):
                for f in ARCHIVOS:
                    src = os.path.join(origen, f)
                    if os.path.exists(src):
                        try:
                            shutil.copy2(src, os.path.join(destino, f))
                        except Exception:
                            pass
                break
    return destino


ESTILO = """
QMainWindow, QDialog { background:#1e1f24; color:#e6e6e6; }
QToolBar { background:#26272d; border:0; spacing:4px; padding:3px; }
QToolBar QToolButton { color:#e6e6e6; padding:3px 8px; border-radius:6px; font-size:15px; }
QToolBar QToolButton:hover { background:#3a3b43; }
QLineEdit { background:#1a1b1f; color:#f0f0f0; border:1px solid #3a3b43;
            border-radius:11px; padding:4px 11px; selection-background-color:#4f7cff; }
QLineEdit:focus { border:1px solid #4f7cff; }
QTabWidget::pane { border:0; }
QTabBar::tab { background:#26272d; color:#b8b8c0; padding:6px 12px; margin-right:2px;
               border-top-left-radius:7px; border-top-right-radius:7px;
               min-width:80px; max-width:180px; }
QTabBar::tab:selected { background:#33343c; color:#ffffff; }
QTabBar::tab:hover { background:#2d2e35; }
QMenu { background:#26272d; color:#e6e6e6; border:1px solid #3a3b43; }
QMenu::item { padding:6px 22px; }
QMenu::item:selected { background:#4f7cff; }
QListWidget { background:#1a1b1f; color:#e6e6e6; border:1px solid #3a3b43; }
QListWidget::item:selected { background:#4f7cff; }
QMessageBox { background:#1e1f24; }
QLabel { color:#e6e6e6; }
QPushButton { background:#33343c; color:#fff; border:0; border-radius:6px; padding:6px 14px; }
QPushButton:hover { background:#4f7cff; }
"""


class Filtro(QWebEngineUrlRequestInterceptor):
    """Corta las conexiones a dominios de la lista antes de que carguen."""

    def __init__(self, dominios):
        super().__init__()
        self.dominios = dominios

    def interceptRequest(self, info):
        host = info.requestUrl().host().lower()
        while host:
            if host in self.dominios:
                info.block(True)
                return
            if "." not in host:
                break
            host = host.split(".", 1)[1]


class Pagina(QWebEnginePage):
    def __init__(self, perfil, ventana, parent=None):
        super().__init__(perfil, parent)
        self.ventana = ventana

    def createWindow(self, tipo):
        # Solo permite abrir pestañas; bloquea ventanas emergentes (pop-ups)
        if tipo in (QWebEnginePage.WebWindowType.WebBrowserTab,
                    QWebEnginePage.WebWindowType.WebBrowserBackgroundTab):
            v = self.ventana.nueva_pestana(None)
            return v.page() if v else None
        return None


class Vista(QWebEngineView):
    def __init__(self, perfil, ventana):
        super().__init__()
        self.setPage(Pagina(perfil, ventana, self))


class Lista(QDialog):
    """Ventana simple para favoritos e historial."""

    def __init__(self, parent, titulo, entradas, abrir, texto_btn, accion_btn):
        super().__init__(parent)
        self.setWindowTitle(titulo)
        self.resize(600, 420)
        self.entradas = entradas
        lay = QVBoxLayout(self)
        self.lista = QListWidget()
        lay.addWidget(self.lista)
        for e in entradas:
            self.lista.addItem(f"{e['titulo'][:55]}  —  {e['url']}")

        def abrir_item(it):
            abrir(self.entradas[self.lista.row(it)]["url"])
            self.close()

        self.lista.itemDoubleClicked.connect(abrir_item)
        b = QPushButton(texto_btn)
        b.clicked.connect(lambda: accion_btn(self))
        lay.addWidget(b)


class MiniNav(QMainWindow):
    def __init__(self):
        super().__init__()
        self.resize(1150, 750)
        self.setWindowTitle("MiniNav")
        self.setStyleSheet(ESTILO)

        # Datos del usuario de Windows actual
        self.usuario = usuario_windows()
        carpeta = carpeta_usuario(self.usuario)
        self.ruta_hist = os.path.join(carpeta, "historial.json")
        self.ruta_fav = os.path.join(carpeta, "favoritos.json")
        self.historial = leer_json(self.ruta_hist, [])
        self.favoritos = leer_json(self.ruta_fav, [])

        # Guarda el historial en diferido (no escribe en disco en cada página)
        self.t_hist = QTimer(self)
        self.t_hist.setSingleShot(True)
        self.t_hist.setInterval(3000)
        self.t_hist.timeout.connect(self.guardar_hist)

        # Perfil web sin nombre = privado: cookies y sesiones no se guardan en disco
        self.perfil = QWebEngineProfile(self)
        self.perfil.setUrlRequestInterceptor(Filtro(cargar_bloqueados()))
        self.perfil.downloadRequested.connect(self.descarga)
        s = self.perfil.settings()
        A = QWebEngineSettings.WebAttribute
        s.setAttribute(A.WebGLEnabled, PERMITIR_WEBGL)
        s.setAttribute(A.PluginsEnabled, False)
        s.setAttribute(A.ScrollAnimatorEnabled, False)
        s.setAttribute(A.AutoLoadIconsForPage, False)
        s.setAttribute(A.WebRTCPublicInterfacesOnly, True)
        s.setAttribute(A.FullScreenSupportEnabled, True)

        self.pestanas = QTabWidget()
        self.pestanas.setDocumentMode(True)
        self.pestanas.setTabsClosable(True)
        self.pestanas.setMovable(True)
        self.pestanas.tabCloseRequested.connect(self.cerrar_pestana)
        self.pestanas.currentChanged.connect(self.cambio_pestana)
        self.setCentralWidget(self.pestanas)

        self.crear_barra()
        self.nueva_pestana(INICIO)

    # ---------- interfaz ----------
    def accion(self, texto, fn, atajo=None, tip=None):
        a = QAction(texto, self)
        a.triggered.connect(lambda _=False: fn())
        if atajo:
            a.setShortcut(QKeySequence(atajo))
        if tip:
            a.setToolTip(tip)
        return a

    def crear_barra(self):
        self.barra = QToolBar()
        self.barra.setMovable(False)
        self.addToolBar(self.barra)
        self.barra.addAction(self.accion("◀", lambda: self.actual().back(), "Alt+Left", "Atrás"))
        self.barra.addAction(self.accion("▶", lambda: self.actual().forward(), "Alt+Right", "Adelante"))
        self.barra.addAction(self.accion("⟳", lambda: self.actual().reload(), "F5", "Recargar"))
        self.barra_url = QLineEdit()
        self.barra_url.setPlaceholderText("Buscá o escribí una dirección")
        self.barra_url.returnPressed.connect(self.ir)
        self.barra.addWidget(self.barra_url)
        self.accion_fav = self.accion("☆", self.alternar_favorito, "Ctrl+D", "Favorito (Ctrl+D)")
        self.barra.addAction(self.accion_fav)
        self.barra.addAction(self.accion("＋", lambda: self.nueva_pestana(INICIO), "Ctrl+T", "Nueva pestaña (Ctrl+T)"))

        a_fav = self.accion("Favoritos    Ctrl+B", self.ver_favoritos, "Ctrl+B")
        a_hist = self.accion("Historial    Ctrl+H", self.ver_historial, "Ctrl+H")
        menu = QMenu(self)
        menu.addAction(a_fav)
        menu.addAction(a_hist)
        self.addAction(a_fav)
        self.addAction(a_hist)
        self.barra.addAction(self.accion("⋮", lambda: menu.popup(QCursor.pos()), None, "Menú"))

        # atajos sin botón
        self.addAction(self.accion("", lambda: self.cerrar_pestana(self.pestanas.currentIndex()), "Ctrl+W"))
        self.addAction(self.accion("", lambda: (self.barra_url.setFocus(), self.barra_url.selectAll()), "Ctrl+L"))

    # ---------- pestañas ----------
    def actual(self):
        return self.pestanas.currentWidget()

    def nueva_pestana(self, url=INICIO):
        if self.pestanas.count() >= MAX_PESTANAS:
            return None
        vista = Vista(self.perfil, self)
        i = self.pestanas.addTab(vista, "Nueva pestaña")
        self.pestanas.setCurrentIndex(i)
        vista.titleChanged.connect(lambda t, v=vista: self.cambio_titulo(v, t))
        vista.urlChanged.connect(lambda u, v=vista: self.cambio_url(v, u))
        vista.loadFinished.connect(lambda ok, v=vista: self.carga_lista(v, ok))
        vista.page().fullScreenRequested.connect(self.pantalla_completa)
        if url:
            vista.setUrl(QUrl(url))
        return vista

    def cerrar_pestana(self, i):
        if self.pestanas.count() <= 1:
            self.close()
            return
        w = self.pestanas.widget(i)
        self.pestanas.removeTab(i)
        w.deleteLater()

    def cambio_pestana(self, _):
        v = self.actual()
        if not v:
            return
        v.page().setLifecycleState(QWebEnginePage.LifecycleState.Active)
        self.barra_url.setText(v.url().toString())
        self.actualizar_estrella()
        QTimer.singleShot(1500, self.congelar_inactivas)

    def congelar_inactivas(self):
        """Pausa las pestañas en segundo plano para ahorrar CPU y RAM (salvo si suenan)."""
        actual = self.actual()
        for i in range(self.pestanas.count()):
            v = self.pestanas.widget(i)
            if v is not actual and not v.page().recentlyAudible():
                v.page().setLifecycleState(QWebEnginePage.LifecycleState.Frozen)

    def cambio_titulo(self, v, t):
        i = self.pestanas.indexOf(v)
        if i >= 0:
            self.pestanas.setTabText(i, (t or "Sin título")[:20])
            self.pestanas.setTabToolTip(i, t)
        if v is self.actual():
            self.setWindowTitle(t or "MiniNav")

    def cambio_url(self, v, u):
        if v is self.actual():
            self.barra_url.setText(u.toString())
            self.actualizar_estrella()

    def pantalla_completa(self, req):
        req.accept()
        on = req.toggleOn()
        self.barra.setVisible(not on)
        self.pestanas.tabBar().setVisible(not on)
        if on:
            self.showFullScreen()
        else:
            self.showNormal()

    # ---------- navegación ----------
    def ir(self):
        t = self.barra_url.text().strip()
        if not t:
            return
        if " " in t or "." not in t:
            q = QUrl.toPercentEncoding(t).data().decode()
            self.actual().setUrl(QUrl("https://duckduckgo.com/?q=" + q))
        else:
            self.actual().setUrl(QUrl.fromUserInput(t))
        self.actual().setFocus()

    def abrir(self, url):
        self.actual().setUrl(QUrl(url))

    # ---------- historial ----------
    def carga_lista(self, v, ok):
        u = v.url().toString()
        if not ok or not u.startswith(("http://", "https://")):
            return
        if self.historial and self.historial[-1]["url"] == u:
            return
        self.historial.append({"titulo": v.title() or u, "url": u})
        del self.historial[:-MAX_HISTORIAL]
        self.t_hist.start()

    def guardar_hist(self):
        guardar_json(self.ruta_hist, self.historial)

    def ver_historial(self):
        entradas = list(reversed(self.historial))
        Lista(self, "Historial", entradas, self.abrir, "Borrar todo el historial",
              self.borrar_historial).exec()

    def borrar_historial(self, dlg):
        self.historial = []
        self.guardar_hist()
        dlg.entradas.clear()
        dlg.lista.clear()

    # ---------- favoritos ----------
    def ver_favoritos(self):
        Lista(self, "Favoritos", list(self.favoritos), self.abrir,
              "Quitar el seleccionado", self.quitar_favorito).exec()

    def quitar_favorito(self, dlg):
        i = dlg.lista.currentRow()
        if i < 0:
            return
        url = dlg.entradas[i]["url"]
        self.favoritos = [f for f in self.favoritos if f["url"] != url]
        guardar_json(self.ruta_fav, self.favoritos)
        dlg.entradas.pop(i)
        dlg.lista.takeItem(i)
        self.actualizar_estrella()

    def alternar_favorito(self):
        v = self.actual()
        u = v.url().toString()
        if not u.startswith(("http://", "https://")):
            return
        if any(f["url"] == u for f in self.favoritos):
            self.favoritos = [f for f in self.favoritos if f["url"] != u]
        else:
            self.favoritos.append({"titulo": v.title() or u, "url": u})
        guardar_json(self.ruta_fav, self.favoritos)
        self.actualizar_estrella()

    def actualizar_estrella(self):
        v = self.actual()
        if not v:
            return
        u = v.url().toString()
        self.accion_fav.setText("★" if any(f["url"] == u for f in self.favoritos) else "☆")

    # ---------- descargas ----------
    def descarga(self, d):
        if BLOQUEAR_DESCARGAS:
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

    def closeEvent(self, e):
        if self.t_hist.isActive():
            self.t_hist.stop()
            self.guardar_hist()
        e.accept()


app = QApplication(sys.argv)
ventana = MiniNav()
ventana.show()
sys.exit(app.exec())
