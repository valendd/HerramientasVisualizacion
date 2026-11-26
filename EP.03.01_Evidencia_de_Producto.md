# EP.03.01 — Evidencia de Producto

**Materia:** IDIA223-4 | Herramientas de Visualización | SD2026
**Docente:** Jairo Pacindo Piña
**Alumna:** Valentina — 125052706@upq.edu.mx
**Repositorio:** `https://github.com/valendd/HerramientasVisualizacion`
**Tablero de la evaluación:** `dashboard_banxico.py` — Tablero del SIE de Banxico en Streamlit
**API de la evaluación:** SIE de Banxico (`https://www.banxico.org.mx/SieAPIRest/service/v1/series`), con token en secretos. Serie de ejemplo: SF43718, tipo de cambio FIX.
**Fecha de entrega en Classroom:** en la lista, hoy 26 de noviembre de 2026, 23:59; en el detalle, ayer 25 de noviembre, 8:40. Por eso aparece también como sin entregar.

> Contexto: mi tablero consulta una API pero no recuerda nada: al cerrar la pestaña se pierde todo. Investiga qué hace falta para que recuerde.

## 1. ¿Qué es una cadena de conexión? Explica cada parte de `postgresql://usuario:clave@servidor:5432/nombre_base`

Una cadena de conexión es una sola línea de texto con todo lo que una aplicación necesita para conectarse a una base de datos: qué motor usar, quién se conecta, con qué contraseña, en qué servidor y puerto, y a qué base en concreto.

Desglose de `postgresql://usuario:clave@servidor:5432/nombre_base`:

- `postgresql://` — el esquema o protocolo. Dice que el motor es PostgreSQL y qué driver debe usar la aplicación. Si fuera `mysql://` o `sqlite:///`, cambiaría el motor.
- `usuario` — el nombre del usuario de base de datos. No es el usuario de la aplicación ni del sistema, es una cuenta creada dentro de Postgres con permisos limitados, por ejemplo solo leer una tabla del tablero.
- `:` — separa usuario y contraseña.
- `clave` — la contraseña de ese usuario. En un trabajo real nunca va escrita en el código ni en GitHub (ver pregunta 4), va en una variable de entorno o en secretos.
- `@` — separa las credenciales del destino.
- `servidor` — el host donde vive Postgres: puede ser `localhost`, una IP, o un dominio como `db.midominio.com` o el host que da un servicio como Neon o Supabase.
- `:5432` — el puerto. 5432 es el puerto por defecto de PostgreSQL. Si el servidor usa otro, se cambia aquí.
- `/nombre_base` — el nombre de la base de datos dentro de ese servidor. Un mismo servidor puede tener varias bases; esta parte dice a cuál conectarse.

Ejemplo aplicado a mi tablero, sin credenciales reales:

```
DATABASE_URL=postgresql://tablero_app:***@db.example.com:5432/tablero_sie
```

En el código solo se lee `os.environ["DATABASE_URL"]`, nunca se escribe la cadena completa en el repositorio.

## 2. ¿Qué significa que SQLite sea una base embebida y no cliente-servidor? Da un caso donde conviene y uno donde no

SQLite no es un servidor aparte. Es una biblioteca que se enlaza a la aplicación y guarda toda la base en un solo archivo, por ejemplo `tablero.db`. No hay proceso de base de datos corriendo, no hay puerto ni red: cuando el programa abre el archivo, lo lee y lo escribe directamente.

En cambio, PostgreSQL o MySQL son cliente-servidor: hay un servidor de base de datos corriendo en otra máquina o proceso, y la aplicación se conecta por red con usuario, contraseña y puerto. El servidor atiende a muchos clientes a la vez, controla permisos y transacciones concurrentes.

**Caso donde conviene SQLite:** mi tablero en local o para una práctica individual. Solo lo usa una persona a la vez, los datos son preferencias y un historial de consultas, y no quiero instalar ni administrar un servidor. Es perfecto para prototipar la persistencia: creo `tablero.db`, guardo las claves SIE favoritas (por ejemplo SF43718), el rango de fechas y el suavizado, y al reabrir la app siguen ahí. También conviene para pruebas y para una app offline.

**Caso donde no conviene:** el tablero publicado con muchos usuarios a la vez. SQLite permite un escritor a la vez y se bloquea con escrituras concurrentes, no tiene usuarios ni permisos por rol como Postgres, y si el archivo vive en el servidor de la app, cada réplica tiene su propia copia. Para un tablero compartido en Streamlit Cloud, con varios alumnos consultando series del SIE y guardando a la vez, conviene PostgreSQL gestionado.

## 3. ¿Por qué una aplicación publicada puede perder lo que guardó en un archivo? ¿Qué alternativas hay?

Porque en los servicios de despliegue modernos el sistema de archivos local es efímero. En Streamlit Cloud, Render, Railway o un contenedor de Docker, cuando la app se reinicia, se redespliega o se mueve a otra réplica, los archivos que creó en ejecución se borran o quedan en una réplica que ya no se usa. Guardar en `./datos.csv`, `./tablero.db` o `./notas.txt` funciona en mi computadora, pero no sobrevive a un reinicio en producción. Además, si hay dos réplicas, cada una tiene su propio disco y no se ven entre sí.

También hay otro problema: si el archivo se sube al repositorio por accidente, se mezcla código con datos y se puede exponer información personal.

**Alternativas:**

- **Base de datos gestionada:** PostgreSQL (Neon, Supabase, Railway, RDS) o MySQL. Es lo adecuado para recordar preferencias, historial y notas de muchos usuarios.
- **SQLite en volumen persistente:** solo si el proveedor ofrece un disco persistente atado a la app y hay un solo usuario o muy poco tráfico. No es la opción general para web multiusuario.
- **Almacenamiento de objetos:** S3 o equivalente para archivos grandes como CSV o imágenes, guardando en la base solo la ruta.
- **Servicios de estado de la plataforma:** por ejemplo, la caché de Streamlit solo sirve para no volver a llamar a la API en una hora (`@st.cache_data(ttl=3600)` en mi `dashboard_banxico.py`), no para recordar entre sesiones. Para persistencia real hace falta algo fuera del proceso de la app.

En mi tablero Banxico, el código ya cuida el token (ver pregunta 4) y no lee ningún archivo del disco: todos los datos vienen del SIE. Eso es bueno para desplegar, pero es justo por lo que no recuerda nada.

## 4. ¿Dónde deben vivir las credenciales y por qué nunca en el código?

Deben vivir fuera del código, en el entorno donde corre la aplicación, y solo llegar a ella en tiempo de ejecución:

- Variables de entorno del servidor o del servicio de despliegue.
- Archivos de secretos del framework, como `.streamlit/secrets.toml` en local, que nunca se sube a GitHub.
- Gestores de secretos como Doppler, Vault, AWS Secrets Manager o los secretos de GitHub Actions, con acceso limitado y rotación.
- En desarrollo, un archivo `.env` local, listado en `.gitignore`.

**Por qué nunca en el código:** porque el código se comparte, se sube a GitHub, se copia, se publica y queda en el historial de git aunque se borre después. Cualquiera con acceso al repositorio — compañeros, el docente, o si el repo es público, internet — vería la contraseña de la base de datos o el token de la API. Con ese token podría consultar el SIE a mi nombre y gastar la cuota. Además, si la credencial cambia, habría que cambiar el código y volver a desplegar, en lugar de solo cambiar el secreto en el servidor.

En mi caso, esto ya está aplicado en `dashboard_banxico.py`: el encabezado dice “EL TOKEN NO VA EN ESTE ARCHIVO” y la función `leer_token()` busca primero `st.secrets["banxico_token"]` y luego `os.environ["BANXICO_TOKEN"]`. El token de 64 caracteres nunca aparece en el repositorio. Lo mismo aplica para `DATABASE_URL` si el tablero usara Postgres: iría en secretos, y en el código solo aparecería `os.environ.get("DATABASE_URL")`. Nunca un `password = "1234"` o un `api_key = "abc"` escrito en el código.

## 5. ¿Qué es una inyección de SQL y por qué una consulta parametrizada la evita?

Una inyección de SQL es un ataque donde el atacante mete código SQL dentro de un campo de entrada y la aplicación lo concatena tal cual en la consulta, así el motor lo ejecuta como si fuera parte de la orden.

Ejemplo vulnerable en Python, **no hacer esto**:

```python
# VULNERABLE: no usar
clave = st.text_input("Clave de la serie")
query = f"SELECT * FROM consultas WHERE clave = '{clave}'"
cursor.execute(query)
```

Si alguien escribe `SF43718' OR '1'='1`, la consulta se convierte en:

```sql
SELECT * FROM consultas WHERE clave = 'SF43718' OR '1'='1'
```

Y devuelve todas las filas. Con un campo más elaborado se podrían borrar tablas o leer otras.

**Consulta parametrizada:** se separa el código de los datos. Se escribe la consulta con un marcador `?` y se pasan los valores aparte; el driver los trata siempre como datos, nunca como código, y los escapa correctamente.

```python
# CORRECTO
cursor.execute(
    "SELECT * FROM consultas WHERE clave = ?",
    (clave,),
)
```

Aunque `clave` contenga comillas o `OR '1'='1`, SQLite / Postgres lo busca como texto literal, no lo ejecuta. Por eso en el código de persistencia de este trabajo todas las inserciones y lecturas usan `?` y tuplas de parámetros, nunca `f-string` para armar SQL.

## Reflexión de cierre: si tu tablero tuviera que recordar algo, ¿qué guardarías y en qué base?

Guardaría tres cosas, en ese orden:

1. **Preferencias del usuario:** claves SIE consultadas (por ejemplo SF43718, tipo de cambio FIX), rango de fechas y días de media móvil. Es lo que más se pierde hoy al cerrar la pestaña y lo que hace que el tablero se sienta personal.
2. **Historial de consultas:** clave, fecha de inicio, fecha de fin, fecha de consulta y cuántos días trajo el SIE. Sirve para no volver a llamar a Banxico para el mismo rango y para mostrar “últimas consultas”.
3. **Series favoritas:** una clave marcada como favorita para abrir el tablero ya filtrado en ella, por ejemplo el FIX.

**¿En qué base?** En dos etapas. Para la práctica y para demostrar la idea en local, **SQLite**: un archivo `tablero.db` con dos tablas (`preferencias` y `consultas`), sin servidor, con consultas parametrizadas. Es suficiente para un solo usuario y para entender el concepto.

Para el tablero publicado y compartido, **PostgreSQL gestionado** (por ejemplo Neon o Supabase), con la cadena en `DATABASE_URL` como variable de entorno. Es cliente-servidor, soporta varios usuarios a la vez, tiene usuarios y permisos, y los datos sobreviven a reinicios y redespliegues, que es justo lo que hoy pierde mi tablero cuando guarda en un archivo.

El archivo `dashboard_banxico_con_persistencia.py` de este repositorio implementa esa idea sobre el tablero real de Banxico: lee y guarda preferencias en SQLite en local, registra cada consulta al SIE con consulta parametrizada, y está preparado para cambiar a Postgres solo cambiando `DATABASE_URL`, sin cambiar las consultas. El token del SIE sigue en secretos, nunca en el código.

---

**Evidencia en GitHub:** `https://github.com/valendd/HerramientasVisualizacion`
- `EP.03.01_Evidencia_de_Producto.md` — este documento
- `dashboard_banxico_con_persistencia.py` — tablero del SIE con persistencia en SQLite + consultas parametrizadas
- `dashboard_banxico.py` — tablero original de la evaluación (SIE de Banxico, Streamlit)
