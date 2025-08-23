# research_assistant.py
# ============================================================
# Flujo de investigación con rust-research-mcp (MCP server)
# 1. Busca papers por temas para descubrir DOIs.
# 2. Descarga los papers seleccionados.
# 3. Vuelve a consultar cada DOI para obtener metadatos enriquecidos (autores, etc.).
# 4. Genera una bibliografía completa con los datos enriquecidos.
# ============================================================

import asyncio
import json
import os
import re
import csv
from datetime import datetime
from typing import Any, Iterable, List, Dict, Optional

from dotenv import load_dotenv
import aiofiles
import aiofiles.os

# Módulos del proyecto
from config_manager import ServerConfig
from mcp_client_manager import MCPClientManager, RemoteMCPClient

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
MAX_TOPICS: int = env_int("MAX_TOPICS", 10)
MAX_RESULTS_PER_TOPIC: int = env_int("MAX_RESULTS_PER_TOPIC", 10)

# ——— Descarga de PDFs ———
DOWNLOAD_ALL_PAPERS: bool = env_bool("DOWNLOAD_ALL_PAPERS", False)
SELECT_TOP_K: int = env_int("SELECT_TOP_K", 5)
MAX_PARALLEL_DOWNLOADS: int = env_int("MAX_PARALLEL_DOWNLOADS", 4)

# ============================================================
# Constantes y Utilidades
# ============================================================
DOI_REGEX = re.compile(r'^10\.\d{4,9}/.+$')

# Directorios de salida globales
SALIDAS_DIR, CSV_DIR, LOGS_DIR, BIB_DIR, JSON_DIR = "", "", "", "", ""
DOWNLOADS_DIR = ""

async def setup_output_dirs() -> None:
    """Configura los directorios de salida y descarga de forma asíncrona."""
    global SALIDAS_DIR, CSV_DIR, LOGS_DIR, BIB_DIR, JSON_DIR, DOWNLOADS_DIR
    
    DOWNLOADS_DIR = os.getenv("RESEARCH_PAPERS_DIR", os.path.join(os.getcwd(), "ResearchPapers"))
    
    base = "salidas"
    if SEPARATE_RUNS_IN_SUBFOLDER:
        tag = RUN_TAG or datetime.now().strftime("%Y%m%d_%H%M%S")
        base = os.path.join(base, tag)
    
    SALIDAS_DIR = base
    CSV_DIR, LOGS_DIR, BIB_DIR, JSON_DIR = (os.path.join(base, d) for d in ["csv", "logs", "bib", "json"])
    
    for d in (base, CSV_DIR, LOGS_DIR, BIB_DIR, JSON_DIR, DOWNLOADS_DIR):
        await aiofiles.os.makedirs(d, exist_ok=True)

def slugify(s: str) -> str:
    s = str(s).lower().strip()
    s = re.sub(r'[\s\W-]+', '-', s)
    s = s.strip('-')
    return s[:75] if len(s) > 75 else s

async def guardar_csv(nombre: str, rows: List[Dict[str, Any]]) -> None:
    path = os.path.join(CSV_DIR, nombre)
    if not rows: return
    async with aiofiles.open(path, "w", encoding="utf-8-sig", newline="") as f:
        fields = list(rows[0].keys())
        await f.write(",".join(fields) + "\n")
        for row in rows:
            values = [f'"{str(row.get(k, "")).replace("\"", "\"\"")}"' for k in fields]
            await f.write(",".join(values) + "\n")
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
    print(f"📚 Bibliografía guardada: {path}")

def extract_text(blobs: Optional[Iterable[Any]]) -> str:
    parts: List[str] = []
    if not blobs: return ""
    for b in blobs:
        if hasattr(b, "text"): parts.append(getattr(b, "text", "") or "")
        elif isinstance(b, str): parts.append(b)
    return "\n".join(parts).strip()

def parse_text_response_to_papers(raw_text: str, topic: str) -> List[Dict[str, Any]]:
    """Parsea la respuesta de texto formateada del servidor Rust para la búsqueda."""
    papers = []
    content = raw_text.split('\n\n', 1)[-1]
    paper_blocks = re.split(r'\n\n(?=\d+\.\s)', content)

    for block in paper_blocks:
        if not block.strip(): continue
        paper_data = {"topic": topic, "title": None, "doi": None, "source": None, "year": None}
        
        title_match = re.search(r'^\d+\.\s*(.*?)\s*\(Relevance:', block)
        if title_match: paper_data['title'] = title_match.group(1).strip()
        
        doi_match = re.search(r'📖\s*DOI:\s*(.*)', block)
        if doi_match:
            doi_str = doi_match.group(1).strip()
            paper_data['doi'] = doi_str if doi_str and " " not in doi_str else None

        source_match = re.search(r'🔍\s*Source:\s*(.*)', block)
        if source_match: paper_data['source'] = source_match.group(1).strip()
            
        year_match = re.search(r'📅\s*Year:\s*(\d{4})', block)
        if year_match: paper_data['year'] = int(year_match.group(1).strip())
            
        if paper_data.get('title'):
            paper_data['url'] = f"https://doi.org/{paper_data['doi']}" if paper_data.get('doi') else None
            paper_data['is_valid_doi'] = bool(paper_data['doi'] and DOI_REGEX.match(paper_data['doi']))
            papers.append(paper_data)
            
    return papers

async def step_a_search_papers(rh_client: RemoteMCPClient, topics: List[str]) -> List[Dict[str, Any]]:
    """Busca papers para cada topic y los devuelve combinados y deduplicados."""
    all_papers = []
    for topic in topics:
        print(f"\n--- 🔎 Buscando topic: '{topic}' ---")
        try:
            res = await rh_client.call_tool("search_papers", {"query": topic, "limit": MAX_RESULTS_PER_TOPIC})
            raw_text_content = extract_text(res)
            papers = parse_text_response_to_papers(raw_text_content, topic)
            all_papers.extend(papers)
            print(f"  -> Encontrados {len(papers)} resultados para '{topic}'.")
        except Exception as e:
            print(f"  ✗ Error buscando topic '{topic}': {e}")
    
    seen_dois = set()
    unique_papers = []
    for p in all_papers:
        doi = p.get("doi")
        if doi and doi not in seen_dois:
            seen_dois.add(doi)
            unique_papers.append(p)
        elif not doi:
             unique_papers.append(p)
    
    print(f"\n✨ Total de papers únicos encontrados: {len(unique_papers)}")
    return unique_papers

async def step_b_select_papers(papers: List[Dict[str, Any]]) -> List[str]:
    """Filtra y selecciona los DOIs válidos para descargar."""
    print("\n--- 🧠 Seleccionando papers para descarga ---")
    
    selected_dois = [p['doi'] for p in papers if p.get('is_valid_doi')]
    
    if DOWNLOAD_ALL_PAPERS:
        print(f"  -> Selección: TODOS ({len(selected_dois)} papers)")
        return selected_dois
    else:
        print(f"  -> Selección: TOP {SELECT_TOP_K} (usando los primeros encontrados)")
        return selected_dois[:SELECT_TOP_K]

async def step_c_download_papers(rh_client: RemoteMCPClient, dois: List[str], papers_metadata: List[Dict]) -> Dict[str, Dict]:
    """Descarga los papers seleccionados en paralelo."""
    if not dois: return {}
    print(f"\n--- 📥 Descargando {len(dois)} papers en paralelo (max {MAX_PARALLEL_DOWNLOADS}) ---")
    semaphore = asyncio.Semaphore(MAX_PARALLEL_DOWNLOADS)
    
    doi_map = {p['doi']: p for p in papers_metadata if p.get('doi')}

    async def _download_one(doi: str):
        async with semaphore:
            title = doi_map.get(doi, {}).get('title', 'untitled')
            filename = f"{slugify(title)}_{slugify(doi)}.pdf"
            try:
                res = await rh_client.call_tool("download_paper", {"doi": doi, "filename": filename, "directory": DOWNLOADS_DIR})
                raw_response_text = extract_text(res)
                
                success_match = re.search(r'File:\s*(.*?)\n', raw_response_text)
                
                if ("Download successful!" in raw_response_text or "File already exists" in raw_response_text) and success_match:
                    file_path = success_match.group(1).strip()
                    print(f"  ✓ Descargado (o ya existía): {doi}")
                    return doi, {"status": "ok", "path": file_path, "title": title}
                else:
                    print(f"  ✗ Fallo en descarga: {doi}")
                    return doi, {"status": "failed", "reason": raw_response_text.strip()}

            except Exception as e:
                print(f"  ✗ Error grave durante la descarga de {doi}: {e}")
                return doi, {"status": "error", "reason": str(e)}

    tasks = [_download_one(doi) for doi in dois]
    results = await asyncio.gather(*tasks)
    return {doi: result for doi, result in results}

def paper_dict_to_bibtex_entry(paper: Dict[str, Any]) -> str:
    """Convierte un diccionario de paper enriquecido en una entrada BibTeX string."""
    # Crea una clave única a partir del primer autor y año
    author_lastname = "unknown"
    if paper.get("authors"):
        try:
            author_lastname = slugify(paper["authors"].split(',')[0].split(' ')[-1])
        except: # noqa
            pass # Mantener 'unknown' si el formato del autor es inesperado
    
    year_str = str(paper.get('year', 'nodate'))
    key = f"{author_lastname}{year_str}"

    entry = f"@article{{{key},\n"
    if paper.get('title'):
        entry += f"  title     = {{{{{paper['title']}}}}},\n"
    if paper.get('authors'):
        entry += f"  author    = {{{paper['authors']}}},\n"
    if paper.get('year'):
        entry += f"  year      = {{{paper['year']}}},\n"
    if paper.get('journal'):
        entry += f"  journal   = {{{paper['journal']}}},\n"
    if paper.get('doi'):
        entry += f"  doi       = {{{paper['doi']}}},\n"
    entry += "}"
    return entry

async def step_d_generate_bibliography(rh_client: RemoteMCPClient, papers: List[Dict[str, Any]]) -> str:
    """Enriquece los metadatos de los papers y genera una bibliografía completa."""
    papers_with_doi = [p for p in papers if p.get('is_valid_doi')]
    if not papers_with_doi:
        return "% No se encontraron papers con DOI válido para generar la bibliografía."

    print(f"\n--- 📚 Generando Bibliografía ---")
    print(f"  -> Enriqueciendo metadatos para {len(papers_with_doi)} papers...")

    enriched_papers = []
    for paper in papers_with_doi:
        try:
            print(f"     - Obteniendo detalles para DOI: {paper['doi']}")
            # Llama a search_papers con el DOI para obtener metadatos ricos
            res = await rh_client.call_tool("search_papers", {"query": paper['doi'], "limit": 1})
            raw_text = extract_text(res)
            
            # Parsea la respuesta rica (puede tener más campos)
            # Usamos un parser simple aquí, asumiendo un formato similar
            enriched_data = paper.copy() # Empezamos con los datos que ya tenemos
            
            authors_match = re.search(r'👤\s*Authors:\s*(.*)', raw_text)
            if authors_match:
                enriched_data['authors'] = authors_match.group(1).strip()

            journal_match = re.search(r' L Journal:\s*(.*)', raw_text)
            if journal_match:
                enriched_data['journal'] = journal_match.group(1).strip()
            
            enriched_papers.append(enriched_data)
        except Exception as e:
            print(f"  ✗ Error enriqueciendo {paper.get('doi')}: {e}. Usando datos básicos.")
            enriched_papers.append(paper) # Añadir con datos básicos si falla

    print(f"  -> Creando entradas BibTeX...")
    bib_entries = [paper_dict_to_bibtex_entry(p) for p in enriched_papers]
        
    print("  -> Bibliografía generada con éxito.")
    return "\n\n".join(bib_entries)

def construir_topics_desde_terminos(terminos: List[str], max_topics: int) -> List[str]:
    if not terminos: return ["model context protocol"]
    topics_a_buscar = terminos[:max_topics]
    print(f"✅ Construidos {len(topics_a_buscar)} topics para la búsqueda: {topics_a_buscar}")
    return topics_a_buscar

async def main():
    """Flujo principal que orquesta la investigación."""
    await setup_output_dirs()
    
    try:
        async with aiofiles.open("terminos.txt", "r", encoding="utf-8") as f:
            contenido = await f.read()
        terminos = [t.strip() for t in contenido.splitlines() if t.strip()]
        if not terminos:
            print("⚠️  El archivo 'terminos.txt' está vacío. No hay nada que procesar.")
            return
    except FileNotFoundError:
        print("❌ ERROR: El archivo 'terminos.txt' no se encontró.")
        return

    topics = construir_topics_desde_terminos(terminos, MAX_TOPICS)
    
    print(f"\nIniciando Asistente de Investigación...")
    print(f"📂 Salidas en: {SALIDAS_DIR}")
    print(f"📥 PDFs se guardarán en: {DOWNLOADS_DIR}")
    
    server_configs = ServerConfig.get_server_configs()
    mcp_manager = MCPClientManager(server_configs)
    
    try:
        print("\n🔗 Conectando al servidor de Research Hub...")
        await mcp_manager._connect_single_server("research_hub", server_configs["research_hub"])
        rh_client = mcp_manager.get_client("research_hub")
        if not rh_client:
            print("❌ No se pudo conectar al servidor de Research Hub. Abortando.")
            return
        print("✅ Conectado.")

        found_papers = await step_a_search_papers(rh_client, topics)
        if not found_papers:
            print("\n⚠️ No se encontraron papers en ninguna de las búsquedas. Terminando.")
            return
        
        await guardar_json("00_resultados_completos.json", found_papers)
        await guardar_csv("01_papers_encontrados.csv", found_papers)
        
        selected_dois = await step_b_select_papers(found_papers)
        if not selected_dois:
            print("\n⚠️ No se seleccionaron papers con DOI válido para descargar.")
        else:
            await guardar_json("02_dois_seleccionados.json", {"dois": selected_dois})
            download_manifest = await step_c_download_papers(rh_client, selected_dois, found_papers)
            await guardar_json("03_manifiesto_descarga.json", download_manifest)

        bib_content = await step_d_generate_bibliography(rh_client, found_papers)
        await guardar_bib("bibliografia_final.bib", bib_content)
        
        print("\n🎉 Proceso completado con éxito.")

    finally:
        print("\n🏁 Finalizando y cerrando conexiones...")
        await mcp_manager.close_all_clients()

if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())