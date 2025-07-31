from CSVHandler import CSVHandler
from SourceCodeAnalyzer import SourceCodeAnalyzer
from PresenceConditionExtractor import PresenceConditionExtractor

import os
import logging
import pandas as pd

# Logging configuration for detailed runtime diagnostics
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def main():
    """
    Main execution function that coordinates the CSV loading, source analysis,
    presence condition extraction, and result saving.
    """
    input_csv_path = 'projects.csv'
    base_directory = '/home/lucas/Documents/presence_condition_extractor/projects'
    output_csv_path = '/home/lucas/Documents/presence_condition_extractor/output/projects_with_pc.csv'

    logging.info(f"Starting CSV processing: {input_csv_path}")
    
    # Load input metadata
    csv_handler = CSVHandler(input_csv_path)
    dataframe = csv_handler.load_csv()

    # Remove duplicated caller-callee entries to avoid redundant PC extraction
    dataframe = dataframe.drop_duplicates(subset=['Project', 'File', 'Caller', 'Callee'])
    updated_rows = []

    # Iterate over each row to process corresponding source files
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
            pcs = extractor.extract_pc_from_caller_context(caller, callee)

            for pc in pcs:
                new_row = row.copy()
                new_row['PC'] = pc
                updated_rows.append(new_row)

            for pc in pcs:
                logging.info(f"{caller} → {callee} → PC: {pc}")

        except FileNotFoundError:
            logging.error(f"File not found: {source_code_path}")
            row['PC'] = 'FILE_NOT_FOUND'
            updated_rows.append(row)
        except Exception as e:
            logging.exception(f"Error processing file {source_code_path}: {e}")
            row['PC'] = f'ERROR: {str(e)}'
            updated_rows.append(row)
    
    # Save the updated results
    result_df = pd.DataFrame(updated_rows)
    csv_handler.dataframe = result_df
    csv_handler.save_csv(output_csv_path)
    logging.info(f"Processing completed. Output saved to: {output_csv_path}")

if __name__ == "__main__":
    main()
