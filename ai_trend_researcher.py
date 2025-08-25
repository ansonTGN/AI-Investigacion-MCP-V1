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
            log("Por favor, complétalas en tu .env o deshabilita las plataformas asociadas.")
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
        self.server_configs = ServerConfig.get_server_configs()
        supported = set(PlatformConfig.get_supported_platforms())
        wanted = set(p.strip() for p in (platforms_filter or supported))
        excluded = set(p.strip() for p in (exclude_platforms or []))
        self.platforms: List[str] = [p for p in wanted if p in supported and p not in excluded]

        # Gestores
        self.mcp_manager = MCPClientManager(self.server_configs)
        self.keyword_extractor = KeywordExtractor(self.ai_client_manager)
        self.data_analyzer = DataAnalyzer(self.ai_client_manager)
        self.report_manager: Optional[ReportManager] = None

        # Parámetros ejecución
        self.per_task_timeout = float(per_task_timeout)
        self.retries = int(max(0, retries))
        self.semaphore = asyncio.Semaphore(int(max(1, concurrency)))
        self.keywords_limit = int(keywords_limit) if keywords_limit else None

    # =======================================================================
    # BLOQUE DE CÓDIGO CORREGIDO Y COMPLETADO
    # =======================================================================
    async def run_daily_research(self) -> str:
        log(f"🚀 Starting AI trend research - {now_str()}")
        report_path = ""
        try:
            # 1) Conectar MCP
            await self.mcp_manager.connect_all_servers()

            # 2) Plataformas activas realmente disponibles
            active_platforms = [p for p in self.platforms if self.mcp_manager.is_platform_available(p)]
            if not active_platforms:
                log("⚠️ No hay servidores MCP activos; nada que hacer.")
                return ""

            log(f"🌐 Servidores MCP activos: {', '.join(active_platforms)}")

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

            # 5) Cargar keywords activas desde terminos.txt
            active_keywords = self._load_active_keywords()
            if self.keywords_limit is not None:
                active_keywords = active_keywords[: self.keywords_limit]
            
            if not active_keywords:
                log("⚠️ No se encontraron keywords en 'terminos.txt'. El archivo está vacío o no existe.")
                return ""
                
            log(f"🔑 Investigando {len(active_keywords)} keywords en {len(active_platforms)} plataformas: {active_keywords}")

            # 6) Investigación concurrente
            tasks = []
            for keyword in active_keywords:
                for platform in active_platforms:
                    task = asyncio.create_task(self._research_single_keyword(keyword, platform))
                    tasks.append(task)
            
            log(f"🔄 Lanzando {len(tasks)} tareas de investigación...")
            research_results: List[Dict] = await asyncio.gather(*tasks)

            # 7) Procesar y analizar resultados
            log("📊 Analizando resultados y extrayendo insights...")
            valid_results = [r for r in research_results if r and not r.get("error")]
            
            new_keywords_list = await self.keyword_extractor.extract_keywords(valid_results)
            scored_keywords = self.data_analyzer.score_keywords(new_keywords_list, valid_results)
            summary_stats = self.data_analyzer.calculate_summary_stats(research_results, new_keywords_list)
            recommendations = await self.data_analyzer.generate_recommendations(valid_results, new_keywords_list)

            # 8) Actualizar base de datos de keywords (Opcional, se mantiene la lógica)
            log("💾 Actualizando el catálogo de keywords...")
            for kw, score in scored_keywords.items():
                self.keyword_manager.add_new_keyword(kw, score, "discovered", "llm_extraction")
            
            self.keyword_manager.mark_keywords_used(active_keywords)
            self.keyword_manager.record_execution(active_keywords, "completed", len(new_keywords_list))
            
            # 9) Generar informes
            log("📄 Generando informes...")
            report_path = await self.report_manager.generate_all_reports(
                research_data=research_results,
                new_keywords=new_keywords_list,
                summary=summary_stats,
                recommendations=recommendations,
            )
            log(f"🎉 Investigación completada con éxito. Informe local: {report_path}")

        except Exception as e:
            log(f"❌ Error catastrófico en el flujo principal: {e}")
            import traceback
            traceback.print_exc()

        finally:
            # Este bloque se asegura de que las conexiones se cierren siempre
            log("🔌 Cerrando todas las conexiones MCP...")
            await self.mcp_manager.close_all_clients()
            return report_path

    # =======================================================================
    # FUNCIÓN MODIFICADA PARA LEER DESDE terminos.txt
    # =======================================================================
    def _load_active_keywords(self) -> List[str]:
        """Carga las keywords directamente desde el archivo 'terminos.txt'."""
        keywords_file = "terminos.txt"
        log(f"Cargando keywords desde '{keywords_file}'...")
        if not os.path.exists(keywords_file):
            log(f"🔥 El archivo '{keywords_file}' no se encuentra en el directorio.")
            return []
        
        try:
            with open(keywords_file, 'r', encoding='utf-8') as f:
                # Lee cada línea, quita espacios/saltos de línea y filtra las que queden vacías
                keywords = [line.strip() for line in f if line.strip()]
            return keywords
        except Exception as e:
            log(f"🔥 Error al leer el archivo de keywords '{keywords_file}': {e}")
            return []

    async def _research_single_keyword(self, keyword: str, platform: str) -> Dict[str, Any]:
        """Ejecuta la investigación para una única combinación de keyword y plataforma con reintentos."""
        async with self.semaphore:
            for attempt in range(self.retries + 1):
                try:
                    handler = PlatformHandlerFactory.create_handler(platform, self.ai_client_manager)
                    client = self.mcp_manager.get_client(platform)
                    config = self.server_configs.get(platform, {})
                    
                    if not client:
                        raise ConnectionError(f"Cliente para {platform} no está disponible.")

                    result = await asyncio.wait_for(
                        handler.research_keyword(client, keyword, config),
                        timeout=self.per_task_timeout
                    )
                    return result

                except asyncio.TimeoutError:
                    log(f"⏳ Timeout investigando '{keyword}' en '{platform}' (intento {attempt+1})")
                    if attempt >= self.retries:
                        return {"platform": platform, "keyword": keyword, "error": "Timeout after all retries"}
                except Exception as e:
                    log(f"🔥 Error investigando '{keyword}' en '{platform}' (intento {attempt+1}): {e}")
                    if attempt >= self.retries:
                        return {"platform": platform, "keyword": keyword, "error": str(e)}
                
                if attempt < self.retries:
                    await asyncio.sleep(2.0 * (attempt + 1)) # Backoff exponencial simple
            
            return {"platform": platform, "keyword": keyword, "error": "Unknown error after all retries"}

# =======================================================================
# FIN DEL BLOQUE MODIFICADO
# =======================================================================

async def main(args):
    """Punto de entrada principal para la ejecución del script."""
    researcher = AITrendResearcher(
        platforms_filter=args.platforms,
        exclude_platforms=args.exclude,
        concurrency=args.concurrency,
        per_task_timeout=args.timeout,
        retries=args.retries,
        keywords_limit=args.limit_keywords
    )
    
    # Manejo de cierre gradual
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _shutdown_handler():
        log("Señal de interrupción recibida, iniciando cierre gradual...")
        stop_event.set()

    if sys.platform != "win32":
        loop.add_signal_handler(signal.SIGINT, _shutdown_handler)
        loop.add_signal_handler(signal.SIGTERM, _shutdown_handler)

    try:
        research_task = asyncio.create_task(researcher.run_daily_research())
        stop_wait_task = asyncio.create_task(stop_event.wait())
        
        done, pending = await asyncio.wait(
            {research_task, stop_wait_task},
            return_when=asyncio.FIRST_COMPLETED
        )

        if stop_wait_task in done:
            log("Cierre solicitado. Cancelando tareas pendientes...")
            research_task.cancel()
            await asyncio.sleep(1) # Dar tiempo para que la cancelación se propague
        
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)

    except asyncio.CancelledError:
        log("Tareas principales canceladas.")
    finally:
        if sys.platform != "win32":
            loop.remove_signal_handler(signal.SIGINT)
            loop.remove_signal_handler(signal.SIGTERM)
        log("Ejecución finalizada.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Motor de Investigación de Tendencias de IA.")
    parser.add_argument("-p", "--platforms", nargs='+', help="Lista de plataformas a investigar (ej. youtube github). Por defecto todas.")
    parser.add_argument("-e", "--exclude", nargs='+', help="Lista de plataformas a excluir (ej. web arxiv).")
    parser.add_argument("-c", "--concurrency", type=int, default=4, help="Número de tareas de investigación concurrentes.")
    parser.add_argument("-t", "--timeout", type=float, default=45.0, help="Timeout en segundos para cada tarea individual.")
    parser.add_argument("-r", "--retries", type=int, default=1, help="Número de reintentos por tarea en caso de fallo.")
    parser.add_argument("-l", "--limit-keywords", type=int, help="Limita el número de keywords a investigar.")
    
    cli_args = parser.parse_args()
    
    try:
        asyncio.run(main(cli_args))
    except KeyboardInterrupt:
        log("Interrupción por teclado detectada. Saliendo.")

