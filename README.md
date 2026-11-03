# ViajaClima - Asistente de Clima y Recomendaciones de Viajes (TP2)

Aplicación web desarrollada en Python con Flask que permite a los usuarios registrarse, planificar viajes, consultar pronósticos meteorológicos en tiempo real e interactuar con un Asistente Inteligente impulsado por Google Gemini.

---

## 🌐 Enlaces del Proyecto

- **Aplicación en Producción (Render):** [https://viajaclima.onrender.com](https://viajaclima.onrender.com) *(o la URL asignada en tu despliegue)*
- **Repositorio de Código (GitHub):** [https://github.com/520tiendaonline-beep/viajaclima](https://github.com/520tiendaonline-beep/viajaclima)

---

## 🚀 Funcionalidades Principales

1. **Autenticación de Usuarios:** Registro e inicio de sesión seguro con contraseñas hasheadas (`werkzeug.security`). Manejo de sesiones en Flask.
2. **Gestión de Viajes:** Panel de usuario para crear, listar, consultar detalles y eliminar itinerarios o planes de viaje.
3. **Consulta Meteorológica:** Integración de APIs de clima para obtener pronósticos y condiciones climáticas según el destino.
4. **Asistente IA con Google Gemini:** Sugerencias y recomendaciones de equipaje, actividades y precauciones según el destino y el clima.
5. **Base de Datos Relacional:** Implementación con SQLite3 estructurada con claves foráneas e inicialización automática.

---

## 🛠️ Tecnologías Utilizadas

- **Backend:** Python 3, Flask, Gunicorn, Requests, Python-dotenv
- **Base de Datos:** SQLite3
- **Inteligencia Artificial:** Google Gemini API
- **Frontend:** HTML5 semántico, CSS3 responsivo, JavaScript (Fetch API)
- **Despliegue y Control de Versiones:** Git, GitHub, Render.com

---

## 💻 Instalación y Ejecución Local

1. **Clonar el repositorio:**
   ```bash
   git clone https://github.com/520tiendaonline-beep/viajaclima.git
   cd viajaclima
   ```

2. **Crear y activar un entorno virtual:**
   ```bash
   # En Windows:
   python -m venv venv
   .\venv\Scripts\activate

   # En Linux / Mac:
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Instalar dependencias:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configurar variables de entorno:**
   Copiar `.env.example` a `.env`:
   ```bash
   cp .env.example .env
   ```
   Completar con la API Key de Gemini y una clave secreta para la sesión de Flask:
   ```env
   FLASK_SECRET_KEY=clave_secreta_local
   GEMINI_API_KEY=tu_api_key_de_gemini
   PORT=5001
   ```

5. **Iniciar la aplicación:**
   ```bash
   python app.py
   ```
   Abrir en el navegador: `http://127.0.0.1:5001`

---

## 📁 Estructura del Proyecto

```text
├── app.py                 # Rutas, controladores e integración con APIs
├── database.py            # Modelos, esquemas y conexión SQLite
├── requirements.txt       # Dependencias del proyecto
├── .env.example           # Plantilla de variables de entorno (sin credenciales)
├── .gitignore             # Archivos omitidos de Git
├── README.md              # Documentación técnica del proyecto
├── static/
│   ├── css/style.css      # Estilos generales y diseño responsivo
│   └── js/main.js         # Lógica interactiva en cliente
└── templates/
    ├── base.html          # Layout base con navbar y footer
    ├── index.html         # Página de inicio
    ├── login.html         # Inicio de sesión
    ├── registro.html      # Registro de usuarios
    ├── panel.html         # Panel principal de viajes
    ├── detalle.html       # Vista detallada de clima y viaje
    └── asistente.html     # Chat / consulta con Asistente Gemini IA
```
