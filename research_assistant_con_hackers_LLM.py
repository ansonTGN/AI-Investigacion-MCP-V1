# research_assistant_con_hackers_LLM.py
# ============================================================
# Flujo de investigación con rust-research-mcp (MCP server)
# 1. Lee 'terminos.txt' y construye topics (MAX_TOPICS).
# 2. Busca papers (search_papers) para DOIs y metadatos.
# 3. Descarga PDFs (download_paper) con control de paralelismo.
# 4. Genera bibliografía (BibTeX) desde los metadatos recolectados.
# 5. Busca discusiones en Hacker News por cada topic y filtra con un LLM.
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

# Módulos del proyecto
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
MAX_HN_RESULTS_PER_TOPIC: int = env_int("MAX_HN_RESULTS_PER_TOPIC", 15)


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

def slugify(s: str) -> str:
    """Convierte un string en un formato seguro para nombres de archivo."""
    s = str(s).lower().strip()
    s = re.sub(r'[\s\W-]+', '-', s)
    s = s.strip('-')
    return s[:75] if len(s) > 75 else s

def now_str() -> str:
    """Devuelve la fecha y hora actual como un string formateado."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def extract_text(blobs: Optional[Iterable[Any]]) -> str:
    """Extrae y une el contenido de texto de una respuesta MCP."""
    if not blobs: 
        return ""
    parts: List[str] = []
    for b in blobs:
        if hasattr(b, "text"):
            parts.append(getattr(b, "text", "") or "")
        elif isinstance(b, str):
            parts.append(b)
    return "\n".join(parts).strip()

def parse_text_response_to_papers(raw_text: str, topic: str) -> List[Dict[str, Any]]:
    """Parsea la respuesta de texto del servidor Rust para la búsqueda de papers."""
    papers = []
    if not raw_text:
        return papers

    content = raw_text.split('\n\n', 1)[-1]
    paper_blocks = re.split(r'\n\n(?=\d+\.\s)', content)

    for block in paper_blocks:
        if not block.strip():
            continue
        paper_data = {"topic": topic, "title": None, "doi": None, "source": None, "year": None, "authors": None, "journal": None}
        
        # Extracción de campos con expresiones regulares
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

        authors_match = re.search(r'👤\s*Authors:\s*(.*)', block)
        if authors_match: paper_data['authors'] = authors_match.group(1).strip()

        journal_match = re.search(r'Journal:\s*(.*)', block)
        if journal_match: paper_data['journal'] = journal_match.group(1).strip()
            
        if paper_data.get('title'):
            paper_data['url'] = f"https://doi.org/{paper_data['doi']}" if paper_data.get('doi') else None
            paper_data['is_valid_doi'] = bool(paper_data['doi'] and DOI_REGEX.match(paper_data['doi']))
            papers.append(paper_data)
            
    return papers

class AdvancedResearchAssistant:
    """Orquesta el flujo de investigación avanzada, gestionando clientes, archivos y lógica de negocio."""
    
    def __init__(self, topics: List[str]):
        """Inicializa el asistente con los temas de investigación."""
        self.topics = topics
        self.mcp_manager: MCPClientManager = None
        self.ai_client: Optional[AIClientManager] = None
        self.rh_client: Optional[RemoteMCPClient] = None
        self.hn_client: Optional[RemoteMCPClient] = None

        # Directorios de salida (inicializados como None)
        self.salidas_dir = self.csv_dir = self.logs_dir = self.bib_dir = self.json_dir = None
        self.downloads_dir = os.getenv("RESEARCH_PAPERS_DIR", os.path.join(os.getcwd(), "ResearchPapers"))

    async def setup_output_dirs(self):
        """Configura los directorios de salida para esta ejecución."""
        base = "salidas"
        if SEPARATE_RUNS_IN_SUBFOLDER:
            tag = RUN_TAG or datetime.now().strftime("%Y%m%d_%H%M%S")
            base = os.path.join(base, tag)
        
        self.salidas_dir = base
        self.csv_dir = os.path.join(base, "csv")
        self.logs_dir = os.path.join(base, "logs")
        self.bib_dir = os.path.join(base, "bib")
        self.json_dir = os.path.join(base, "json")
        
        for d in (self.salidas_dir, self.csv_dir, self.logs_dir, self.bib_dir, self.json_dir, self.downloads_dir):
            await aiofiles.os.makedirs(d, exist_ok=True)
        print(f"📂 Salidas se guardarán en: {self.salidas_dir}")
        print(f"📥 PDFs se guardarán en: {self.downloads_dir}")

    async def _save_json(self, name: str, data: Any):
        """Guarda datos en un archivo JSON en el directorio de salida."""
        path = os.path.join(self.json_dir, name)
        async with aiofiles.open(path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(data, ensure_ascii=False, indent=2))
        print(f"💾 JSON guardado: {os.path.basename(path)}")
    
    async def _save_csv(self, name: str, rows: List[Dict[str, Any]]):
        """Guarda una lista de diccionarios en un archivo CSV."""
        if not rows: return
        path = os.path.join(self.csv_dir, name)
        async with aiofiles.open(path, "w", encoding="utf-8-sig", newline="") as f:
            fields = list(rows[0].keys())
            await f.write(",".join(fields) + "\n")
            for row in rows:
                values = [f"\"{str(row.get(k, '')).replace('\"', '\"\"')}\"" for k in fields]
                await f.write(",".join(values) + "\n")
        print(f"💾 CSV guardado: {os.path.basename(path)} ({len(rows)} filas)")

    async def _save_bib(self, name: str, content: str):
        """Guarda contenido en un archivo BibTeX."""
        path = os.path.join(self.bib_dir, name)
        async with aiofiles.open(path, "w", encoding="utf-8") as f:
            await f.write(content)
        print(f"📚 Bibliografía guardada: {os.path.basename(path)}")

    async def _save_log(self, name: str, content: str):
        """Guarda texto en un archivo de registro."""
        path = os.path.join(self.logs_dir, name)
        async with aiofiles.open(path, "w", encoding="utf-8") as f:
            await f.write(content)
        print(f"📜 Log de error guardado: {os.path.basename(path)}")

    async def _connect_with_retries(self, name: str, cfg: Dict[str, Any], timeout: int, retries: int) -> bool:
        """Intenta conectar a un servidor MCP con reintentos."""
        delay = 2.0
        for attempt in range(retries + 1):
            try:
                print(f"[{now_str()}] [MCP] Conectando a '{name}' (intento {attempt+1}/{retries+1}) | timeout={timeout}s")
                await asyncio.wait_for(self.mcp_manager._connect_single_server(name, cfg), timeout=timeout)
                if self.mcp_manager.is_platform_available(name):
                    print(f"  [ÉXITO] Conexión establecida con '{name}'")
                    return True
            except Exception as e:
                err = f"Timeout en initialize() para '{name}'" if isinstance(e, asyncio.TimeoutError) else str(e)
            print(f"  [FALLO] Error conectando a '{name}': {err}")
            if attempt < retries:
                await asyncio.sleep(delay)
                delay *= 2
        print(f"  [FALLO] Conexión definitiva fallida con '{name}'")
        return False

    async def connect_services(self) -> bool:
        """Inicializa y conecta a todos los servicios externos (MCP, IA)."""
        # 1. Conectar servidores MCP
        server_configs = ServerConfig.get_server_configs()
        self.mcp_manager = MCPClientManager(server_configs)
        
        print("\n🔗 Conectando a servidores MCP…")
        rh_cfg = server_configs.get("research_hub", {})
        hn_cfg = server_configs.get("hackernews", {})

        rh_ok, hn_ok = await asyncio.gather(
            self._connect_with_retries("research_hub", rh_cfg, RESEARCH_HUB_INIT_TIMEOUT, MCP_INIT_RETRIES),
            self._connect_with_retries("hackernews", hn_cfg, HACKERNEWS_INIT_TIMEOUT, MCP_INIT_RETRIES),
        )
        self.rh_client = self.mcp_manager.get_client("research_hub") if rh_ok else None
        self.hn_client = self.mcp_manager.get_client("hackernews") if hn_ok else None

        # 2. Inicializar cliente de IA
        try:
            ai_provider = AppConfig.get_ai_provider()
            api_key = AppConfig.get_api_key(ai_provider)
            ai_model = AppConfig.get_ai_model(ai_provider)
            if ai_provider != "ollama" and not api_key:
                print(f"⚠️  [OMITIDO] No hay API Key para {ai_provider}. Se omitirá el filtrado con LLM.")
            else:
                self.ai_client = AIClientManager(provider=ai_provider, api_key=api_key, model=ai_model)
                print(f"✅ Cliente IA inicializado: {ai_provider.upper()} (modelo: {ai_model or 'default'})")
        except Exception as e:
            print(f"⚠️  [FALLO] No se pudo inicializar el cliente de IA: {e}. Se omitirá el filtrado con LLM.")
        
        return self.rh_client is not None or self.hn_client is not None

    async def _search_papers(self) -> List[Dict[str, Any]]:
        """Paso A: Busca papers para cada topic y los devuelve combinados y deduplicados."""
        print("\n--- PASO A: Búsqueda de Papers Académicos ---")
        if not self.rh_client:
            print("  [OMITIDO] El cliente de Research Hub no está disponible.")
            return []
        
        all_papers: List[Dict[str, Any]] = []
        for topic in self.topics:
            print(f"  -> Buscando topic: '{topic}'...")
            try:
                res = await self.rh_client.call_tool("search_papers", {"query": topic, "limit": MAX_RESULTS_PER_TOPIC})
                papers = parse_text_response_to_papers(extract_text(res), topic)
                all_papers.extend(papers)
                print(f"     Encontrados {len(papers)} resultados.")
            except Exception as e:
                print(f"     [FALLO] Error buscando topic '{topic}': {e}")
        
        # Deduplicado por DOI
        seen_dois = set()
        unique_papers = [p for p in all_papers if p.get("doi") not in seen_dois and not seen_dois.add(p.get("doi"))]
        
        print(f"\n✨ [ÉXITO] Total de papers únicos encontrados: {len(unique_papers)}")
        return unique_papers

    async def _select_and_download_papers(self, papers: List[Dict[str, Any]]):
        """Pasos B y C: Selecciona DOIs para descargar y ejecuta la descarga en paralelo."""
        print("\n--- PASOS B & C: Selección y Descarga de PDFs ---")
        if not self.rh_client:
            print("  [OMITIDO] El cliente de Research Hub no está disponible.")
            return

        # Paso B: Selección
        selected_dois = [p['doi'] for p in papers if p.get('is_valid_doi')]
        if not DOWNLOAD_ALL_PAPERS:
            selected_dois = selected_dois[:SELECT_TOP_K]
            print(f"  -> Selección: TOP {SELECT_TOP_K} papers ({len(selected_dois)} con DOI válido).")
        else:
            print(f"  -> Selección: TODOS los papers ({len(selected_dois)} con DOI válido).")
        
        if not selected_dois:
            print("  [AVISO] No hay DOIs válidos para descargar.")
            return

        await self._save_json("02_dois_seleccionados.json", {"dois": selected_dois})

        # Paso C: Descarga
        print(f"  -> Descargando {len(selected_dois)} papers en paralelo (max {MAX_PARALLEL_DOWNLOADS})...")
        semaphore = asyncio.Semaphore(MAX_PARALLEL_DOWNLOADS)
        doi_map = {p['doi']: p for p in papers if p.get('doi')}

        async def _download_one(doi: str):
            async with semaphore:
                title = doi_map.get(doi, {}).get('title', 'untitled')
                filename = f"{slugify(title)}_{slugify(doi)}.pdf"
                try:
                    res = await self.rh_client.call_tool("download_paper", {"doi": doi, "filename": filename})
                    raw_text = extract_text(res)
                    if "Download successful!" in raw_text or "File already exists" in raw_text:
                        print(f"     ✓ Descargado (o ya existía): {doi}")
                        return doi, {"status": "ok", "title": title}
                    print(f"     ✗ Fallo en descarga: {doi}")
                    return doi, {"status": "failed", "reason": raw_text.strip()}
                except Exception as e:
                    print(f"     ✗ Error grave durante la descarga de {doi}: {e}")
                    return doi, {"status": "error", "reason": str(e)}

        tasks = [_download_one(doi) for doi in selected_dois]
        results = await asyncio.gather(*tasks)
        download_manifest = {doi: result for doi, result in results}
        await self._save_json("03_manifiesto_descarga.json", download_manifest)
        print("✨ [ÉXITO] Proceso de descarga completado.")

    def _paper_to_bibtex(self, paper: Dict[str, Any]) -> str:
        """Convierte un diccionario de metadatos de un paper a una entrada BibTeX."""
        author_lastname = "unknown"
        if paper.get("authors"):
            try: author_lastname = slugify(paper["authors"].split(',')[0].split(' ')[-1])
            except: pass
        
        year_str = str(paper.get('year', 'nodate'))
        title_slug = slugify(paper.get('title', 'notitle')[:10])
        key = f"{author_lastname}{year_str}{title_slug}"

        entry = f"@article{{{key},\n"
        if paper.get('title'): entry += f"  title     = {{{{{paper['title']}}}}},\n"
        if paper.get('authors'): entry += f"  author    = {{{paper['authors']}}},\n"
        if paper.get('year'): entry += f"  year      = {{{paper['year']}}},\n"
        if paper.get('journal'): entry += f"  journal   = {{{paper['journal']}}},\n"
        if paper.get('doi'): entry += f"  doi       = {{{paper['doi']}}},\n"
        entry += "}"
        return entry
        
    async def _generate_bibliography(self, papers: List[Dict[str, Any]]):
        """Paso D: Genera una bibliografía completa a partir de los metadatos recolectados."""
        print("\n--- PASO D: Generación de Bibliografía ---")
        papers_with_doi = [p for p in papers if p.get('is_valid_doi')]
        if not papers_with_doi:
            print("  [OMITIDO] No se encontraron papers con DOI válido para generar bibliografía.")
            return

        print(f"  -> Usando metadatos de {len(papers_with_doi)} papers.")
        bib_entries = [self._paper_to_bibtex(p) for p in papers_with_doi]
        await self._save_bib("bibliografia_final.bib", "\n\n".join(bib_entries))
        print("✨ [ÉXITO] Bibliografía generada.")

    async def _search_hackernews(self) -> Dict[str, Any]:
        """
        Paso E: Busca en Hacker News para cada topic.
        MEJORA: Maneja explícitamente errores de JSON y guarda la respuesta cruda.
        """
        print("\n--- PASO E: Búsqueda en Hacker News ---")
        if not self.hn_client:
            print("  [OMITIDO] El cliente de Hacker News no está disponible.")
            return {}

        all_results = {}
        for topic in self.topics:
            print(f"  -> Buscando en HN: '{topic}'...")
            raw_response_text = ""
            try:
                params = {"query": topic, "max_results": MAX_HN_RESULTS_PER_TOPIC}
                response = await self.hn_client.call_tool("getStories", params)
                
                stories = []
                # El problema puede estar aquí: la respuesta puede ser un texto vacío o un error HTML
                raw_response_text = extract_text(response)
                if not raw_response_text.strip():
                     print(f"     [AVISO] Respuesta vacía del servidor para '{topic}'.")
                     all_results[topic] = []
                     continue

                # Intentamos decodificar el JSON
                response_json = json.loads(raw_response_text)
                
                # Asumimos que la respuesta es una lista de historias (o un dict con 'hits')
                story_items = response_json if isinstance(response_json, list) else response_json.get('hits', [])

                all_results[topic] = story_items
                print(f"     Encontrados {len(story_items)} resultados.")
            
            except json.JSONDecodeError as e:
                log_filename = f"hackernews_error_response_{slugify(topic)}.log"
                error_msg = f"     [FALLO] El servidor HN no devolvió un JSON válido para '{topic}'. Error: {e}"
                print(error_msg)
                await self._save_log(log_filename, f"{error_msg}\n\n--- RESPUESTA RECIBIDA ---\n{raw_response_text}")
                all_results[topic] = []
            except Exception as e:
                print(f"     [FALLO] Error inesperado buscando en HN para '{topic}': {e}")
                all_results[topic] = []
        
        print("✨ [ÉXITO] Búsqueda en Hacker News completada.")
        return all_results

    async def _filter_with_llm(self, hn_results: Dict[str, List[Dict]]) -> Dict[str, Any]:
        """Paso F: Usa un LLM para validar la relevancia de los resultados de Hacker News."""
        print("\n--- PASO F: Filtrado de HN con LLM ---")
        if not self.ai_client:
            print("  [OMITIDO] Cliente de IA no disponible.")
            return hn_results
        
        final_results = {}
        for topic, stories in hn_results.items():
            if not stories:
                final_results[topic] = []
                continue

            print(f"  -> Pidiendo al LLM que valide {len(stories)} historias para: '{topic}'...")
            titles_str = "\n".join([f"{i+1}. {s.get('title', 'N/A')}" for i, s in enumerate(stories)])
            
            prompt = (
                f"Identify which of the following Hacker News titles are relevant to the research topic: '{topic}'.\n\n"
                "A title is relevant if it discusses the topic directly, not if it just uses some of the same words in a different context.\n\n"
                f"Candidate Titles:\n{titles_str}\n\n"
                "Return a JSON object with a single key 'relevant_indices', a list of the numbers of relevant titles. Example: {\"relevant_indices\": [1, 4, 5]}.\n"
                "If none are relevant, return an empty list. Respond ONLY with the JSON object."
            )

            try:
                response_text = await self.ai_client.chat_completion(prompt)
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                response_json = json.loads(json_match.group(0)) if json_match else {}
                relevant_indices = response_json.get("relevant_indices", [])
                
                filtered = [stories[i-1] for i in relevant_indices if 0 < i <= len(stories)]
                final_results[topic] = filtered
                print(f"     LLM identificó {len(filtered)} historias relevantes.")
            except Exception as e:
                print(f"     [FALLO] Error con el LLM para '{topic}': {e}. Se mantienen resultados sin filtrar.")
                final_results[topic] = stories
        
        print("✨ [ÉXITO] Filtrado con LLM completado.")
        return final_results

    async def run(self):
        """Ejecuta el flujo completo de investigación."""
        print(f"\n[{now_str()}] 🚀 Iniciando Asistente de Investigación…")
        await self.setup_output_dirs()
        
        if not await self.connect_services():
            print("\n❌ [ERROR] No se pudo conectar a los servicios necesarios. Abortando.")
            return

        try:
            # Flujo de Research Hub
            found_papers = await self._search_papers()
            if found_papers:
                await self._save_json("01_papers_encontrados.json", found_papers)
                await self._save_csv("01_papers_encontrados.csv", found_papers)
                await self._select_and_download_papers(found_papers)
                await self._generate_bibliography(found_papers)
            
            # Flujo de Hacker News
            hackernews_results = await self._search_hackernews()
            await self._save_json("04_hackernews_raw.json", hackernews_results)
            
            final_hn_results = await self._filter_with_llm(hackernews_results)
            await self._save_json("05_hackernews_filtrado_llm.json", final_hn_results)
            
            print(f"\n🎉 [{now_str()}] Proceso completado con éxito.")

        finally:
            print("\n🏁 Finalizando y cerrando conexiones…")
            if self.mcp_manager:
                await self.mcp_manager.close_all_clients()
                print("   [ÉXITO] Conexiones MCP cerradas.")

async def main():
    """Punto de entrada principal del script."""
    try:
        async with aiofiles.open("terminos.txt", "r", encoding="utf-8") as f:
            terminos = [t.strip() for t in (await f.read()).splitlines() if t.strip()]
        if not terminos:
            print("⚠️  'terminos.txt' está vacío. No hay nada que procesar.")
            return
    except FileNotFoundError:
        print("❌ ERROR: No se encontró 'terminos.txt'. Por favor, crea el archivo con los temas a investigar.")
        return
    
    topics = terminos[:MAX_TOPICS]
    print(f"✅ Temas a investigar ({len(topics)}): {topics}")
    
    assistant = AdvancedResearchAssistant(topics)
    await assistant.run()

if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())