# EP.03.01 — Tablero del SIE de Banxico con persistencia
# Herramientas de Visualización · IDIA223-4 · Parcial III
# Basado en dashboard_banxico.py (valendd/HerramientasVisualizacion)
#
# Qué cambia respecto al original:
# - Antes: todo se perdía al cerrar la pestaña. La caché de Streamlit
#   (@st.cache_data) solo evita volver a llamar al SIE por 1 hora,
#   no recuerda preferencias entre sesiones.
# - Ahora: preferencias e historial se guardan en SQLite (local) con
#   consultas parametrizadas. En producción se cambiaría a PostgreSQL
#   solo cambiando DATABASE_URL, sin reescribir las consultas.
#
# Uso:
#     pip install -r requirements.txt
#     streamlit run dashboard_banxico_con_persistencia.py
#
# EL TOKEN NO VA EN ESTE ARCHIVO.
# En tu equipo: crea la carpeta .streamlit y dentro un archivo secrets.toml
# con una sola línea:
#     banxico_token = "pega-aqui-tu-token"
# Al publicar: pega esa misma línea en la sección de secretos de la app.
# El archivo secrets.toml nunca se sube al repositorio.
#
# Notas de seguridad (ver EP.03.01_Evidencia_de_Producto.md):
# - Nunca hay credenciales en el código. La ruta de SQLite se lee de
#   TABLERO_DB_PATH y la URL de Postgres, si se usa, de DATABASE_URL.
# - Todas las consultas SQL usan marcadores ? y tuplas de parámetros,
#   nunca f-strings. Así se evita inyección de SQL.

import os
import sqlite3
from datetime import date, datetime

import matplotlib.pyplot as plt
import pandas as pd
import requests
import seaborn as sns
import streamlit as st

# ─── Paleta del curso ──────────────────────────────────────────────────
GRIS = "#B9C3D1"
AZUL = "#1C4C9A"
ROJO = "#B2182B"
AZUL_POS = "#2166AC"
CUALI = ["#E69F00", "#56B4E9", "#009E73", "#0072B2"]

sns.set_theme(style="whitegrid")

SIE = "https://www.banxico.org.mx/SieAPIRest/service/v1/series"
st.set_page_config(page_title="Tablero del SIE", layout="wide")


# ─── Persistencia: SQLite en local, Postgres en producción ─────────────
# En local SQLite guarda todo en un archivo. En producción ese archivo es
# efímero (se borra al reiniciar), por eso ahí se usaría PostgreSQL
# gestionado con DATABASE_URL en secretos.
DB_PATH = os.environ.get("TABLERO_DB_PATH", "tablero.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_connection()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS preferencias (
                clave TEXT PRIMARY KEY,
                valor TEXT NOT NULL,
                actualizado_en TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS consultas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                clave TEXT NOT NULL,
                inicio TEXT NOT NULL,
                fin TEXT NOT NULL,
                dias INTEGER NOT NULL,
                consultado_en TEXT NOT NULL
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def guardar_preferencia(clave, valor):
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO preferencias (clave, valor, actualizado_en) "
            "VALUES (?, ?, ?) "
            "ON CONFLICT(clave) DO UPDATE SET "
            "valor = excluded.valor, actualizado_en = excluded.actualizado_en",
            (clave, valor, datetime.now().isoformat(timespec="seconds")),
        )
        conn.commit()
    finally:
        conn.close()


def cargar_preferencias():
    conn = get_connection()
    try:
        filas = conn.execute(
            "SELECT clave, valor FROM preferencias"
        ).fetchall()
        return {clave: valor for clave, valor in filas}
    finally:
        conn.close()


def registrar_consulta(clave, inicio, fin, dias):
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO consultas (clave, inicio, fin, dias, consultado_en) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                clave,
                str(inicio),
                str(fin),
                int(dias),
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def ultimas_consultas(limite=5):
    conn = get_connection()
    try:
        filas = conn.execute(
            "SELECT clave, inicio, fin, dias, consultado_en "
            "FROM consultas ORDER BY id DESC LIMIT ?",
            (int(limite),),
        ).fetchall()
        return filas
    finally:
        conn.close()


init_db()
prefs = cargar_preferencias()
claves_guardadas = prefs.get("claves", "SF43718")
try:
    inicio_guardado = date.fromisoformat(prefs.get("inicio", "2021-01-01"))
except ValueError:
    inicio_guardado = date(2021, 1, 1)
try:
    fin_guardado = date.fromisoformat(prefs.get("fin", "2025-12-31"))
except ValueError:
    fin_guardado = date(2025, 12, 31)
try:
    suavizado_guardado = int(prefs.get("suavizado", "30"))
except ValueError:
    suavizado_guardado = 30


# ─── El token ──────────────────────────────────────────────────────────
def leer_token():
    try:
        if "banxico_token" in st.secrets:
            return str(st.secrets["banxico_token"]).strip()
    except Exception:
        pass
    if os.environ.get("BANXICO_TOKEN"):
        return os.environ["BANXICO_TOKEN"].strip()
    return None


TOKEN = leer_token()

if TOKEN and len(TOKEN) < 32:
    st.error(
        f"El token tiene {len(TOKEN)} caracteres y deberían ser 64. "
        "Revisa que esté completo y sin comillas."
    )
    st.stop()

if not TOKEN:
    st.error("Falta el token del SIE.")
    st.markdown(
        "1. Pídelo gratis en "
        "https://www.banxico.org.mx/SieAPIRest/service/v1/token\n"
        "2. Crea la carpeta `.streamlit` junto a este archivo.\n"
        "3. Dentro, un archivo `secrets.toml` con la línea:\n"
        '   `banxico_token = "tu-token"`\n'
        "4. Vuelve a cargar esta página."
    )
    st.stop()


# ─── La consulta ───────────────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def consultar(claves, inicio, fin, token):
    url = f"{SIE}/{','.join(claves)}/datos/{inicio}/{fin}"
    respuesta = requests.get(
        url,
        headers={
            "Bmx-Token": token,
            "Accept": "application/json",
            "User-Agent": "UPQ-IDIA224/1.0",
        },
        timeout=60,
    )
    if respuesta.status_code == 401:
        raise PermissionError("El token no fue aceptado.")
    if respuesta.status_code == 429:
        raise PermissionError("Demasiadas peticiones. Espera un momento.")
    respuesta.raise_for_status()

    tipo = respuesta.headers.get("Content-Type") or ""
    if "json" not in tipo:
        raise ValueError(
            f"El servidor no devolvió JSON sino {tipo}. "
            "Suele ser el token o una clave inexistente."
        )

    tablas = []
    faltantes = {}
    for serie in respuesta.json()["bmx"]["series"]:
        if "datos" not in serie:
            continue
        t = pd.DataFrame(serie["datos"])
        t["Fecha"] = pd.to_datetime(t.pop("fecha"), format="%d/%m/%Y")
        faltantes[serie["idSerie"]] = int((t["dato"] == "N/E").sum())
        t["Valor"] = pd.to_numeric(
            t.pop("dato").str.replace(",", "", regex=False), errors="coerce"
        )
        t["Clave"] = serie["idSerie"]
        t["Serie"] = serie.get("titulo", serie["idSerie"])
        tablas.append(t)

    if not tablas:
        raise ValueError("Ninguna de las claves devolvió datos en ese rango.")
    df = pd.concat(tablas, ignore_index=True)
    df["Anio"] = df["Fecha"].dt.year
    df["Mes"] = df["Fecha"].dt.month
    return df, faltantes


# ─── Controles ─────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Qué consultar")
    texto = st.text_input(
        "Claves de las series",
        claves_guardadas,
        help="Sepáralas con comas. Búscalas en el catálogo del SIE. "
        "SF43718 es el tipo de cambio FIX.",
    )
    inicio = st.date_input("Desde", inicio_guardado)
    fin = st.date_input("Hasta", fin_guardado)
    suavizado = st.slider("Días de media móvil", 1, 90, suavizado_guardado)
    st.caption("Fuente: SIE, Banco de México")

    if st.button("Guardar mis preferencias"):
        guardar_preferencia("claves", texto)
        guardar_preferencia("inicio", str(inicio))
        guardar_preferencia("fin", str(fin))
        guardar_preferencia("suavizado", str(suavizado))
        st.success("Preferencias guardadas. Al reabrir, seguirán aquí.")

claves = [c.strip().upper() for c in texto.split(",") if c.strip()]
if not claves:
    st.info("Escribe al menos una clave en el panel de la izquierda.")
    st.stop()
if inicio >= fin:
    st.error("La fecha inicial debe ser anterior a la final.")
    st.stop()

with st.spinner("Consultando el SIE..."):
    try:
        df, faltantes = consultar(tuple(claves), str(inicio), str(fin), TOKEN)
    except PermissionError as e:
        st.error(str(e))
        st.stop()
    except ValueError as e:
        st.warning(str(e))
        st.stop()
    except requests.exceptions.RequestException as e:
        st.error(f"No se pudo consultar el SIE: {e}")
        st.stop()

# Registrar la consulta para que el tablero recuerde qué se consultó.
for clave in claves:
    parte = df[df["Clave"] == clave]
    registrar_consulta(clave, inicio, fin, int(len(parte)))

limpio = df.dropna(subset=["Valor"]).copy()
if limpio.empty:
    st.warning("No hay valores numéricos en ese rango.")
    st.stop()

principal = limpio[limpio["Clave"] == claves[0]].sort_values("Fecha").copy()
titulo_principal = principal["Serie"].iloc[0]

# ─── Encabezado e indicadores ──────────────────────────────────────────
st.title("Tablero de series del SIE")
st.caption(
    f"{titulo_principal} · del {inicio} al {fin} · "
    f"consultado el {datetime.now():%d/%m/%Y %H:%M}"
)

primero = principal["Valor"].iloc[0]
ultimo = principal["Valor"].iloc[-1]
c1, c2, c3, c4 = st.columns(4)
c1.metric("Días con dato", len(principal))
c2.metric("Días inhábiles (N/E)", faltantes.get(claves[0], 0))
c3.metric(
    "Último valor",
    f"{ultimo:,.4f}",
    delta=f"{(ultimo / primero - 1) * 100:+.1f} % en el periodo",
)
c4.metric(
    "Mínimo y máximo",
    f"{principal['Valor'].min():,.2f} – {principal['Valor'].max():,.2f}",
)
st.divider()

# ─── Gráficas ──────────────────────────────────────────────────────────
izquierda, derecha = st.columns(2)

with izquierda:
    if len(claves) == 1:
        st.subheader("La serie y su tendencia")
        principal["Suave"] = principal["Valor"].rolling(suavizado).mean()
        fig, ax = plt.subplots(figsize=(6, 3.4))
        ax.plot(
            principal["Fecha"],
            principal["Valor"],
            color=GRIS,
            linewidth=0.9,
            label="Valor diario",
        )
        ax.plot(
            principal["Fecha"],
            principal["Suave"],
            color=AZUL,
            linewidth=2,
            label=f"Media móvil {suavizado} días",
        )
        ax.set_xlabel("Fecha")
        ax.set_ylabel("Valor de la serie")
        ax.legend(frameon=False)
        st.pyplot(fig)
    else:
        st.subheader("Comparación en base 100")
        limpio = limpio.sort_values("Fecha")
        limpio["Base100"] = limpio.groupby("Clave")["Valor"].transform(
            lambda s: s / s.iloc[0] * 100
        )
        fig, ax = plt.subplots(figsize=(6, 3.4))
        for i, clave in enumerate(claves):
            parte = limpio[limpio["Clave"] == clave]
            if parte.empty:
                continue
            ax.plot(
                parte["Fecha"],
                parte["Base100"],
                color=CUALI[i % len(CUALI)],
                linewidth=1.8,
                label=clave,
            )
        ax.axhline(100, color="gray", linewidth=0.8)
        ax.set_xlabel("Fecha")
        ax.set_ylabel("Índice base 100")
        ax.legend(frameon=False)
        st.pyplot(fig)

with derecha:
    st.subheader("Cambio de un mes a otro")
    mensual = principal.set_index("Fecha")["Valor"].resample("ME").last()
    cambio = (mensual.pct_change() * 100).dropna()
    fig, ax = plt.subplots(figsize=(6, 3.4))
    ax.bar(
        cambio.index,
        cambio.values,
        color=[ROJO if v > 0 else AZUL_POS for v in cambio.values],
        width=20,
    )
    ax.axhline(0, color="gray", linewidth=0.8)
    ax.set_xlabel("Mes")
    ax.set_ylabel("Cambio respecto al mes anterior (%)")
    st.pyplot(fig)
    st.caption(
        "Rojo: el valor subió. Azul: bajó. Para un tipo de cambio, "
        "subir significa que el peso se debilitó."
    )

principal["Variacion"] = principal["Valor"].pct_change() * 100
porAnio = principal.dropna(subset=["Variacion"])

abajo_izq, abajo_der = st.columns(2)

with abajo_izq:
    st.subheader("Qué tan movido estuvo cada año")
    fig, ax = plt.subplots(figsize=(6, 3.4))
    sns.boxplot(data=porAnio, x="Anio", y="Variacion", color=GRIS, ax=ax)
    ax.axhline(0, color=ROJO, linewidth=1, linestyle="--")
    ax.set_xlabel("Año")
    ax.set_ylabel("Variación diaria (%)")
    st.pyplot(fig)

with abajo_der:
    st.subheader("Volatilidad móvil")
    ventana = max(suavizado, 5)
    volatilidad = (
        principal.set_index("Fecha")["Variacion"]
        .rolling(ventana)
        .std()
        .dropna()
    )
    fig, ax = plt.subplots(figsize=(6, 3.4))
    if volatilidad.empty:
        ax.text(
            0.5,
            0.5,
            "Pocos datos para esta ventana",
            ha="center",
            va="center",
            transform=ax.transAxes,
        )
    else:
        ax.fill_between(
            volatilidad.index, volatilidad.values, color=GRIS, alpha=0.6
        )
        ax.plot(volatilidad.index, volatilidad.values, color=AZUL, linewidth=1.6)
        pico = volatilidad.idxmax()
        ax.scatter([pico], [volatilidad.max()], color=ROJO, zorder=3)
        ax.annotate(
            f"Máximo: {volatilidad.max():.2f} %\n{pico:%d/%m/%Y}",
            xy=(pico, volatilidad.max()),
            xytext=(10, -28),
            textcoords="offset points",
            fontsize=8,
            color=ROJO,
        )
    ax.set_xlabel("Fecha")
    ax.set_ylabel(f"Volatilidad ({ventana} d, %)")
    fig.tight_layout()
    st.pyplot(fig)
    st.caption(
        "Mientras más alta la curva, más impredecibles fueron los "
        "cambios diarios en esa ventana. Una curva baja y plana "
        "indica un periodo estable."
    )

# ─── Datos ─────────────────────────────────────────────────────────────
with st.expander("Ver y descargar los datos"):
    st.write("Días marcados como N/E por serie:", faltantes)
    st.dataframe(df)
    st.download_button(
        "Descargar CSV",
        df.to_csv(index=False).encode("utf-8"),
        file_name=f"sie_{'_'.join(claves)}_{inicio}_{fin}.csv",
        mime="text/csv",
    )


# ─── Lo que este tablero ahora recuerda ────────────────────────────────
with st.expander("Lo que este tablero ahora recuerda"):
    st.write(
        "Antes, al cerrar la pestaña se perdía todo. Ahora las "
        "preferencias y el historial viven en SQLite (en local) y "
        "en PostgreSQL gestionado cuando se publica."
    )
    st.write(f"Claves guardadas: {', '.join(claves)}")
    ultimas = ultimas_consultas(5)
    if ultimas:
        st.dataframe(
            pd.DataFrame(
                ultimas,
                columns=["Clave", "Desde", "Hasta", "Días", "Consultado en"],
            )
        )
    else:
        st.info("Aún no hay consultas guardadas en esta base.")
