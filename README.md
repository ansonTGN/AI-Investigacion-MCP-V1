¡Excelente idea! Añadir la referencia al repositorio `research_hub_mcp` es importante para dar el crédito correspondiente y clarificar la arquitectura.

Aquí tienes la versión actualizada del `README.md` que incluye la nueva referencia en las tres secciones de idioma.

---

# AI Trend Research Engine

Basado en los repositorios:
[EmpowerHerDev/ai-trend-research-system](https://github.com/EmpowerHerDev/ai-trend-research-system) y [Ladvien/research_hub_mcp](https://github.com/Ladvien/research_hub_mcp)

![Python Version](https://img.shields.io/badge/python-3.9%2B-blue)![License](https://img.shields.io/badge/license-MIT-green)![Status](https://img.shields.io/badge/status-activo-brightgreen)

<p align="center">
  <strong>Languages:</strong>
  <br>
  <a href="#-english">English</a> | <a href="#-español">Español</a> | <a href="#-català">Català</a>
</p>

---

<a name="-english"></a>
## 🇬🇧 English

<details>
<summary><strong>Table of Contents</strong></summary>

- [🚀 Key Features](#-key-features)
- [🏛️ Project Architecture](#️-project-architecture)
- [🛠️ Installation and Setup](#️-installation-and-setup)
  - [1. Prerequisites](#1-prerequisites)
  - [2. Clone the Repository](#2-clone-the-repository)
  - [3. Install Python Dependencies](#3-install-python-dependencies)
  - [4. Configure Environment Variables](#4-configure-environment-variables)
  - [5. Set Up the Database (Supabase)](#5-set-up-the-database-supabase)
- [▶️ Usage](#️-usage)
  - [Daily Trend Research](#daily-trend-research)
  - [Deep Dive Research](#deep-dive-research)
- [🤝 Contributing](#-contributing)
- [📄 License](#-license)

</details>

An automated and modular system for researching trends in Artificial Intelligence. It collects and processes data from multiple platforms (GitHub, YouTube, ArXiv, etc.), uses language models (LLMs) to extract insights, discover new keywords, and generates comprehensive reports in multiple formats (JSON, Notion, Supabase).

**Note:** This project was developed by modifying the [EmpowerHerDev/ai-trend-research-system](https://github.com/EmpowerHerDev/ai-trend-research-system) project and integrating the custom research server from [Ladvien/research_hub_mcp](https://github.com/Ladvien/research_hub_mcp). The result is a flexible and modular system that now supports multiple large language model (LLM) providers, including **OpenAI (GPT), Google (Gemini), Anthropic (Claude), Groq, and Ollama**. This work is also part of a personal learning journey in the field of artificial intelligence agent development.

### 🚀 Key Features

-   **Multi-Platform Research**: Gathers data from YouTube, GitHub, web searches, ArXiv, HackerNews, and a custom paper research engine.
-   **AI-Powered Processing**: Uses LLMs (OpenAI, Gemini, Groq, Anthropic, Ollama) for advanced tasks such as:
    -   Intelligent extraction of new keywords.
    -   Generation of dynamic and contextual recommendations.
    -   Translation of search terms for multilingual queries.
-   **Asynchronous Architecture**: Built with `asyncio` for high concurrency and efficiency in network operations and process handling.
-   **Report Generation**: Automatically creates detailed reports in:
    -   **JSON**: Local files for archiving and analysis.
    -   **Notion**: Structured and easy-to-read pages in your workspace.
    -   **Supabase**: Records in a PostgreSQL database for long-term persistence.
-   **Keyword Management**: Maintains a lifecycle for keywords, with a master catalog, an active list for research, and a history of executions.
-   **Highly Configurable**: All settings (API keys, AI model selection, file paths) are managed through a `.env` file for easy portability and security.
-   **Standard Protocol**: Uses the **Model Context Protocol (MCP)** to communicate with each platform's servers, ensuring a standardized and decoupled interface.

### 🏛️ Project Architecture

The system is designed with a modular and decoupled architecture to facilitate maintenance and extension.

-   `ai_trend_researcher.py`: The main orchestrator that runs the daily research workflow.
-   `config_manager.py`: Centralizes the loading and validation of all configurations from the `.env` file.
-   `mcp_client_manager.py`: Manages the lifecycle (connection, calls, closing) of clients for each platform's MCP servers.
-   `platform_handlers.py`: Contains the specific logic to interact with each platform (e.g., `YouTubeHandler`, `GitHubHandler`), process their data, and standardize it.
-   `data_processor.py`: Handles data analysis, keyword extraction, and recommendation generation using both heuristics and LLMs.
-   `ai_client_manager.py`: Acts as a factory to interact uniformly with different language model providers (OpenAI, Gemini, etc.).
-   `report_generator.py`: Generates the final reports in all supported formats (JSON, Notion, Supabase).
-   `keyword_manager.py`: Manages the keyword database in JSON files.
-   `research_assistant.py`: An advanced script for performing deep research dives using the custom `research_hub` server.

### 🛠️ Installation and Setup

Follow these steps to get the project running in your local environment.

#### 1. Prerequisites

-   **Python 3.9+**
-   **Node.js and npm** (required for `npx`, which runs the community's MCP servers).
-   **Git**
-   (Optional) **Rust Compiler**, if you want to compile the `research_hub` executable from the source code.

#### 2. Clone the Repository

```bash
git clone https://github.com/your_user/your_repository.git
cd your_repository
```

#### 3. Install Python Dependencies

Create a virtual environment (recommended) and install the required libraries.

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

#### 4. Configure Environment Variables

This is the most important step. The project is controlled via a `.env` file.

1.  Copy the example file:
    ```bash
    cp .env.example .env
    ```
2.  Edit the `.env` file with a text editor and fill in all the necessary API keys and paths.

```env
# .env.example

# --- API Keys (Required for the platforms you use) ---
YOUTUBE_API_KEY=AIzaSy...
GITHUB_PERSONAL_ACCESS_TOKEN=ghp_...
NOTION_API_KEY=secret_...
SUPABASE_ACCESS_TOKEN=eyJhbGciOi...
SILICONFLOW_API_KEY= # Optional, for the ArXiv server

# --- Notion Configuration (Required if using Notion) ---
NOTION_PARENT_PAGE_ID=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# --- System Path Configuration (IMPORTANT!) ---
# Modify these paths to point to directories on your machine.
RESEARCH_PAPERS_DIR="/home/user/documents/research-papers"
RESEARCH_HUB_EXECUTABLE="/home/user/projects/rust-research-mcp/target/release/rust-research-mcp"

# --- AI Provider Configuration ---
# Choose one: "openai", "gemini", "groq", "anthropic", "ollama"
AI_PROVIDER="openai"

# Fill in the API key for your chosen provider.
OPENAI_API_KEY="sk-..."
GOOGLE_API_KEY="AIzaSy..."
GROQ_API_KEY="gsk_..."
ANTHROPIC_API_KEY="sk-ant-..."

# --- (Optional) Specific AI Models ---
# If left blank, default models will be used.
AI_MODEL_OPENAI="gpt-4o"
AI_MODEL_GEMINI="gemini-1.5-flash"
AI_MODEL_GROQ="llama3-70b-8192"
AI_MODEL_ANTHROPIC="claude-3-haiku-20240307"
AI_MODEL_OLLAMA="llama3"
```

#### 5. Set Up the Database (Supabase)

If you plan to use the Supabase integration, make sure your database table matches the schema defined in `supabase_schema.sql`. You can run this script in the SQL editor of your Supabase project.

### ▶️ Usage

Once configured, you can run the two main workflows.

#### Daily Trend Research

This is the main workflow. It will run the research on all enabled platforms, analyze the data, and generate reports.

```bash
python ai_trend_researcher.py
```

The script will print its progress to the console. Upon completion, you will find the JSON report in the `reports/` directory and, if configured, a new page in Notion and a new record in your Supabase table.

#### Deep Dive Research

This script uses the `research_hub` server to perform advanced paper searches, download them, analyze them, and generate bibliographies.

1.  Ensure the `research_hub` executable is correctly configured in your `.env`.
2.  (Optional) Add search terms to the `terminos.txt` file.

```bash
python research_assistant.py
```

The results of this execution (CSVs, JSONs, BibTeX files, and logs) will be saved in subdirectories within `salidas/` to keep each run organized.

### 🤝 Contributing

Contributions are welcome. If you have ideas for improving the project, new platforms to integrate, or find any bugs, please open an issue or submit a pull request.

### 📄 License

This project is licensed under the MIT License. See the `LICENSE` file for more details.

---

<a name="-español"></a>
## 🇪🇸 Español

<details>
<summary><strong>Tabla de Contenidos</strong></summary>

- [🚀 Características Principales](#-características-principales)
- [🏛️ Arquitectura del Proyecto](#️-arquitectura-del-proyecto)
- [🛠️ Instalación y Configuración](#️-instalación-y-configuración)
  - [1. Prerrequisitos](#1-prerrequisitos)
  - [2. Clonar el Repositorio](#2-clonar-el-repositorio)
  - [3. Instalar Dependencias de Python](#3-instalar-dependencias-de-python)
  - [4. Configurar las Variables de Entorno](#4-configurar-las-variables-de-entorno)
  - [5. Configurar la Base de Datos (Supabase)](#5-configurar-la-base-de-datos-supabase)
- [▶️ Uso](#️-uso)
  - [Investigación Diaria de Tendencias](#investigación-diaria-de-tendencias)
  - [Inmersión Profunda de Investigación](#inmersión-profunda-de-investigación)
- [🤝 Contribuciones](#-contribuciones)
- [📄 Licencia](#-licencia)

</details>

Un sistema automatizado y modular para la investigación de tendencias en Inteligencia Artificial. Recopila y procesa datos de múltiples plataformas (GitHub, YouTube, ArXiv, etc.), utiliza modelos de lenguaje (LLMs) para extraer *insights*, descubrir nuevas palabras clave y genera informes completos en múltiples formatos (JSON, Notion, Supabase).

**Nota:** Este proyecto ha sido desarrollado modificando el proyecto [EmpowerHerDev/ai-trend-research-system](https://github.com/EmpowerHerDev/ai-trend-research-system) e integrando el servidor de investigación personalizado de [Ladvien/research_hub_mcp](https://github.com/Ladvien/research_hub_mcp). El resultado es un sistema flexible y modular que ahora es compatible con múltiples proveedores de modelos de lenguaje grande (LLM), incluyendo **OpenAI (GPT), Google (Gemini), Anthropic (Claude), Groq y Ollama**. Este trabajo también forma parte de un proceso de aprendizaje personal en el campo del desarrollo de agentes de inteligencia artificial.

### 🚀 Características Principales

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

### 🏛️ Arquitectura del Proyecto

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

### 🛠️ Instalación y Configuración

Sigue estos pasos para poner en marcha el proyecto en tu entorno local.

#### 1. Prerrequisitos

-   **Python 3.9+**
-   **Node.js y npm** (necesario para `npx`, que ejecuta los servidores MCP de la comunidad).
-   **Git**
-   (Opcional) **Compilador de Rust**, si deseas compilar el ejecutable de `research_hub` desde el código fuente.

#### 2. Clonar el Repositorio

```bash
git clone https://github.com/tu_usuario/tu_repositorio.git
cd tu_repositorio
```

#### 3. Instalar Dependencias de Python

Crea un entorno virtual (recomendado) e instala las bibliotecas necesarias.

```bash
python -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate
pip install -r requirements.txt```

#### 4. Configurar las Variables de Entorno

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

#### 5. Configurar la Base de Datos (Supabase)

Si planeas usar la integración con Supabase, asegúrate de que tu tabla en la base de datos coincida con el esquema definido en `supabase_schema.sql`. Puedes ejecutar ese script en el editor SQL de tu proyecto de Supabase.

### ▶️ Uso

Una vez configurado, puedes ejecutar los dos flujos de trabajo principales.

#### Investigación Diaria de Tendencias

Este es el flujo principal. Ejecutará la investigación en todas las plataformas habilitadas, analizará los datos y generará los informes.

```bash
python ai_trend_researcher.py
```

El script imprimirá su progreso en la consola. Al finalizar, encontrarás el informe JSON en el directorio `reports/` y, si está configurado, una nueva página en Notion y un nuevo registro en tu tabla de Supabase.

#### Inmersión Profunda de Investigación

Este script utiliza el servidor `research_hub` para realizar búsquedas avanzadas de *papers*, descargarlos, analizarlos y generar bibliografías.

1.  Asegúrate de que el ejecutable `research_hub` esté correctamente configurado en tu `.env`.
2.  (Opcional) Añade términos de búsqueda al archivo `terminos.txt`.

```bash
python research_assistant.py
```

Los resultados de esta ejecución (CSVs, JSONs, archivos BibTeX y logs) se guardarán en subdirectorios dentro de `salidas/` para mantener cada ejecución organizada.

### 🤝 Contribuciones

Las contribuciones son bienvenidas. Si tienes ideas para mejorar el proyecto, nuevas plataformas para integrar o encuentras algún error, por favor abre un *issue* o envía un *pull request*.

### 📄 Licencia

Este proyecto está bajo la Licencia MIT. Consulta el archivo `LICENSE` para más detalles.

---

<a name="-català"></a>
## CAT Català

<details>
<summary><strong>Taula de Continguts</strong></summary>

- [🚀 Característiques Principals](#-característiques-principals)
- [🏛️ Arquitectura del Projecte](#️-arquitectura-del-projecte)
- [🛠️ Instal·lació i Configuració](#️-installació-i-configuració)
  - [1. Prerequisits](#1-prerequisits)
  - [2. Clonar el Repositori](#2-clonar-el-repositori)
  - [3. Instal·lar Dependències de Python](#3-installar-dependències-de-python)
  - [4. Configurar les Variables d'Entorn](#4-configurar-les-variables-dentorn)
  - [5. Configurar la Base de Dades (Supabase)](#5-configurar-la-base-de-dades-supabase)
- [▶️ Ús](#️-ús)
  - [Recerca Diària de Tendències](#recerca-diària-de-tendències)
  - [Recerca d'Immersió Profunda](#recerca-dimmersió-profunda)
- [🤝 Contribucions](#-contribucions)
- [📄 Llicència](#-llicència)

</details>

Un sistema automatitzat i modular per a la investigació de tendències en Intel·ligència Artificial. Recopila i processa dades de múltiples plataformes (GitHub, YouTube, ArXiv, etc.), utilitza models de llenguatge (LLMs) per extreure *insights*, descobrir noves paraules clau i genera informes complets en múltiples formats (JSON, Notion, Supabase).

**Nota:** Aquest projecte ha estat desenvolupat modificant el projecte [EmpowerHerDev/ai-trend-research-system](https://github.com/EmpowerHerDev/ai-trend-research-system) i integrant el servidor de recerca personalitzat de [Ladvien/research_hub_mcp](https://github.com/Ladvien/research_hub_mcp). El resultat és un sistema flexible i modular que ara és compatible amb múltiples proveïdors de models de llenguatge grans (LLM), incloent-hi **OpenAI (GPT), Google (Gemini), Anthropic (Claude), Groq i Ollama**. Aquest treball també forma part d'un procés d'aprenentatge personal en el camp del desenvolupament d'agents d'intel·ligència artificial.

### 🚀 Característiques Principals

-   **Recerca Multiplataforma**: Recopila dades de YouTube, GitHub, cerques web, ArXiv, HackerNews i un motor de recerca de *papers* personalitzat.
-   **Processament amb IA**: Utilitza LLMs (OpenAI, Gemini, Groq, Anthropic, Ollama) per a tasques avançades com:
    -   Extracció intel·ligent de noves paraules clau.
    -   Generació de recomanacions dinàmiques i contextuals.
    -   Traducció de termes de cerca per a consultes multilingües.
-   **Arquitectura Asíncrona**: Construït amb `asyncio` per a una alta concurrència i eficiència en operacions de xarxa i gestió de processos.
-   **Generació d'Informes**: Crea automàticament informes detallats en:
    -   **JSON**: Fitxers locals per a arxiu i anàlisi.
    -   **Notion**: Pàgines estructurades i fàcils de llegir al teu *workspace*.
    -   **Supabase**: Registres en una base de dades PostgreSQL per a persistència a llarg termini.
-   **Gestió de Keywords**: Manté un cicle de vida per a les paraules clau, amb un catàleg mestre, una llista activa per investigar i un historial d'execucions.
-   **Altament Configurable**: Tota la configuració (claus d'API, selecció de models d'IA, rutes de fitxers) es gestiona mitjançant un fitxer `.env` per facilitar la portabilitat i seguretat.
-   **Protocol Estàndard**: Utilitza el **Model Context Protocol (MCP)** per comunicar-se amb els servidors de cada plataforma, assegurant una interfície estandarditzada i desacoblada.

### 🏛️ Arquitectura del Projecte

El sistema està dissenyat amb una arquitectura modular i desacoblada per facilitar el seu manteniment i extensió.

-   `ai_trend_researcher.py`: L'orquestrador principal que executa el flux de recerca diari.
-   `config_manager.py`: Centralitza la càrrega i validació de tota la configuració des del fitxer `.env`.
-   `mcp_client_manager.py`: Gestiona el cicle de vida (connexió, trucades, tancament) dels clients per als servidors MCP de cada plataforma.
-   `platform_handlers.py`: Conté la lògica específica per interactuar amb cada plataforma (ex. `YouTubeHandler`, `GitHubHandler`), processar les seves dades i estandarditzar-les.
-   `data_processor.py`: S'encarrega de l'anàlisi de dades, l'extracció de paraules clau i la generació de recomanacions utilitzant tant heurístiques com LLMs.
-   `ai_client_manager.py`: Actua com una fàbrica per interactuar de manera unificada amb diferents proveïdors de models de llenguatge (OpenAI, Gemini, etc.).
-   `report_generator.py`: Genera els informes finals en tots els formats suportats (JSON, Notion, Supabase).
-   `keyword_manager.py`: Administra la base de dades de paraules clau en fitxers JSON.
-   `research_assistant.py`: Un script avançat per realitzar immersions profundes de recerca utilitzant el servidor personalitzat `research_hub`.

### 🛠️ Instal·lació i Configuració

Segueix aquests passos per posar en marxa el projecte al teu entorn local.

#### 1. Prerequisits

-   **Python 3.9+**
-   **Node.js i npm** (necessari per a `npx`, que executa els servidors MCP de la comunitat).
-   **Git**
-   (Opcional) **Compilador de Rust**, si vols compilar l'executable de `research_hub` des del codi font.

#### 2. Clonar el Repositori

```bash
git clone https://github.com/el_teu_usuari/el_teu_repositori.git
cd el_teu_repositori
```

#### 3. Instal·lar Dependències de Python

Crea un entorn virtual (recomanat) i instal·la les llibreries necessàries.

```bash
python -m venv venv
source venv/bin/activate  # A Windows: venv\Scripts\activate
pip install -r requirements.txt
```

#### 4. Configurar les Variables d'Entorn

Aquest és el pas més important. El projecte es controla mitjançant un fitxer `.env`.

1.  Copia el fitxer d'exemple:
    ```bash
    cp .env.example .env
    ```
2.  Edita el fitxer `.env` amb un editor de text i omple totes les claus d'API i rutes necessàries.

```env
# .env.example

# --- Claus d'API (Obligatòries per a les plataformes que facis servir) ---
YOUTUBE_API_KEY=AIzaSy...
GITHUB_PERSONAL_ACCESS_TOKEN=ghp_...
NOTION_API_KEY=secret_...
SUPABASE_ACCESS_TOKEN=eyJhbGciOi...
SILICONFLOW_API_KEY= # Opcional, per al servidor d'ArXiv

# --- Configuració de Notion (Obligatòria si s'usa Notion) ---
NOTION_PARENT_PAGE_ID=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# --- Configuració de Rutes del Sistema (IMPORTANT!) ---
# Modifica aquestes rutes perquè apuntin a directoris a la teva màquina.
RESEARCH_PAPERS_DIR="/home/user/documents/research-papers"
RESEARCH_HUB_EXECUTABLE="/home/user/projectes/rust-research-mcp/target/release/rust-research-mcp"

# --- Configuració del Proveïdor d'IA ---
# Tria'n un: "openai", "gemini", "groq", "anthropic", "ollama"
AI_PROVIDER="openai"

# Omple la clau d'API per al proveïdor que hagis triat.
OPENAI_API_KEY="sk-..."
GOOGLE_API_KEY="AIzaSy..."
GROQ_API_KEY="gsk_..."
ANTHROPIC_API_KEY="sk-ant-..."

# --- (Opcional) Models Específics d'IA ---
# Si es deixen en blanc, s'utilitzaran els models per defecte.
AI_MODEL_OPENAI="gpt-4o"
AI_MODEL_GEMINI="gemini-1.5-flash"
AI_MODEL_GROQ="llama3-70b-8192"
AI_MODEL_ANTHROPIC="claude-3-haiku-20240307"
AI_MODEL_OLLAMA="llama3"
```

#### 5. Configurar la Base de Dades (Supabase)

Si planeges fer servir la integració amb Supabase, assegura't que la teva taula a la base de dades coincideixi amb l'esquema definit a `supabase_schema.sql`. Pots executar aquest script a l'editor SQL del teu projecte de Supabase.

### ▶️ Ús

Un cop configurat, pots executar els dos fluxos de treball principals.

#### Recerca Diària de Tendències

Aquest és el flux principal. Executarà la recerca a totes les plataformes habilitades, analitzarà les dades i generarà els informes.

```bash
python ai_trend_researcher.py
```

L'script imprimirà el seu progrés a la consola. En finalitzar, trobaràs l'informe JSON al directori `reports/` i, si està configurat, una nova pàgina a Notion i un nou registre a la teva taula de Supabase.

#### Recerca d'Immersió Profunda

Aquest script utilitza el servidor `research_hub` per realitzar cerques avançades de *papers*, descarregar-los, analitzar-los i generar bibliografies.

1.  Assegura't que l'executable `research_hub` estigui correctament configurat al teu `.env`.
2.  (Opcional) Afegeix termes de cerca al fitxer `terminos.txt`.

```bash
python research_assistant.py```

Els resultats d'aquesta execució (CSVs, JSONs, fitxers BibTeX i logs) es desaran en subdirectoris dins de `salidas/` per mantenir cada execució organitzada.

### 🤝 Contribucions

Les contribucions són benvingudes. Si tens idees per millorar el projecte, noves plataformes per integrar o trobes algun error, si us plau obre un *issue* o envia un *pull request*.

### 📄 Llicència

Aquest projecte està sota la Llicència MIT. Consulta el fitxer `LICENSE` per a més detalls.
