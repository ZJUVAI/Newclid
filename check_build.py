import os
from pathlib import Path
import subprocess
from sys import stderr


def run_geosolver(filepath: Path):
    count = 0

    # Check if the file exists
    if not os.path.exists(filepath):
        print(f"File {filepath} not found.")
        return

    # Open the file and read each line
    with open(filepath, "r") as file:
        for line in file:
            count += 1

            # Process only odd-numbered lines
            if count % 2 == 1:
                problemname = line.strip()
                command = [
                    "geosolver",
                    "--problem",
                    f"{filepath}:{problemname}",
                    "--agent",
                    "flemmard",
                ]

                # Run the command and check for errors
                try:
                    subprocess.run(command, check=True, capture_output=True, text=True)
                except subprocess.CalledProcessError:
                    print(
                        f"Warning: geosolver crashed on problem '{problemname}'",
                        file=stderr,
                    )


if __name__ == "__main__":
    filepath = "problems_datasets/examples.txt"
    run_geosolver(Path(filepath))
