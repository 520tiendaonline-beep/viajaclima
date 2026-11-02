import os
import json
import requests
from datetime import datetime, date, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
import database

# Cargar variables de entorno desde el archivo .env
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev_secret_key_12345")

# Inicializar las tablas de la base de datos SQLite si no existen
database.init_db()

# Tabla de interpretación de códigos meteorológicos WMO (Open-Meteo)
WMO_CODES = {
    0: ("Despejado", "☀️"),
    1: ("Mayormente despejado", "🌤️"),
    2: ("Parcialmente nublado", "⛅"),
    3: ("Nublado", "☁️"),
    45: ("Neblina", "🌫️"),
    48: ("Niebla con escarcha", "🌫️"),
    51: ("Llovizna ligera", "🌦️"),
    53: ("Llovizna moderada", "🌦️"),
    55: ("Llovizna intensa", "🌧️"),
    61: ("Lluvia ligera", "🌧️"),
    63: ("Lluvia moderada", "🌧️"),
    65: ("Lluvia fuerte", "⛈️"),
    71: ("Nevada ligera", "🌨️"),
    73: ("Nevada moderada", "❄️"),
    75: ("Nevada intensa", "❄️"),
    80: ("Chubascos leves", "🌦️"),
    81: ("Chubascos moderados", "🌧️"),
    82: ("Chubascos violentos", "⛈️"),
    95: ("Tormenta eléctrica", "⛈️"),
    96: ("Tormenta con granizo", "⛈️"),
    99: ("Tormenta eléctrica severa", "⛈️"),
}


# ==========================================================
# SERVICIOS EXTERNOS (OPEN-METEO Y GOOGLE GEMINI)
# ==========================================================

def consultar_clima(ciudad, fecha_inicio=None, fecha_fin=None):
    """
    Consulta meteorológica avanzada e híbrida:
    1. Si el viaje ocurre dentro de los próximos 16 días:
       -> Consulta la API satelital en vivo de Open-Meteo para las fechas exactas.
    2. Si el viaje es en fechas futuras lejanas (otro mes, vacaciones, etc.):
       -> Consulta la API Histórica Oficial de Open-Meteo (ERA5 Archive) para las
          mismas fechas (mismo día y mes) de un año de referencia reciente.
       -> Asigna los días reales del calendario del viaje para mostrar la previsión típica esperable.
    3. Fallback a 7 días en caso de indisponibilidad.
    """
    try:
        # 1. Geocodificación
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={ciudad}&count=1&language=es&format=json"
        geo_resp = requests.get(geo_url, timeout=5)
        geo_data = geo_resp.json()

        if not geo_data.get("results"):
            return None

        resultado = geo_data["results"][0]
        lat = resultado["latitude"]
        lon = resultado["longitude"]
        nombre_oficial = resultado.get("name", ciudad)
        pais = resultado.get("country", "")

        # Obtener temperatura actual de referencia
        temp_actual = "--"
        try:
            curr_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m&timezone=auto"
            c_resp = requests.get(curr_url, timeout=4)
            if c_resp.status_code == 200:
                temp_actual = c_resp.json().get("current", {}).get("temperature_2m", "--")
        except Exception:
            pass

        tipo_prevision = "actual_7dias"
        dias_prevision = []

        # Determinar estrategia según las fechas elegidas en el calendario
        if fecha_inicio and fecha_fin:
            try:
                hoy = date.today()
                dt_inicio = datetime.strptime(fecha_inicio, "%Y-%m-%d").date()
                dt_fin = datetime.strptime(fecha_fin, "%Y-%m-%d").date()
                if dt_fin < dt_inicio:
                    dt_fin = dt_inicio

                diff_inicio = (dt_inicio - hoy).days
                diff_fin = (dt_fin - hoy).days

                # CASO A: Fechas dentro de la ventana de previsión satelital (-1 a 15 días)
                if -1 <= diff_inicio <= 15 and diff_fin <= 15:
                    url_satelite = (
                        f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
                        f"&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max"
                        f"&start_date={fecha_inicio}&end_date={fecha_fin}&timezone=auto"
                    )
                    sat_resp = requests.get(url_satelite, timeout=6)
                    if sat_resp.status_code == 200:
                        daily = sat_resp.json().get("daily", {})
                        fechas = daily.get("time", [])
                        t_maxs = daily.get("temperature_2m_max", [])
                        t_mins = daily.get("temperature_2m_min", [])
                        w_codes = daily.get("weather_code", [])
                        precips = daily.get("precipitation_probability_max", [])

                        for i in range(len(fechas)):
                            code = w_codes[i] if i < len(w_codes) else 0
                            desc, emoji = WMO_CODES.get(code, ("Variable", "🌤️"))
                            dias_prevision.append({
                                "fecha": fechas[i],
                                "temp_min": t_mins[i] if i < len(t_mins) else "--",
                                "temp_max": t_maxs[i] if i < len(t_maxs) else "--",
                                "condicion": desc,
                                "icono": emoji,
                                "lluvia_info": f"{precips[i]}% prob." if (precips and i < len(precips) and precips[i] is not None) else "0%"
                            })
                        tipo_prevision = "satelital"

                # CASO B: Fechas futuras lejanas (más de 16 días) -> Archivo Histórico ERA5 de Open-Meteo
                if not dias_prevision:
                    # Usar el año anterior como referencia histórica completa
                    anio_ref = hoy.year - 1 if hoy.year > 2024 else 2024

                    def desplazar_a_pasado(d, anio):
                        try:
                            return d.replace(year=anio).strftime("%Y-%m-%d")
                        except ValueError:
                            return d.replace(year=anio, day=28).strftime("%Y-%m-%d")

                    hist_start = desplazar_a_pasado(dt_inicio, anio_ref)
                    hist_end = desplazar_a_pasado(dt_fin, anio_ref)

                    # Limitamos la consulta a un máximo de 14 días para optimizar la respuesta
                    duracion_dias = min((dt_fin - dt_inicio).days + 1, 14)
                    dt_hist_end_capped = datetime.strptime(hist_start, "%Y-%m-%d").date() + timedelta(days=duracion_dias - 1)
                    hist_end_str = dt_hist_end_capped.strftime("%Y-%m-%d")

                    url_archivo = (
                        f"https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}"
                        f"&start_date={hist_start}&end_date={hist_end_str}"
                        f"&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum&timezone=auto"
                    )
                    arch_resp = requests.get(url_archivo, timeout=7)
                    if arch_resp.status_code == 200:
                        daily = arch_resp.json().get("daily", {})
                        t_maxs = daily.get("temperature_2m_max", [])
                        t_mins = daily.get("temperature_2m_min", [])
                        w_codes = daily.get("weather_code", [])
                        precips = daily.get("precipitation_sum", [])

                        # Mapeamos los datos históricos exactamente sobre las fechas del viaje del usuario
                        for i in range(len(t_maxs)):
                            fecha_viaje = (dt_inicio + timedelta(days=i)).strftime("%Y-%m-%d")
                            code = w_codes[i] if i < len(w_codes) else 0
                            desc, emoji = WMO_CODES.get(code, ("Típico de la época", "🌤️"))
                            mm_lluvia = precips[i] if (precips and i < len(precips) and precips[i] is not None) else 0.0
                            dias_prevision.append({
                                "fecha": fecha_viaje,
                                "temp_min": t_mins[i] if i < len(t_mins) else "--",
                                "temp_max": t_maxs[i] if i < len(t_maxs) else "--",
                                "condicion": desc,
                                "icono": emoji,
                                "lluvia_info": f"{mm_lluvia} mm registrados"
                            })
                        tipo_prevision = "historico"
            except Exception:
                dias_prevision = []

        # CASO C: Fallback a los próximos 7 días en caso de que no haya fechas o fallen las consultas
        if not dias_prevision:
            url_fallback = (
                f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
                f"&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max"
                f"&forecast_days=7&timezone=auto"
            )
            fb_resp = requests.get(url_fallback, timeout=6)
            if fb_resp.status_code == 200:
                daily = fb_resp.json().get("daily", {})
                fechas = daily.get("time", [])
                t_maxs = daily.get("temperature_2m_max", [])
                t_mins = daily.get("temperature_2m_min", [])
                w_codes = daily.get("weather_code", [])
                precips = daily.get("precipitation_probability_max", [])

                for i in range(len(fechas)):
                    code = w_codes[i] if i < len(w_codes) else 0
                    desc, emoji = WMO_CODES.get(code, ("Variable", "🌤️"))
                    dias_prevision.append({
                        "fecha": fechas[i],
                        "temp_min": t_mins[i] if i < len(t_mins) else "--",
                        "temp_max": t_maxs[i] if i < len(t_maxs) else "--",
                        "condicion": desc,
                        "icono": emoji,
                        "lluvia_info": f"{precips[i]}% prob." if (precips and i < len(precips) and precips[i] is not None) else "0%"
                    })
                tipo_prevision = "actual_7dias"

        # Construir resumen corto para las tarjetas del panel
        if dias_prevision:
            d0 = dias_prevision[0]
            if tipo_prevision == "historico":
                resumen_corto = f"Clima histórico de referencia: {d0['icono']} {d0['temp_min']}°C a {d0['temp_max']}°C"
            else:
                resumen_corto = f"{temp_actual}°C actual | {d0['icono']} {d0['temp_min']}°C a {d0['temp_max']}°C"
        else:
            resumen_corto = f"{temp_actual}°C en {nombre_oficial}"

        return {
            "ciudad": nombre_oficial,
            "pais": pais,
            "temp_actual": temp_actual,
            "tipo_prevision": tipo_prevision,
            "resumen": resumen_corto,
            "dias": dias_prevision
        }

    except requests.exceptions.Timeout:
        return {"error": "Tiempo de espera agotado al consultar el clima."}
    except requests.exceptions.RequestException:
        return {"error": "No se pudo conectar con el servicio de clima."}


def responder_consulta_ia(pregunta_usuario, contexto=""):
    """
    Consulta directamente a la API REST de Google Gemini mediante requests HTTP.
    Usa el modelo oficial recomendado (gemini-3.8-flash) y prueba alternativas si es necesario.
    """
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return (
            "⚠️ No se detectó GEMINI_API_KEY configurada en tu archivo .env.\n\n"
            "Ejemplo de sugerencia generada:\n"
            "Si buscas relajarte y disfrutar de buen clima, te sugiero considerar destinos como Bariloche, Mendoza o Salta. "
            "Para recibir sugerencias personalizadas en vivo, agrega tu clave gratuita de Google Gemini en el archivo .env."
        )

    prompt = f"""
Eres un asesor turístico experto, empático, claro y muy práctico.
{f'Contexto meteorológico y fechas del viaje: {contexto}' if contexto else ''}

Pregunta o requerimiento del viajero:
"{pregunta_usuario}"

Instrucciones:
1. Utiliza los datos climáticos y las fechas previstas provistas para fundamentar qué hacer cada día y qué vestimenta empacar.
2. Si los datos son históricos de esa época, explica que representan los valores típicos esperables para ese mes.
3. Sugiere atractivos específicos adaptados a ese clima y temporada.
4. Brinda 3 consejos prácticos (ropa, presupuesto o traslados).
Sé conciso, estructurado con viñetas y amigable.
"""

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ]
    }

    modelos_candidatos = [
        "models/gemini-3.8-flash",
        "models/gemini-3.5-flash",
        "models/gemini-3.1-flash-lite",
        "models/gemini-2.5-flash"
    ]

    try:
        list_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
        list_resp = requests.get(list_url, timeout=8)
        
        if list_resp.status_code == 200:
            modelos_remotos = [
                m["name"] for m in list_resp.json().get("models", [])
                if "generateContent" in m.get("supportedGenerationMethods", [])
            ]
            flash_remotos = [m for m in modelos_remotos if "flash" in m.lower()]
            otros_remotos = [m for m in modelos_remotos if "flash" not in m.lower()]
            modelos_a_probar = list(dict.fromkeys(modelos_candidatos + flash_remotos + otros_remotos))
        else:
            modelos_a_probar = modelos_candidatos

        ultimo_error = ""

        for modelo in modelos_a_probar:
            modelo_limpio = modelo if modelo.startswith("models/") else f"models/{modelo}"
            gen_url = f"https://generativelanguage.googleapis.com/v1beta/{modelo_limpio}:generateContent?key={api_key}"

            resp = requests.post(gen_url, json=payload, timeout=20)
            
            if resp.status_code == 200:
                try:
                    texto = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                    return texto
                except (KeyError, IndexError):
                    continue
            else:
                try:
                    ultimo_error = resp.json().get("error", {}).get("message", f"HTTP {resp.status_code}")
                except Exception:
                    ultimo_error = f"HTTP {resp.status_code}"
                continue

        return f"No se pudo generar respuesta con los modelos disponibles: {ultimo_error}"

    except requests.exceptions.Timeout:
        return "El servicio de Google Gemini tardó demasiado en responder. Por favor intenta nuevamente."
    except Exception as e:
        return f"Ocurrió un inconveniente al consultar con el servicio de IA: {str(e)}"


# ==========================================================
# RUTAS DE AUTENTICACIÓN Y PÁGINAS PRINCIPALES
# ==========================================================

@app.route("/")
def inicio():
    return render_template("index.html")


@app.route("/registro", methods=["GET", "POST"])
def registro():
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not nombre or not email or not password:
            flash("Todos los campos son obligatorios.", "danger")
            return redirect(url_for("registro"))

        if len(password) < 6:
            flash("La contraseña debe tener al menos 6 caracteres.", "warning")
            return redirect(url_for("registro"))

        password_hash = generate_password_hash(password)

        conn = database.get_db()
        try:
            conn.execute(
                "INSERT INTO usuarios (nombre, email, password_hash) VALUES (?, ?, ?)",
                (nombre, email, password_hash)
            )
            conn.commit()
            flash("¡Registro exitoso! Ya puedes iniciar sesión con tu cuenta.", "success")
            return redirect(url_for("login"))
        except Exception:
            flash("El correo electrónico ya se encuentra registrado.", "danger")
        finally:
            conn.close()

    return render_template("registro.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        conn = database.get_db()
        usuario = conn.execute("SELECT * FROM usuarios WHERE email = ?", (email,)).fetchone()
        conn.close()

        if usuario and check_password_hash(usuario["password_hash"], password):
            session["usuario_id"] = usuario["id"]
            session["usuario_nombre"] = usuario["nombre"]
            flash(f"¡Bienvenido/a de nuevo, {usuario['nombre']}!", "success")
            return redirect(url_for("panel"))
        else:
            flash("Credenciales incorrectas. Verifica tu email y contraseña.", "danger")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Has cerrado sesión exitosamente.", "info")
    return redirect(url_for("inicio"))


# ==========================================================
# PANEL DE CONTROL Y GESTIÓN DE VIAJES
# ==========================================================

@app.route("/panel", methods=["GET", "POST"])
def panel():
    if "usuario_id" not in session:
        flash("Debes iniciar sesión para acceder a tu panel de viajes.", "warning")
        return redirect(url_for("login"))

    usuario_id = session["usuario_id"]
    conn = database.get_db()

    if request.method == "POST":
        ciudad = request.form.get("ciudad", "").strip()
        pais = request.form.get("pais", "").strip()
        fecha_inicio = request.form.get("fecha_inicio", "")
        fecha_fin = request.form.get("fecha_fin", "")

        if not ciudad or not fecha_inicio or not fecha_fin:
            flash("Por favor completa los campos requeridos.", "warning")
        else:
            clima = consultar_clima(ciudad, fecha_inicio=fecha_inicio, fecha_fin=fecha_fin)
            
            if clima and "dias" in clima:
                clima_serializado = json.dumps(clima, ensure_ascii=False)
                pais_final = clima.get("pais", pais) or pais
            else:
                clima_serializado = json.dumps({"resumen": "Clima no disponible", "dias": []}, ensure_ascii=False)
                pais_final = pais

            conn.execute(
                """
                INSERT INTO viajes (usuario_id, ciudad, pais, fecha_inicio, fecha_fin, clima_info)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (usuario_id, ciudad, pais_final, fecha_inicio, fecha_fin, clima_serializado)
            )
            conn.commit()
            flash(f"¡Viaje a {ciudad} guardado con previsión meteorológica para tus fechas!", "success")
            return redirect(url_for("panel"))

    viajes_raw = conn.execute(
        "SELECT * FROM viajes WHERE usuario_id = ? ORDER BY id DESC",
        (usuario_id,)
    ).fetchall()
    conn.close()

    viajes = []
    for v in viajes_raw:
        item = dict(v)
        resumen_texto = "Consultando clima..."
        if item.get("clima_info"):
            try:
                data_clima = json.loads(item["clima_info"])
                resumen_texto = data_clima.get("resumen", item["clima_info"])
            except Exception:
                resumen_texto = item["clima_info"]
        item["clima_resumen"] = resumen_texto
        viajes.append(item)

    return render_template("panel.html", viajes=viajes)


@app.route("/asistente", methods=["GET", "POST"])
def asistente():
    """Asistente de viajes interactivo: responde a preguntas libres del usuario."""
    if "usuario_id" not in session:
        flash("Debes iniciar sesión para consultar al Asistente IA.", "warning")
        return redirect(url_for("login"))

    respuesta = None
    pregunta = ""

    if request.method == "POST":
        pregunta = request.form.get("pregunta", "").strip()
        if not pregunta:
            flash("Por favor escribe tu consulta sobre a dónde viajar.", "warning")
        else:
            respuesta = responder_consulta_ia(pregunta)

    return render_template("asistente.html", pregunta=pregunta, respuesta=respuesta)


@app.route("/viaje/<int:viaje_id>")
def detalle_viaje(viaje_id):
    if "usuario_id" not in session:
        return redirect(url_for("login"))

    conn = database.get_db()
    viaje = conn.execute(
        "SELECT * FROM viajes WHERE id = ? AND usuario_id = ?",
        (viaje_id, session["usuario_id"])
    ).fetchone()
    conn.close()

    if not viaje:
        flash("Viaje no encontrado.", "danger")
        return redirect(url_for("panel"))

    clima = {"resumen": "Sin información", "dias": [], "tipo_prevision": "actual_7dias"}
    if viaje["clima_info"]:
        try:
            clima = json.loads(viaje["clima_info"])
        except Exception:
            clima = {"resumen": viaje["clima_info"], "dias": [], "tipo_prevision": "actual_7dias"}

    return render_template("detalle.html", viaje=viaje, clima=clima)


@app.route("/viaje/<int:viaje_id>/consultar", methods=["POST"])
def consultar_viaje_ia(viaje_id):
    """Consulta libre a la IA combinando el contexto del viaje y el pronóstico diario exacto."""
    if "usuario_id" not in session:
        return redirect(url_for("login"))

    pregunta = request.form.get("pregunta_viaje", "").strip()
    if not pregunta:
        flash("Por favor escribe una pregunta sobre tu viaje.", "warning")
        return redirect(url_for("detalle_viaje", viaje_id=viaje_id))

    conn = database.get_db()
    viaje = conn.execute(
        "SELECT * FROM viajes WHERE id = ? AND usuario_id = ?",
        (viaje_id, session["usuario_id"])
    ).fetchone()

    if viaje:
        dias_texto = ""
        tipo_str = "satelital en vivo"
        if viaje["clima_info"]:
            try:
                data_c = json.loads(viaje["clima_info"])
                dias_list = data_c.get("dias", [])
                if data_c.get("tipo_prevision") == "historico":
                    tipo_str = "registros históricos de esa misma época (Open-Meteo Archive)"
                if dias_list:
                    dias_texto = "; ".join([
                        f"{d['fecha']}: {d['icono']} {d['condicion']} (Mín {d['temp_min']}°C / Máx {d['temp_max']}°C, Lluvia: {d.get('lluvia_info', 'N/D')})"
                        for d in dias_list
                    ])
            except Exception:
                dias_texto = viaje["clima_info"]

        contexto = (
            f"Destino: {viaje['ciudad']}, {viaje['pais']}. "
            f"Fechas programadas: del {viaje['fecha_inicio']} al {viaje['fecha_fin']}. "
            f"Fuente meteorológica: {tipo_str}. "
            f"Previsión detallada día a día: [{dias_texto or 'No disponible'}]."
        )

        respuesta = responder_consulta_ia(pregunta, contexto=contexto)

        historial = f"Pregunta: {pregunta}\n\nRespuesta IA:\n{respuesta}"
        conn.execute(
            "UPDATE viajes SET actividades_ia = ? WHERE id = ?",
            (historial, viaje_id)
        )
        conn.commit()
        flash("¡La IA respondió tu consulta teniendo en cuenta el clima de tus fechas!", "success")

    conn.close()
    return redirect(url_for("detalle_viaje", viaje_id=viaje_id))


@app.route("/viaje/<int:viaje_id>/eliminar", methods=["POST"])
def eliminar_viaje(viaje_id):
    """Permite al usuario eliminar un viaje de su historial."""
    if "usuario_id" not in session:
        return redirect(url_for("login"))

    conn = database.get_db()
    conn.execute(
        "DELETE FROM viajes WHERE id = ? AND usuario_id = ?",
        (viaje_id, session["usuario_id"])
    )
    conn.commit()
    conn.close()

    flash("El viaje ha sido eliminado correctamente.", "info")
    return redirect(url_for("panel"))


# ==========================================================
# ENDPOINT JSON PROPIO (Requisito de consigna)
# ==========================================================

@app.route("/api/viajes")
def api_viajes():
    conn = database.get_db()
    viajes = conn.execute("SELECT id, ciudad, pais, fecha_inicio, fecha_fin, clima_info FROM viajes").fetchall()
    conn.close()

    lista_viajes = []
    for v in viajes:
        d = dict(v)
        try:
            d["clima_detalle"] = json.loads(d["clima_info"])
        except Exception:
            d["clima_detalle"] = d["clima_info"]
        lista_viajes.append(d)

    return jsonify({
        "status": "success",
        "total": len(lista_viajes),
        "viajes": lista_viajes
    })


if __name__ == "__main__":
    puerto = int(os.getenv("PORT", 5001))
    app.run(debug=True, port=puerto)
