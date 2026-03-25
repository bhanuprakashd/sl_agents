"""
Generate a standalone HTML org chart from the ADK agent tree.

Usage:
    python -m tools.generate_orgchart                    # outputs orgchart.html
    python -m tools.generate_orgchart --out my_chart.html
    python -m tools.generate_orgchart --open             # opens in browser automatically
"""

import argparse
import os
import webbrowser
from tools.register_agents import AGENT_TREE, AgentNode

# ── Role colours ──────────────────────────────────────────────────────────────

ROLE_COLORS = {
    "ceo":        ("#1a1a2e", "#e94560"),
    "cto":        ("#0f3460", "#16213e"),
    "cmo":        ("#533483", "#e8d5b7"),
    "cfo":        ("#2b4865", "#82c0cc"),
    "pm":         ("#1b4332", "#52b788"),
    "engineer":   ("#1c3144", "#4dabf7"),
    "designer":   ("#3d1c56", "#da77f2"),
    "devops":     ("#7f4f24", "#ffd166"),
    "qa":         ("#495057", "#a9c5a0"),
    "researcher": ("#212529", "#74c0fc"),
    "general":    ("#343a40", "#ced4da"),
}

# ── HTML builder ──────────────────────────────────────────────────────────────

def _node_to_html(node: AgentNode) -> str:
    bg, accent = ROLE_COLORS.get(node.role, ("#343a40", "#ced4da"))
    children_html = ""
    if node.children:
        children_inner = "\n".join(_node_to_html(c) for c in node.children)
        children_html = f'<div class="children">{children_inner}</div>'

    return f"""
<div class="node-wrap">
  <div class="node" style="background:{bg}; border-top: 3px solid {accent};">
    <div class="node-role" style="color:{accent};">{node.role.upper()}</div>
    <div class="node-title">{node.title}</div>
    <div class="node-name">{node.name}</div>
    <div class="node-caps">{node.capabilities}</div>
  </div>
  {children_html}
</div>
"""


def generate_html(tree: AgentNode) -> str:
    tree_html = _node_to_html(tree)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>SL Agents — Org Chart</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}

    body {{
      background: #0d0d0d;
      color: #f0f0f0;
      font-family: 'Segoe UI', system-ui, sans-serif;
      padding: 40px 20px;
      overflow-x: auto;
    }}

    h1 {{
      text-align: center;
      font-size: 1.6rem;
      color: #e94560;
      margin-bottom: 8px;
      letter-spacing: 2px;
      text-transform: uppercase;
    }}

    .subtitle {{
      text-align: center;
      color: #666;
      font-size: 0.85rem;
      margin-bottom: 40px;
    }}

    /* Tree layout */
    .node-wrap {{
      display: flex;
      flex-direction: column;
      align-items: center;
    }}

    .children {{
      display: flex;
      flex-direction: row;
      align-items: flex-start;
      justify-content: center;
      gap: 16px;
      position: relative;
      padding-top: 28px;
    }}

    /* Vertical connector from parent down */
    .node-wrap > .children::before {{
      content: '';
      position: absolute;
      top: 0;
      left: 50%;
      transform: translateX(-50%);
      width: 2px;
      height: 28px;
      background: #444;
    }}

    /* Horizontal connector across children */
    .node-wrap > .children::after {{
      content: '';
      position: absolute;
      top: 0;
      left: calc(50px);
      right: calc(50px);
      height: 2px;
      background: #444;
    }}

    /* Vertical connector from horizontal bar down to each child */
    .children > .node-wrap {{
      position: relative;
    }}

    .children > .node-wrap::before {{
      content: '';
      position: absolute;
      top: -28px;
      left: 50%;
      transform: translateX(-50%);
      width: 2px;
      height: 28px;
      background: #444;
    }}

    /* Agent card */
    .node {{
      width: 200px;
      border-radius: 8px;
      padding: 14px 12px;
      cursor: default;
      transition: transform 0.15s, box-shadow 0.15s;
      box-shadow: 0 4px 12px rgba(0,0,0,0.4);
    }}

    .node:hover {{
      transform: translateY(-3px);
      box-shadow: 0 8px 24px rgba(0,0,0,0.6);
    }}

    .node-role {{
      font-size: 0.65rem;
      font-weight: 700;
      letter-spacing: 1.5px;
      margin-bottom: 6px;
    }}

    .node-title {{
      font-size: 0.9rem;
      font-weight: 600;
      color: #f0f0f0;
      margin-bottom: 3px;
    }}

    .node-name {{
      font-size: 0.7rem;
      color: #888;
      font-family: monospace;
      margin-bottom: 8px;
    }}

    .node-caps {{
      font-size: 0.72rem;
      color: #bbb;
      line-height: 1.4;
    }}

    /* Legend */
    .legend {{
      display: flex;
      flex-wrap: wrap;
      justify-content: center;
      gap: 10px;
      margin-top: 50px;
    }}

    .legend-item {{
      display: flex;
      align-items: center;
      gap: 6px;
      font-size: 0.75rem;
      color: #aaa;
    }}

    .legend-dot {{
      width: 10px;
      height: 10px;
      border-radius: 2px;
    }}
  </style>
</head>
<body>
  <h1>SL Agents — Org Chart</h1>
  <p class="subtitle">Auto-generated from ADK agent hierarchy</p>

  <div style="display:flex; justify-content:center; overflow-x:auto; padding-bottom:20px;">
    {tree_html}
  </div>

  <div class="legend">
    {''.join(
        f'<div class="legend-item"><div class="legend-dot" style="background:{accent};"></div>{role}</div>'
        for role, (bg, accent) in ROLE_COLORS.items()
    )}
  </div>
</body>
</html>
"""


# ── Entry point ───────────────────────────────────────────────────────────────

def run(out: str = "orgchart.html", open_browser: bool = False) -> None:
    html = generate_html(AGENT_TREE)
    out_path = os.path.abspath(out)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Org chart written → {out_path}")
    if open_browser:
        webbrowser.open(f"file://{out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate standalone HTML org chart from ADK agent tree")
    parser.add_argument("--out", default="orgchart.html", help="Output file path (default: orgchart.html)")
    parser.add_argument("--open", action="store_true", help="Open in browser after generating")
    args = parser.parse_args()
    run(out=args.out, open_browser=args.open)
