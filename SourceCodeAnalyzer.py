import re
from typing import Optional

class SourceCodeAnalyzer:
    """
    Classe responsável por localizar funções em arquivos fonte C.
    """
    
    def __init__(self, source_code_path: str):
        """
        Inicializa com o caminho para o arquivo C.
        
        :param source_code_path: Caminho para o arquivo de código fonte.
        """
        self.source_code_path = source_code_path
        self.source_code = self._load_source_code()

    def _load_source_code(self) -> str:
        """
        Carrega o conteúdo do arquivo fonte.
        
        :return: Conteúdo do arquivo como string.
        """
        try:
            with open(self.source_code_path, 'r') as file:
                return file.read()
        except Exception as e:
            print(f"Erro ao carregar arquivo fonte: {e}")
            raise

    def find_function_definition(self, function_name: str) -> Optional[re.Match]:
        """
        Localiza a definição da função no código-fonte.
        
        :param function_name: Nome da função a ser localizada.
        :return: Match do regex se encontrado, ou None.
        """
        # Padrão simples: tipo retorno + nome função + (parametros)
        pattern = rf'^[\w\s\*]+{function_name}\s*\(.*?\)\s*\{{'
        
        # Regex multiline e case-sensitive
        match = re.search(pattern, self.source_code, re.MULTILINE | re.DOTALL)
        
        if match:
            print(f"Função '{function_name}' encontrada no arquivo '{self.source_code_path}'.")
            return match
        else:
            print(f"Função '{function_name}' NÃO encontrada no arquivo '{self.source_code_path}'.")
            return None
