# ai_trend_researcher.py
# -*- coding: utf-8 -*-

# Importa el módulo 'asyncio' para manejar operaciones asíncronas (ejecución concurrente).
import asyncio
# Importa el módulo 'sys' para terminar la aplicación de forma controlada.
import sys
# Importa 'datetime' para trabajar con fechas y horas (ej. para timestamps).
from datetime import datetime
# Importa herramientas de 'typing' para anotaciones de tipo.
from typing import Dict, List, Any

# Importa 'load_dotenv' de la biblioteca python-dotenv para cargar variables del archivo .env.
from dotenv import load_dotenv

# Importa los módulos personalizados de la aplicación.
from keyword_manager import KeywordManager
from mcp_client_manager import MCPClientManager
from platform_handlers import PlatformHandlerFactory
from data_processor import KeywordExtractor, DataAnalyzer
from report_generator import ReportManager
from config_manager import ServerConfig, AppConfig, PlatformConfig
from ai_client_manager import AIClientManager

# Ejecuta la función para cargar las variables de entorno del archivo .env al inicio del script.
load_dotenv()


class AITrendResearcher:
    """
    Clase principal que actúa como orquestador del investigador de tendencias de IA.
    Su arquitectura es modular, utilizando diferentes gestores para cada tarea.
    """

    def __init__(self):
        """Constructor de la clase. Inicializa todos los componentes necesarios."""
        # Imprime el estado de la configuración y valida las variables requeridas.
        AppConfig.print_config_status()
        missing_vars = AppConfig.validate_required_env_vars()
        if missing_vars:
            print("\n✗ Error: Faltan las siguientes variables de entorno requeridas:")
            for var in missing_vars:
                print(f"  - {var}")
            print("\nPor favor, defínelas en tu archivo .env y vuelve a intentarlo.")
            sys.exit(1)

        # Inicializa el cliente de IA según la configuración en .env.
        ai_provider = AppConfig.get_ai_provider()
        api_key = AppConfig.get_api_key(ai_provider)
        ai_model = AppConfig.get_ai_model(ai_provider)
        self.ai_client_manager = AIClientManager(provider=ai_provider, api_key=api_key, model=ai_model)

        # Inicializa los componentes principales de la lógica de negocio.
        self.keyword_manager = KeywordManager()

        # Carga las configuraciones de los servidores MCP y la lista de plataformas soportadas.
        server_configs = ServerConfig.get_server_configs()
        self.platforms = PlatformConfig.get_supported_platforms()

        # Inicializa los gestores que dependen de otras configuraciones.
        self.mcp_manager = MCPClientManager(server_configs)
        self.keyword_extractor = KeywordExtractor(self.ai_client_manager)
        self.data_analyzer = DataAnalyzer(self.ai_client_manager) # Pasa el cliente de IA al analizador

        # El gestor de reportes se inicializará más tarde, una vez que los clientes MCP estén conectados.
        self.report_manager = None

    async def run_daily_research(self) -> str:
        """
        Ejecuta el ciclo completo de investigación diaria.
        Retorna la ruta del archivo de informe generado.
        """
        print(f"\n🚀 Starting AI trend research - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        try:
            # 1. Conectar a todos los servidores MCP habilitados.
            await self.mcp_manager.connect_all_servers()

            # 2. Filtrar para usar solo las plataformas cuyos servidores se conectaron con éxito.
            active_platforms = [p for p in self.platforms if self.mcp_manager.is_platform_available(p)]
            print(f"🌐 Servidores MCP activos: {active_platforms}")

            # 3. Obtener clientes específicos para Notion y Supabase que se usarán en los reportes.
            notion_client = self.mcp_manager.get_client("notion")
            supabase_client = self.mcp_manager.get_client("supabase")
            notion_parent_id = AppConfig.get_notion_parent_page_id()

            # 4. Inicializar el gestor de reportes con los clientes ya conectados.
            self.report_manager = ReportManager(
                reports_dir=AppConfig.get_reports_directory(),
                notion_client=notion_client,
                notion_parent_id=notion_parent_id,
                supabase_client=supabase_client,
            )

            # 5. Cargar las palabras clave que se van a investigar.
            active_keywords = self._load_active_keywords()
            print(f"🔑 Investigando {len(active_keywords)} keywords en {len(active_platforms)} plataformas: {active_keywords}")

            # 6. Realizar la investigación en todas las plataformas activas para cada palabra clave.
            research_data = await self._conduct_research(active_keywords, platforms=active_platforms)

            # 7. Procesar los datos recolectados.
            print("\n🔄 Procesando datos y extrayendo nuevas keywords...")
            new_keywords = await self.keyword_extractor.extract_keywords(research_data)
            keyword_scores = self.data_analyzer.score_keywords(new_keywords, research_data)
            summary = self.data_analyzer.calculate_summary_stats(research_data, new_keywords)
            print("🧠 Generando recomendaciones con IA...")
            recommendations = await self.data_analyzer.generate_recommendations(research_data, new_keywords)

            # 8. Actualizar la base de datos de palabras clave con los nuevos hallazgos.
            self._update_keywords(new_keywords, keyword_scores, active_keywords)

            # 9. Generar todos los informes (JSON, Notion, Supabase).
            print("\n📝 Generando informes...")
            report_file = await self.report_manager.generate_all_reports(
                research_data, new_keywords, summary, recommendations
            )
            print(f"📄 Informe local generado: {report_file}")

            # 10. Registrar que la ejecución de hoy se ha completado.
            self.keyword_manager.record_execution(active_keywords, "completed", len(new_keywords))

            print("\n✅ Daily research completed successfully!")
            return report_file

        except Exception as e:
            # Captura cualquier error que ocurra durante el proceso para registrarlo.
            print(f"❌ Error fatal en la investigación diaria: {e}")
            raise # Vuelve a lanzar la excepción para que el programa principal la maneje.
        # El cierre de los clientes MCP se gestiona en la función 'main' para asegurar que siempre se ejecute.

    def _load_active_keywords(self) -> List[str]:
        """Carga las palabras clave activas desde el archivo. Si está vacío, lo refresca desde la lista maestra."""
        active_keywords = self.keyword_manager.load_active_keywords()
        if not active_keywords:
            print("No se encontraron keywords activas. Refrescando desde la lista maestra...")
            active_keywords = self.keyword_manager.refresh_active_keywords()
        return active_keywords

    async def _conduct_research(self, keywords: List[str], platforms: List[str]) -> List[Dict[str, Any]]:
        """Realiza la investigación iterando sobre cada palabra clave y cada plataforma."""
        all_research_data: List[Dict[str, Any]] = []
        
        total_tasks = len(keywords) * len(platforms)
        print(f"\n🔍 Realizando {total_tasks} tareas de investigación...")

        # Bucle anidado para investigar cada combinación de palabra clave y plataforma.
        for keyword in keywords:
            for platform in platforms:
                try:
                    # Llama al método que realiza la investigación para una combinación específica.
                    result = await self._research_platform_keyword(platform, keyword)
                    all_research_data.append(result)
                    # Informa al usuario sobre el resultado.
                    if result.get("error"):
                        print(f"  ✗ Error en '{keyword}' en {platform}: {result['error']}")
                    else:
                        item_count = len(result.get("results", []))
                        print(f"  ✓ Completado '{keyword}' en {platform} ({item_count} resultados)")
                except Exception as e:
                    # Si ocurre un error inesperado, lo registra y continúa con la siguiente.
                    print(f"  ✗ Error inesperado investigando '{keyword}' en {platform}: {e}")
                    # Añade un registro de error estandarizado a los datos de investigación.
                    all_research_data.append({
                        "platform": platform,
                        "keyword": keyword,
                        "timestamp": datetime.now().isoformat(),
                        "results": [],
                        "new_keywords": [],
                        "sentiment_score": 0.0,
                        "engagement_metrics": {},
                        "error": str(e),
                    })

        return all_research_data

    async def _research_platform_keyword(self, platform: str, keyword: str) -> Dict[str, Any]:
        """Investiga una palabra clave en una plataforma específica usando el manejador (handler) apropiado."""
        if self.mcp_manager.is_platform_available(platform):
            try:
                # La 'fábrica' crea el objeto manejador correcto para la plataforma (ej. YouTubeHandler).
                handler = PlatformHandlerFactory.create_handler(platform, self.ai_client_manager)
                # Obtiene el cliente MCP para esa plataforma.
                client = self.mcp_manager.get_client(platform)
                # Obtiene la configuración específica de esa plataforma.
                config = ServerConfig.get_server_configs().get(platform, {})
                # Llama al método 'research_keyword' del manejador, que contiene la lógica específica de la plataforma.
                return await handler.research_keyword(client, keyword, config)
            except Exception as e:
                print(f"Error con el manejador de {platform}: {e}")

        # Si la plataforma no está disponible o hubo un error, devuelve un resultado de error.
        return {
            "platform": platform,
            "keyword": keyword,
            "timestamp": datetime.now().isoformat(),
            "results": [],
            "new_keywords": [],
            "sentiment_score": 0.0,
            "engagement_metrics": {},
            "error": f"Platform {platform} not available or handler failed",
        }

    def _update_keywords(self, new_keywords: List[str], keyword_scores: Dict[str, int], active_keywords: List[str]):
        """Añade nuevas palabras clave al archivo maestro y marca las usadas como 'utilizadas hoy'."""
        if not new_keywords:
            print("ℹ️ No se añadieron nuevas keywords en esta ejecución.")
        else:
            print("\n💾 Actualizando base de datos de keywords...")

        for keyword, score in keyword_scores.items():
            # Intenta añadir la nueva palabra clave.
            added = self.keyword_manager.add_new_keyword(keyword, score, "discovered", "daily_research")
            if added:
                print(f"  + Nueva keyword añadida: '{keyword}' (score: {score})")
        # Marca las palabras clave de esta ejecución para que no se seleccionen inmediatamente de nuevo.
        self.keyword_manager.mark_keywords_used(active_keywords)


# --- Punto de entrada principal y funciones de ayuda ---

async def main():
    """Función principal que inicializa el investigador y maneja el ciclo de vida de la aplicación."""
    researcher = AITrendResearcher()

    def signal_handler():
        """Función que se ejecuta cuando se recibe una señal de apagado (Ctrl+C)."""
        print("\n🛑 Señal de apagado recibida - forzando limpieza...")
        # Lanza una tarea asíncrona para limpiar y salir de forma forzada.
        asyncio.create_task(force_cleanup_and_exit(researcher))

    # Configura manejadores de señales para un cierre limpio (SIGTERM para sistemas Unix, SIGINT para Ctrl+C).
    if hasattr(asyncio, "create_task"):
        import signal
        for sig in [signal.SIGTERM, signal.SIGINT]:
            try:
                # Asocia la función signal_handler a las señales.
                asyncio.get_event_loop().add_signal_handler(sig, signal_handler)
            except (NotImplementedError, AttributeError):
                # Algunos sistemas (como Windows) pueden no soportar esto.
                pass

    try:
        # Ejecuta la lógica principal de investigación.
        await researcher.run_daily_research()
    except KeyboardInterrupt:
        print("\n🛑 Interrumpido por el usuario")
    except asyncio.CancelledError:
        print("\n🛑 Operación cancelada")
    except Exception as e:
        print(f"❌ Error en la ejecución principal: {e}")
        # En un entorno de producción, aquí se podría registrar el traceback completo.
    finally:
        # Este bloque 'finally' se ejecuta siempre, tanto si hay errores como si no.
        # Es el lugar ideal para la limpieza de recursos.
        print("\n🏁 Finalizando ejecución, cerrando todos los clientes MCP...")
        try:
            # Cierra todos los clientes MCP de forma secuencial con un tiempo de espera.
            await asyncio.wait_for(researcher.mcp_manager.close_all_clients(), timeout=10.0)
        except asyncio.TimeoutError:
            print("Aviso: Timeout durante la limpieza en main")
        except asyncio.CancelledError:
            print("Aviso: La limpieza fue cancelada en main")
        except Exception as e:
            print(f"Aviso: Error durante la limpieza en main: {e}")


async def force_cleanup_and_exit(researcher: AITrendResearcher):
    """Realiza una limpieza rápida y forzada y termina el proceso."""
    print("⚠️ Forzando salida...")
    try:
        # Intenta cerrar los clientes MCP con un tiempo de espera muy corto.
        await asyncio.wait_for(researcher.mcp_manager.close_all_clients(), timeout=5.0)
    except Exception:
        # Ignora cualquier error durante el cierre forzado.
        pass
    # Usa os._exit(1) para terminar el proceso inmediatamente.
    import os as _os
    _os._exit(1)


# Este es el punto de entrada estándar para un script de Python.
if __name__ == "__main__":
    # Inicia el bucle de eventos de asyncio y ejecuta la función 'main'.
    asyncio.run(main())
