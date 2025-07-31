import pandas as pd
from typing import Optional, List
import logging

class CSVHandler:
    """
    Classe utilitária para operações robustas de entrada e saída com arquivos CSV,
    utilizando pandas como backend de processamento tabular.

    Esta abstração provê métodos para carregar e salvar DataFrames, encapsulando
    detalhes de tratamento de exceções e integrando com o sistema de logging da aplicação.
    """

    def __init__(self, csv_path: str):
        """
        Inicializa o gerenciador com o caminho do arquivo CSV.

        Args:
            csv_path (str): Caminho absoluto ou relativo do arquivo CSV.
        """
        self.csv_path = csv_path
        self.dataframe: Optional[pd.DataFrame] = None

    def load_csv(self, required_columns: Optional[List[str]] = None) -> pd.DataFrame:
        """
        Carrega o conteúdo de um arquivo CSV em um DataFrame pandas.

        Args:
            required_columns (List[str], opcional): Lista de colunas esperadas para validação.

        Returns:
            pd.DataFrame: O DataFrame populado com os dados do arquivo CSV.

        Raises:
            IOError: Em caso de falha de leitura.
            ValueError: Caso colunas esperadas não estejam presentes.
        """
        try:
            df = pd.read_csv(self.csv_path)
            if required_columns:
                missing = [col for col in required_columns if col not in df.columns]
                if missing:
                    raise ValueError(f"CSV file is missing required columns: {missing}")
            self.dataframe = df
            logging.info(f"CSV carregado com sucesso: {self.csv_path} ({len(df)} linhas)")
            return df
        except Exception as e:
            logging.error(f"Erro ao carregar CSV: {e}")
            raise IOError(f"Falha ao carregar o arquivo CSV: {e}")

    def save_csv(self, output_path: str):
        """
        Salva o DataFrame corrente no caminho especificado.

        Args:
            output_path (str): Caminho de destino para salvar o CSV.

        Raises:
            ValueError: Caso não haja DataFrame em memória.
            IOError: Em caso de falha na escrita do arquivo.
        """
        if self.dataframe is not None:
            try:
                self.dataframe.to_csv(output_path, index=False)
                logging.info(f"CSV salvo com sucesso: {output_path}")
            except Exception as e:
                logging.error(f"Erro ao salvar CSV: {e}")
                raise IOError(f"Falha ao salvar o arquivo CSV: {e}")
        else:
            raise ValueError("Nenhum DataFrame carregado. Use load_csv() primeiro.")
