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
