import pandas as pd
from typing import Optional

class CSVHandler:
    """
    Handles loading and saving CSV files for project data.
    """

    def __init__(self, csv_path: str):
        """
        Initialize the CSVHandler with the path to the CSV file.
        """
        self.csv_path = csv_path
        self.dataframe: Optional[pd.DataFrame] = None

    def load_csv(self) -> pd.DataFrame:
        """
        Load the CSV file and return it as a DataFrame.
        """
        try:
            self.dataframe = pd.read_csv(self.csv_path)
            print(f"CSV loaded successfully with {len(self.dataframe)} entries.")
            return self.dataframe
        except Exception as e:
            print(f"Error loading CSV: {e}")
            raise

    def save_csv(self, output_path: str):
        """
        Save the current DataFrame to the specified output path.
        """
        if self.dataframe is not None:
            try:
                self.dataframe.to_csv(output_path, index=False)
                print(f"CSV saved successfully to: {output_path}")
            except Exception as e:
                print(f"Error saving CSV: {e}")
                raise
        else:
            raise ValueError("No data to save. Load a CSV first.")
