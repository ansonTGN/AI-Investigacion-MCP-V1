# report_generator.py

# Importa el módulo 'json' para trabajar con datos JSON.
import json
# Importa el módulo 'os' para interactuar con el sistema de archivos (crear directorios y archivos).
import os
# Importa 'datetime' para obtener la fecha y hora actuales.
from datetime import datetime
# Importa herramientas de 'typing' para anotaciones de tipo.
from typing import Dict, List, Any, Optional
# Importa la clase 'RemoteMCPClient' para interactuar con los servidores de Notion y Supabase.
from mcp_client_manager import RemoteMCPClient


class JSONReportGenerator:
    """Genera informes de la investigación en formato de archivo JSON."""
    
    def __init__(self, reports_dir: str = "reports"):
        """Constructor. Define el directorio donde se guardarán los informes."""
        self.reports_dir = reports_dir
    
    def generate_report(self, research_data: List[Dict], new_keywords: List[str], 
                       summary: Dict[str, Any], recommendations: List[str]) -> str:
        """Crea un archivo JSON con todos los datos de la investigación."""
        today = datetime.now().strftime("%Y-%m-%d")
        # Define la estructura del informe.
        report = {
            "date": today,
            "summary": summary,
            "new_keywords": new_keywords,
            "recommendations": recommendations,
            "detailed_results": research_data
        }
        
        # Construye la ruta completa del archivo.
        report_file = os.path.join(self.reports_dir, f"ai_trends_{today}.json")
        # Asegura que el directorio de informes exista.
        os.makedirs(self.reports_dir, exist_ok=True)
        
        # Abre el archivo en modo escritura y vuelca el diccionario del informe como JSON.
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2) # indent=2 para formato legible.
        
        return report_file # Devuelve la ruta del archivo creado.


class NotionReportGenerator:
    """Genera informes como una nueva página en Notion."""
    
    def __init__(self, notion_client: Optional[RemoteMCPClient], parent_page_id: str):
        """Constructor. Necesita el cliente MCP de Notion y el ID de la página padre."""
        self.notion_client = notion_client
        self.parent_page_id = parent_page_id
    
    async def create_notion_report(self, report: Dict) -> Any:
        """Crea una página en Notion con el contenido del informe."""
        # Si no hay cliente o ID de página, no se puede crear el informe.
        if not self.notion_client or not self.parent_page_id:
            print("Aviso: Cliente de Notion o ID de página padre no disponible. Omitiendo informe de Notion.")
            return None
        
        try:
            today = report.get("date", datetime.now().strftime("%Y-%m-%d"))
            page_title = f"Informe de Tendencias IA - {today}"
            
            print("  - Creando bloques de contenido para Notion...")
            blocks = self._create_notion_blocks(report)
            
            # Valida la estructura de los bloques antes de enviarlos a la API de Notion.
            if not self._validate_blocks_structure(blocks):
                print("Error: La estructura de los bloques de Notion generados es inválida. Omitiendo informe.")
                return None
            
            # Llama a la herramienta 'create-page' del servidor MCP de Notion.
            response = await self.notion_client.call_tool(
                "create-page",
                {
                    "parent_type": "page_id",
                    "parent_id": self.parent_page_id,
                    # Las propiedades (como el título) deben ser un string JSON.
                    "properties": json.dumps({
                        "title": {"title": [{"text": {"content": page_title}}]}
                    }),
                    # El contenido (los bloques) también debe ser un string JSON.
                    "children": json.dumps(blocks)
                }
            )
            
            print(f"  ✓ Informe de Notion creado: '{page_title}'")
            return response
            
        except Exception as e:
            print(f"  ✗ Error al crear el informe de Notion: {e}")
            return None
    
    def _validate_blocks_structure(self, blocks: List[Dict]) -> bool:
        """Valida que la estructura básica de los bloques sea correcta para la API de Notion."""
        if not isinstance(blocks, list): return False
        for block in blocks:
            if not isinstance(block, dict): return False
            if "object" not in block or block["object"] != "block": return False
            if "type" not in block: return False
            block_type = block["type"]
            if block_type not in block: return False
        return True
    
    def _create_rich_text(self, text: str) -> List[Dict]:
        """Función de utilidad para crear un objeto 'rich_text' de Notion."""
        return [{"type": "text", "text": {"content": text}}]

    def _create_notion_blocks(self, report: Dict) -> List[Dict]:
        """Crea una lista detallada de bloques de contenido de Notion a partir de los datos del informe."""
        blocks = []
        
        # --- Resumen ---
        blocks.append({"object": "block", "type": "heading_2", "heading_2": {"rich_text": self._create_rich_text("📊 Resumen")}})
        summary = report.get("summary", {})
        summary_text = (
            f"• Resultados Totales: {summary.get('total_items', 0)}\n"
            f"• Nuevas Keywords: {summary.get('new_keywords_count', 0)}\n"
            f"• Ejecuciones con Errores: {summary.get('runs_with_errors', 0)}"
        )
        blocks.append({"object": "block", "type": "paragraph", "paragraph": {"rich_text": self._create_rich_text(summary_text)}})
        
        # --- Recomendaciones ---
        blocks.append({"object": "block", "type": "heading_2", "heading_2": {"rich_text": self._create_rich_text("📋 Recomendaciones")}})
        recommendations = report.get("recommendations", [])
        if recommendations:
            for rec in recommendations:
                if rec and isinstance(rec, str) and rec.strip():
                    blocks.append({"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": self._create_rich_text(rec.strip())}})
        else:
            blocks.append({"object": "block", "type": "paragraph", "paragraph": {"rich_text": self._create_rich_text("No se generaron recomendaciones.")}})
        
        # --- Nuevas Keywords ---
        blocks.append({"object": "block", "type": "heading_2", "heading_2": {"rich_text": self._create_rich_text("🔍 Nuevas Keywords Descubiertas")}})
        new_keywords = report.get("new_keywords", [])
        if new_keywords:
            blocks.append({"object": "block", "type": "paragraph", "paragraph": {"rich_text": self._create_rich_text(", ".join(new_keywords))}})
        else:
            blocks.append({"object": "block", "type": "paragraph", "paragraph": {"rich_text": self._create_rich_text("No se encontraron nuevas keywords.")}})

        # --- Resultados Detallados ---
        blocks.append({"object": "block", "type": "heading_2", "heading_2": {"rich_text": self._create_rich_text("🔬 Resultados Detallados por Plataforma")}})
        platform_results = self._group_results_by_platform(report.get("detailed_results", []))
        
        for platform, results in platform_results.items():
            if not results: continue
            blocks.append({"object": "block", "type": "heading_3", "heading_3": {"rich_text": self._create_rich_text(f" प्लेटफॉर्म: {platform.upper()}")}})
            for i, result in enumerate(results[:3], 1): # Limita a los 3 primeros resultados para ser conciso.
                title = str(result.get('title', result.get('name', 'Sin título'))).strip()
                url = result.get('url', '')
                snippet = (result.get('description', result.get('snippet', '')) or "")[:250].strip()
                
                if not title: continue
                
                toggle_block = {
                    "object": "block",
                    "type": "toggle",
                    "toggle": {
                        "rich_text": self._create_rich_text(f"{i}. {title}"),
                        "children": []
                    }
                }
                
                if url:
                    toggle_block["toggle"]["children"].append({"object": "block", "type": "paragraph", "paragraph": {"rich_text": self._create_rich_text(f"🔗 URL: {url}")}})
                if snippet:
                     toggle_block["toggle"]["children"].append({"object": "block", "type": "paragraph", "paragraph": {"rich_text": self._create_rich_text(f"📝 Extracto: {snippet}...")}})
                
                blocks.append(toggle_block)
        
        return blocks
    
    def _group_results_by_platform(self, detailed_results: List[Dict]) -> Dict[str, List[Dict]]:
        """Agrupa una lista de resultados en un diccionario por plataforma."""
        platform_results = {}
        for data in detailed_results:
            platform = data.get("platform", "unknown")
            if not data.get("error") and data.get("results"):
                if platform not in platform_results:
                    platform_results[platform] = []
                platform_results[platform].extend(data["results"])
        return platform_results


class SupabaseReportGenerator:
    """Genera informes guardando los datos en una tabla de Supabase."""
    
    def __init__(self, supabase_client: Optional[RemoteMCPClient]):
        """Constructor. Necesita el cliente MCP de Supabase."""
        self.supabase_client = supabase_client
    
    async def create_supabase_report(self, report: Dict) -> Any:
        """Inserta los datos del informe en una tabla de la base de datos Supabase."""
        if not self.supabase_client:
            print("Aviso: Cliente de Supabase no disponible. Omitiendo informe de Supabase.")
            return None
        
        try:
            today = report.get("date", datetime.now().strftime("%Y-%m-%d"))
            
            # Define la consulta SQL para insertar los datos.
            # ADVERTENCIA: Este método formatea una cadena SQL. Es seguro en este contexto
            # porque los datos son generados por la propia aplicación, pero para datos
            # externos, se deben usar consultas parametrizadas si el servidor MCP las soporta.
            sql = """
            INSERT INTO ai_trend_reports (date, summary, detailed_results, new_keywords, recommendations)
            VALUES ('{date}', '{summary}', '{detailed_results}', '{new_keywords}', '{recommendations}')
            RETURNING id;
            """
            
            # Prepara los parámetros, convirtiendo los diccionarios/listas a strings JSON
            # y escapando comillas simples para evitar errores de sintaxis SQL.
            params = {
                "date": today,
                "summary": json.dumps(report.get("summary", {}), ensure_ascii=False).replace("'", "''"),
                "detailed_results": json.dumps(report.get("detailed_results", []), ensure_ascii=False).replace("'", "''"),
                "new_keywords": json.dumps(report.get("new_keywords", []), ensure_ascii=False).replace("'", "''"),
                "recommendations": json.dumps(report.get("recommendations", []), ensure_ascii=False).replace("'", "''"),
            }
            # Formatea la consulta SQL con los parámetros.
            query = sql.format(**params)

            # Llama a la herramienta 'execute_sql' del servidor MCP de Supabase.
            response = await self.supabase_client.call_tool("execute_sql", {"query": query})
            
            print(f"  ✓ Informe de Supabase creado para la fecha: {today}")
            return response
            
        except Exception as e:
            print(f"  ✗ Error al crear el informe de Supabase: {e}")
            return None


class ReportManager:
    """Clase de alto nivel que gestiona la generación de todos los tipos de informes."""
    
    def __init__(self, reports_dir: str = "reports", notion_client: Optional[RemoteMCPClient] = None, 
                 notion_parent_id: Optional[str] = None, supabase_client: Optional[RemoteMCPClient] = None):
        """Constructor. Inicializa todos los generadores de informes necesarios."""
        self.json_generator = JSONReportGenerator(reports_dir)
        self.notion_generator = NotionReportGenerator(notion_client, notion_parent_id)
        self.supabase_generator = SupabaseReportGenerator(supabase_client)
    
    async def generate_all_reports(self, research_data: List[Dict], new_keywords: List[str],
                                 summary: Dict[str, Any], recommendations: List[str]) -> str:
        """Orquesta la generación de informes en JSON, Notion y Supabase."""
        # Primero, siempre genera el informe JSON local.
        report_file = self.json_generator.generate_report(
            research_data, new_keywords, summary, recommendations
        )
        
        # Prepara un diccionario unificado con los datos del informe.
        report_data = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "summary": summary,
            "detailed_results": research_data,
            "new_keywords": new_keywords,
            "recommendations": recommendations
        }
        
        # Genera los informes de Notion y Supabase en paralelo si están disponibles.
        tasks = []
        if self.notion_generator:
            tasks.append(self.notion_generator.create_notion_report(report_data))
        if self.supabase_generator:
            tasks.append(self.supabase_generator.create_supabase_report(report_data))
            
        if tasks:
            await asyncio.gather(*tasks)
        
        return report_file # Devuelve la ruta del archivo JSON como confirmación.
