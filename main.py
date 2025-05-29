from CSVHandler import CSVHandler
from SourceCodeAnalyzer import SourceCodeAnalyzer
from PresenceConditionExtractor import PresenceConditionExtractor

import os
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def main():
    input_csv_path = 'projects.csv'
    base_directory = '/home/lucas/Documents/pc_extractor/projects'
    output_csv_path = 'projects_with_pc.csv'

    logging.info(f"Inicializando processamento com CSV: {input_csv_path}")
    
    csv_handler = CSVHandler(input_csv_path)
    dataframe = csv_handler.load_csv()
    dataframe['PC'] = 'UNDEFINED'
    
    for index, row in dataframe.iterrows():
        project = row['Project']
        file_name = row['File']
        callee = row['Callee']
        
        source_code_path = os.path.join(base_directory, project, file_name)
        
        logging.info(f"Processando arquivo: {source_code_path}, função: {callee}")
        
        try:
            analyzer = SourceCodeAnalyzer(source_code_path)
            match = analyzer.find_function_definition(callee)
            
            if match:
                source_code = analyzer.source_code

                extractor = PresenceConditionExtractor(source_code)
                # ✅ Usa o método robusto com controle de blocos
                pc = extractor.extract_pc_with_blocks(callee)
                
                dataframe.at[index, 'PC'] = pc
                logging.info(f"Função '{callee}' → PC: {pc}")
            else:
                logging.warning(f"Função '{callee}' NÃO encontrada no arquivo '{file_name}'.")
                dataframe.at[index, 'PC'] = 'NOT_FOUND'
                
        except FileNotFoundError:
            logging.error(f"Arquivo não encontrado: {source_code_path}")
            dataframe.at[index, 'PC'] = 'FILE_NOT_FOUND'
        except Exception as e:
            logging.exception(f"Erro ao processar arquivo {source_code_path}: {e}")
            dataframe.at[index, 'PC'] = f'ERROR: {str(e)}'
    
    csv_handler.dataframe = dataframe
    csv_handler.save_csv(output_csv_path)
    logging.info(f"Processamento concluído. Arquivo salvo em: {output_csv_path}")

if __name__ == "__main__":
    main()
