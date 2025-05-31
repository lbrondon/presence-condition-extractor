import pandas as pd
from typing import Optional

class CSVHandler:
    """
    A utility class for managing CSV file input and output operations using pandas.

    This class encapsulates methods to load a CSV file into a DataFrame and to persist
    that DataFrame to disk. It is designed to abstract file handling operations and ensure
    robust error reporting during I/O tasks.
    """

    def __init__(self, csv_path: str):
        """
        Initializes the CSVHandler with the path to the target CSV file.

        Args:
            csv_path (str): Absolute or relative path to the CSV file.
        """
        self.csv_path = csv_path
        self.dataframe: Optional[pd.DataFrame] = None

    def load_csv(self) -> pd.DataFrame:
        """
        Loads the contents of the CSV file into a pandas DataFrame.

        Returns:
            pd.DataFrame: DataFrame populated with the contents of the CSV file.

        Raises:
            IOError: If the file cannot be read or parsed by pandas.
        """
        try:
            self.dataframe = pd.read_csv(self.csv_path)
            print(f"CSV loaded successfully with {len(self.dataframe)} entries.")
            return self.dataframe
        except Exception as e:
            print(f"Error loading CSV: {e}")
            raise IOError(f"Failed to load CSV file: {e}")

    def save_csv(self, output_path: str):
        """
        Saves the current DataFrame to the specified output file path.

        Args:
            output_path (str): Destination path where the CSV file will be written.

        Raises:
            ValueError: If no DataFrame is loaded before calling save.
            IOError: If the file cannot be written to the specified path.
        """
        if self.dataframe is not None:
            try:
                self.dataframe.to_csv(output_path, index=False)
                print(f"CSV saved successfully to: {output_path}")
            except Exception as e:
                print(f"Error saving CSV: {e}")
                raise IOError(f"Failed to save CSV file: {e}")
        else:
            raise ValueError("No data to save. Load a CSV first.")
