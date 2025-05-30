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
    base_directory = '/home/lucas/Documents/presence_condition_extractor/projects'
    output_csv_path = '/home/lucas/Documents/presence_condition_extractor/output/projects_with_pc.csv'

    logging.info(f"Starting CSV processing: {input_csv_path}")
    
    csv_handler = CSVHandler(input_csv_path)
    dataframe = csv_handler.load_csv()
    dataframe['PC'] = 'UNDEFINED'
    
    for index, row in dataframe.iterrows():
        project = row['Project']
        file_name = row['File']
        caller = row['Caller']
        callee = row['Callee']
        
        source_code_path = os.path.join(base_directory, project, file_name)
        logging.info(f"Processing file: {source_code_path}, Caller: {caller}, Callee: {callee}")
        
        try:
            analyzer = SourceCodeAnalyzer(source_code_path)
            source_code = analyzer.source_code

            extractor = PresenceConditionExtractor(source_code)
            pc = extractor.extract_pc_from_caller_context(caller, callee)
            dataframe.at[index, 'PC'] = pc

            logging.info(f"{caller} → {callee} → PC: {pc}")

        except FileNotFoundError:
            logging.error(f"File not found: {source_code_path}")
            dataframe.at[index, 'PC'] = 'FILE_NOT_FOUND'
        except Exception as e:
            logging.exception(f"Error processing file {source_code_path}: {e}")
            dataframe.at[index, 'PC'] = f'ERROR: {str(e)}'
    
    csv_handler.dataframe = dataframe
    csv_handler.save_csv(output_csv_path)
    logging.info(f"Processing completed. Output saved to: {output_csv_path}")

if __name__ == "__main__":
    main()
