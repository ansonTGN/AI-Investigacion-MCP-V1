# Motor de Investigación de Tendencias de IA

![Python Version](https://img.shields.io/badge/python-3.9%2B-blue)![License](https://img.shields.io/badge/license-MIT-green)![Status](https://img.shields.io/badge/status-activo-brightgreen)

Un sistema automatizado y modular para la investigación de tendencias en Inteligencia Artificial. Recopila y procesa datos de múltiples plataformas (GitHub, YouTube, ArXiv, etc.), utiliza modelos de lenguaje (LLMs) para extraer *insights*, descubrir nuevas palabras clave y genera informes completos en múltiples formatos (JSON, Notion, Supabase).

## 🚀 Características Principales

-   **Investigación Multiplataforma**: Recopila datos de YouTube, GitHub, búsquedas web, ArXiv, HackerNews y un motor de investigación de *papers* personalizado.
-   **Procesamiento con IA**: Utiliza LLMs (OpenAI, Gemini, Groq, Anthropic, Ollama) para tareas avanzadas como:
    -   Extracción inteligente de nuevas palabras clave.
    -   Generación de recomendaciones dinámicas y contextuales.
    -   Traducción de términos de búsqueda para consultas multilingües.
-   **Arquitectura Asíncrona**: Construido con `asyncio` para una alta concurrencia y eficiencia en operaciones de red y manejo de procesos.
-   **Generación de Informes**: Crea automáticamente informes detallados en:
    -   **JSON**: Archivos locales para archivo y análisis.
    -   **Notion**: Páginas estructuradas y fáciles de leer en tu *workspace*.
    -   **Supabase**: Registros en una base de datos PostgreSQL para persistencia a largo plazo.
-   **Gestión de Keywords**: Mantiene un ciclo de vida para las palabras clave, con un catálogo maestro, una lista activa para investigar y un historial de ejecuciones.
-   **Altamente Configurable**: Toda la configuración (API keys, selección de modelos de IA, rutas de archivos) se gestiona a través de un archivo `.env` para facilitar la portabilidad y seguridad.
-   **Protocolo Estándar**: Utiliza el **Model Context Protocol (MCP)** para comunicarse con los servidores de cada plataforma, asegurando una interfaz estandarizada y desacoplada.

## 🏛️ Arquitectura del Proyecto

El sistema está diseñado con una arquitectura modular y desacoplada para facilitar su mantenimiento y extensión.

-   `ai_trend_researcher.py`: El orquestador principal que ejecuta el flujo de investigación diario.
-   `config_manager.py`: Centraliza la carga y validación de toda la configuración desde el archivo `.env`.
-   `mcp_client_manager.py`: Gestiona el ciclo de vida (conexión, llamadas, cierre) de los clientes para los servidores MCP de cada plataforma.
-   `platform_handlers.py`: Contiene la lógica específica para interactuar con cada plataforma (ej. `YouTubeHandler`, `GitHubHandler`), procesar sus datos y estandarizarlos.
-   `data_processor.py`: Se encarga del análisis de datos, la extracción de keywords y la generación de recomendaciones utilizando tanto heurísticas como LLMs.
-   `ai_client_manager.py`: Actúa como una fábrica para interactuar de forma unificada con diferentes proveedores de modelos de lenguaje (OpenAI, Gemini, etc.).
-   `report_generator.py`: Genera los informes finales en todos los formatos soportados (JSON, Notion, Supabase).
-   `keyword_manager.py`: Administra la base de datos de palabras clave en archivos JSON.
-   `research_assistant.py`: Un script avanzado para realizar inmersiones profundas de investigación utilizando el servidor personalizado `research_hub`.

## 🛠️ Instalación y Configuración

Sigue estos pasos para poner en marcha el proyecto en tu entorno local.

### 1. Prerrequisitos

-   **Python 3.9+**
-   **Node.js y npm** (necesario para `npx`, que ejecuta los servidores MCP de la comunidad).
-   **Git**
-   (Opcional) **Compilador de Rust**, si deseas compilar el ejecutable de `research_hub` desde el código fuente.

### 2. Clonar el Repositorio

```bash
git clone https://github.com/tu_usuario/tu_repositorio.git
cd tu_repositorio
```

### 3. Instalar Dependencias de Python

Crea un entorno virtual (recomendado) e instala las bibliotecas necesarias.

```bash
python -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 4. Configurar las Variables de Entorno

Este es el paso más importante. El proyecto se controla mediante un archivo `.env`.

1.  Copia el archivo de ejemplo:
    ```bash
    cp .env.example .env
    ```
2.  Edita el archivo `.env` con un editor de texto y rellena todas las claves de API y rutas necesarias.

```env
# .env.example

# --- Claves de API (Obligatorias para las plataformas que uses) ---
YOUTUBE_API_KEY=AIzaSy...
GITHUB_PERSONAL_ACCESS_TOKEN=ghp_...
NOTION_API_KEY=secret_...
SUPABASE_ACCESS_TOKEN=eyJhbGciOi...
SILICONFLOW_API_KEY= # Opcional, para el servidor de ArXiv

# --- Configuración de Notion (Obligatoria si se usa Notion) ---
NOTION_PARENT_PAGE_ID=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# --- Configuración de Rutas del Sistema (¡IMPORTANTE!) ---
# Modifica estas rutas para que apunten a directorios en tu máquina.
RESEARCH_PAPERS_DIR="/home/user/documentos/research-papers"
RESEARCH_HUB_EXECUTABLE="/home/user/proyectos/rust-research-mcp/target/release/rust-research-mcp"

# --- Configuración del Proveedor de IA ---
# Elige uno: "openai", "gemini", "groq", "anthropic", "ollama"
AI_PROVIDER="openai"

# Rellena la clave de API para el proveedor que hayas elegido.
OPENAI_API_KEY="sk-..."
GOOGLE_API_KEY="AIzaSy..."
GROQ_API_KEY="gsk_..."
ANTHROPIC_API_KEY="sk-ant-..."

# --- (Opcional) Modelos Específicos de IA ---
# Si se dejan en blanco, se usarán los modelos por defecto.
AI_MODEL_OPENAI="gpt-4o"
AI_MODEL_GEMINI="gemini-1.5-flash"
AI_MODEL_GROQ="llama3-70b-8192"
AI_MODEL_ANTHROPIC="claude-3-haiku-20240307"
AI_MODEL_OLLAMA="llama3"
```

### 5. Configurar la Base de Datos (Supabase)

Si planeas usar la integración con Supabase, asegúrate de que tu tabla en la base de datos coincida con el esquema definido en `supabase_schema.sql`. Puedes ejecutar ese script en el editor SQL de tu proyecto de Supabase.

## ▶️ Uso

Una vez configurado, puedes ejecutar los dos flujos de trabajo principales.

### Investigación Diaria de Tendencias

Este es el flujo principal. Ejecutará la investigación en todas las plataformas habilitadas, analizará los datos y generará los informes.

```bash
python ai_trend_researcher.py
```

El script imprimirá su progreso en la consola. Al finalizar, encontrarás el informe JSON en el directorio `reports/` y, si está configurado, una nueva página en Notion y un nuevo registro en tu tabla de Supabase.

### Inmersión Profunda de Investigación

Este script utiliza el servidor `research_hub` para realizar búsquedas avanzadas de *papers*, descargarlos, analizarlos y generar bibliografías.

1.  Asegúrate de que el ejecutable `research_hub` esté correctamente configurado en tu `.env`.
2.  (Opcional) Añade términos de búsqueda al archivo `terminos.txt`.

```bash
python research_assistant.py
```

Los resultados de esta ejecución (CSVs, JSONs, archivos BibTeX y logs) se guardarán en subdirectorios dentro de `salidas/` para mantener cada ejecución organizada.

## 🤝 Contribuciones

Las contribuciones son bienvenidas. Si tienes ideas para mejorar el proyecto, nuevas plataformas para integrar o encuentras algún error, por favor abre un *issue* o envía un *pull request*.

## 📄 Licencia

Este proyecto está bajo la Licencia MIT. Consulta el archivo `LICENSE` para más detalles.