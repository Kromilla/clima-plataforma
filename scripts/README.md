# scripts/

Utilidades puntuales, no parte del servicio. Se corren a mano desde la raíz del
repo.

| Script | Para qué |
|---|---|
| `telegram_chat_id.py` | Averiguar tu `TELEGRAM_CHAT_ID` para el `.env` |
| `telegram_test.py` | Enviar un mensaje de prueba y confirmar que el bot está bien configurado |
| `validar_openaq.py` | Comprobar si OpenAQ tiene estaciones en un bbox (diagnóstico) |

```bash
python scripts/telegram_chat_id.py
```
