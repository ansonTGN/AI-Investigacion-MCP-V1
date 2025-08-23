# data_processor.py
# -*- coding: utf-8 -*-

# Importa el módulo 'asyncio' para ejecutar tareas síncronas en un hilo.
import asyncio
# Importa el módulo 'json' para trabajar con datos en formato JSON.
import json
# Importa el módulo 're' para trabajar con expresiones regulares (búsqueda de patrones en texto).
import re
# De 'collections', importa 'Counter' para contar fácilmente la frecuencia de elementos en una lista.
from collections import Counter
# De 'datetime', importa 'datetime' para obtener la fecha y hora actuales.
from datetime import datetime
# De 'typing', importa herramientas para anotaciones de tipo.
from typing import Dict, List, Any

# Importa el gestor de clientes de IA para que el analizador pueda usar LLMs.
from ai_client_manager import AIClientManager

class KeywordExtractor:
    """
    Extrae nuevas palabras clave a partir de los datos de investigación.
    Utiliza un LLM (Modelo Lingüístico Grande) si está disponible para una extracción más inteligente.
    Si no, recurre a un método heurístico local basado en frecuencia de palabras.
    """
    def __init__(self, ai_client_manager: AIClientManager = None):
        """
        Constructor. Recibe un gestor de cliente de IA.
        Este gestor debe tener un método `async chat_completion(prompt, max_tokens=...)`.
        """
        self.ai_client = ai_client_manager

    async def extract_keywords(self, research_data: List[Dict[str, Any]]) -> List[str]:
        """
        Método principal para extraer palabras clave.
        Decide si usar el LLM o el método heurístico de respaldo.
        """
        # Si no hay datos de investigación, no hay nada que hacer.
        if not research_data:
            print("No hay datos de investigación para la extracción de keywords.")
            return []

        # Prepara un resumen compacto del contenido para no enviar demasiada información al LLM.
        content_summary = self._prepare_content_for_analysis(research_data)

        # Si después de preparar el resumen no hay contenido, usa la heurística sobre los datos brutos.
        if not content_summary:
            print("No se encontró contenido utilizable. Usando heurística sobre corpus completo.")
            corpus = self._concat_corpus_from_raw(research_data)
            return self._heuristic_keywords(corpus)

        # Si hay un cliente de IA disponible, intenta usarlo.
        if self.ai_client:
            try:
                # Crea el prompt (la instrucción) para el LLM.
                prompt = self._create_extraction_prompt(content_summary)
                # Llama al LLM para obtener una respuesta.
                response = await self.ai_client.chat_completion(prompt, max_tokens=512)
                # Parsea la respuesta del LLM para extraer la lista de palabras clave.
                keywords = self._parse_keywords_from_response(response)
                provider = getattr(self.ai_client, "provider", "ai").capitalize()
                print(f"LLM ({provider}) extrajo {len(keywords)} keywords: {keywords}")
                return keywords
            except Exception as e:
                # Si el LLM falla, informa del error y pasa al método de respaldo.
                print(f"[KeywordExtractor] Fallo con LLM, usando heurística. Error: {e}")

        # Si no hay cliente de IA o si falló, usa el método heurístico local.
        corpus = self._concat_corpus(content_summary)
        return self._heuristic_keywords(corpus)

    # ---------- Métodos de utilidad internos ----------

    def _prepare_content_for_analysis(self, research_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Compacta los resultados de la investigación para crear un resumen manejable."""
        content_summary: List[Dict[str, Any]] = []
        for data in research_data:
            results = data.get("results", [])
            # Toma como máximo los 3 primeros resultados de cada plataforma para ser conciso.
            for result in results[:3]:
                content_summary.append({
                    "platform": data.get("platform", ""),
                    "keyword": data.get("keyword", ""),
                    "title": result.get("title") or result.get("name") or "",
                    # Acorta la descripción a 200 caracteres.
                    "description": (result.get("description") or result.get("snippet") or result.get("abstract") or "")[:200],
                    "topics": result.get("topics", []),
                })
        return content_summary

    def _create_extraction_prompt(self, content_summary: List[Dict[str, Any]]) -> str:
        """Crea el prompt que se enviará al LLM, pidiéndole que extraiga keywords en formato JSON."""
        return (
            "Analyze this AI trend research data and extract 5-10 new trending keywords related to AI, "
            "machine learning, or technology.\n\n"
            f"Data: {json.dumps(content_summary, indent=2, ensure_ascii=False)}\n\n"
            "Instructions:\n"
            "1. Focus on AI tools, frameworks, companies, techniques, or emerging technologies\n"
            "2. Return only a JSON array of keywords, like: [\"keyword1\", \"keyword2\", \"keyword3\"]\n"
            "3. Prioritize keywords that appear frequently or have high engagement\n"
            "4. Include both English and Japanese keywords if relevant\n"
            "5. If no relevant keywords are found, return an empty array: []\n"
        )

    def _parse_keywords_from_response(self, response: str) -> List[str]:
        """Parsea la respuesta del LLM. Intenta leer un array JSON, y si falla, lo trata como texto plano."""
        if not response:
            return []
        try:
            # Busca una estructura que parezca un array JSON (empieza con [ y termina con ]).
            m = re.search(r"\[.*?\]", response, re.DOTALL)
            if m:
                # Si lo encuentra, intenta decodificarlo como JSON.
                arr = json.loads(m.group())
                # Limpia y devuelve la lista de strings.
                return [s.strip() for s in arr if isinstance(s, str) and s.strip()]
        except Exception as e:
            # Si el parseo JSON falla, lo informa.
            print(f"Error parseando JSON de keywords: {e}")

        # Si no es JSON, lo trata como texto plano separado por comas.
        parts = response.replace("[", "").replace("]", "").replace('"', "")
        kws = [p.strip() for p in parts.split(",") if p.strip()]
        # Devuelve como máximo las 10 primeras.
        return kws[:10]

    def _concat_corpus(self, content_summary: List[Dict[str, Any]]) -> str:
        """Une todos los textos del resumen (títulos, descripciones, temas) en un solo bloque de texto (corpus)."""
        parts: List[str] = []
        for item in content_summary:
            parts.append(item.get("title", ""))
            parts.append(item.get("description", ""))
            topics = item.get("topics", [])
            if isinstance(topics, list) and topics:
                parts.extend([str(t) for t in topics])
        return " \n".join([p for p in parts if p])

    def _concat_corpus_from_raw(self, research_data: List[Dict[str, Any]]) -> str:
        """Similar a _concat_corpus, pero trabaja directamente con los datos brutos de investigación."""
        parts: List[str] = []
        for d in research_data:
            for r in d.get("results", []):
                parts.append(r.get("title") or r.get("name") or "")
                parts.append(r.get("description") or r.get("snippet") or r.get("abstract") or "")
                topics = r.get("topics", [])
                if isinstance(topics, list):
                    parts.extend([str(t) for t in topics])
        return " \n".join([p for p in parts if p])

    def _heuristic_keywords(self, corpus: str) -> List[str]:
        """
        Método heurístico de respaldo para extraer keywords.
        Se basa en encontrar las palabras y frases (n-gramas) más frecuentes.
        """
        if not corpus:
            return []

        text = corpus.lower()

        # Extrae tokens (palabras) que parecen relevantes.
        tokens = re.findall(r"[a-z0-9][a-z0-9\-_/\.]{2,}", text)
        # Define una lista de palabras comunes (stop words) para ignorar.
        stop = {
            "https", "http", "www", "com", "org", "from", "with", "that", "this", "what", "when",
            "your", "have", "about", "into", "like", "will", "there", "their", "been", "make",
            "only", "some", "more", "over", "also", "than", "which", "were", "after", "before",
            "because", "could", "should", "would"
        }
        tokens = [t for t in tokens if t not in stop]
        # Obtiene las 20 palabras más comunes.
        singles = [w for w, _ in Counter(tokens).most_common(20)]

        # Busca frases de 2 palabras (bigramas) y 3 palabras (trigramas).
        words = re.findall(r"[a-z0-9]+", text)
        bigrams = [" ".join(words[i:i+2]) for i in range(len(words)-1)]
        trigrams = [" ".join(words[i:i+3]) for i in range(len(words)-2)]
        # Cuenta la frecuencia de los n-gramas más relevantes.
        bf = Counter([b for b in bigrams if len(b) > 6])
        tf = Counter([t for t in trigrams if len(t) > 8])

        # Combina las palabras sueltas y los n-gramas más comunes.
        candidates = singles + [w for w, _ in bf.most_common(10)] + [w for w, _ in tf.most_common(10)]
        # Normaliza y limpia la lista final.
        return self._normalize_keywords(candidates)

    def _normalize_keywords(self, kws: List[str]) -> List[str]:
        """Limpia una lista de keywords: convierte a minúsculas, quita espacios y duplicados."""
        out: List[str] = []
        for kw in kws:
            k = re.sub(r"\s+", " ", kw.lower()).strip()
            k = k.strip(" .,:;-/\\|\"'()[]{}")
            if len(k) >= 3:
                out.append(k)
        # Elimina duplicados manteniendo el orden.
        seen = set()
        uniq = []
        for k in out:
            if k not in seen:
                seen.add(k)
                uniq.append(k)
        return uniq


class DataAnalyzer:
    """Analiza los datos recolectados para calcular métricas, puntuar keywords y generar recomendaciones."""
    
    def __init__(self, ai_client_manager: AIClientManager = None):
        """Constructor. Recibe el gestor de cliente de IA para generar recomendaciones dinámicas."""
        self.ai_client = ai_client_manager

    def score_keywords(self, new_keywords: List[str], research_data: List[Dict[str, Any]]) -> Dict[str, int]:
        """Asigna una puntuación a cada nueva palabra clave basada en su frecuencia en los resultados de la investigación."""
        if not new_keywords:
            return {}

        # Crea un gran bloque de texto (corpus) con todos los títulos, descripciones y temas.
        parts: List[str] = []
        for item in research_data:
            for r in item.get("results", []):
                title = r.get("title") or r.get("name") or ""
                desc = r.get("description") or r.get("snippet") or r.get("abstract") or ""
                topics = r.get("topics") or []
                parts.append(title)
                parts.append(desc)
                if isinstance(topics, list):
                    parts.extend([str(t) for t in topics])
        text = " \n".join([p for p in parts if p]).lower()

        # Cuenta cuántas veces aparece cada nueva palabra clave en el corpus.
        hits_map: Dict[str, int] = {}
        max_hits = 1
        for kw in new_keywords:
            if not kw:
                continue
            hits = len(re.findall(re.escape(kw.lower()), text))
            hits_map[kw] = hits
            if hits > max_hits:
                max_hits = hits

        # Normaliza las puntuaciones en una escala de 0 a 100 usando una escala logarítmica.
        import math
        scores: Dict[str, int] = {}
        for kw, h in hits_map.items():
            norm = math.log1p(h) / math.log1p(max_hits) if max_hits > 0 else 0.0
            scores[kw] = int(round(norm * 100))
        return scores

    def calculate_summary_stats(self, research_data: List[Dict[str, Any]], new_keywords: List[str]) -> Dict[str, Any]:
        """Calcula estadísticas agregadas básicas sobre la ejecución de la investigación."""
        # Cuenta cuántas ejecuciones se hicieron por plataforma.
        per_platform = Counter([d.get("platform", "unknown") for d in research_data])
        # Suma el total de resultados obtenidos.
        total_results = sum(len(d.get("results", [])) for d in research_data)
        # Cuenta cuántas ejecuciones tuvieron errores.
        runs_with_errors = sum(1 for d in research_data if d.get("error"))

        return {
            "timestamp": datetime.now().isoformat(),
            "platform_breakdown": dict(per_platform),
            "total_items": total_results,
            "new_keywords_count": len(new_keywords),
            "runs_with_errors": runs_with_errors,
        }

    async def generate_recommendations(self, research_data: List[Dict[str, Any]], new_keywords: List[str]) -> List[str]:
        """Genera una lista de recomendaciones de acción, usando IA si está disponible."""
        # Si no hay cliente de IA o no hay datos, usa el método de respaldo.
        if not self.ai_client or (not research_data and not new_keywords):
            return self._heuristic_recommendations(research_data, new_keywords)

        try:
            prompt = self._create_recommendation_prompt(research_data, new_keywords)
            response = await self.ai_client.chat_completion(prompt, max_tokens=512)
            # Parsea la respuesta en una lista de strings.
            recommendations = [rec.strip("- ").strip() for rec in response.split("\n") if rec.strip("- ").strip()]
            return recommendations if recommendations else ["No specific recommendations generated."]
        except Exception as e:
            print(f"Error generando recomendaciones con IA, usando heurística. Error: {e}")
            return self._heuristic_recommendations(research_data, new_keywords)

    def _create_recommendation_prompt(self, research_data: List[Dict[str, Any]], new_keywords: List[str]) -> str:
        """Crea el prompt para que el LLM genere recomendaciones."""
        summary_stats = self.calculate_summary_stats(research_data, new_keywords)
        
        # Prepara un resumen de los hallazgos más importantes para el prompt.
        top_findings = []
        for data in research_data:
            platform = data.get("platform")
            if data.get("results"):
                top_result = data["results"][0]
                title = top_result.get("title") or top_result.get("name")
                if title:
                    top_findings.append(f"- From {platform}: Found '{title}' related to '{data.get('keyword')}'.")
        
        return (
            "You are an AI research analyst. Based on the following summary of a trend investigation, "
            "provide 3-5 actionable and insightful recommendations for a research team. "
            "Focus on what to investigate next, what technologies seem promising, and potential content ideas.\n\n"
            f"--- Data Summary ---\n"
            f"Total items found: {summary_stats['total_items']}\n"
            f"Platforms with most results: {', '.join(summary_stats['platform_breakdown'].keys())}\n"
            f"New keywords discovered: {', '.join(new_keywords)}\n"
            f"Top findings:\n{''.join(top_findings[:5])}\n"
            f"--- End of Summary ---\n\n"
            "Generate the recommendations as a bulleted list (e.g., - Recommendation 1). Do not add any introductory text."
        )

    def _heuristic_recommendations(self, research_data: List[Dict[str, Any]], new_keywords: List[str]) -> List[str]:
        """Genera una lista de recomendaciones de acción simples basadas en los resultados."""
        recs: List[str] = []
        platform_counts = Counter([d.get("platform", "unknown") for d in research_data])

        # Añade recomendaciones específicas según las plataformas que devolvieron datos.
        if platform_counts.get("github", 0) > 0:
            recs.append("Priorizar repositorios con una alta tasa de estrellas (star_rate) y actividad reciente.")
        if platform_counts.get("web", 0) > 0:
            recs.append("Revisar los resultados web en japonés para detectar términos emergentes locales.")
        if platform_counts.get("arxiv", 0) > 0:
            recs.append("Leer los abstracts recientes de arXiv (≤ 30 días) para captar nuevas líneas de investigación.")
        
        # Si no hay recomendaciones, sugiere ampliar la búsqueda.
        if not recs:
            recs.append("Ampliar las fuentes o las palabras clave para obtener más señales.")
        
        # Si se encontraron nuevas keywords, sugiere explorarlas.
        if new_keywords:
            recs.append(f"Explorar en profundidad las nuevas keywords descubiertas: {', '.join(new_keywords[:5])}...")

        return recs
