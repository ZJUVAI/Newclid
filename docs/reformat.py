import os
from pathlib import Path


def rename_modules(filepath: Path):
    with open(filepath, "r") as file:
        lines = file.readlines()

    module_name = lines[0].split(".")[-1].split(" ")[0]
    lines[0] = module_name.replace("\\_", " ").capitalize() + "\n"
    lines[1] = "=" * (len(lines[0]) - 1) + "\n"

    for header in ["Subpackages\n", "Submodules\n"]:
        if header in lines:
            submodule_line = lines.index(header)
            lines.pop(submodule_line)
            lines.pop(submodule_line)

    with open(filepath, "w") as file:
        file.writelines(lines)


if __name__ == "__main__":
    path = Path(__file__).parent / "source"

    os.remove(path / "modules.rst")

    for folderpath, folders, files in os.walk(path):
        for filename in [file for file in files if file.endswith(".rst")]:
            rename_modules(Path(folderpath) / filename)
