# platform_handlers.py
# -*- coding: utf-8 -*-

# Este archivo es una versión consolidada y mejorada que fusiona la lógica de
# platform_manager.py y platform_handlers.py, eliminando la redundancia.

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
from datetime import datetime
import json
import re
from collections import Counter
from urllib.parse import urlparse

# NOTA: No se importa AIClientManager aquí para evitar una dependencia circular.
# Se pasa como un argumento en el método de la fábrica 'create_handler'.

# ---------------- Clase Base ----------------
class BasePlatformHandler(ABC):
    """
    Define la plantilla (interfaz) que todos los manejadores de plataforma deben seguir.
    Garantiza una estructura consistente.
    """
    def __init__(self, platform_name: str):
        """Constructor. Almacena el nombre de la plataforma."""
        self.platform_name = platform_name
    
    @abstractmethod
    async def research_keyword(self, client: Any, keyword: str, config: Dict) -> Dict[str, Any]:
        """Método abstracto para la lógica de investigación. Debe ser implementado por las subclases."""
        pass
    
    @abstractmethod
    def process_response(self, response: Any, keyword: str) -> Dict[str, Any]:
        """Método abstracto para procesar la respuesta cruda. Debe ser implementado por las subclases."""
        pass
    
    def create_error_result(self, keyword: str, error: str) -> Dict[str, Any]:
        """Método de utilidad para crear un resultado de error estandarizado."""
        return {
            "platform": self.platform_name, "keyword": keyword, "timestamp": datetime.now().isoformat(),
            "results": [], "new_keywords": [], "sentiment_score": 0.0,
            "engagement_metrics": {}, "error": str(error)
        }

# ---------------- Manejador de YouTube ----------------
class YouTubeHandler(BasePlatformHandler):
    """Manejador con la lógica específica para investigar en YouTube."""
    def __init__(self):
        super().__init__("youtube")
    
    async def research_keyword(self, client: Any, keyword: str, config: Dict) -> Dict[str, Any]:
        try:
            params = {"query": keyword, "order": "relevance", "type": "video", "max_results": 10}
            tool_name = config["tools"][0]
            response = await client.call_tool(tool_name, params)
            return self.process_response(response, keyword)
        except Exception as e:
            return self.create_error_result(keyword, str(e))
    
    def process_response(self, response: Any, keyword: str) -> Dict[str, Any]:
        results = []
        data = self._extract_data_from_response(response)
        videos = data.get('videos', data.get('items', [])) if isinstance(data, dict) else (data if isinstance(data, list) else [])
        
        for video in videos:
            snippet = video.get('snippet', {})
            video_id = video.get('id', {}).get('videoId', '')
            if not video_id: continue

            results.append({
                'title': snippet.get('title', ''), 'description': snippet.get('description', ''),
                'published_at': snippet.get('publishedAt', ''), 'channel': snippet.get('channelTitle', ''),
                'video_id': video_id, 'url': f"https://www.youtube.com/watch?v={video_id}",
                'content_type': self._classify_content(snippet.get('title', ''), snippet.get('description', '')),
                'language': self._detect_language(snippet.get('title', '') + ' ' + snippet.get('description', ''))
            })
        return {
            "platform": self.platform_name, "keyword": keyword, "timestamp": datetime.now().isoformat(),
            "results": results, "new_keywords": [], "sentiment_score": 0.0,
            "engagement_metrics": self._calculate_engagement_metrics(results)
        }
    
    def _extract_data_from_response(self, response: Any) -> Any:
        if isinstance(response, list) and len(response) > 0 and hasattr(response[0], 'text'):
            try: return json.loads(response[0].text)
            except (json.JSONDecodeError, AttributeError): return {}
        elif hasattr(response, 'content'): return response.content
        return response if isinstance(response, (dict, list)) else {}

    def _classify_content(self, title: str, description: str) -> str:
        text = (title + ' ' + description).lower()
        if any(k in text for k in ['解説', '説明', '入門', '基礎', '学習', 'チュートリアル']): return "解説動画"
        elif any(k in text for k in ['デモ', 'デモンストレーション', '実演', 'サンプル']): return "デモ"
        elif any(k in text for k in ['カンファレンス', 'セミナー', '講演', '発表', 'talk']): return "カンファレンス"
        elif any(k in text for k in ['ニュース', '最新', 'アップデート', 'リリース']): return "ニュース"
        else: return "その他"
    
    def _detect_language(self, text: str) -> str:
        if re.search(r'[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]', text): return "ja"
        return "en"
    
    def _calculate_engagement_metrics(self, results: List[Dict]) -> Dict:
        return {"total_videos": len(results)}

# ---------------- Manejador de GitHub ----------------
class GitHubHandler(BasePlatformHandler):
    """Manejador robusto para investigar en GitHub."""
    def __init__(self):
        super().__init__("github")
    
    async def research_keyword(self, client: Any, keyword: str, config: Dict) -> Dict[str, Any]:
        try:
            params = {
                "query": f"{keyword} stars:>50", "sort": "stars",
                "order": "desc", "per_page": 10
            }
            tool_name = "search_repositories"
            response = await client.call_tool(tool_name, params)
            return self.process_response(response, keyword)
        except Exception as e:
            return self.create_error_result(keyword, str(e))
    
    def process_response(self, response: Any, keyword: str) -> Dict[str, Any]:
        results = []
        repos = self._extract_repositories(response)
        for repo in repos:
            if isinstance(repo, dict):
                stars = repo.get('stargazers_count', repo.get('stars', 0))
                created_at = repo.get('created_at', '')
                star_rate, days_old, is_trending = self._calculate_trend_metrics(stars, created_at)
                results.append({
                    'name': repo.get('name', ''), 'description': repo.get('description', ''),
                    'owner': repo.get('owner', {}).get('login', ''), 'stars': stars, 'language': repo.get('language', ''),
                    'url': repo.get('html_url', ''), 'created_at': created_at, 'topics': repo.get('topics', []),
                    'star_rate': round(star_rate, 2), 'days_old': days_old, 'is_trending': is_trending,
                    'trend_score': self._calculate_trend_score(stars, days_old, star_rate)
                })
        return {
            "platform": self.platform_name, "keyword": keyword, "timestamp": datetime.now().isoformat(),
            "results": results, "new_keywords": [], "sentiment_score": 0.0,
            "engagement_metrics": self._calculate_engagement_metrics(results)
        }
    
    def _extract_repositories(self, response: Any) -> List[Dict]:
        if not response: return []
        if isinstance(response, str):
            try: return self._extract_repositories(json.loads(response))
            except json.JSONDecodeError: return []
        if isinstance(response, list) and len(response) > 0 and hasattr(response[0], 'text'):
            try: return self._extract_repositories(json.loads(response[0].text))
            except (json.JSONDecodeError, AttributeError): return []
        if isinstance(response, list): return response
        if isinstance(response, dict): return response.get('items', response.get('repositories', []))
        return []

    def _calculate_trend_metrics(self, stars: int, created_at: str) -> tuple:
        if not created_at or not isinstance(stars, int): return (0.0, 0, False)
        try:
            created_date = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            days_old = (datetime.now(created_date.tzinfo) - created_date).days
            if days_old <= 0: return (stars, 0, False)
            star_rate = stars / days_old
            is_trending = (stars >= 100 and days_old <= 365 and star_rate > 0.5)
            return (star_rate, days_old, is_trending)
        except (ValueError, TypeError): return (0.0, 0, False)
    
    def _calculate_trend_score(self, stars: int, days_old: int, star_rate: float) -> float:
        if days_old <= 0: return 0.0
        base_score = min(star_rate * 10, 50)
        recency_bonus = max(0, (365 - days_old) / 365 * 30)
        star_bonus = min(stars / 200, 20)
        return round(min(base_score + recency_bonus + star_bonus, 100), 2)
    
    def _calculate_engagement_metrics(self, results: List[Dict]) -> Dict:
        if not results: return {"repo_count": 0}
        languages = [r.get('language') for r in results if r.get('language')]
        return {
            "repo_count": len(results),
            "total_stars": sum(r.get('stars', 0) for r in results),
            "trending_repos_count": sum(1 for r in results if r.get('is_trending')),
            "top_languages": dict(Counter(languages).most_common(3)) if languages else {}
        }

# ---------------- Manejador de Web ----------------
class WebHandler(BasePlatformHandler):
    def __init__(self):
        super().__init__("web")
    
    async def research_keyword(self, client: Any, keyword: str, config: Dict) -> Dict[str, Any]:
        try:
            params = {"query": f"{keyword} site:github.com OR site:arxiv.org OR site:huggingface.co", "language": "ja", "region": "jp", "max_results": 10}
            tool_name = config["tools"][0]
            response = await client.call_tool(tool_name, params)
            return self.process_response(response, keyword)
        except Exception as e:
            return self.create_error_result(keyword, str(e))
    
    def process_response(self, response: Any, keyword: str) -> Dict[str, Any]:
        results = self._parse_web_results(response)
        return {
            "platform": self.platform_name, "keyword": keyword, "timestamp": datetime.now().isoformat(),
            "results": results, "new_keywords": [], "sentiment_score": 0.0,
            "engagement_metrics": {"search_count": len(results)}
        }
    
    def _parse_web_results(self, response: Any) -> List[Dict]:
        if isinstance(response, list) and len(response) > 0 and hasattr(response[0], 'text'):
            try: response = json.loads(response[0].text)
            except (json.JSONDecodeError, AttributeError): response = {}
        
        results = []
        web_results = response.get('results', []) if isinstance(response, dict) else []
        for result in web_results:
            url = result.get('url', result.get('link', ''))
            results.append({
                'title': result.get('title', ''), 'snippet': result.get('snippet', ''),
                'url': url, 'source': urlparse(url).netloc if url else ''
            })
        return results

# ---------------- Manejador de ArXiv ----------------
class ArxivHandler(BasePlatformHandler):
    def __init__(self, ai_client_manager: Optional[Any] = None):
        super().__init__("arxiv")
        self.ai_client = ai_client_manager
    
    async def research_keyword(self, client: Any, keyword: str, config: Dict) -> Dict[str, Any]:
        try:
            english_query = await self._translate_keyword(keyword)
            params = {"query": english_query, "max_results": 10, "sort_by": "relevance"}
            response = await client.call_tool("search_arxiv", params)
            return self.process_response(response, keyword)
        except Exception as e:
            return self.create_error_result(keyword, str(e))

    async def _translate_keyword(self, keyword: str) -> str:
        if not self.ai_client or not re.search(r'[\u3040-\u30ff]', keyword): return keyword
        try:
            prompt = f"Translate the following Japanese technical keyword to English for an ArXiv search. Provide only the English translation, no extra text. Keyword: '{keyword}'"
            translation = await self.ai_client.chat_completion(prompt)
            return translation.strip().replace('"', '') or keyword
        except Exception: return keyword
            
    def process_response(self, response: Any, keyword: str) -> Dict[str, Any]:
        results = []
        papers = self._extract_papers(response)
        for paper in papers:
            if isinstance(paper, dict):
                published_date = paper.get('published', '')
                days_old, is_recent = self._calculate_time_metrics(published_date)
                results.append({
                    'title': paper.get('title', ''), 'abstract': paper.get('summary', ''),
                    'authors': paper.get('authors', []), 'published_date': published_date,
                    'url': paper.get('url', ''), 'days_old': days_old, 'is_recent': is_recent,
                })
        return {
            "platform": self.platform_name, "keyword": keyword, "timestamp": datetime.now().isoformat(),
            "results": results, "new_keywords": [], "sentiment_score": 0.0,
            "engagement_metrics": {"paper_count": len(results), "recent_paper_count": sum(1 for r in results if r['is_recent'])}
        }

    def _extract_papers(self, response: Any) -> List[Dict]:
        if isinstance(response, list) and len(response)>0 and hasattr(response[0], 'text'):
            try: response = json.loads(response[0].text)
            except (json.JSONDecodeError, AttributeError): return []
        if isinstance(response, dict): return response.get('results', [])
        if isinstance(response, list): return response
        return []

    def _calculate_time_metrics(self, published_date: str) -> tuple:
        if not published_date: return (9999, False)
        try:
            pub_date = datetime.fromisoformat(published_date.replace('Z', '+00:00'))
            days_old = (datetime.now(pub_date.tzinfo) - pub_date).days
            return (days_old, days_old <= 90)
        except (ValueError, TypeError): return (9999, False)

# ---------------- Manejador de HackerNews ----------------
class HackerNewsHandler(BasePlatformHandler):
    def __init__(self, ai_client_manager: Optional[Any] = None):
        super().__init__("hackernews")
        self.ai_client = ai_client_manager
        
    async def research_keyword(self, client: Any, keyword: str, config: Dict) -> Dict[str, Any]:
        try:
            english_keyword = await self._translate_keyword(keyword)
            # HackerNews tool might be named 'search' or similar, adapt as needed.
            # Assuming the tool is 'getStories' for this implementation.
            params = {"query": english_keyword, "max_results": 15}
            response = await client.call_tool(config['tools'][0], params)
            return self.process_response(response, keyword)
        except Exception as e:
            return self.create_error_result(keyword, str(e))
    
    async def _translate_keyword(self, keyword: str) -> str:
        # Same translation logic as Arxiv
        if not self.ai_client or not re.search(r'[\u3040-\u30ff]', keyword): return keyword
        try:
            prompt = f"Translate the following Japanese keyword to a simple English equivalent for a HackerNews search. Provide only the English translation. Keyword: '{keyword}'"
            translation = await self.ai_client.chat_completion(prompt)
            return translation.strip().replace('"', '') or keyword
        except Exception: return keyword

    def process_response(self, response: Any, keyword: str) -> Dict[str, Any]:
        results = []
        posts = self._extract_posts(response)
        for post in posts:
            if isinstance(post, dict):
                results.append({
                    'title': post.get('title', ''), 'url': post.get('url', ''),
                    'score': post.get('score', post.get('points', 0)),
                    'comments_count': post.get('descendants', post.get('num_comments', 0)),
                })
        return {
            "platform": self.platform_name, "keyword": keyword, "timestamp": datetime.now().isoformat(),
            "results": results, "new_keywords": [], "sentiment_score": 0.0,
            "engagement_metrics": self._calculate_engagement_metrics(results)
        }
    
    def _extract_posts(self, response: Any) -> List[Dict]:
        if isinstance(response, list): return response
        if isinstance(response, dict): return response.get('hits', [])
        return []

    def _calculate_engagement_metrics(self, results: List[Dict]) -> Dict:
        if not results: return {"post_count": 0}
        post_count = len(results)
        total_score = sum(r.get('score', 0) for r in results)
        return {"post_count": post_count, "avg_score": round(total_score / post_count if post_count > 0 else 0)}

# ---------------- Manejador de Supabase (Placeholder) ----------------
class SupabaseHandler(BasePlatformHandler):
    def __init__(self):
        super().__init__("supabase")
    
    async def research_keyword(self, client: Any, keyword: str, config: Dict) -> Dict[str, Any]:
        return self.create_error_result(keyword, "Supabase no se utiliza para la investigación de keywords.")
    
    def process_response(self, response: Any, keyword: str) -> Dict[str, Any]:
        return self.create_error_result(keyword, "Supabase no se utiliza para la investigación de keywords.")

# ---------------- Manejador de Research Hub ----------------
class ResearchHubHandler(BasePlatformHandler):
    def __init__(self):
        super().__init__("research_hub")

    async def research_keyword(self, client: Any, keyword: str, config: Dict) -> Dict[str, Any]:
        try:
            params = {"query": keyword, "limit": 10}
            response = await client.call_tool("search_papers", params)
            return self.process_response(response, keyword)
        except Exception as e:
            return self.create_error_result(keyword, str(e))

    def process_response(self, response: Any, keyword: str) -> Dict[str, Any]:
        results = []
        papers_data = response
        if isinstance(response, list) and len(response) > 0 and hasattr(response[0], 'content'):
            try: papers_data = json.loads(response[0].content)
            except (json.JSONDecodeError, AttributeError): papers_data = []

        if isinstance(papers_data, list):
            for paper in papers_data:
                results.append({
                    'title': paper.get('title', 'N/A'), 'authors': ", ".join(paper.get('authors', [])),
                    'url': paper.get('url', ''), 'abstract': paper.get('summary', ''),
                    'source': paper.get('source', 'Unknown'), 'year': paper.get('year', 0)
                })
        return {
            "platform": self.platform_name, "keyword": keyword, "timestamp": datetime.now().isoformat(),
            "results": results, "new_keywords": [], "sentiment_score": 0.0,
            "engagement_metrics": self._calculate_engagement_metrics(results)
        }

    def _calculate_engagement_metrics(self, results: List[Dict]) -> Dict:
        if not results: return {"paper_count": 0, "recent_papers_count": 0}
        current_year = datetime.now().year
        recent_papers = sum(1 for p in results if p.get('year', 0) >= current_year - 2)
        return {"paper_count": len(results), "recent_papers_count": recent_papers}

# ---------------- Fábrica de Manejadores ----------------
class PlatformHandlerFactory:
    """Utiliza el patrón de diseño Factory para crear el manejador de plataforma correcto."""
    
    _handler_classes: Dict[str, Any] = {
        "youtube": YouTubeHandler,
        "github": GitHubHandler,
        "web": WebHandler,
        "arxiv": ArxivHandler,
        "hackernews": HackerNewsHandler,
        "supabase": SupabaseHandler,
        "research_hub": ResearchHubHandler
    }

    @staticmethod
    def create_handler(platform: str, ai_client_manager: Optional[Any] = None) -> BasePlatformHandler:
        handler_class = PlatformHandlerFactory._handler_classes.get(platform)
        if not handler_class:
            raise ValueError(f"No hay un manejador disponible para la plataforma: {platform}")
        
        # Inyecta el cliente de IA si el constructor del manejador lo acepta.
        import inspect
        sig = inspect.signature(handler_class.__init__)
        if 'ai_client_manager' in sig.parameters:
            return handler_class(ai_client_manager=ai_client_manager)
        else:
            return handler_class()
