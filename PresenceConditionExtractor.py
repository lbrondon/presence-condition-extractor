import re
from typing import List

class PresenceConditionExtractor:
    """
    Classe para extrair a Presence Condition (PC) de uma função no código-fonte,
    considerando blocos condicionais corretamente.
    """

    def __init__(self, source_code: str):
        """
        Inicializa com o código-fonte como string.
        
        :param source_code: Código-fonte do arquivo C.
        """
        self.source_code_lines = source_code.splitlines()

    def _normalize_expression(self, expr: str) -> str:
        """
        Normaliza expressões de diretivas, simplificando defined() para variável.
        
        :param expr: Expressão original.
        :return: Expressão normalizada.
        """
        expr = re.sub(r'defined\s*\(\s*(\w+)\s*\)', r'\1', expr)
        expr = re.sub(r'!\s*defined\s*\(\s*(\w+)\s*\)', r'!\1', expr)
        return expr.strip()

    def extract_pc_with_blocks(self, callee_name: str) -> str:
        """
        Extrai a Presence Condition da definição de uma função, considerando blocos condicionais.

        :param callee_name: Nome da função Callee.
        :return: Expressão booleana da PC ou 'TRUE' se não houver blocos.
        """
        block_stack: List[str] = []
        pc_conditions: List[str] = []
        
        # Regex para detectar definição de função
        func_pattern = re.compile(r'^[\w\s\*]+{}\s*\(.*?\)\s*\{{'.format(re.escape(callee_name)))
        
        for i, line in enumerate(self.source_code_lines):
            line = line.strip()

            # Detectar início de blocos condicionais
            if re.match(r'#\s*ifdef\s+(\w+)', line):
                feature = re.findall(r'#\s*ifdef\s+(\w+)', line)[0]
                block_stack.append(feature)
            elif re.match(r'#\s*ifndef\s+(\w+)', line):
                feature = re.findall(r'#\s*ifndef\s+(\w+)', line)[0]
                block_stack.append(f'!{feature}')
            elif re.match(r'#\s*if\s+(.+)', line):
                expr = re.findall(r'#\s*if\s+(.+)', line)[0]
                expr = self._normalize_expression(expr)
                block_stack.append(expr)
            elif re.match(r'#\s*elif\s+(.+)', line):
                expr = re.findall(r'#\s*elif\s+(.+)', line)[0]
                expr = self._normalize_expression(expr)
                if block_stack:
                    block_stack.pop()
                block_stack.append(expr)
            elif re.match(r'#\s*endif', line):
                if block_stack:
                    block_stack.pop()

            # Detectar definição de função
            if func_pattern.match(line):
                pc_conditions = block_stack.copy()
                break  # Encontrou a função, pode parar

        # Compor a expressão
        if pc_conditions:
            pc_expression = ' && '.join(pc_conditions)
            return pc_expression
        else:
            return 'TRUE'
