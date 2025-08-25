# research_assistant.py
# ============================================================
# Flujo de investigación con rust-research-mcp (MCP server)
# 1. Lee 'terminos.txt' y construye topics (MAX_TOPICS).
# 2. Busca papers (search_papers) para DOIs y metadatos.
# 3. Descarga PDFs (download_paper) con control de paralelismo.
# 4. Genera bibliografía (BibTeX) desde los metadatos recolectados.
# 5. Busca discusiones en Hacker News y filtra con un LLM (opcional).
# ============================================================

from __future__ import annotations
import asyncio
import json
import os
import re
from datetime import datetime
from typing import Any, Iterable, List, Dict, Optional

from dotenv import load_dotenv
import aiofiles
import aiofiles.os

# Módulos del proyecto (mantén tus rutas reales)
from config_manager import ServerConfig, AppConfig
from mcp_client_manager import MCPClientManager, RemoteMCPClient
from ai_client_manager import AIClientManager

load_dotenv()

# ============================================================
# 🔧 PARÁMETROS CONFIGURABLES (env-first)
# ============================================================

def env_bool(name: str, default: bool) -> bool:
    val = os.getenv(name, str(default)).strip().lower()
    return val in ("1", "true", "t", "yes", "y", "on")

def env_int(name: str, default: int) -> int:
    try:
        v = os.getenv(name)
        return int(v) if v is not None else default
    except ValueError:
        return default

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

# ——— Timeouts/reintentos MCP ———
MCP_INIT_RETRIES: int = env_int("MCP_INIT_RETRIES", 1)
RESEARCH_HUB_INIT_TIMEOUT: int = env_int("RESEARCH_HUB_INIT_TIMEOUT", 45)
HACKERNEWS_INIT_TIMEOUT: int = env_int("HACKERNEWS_INIT_TIMEOUT", 15)

# ============================================================
# Constantes y Utilidades
# ============================================================
DOI_REGEX = re.compile(r'^10\.\d{4,9}/.+$')

# Directorios de salida globales
SALIDAS_DIR, CSV_DIR, LOGS_DIR, BIB_DIR, JSON_DIR = "", "", "", "", ""
DOWNLOADS_DIR = ""

def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

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
    if not rows: 
        return
    path = os.path.join(CSV_DIR, nombre)
    # CSV simple (sin dependencias); escapado básico de comillas
    async with aiofiles.open(path, "w", encoding="utf-8-sig", newline="") as f:
        fields = list(rows[0].keys())
        await f.write(",".join(fields) + "\n")
        for row in rows:
            values = [f"\"{str(row.get(k, '')).replace('\"', '\"\"')}\"" for k in fields]
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
    if not blobs: 
        return ""
    for b in blobs:
        if hasattr(b, "text"):
            parts.append(getattr(b, "text", "") or "")
        elif isinstance(b, str):
            parts.append(b)
    return "\n".join(parts).strip()

def parse_text_response_to_papers(raw_text: str, topic: str) -> List[Dict[str, Any]]:
    """Parsea la respuesta texto-formateada del servidor Rust para la búsqueda."""
    papers = []
    if not raw_text:
        return papers

    # El servidor suele poner cabecera; separamos doble salto
    content = raw_text.split('\n\n', 1)[-1]
    paper_blocks = re.split(r'\n\n(?=\d+\.\s)', content)

    for block in paper_blocks:
        if not block.strip():
            continue
        paper_data = {"topic": topic, "title": None, "doi": None, "source": None, "year": None, "authors": None, "journal": None}
        
        title_match = re.search(r'^\d+\.\s*(.*?)\s*\(Relevance:', block)
        if title_match: 
            paper_data['title'] = title_match.group(1).strip()
        
        doi_match = re.search(r'📖\s*DOI:\s*(.*)', block)
        if doi_match:
            doi_str = doi_match.group(1).strip()
            paper_data['doi'] = doi_str if doi_str and " " not in doi_str else None

        source_match = re.search(r'🔍\s*Source:\s*(.*)', block)
        if source_match: 
            paper_data['source'] = source_match.group(1).strip()
            
        year_match = re.search(r'📅\s*Year:\s*(\d{4})', block)
        if year_match: 
            paper_data['year'] = int(year_match.group(1).strip())

        authors_match = re.search(r'👤\s*Authors:\s*(.*)', block)
        if authors_match: 
            paper_data['authors'] = authors_match.group(1).strip()

        journal_match = re.search(r'Journal:\s*(.*)', block)
        if journal_match: 
            paper_data['journal'] = journal_match.group(1).strip()
            
        if paper_data.get('title'):
            paper_data['url'] = f"https://doi.org/{paper_data['doi']}" if paper_data.get('doi') else None
            paper_data['is_valid_doi'] = bool(paper_data['doi'] and DOI_REGEX.match(paper_data['doi']))
            papers.append(paper_data)
            
    return papers

async def step_a_search_papers(rh_client: RemoteMCPClient, topics: List[str]) -> List[Dict[str, Any]]:
    """Busca papers para cada topic y los devuelve combinados y deduplicados."""
    all_papers: List[Dict[str, Any]] = []
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
    
    # Deduplicado por DOI (si está) manteniendo entradas sin DOI
    seen_dois = set()
    unique_papers: List[Dict[str, Any]] = []
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
    if not dois: 
        return {}
    print(f"\n--- 📥 Descargando {len(dois)} papers en paralelo (max {MAX_PARALLEL_DOWNLOADS}) ---")
    semaphore = asyncio.Semaphore(MAX_PARALLEL_DOWNLOADS)
    
    doi_map = {p['doi']: p for p in papers_metadata if p.get('doi')}

    async def _download_one(doi: str):
        async with semaphore:
            title = doi_map.get(doi, {}).get('title', 'untitled')
            filename = f"{slugify(title)}_{slugify(doi)}.pdf"
            try:
                res = await rh_client.call_tool("download_paper", {"doi": doi, "filename": filename})
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
    author_lastname = "unknown"
    if paper.get("authors"):
        try:
            author_lastname = slugify(paper["authors"].split(',')[0].split(' ')[-1])
        except:  # noqa
            pass 
    
    year_str = str(paper.get('year', 'nodate'))
    title_slug = slugify(paper.get('title', 'notitle')[:10])
    key = f"{author_lastname}{year_str}{title_slug}"

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

async def step_d_generate_bibliography(papers: List[Dict[str, Any]]) -> str:
    """Genera una bibliografía completa a partir de los metadatos ya recolectados."""
    papers_with_doi = [p for p in papers if p.get('is_valid_doi')]
    if not papers_with_doi:
        return "% No se encontraron papers con DOI válido para generar la bibliografía."

    print(f"\n--- 📚 Generando Bibliografía a partir de los datos existentes ---")
    print(f"  -> Usando metadatos para {len(papers_with_doi)} papers.")
    
    bib_entries = [paper_dict_to_bibtex_entry(p) for p in papers_with_doi]
        
    print("  -> Bibliografía generada con éxito.")
    return "\n\n".join(bib_entries)

async def step_e_search_hackernews(hn_client: RemoteMCPClient, topics: List[str]) -> Dict[str, Any]:
    """Obtiene historias de Hacker News y las filtra localmente por palabras clave."""
    print("\n--- 🌐 Buscando en Hacker News (Estrategia de Palabras Clave) ---")
    clean_topics = [t.strip().strip('"') for t in topics]
    all_results = {t: [] for t in clean_topics}
    
    try:
        raw_stories = None
        max_retries = 3
        base_delay = 2
        
        for attempt in range(max_retries):
            print(f"  -> Obteniendo las historias principales de HN (Intento {attempt + 1}/{max_retries})...")
            try:
                # Llamada robusta sin parámetros
                raw_stories = await hn_client.call_tool("getStories", {})
                if raw_stories and isinstance(raw_stories, list):
                    break
                print(f"  -> Intento {attempt + 1} sin datos. Reintentando...")
            except Exception as e:
                print(f"  -> Intento {attempt + 1} falló: {e}. Reintentando...")
            
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                await asyncio.sleep(delay)
        
        if not raw_stories:
            print("  ✗ No se pudieron obtener historias de Hacker News.")
            return all_results

        stories = []
        for item in raw_stories:
            story_dict = None
            if isinstance(item, dict):
                story_dict = item
            elif hasattr(item, 'text'):
                try:
                    story_dict = json.loads(item.text)
                except json.JSONDecodeError:
                    continue
            if story_dict:
                stories.append(story_dict)

        print(f"  -> Obtenidas {len(stories)} historias. Filtrando por temas...")
        
        for clean_topic in clean_topics:
            topic_keywords = set(clean_topic.lower().split())
            match_threshold = 2 if len(topic_keywords) > 1 else 1

            for story in stories:
                title = story.get("title", "")
                if not title: 
                    continue
                title_words = set(title.lower().split())
                matches = len(topic_keywords.intersection(title_words))

                if matches >= match_threshold:
                    all_results[clean_topic].append({
                        "title": title,
                        "url": story.get("url"),
                        "author": story.get("by"),
                        "score": story.get("score", 0),
                        "comments": story.get("descendants", 0),
                        "timestamp": story.get("time"),
                        "objectID": story.get("id")
                    })
            
            print(f"    -> {len(all_results[clean_topic])} resultados para '{clean_topic}'.")

    except Exception as e:
        print(f"  ✗ Error durante la búsqueda en Hacker News: {e}")
            
    print("\n✨ Búsqueda en Hacker News completada.")
    return all_results

async def step_f_filter_with_llm(ai_client: AIClientManager, hn_results: Dict[str, List[Dict]]) -> Dict[str, Any]:
    """Usa un LLM para validar la relevancia contextual de los resultados de Hacker News."""
    print("\n--- 🤖 Filtrando resultados de Hacker News con LLM ---")
    final_results: Dict[str, Any] = {}

    for topic, stories in hn_results.items():
        if not stories:
            print(f"  -> Sin historias para filtrar para: '{topic}'")
            final_results[topic] = []
            continue

        print(f"  -> Pidiendo al LLM validar {len(stories)} historias para: '{topic}'...")
        titles_with_ids = {f"{i+1}": s['title'] for i, s in enumerate(stories)}
        titles_str = "\n".join([f"{idx}. {title}" for idx, title in titles_with_ids.items()])
        
        prompt = (
            f"You are a research assistant. Your task is to identify which of the following Hacker News titles are truly relevant to the research topic: '{topic}'.\n\n"
            "A title is relevant if it discusses the topic directly. It is NOT relevant if it just uses some of the same words in a different context.\n\n"
            "Candidate Titles:\n"
            f"{titles_str}\n\n"
            "Instructions:\n"
            "Return a JSON object with a single key, 'relevant_indices', which is a list of the numbers of the relevant titles. For example: {\"relevant_indices\": [1, 4, 5]}\n"
            "If no titles are relevant, return an empty list: {\"relevant_indices\": []}\n"
            "Return ONLY the JSON object and nothing else."
        )

        try:
            response_text = await ai_client.chat_completion(prompt)
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if not json_match:
                print(f"  ✗ LLM no devolvió JSON válido para '{topic}'. Se mantiene sin filtrar.")
                final_results[topic] = stories
                continue

            response_json = json.loads(json_match.group(0))
            relevant_indices = response_json.get("relevant_indices", [])
            filtered_stories = [stories[i-1] for i in relevant_indices if 0 < i <= len(stories)]
            final_results[topic] = filtered_stories
            print(f"  -> LLM identificó {len(filtered_stories)} historias relevantes.")

        except Exception as e:
            print(f"  ✗ Error LLM para '{topic}': {e}. Se mantiene sin filtrar.")
            final_results[topic] = stories

    print("\n✨ Filtrado con LLM completado.")
    return final_results

def construir_topics_desde_terminos(terminos: List[str], max_topics: int) -> List[str]:
    """Construye la lista final de topics a partir de 'terminos.txt'."""
    if not terminos: 
        return ["model context protocol"]
    topics_a_buscar = terminos[:max_topics]
    print(f"✅ Construidos {len(topics_a_buscar)} topics: {topics_a_buscar}")
    return topics_a_buscar

# ============ Conexión MCP con timeouts/reintentos por servidor ============
async def connect_with_retries(mgr: MCPClientManager, name: str, cfg: Dict[str, Any], timeout: int, retries: int) -> bool:
    delay = 2.0
    for attempt in range(retries + 1):
        try:
            print(f"[{now_str()}] [MCP] Conectando a '{name}' (intento {attempt+1}/{retries+1}) | timeout={timeout}s")
            await asyncio.wait_for(mgr._connect_single_server(name, cfg), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            err = f"Timeout en initialize() para '{name}'"
        except Exception as e:
            err = str(e)
        print(f"  ✗ Error conectando '{name}': {err}")
        if attempt < retries:
            await asyncio.sleep(delay)
            delay *= 2
    print(f"  ✗ Fallo definitivo conectando a '{name}'")
    return False

# ============================================================
# Orquestación principal
# ============================================================
async def main():
    await setup_output_dirs()
    
    # 1) Leer terminos.txt
    try:
        async with aiofiles.open("terminos.txt", "r", encoding="utf-8") as f:
            contenido = await f.read()
        terminos = [t.strip() for t in contenido.splitlines() if t.strip()]
        if not terminos:
            print("⚠️  'terminos.txt' está vacío. No hay nada que procesar.")
            return
    except FileNotFoundError:
        print("❌ ERROR: No se encontró 'terminos.txt'.")
        return

    topics = construir_topics_desde_terminos(terminos, MAX_TOPICS)
    
    print(f"\nIniciando Asistente de Investigación…")
    print(f"📂 Salidas en: {SALIDAS_DIR}")
    print(f"📥 PDFs se guardarán en: {DOWNLOADS_DIR}")

    # 2) Inicializar (opcional) cliente de IA para filtrado HN
    ai_client = None
    try:
        ai_provider = AppConfig.get_ai_provider()
        api_key = AppConfig.get_api_key(ai_provider)
        ai_model = AppConfig.get_ai_model(ai_provider)
        if ai_provider != "ollama" and not api_key:
            print(f"⚠️  No hay API Key para {ai_provider}. Omito filtrado con LLM.")
        else:
            ai_client = AIClientManager(provider=ai_provider, api_key=api_key, model=ai_model)
            print(f"✅ Cliente IA: {ai_provider.upper()} ({ai_model})")
    except Exception as e:
        print(f"⚠️  No se pudo inicializar el cliente de IA: {e}. Omito filtrado con LLM.")

    # 3) Conectar MCP (Research Hub + HackerNews) con timeouts/reintentos
    server_configs = ServerConfig.get_server_configs()
    mcp_manager = MCPClientManager(server_configs)
    
    print("\n🔗 Conectando a servidores MCP…")
    rh_cfg = server_configs.get("research_hub", {})
    hn_cfg = server_configs.get("hackernews", {})

    rh_ok, hn_ok = await asyncio.gather(
        connect_with_retries(mcp_manager, "research_hub", rh_cfg, RESEARCH_HUB_INIT_TIMEOUT, MCP_INIT_RETRIES),
        connect_with_retries(mcp_manager, "hackernews", hn_cfg, HACKERNEWS_INIT_TIMEOUT, MCP_INIT_RETRIES),
    )

    rh_client = mcp_manager.get_client("research_hub") if rh_ok else None
    hn_client = mcp_manager.get_client("hackernews") if hn_ok else None

    try:
        # 4) Paso A–D con Research Hub
        if not rh_client:
            print("⚠️ Research Hub no disponible. Omito búsqueda/descarga/bibliografía.")
        else:
            print("✅ Conectado a Research Hub.")
            found_papers = await step_a_search_papers(rh_client, topics)
            if not found_papers:
                print("\n⚠️ No se encontraron papers para los topics.")
            else:
                await guardar_json("00_resultados_completos.json", found_papers)
                await guardar_csv("01_papers_encontrados.csv", found_papers)
                
                selected_dois = await step_b_select_papers(found_papers)
                if not selected_dois:
                    print("\n⚠️ No hay DOIs válidos para descargar.")
                else:
                    await guardar_json("02_dois_seleccionados.json", {"dois": selected_dois})
                    download_manifest = await step_c_download_papers(rh_client, selected_dois, found_papers)
                    await guardar_json("03_manifiesto_descarga.json", download_manifest)

                bib_content = await step_d_generate_bibliography(found_papers)
                await guardar_bib("bibliografia_final.bib", bib_content)

        # 5) Paso E–F Hacker News + LLM
        if not hn_client:
            print("⚠️ Hacker News no disponible. Omito este paso.")
        else:
            print("✅ Conectado a Hacker News.")
            hackernews_raw_results = await step_e_search_hackernews(hn_client, topics)
            await guardar_json("04_hackernews_raw_search.json", hackernews_raw_results)

            if ai_client:
                final_hn_results = await step_f_filter_with_llm(ai_client, hackernews_raw_results)
                await guardar_json("05_hackernews_llm_filtered.json", final_hn_results)
            else:
                print("-> Omitiendo filtrado con LLM (cliente no disponible).")
        
        print("\n🎉 Proceso completado con éxito.")

    finally:
        print("\n🏁 Finalizando y cerrando conexiones…")
        await mcp_manager.close_all_clients()

if __name__ == "__main__":
    if os.name == 'nt':
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        except Exception:
            pass
    asyncio.run(main())
