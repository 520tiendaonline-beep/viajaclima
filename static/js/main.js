document.addEventListener("DOMContentLoaded", () => {
    // --- 1. VALIDACIÓN EN CLIENTE DEL FORMULARIO DE REGISTRO ---
    const formRegistro = document.getElementById("form-registro");
    if (formRegistro) {
        formRegistro.addEventListener("submit", (e) => {
            let valido = true;

            const nombre = document.getElementById("nombre");
            const email = document.getElementById("email");
            const password = document.getElementById("password");

            document.querySelectorAll(".error-msg").forEach(el => el.textContent = "");

            if (!nombre.value.trim()) {
                document.getElementById("error-nombre").textContent = "Por favor ingresa tu nombre.";
                valido = false;
            }

            const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
            if (!emailRegex.test(email.value.trim())) {
                document.getElementById("error-email").textContent = "Ingresa un correo electrónico válido.";
                valido = false;
            }

            if (password.value.length < 6) {
                document.getElementById("error-password").textContent = "La contraseña debe tener mínimo 6 caracteres.";
                valido = false;
            }

            if (!valido) {
                e.preventDefault();
            }
        });
    }

    // --- 2. AUTOCOMPLETADO INTELIGENTE DE CIUDAD Y PAÍS ---
    const ciudadInput = document.getElementById("ciudad");
    const paisInput = document.getElementById("pais");
    const datalist = document.getElementById("ciudades-sugeridas");

    if (ciudadInput && datalist) {
        let timerBusqueda = null;

        const autoCompletarPais = (textoIngresado) => {
            if (!paisInput) return false;
            const opciones = datalist.querySelectorAll("option");
            for (const opt of opciones) {
                if (opt.value.toLowerCase() === textoIngresado.toLowerCase() && opt.dataset.pais) {
                    paisInput.value = opt.dataset.pais;
                    return true;
                }
            }
            return false;
        };

        // Al escribir en el campo de ciudad:
        ciudadInput.addEventListener("input", (e) => {
            const query = e.target.value.trim();

            // Si coincide con alguna opción sugerida, rellenar el país de inmediato
            if (autoCompletarPais(query)) {
                return;
            }

            // Si escribe al menos 3 caracteres, buscar dinámicamente en Open-Meteo
            if (query.length >= 3) {
                clearTimeout(timerBusqueda);
                timerBusqueda = setTimeout(async () => {
                    try {
                        const url = `https://geocoding-api.open-meteo.com/v1/search?name=${encodeURIComponent(query)}&count=5&language=es&format=json`;
                        const res = await fetch(url);
                        if (!res.ok) return;
                        const data = await res.json();

                        if (data.results && data.results.length > 0) {
                            data.results.forEach(item => {
                                const nombre = item.name;
                                const pais = item.country || "";
                                const yaExiste = Array.from(datalist.options).some(
                                    o => o.value.toLowerCase() === nombre.toLowerCase()
                                );
                                if (!yaExiste) {
                                    const opt = document.createElement("option");
                                    opt.value = nombre;
                                    opt.dataset.pais = pais;
                                    opt.textContent = `${nombre} (${pais})`;
                                    datalist.appendChild(opt);
                                }
                            });
                        }
                    } catch (err) {
                        // Silencioso en caso de desconexión
                    }
                }, 280);
            }
        });

        // Evento cuando el usuario hace clic o confirma una sugerencia
        ciudadInput.addEventListener("change", (e) => {
            autoCompletarPais(e.target.value.trim());
        });
    }
});
