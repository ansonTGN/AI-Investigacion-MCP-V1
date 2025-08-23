import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Any, TypedDict

# Define un tipo para la metadata de las keywords para mejorar la legibilidad y el autocompletado.
class KeywordMetadata(TypedDict, total=False):
    score: int
    status: str
    source: str
    created_date: str
    last_used: Optional[str]
    discovered_from: Optional[str]

MasterKeywords = Dict[str, KeywordMetadata]

class KeywordManager:
    """
    Gestiona el ciclo de vida de las palabras clave con persistencia en archivos JSON.
    Maneja tres archivos principales:
      - keywords/master.json: Un catálogo de todas las keywords descubiertas con sus metadatos.
      - keywords/active.json: Una lista simple de las keywords a investigar en la próxima ejecución.
      - keywords/history.json: Un registro de las ejecuciones pasadas.
    """

    def __init__(self, keywords_dir: str = "keywords"):
        """Constructor. Define las rutas a los archivos y se asegura de que existan."""
        self.keywords_dir = keywords_dir
        self.master_file = os.path.join(keywords_dir, "master.json")
        self.active_file = os.path.join(keywords_dir, "active.json")
        self.history_file = os.path.join(keywords_dir, "history.json")

        # Asegura que el directorio 'keywords' exista.
        os.makedirs(self.keywords_dir, exist_ok=True)
        # Si los archivos JSON no existen, los crea con un contenido inicial vacío.
        if not os.path.exists(self.master_file):
            self._atomic_write(self.master_file, {})
        if not os.path.exists(self.active_file):
            self._atomic_write(self.active_file, [])
        if not os.path.exists(self.history_file):
            self._atomic_write(self.history_file, {})

    # ---------------------------------
    # Métodos para cargar/guardar JSON
    # ---------------------------------
    def load_master_keywords(self) -> MasterKeywords:
        """Carga el catálogo maestro de keywords desde master.json."""
        try:
            with open(self.master_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Devuelve los datos solo si son un diccionario, para evitar errores.
                return data if isinstance(data, dict) else {}
        except (FileNotFoundError, json.JSONDecodeError):
            # Si hay algún error (archivo no encontrado, JSON mal formado), devuelve un diccionario vacío.
            return {}

    def load_active_keywords(self) -> List[str]:
        """Carga la lista de keywords activas desde active.json."""
        try:
            with open(self.active_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Devuelve los datos solo si son una lista.
                return data if isinstance(data, list) else []
        except (FileNotFoundError, json.JSONDecodeError):
            # En caso de error, devuelve una lista vacía.
            return []

    def load_history(self) -> Dict[str, Any]:
        """Carga el historial de ejecuciones desde history.json."""
        try:
            with open(self.history_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Devuelve los datos solo si son un diccionario.
                return data if isinstance(data, dict) else {}
        except (FileNotFoundError, json.JSONDecodeError):
            # En caso de error, devuelve un diccionario vacío.
            return {}

    def save_master_keywords(self, keywords: MasterKeywords):
        """Guarda el catálogo maestro de keywords en master.json."""
        self._atomic_write(self.master_file, keywords)

    def save_active_keywords(self, keywords: List[str]):
        """Guarda la lista de keywords activas en active.json."""
        self._atomic_write(self.active_file, keywords)

    def save_history(self, history: Dict[str, Any]):
        """Guarda el historial de ejecuciones en history.json."""
        self._atomic_write(self.history_file, history)

    def _atomic_write(self, path: str, data: Any):
        """
        Realiza una escritura "atómica" para evitar la corrupción de archivos.
        Primero escribe en un archivo temporal (.tmp) y, si tiene éxito, lo renombra al archivo final.
        """
        tmp_path = path + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                # Vuelca los datos al archivo JSON con formato legible.
                json.dump(data, f, ensure_ascii=False, indent=2)
            # Reemplaza el archivo original con el nuevo archivo temporal.
            os.replace(tmp_path, path)
        except Exception as e:
            print(f"Error durante la escritura atómica en {path}: {e}")
            # Si hubo un error, intenta eliminar el archivo temporal si existe.
            if os.path.exists(tmp_path):
                os.remove(tmp_path)


    # ---------------------------------
    # API pública para gestionar keywords
    # ---------------------------------
    def add_new_keyword(
        self,
        keyword: str,
        score: int,
        status: str,
        source: str,
        discovered_from: Optional[str] = None
    ) -> bool:
        """
        Añade una nueva palabra clave al catálogo maestro si no existe previamente.
        Devuelve True si la keyword fue añadida, False si ya existía.
        """
        # Limpia la keyword de espacios en blanco.
        keyword = (keyword or "").strip()
        if not keyword:
            return False

        master = self.load_master_keywords()
        # Si la keyword ya está en el catálogo, no hace nada.
        if keyword in master:
            return False

        # Crea la nueva entrada para la palabra clave.
        now_date = datetime.now().strftime("%Y-%m-%d")
        entry: KeywordMetadata = {
            "score": int(score),
            "status": status,
            "source": source,
            "created_date": now_date,
            "last_used": None  # Aún no se ha usado para investigar.
        }
        if discovered_from:
            entry["discovered_from"] = discovered_from

        # Añade la nueva entrada al catálogo y lo guarda.
        master[keyword] = entry
        self.save_master_keywords(master)
        return True

    def update_keyword_score(self, keyword: str, new_score: int) -> bool:
        """Actualiza la puntuación de una palabra clave existente."""
        master = self.load_master_keywords()
        if keyword in master:
            master[keyword]["score"] = int(new_score)
            self.save_master_keywords(master)
            return True
        return False

    def mark_keywords_used(self, keywords: List[str]) -> None:
        """Marca una lista de palabras clave como 'usadas' en la fecha actual."""
        if not keywords:
            return

        master = self.load_master_keywords()
        today = datetime.now().strftime("%Y-%m-%d")

        changed = False
        for kw in keywords:
            kw = (kw or "").strip()
            if not kw:
                continue
            # Si la keyword no existía por alguna razón, la crea con datos por defecto.
            if kw not in master:
                master[kw] = {
                    "score": 0, "status": "unknown", "source": "runtime",
                    "created_date": today, "last_used": today
                }
                changed = True
            else:
                # Actualiza la fecha del último uso.
                master[kw]["last_used"] = today
                changed = True

        # Guarda los cambios solo si se realizó alguna modificación.
        if changed:
            self.save_master_keywords(master)

    def record_execution(self, keywords: List[str], status: str = "completed", new_keywords_found: int = 0) -> None:
        """Registra un resumen de la ejecución actual en el archivo de historial."""
        history = self.load_history()
        today = datetime.now().strftime("%Y-%m-%d")
        # Crea o sobrescribe la entrada para el día de hoy.
        history[today] = {
            "keywords_used": keywords,
            "execution_time": datetime.now().strftime("%H:%M:%S"),
            "status": status,
            "new_keywords_found": int(new_keywords_found)
        }
        self.save_history(history)

    def get_top_keywords(self, limit: int = 10) -> List[str]:
        """Devuelve una lista de las N mejores keywords según su puntuación y fecha de último uso."""
        master = self.load_master_keywords()
        
        # Define una función de ordenación compleja:
        def sort_key(item: tuple[str, KeywordMetadata]):
            kw, meta = item
            score = int(meta.get("score", 0))
            # Trata 'None' o '' como la fecha más antigua para priorizar keywords nunca usadas.
            last_used = meta.get("last_used") or "1970-01-01" 
            # Ordena por puntuación descendente (-score) y luego por fecha de último uso ascendente.
            return (-score, last_used)

        # Ordena los ítems del catálogo usando la clave definida.
        sorted_items = sorted(master.items(), key=sort_key)
        # Devuelve solo los nombres de las keywords del top N.
        return [kw for kw, _ in sorted_items[:limit]]

    def refresh_active_keywords(self, limit: int = 5) -> List[str]:
        """
        Selecciona las mejores keywords del catálogo maestro y las guarda en active.json
        para que sean usadas en la próxima ejecución.
        """
        top_keywords = self.get_top_keywords(limit=limit)
        self.save_active_keywords(top_keywords)
        return top_keywords
