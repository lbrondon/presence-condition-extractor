import pandas as pd
from typing import List

class CSVHandler:
    """
    Classe responsável por carregar e salvar o arquivo CSV de entrada e saída.
    """
    def __init__(self, csv_path: str):
        """
        Inicializa o CSVHandler com o caminho para o arquivo CSV.
        
        :param csv_path: Caminho para o arquivo CSV.
        """
        self.csv_path = csv_path
        self.dataframe = None

    def load_csv(self) -> pd.DataFrame:
        """
        Carrega o arquivo CSV e armazena internamente.
        
        :return: DataFrame com os dados carregados.
        """
        try:
            self.dataframe = pd.read_csv(self.csv_path)
            print(f"CSV carregado com {len(self.dataframe)} entradas.")
            return self.dataframe
        except Exception as e:
            print(f"Erro ao carregar CSV: {e}")
            raise

    def save_csv(self, output_path: str):
        """
        Salva o DataFrame atualizado com a coluna 'PC' no arquivo especificado.
        
        :param output_path: Caminho para o arquivo CSV de saída.
        """
        if self.dataframe is not None:
            try:
                self.dataframe.to_csv(output_path, index=False)
                print(f"CSV salvo com sucesso em: {output_path}")
            except Exception as e:
                print(f"Erro ao salvar CSV: {e}")
                raise
        else:
            raise ValueError("Nenhum DataFrame carregado para salvar.")
