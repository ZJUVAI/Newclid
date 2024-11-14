import os
from pathlib import Path
from newclid.numerical.draw_figure import draw_figure
from newclid.proof import ProofState


human_agent_index: str = r"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SVG and Iframes Layout</title>
    <style>
        body {
            display: flex;
            margin: 0;
            height: 100vh;
        }
        .svg-container {
            flex: 1;
            display: flex;
            justify-content: center;
            align-items: center;
            border-right: 1px solid #ccc;
        }
        .iframe-container {
            flex: 2;
            display: flex;
            flex-direction: column;
            justify-content: space-around;
            padding: 10px;
        }
        iframe {
            width: 100%;
            height: 45%;
            border: 1px solid #ccc;
        }
    </style>
</head>
<body>
    <div class="svg-container">
        <img src="geometry.svg" alt="Geometry SVG">
    </div>
    <div class="iframe-container">
        <iframe src="symbols_graph.html"></iframe>
        <iframe src="dependency_graph.html"></iframe>
    </div>
</body>
</html>
"""


def pull_to_server(proof: ProofState, *, server_path: Path):
    os.makedirs(server_path, exist_ok=True)
    with open(server_path / "index.html", "w") as f:
        f.write(human_agent_index)
    draw_figure(proof, save_to=server_path / "geometry.svg", rng=proof.rng)
    proof.symbols_graph.save_pyvis(server_path / "symbols_graph.html")
    if proof.check_goals():
        proof.dep_graph.save_pyvis(
            path=server_path / "dependency_graph.html", stars=proof.goals
        )
    else:
        proof.dep_graph.save_pyvis(path=server_path / "dependency_graph.html")
