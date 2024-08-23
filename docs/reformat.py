import os
from pathlib import Path
import shutil
import subprocess


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


def run_command(cmd: str):
    print(f"run command: {cmd}")
    process = subprocess.Popen(
        args=cmd,
        stdout=1,
        stderr=2,
        shell=True,
    )
    # for line in process.stdout:  # type: ignore
    #     print(line, end="")

    process.wait()

    # for line in process.stderr:  # type: ignore
    #     print(line, end="")
    return process.returncode


if __name__ == "__main__":
    docsfolder = Path("./docs")
    projfolder = Path(".")
    try:
        shutil.rmtree(docsfolder / "source")
    except FileNotFoundError:
        pass
    os.mkdir(docsfolder / "source")
    run_command(
        f"sphinx-apidoc -M -e -f --implicit-namespaces -o {docsfolder / 'source'} {projfolder / 'src' / 'geosolver'}"
    )
    run_command(f"ls {docsfolder / 'source'}")
    os.remove(docsfolder / "source" / "modules.rst")

    for folderpath, folders, files in os.walk(docsfolder / "source"):
        for filename in [file for file in files if file.endswith(".rst")]:
            rename_modules(Path(folderpath) / filename)

    run_command(f"sphinx-build -b html {docsfolder} {docsfolder / '_build' / 'html'}")