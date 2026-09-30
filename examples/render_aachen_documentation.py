"""Render the Aachen method Markdown as browser HTML with MathJax equations."""

from __future__ import annotations

import json
import webbrowser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "aachen_osm_street_cluster_method_results.md"
OUTPUT = ROOT / "docs" / "aachen_osm_street_cluster_method_results.html"


def render() -> Path:
    markdown_source = SOURCE.read_text(encoding="utf-8")
    encoded_source = json.dumps(markdown_source, ensure_ascii=False).replace(
        "</", "<\\/"
    )
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Aachen OSM district method</title>
  <style>
    body {{
      color: #202124;
      font-family: Arial, Helvetica, sans-serif;
      font-size: 17px;
      line-height: 1.6;
      margin: 0 auto;
      max-width: 1180px;
      padding: 32px 48px 80px;
    }}
    h1, h2, h3, h4 {{ line-height: 1.25; margin-top: 1.5em; }}
    table {{ border-collapse: collapse; display: block; overflow-x: auto; }}
    th, td {{ border: 1px solid #c8c8c8; padding: 6px 10px; text-align: left; }}
    th {{ background: #f1f3f4; }}
    code {{ background: #f3f4f5; padding: 0.1em 0.3em; }}
    pre {{ background: #f3f4f5; overflow-x: auto; padding: 14px; }}
    blockquote {{ border-left: 4px solid #9aa0a6; margin-left: 0; padding-left: 16px; }}
    mjx-container[display="true"] {{ overflow-x: auto; overflow-y: hidden; }}
  </style>
  <script>
    window.MathJax = {{
      tex: {{
        inlineMath: [['$', '$']],
        displayMath: [['$$', '$$']],
        processEscapes: true
      }},
      options: {{ skipHtmlTags: ['script', 'noscript', 'style', 'textarea', 'pre', 'code'] }},
      startup: {{ typeset: false }}
    }};
  </script>
</head>
<body>
  <main id="content">Loading documentation…</main>
  <script src="https://cdn.jsdelivr.net/npm/marked@15.0.7/marked.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/mathjax@3.2.2/es5/tex-mml-chtml.js"></script>
  <script>
    const source = {encoded_source};
    const content = document.getElementById('content');
    content.innerHTML = marked.parse(source);
    MathJax.startup.promise.then(() => MathJax.typesetPromise([content]));
  </script>
</body>
</html>
"""
    OUTPUT.write_text(html, encoding="utf-8")
    return OUTPUT


if __name__ == "__main__":
    rendered = render()
    print(f"Updated HTML preview: {rendered}")
    webbrowser.open(rendered.as_uri())
