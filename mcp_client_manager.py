# mcp_client_manager.py
# -*- coding: utf-8 -*-

# Importa el módulo 'asyncio' para la programación asíncrona.
import asyncio
# Importa el módulo 'os' para leer variables de entorno.
import os
# Importa herramientas de 'typing' para anotaciones de tipo.
from typing import Dict, List, Any, Optional
# De 'contextlib', importa 'AsyncExitStack' para gestionar múltiples contextos asíncronos de forma segura.
from contextlib import AsyncExitStack

# Importa las clases necesarias de la biblioteca 'mcp'.
from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters


class RemoteMCPClient:
    """
    Representa un cliente para un único servidor MCP que se ejecuta como un proceso local (ej. iniciado con npx).
    Gestiona la conexión, los reintentos, las llamadas a herramientas y el cierre seguro.
    """

    def __init__(self):
        """Constructor. Inicializa el estado del cliente."""
        self.session: Optional[ClientSession] = None  # La sesión de comunicación MCP.
        self.exit_stack: Optional[AsyncExitStack] = None  # Para gestionar recursos asíncronos.
        self._connected: bool = False  # Flag para indicar si la conexión está activa.
        self._cleanup_attempted: bool = False  # Flag para evitar limpiezas duplicadas.
        self._available_tools: List[str] = []  # Lista de herramientas que ofrece el servidor.

    async def connect_to_server_by_name(
        self,
        server_name: str,
        args: List[str] = None,
        env: Dict[str, Any] = None
    ) -> bool:
        """
        Establece una conexión con un servidor MCP a través de su entrada/salida estándar (stdio).
        Implementa una lógica de reintentos y timeouts adaptables.
        """
        args = args or []
        joined_args = " ".join(args)

        # Heurística para definir timeouts de conexión más largos para servidores que tardan más en arrancar.
        base_timeout = 15.0
        if "one-search-mcp" in server_name or "one-search-mcp" in joined_args:
            init_timeout = 45.0
        elif "@langgpt/arxiv-mcp-server" in joined_args:
            init_timeout = 60.0
        else:
            init_timeout = base_timeout

        # Permite sobrescribir el timeout globalmente mediante una variable de entorno.
        try:
            init_timeout = float(os.getenv("MCP_INIT_TIMEOUT", init_timeout))
        except (ValueError, TypeError):
            pass

        # Prepara el diccionario de entorno, limpiándolo de valores nulos o vacíos.
        clean_env: Optional[Dict[str, str]] = None
        if env:
            cleaned = {k: str(v) for k, v in env.items() if v not in (None, "")}
            clean_env = cleaned if cleaned else None

        attempts = 2  # Número de intentos de conexión (1 original + 1 reintento).
        last_err: Optional[BaseException] = None
        full_cmd = " ".join([server_name] + args)

        # Bucle de intentos de conexión.
        for attempt in range(1, attempts + 1):
            try:
                # Prepara un 'AsyncExitStack' para este intento.
                self.exit_stack = AsyncExitStack()

                print(f"[MCP] Conectando a '{os.path.basename(server_name)}' (intento {attempt}/{attempts})")
                if clean_env:
                    print(f"      ┖─ Entorno: {list(clean_env.keys())}")
                print(f"      ┖─ Timeout: {int(init_timeout)}s")


                # Define los parámetros para iniciar el servidor como un subproceso.
                server_params = StdioServerParameters(
                    command=server_name,
                    args=args,
                    env=clean_env
                )

                # Inicia el cliente stdio, que a su vez lanza el proceso del servidor.
                stdio_context = stdio_client(server_params)
                # Entra en el contexto del cliente para obtener los streams de lectura y escritura.
                read_stream, write_stream = await self.exit_stack.enter_async_context(stdio_context)

                # Crea una sesión MCP usando los streams.
                session_context = ClientSession(read_stream, write_stream)
                self.session = await self.exit_stack.enter_async_context(session_context)

                # Llama al método 'initialize' del servidor con un tiempo de espera.
                try:
                    await asyncio.wait_for(self.session.initialize(), timeout=init_timeout)
                except asyncio.TimeoutError:
                    raise TimeoutError(f"Timeout en initialize() para '{os.path.basename(server_name)}'")

                # Si la inicialización es exitosa, obtiene la lista de herramientas disponibles.
                response = await self.session.list_tools()
                tools = response.tools
                self._available_tools = [tool.name for tool in tools]
                print(f"  ✓ Conexión exitosa a '{os.path.basename(server_name)}' | Herramientas: {self._available_tools}")

                self._connected = True
                return True  # Conexión exitosa, sale del bucle.

            except Exception as e:
                # Si ocurre un error, lo registra y se prepara para el siguiente intento.
                last_err = e
                print(f"  ✗ Error al conectar '{os.path.basename(server_name)}' (intento {attempt}/{attempts}): {e}")

                # Limpia los recursos del intento fallido.
                try:
                    if self.exit_stack:
                        await asyncio.wait_for(self.exit_stack.aclose(), timeout=5.0)
                except Exception as close_err:
                    print(f"    Aviso: Error durante la limpieza del intento fallido: {close_err}")


                self.session = None
                self.exit_stack = None
                self._connected = False

                # Espera un poco antes de reintentar.
                if attempt < attempts:
                    await asyncio.sleep(2.0)

        print(f"  ✗ Fallo definitivo conectando a '{os.path.basename(server_name)}': {last_err}")
        return False

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]):
        """Llama a una herramienta específica del servidor MCP conectado."""
        if not self.session or not self._connected:
            raise ConnectionError("No está conectado a ningún servidor MCP para llamar a la herramienta.")

        try:
            # Llama a la herramienta y espera la respuesta.
            response = await self.session.call_tool(tool_name, arguments)
            # Devuelve el contenido principal de la respuesta, que puede estar en 'content' o 'result'.
            if hasattr(response, "content"):
                return response.content
            if hasattr(response, "result"):
                return response.result
            return response
        except Exception as e:
            print(f"✗ Error al llamar a la herramienta '{tool_name}': {e}")
            # Devuelve None o relanza una excepción más específica.
            return None

    def get_available_tools(self) -> List[str]:
        """Devuelve la lista de nombres de herramientas disponibles en el servidor."""
        return self._available_tools

    async def _cleanup(self):
        """Método privado para cerrar y limpiar los recursos del cliente de forma segura."""
        if self._cleanup_attempted:
            return
        self._cleanup_attempted = True

        try:
            # Usa el 'AsyncExitStack' para cerrar todos los contextos abiertos (sesión, proceso, etc.).
            if self.exit_stack:
                await asyncio.wait_for(self.exit_stack.aclose(), timeout=5.0)
        except asyncio.TimeoutError:
            print("Aviso: Tiempo de espera de limpieza agotado, forzando cierre")
        except asyncio.CancelledError:
            print("Aviso: La limpieza fue cancelada")
        except Exception as e:
            print(f"Aviso: Error durante la limpieza: {e}")
        finally:
            self.exit_stack = None

    async def close(self):
        """Método público para cerrar la conexión con el servidor de forma segura."""
        if not self._connected:
            return
        self._connected = False
        try:
            # Llama al método de limpieza con un tiempo de espera.
            await asyncio.wait_for(self._cleanup(), timeout=10.0)
        except Exception as e:
            print(f"Aviso: Error durante el cierre: {e}")
        finally:
            # Resetea el estado del cliente.
            self.session = None
            self.exit_stack = None


class MCPClientManager:
    """
    Gestiona un conjunto de múltiples 'RemoteMCPClient', uno para cada plataforma.
    Orquesta la conexión y desconexión de todos ellos.
    """

    def __init__(self, server_configs: Dict[str, Dict]):
        """Constructor. Recibe las configuraciones de todos los servidores."""
        self.server_configs = server_configs
        # Diccionario para almacenar las instancias de cliente, una por plataforma.
        self.clients: Dict[str, Optional[RemoteMCPClient]] = {}

    async def connect_all_servers(self):
        """Intenta conectar a todos los servidores que están marcados como habilitados en la configuración."""
        print("\n[MCP] Conectando a todos los servidores habilitados...")
        
        # Crea tareas para conectar a todos los servidores en paralelo.
        tasks = [
            self._connect_single_server(platform, config)
            for platform, config in self.server_configs.items()
            if config.get("enabled", False)
        ]
        
        # Ejecuta las tareas de conexión concurrentemente.
        await asyncio.gather(*tasks)

        # Imprime los servidores omitidos.
        for platform, config in self.server_configs.items():
            if not config.get("enabled", False):
                print(f"  ↷ Omitido '{platform}' (deshabilitado en config)")


    async def _connect_single_server(self, platform: str, config: Dict):
        """Crea un cliente y intenta conectar a un único servidor MCP."""
        try:
            mcp_client = RemoteMCPClient()
            args = config.get("args", [])
            env = config.get("env", {})
            # Llama al método de conexión del cliente.
            success = await mcp_client.connect_to_server_by_name(config["server_name"], args, env)

            # Si la conexión es exitosa, almacena el cliente. Si no, almacena None.
            self.clients[platform] = mcp_client if success else None
        except Exception as e:
            print(f"  ✗ Fallo crítico al inicializar la conexión para {platform}: {e}")
            self.clients[platform] = None

    def get_client(self, platform: str) -> Optional[RemoteMCPClient]:
        """Devuelve la instancia del cliente para una plataforma, o None si no está conectado."""
        return self.clients.get(platform)

    def is_platform_available(self, platform: str) -> bool:
        """Comprueba si el cliente de una plataforma está conectado y disponible."""
        client = self.clients.get(platform)
        return client is not None and client._connected

    def get_available_tools(self, platform: str) -> List[str]:
        """Obtiene la lista de herramientas disponibles para una plataforma específica."""
        client = self.get_client(platform)
        return client.get_available_tools() if client else []

    async def close_all_clients(self):
        """
        Cierra todos los clientes MCP conectados de forma SECUENCIAL.
        Esto es importante en asyncio para evitar problemas de cancelación de tareas.
        """
        print("[MCP] Cerrando todos los clientes...")
        # Itera sobre una copia de los ítems para poder modificar el diccionario original.
        for platform, client in list(self.clients.items()):
            if client:
                try:
                    print(f"      ┖─ Cerrando '{platform}'...")
                    await client.close()  # Espera a que cada cliente se cierre antes de pasar al siguiente.
                except Exception as e:
                    print(f"      ┖─ Error al cerrar '{platform}': {e}")
        # Limpia el diccionario de clientes.
        self.clients.clear()
        print("[MCP] Todos los clientes cerrados.")
