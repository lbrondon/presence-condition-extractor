"""
Main script for extracting presence conditions from C source files.

This script reads project metadata from a CSV file, analyzes the C source files
to identify the presence conditions under which a callee function is invoked
from a caller function, and writes the results to an output CSV.

Modules:
    - CSVHandler: Handles loading and saving of CSV project metadata.
    - SourceCodeAnalyzer: Extracts raw source code from C files.
    - PresenceConditionExtractor: Analyzes preprocessor directives to infer conditions.

Typical usage example:
    python main.py
"""

from CSVHandler import CSVHandler
from SourceCodeAnalyzer import SourceCodeAnalyzer
from PresenceConditionExtractor import PresenceConditionExtractor

import os
import logging

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
    dataframe['PC'] = 'UNDEFINED'  # Default placeholder for presence conditions
    
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
            pc = extractor.extract_pc_from_caller_context(caller, callee)
            dataframe.at[index, 'PC'] = pc

            logging.info(f"{caller} → {callee} → PC: {pc}")

        except FileNotFoundError:
            logging.error(f"File not found: {source_code_path}")
            dataframe.at[index, 'PC'] = 'FILE_NOT_FOUND'
        except Exception as e:
            logging.exception(f"Error processing file {source_code_path}: {e}")
            dataframe.at[index, 'PC'] = f'ERROR: {str(e)}'
    
    # Save the updated results
    csv_handler.dataframe = dataframe
    csv_handler.save_csv(output_csv_path)
    logging.info(f"Processing completed. Output saved to: {output_csv_path}")

if __name__ == "__main__":
    main()
