# ai_client_manager.py

import asyncio
# Importa las bibliotecas cliente de cada proveedor de IA soportado.
import google.generativeai as genai  # Para Google Gemini
from anthropic import Anthropic       # Para Anthropic Claude
from groq import Groq                 # Para Groq
import ollama                         # Para Ollama (modelos locales)
from openai import OpenAI             # Para OpenAI
from typing import Callable, Any

class AIClientManager:
    """
    Gestiona la inicialización e interacción con diferentes clientes de IA.
    Actúa como una "fábrica" que crea el cliente correcto según la configuración
    y proporciona un método unificado 'chat_completion' para interactuar con él de forma no bloqueante.
    """
    def __init__(self, provider: str, api_key: str = None, model: str = None):
        """
        Constructor. Inicializa el cliente de IA basado en el proveedor especificado.
        :param provider: El nombre del proveedor (ej. "openai", "gemini").
        :param api_key: La clave de API para el proveedor.
        :param model: El nombre del modelo específico a usar (opcional).
        """
        self.provider = provider.lower()
        self.model = model
        self.client: Any = None
        print(f"Initializing AI client for provider: {self.provider}")

        # Lógica condicional para inicializar el cliente correcto.
        if self.provider == 'gemini':
            if not api_key: raise ValueError("Google API Key is required for Gemini provider.")
            genai.configure(api_key=api_key)
            self.client = genai.GenerativeModel(self.model or 'gemini-pro')
        elif self.provider == 'groq':
            if not api_key: raise ValueError("Groq API Key is required for Groq provider.")
            self.client = Groq(api_key=api_key)
        elif self.provider == 'ollama':
            # Para Ollama, el cliente es el propio módulo de la biblioteca.
            self.client = ollama
        elif self.provider == 'anthropic':
            if not api_key: raise ValueError("Anthropic API Key is required for Anthropic provider.")
            self.client = Anthropic(api_key=api_key)
        elif self.provider == 'openai':
            if not api_key: raise ValueError("OpenAI API Key is required for OpenAI provider.")
            self.client = OpenAI(api_key=api_key)
        else:
            raise ValueError(f"Unsupported AI provider: {self.provider}")

    async def chat_completion(self, prompt: str, max_tokens: int = 1024) -> str:
        """
        Envía un prompt al modelo de IA y devuelve la respuesta de texto.
        Este método abstrae las diferencias en las llamadas a la API y las ejecuta en un
        hilo separado para no bloquear el bucle de eventos de asyncio.
        """
        try:
            # Selecciona la función de llamada a la API correcta basada en el proveedor.
            api_call_function = self._get_api_call_function(prompt, max_tokens)
            
            # Ejecuta la llamada síncrona de la biblioteca en un hilo separado.
            # Esto es crucial para no bloquear la aplicación asíncrona.
            loop = asyncio.get_running_loop()
            response_text = await loop.run_in_executor(
                None,  # Usa el ejecutor de hilos por defecto.
                api_call_function
            )
            return response_text

        except Exception as e:
            print(f"Error calling {self.provider} API: {e}")
            return ""

    def _get_api_call_function(self, prompt: str, max_tokens: int) -> Callable[[], str]:
        """Devuelve la función lambda correcta para realizar la llamada a la API síncrona."""
        
        if self.provider == 'gemini':
            return lambda: self.client.generate_content(prompt).text

        elif self.provider == 'groq':
            return lambda: self.client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=self.model or "llama3-8b-8192",
            ).choices[0].message.content

        elif self.provider == 'ollama':
            return lambda: self.client.chat(
                model=self.model or 'llama3',
                messages=[{'role': 'user', 'content': prompt}]
            )['message']['content']

        elif self.provider == 'anthropic':
            return lambda: self.client.messages.create(
                model=self.model or "claude-3-sonnet-20240229",
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}]
            ).content[0].text

        elif self.provider == 'openai':
            return lambda: self.client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=self.model or "gpt-4o",
            ).choices[0].message.content
            
        else:
            # Esto no debería ocurrir si el constructor funcionó, pero es una salvaguarda.
            raise NotImplementedError(f"API call function not implemented for {self.provider}")
