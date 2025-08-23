# config_manager.py
# -*- coding: utf-8 -*-

# Importa el módulo 'os' para interactuar con el sistema operativo, principalmente para leer variables de entorno.
import os
# Importa herramientas de 'typing' para añadir anotaciones de tipo, mejorando la legibilidad y robustez del código.
from typing import Dict, List, Any


class ServerConfig:
    """
    Gestiona las configuraciones de los servidores MCP (Model Context Protocol).
    Define cómo iniciar y conectar con los diferentes servicios externos (YouTube, GitHub, etc.).
    """

    @staticmethod
    def _clean_env(env: Dict[str, Any]) -> Dict[str, str]:
        """
        Método privado para limpiar el diccionario de entorno.
        Elimina claves con valores None o vacíos ("") y convierte todos los valores a string.
        Esto es necesario porque algunas bibliotecas (como Pydantic, usada por MCP) no aceptan None en variables de entorno.
        """
        # Si el diccionario de entrada está vacío, devuelve uno vacío.
        if not env:
            return {}
        # Devuelve un nuevo diccionario que solo incluye los ítems válidos y con valores casteados a string.
        return {k: str(v) for k, v in env.items() if v not in (None, "")}

    @staticmethod
    def get_server_configs() -> Dict[str, Dict[str, Any]]:
        """
        Devuelve un diccionario que contiene la configuración detallada para cada servidor MCP.
        Los servidores que requieren credenciales (API keys) se marcan con enabled=False si la clave no está presente.
        """
        # Lee todas las claves de API y tokens de las variables de entorno.
        youtube_key   = os.getenv("YOUTUBE_API_KEY")
        gh_token      = os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN")
        notion_key    = os.getenv("NOTION_API_KEY")
        notion_parent = os.getenv("NOTION_PARENT_PAGE_ID")
        supa_token    = os.getenv("SUPABASE_ACCESS_TOKEN")
        silicon_key   = os.getenv("SILICONFLOW_API_KEY")

        # Lee las rutas configurables desde el entorno para mayor portabilidad.
        download_dir = os.getenv("RESEARCH_PAPERS_DIR", "research-papers")
        research_hub_executable = os.getenv("RESEARCH_HUB_EXECUTABLE", "rust-research-mcp")

        # Construye dinámicamente la lista de argumentos para el servidor de Notion.
        notion_args = ["@ramidecodes/mcp-server-notion@latest", "-y"]
        # Añade la clave de API a los argumentos solo si existe, para no exponer un argumento vacío.
        if notion_key:
            notion_args.append(f"--api-key={notion_key}")

        # Construye dinámicamente la lista de argumentos para el servidor de Supabase.
        supabase_args = ["-y", "@supabase/mcp-server-supabase@latest"]
        # Añade el token de acceso a los argumentos solo si existe.
        if supa_token:
            supabase_args += ["--access-token", supa_token]

        # Define el diccionario principal de configuraciones.
        configs: Dict[str, Dict[str, Any]] = {
            "youtube": {
                "server_name": "npx",  # Comando para ejecutar el servidor (a través de npx).
                "args": ["-y", "youtube-data-mcp-server"],  # Argumentos para el comando.
                "env": ServerConfig._clean_env({  # Variables de entorno específicas para este servidor.
                    "YOUTUBE_API_KEY": youtube_key,
                    "YOUTUBE_TRANSCRIPT_LANG": "ja",  # Configura el idioma de las transcripciones a japonés.
                }),
                "tools": ["searchVideos", "getVideoDetails", "getTranscripts"],  # Herramientas que expone el servidor.
                "required_env": ["YOUTUBE_API_KEY"],  # Variables de entorno obligatorias.
                "enabled": True if youtube_key else False,  # Se activa solo si la clave de API está presente.
            },
            "github": {
                "server_name": "npx",
                "args": ["-y", "@modelcontextprotocol/server-github"],
                "env": ServerConfig._clean_env({
                    "GITHUB_PERSONAL_ACCESS_TOKEN": gh_token,
                }),
                "tools": ["search_code", "search_repositories", "get_repository"],
                "required_env": ["GITHUB_PERSONAL_ACCESS_TOKEN"],
                "enabled": True if gh_token else False, # Se activa solo si el token de GitHub está presente.
            },
            "web": {
                "server_name": "one-search-mcp",  # Este servidor se ejecuta directamente, sin 'npx'.
                "args": [],  # No necesita argumentos adicionales.
                "env": {  # Variables de entorno para estandarizar y silenciar la salida de la consola.
                    "DOTENVX_SILENT": "1",
                    "FORCE_COLOR": "0",
                    "NO_COLOR": "1"
                },
                "tools": ["one_search", "one_extract", "one_scrape"],
                "enabled": True,  # Este servidor siempre está habilitado ya que no requiere claves.
            },
            "notion": {
                "server_name": "npx",
                "args": ["-y", *notion_args],  # Usa los argumentos construidos dinámicamente.
                "env": ServerConfig._clean_env({}), # No necesita variables de entorno adicionales.
                "tools": ["create-page", "get-page", "update-page", "query-database", "search"],
                "required_env": ["NOTION_API_KEY"],
                "enabled": True if notion_key else False, # Se activa solo si la clave de Notion está presente.
            },
            "arxiv": {
                "server_name": "npx",
                "args": ["-y", "@langgpt/arxiv-mcp-server@latest"],
                "env": {
                    "SILICONFLOW_API_KEY": silicon_key,
                    "WORK_DIR": "./reports",  # Directorio de trabajo para descargar PDFs.
                    "FORCE_COLOR": "0",
                    "NO_COLOR": "1",
                    "DOTENVX_SILENT": "1"
                },
                "tools": [
                    "search_arxiv", "download_arxiv_pdf", "parse_pdf_to_text",
                    "convert_to_wechat_article", "parse_pdf_to_markdown",
                    "process_arxiv_paper", "clear_workdir"
                ],
                "enabled": bool(silicon_key), # Se activa solo si la clave de SiliconFlow está presente.
            },
            "hackernews": {
                "server_name": "npx",
                "args": ["-y", "@microagents/server-hackernews"],
                "env": ServerConfig._clean_env({}),
                "tools": ["getStories", "getStory", "getStoryWithComments"],
                "required_env": [],  # No requiere variables de entorno.
                "enabled": True,  # Siempre habilitado.
            },
            "supabase": {
                "server_name": "npx",
                "args": supabase_args,  # Usa los argumentos construidos dinámicamente.
                "env": ServerConfig._clean_env({}),
                "tools": ["execute_sql"],
                "required_env": ["SUPABASE_ACCESS_TOKEN"],
                "enabled": True if supa_token else False, # Se activa solo si el token de Supabase está presente.
            },
            "research_hub": {
                "server_name": research_hub_executable,
                "args": [
                    "--download-dir", download_dir,
                    "--log-level", "info"
                ],
                "env": {
                    "RUST_LOG": "info",
                    "DOTENVX_SILENT": "1",
                    "FORCE_COLOR": "0",
                    "NO_COLOR": "1"
                },
                "tools": [
                    "search_papers", 
                    "download_paper", 
                    "extract_metadata",
                    "search_code", 
                    "generate_bibliography"
                ],
                "required_env": ["RESEARCH_HUB_EXECUTABLE", "RESEARCH_PAPERS_DIR"], 
                "enabled": os.path.exists(research_hub_executable), # Se activa si el binario existe.
            },
        }
        # Devuelve el diccionario completo de configuraciones.
        return configs

    @staticmethod
    def get_enabled_platforms() -> List[str]:
        """Devuelve una lista con los nombres de las plataformas que están actualmente habilitadas."""
        configs = ServerConfig.get_server_configs()
        # Crea una lista de plataformas donde el valor de 'enabled' es True.
        return [platform for platform, config in configs.items() if config.get("enabled", False)]


class AppConfig:
    """Clase para gestionar la configuración general de la aplicación (proveedor de IA, modelos, etc.)."""

    @staticmethod
    def get_ai_provider() -> str:
        """Obtiene el proveedor de IA configurado en .env, con 'openai' como valor por defecto."""
        return os.getenv("AI_PROVIDER", "openai").lower()

    @staticmethod
    def get_api_key(provider: str) -> str:
        """Obtiene la clave de API para un proveedor de IA específico."""
        # Mapea el nombre del proveedor a su variable de entorno correspondiente.
        provider_key_map = {
            "anthropic": "ANTHROPIC_API_KEY",
            "gemini": "GOOGLE_API_KEY",
            "groq": "GROQ_API_KEY",
            "openai": "OPENAI_API_KEY",
            # 'ollama' se ejecuta localmente y no requiere clave.
        }
        # Obtiene el nombre de la variable de entorno del mapa.
        env_var_name = provider_key_map.get(provider)
        # Devuelve el valor de la variable de entorno si existe, si no, None.
        return os.getenv(env_var_name) if env_var_name else None

    @staticmethod
    def get_ai_model(provider: str) -> str:
        """Obtiene el nombre del modelo de IA específico para un proveedor, si está configurado."""
        # Construye el nombre de la variable de entorno (ej. "AI_MODEL_OPENAI").
        env_var_name = f"AI_MODEL_{provider.upper()}"
        # Devuelve el valor de la variable de entorno.
        return os.getenv(env_var_name)

    @staticmethod
    def get_notion_parent_page_id() -> str:
        """Obtiene el ID de la página padre de Notion desde las variables de entorno."""
        return os.getenv("NOTION_PARENT_PAGE_ID", "")

    @staticmethod
    def get_reports_directory() -> str:
        """Devuelve el nombre del directorio donde se guardan los informes locales."""
        return "reports"

    @staticmethod
    def validate_required_env_vars() -> List[str]:
        """
        Valida que todas las variables de entorno necesarias estén definidas.
        Devuelve una lista con las variables que faltan.
        """
        # Define un diccionario de variables requeridas y su descripción.
        required_vars = {
            "YOUTUBE_API_KEY": "YouTube API key",
            "GITHUB_PERSONAL_ACCESS_TOKEN": "GitHub access token",
            "NOTION_API_KEY": "Notion API key",
            "NOTION_PARENT_PAGE_ID": "Notion parent page ID",
            "SUPABASE_ACCESS_TOKEN": "Supabase access token",
            "RESEARCH_PAPERS_DIR": "Research papers download directory",
            "RESEARCH_HUB_EXECUTABLE": "Path to the Research Hub executable"
        }
        # Añade la clave de API del proveedor de IA seleccionado a la lista de requeridos.
        ai_provider = AppConfig.get_ai_provider()
        api_key_env_var = {
            "gemini": "GOOGLE_API_KEY",
            "groq": "GROQ_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "openai": "OPENAI_API_KEY",
        }.get(ai_provider)
        if api_key_env_var:
            required_vars[api_key_env_var] = f"API Key for {ai_provider.capitalize()}"

        # Crea una lista de las variables que no están definidas.
        missing = [f"{var} ({desc})" for var, desc in required_vars.items() if not os.getenv(var)]
        return missing

    @staticmethod
    def print_config_status():
        """Imprime en la consola un resumen del estado de la configuración actual."""
        print("=== Configuration Status ===")
        ai_provider = AppConfig.get_ai_provider()
        print(f"✓ AI Provider configured: {ai_provider.upper()}")

        api_key = AppConfig.get_api_key(ai_provider)
        if ai_provider not in ["ollama"]: # Ollama no necesita clave.
            print(f"✓ {ai_provider.capitalize()} API key loaded" if api_key else f"✗ {ai_provider.capitalize()} API key not found")

        ai_model = AppConfig.get_ai_model(ai_provider)
        print(f"✓ Using specific model for {ai_provider}: {ai_model}" if ai_model else f"✓ Using default model for {ai_provider}")
        print("---")

        # Comprueba el estado de otras claves de API importantes.
        other_vars = [
            ("YOUTUBE_API_KEY", "YouTube API key"),
            ("GITHUB_PERSONAL_ACCESS_TOKEN", "GitHub access token"),
            ("NOTION_API_KEY", "Notion API key"),
            ("NOTION_PARENT_PAGE_ID", "Notion parent page ID"),
            ("SUPABASE_ACCESS_TOKEN", "Supabase access token"),
            ("RESEARCH_PAPERS_DIR", "Research papers directory"),
            ("RESEARCH_HUB_EXECUTABLE", "Research Hub executable"),
        ]
        for var, description in other_vars:
            # Imprime un tick (✓) si la variable está cargada, o una cruz (✗) si no.
            print(f"✓ {description} loaded" if os.getenv(var) else f"✗ {description} not found")
        
        if os.getenv("RESEARCH_HUB_EXECUTABLE") and not os.path.exists(os.getenv("RESEARCH_HUB_EXECUTABLE")):
            print(f"✗ WARNING: Research Hub executable not found at specified path.")

        print("============================")


class PlatformConfig:
    """Define las plataformas que la aplicación soporta para la investigación."""
    # Lista fija de plataformas soportadas en el código.
    SUPPORTED_PLATFORMS = ["web", "youtube", "github", "arxiv", "hackernews", "supabase", "research_hub"]

    @staticmethod
    def get_supported_platforms() -> List[str]:
        """Devuelve una copia de la lista de plataformas soportadas."""
        return PlatformConfig.SUPPORTED_PLATFORMS.copy()

    @staticmethod
    def is_platform_supported(platform: str) -> bool:
        """Comprueba si una plataforma dada está en la lista de soportadas."""
        return platform in PlatformConfig.SUPPORTED_PLATFORMS
