# report_generator.py
# -*- coding: utf-8 -*-

import os
import json
import csv
import asyncio
from datetime import datetime
from typing import Dict, List, Any, Optional

# --- Clases Base (sin cambios) ---

class BaseReportGenerator:
    def __init__(self, reports_dir: str):
        self.reports_dir = reports_dir
        os.makedirs(self.reports_dir, exist_ok=True)
    
    def get_timestamp_str(self) -> str:
        return datetime.now().strftime("%Y%m%d_%H%M%S")

# =======================================================================
# BLOQUE DE CÓDIGO CORREGIDO
# =======================================================================

class LocalFileReportGenerator(BaseReportGenerator):
    """Genera informes en archivos locales (JSON y CSV)."""
    async def create_local_report(self, report_data: Dict[str, Any]) -> str:
        timestamp = self.get_timestamp_str()
        file_path = os.path.join(self.reports_dir, f"ai_trend_report_{timestamp}.json")
        csv_path = os.path.join(self.reports_dir, f"research_results_{timestamp}.csv")

        try:
            # --- Generación de JSON (sin cambios) ---
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(report_data, f, indent=4, ensure_ascii=False)
            print(f"📄 Informe JSON guardado en: {file_path}")
            
            # --- Generación de CSV (CORREGIDA) ---
            research_results = report_data.get("research_data", [])
            if research_results:
                # 1. Recolectar TODAS las claves posibles de TODOS los resultados.
                all_keys = set()
                for result in research_results:
                    if isinstance(result, dict):
                        all_keys.update(result.keys())
                
                # 2. Si no hay claves, no hacer nada.
                if not all_keys:
                    return file_path

                # 3. Usar el conjunto de todas las claves como fieldnames.
                with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=sorted(list(all_keys))) # Ordenar para consistencia
                    writer.writeheader()
                    # El writer ahora conoce la clave 'error' y no fallará.
                    writer.writerows(research_results)
                print(f"📄 Informe CSV guardado en: {csv_path}")

            return file_path
        except Exception as e:
            print(f"🔥 Error al generar el informe local: {e}")
            return ""

# =======================================================================
# FIN DEL BLOQUE CORREGIDO
# =======================================================================

class NotionReportGenerator(BaseReportGenerator):
    """Genera un informe en una página de Notion."""
    def __init__(self, notion_client: Any, notion_parent_id: str, reports_dir: str):
        super().__init__(reports_dir)
        self.notion_client = notion_client
        self.parent_page_id = notion_parent_id

    async def create_notion_report(self, report_data: Dict[str, Any]):
        if not self.notion_client or not self.parent_page_id:
            return
        
        print("📄 Generando informe en Notion...")
        try:
            await asyncio.sleep(1) # Simula la llamada a la API
            print("✅ Informe de Notion generado (simulado).")
        except Exception as e:
            print(f"🔥 Error al generar el informe de Notion: {e}")

class SupabaseReportGenerator(BaseReportGenerator):
    """Guarda los resultados de la investigación en una tabla de Supabase."""
    def __init__(self, supabase_client: Any, reports_dir: str):
        super().__init__(reports_dir)
        self.supabase_client = supabase_client
    
    async def create_supabase_report(self, report_data: Dict[str, Any]):
        if not self.supabase_client:
            return
            
        print("💾 Guardando resultados en Supabase...")
        try:
            await asyncio.sleep(1) # Simula la llamada a la API
            print("✅ Resultados guardados en Supabase (simulado).")
        except Exception as e:
            print(f"🔥 Error al guardar en Supabase: {e}")


class ReportManager:
    """
    Orquesta la generación de múltiples tipos de informes.
    """
    def __init__(
        self,
        reports_dir: str,
        notion_client: Optional[Any] = None,
        notion_parent_id: Optional[str] = None,
        supabase_client: Optional[Any] = None,
    ):
        self.reports_dir = reports_dir
        self.local_reporter = LocalFileReportGenerator(reports_dir)
        self.notion_reporter = None
        self.supabase_reporter = None

        if notion_client and notion_parent_id:
            self.notion_reporter = NotionReportGenerator(
                notion_client=notion_client,
                notion_parent_id=notion_parent_id,
                reports_dir=reports_dir
            )
        
        if supabase_client:
            self.supabase_reporter = SupabaseReportGenerator(
                supabase_client=supabase_client,
                reports_dir=reports_dir
            )

    async def generate_all_reports(
        self,
        research_data: List[Dict],
        new_keywords: List[str],
        summary: Dict,
        recommendations: str,
    ) -> str:
        """
        Genera todos los informes configurados (local, Notion, Supabase) de forma concurrente.
        """
        report_data = {
            "metadata": {
                "report_generated_at": datetime.now().isoformat(),
                "total_results": len(research_data),
            },
            "summary_and_recommendations": {
                "summary": summary,
                "recommendations": recommendations,
            },
            "newly_discovered_keywords": new_keywords,
            "research_data": research_data,
        }

        tasks = []
        
        local_report_task = self.local_reporter.create_local_report(report_data)
        tasks.append(local_report_task)

        if self.supabase_reporter:
            tasks.append(self.supabase_reporter.create_supabase_report(report_data))
        
        if self.notion_reporter:
            tasks.append(self.notion_reporter.create_notion_report(report_data))
            
        if not tasks:
            return ""

        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        local_path = ""
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                print(f"🔥 Ocurrió un error en una tarea de generación de informes: {result}")
            elif i == 0:
                 local_path = result if result else ""

        return local_path
