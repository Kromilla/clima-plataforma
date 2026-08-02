# Guía de contribuciones · clima-plataforma

¡Gracias por tu interés en contribuir! Este documento explica cómo funciona el proceso
de contribución para mantener la calidad del proyecto.

---

## Código de conducta

Al participar en este proyecto, aceptas el [Código de Conducta](CODE_OF_CONDUCT.md).
El objetivo es mantener un ambiente respetuoso y constructivo para todos.

---

## ¿Cómo puedo contribuir?

### 🐛 Reportar un bug

1. Busca en los [issues existentes](https://github.com/Kromilla/clima-plataforma/issues)
   por si ya fue reportado.
2. Si no existe, abre un nuevo issue usando la plantilla **Bug Report**.
3. Incluye siempre: versión de Python/Node, sistema operativo, y el mensaje de error completo.

### 💡 Proponer una nueva funcionalidad

1. Abre un issue con la plantilla **Feature Request**.
2. Describe el problema que resuelve y cómo encaja con los principios del proyecto.
3. Espera feedback antes de empezar a codificar — evita trabajo en vano.

### 🔧 Contribuir código (Pull Request)

1. Haz fork del repositorio.
2. Crea una rama desde `main` con un nombre descriptivo:
   ```bash
   git checkout -b feat/nueva-fuente-ideam
   git checkout -b fix/corrección-pm25
   ```
3. Implementa tus cambios siguiendo las guías más abajo.
4. Asegúrate de que los tests pasan.
5. Abre un Pull Request con la plantilla incluida.

---

## Levantando el entorno de desarrollo

### Requisitos previos

- Python 3.11+
- Node.js 20+
- Git

### Instalación

```bash
# 1. Fork + clonar
git clone https://github.com/TU-USUARIO/clima-plataforma.git
cd clima-plataforma

# 2. Entorno de Python
python -m venv .venv
.venv\Scripts\activate      # Windows
source .venv/bin/activate   # macOS / Linux
pip install -r requirements.txt

# 3. Variables de entorno
cp .env.example .env
# Edita .env y añade al menos TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID

# 4. Historial para el predictor (opcional, solo para tocar risk.py)
python backfill.py --dias 30

# 5. Dashboard
npm install --prefix dashboard-ui
```

### Levantar los servicios

```bash
# Terminal 1 — recolector
python collector.py

# Terminal 2 — API
python api.py
# → Swagger UI en http://localhost:8000/docs

# Terminal 3 — dashboard
npm run dev --prefix dashboard-ui
# → http://localhost:5173

# Terminal 4 — bot (opcional)
python bot.py
```

---

## Correr los tests

```bash
# Todos los tests (sin conexión a internet — usan fixtures grabadas)
pytest tests/ -q

# Con cobertura
pytest tests/ -q --cov=. --cov-report=term-missing

# Un archivo específico
pytest tests/test_robustez.py -v
```

Los 120 tests no hacen peticiones reales a internet. Si añades un adaptador nuevo,
graba sus fixtures en `tests/fixtures/` usando `httpx` o `requests-mock`.

---

## Convención de commits

Usa la convención [Conventional Commits](https://www.conventionalcommits.org/) simplificada:

```
<tipo>: <descripción corta en español>
```

| Tipo | Cuándo usarlo |
|------|--------------|
| `feat` | Nueva funcionalidad |
| `fix` | Corrección de bug |
| `docs` | Solo cambios en documentación |
| `test` | Añadir o mejorar tests |
| `refactor` | Refactorización sin cambio de comportamiento |
| `chore` | Tareas de mantenimiento (deps, CI…) |

**Ejemplos:**
```
feat: añadir fuente IDEAM para Santa Marta
fix: corregir parseo de fechas en XM con rezago de 3 días
docs: actualizar sección de troubleshooting en README
test: añadir regresión para PM2.5 negativo
```

---

## Cómo añadir una nueva fuente de datos

Esta es la contribución más valiosa. La arquitectura está diseñada para que
**añadir una fuente no requiera tocar el bot, la API ni el dashboard**.

### Paso 1 — Crear el adaptador

```python
# sources/mi_fuente.py
from sources.base import FuenteBase, Lectura

class MiFuente(FuenteBase):
    nombre = "mi_fuente"

    def obtener(self, lugar) -> Lectura:
        # Hace la petición HTTP
        # Devuelve siempre un Lectura, incluso en caso de error
        try:
            datos = self._fetch(lugar)
            return Lectura(
                valor=datos["valor"],
                unidad="µg/m³",
                fuente="Mi Fuente API",
                edad_segundos=0,
            )
        except Exception as e:
            return Lectura.error(str(e))
```

### Paso 2 — Registrarla

```python
# sources/registry.py  — añade una línea
from sources.mi_fuente import MiFuente

FUENTES = [
    ...
    MiFuente(),   # ← aquí
]
```

### Paso 3 — Tests

```python
# tests/test_mi_fuente.py
# Graba una fixture en tests/fixtures/mi_fuente_respuesta.json
# y úsala en los tests para no depender de internet
```

### Eso es todo

El recolector, la API y el bot ya la detectan automáticamente.

---

## Criterios de revisión de PR

Un PR será aprobado si:

- ✅ Todos los tests pasan (`pytest tests/ -q`)
- ✅ El frontend compila sin errores (`npm run build --prefix dashboard-ui`)
- ✅ No hay secretos hardcodeados (tokens, keys, passwords)
- ✅ El código nuevo tiene tests (o hay una justificación clara de por qué no)
- ✅ Sigue los principios del proyecto (nunca crashear, nunca fingir frescura)
- ✅ El PR describe qué cambia y por qué

---

## Preguntas

Abre un issue con la etiqueta `pregunta` o escribe en las discusiones del repo.
No hay preguntas tontas.
