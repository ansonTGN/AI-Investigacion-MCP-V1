# ai_trend_researcher.py
# -*- coding: utf-8 -*-

import asyncio
import sys
import os
import signal
import argparse
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple, Iterable

from dotenv import load_dotenv

from keyword_manager import KeywordManager
from mcp_client_manager import MCPClientManager
from platform_handlers import PlatformHandlerFactory
from data_processor import KeywordExtractor, DataAnalyzer
from report_generator import ReportManager
from config_manager import ServerConfig, AppConfig, PlatformConfig
from ai_client_manager import AIClientManager

load_dotenv()


# ----------------------------- utilidades -----------------------------

def env_int(name: str, default: int) -> int:
    try:
        v = os.getenv(name)
        return int(v) if v is not None else default
    except ValueError:
        return default

def env_float(name: str, default: float) -> float:
    try:
        v = os.getenv(name)
        return float(v) if v is not None else default
    except ValueError:
        return default

def env_bool(name: str, default: bool) -> bool:
    v = (os.getenv(name, str(default)) or "").strip().lower()
    return v in ("1", "true", "t", "yes", "y", "on")

def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def log(msg: str) -> None:
    print(f"[{now_str()}] {msg}", flush=True)


# --------------------------- núcleo investigador ---------------------------

class AITrendResearcher:
    """
    Orquestador principal del flujo de investigación de tendencias de IA.
    Mejora: control de concurrencia, timeouts, reintentos y CLI.
    """

    def __init__(
        self,
        platforms_filter: Optional[Iterable[str]] = None,
        exclude_platforms: Optional[Iterable[str]] = None,
        per_task_timeout: float = 35.0,
        retries: int = 1,
        concurrency: int = 4,
        keywords_limit: Optional[int] = None,
    ):
        # Estado configuración / validaciones
        AppConfig.print_config_status()
        missing_vars = AppConfig.validate_required_env_vars()
        if missing_vars:
            log("✗ Faltan variables de entorno requeridas:")
            for var in missing_vars:
                log(f"  - {var}")
            log("Por favor, complétalas en tu .env")
            # No abortamos aquí: el sistema puede operar con subset (ej. sin Notion/Supabase)
            # pero si faltan claves críticas de proveedor de IA, AIClientManager fallará.

        # Cliente de IA
        ai_provider = AppConfig.get_ai_provider()
        api_key = AppConfig.get_api_key(ai_provider)
        ai_model = AppConfig.get_ai_model(ai_provider)
        self.ai_client_manager = AIClientManager(provider=ai_provider, api_key=api_key, model=ai_model)

        # Palabras clave
        self.keyword_manager = KeywordManager()

        # Servidores MCP / plataformas
        server_configs = ServerConfig.get_server_configs()
        supported = set(PlatformConfig.get_supported_platforms())
        wanted = set(p.strip() for p in (platforms_filter or supported))
        excluded = set(p.strip() for p in (exclude_platforms or []))
        self.platforms: List[str] = [p for p in wanted if p in supported and p not in excluded]

        # Gestores
        self.mcp_manager = MCPClientManager(server_configs)
        self.keyword_extractor = KeywordExtractor(self.ai_client_manager)
        self.data_analyzer = DataAnalyzer(self.ai_client_manager)
        self.report_manager: Optional[ReportManager] = None

        # Parámetros ejecución
        self.per_task_timeout = float(per_task_timeout)
        self.retries = int(max(0, retries))
        self.semaphore = asyncio.Semaphore(int(max(1, concurrency)))
        self.keywords_limit = int(keywords_limit) if keywords_limit else None

    async def run_daily_research(self) -> str:
        log(f"🚀 Starting AI trend research - {now_str()}")

        try:
            # 1) Conectar MCP
            await self.mcp_manager.connect_all_servers()

            # 2) Plataformas activas realmente disponibles
            active_platforms = [p for p in self.platforms if self.mcp_manager.is_platform_available(p)]
            if not active_platforms:
                log("⚠️ No hay servidores MCP activos; nada que hacer.")
                return ""

            log(f"🌐 Servidores MCP activos: {active_platforms}")

            # 3) Clientes opcionales para reportes
            notion_client = self.mcp_manager.get_client("notion")
            supabase_client = self.mcp_manager.get_client("supabase")
            notion_parent_id = AppConfig.get_notion_parent_page_id()

            # 4) Gestor de reportes
            self.report_manager = ReportManager(
                reports_dir=AppConfig.get_reports_directory(),
                notion_client=notion_client,
                notion_parent_id=notion_parent_id,
                supabase_client=supabase_client,
            )

            # 5) Cargar keywords activas
            active_keywords = self._load_active_keywords()
            if self.keywords_limit is not None:
                active_keywords = active_keywords[: self.keywords_limit]
            log(f"🔑 Investigando {len(active_keywords)} keywords en {len(active_platforms)} plataformas: {active_keywords}")

            # 6) Investigación concurrente con

