import sys
import os
import json
import shutil
import getpass
import time
import math
import wave
import struct
import random
import base64
import html
from collections import deque
from urllib.parse import unquote, quote
from PyQt6.QtCore import Qt, QUrl, QTimer, QDateTime, QEvent
from PyQt6.QtGui import QAction, QKeySequence, QCursor, QImage
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QToolBar, QLineEdit, QMessageBox, QTabWidget,
    QDialog, QVBoxLayout, QListWidget, QPushButton, QMenu, QFileDialog, QCheckBox,
)
from PyQt6.QtNetwork import QNetworkCookie
from PyQt6.QtMultimedia import QSoundEffect
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import (
    QWebEngineProfile, QWebEnginePage, QWebEngineSettings,
    QWebEngineUrlRequestInterceptor, QWebEngineScript, QWebEngineDownloadRequest,
)

# ======================= Configuración =======================
NOMBRE = "Rifpan"
BLOQUEAR_DESCARGAS = False   # True = bloquea TODAS las descargas sin preguntar
MAX_PESTANAS = 8             # límite de pestañas abiertas (ahorra memoria)
MAX_HISTORIAL = 200
PERMITIR_WEBGL = False       # True = habilita WebGL (mapas 3D, juegos); gasta más
SONIDOS = True               # False = silencio total
ESPERA_CIERRE_MS = 700       # tiempo que suena el "daño" antes de cerrar
BUSCADOR = "https://lite.duckduckgo.com/lite/?q="
INICIO = "rifpan:inicio"     # escritorio estilo Windows 98
BASE_INICIO = "https://rifpan.local/"

# Cookies: solo estos dominios se guardan en disco, y duran VIDA_SESION_DIAS días.
# Todo lo demás se olvida al cerrar.
PERSISTIR = ("youtube.com", "google.com", "google.com.ar")
VIDA_SESION_DIAS = 3

CARPETA = os.path.join(os.path.expanduser("~"), ".rifpan")
CARPETA_VIEJA = os.path.join(os.path.expanduser("~"), ".mininav")
CARPETA_SONIDOS = os.path.join(CARPETA, "sonidos")
CARPETA_FONDOS = os.path.join(CARPETA, "fondos")
FONDO_SEGUNDOS = 15          # cada cuánto cambia el fondo del escritorio
EXT_IMAGEN = (".jpg", ".jpeg", ".jfif", ".png", ".webp", ".gif", ".bmp")
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
    for ruta in (os.path.join(CARPETA, "bloqueados.txt"),
                 os.path.join(CARPETA_VIEJA, "bloqueados.txt")):
        if not os.path.exists(ruta):
            continue
        with open(ruta, encoding="utf-8", errors="ignore") as f:
            for linea in f:
                linea = linea.split("#")[0].strip().lower()
                if not linea:
                    continue
                d = linea.split()[-1]
                if "." in d and d not in ("0.0.0.0", "127.0.0.1", "localhost"):
                    dominios.add(d)
        break
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


def listar_fondos():
    try:
        return sorted(f for f in os.listdir(CARPETA_FONDOS) if f.lower().endswith(EXT_IMAGEN))
    except Exception:
        return []


# ======================= Perfil = usuario de Windows =======================
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
        # trae favoritos e historial de versiones anteriores, si existen
        for origen in (os.path.join(CARPETA_VIEJA, "usuarios", nombre),
                       os.path.join(CARPETA_VIEJA, "perfiles", "Principal"),
                       CARPETA_VIEJA):
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


# ==SINTE== sonidos generados por código (originales, sin archivos externos)
TASA = 22050


def escribir_wav(ruta, muestras):
    with wave.open(ruta, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(TASA)
        w.writeframes(b"".join(
            struct.pack("<h", max(-32767, min(32767, int(m * 32767)))) for m in muestras))


def sintetizar_maullido(base, dur):
    """Un 'miau' simple: el tono sube y baja, con vibrato y una vocal que se mueve."""
    n = int(TASA * dur)
    fase = 0.0
    salida = []
    for i in range(n):
        t = i / TASA
        x = i / n
        f = base * (0.8 + 0.7 * math.sin(math.pi * x ** 0.8)) + 12 * math.sin(2 * math.pi * 6 * t)
        fase += 2 * math.pi * f / TASA
        formante = 900 + 1100 * math.sin(math.pi * x)
        s = 0.0
        for k in range(1, 11):
            g = math.exp(-((k * f - formante) / 700) ** 2) + 0.15 / k
            s += g * math.sin(k * fase)
        env = min(1.0, x / 0.12) * (1 - x) ** 0.7
        salida.append(0.45 * env * s / 2.5)
    return salida


def sintetizar_dano():
    """Tono descendente tipo 'auch' (sonido propio, genérico)."""
    n = int(TASA * 0.35)
    fase = 0.0
    salida = []
    for i in range(n):
        x = i / n
        f = 520 * (1 - x) ** 1.5 + 90
        fase += 2 * math.pi * f / TASA
        s = 1.0 if math.sin(fase) > 0 else -1.0
        salida.append(0.3 * s * (1 - x))
    return salida


def preparar_sonidos(carpeta):
    """Devuelve (rutas_maullidos, ruta_dano). Si ponés tus propios .wav, usa esos."""
    os.makedirs(carpeta, exist_ok=True)
    propios = sorted(
        os.path.join(carpeta, f) for f in os.listdir(carpeta)
        if f.lower().endswith(".wav") and not f.startswith("_") and f.lower() != "dano.wav")
    if not propios:
        for i, (base, dur) in enumerate(((600, 0.45), (760, 0.38), (900, 0.30)), 1):
            ruta = os.path.join(carpeta, f"_gen_miau{i}.wav")
            if not os.path.exists(ruta):
                escribir_wav(ruta, sintetizar_maullido(base, dur))
            propios.append(ruta)
    dano = os.path.join(carpeta, "dano.wav")
    if not os.path.exists(dano):
        dano = os.path.join(carpeta, "_gen_dano.wav")
        if not os.path.exists(dano):
            escribir_wav(dano, sintetizar_dano())
    return propios, dano
# ==FIN-SINTE==


class Sonidos:
    def __init__(self):
        self.maullidos = []
        self.dano = None
        self.ultimo = 0.0
        if not SONIDOS:
            return
        try:
            rutas, dano = preparar_sonidos(CARPETA_SONIDOS)
            self.maullidos = [self._efecto(r, 0.6) for r in rutas]
            self.dano = self._efecto(dano, 0.8)
        except Exception:
            pass

    @staticmethod
    def _efecto(ruta, volumen):
        e = QSoundEffect()
        e.setSource(QUrl.fromLocalFile(ruta))
        e.setVolume(volumen)
        return e

    def maullar(self):
        if not self.maullidos:
            return
        t = time.monotonic()
        if t - self.ultimo < 0.15:
            return
        self.ultimo = t
        random.choice(self.maullidos).play()

    def golpe(self):
        if self.dano:
            self.dano.play()


# ======================= Escritorio estilo Windows 98 =======================
PLANTILLA_INICIO = """<!DOCTYPE html><html><head><meta charset="utf-8"><title>Rifpan</title>
<style>
*{box-sizing:border-box}
html,body{margin:0;height:100%;overflow:hidden;background:#008080;
 font:11px Tahoma,"MS Sans Serif",Arial,sans-serif;color:#000;user-select:none}
#esc{position:absolute;top:0;left:0;right:0;bottom:30px}
.icono{position:absolute;width:78px;text-align:center;text-decoration:none;color:#fff;padding:3px 2px;
 touch-action:none;-webkit-user-drag:none;cursor:default}
.icono span{display:block;font-size:30px;line-height:36px}
.icono b{font-weight:normal;display:inline-block;margin-top:3px;padding:1px 2px;text-shadow:1px 1px #000}
.icono:hover b,.icono:focus b{background:#000080;outline:1px dotted #ff0}
.vent{position:absolute;left:50%;top:44%;transform:translate(-50%,-50%);width:360px;background:#c0c0c0;
 border:2px solid;border-color:#fff #404040 #404040 #fff;box-shadow:1px 1px 0 #000;padding:2px}
.tit{background:linear-gradient(90deg,#000080,#1084d0);color:#fff;font-weight:bold;padding:3px 5px;
 display:flex;justify-content:space-between;cursor:move;touch-action:none}
.tit i{cursor:pointer;font-style:normal;background:#c0c0c0;color:#000;border:1px solid;
 border-color:#fff #404040 #404040 #fff;padding:0 5px;font-weight:bold}
.cuerpo{padding:12px}
.cuerpo p{margin:0 0 10px}
input[type=text]{width:100%;padding:4px;font:12px Tahoma,Arial;background:#fff;border:2px solid;
 border-color:#404040 #fff #fff #404040;margin-bottom:8px}
button{font:11px Tahoma,Arial;padding:4px 18px;background:#c0c0c0;border:2px solid;
 border-color:#fff #404040 #404040 #fff;cursor:pointer}
button:active{border-color:#404040 #fff #fff #404040}
#barra{position:absolute;left:0;right:0;bottom:0;height:30px;background:#c0c0c0;
 border-top:2px solid #fff;display:flex;align-items:center;padding:2px 3px;gap:6px}
#inicio{font-weight:bold;font-size:12px;padding:3px 10px}
.sepv{width:2px;height:20px;border-left:1px solid #808080;border-right:1px solid #fff}
.tarea{padding:3px 12px;border:2px solid;border-color:#404040 #fff #fff #404040;background:#d8d8d8;font-weight:bold}
#reloj{margin-left:auto;padding:3px 10px;border:1px solid;border-color:#808080 #fff #fff #808080}
#menu{display:none;position:absolute;left:3px;bottom:30px;width:210px;background:#c0c0c0;
 border:2px solid;border-color:#fff #404040 #404040 #fff;box-shadow:1px 1px 0 #000;
 padding:2px 2px 2px 28px;z-index:9}
#menu:before{content:"Rifpan";position:absolute;left:2px;top:2px;bottom:2px;width:24px;background:linear-gradient(0deg,#000080,#1084d0);
 color:#fff;font:bold 15px Tahoma,Arial;writing-mode:vertical-rl;transform:rotate(180deg);text-align:left;padding:6px 2px}
#menu a{display:block;padding:7px 8px;color:#000;text-decoration:none;font-size:12px;position:relative}
#menu a:hover,.sub:hover>span{background:#000080;color:#fff}
.sep{height:2px;border-top:1px solid #808080;border-bottom:1px solid #fff;margin:3px 0}
.sub{position:relative}
.sub>span{display:block;padding:7px 8px;font-size:12px}
.subm{display:none;position:absolute;left:100%;top:-2px;width:200px;background:#c0c0c0;
 border:2px solid;border-color:#fff #404040 #404040 #fff;padding:2px}
.sub:hover .subm{display:block}
.fondo{position:absolute;top:0;left:0;right:0;bottom:30px;background-size:cover;
 background-position:center;opacity:0;transition:opacity 1s}
.fondo.ver{opacity:1}
</style></head><body>
<div class="fondo" id="f1"></div><div class="fondo" id="f2"></div>
<div id="esc">
 <a class="icono" data-id="buscar" href="https://lite.duckduckgo.com/lite/"><span>🔍</span><b>Buscar</b></a>
 <a class="icono" data-id="youtube" href="https://www.youtube.com"><span>▶️</span><b>YouTube</b></a>
 <a class="icono" data-id="historial" href="rifpan://historial"><span>🕘</span><b>Historial</b></a>
 %%FAVS%%
 <div class="vent" id="vent">
  <div class="tit" id="tit"><span>🐱 Bienvenido a Rifpan</span><i id="cerrar">x</i></div>
  <div class="cuerpo">
   <p>¿Qué querés buscar hoy?</p>
   <form action="https://lite.duckduckgo.com/lite/" method="get">
    <input type="text" name="q" placeholder="Escribí y apretá Enter" autofocus>
    <button type="submit">Buscar</button>
   </form>
  </div>
 </div>
</div>
<div id="menu">
 <a href="https://lite.duckduckgo.com/lite/">🔍 Buscar</a>
 <a href="https://www.youtube.com">▶️ YouTube</a>
 <div class="sep"></div>
 <div class="sub"><span>⭐ Favoritos ▸</span><div class="subm">%%MENUFAVS%%</div></div>
 <a href="rifpan://historial">🕘 Historial</a>
 <div class="sep"></div>
 <a href="rifpan://reordenar">🧹 Reordenar íconos</a>
 <a href="rifpan://fondos">🖼️ Elegir fondos...</a>
 <a href="rifpan://sinfondos">🚫 Quitar fondos</a>
 <a href="rifpan://cerrar">⏻ Apagar Rifpan...</a>
</div>
<div id="barra">
 <button id="inicio">🐱 Inicio</button>
 <div class="sepv"></div>
 <div class="tarea">Rifpan</div>
 <div id="reloj"></div>
</div>
<script>
var m=document.getElementById('menu');
document.getElementById('inicio').onclick=function(e){e.stopPropagation();
 m.style.display=m.style.display==='block'?'none':'block'};
document.onclick=function(){m.style.display='none'};
function hora(){document.getElementById('reloj').textContent=
 new Date().toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})}
hora();setInterval(hora,20000);

var POS=%%POS%%;
var ic=document.querySelectorAll('.icono'),vent=document.getElementById('vent');
function colocar(el,x,y){
 el.style.left=Math.max(0,Math.min(innerWidth-el.offsetWidth,x))+'px';
 el.style.top=Math.max(0,Math.min(innerHeight-30-el.offsetHeight,y))+'px';}
function guardar(){
 var d={};
 ic.forEach(function(el){d[el.dataset.id]={x:el.offsetLeft,y:el.offsetTop}});
 d.ventana={x:vent.offsetLeft,y:vent.offsetTop};
 location.href='rifpan://guardar?d='+encodeURIComponent(JSON.stringify(d));}
function arrastrar(el,asa){
 asa.addEventListener('pointerdown',function(e){
  if(e.button!==0)return;
  if(e.target.id==='cerrar'){vent.style.display='none';return;}
  var dx=e.clientX-el.offsetLeft,dy=e.clientY-el.offsetTop,movio=false;
  asa.setPointerCapture(e.pointerId);
  function mover(ev){
   var x=ev.clientX-dx,y=ev.clientY-dy;
   if(Math.abs(x-el.offsetLeft)+Math.abs(y-el.offsetTop)>3)movio=true;
   if(movio)colocar(el,x,y);}
  function soltar(){
   asa.removeEventListener('pointermove',mover);
   asa.removeEventListener('pointerup',soltar);
   if(movio){el.dataset.mov='1';guardar();
    setTimeout(function(){el.dataset.mov=''},50);}}
  asa.addEventListener('pointermove',mover);
  asa.addEventListener('pointerup',soltar);
 });
 el.addEventListener('click',function(e){
  if(el.dataset.mov){e.preventDefault();}});
}
var filas=Math.max(1,Math.floor((innerHeight-50)/92));
ic.forEach(function(el,i){
 var p=POS[el.dataset.id]||{x:10+Math.floor(i/filas)*88,y:10+(i%filas)*92};
 el.draggable=false;colocar(el,p.x,p.y);arrastrar(el,el);});
var r=vent.getBoundingClientRect();vent.style.transform='none';
var pv=POS.ventana||{x:r.left,y:r.top};colocar(vent,pv.x,pv.y);
arrastrar(vent,document.getElementById('tit'));

var FONDOS=%%FONDOS%%,SEG=%%SEG%%;
if(FONDOS.length){
 var capas=[document.getElementById('f1'),document.getElementById('f2')],ix=0,cap=0;
 function poner(i){var c=capas[cap];c.style.backgroundImage='url("'+FONDOS[i]+'")';
  c.classList.add('ver');capas[1-cap].classList.remove('ver');cap=1-cap;}
 poner(0);
 if(FONDOS.length>1)setInterval(function(){ix=(ix+1)%FONDOS.length;
  var im=new Image();im.onload=function(){poner(ix)};im.src=FONDOS[ix];},SEG*1000);
}
</script></body></html>"""


ESTILO = """
QMainWindow, QDialog { background:#f0f4fa; color:#1e395b; }
QToolBar { background:qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #e8f0fa, stop:0.5 #d6e4f5, stop:0.51 #c6d9ef, stop:1 #d9e6f6);
           border:0; border-bottom:1px solid #8fa8c8; spacing:4px; padding:3px; }
QToolBar QToolButton { color:#1e395b; padding:3px 8px; border:1px solid transparent; border-radius:4px; font-size:15px; }
QToolBar QToolButton:hover { border:1px solid #7da2ce;
    background:qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #f4f9ff, stop:0.5 #dcebfc, stop:0.51 #c1dcfc, stop:1 #e5f1fd); }
QToolBar QToolButton:pressed { border:1px solid #5b8cc0;
    background:qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #cfe3f8, stop:1 #b2d3f5); }
QLineEdit { background:#ffffff; color:#000000; border:1px solid #8ea6c4; border-radius:3px;
            padding:3px 8px; selection-background-color:#3399ff; selection-color:#ffffff; }
QLineEdit:focus { border:1px solid #3d7bd1; }
QTabWidget::pane { border:0; }
QTabBar { background:#c6d9ef; }
QTabBar::tab { background:qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #eef4fb, stop:1 #d3e1f2); color:#1e395b;
               border:1px solid #8fa8c8; border-bottom:none; padding:5px 12px; margin-right:2px; margin-top:3px;
               border-top-left-radius:4px; border-top-right-radius:4px; min-width:80px; max-width:180px; }
QTabBar::tab:selected { background:qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #ffffff, stop:1 #eaf2fb);
                        color:#000000; margin-top:1px; }
QTabBar::tab:hover:!selected { background:qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #f4f9ff, stop:1 #dcebfc); }
QMenu { background:#f0f0f0; color:#000000; border:1px solid #979797; padding:2px; }
QMenu::item { padding:5px 24px; border:1px solid transparent; border-radius:3px; }
QMenu::item:selected { background:qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #f1f7fe, stop:1 #d3e6fa);
                       border:1px solid #7da2ce; color:#000000; }
QMenu::separator { height:1px; background:#d0d0d0; margin:3px 6px; }
QListWidget { background:#ffffff; color:#000000; border:1px solid #8ea6c4; }
QListWidget::item:selected { background:qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #e5f1fd, stop:1 #c5def8); color:#000000; }
QMessageBox { background:#f0f0f0; }
QLabel { color:#1e395b; }
QPushButton { background:qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #f6f6f6, stop:0.5 #ebebeb, stop:0.51 #dddddd, stop:1 #cfcfcf);
              color:#000000; border:1px solid #707070; border-radius:3px; padding:5px 16px; }
QPushButton:hover { border:1px solid #3c7fb1;
    background:qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #eaf6fd, stop:0.5 #d9f0fc, stop:0.51 #bee6fd, stop:1 #a7d9f5); }
QPushButton:pressed { background:#c4e5f6; border:1px solid #2c628b; }
QCheckBox { color:#1e395b; spacing:8px; padding:5px; }
QToolTip { background:#ffffe1; color:#000000; border:1px solid #767676; }
"""


JS_BUSQUEDA = r"""
(function(){
if(location.hostname!=='lite.duckduckgo.com')return;
var inp=document.querySelector('input[name=q]');
var q=(inp&&inp.value)||new URLSearchParams(location.search).get('q')||'';
var e=encodeURIComponent(q);
var css=[
'body{background:#fff!important;color:#000!important;font:13px Arial,Helvetica,sans-serif!important;margin:0!important;padding:0 0 40px 16px!important}',
'*{font-family:Arial,Helvetica,sans-serif}',
'a{color:#00c}a:visited{color:#551a8b}',
'#rf-nav{display:flex;gap:14px;align-items:center;padding:6px 0;font-size:13px}',
'#rf-nav a{color:#00c;text-decoration:none}#rf-nav a:hover{text-decoration:underline}',
'#rf-nav a.act{color:#000;font-weight:bold}',
'#rf-logo{font:bold 34px Georgia,"Times New Roman",serif!important;letter-spacing:-1px;margin:4px 0 8px}',
'#rf-logo span{font-family:Georgia,"Times New Roman",serif!important}',
'.l1,.l4{color:#3b6fd4}.l2,.l6{color:#d93025}.l3{color:#f4b400}.l5{color:#0f9d58}',
'#rf-res{background:#e5ecf9;border-top:1px solid #36c;margin:12px 0 14px -16px;padding:3px 16px;font-size:13px;display:flex;justify-content:space-between}',
'#rf-res b{font-size:14px}',
'input[type=text],input.query{font-size:16px;padding:4px 5px;border:1px solid #7f9db9!important;background:#fff;color:#000}',
'input[type=submit],input.submit{font-size:13px;padding:4px 14px;background:#f0f0f0;border:1px solid #888;border-radius:2px;color:#000}',
'select{font-size:13px;padding:2px}',
'h1,.header{display:none!important}',
'table{border-collapse:collapse}td{padding:1px 3px}',
'.result-link{font-size:17px!important;text-decoration:underline!important;color:#00c!important}',
'.result-snippet{color:#000!important;font-size:13px!important;line-height:1.4}',
'.rf-url,.link-text{color:#008000!important;font-size:13px!important}'
].join('');
try{var sh=new CSSStyleSheet();sh.replaceSync(css);
 document.adoptedStyleSheets=document.adoptedStyleSheets.concat([sh]);}
catch(x){var st=document.createElement('style');st.textContent=css;document.head.appendChild(st);}
var cab=document.createElement('div');
cab.innerHTML='<div id="rf-nav"><a class="act" href="https://lite.duckduckgo.com/lite/?q='+e+'">Web</a>'
 +'<a href="https://duckduckgo.com/?q='+e+'&iax=images&ia=images">Imágenes</a>'
 +'<a href="https://duckduckgo.com/?q='+e+'&iax=videos&ia=videos">Videos</a>'
 +'<a href="https://duckduckgo.com/?q='+e+'&iar=news&ia=news">Noticias</a>'
 +'<a href="https://duckduckgo.com/?q='+e+'&iaxm=maps">Mapas</a></div>'
 +'<div id="rf-logo"><span class="l1">R</span><span class="l2">i</span><span class="l3">f</span>'
 +'<span class="l4">p</span><span class="l5">a</span><span class="l6">n</span></div>';
document.body.insertBefore(cab,document.body.firstChild);
var barra=document.createElement('div');barra.id='rf-res';
barra.innerHTML='<span><b>Web</b></span><span></span>';
var f=inp&&inp.form;
if(f){f.insertAdjacentElement('afterend',barra);}else{cab.appendChild(barra);}
document.querySelectorAll('a.result-link').forEach(function(a){
 var tr=a.closest('tr');if(!tr)return;
 var u=tr.nextElementSibling&&tr.nextElementSibling.nextElementSibling;
 if(u)u.querySelectorAll('td').forEach(function(td){td.classList.add('rf-url')});
});
document.querySelectorAll('td').forEach(function(td){
 if(td.querySelector('td'))return;
 if(!/Sponsored link/i.test(td.textContent))return;
 var tr=td.closest('tr');if(!tr)return;
 var fila=tr,borrar=[tr];
 for(var i=0;i<3&&fila.nextElementSibling;i++){fila=fila.nextElementSibling;borrar.push(fila);}
 borrar.forEach(function(r){r.style.display='none'});
});
})();
"""


def instalar_estilo_busqueda(perfil):
    """Da a DuckDuckGo Lite un aspecto clásico, con pestañas Web | Imágenes, y oculta anuncios."""
    sc = QWebEngineScript()
    sc.setName("rifpan-busqueda")
    sc.setSourceCode(JS_BUSQUEDA)
    sc.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentReady)
    sc.setRunsOnSubFrames(False)
    perfil.scripts().insert(sc)


class Filtro(QWebEngineUrlRequestInterceptor):
    """Corta las conexiones a dominios de la lista antes de que carguen."""

    def __init__(self, dominios, registro):
        super().__init__()
        self.dominios = dominios
        self.registro = registro  # deque compartida con el visor de eventos

    def interceptRequest(self, info):
        host = info.requestUrl().host().lower()
        while host:
            if host in self.dominios:
                info.block(True)
                try:
                    origen = info.firstPartyUrl().host() or "la página"
                    self.registro.append(f"{time.strftime('%H:%M:%S')}  {host}  (desde {origen})")
                except Exception:
                    pass
                return
            if "." not in host:
                break
            host = host.split(".", 1)[1]


class Pagina(QWebEnginePage):
    def __init__(self, perfil, ventana, parent=None):
        super().__init__(perfil, parent)
        self.ventana = ventana

    def javaScriptConsoleMessage(self, nivel, mensaje, linea, origen):
        if nivel == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
            self.ventana.registrar(
                "errores", f"JS: {mensaje[:150]} ({os.path.basename(origen)}:{linea})")

    def acceptNavigationRequest(self, url, tipo, principal):
        # Enlaces internos del escritorio Win98: rifpan://cerrar y rifpan://historial
        if url.scheme() == "rifpan":
            if url.host() == "cerrar":
                QTimer.singleShot(0, self.ventana.close)
            elif url.host() == "historial":
                QTimer.singleShot(0, self.ventana.ver_historial)
            elif url.host() == "reordenar":
                QTimer.singleShot(0, self.ventana.reordenar_escritorio)
            elif url.host() == "fondos":
                QTimer.singleShot(0, self.ventana.elegir_fondos)
            elif url.host() == "sinfondos":
                QTimer.singleShot(0, self.ventana.quitar_fondos)
            elif url.host() == "guardar":
                try:
                    raw = url.toEncoded().data().decode("utf-8", "replace")
                    datos = json.loads(unquote(raw.split("?d=", 1)[1]))
                    QTimer.singleShot(0, lambda: self.ventana.guardar_escritorio(datos))
                except Exception:
                    pass
            return False
        return super().acceptNavigationRequest(url, tipo, principal)

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

    def __init__(self, parent, titulo, entradas, abrir, texto_btn, accion_btn, al_cerrar):
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
        self.finished.connect(lambda _: al_cerrar())


class Visor(QDialog):
    """Visor de eventos: errores, bloqueos y descargas (se actualiza solo)."""
    CLAVES = (("errores", "Errores"), ("bloqueos", "Bloqueos"), ("descargas", "Descargas"))

    def __init__(self, parent, eventos):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle("Visor de eventos")
        self.resize(760, 480)
        self.eventos = eventos
        self.vistos = {}
        lay = QVBoxLayout(self)
        self.tabs = QTabWidget()
        lay.addWidget(self.tabs)
        self.listas = {}
        for clave, nombre in self.CLAVES:
            lista = QListWidget()
            self.listas[clave] = lista
            self.tabs.addTab(lista, nombre)
        b = QPushButton("Vaciar esta pestaña")
        b.clicked.connect(self.vaciar)
        lay.addWidget(b)
        self.reloj = QTimer(self)
        self.reloj.timeout.connect(self.refrescar)
        self.reloj.start(1500)
        self.refrescar()

    def refrescar(self):
        for i, (clave, nombre) in enumerate(self.CLAVES):
            datos = list(self.eventos[clave])
            marca = (len(datos), datos[-1] if datos else None)
            if self.vistos.get(clave) != marca:
                self.vistos[clave] = marca
                lista = self.listas[clave]
                lista.clear()
                lista.addItems(list(reversed(datos)))  # lo más nuevo arriba
            self.tabs.setTabText(i, f"{nombre} ({len(datos)})")

    def vaciar(self):
        clave = self.CLAVES[self.tabs.currentIndex()][0]
        self.eventos[clave].clear()
        self.refrescar()


class Rifpan(QMainWindow):
    def __init__(self):
        super().__init__()
        self.resize(1150, 750)
        self.setWindowTitle(NOMBRE)
        self.setStyleSheet(ESTILO)
        self.cerrando = False
        self.sonidos = Sonidos()

        # Datos del usuario de Windows actual
        self.usuario = usuario_windows()
        carpeta = carpeta_usuario(self.usuario)
        self.ruta_hist = os.path.join(carpeta, "historial.json")
        self.ruta_fav = os.path.join(carpeta, "favoritos.json")
        self.ruta_cook = os.path.join(carpeta, "sesion.json")
        self.ruta_esc = os.path.join(carpeta, "escritorio.json")
        self.ruta_cfg = os.path.join(carpeta, "ajustes.json")
        self.historial = leer_json(self.ruta_hist, [])
        self.favoritos = leer_json(self.ruta_fav, [])
        self.posiciones = leer_json(self.ruta_esc, {})

        # Ajustes y registro de eventos (errores, bloqueos, descargas)
        self.config = {"visor": True, "pantalla_completa": True}
        cfg = leer_json(self.ruta_cfg, {})
        if isinstance(cfg, dict):
            self.config.update(cfg)
        self.eventos = {"errores": deque(maxlen=300),
                        "bloqueos": deque(maxlen=500),
                        "descargas": deque(maxlen=200)}
        self.visor = None
        sys.excepthook = self._hook

        # Guarda en diferido (no escribe en disco a cada rato)
        self.t_hist = QTimer(self)
        self.t_hist.setSingleShot(True)
        self.t_hist.setInterval(3000)
        self.t_hist.timeout.connect(self.guardar_hist)
        self.t_cook = QTimer(self)
        self.t_cook.setSingleShot(True)
        self.t_cook.setInterval(5000)
        self.t_cook.timeout.connect(self.guardar_cookies)

        # Perfil web sin nombre = privado: nada se guarda en disco por sí solo.
        # Las cookies de PERSISTIR las guardamos nosotros, con vencimiento corto.
        self.perfil = QWebEngineProfile(self)
        self.perfil.setUrlRequestInterceptor(Filtro(cargar_bloqueados(), self.eventos["bloqueos"]))
        instalar_estilo_busqueda(self.perfil)
        self.perfil.downloadRequested.connect(self.descarga)
        s = self.perfil.settings()
        A = QWebEngineSettings.WebAttribute
        s.setAttribute(A.WebGLEnabled, PERMITIR_WEBGL)
        s.setAttribute(A.PluginsEnabled, False)
        s.setAttribute(A.ScrollAnimatorEnabled, False)
        s.setAttribute(A.AutoLoadIconsForPage, False)
        s.setAttribute(A.WebRTCPublicInterfacesOnly, True)
        s.setAttribute(A.FullScreenSupportEnabled, True)
        # El escritorio se carga desde una carpeta local (por los fondos): sin esto
        # sus enlaces y su buscador dan ERR_NETWORK_ACCESS_DENIED
        s.setAttribute(A.LocalContentCanAccessRemoteUrls, True)

        self.cookies = {}
        self.desde = time.time()
        self.tienda = self.perfil.cookieStore()
        self.tienda.cookieAdded.connect(self.cookie_nueva)
        self.tienda.cookieRemoved.connect(self.cookie_borrada)
        self.tienda.loadAllCookies()
        self.cargar_cookies()

        self.pestanas = QTabWidget()
        self.pestanas.setDocumentMode(True)
        self.pestanas.setTabsClosable(True)
        self.pestanas.setMovable(True)
        self.pestanas.tabCloseRequested.connect(self.cerrar_pestana)
        self.pestanas.currentChanged.connect(self.cambio_pestana)
        self.setCentralWidget(self.pestanas)

        self.crear_barra()
        self.nueva_pestana(INICIO)

    # ---------- cookies (solo YouTube/Google, 3 días) ----------
    def permitida(self, c):
        d = c.domain().lstrip(".").lower()
        return any(d == s or d.endswith("." + s) for s in PERSISTIR)

    def clave(self, c):
        return (c.name().data(), c.domain(), c.path())

    def cookie_nueva(self, c):
        if self.permitida(c):
            self.cookies[self.clave(c)] = QNetworkCookie(c)
            self.t_cook.start()

    def cookie_borrada(self, c):
        if self.cookies.pop(self.clave(c), None) is not None:
            self.t_cook.start()

    def cargar_cookies(self):
        datos = leer_json(self.ruta_cook, None)
        if not datos:
            return
        desde = datos.get("desde", 0)
        ahora = time.time()
        if ahora - desde > VIDA_SESION_DIAS * 86400:
            try:
                os.remove(self.ruta_cook)  # la sesión venció: hay que volver a iniciar
            except Exception:
                pass
            return
        self.desde = desde
        limite_ms = int((desde + VIDA_SESION_DIAS * 86400) * 1000)
        for d in datos.get("cookies", []):
            try:
                c = QNetworkCookie(base64.b64decode(d["n"]), base64.b64decode(d["v"]))
                dom = d["d"]
                if dom.startswith("."):
                    c.setDomain(dom)
                host = dom.lstrip(".")
                c.setPath(d["p"])
                c.setSecure(d["s"])
                c.setHttpOnly(d["h"])
                exp = d.get("e")
                exp = limite_ms if exp is None else min(exp, limite_ms)
                if exp < ahora * 1000:
                    continue
                c.setExpirationDate(QDateTime.fromMSecsSinceEpoch(exp))
                if d.get("ss"):
                    try:
                        c.setSameSitePolicy(getattr(QNetworkCookie.SameSite, d["ss"]))
                    except Exception:
                        pass
                self.tienda.setCookie(c, QUrl("https://" + host + "/"))
            except Exception:
                continue

    def guardar_cookies(self):
        if not self.cookies:
            try:
                os.remove(self.ruta_cook)
            except Exception:
                pass
            return
        lista = []
        for c in self.cookies.values():
            exp = None if c.isSessionCookie() else c.expirationDate().toMSecsSinceEpoch()
            lista.append({
                "n": base64.b64encode(c.name().data()).decode(),
                "v": base64.b64encode(c.value().data()).decode(),
                "d": c.domain(), "p": c.path(),
                "s": c.isSecure(), "h": c.isHttpOnly(),
                "e": exp, "ss": c.sameSitePolicy().name,
            })
        guardar_json(self.ruta_cook, {"desde": self.desde, "cookies": lista})

    # ---------- interfaz ----------
    def accion(self, texto, fn, atajo=None, tip=None, sonar=True):
        a = QAction(texto, self)

        def ejecutar(_=False):
            if sonar:
                self.sonidos.maullar()
            fn()

        a.triggered.connect(ejecutar)
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
        self.barra.addAction(self.accion("🏠", self.ir_inicio, "Alt+Home", "Escritorio (Alt+Home)"))
        self.barra_url = QLineEdit()
        self.barra_url.setPlaceholderText("Buscá o escribí una dirección")
        self.barra_url.returnPressed.connect(self.ir)
        self.barra.addWidget(self.barra_url)
        self.accion_fav = self.accion("☆", self.alternar_favorito, "Ctrl+D", "Favorito (Ctrl+D)")
        self.barra.addAction(self.accion_fav)
        self.barra.addAction(self.accion("＋", lambda: self.nueva_pestana(INICIO), "Ctrl+T", "Nueva pestaña (Ctrl+T)"))

        self.accion_visor = self.accion("📋", self.abrir_visor, "Ctrl+E", "Visor de eventos (Ctrl+E)")
        self.accion_visor.setVisible(self.config["visor"])
        self.barra.addAction(self.accion_visor)

        a_fav = self.accion("Favoritos    Ctrl+B", self.ver_favoritos, "Ctrl+B")
        a_hist = self.accion("Historial    Ctrl+H", self.ver_historial, "Ctrl+H")
        a_ajustes = self.accion("Ajustes", self.abrir_ajustes)
        menu = QMenu(self)
        menu.addAction(a_fav)
        menu.addAction(a_hist)
        menu.addSeparator()
        menu.addAction(a_ajustes)
        self.addAction(a_fav)
        self.addAction(a_hist)
        self.barra.addAction(self.accion("⋮", lambda: menu.popup(QCursor.pos()), None, "Menú"))

        # botones de ventana: solo se ven en pantalla completa
        self.accion_min = self.accion("—", self.showMinimized, None, "Minimizar", sonar=False)
        self.accion_cerrar = self.accion("✕", self.close, None, "Cerrar", sonar=False)
        self.barra.addAction(self.accion_min)
        self.barra.addAction(self.accion_cerrar)
        self.actualizar_botones_ventana()
        self.addAction(self.accion("", self.alternar_pantalla, "F11", sonar=False))

        # atajos sin botón
        self.addAction(self.accion("", lambda: self.cerrar_pestana(self.pestanas.currentIndex()), "Ctrl+W", sonar=False))
        self.addAction(self.accion("", lambda: (self.barra_url.setFocus(), self.barra_url.selectAll()), "Ctrl+L", sonar=False))

    # ---------- escritorio Win98 ----------
    def html_inicio(self):
        favs = "".join(
            f'<a class="icono" data-id="{html.escape("fav:" + fv["url"], quote=True)}" '
            f'href="{html.escape(fv["url"], quote=True)}">'
            f'<span>🌐</span><b>{html.escape((fv["titulo"] or fv["url"])[:14])}</b></a>'
            for fv in self.favoritos[:12])
        menu_favs = "".join(
            f'<a href="{html.escape(fv["url"], quote=True)}">{html.escape((fv["titulo"] or fv["url"])[:28])}</a>'
            for fv in self.favoritos[:10]) or "<a>(sin favoritos)</a>"
        pos = json.dumps(self.posiciones).replace("<", "\\u003c")
        fondos = json.dumps([quote(f) for f in listar_fondos()]).replace("<", "\\u003c")
        return (PLANTILLA_INICIO.replace("%%FAVS%%", favs)
                .replace("%%MENUFAVS%%", menu_favs).replace("%%POS%%", pos)
                .replace("%%FONDOS%%", fondos).replace("%%SEG%%", str(int(FONDO_SEGUNDOS))))

    def mostrar_inicio(self, vista):
        if listar_fondos():
            base = QUrl.fromLocalFile(CARPETA_FONDOS.replace(os.sep, "/") + "/")
        else:
            base = QUrl(BASE_INICIO)
        vista.setHtml(self.html_inicio(), base)

    def ir_inicio(self):
        self.mostrar_inicio(self.actual())

    def guardar_escritorio(self, datos):
        limpio = {}
        if isinstance(datos, dict):
            for k, p in list(datos.items())[:100]:
                try:
                    limpio[str(k)[:300]] = {"x": int(p["x"]), "y": int(p["y"])}
                except Exception:
                    continue
        self.posiciones = limpio
        guardar_json(self.ruta_esc, limpio)

    def reordenar_escritorio(self):
        self.posiciones = {}
        try:
            os.remove(self.ruta_esc)
        except Exception:
            pass
        self.mostrar_inicio(self.actual())

    def elegir_fondos(self):
        rutas, _ = QFileDialog.getOpenFileNames(
            self, "Elegí tus fondos (marcá varios con Ctrl)", os.path.expanduser("~"),
            "Imágenes (*.jpg *.jpeg *.jfif *.png *.webp *.gif *.bmp)")
        if not rutas:
            return
        os.makedirs(CARPETA_FONDOS, exist_ok=True)
        for f in listar_fondos():  # reemplaza el conjunto anterior
            try:
                os.remove(os.path.join(CARPETA_FONDOS, f))
            except Exception:
                pass
        for i, r in enumerate(rutas, 1):
            destino = os.path.join(CARPETA_FONDOS, f"fondo{i:02d}")
            if r.lower().endswith(".gif"):
                shutil.copy2(r, destino + ".gif")  # el GIF mantiene su animación
                continue
            img = QImage(r)
            if img.isNull():
                continue
            if max(img.width(), img.height()) > 1600:  # achica para ahorrar memoria
                img = img.scaled(1600, 1600, Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
            if img.hasAlphaChannel():
                img.save(destino + ".png", "PNG")
            else:
                img.save(destino + ".jpg", "JPG", 85)
        self.mostrar_inicio(self.actual())

    def quitar_fondos(self):
        for f in listar_fondos():
            try:
                os.remove(os.path.join(CARPETA_FONDOS, f))
            except Exception:
                pass
        self.mostrar_inicio(self.actual())

    # ---------- pestañas ----------
    def actual(self):
        return self.pestanas.currentWidget()

    def nueva_pestana(self, url=INICIO):
        if self.pestanas.count() >= MAX_PESTANAS:
            return None
        self.sonidos.maullar()
        vista = Vista(self.perfil, self)
        i = self.pestanas.addTab(vista, "Nueva pestaña")
        self.pestanas.setCurrentIndex(i)
        vista.titleChanged.connect(lambda t, v=vista: self.cambio_titulo(v, t))
        vista.urlChanged.connect(lambda u, v=vista: self.cambio_url(v, u))
        vista.loadFinished.connect(lambda ok, v=vista: self.carga_lista(v, ok))
        vista.page().fullScreenRequested.connect(self.pantalla_completa)
        vista.page().certificateError.connect(
            lambda e: self.registrar("errores", f"Certificado: {e.description()} — {e.url().host()}"))
        vista.page().renderProcessTerminated.connect(
            lambda st, cod: self.registrar("errores", f"Se cerró el proceso de una pestaña (código {cod})"))
        if url == INICIO:
            self.mostrar_inicio(vista)
        elif url:
            vista.setUrl(QUrl(url))
        return vista

    def cerrar_pestana(self, i):
        self.sonidos.maullar()
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
        self.mostrar_url(v.url())
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
            self.setWindowTitle(f"{t} — {NOMBRE}" if t else NOMBRE)

    @staticmethod
    def es_web(u):
        return u.scheme() in ("http", "https") and u.host() != "rifpan.local"

    def mostrar_url(self, u):
        self.barra_url.setText(u.toString() if self.es_web(u) else "")

    def cambio_url(self, v, u):
        if v is self.actual():
            self.mostrar_url(u)
            self.actualizar_estrella()

    def pantalla_completa(self, req):
        req.accept()
        on = req.toggleOn()
        if on:
            self.estaba_completa = self.isFullScreen()
        self.barra.setVisible(not on)
        self.pestanas.tabBar().setVisible(not on)
        if on or getattr(self, "estaba_completa", False):
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
            self.actual().setUrl(QUrl(BUSCADOR + q))
        else:
            self.actual().setUrl(QUrl.fromUserInput(t))
        self.actual().setFocus()

    def abrir(self, url):
        self.actual().setUrl(QUrl(url))

    # ---------- historial ----------
    def carga_lista(self, v, ok):
        if not ok:
            self.registrar("errores", f"No se pudo cargar: {v.url().toString()[:120]}")
            return
        self.sonidos.maullar()
        u = v.url()
        if not self.es_web(u):
            return
        u = u.toString()
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
              self.borrar_historial, self.sonidos.golpe).exec()

    def borrar_historial(self, dlg):
        self.historial = []
        self.guardar_hist()
        dlg.entradas.clear()
        dlg.lista.clear()

    # ---------- favoritos ----------
    def ver_favoritos(self):
        Lista(self, "Favoritos", list(self.favoritos), self.abrir,
              "Quitar el seleccionado", self.quitar_favorito, self.sonidos.golpe).exec()

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
        if not self.es_web(v.url()):
            return
        u = v.url().toString()
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
        nombre, host = d.downloadFileName(), d.url().host()
        if BLOQUEAR_DESCARGAS:
            self.registrar("descargas", f"Bloqueada: {nombre} (desde {host})")
            d.cancel()
            return
        r = QMessageBox.question(
            self, "Descarga detectada",
            f"¿Permitir esta descarga?\n\nArchivo: {nombre}\nDesde: {host}"
        )
        if r == QMessageBox.StandardButton.Yes:
            self.sonidos.maullar()
            self.registrar("descargas", f"Aceptada: {nombre} (desde {host})")
            d.stateChanged.connect(lambda st, n=nombre: self.estado_descarga(n, st))
            d.accept()
        else:
            self.registrar("descargas", f"Rechazada: {nombre} (desde {host})")
            d.cancel()

    def estado_descarga(self, nombre, st):
        E = QWebEngineDownloadRequest.DownloadState
        if st == E.DownloadCompleted:
            self.registrar("descargas", f"Terminada: {nombre}")
        elif st == E.DownloadCancelled:
            self.registrar("descargas", f"Cancelada: {nombre}")
        elif st == E.DownloadInterrupted:
            self.registrar("descargas", f"Interrumpida: {nombre}")

    # ---------- eventos, ajustes y pantalla completa ----------
    def registrar(self, tipo, texto):
        self.eventos[tipo].append(f"{time.strftime('%H:%M:%S')}  {texto}")

    def _hook(self, tipo, valor, tb):
        self.registrar("errores", f"Python: {tipo.__name__}: {valor}"[:200])
        sys.__excepthook__(tipo, valor, tb)

    def abrir_visor(self):
        if self.visor is not None:
            try:
                self.visor.raise_()
                self.visor.activateWindow()
                return
            except RuntimeError:
                self.visor = None
        self.visor = Visor(self, self.eventos)
        self.visor.destroyed.connect(lambda *_: setattr(self, "visor", None))
        self.visor.show()

    def abrir_ajustes(self):
        d = QDialog(self)
        d.setWindowTitle("Ajustes")
        d.resize(380, 170)
        lay = QVBoxLayout(d)
        c1 = QCheckBox("Mostrar el visor de eventos en la barra")
        c1.setChecked(bool(self.config["visor"]))
        c1.toggled.connect(lambda v: self.cambiar_config("visor", v))
        c2 = QCheckBox("Abrir Rifpan en pantalla completa")
        c2.setChecked(bool(self.config["pantalla_completa"]))
        c2.toggled.connect(lambda v: self.cambiar_config("pantalla_completa", v))
        lay.addWidget(c1)
        lay.addWidget(c2)
        b = QPushButton("Cerrar")
        b.clicked.connect(d.accept)
        lay.addWidget(b)
        d.exec()

    def cambiar_config(self, clave, valor):
        self.config[clave] = bool(valor)
        guardar_json(self.ruta_cfg, self.config)
        if clave == "visor":
            self.accion_visor.setVisible(bool(valor))

    def alternar_pantalla(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def actualizar_botones_ventana(self):
        completa = self.isFullScreen()
        self.accion_min.setVisible(completa)
        self.accion_cerrar.setVisible(completa)

    def changeEvent(self, e):
        super().changeEvent(e)
        if e.type() == QEvent.Type.WindowStateChange and hasattr(self, "accion_min"):
            self.actualizar_botones_ventana()

    # ---------- cierre (con sonido de "daño") ----------
    def closeEvent(self, e):
        if not self.cerrando and self.sonidos.dano is not None:
            self.cerrando = True
            e.ignore()
            self.sonidos.golpe()
            QTimer.singleShot(ESPERA_CIERRE_MS, self.close)
            return
        self.guardar_hist()
        self.guardar_cookies()
        e.accept()


def main():
    app = QApplication(sys.argv)
    ventana = Rifpan()
    if ventana.config.get("pantalla_completa", True):
        ventana.showFullScreen()
    else:
        ventana.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
