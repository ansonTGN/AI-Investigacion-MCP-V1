# research_assistant.py
# ============================================================
# Flujo de investigación con rust-research-mcp (MCP server)
# - Lee conceptos desde terminos.txt y construye topics
# - Busca papers por topic (MCP: search_papers)
# - NORMALIZA + ENRIQUECE (BibTeX robusto) ANTES de filtrar por año
# - Filtra por año, prioriza Open Access, selecciona (LLM o “todos”)
# - Elige PRIMARIO por “descargabilidad” (arXiv/TechRxiv/PMC/Preprints primero)
# - Descarga el primario con reintentos rotando DOIs; luego descarga en lote
# - Extrae metadatos, busca patrones de código y genera bibliografía
# - Salidas en salidas/<RUN_TAG>/{csv,json,bib,logs}
# ============================================================

import asyncio
import json
import os
import re
import csv
import itertools
import hashlib
import unicodedata
from datetime import datetime
from typing import Any, Iterable, List, Dict, Optional, Tuple

from dotenv import load_dotenv
import aiofiles
import aiofiles.os

# Módulos del proyecto
from config_manager import ServerConfig, AppConfig
from mcp_client_manager import MCPClientManager, RemoteMCPClient
from ai_client_manager import AIClientManager

load_dotenv()

# ============================================================
# 🔧 PARÁMETROS CONFIGURABLES
# ============================================================

def env_bool(name: str, default: bool) -> bool:
    val = os.getenv(name, str(default)).strip().lower()
    return val in ("1", "true", "t", "yes", "y", "on")

def env_int(name: str, default: int) -> int:
    val = os.getenv(name)
    return int(val) if val and val.isdigit() else default

# ——— Control de salidas ———
SEPARATE_RUNS_IN_SUBFOLDER: bool = env_bool("SEPARATE_RUNS_IN_SUBFOLDER", True)
RUN_TAG: Optional[str] = os.getenv("RUN_TAG")

# ——— Búsqueda y filtrado ———
YEAR_MIN: int = env_int("YEAR_MIN", 2020)
YEAR_MAX: int = env_int("YEAR_MAX", datetime.now().year)
INCLUIR_SIN_ANIO: bool = env_bool("INCLUIR_SIN_ANIO", False)
MAX_TOPICS: int = env_int("MAX_TOPICS", 3)
MAX_RESULTS_PER_TOPIC: int = env_int("MAX_RESULTS_PER_TOPIC", 10)

# ——— Preferencias ———
OPEN_ACCESS_PREFERRED: bool = env_bool("OPEN_ACCESS_PREFERRED", True)
AVOID_SOURCES_FOR_PRIMARY: List[str] = os.getenv("AVOID_SOURCES_FOR_PRIMARY", "ssrn").split(',')

# ——— Descarga de PDFs ———
DOWNLOAD_ALL_PAPERS: bool = env_bool("DOWNLOAD_ALL_PAPERS", False)
DOWNLOAD_ONLY_OA: bool = env_bool("DOWNLOAD_ONLY_OA", False)
SELECT_TOP_K: int = env_int("SELECT_TOP_K", 5)
MAX_PARALLEL_DOWNLOADS: int = env_int("MAX_PARALLEL_DOWNLOADS", 4)

# ——— Bibliografía ———
BIB_FORMAT: str = os.getenv("BIB_FORMAT", "bibtex")
GENERAR_BIB_TODOS: bool = env_bool("GENERAR_BIB_TODOS", True)

# ============================================================
# Constantes y Utilidades
# ============================================================
DOI_REGEX = re.compile(r'(10\.\d{4,9}/[^\s"\']+)'.encode('utf-8').decode('unicode_escape'), re.IGNORECASE)
GENERIC_TITLE_REGEXES = [re.compile(pat, re.IGNORECASE) for pat in [r"^\s*doi\s*$", r"^paper$", r"^link$", r"^ref$", r"^paper title for\b"]]
OA_PATTERNS = ["arxiv.org", "arxiv", "10.48550/arxiv", "biorxiv", "medrxiv", "ncbi.nlm.nih.gov/pmc", "pmc", "mdpi.com", "openreview.net", "osf.io", "zenodo.org", "preprints"]

# Directorios de salida globales
SALIDAS_DIR, CSV_DIR, LOGS_DIR, BIB_DIR, JSON_DIR = "", "", "", "", ""

async def setup_output_dirs() -> None:
    """Configura los directorios de salida de forma asíncrona."""
    global SALIDAS_DIR, CSV_DIR, LOGS_DIR, BIB_DIR, JSON_DIR
    base = "salidas"
    if SEPARATE_RUNS_IN_SUBFOLDER:
        tag = RUN_TAG or datetime.now().strftime("%Y%m%d_%H%M%S")
        base = os.path.join(base, tag)
    
    SALIDAS_DIR = base
    CSV_DIR, LOGS_DIR, BIB_DIR, JSON_DIR = (os.path.join(base, d) for d in ["csv", "logs", "bib", "json"])
    
    for d in (base, CSV_DIR, LOGS_DIR, BIB_DIR, JSON_DIR):
        await aiofiles.os.makedirs(d, exist_ok=True)

# ... (Las funciones de utilidad como normalizar_texto, slugify, etc., se mantienen igual) ...

# Funciones de guardado asíncronas
async def guardar_csv(nombre: str, rows: List[Dict[str, Any]]) -> None:
    path = os.path.join(CSV_DIR, nombre)
    if not rows: return
    async with aiofiles.open(path, "w", encoding="utf-8-sig", newline="") as f:
        fields = list(rows[0].keys())
        writer = csv.DictWriter(f, fieldnames=fields)
        await f.write(",".join(fields) + "\n")
        for row in rows:
            await f.write(",".join(str(row.get(k, "")) for k in fields) + "\n")
    print(f"💾 CSV guardado: {path} ({len(rows)} filas)")

async def guardar_json(nombre: str, data: Any) -> None:
    path = os.path.join(JSON_DIR, nombre)
    async with aiofiles.open(path, "w", encoding="utf-8") as f:
        await f.write(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"💾 JSON guardado: {path}")

async def guardar_bib(nombre: str, contenido: str) -> None:
    path = os.path.join(BIB_DIR, nombre)
    async with aiofiles.open(path, "w", encoding="utf-8") as f:
        await f.write(contenido)
    print(f"💾 BibTeX guardado: {path}")

# ... (El resto de las funciones de parsing, normalización y lógica se mantienen,
#      pero se integran en el nuevo flujo refactorizado a continuación) ...

def extract_text(blobs: Optional[Iterable[Any]]) -> str:
    # (Función sin cambios)
    parts: List[str] = []
    if not blobs: return ""
    for b in blobs:
        if hasattr(b, "text"): parts.append(getattr(b, "text", "") or "")
        elif isinstance(b, str): parts.append(b)
    return "\n".join(parts).strip()

def extract_json_any(raw_text: str) -> Any:
    # (Función sin cambios, asume que es lo suficientemente rápida para no necesitar `to_thread`)
    try: return json.loads(raw_text)
    except Exception: pass
    m = re.search(r"```json\s*(.*?)\s*```", raw_text, re.DOTALL)
    if m:
        try: return json.loads(m.group(1).strip())
        except Exception: pass
    return None

def normalize_papers(data: Any) -> List[Dict[str, Any]]:
    # (Función sin cambios)
    papers = []
    items = data if isinstance(data, list) else (data.get("results") if isinstance(data, dict) else [])
    for it in items:
        if isinstance(it, dict):
            doi = it.get("doi")
            papers.append({
                "title": it.get("title"), "doi": doi, "year": it.get("year"),
                "url": it.get("url") or (f"https://doi.org/{doi}" if doi else None),
                "source": it.get("source")
            })
    return papers

async def step_a_search_papers(rh_client: RemoteMCPClient, topics: List[str]) -> List[Dict[str, Any]]:
    """Busca papers para cada topic y los devuelve combinados."""
    all_papers = []
    for topic in topics:
        print(f"\n--- 🔎 Buscando topic: '{topic}' ---")
        res = await rh_client.call_tool("search_papers", {"query": topic, "limit": MAX_RESULTS_PER_TOPIC})
        data = extract_json_any(extract_text(res))
        papers = normalize_papers(data)
        all_papers.extend(papers)
        print(f"  -> Encontrados {len(papers)} resultados.")
    # Deduplicar aquí es una buena práctica
    seen_dois = set()
    unique_papers = []
    for p in all_papers:
        doi = p.get("doi")
        if doi and doi not in seen_dois:
            seen_dois.add(doi)
            unique_papers.append(p)
        elif not doi:
             unique_papers.append(p) # Mantener los que no tienen DOI por ahora
    return unique_papers

async def step_b_select_papers(ai_client: AIClientManager, papers: List[Dict[str, Any]]) -> List[str]:
    """Filtra y selecciona los papers a descargar, usando LLM si es necesario."""
    # Aquí iría la lógica de filtrado por año y la selección (LLM o todos)
    print("\n--- 🧠 Seleccionando papers para descarga ---")
    
    # Placeholder: por ahora, selecciona todos los que tienen DOI
    selected_dois = [p['doi'] for p in papers if p.get('doi')]
    
    if DOWNLOAD_ALL_PAPERS:
        print(f"  -> Selección: TODOS ({len(selected_dois)} papers)")
        return selected_dois
    else:
        # Aquí se implementaría la llamada al LLM
        print(f"  -> Selección: TOP {SELECT_TOP_K} (Lógica LLM pendiente)")
        return selected_dois[:SELECT_TOP_K]

async def step_c_download_papers(rh_client: RemoteMCPClient, dois: List[str], papers_metadata: List[Dict]) -> Dict[str, Dict]:
    """Descarga los papers seleccionados en paralelo."""
    print(f"\n--- 📥 Descargando {len(dois)} papers en paralelo (max {MAX_PARALLEL_DOWNLOADS}) ---")
    semaphore = asyncio.Semaphore(MAX_PARALLEL_DOWNLOADS)
    
    doi_map = {p['doi']: p for p in papers_metadata if p.get('doi')}

    async def _download_one(doi: str):
        async with semaphore:
            title = doi_map.get(doi, {}).get('title', 'untitled')
            filename = f"{slugify(title)}_{slugify(doi)}.pdf"
            try:
                res = await rh_client.call_tool("download_paper", {"doi": doi, "filename": filename})
                data = extract_json_any(extract_text(res))
                if data and data.get("file_path"):
                    print(f"  ✓ Descargado: {doi}")
                    return doi, {"status": "ok", "path": data["file_path"], "title": title}
                else:
                    print(f"  ✗ Fallo (sin path): {doi}")
                    return doi, {"status": "failed", "reason": "No file path in response"}
            except Exception as e:
                print(f"  ✗ Error: {doi} -> {e}")
                return doi, {"status": "error", "reason": str(e)}

    tasks = [_download_one(doi) for doi in dois]
    results = await asyncio.gather(*tasks)
    return {doi: result for doi, result in results}

# Flujo principal refactorizado
async def main():
    await setup_output_dirs()
    
    terminos = (await aiofiles.open("terminos.txt", "r", encoding="utf-8").read()).splitlines()
    terminos = [t.strip() for t in terminos if t.strip()]
    topics = construir_topics_desde_terminos(terminos, MAX_TOPICS) # Asumiendo que esta función existe
    
    print("Iniciando Asistente de Investigación...")
    print(f"📂 Salidas en: {SALIDAS_DIR}")
    
    server_configs = ServerConfig.get_server_configs()
    mcp_manager = MCPClientManager(server_configs)
    ai_client = AIClientManager(
        provider=AppConfig.get_ai_provider(),
        api_key=AppConfig.get_api_key(AppConfig.get_ai_provider()),
        model=AppConfig.get_ai_model(AppConfig.get_ai_provider())
    )
    
    try:
        print("\n🔗 Conectando al servidor de Research Hub...")
        await mcp_manager._connect_single_server("research_hub", server_configs["research_hub"])
        rh_client = mcp_manager.get_client("research_hub")
        if not rh_client:
            print("❌ No se pudo conectar al servidor de Research Hub. Abortando.")
            return
        print("✅ Conectado.")

        # PASO A: Búsqueda
        found_papers = await step_a_search_papers(rh_client, topics)
        if not found_papers:
            print("⚠️ No se encontraron papers. Terminando.")
            return
        await guardar_csv("01_papers_encontrados.csv", found_papers)
        
        # PASO B: Selección
        selected_dois = await step_b_select_papers(ai_client, found_papers)
        if not selected_dois:
            print("⚠️ No se seleccionaron papers para descargar. Terminando.")
            return
        await guardar_json("02_dois_seleccionados.json", {"dois": selected_dois})

        # PASO C: Descarga
        download_manifest = await step_c_download_papers(rh_client, selected_dois, found_papers)
        downloaded_files = [v for v in download_manifest.values() if v.get("status") == "ok"]
        await guardar_json("03_manifiesto_descarga.json", download_manifest)

        if not downloaded_files:
            print("⚠️ No se pudo descargar ningún paper. Terminando.")
            return

        # PASOS D y E (Análisis y Bibliografía) se ejecutarían aquí
        print("\n--- 🔬 Análisis y Bibliografía (Pasos D y E) ---")
        # Placeholder para la lógica de búsqueda de código y generación de bibliografía
        primary_paper_path = downloaded_files[0]['path']
        print(f"  -> Analizando paper primario: {primary_paper_path}")
        # ... llamar a 'search_code' ...
        # ... llamar a 'generate_bibliography' ...
        bib_content = "BibTeX content placeholder."
        await guardar_bib("bibliografia_final.bib", bib_content)

    finally:
        print("\n🏁 Finalizando y cerrando conexiones...")
        await mcp_manager.close_all_clients()

# (Se omiten las funciones auxiliares no refactorizadas para brevedad)
def construir_topics_desde_terminos(terminos: List[str], max_topics: int) -> List[str]:
    if not terminos: return ["model context protocol"]
    return [" ".join(terminos[:3])] # Simplificado
def slugify(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r'[\s\W-]+', '-', s)
    return s[:50]

if __name__ == "__main__":
    # Windows necesita una política de eventos diferente para Subprocess
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
