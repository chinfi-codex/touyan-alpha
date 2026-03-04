import re
from pathlib import Path

file_path = Path("c:/Users/chenh/Documents/Stocks/touyan-alpha/render_static_report.py")
content = file_path.read_text(encoding="utf-8")

# Let's replace the head section and style block.
# We will use regex to find everything between html_doc = f"""<!doctype html> and </head>
# Or between <style> and </style>

new_style = """
    /* ============================================
       Modern Premium Dark Mode UI - "Alpha Terminal"
       ============================================ */
    :root {
      /* Background */
      --bg-primary: #09090b;       /* Pure dark */
      --bg-secondary: #121214;     /* Slightly lighter */
      --bg-tertiary: #18181b;      /* Panels */
      --bg-hover: #27272a;
      
      /* Text */
      --text-primary: #f8fafc;
      --text-secondary: #a1a1aa;
      --text-tertiary: #71717a;
      --text-inverse: #09090b;
      
      /* Borders & Glass */
      --border-light: rgba(255, 255, 255, 0.08);
      --border-medium: rgba(255, 255, 255, 0.12);
      --border-dark: rgba(255, 255, 255, 0.2);
      --glass-bg: rgba(24, 24, 27, 0.7);
      
      /* Financial Colors */
      --color-up: #10b981;           /* Neo Green */
      --color-down: #ef4444;         /* Neo Red */
      --color-warning: #fbbf24;      /* Amber */
      --color-info: #3b82f6;         /* Blue */
      
      /* Accents */
      --accent-primary: #3b82f6;
      --accent-glow: rgba(59, 130, 246, 0.4);
      --accent-gradient: linear-gradient(135deg, #3b82f6, #8b5cf6);
      
      /* Shadows */
      --shadow-glow: 0 0 20px rgba(59, 130, 246, 0.15);
      --shadow-card: 0 8px 30px rgba(0, 0, 0, 0.4);
      
      /* AI */
      --ai-bg: rgba(59, 130, 246, 0.1);
      --ai-border: rgba(59, 130, 246, 0.3);
      --ai-text: #60a5fa;
    }
    
    * { box-sizing: border-box; }
    
    html {
      scroll-behavior: smooth;
      scroll-padding-top: 90px;
    }
    
    body {
      margin: 0;
      font-family: "Inter", "Outfit", -apple-system, sans-serif;
      color: var(--text-primary);
      background: var(--bg-primary);
      /* Subtle radial gradient background */
      background-image: radial-gradient(circle at top right, rgba(59, 130, 246, 0.05), transparent 40%),
                        radial-gradient(circle at bottom left, rgba(139, 92, 246, 0.05), transparent 40%);
      line-height: 1.6;
      -webkit-font-smoothing: antialiased;
      -moz-osx-font-smoothing: grayscale;
    }
    
    .wrap { 
      max-width: 1400px; 
      margin: 0 auto; 
      padding: 32px 24px 60px; 
    }
    
    h1, h2, h3 { 
      margin: 0; 
      font-weight: 700;
      letter-spacing: -0.02em;
    }
    
    h1 {
      font-family: "Outfit", sans-serif;
      font-size: 32px;
      color: var(--text-primary);
      padding-bottom: 16px;
      border-bottom: 2px solid transparent;
      border-image: var(--accent-gradient);
      border-image-slice: 1;
      display: inline-block;
      text-transform: uppercase;
      letter-spacing: 2px;
    }
    
    h1::after {
      content: '';
      display: block;
      width: 50%;
      height: 2px;
      background: var(--accent-gradient);
      margin-top: 14px;
      box-shadow: var(--shadow-glow);
    }
    
    /* ============================================
       Tabs - Pill shapes with hover glows
       ============================================ */
    .tabs { 
      display: flex; 
      gap: 12px; 
      margin-top: 30px; 
      padding: 16px 8px; 
      border-bottom: 1px solid var(--border-light); 
      position: sticky; 
      top: 0; 
      background: rgba(9, 9, 11, 0.85); 
      backdrop-filter: blur(20px); 
      -webkit-backdrop-filter: blur(20px);
      z-index: 100;
      overflow-x: auto;
      scrollbar-width: none;
    }
    .tabs::-webkit-scrollbar { display: none; }
    
    .tab { 
      padding: 10px 24px; 
      border-radius: 30px; 
      background: var(--bg-tertiary); 
      border: 1px solid var(--border-light); 
      color: var(--text-secondary); 
      text-decoration: none; 
      font-size: 14px; 
      font-weight: 600; 
      transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
      white-space: nowrap;
    }
    .tab:hover { 
      background: var(--bg-hover); 
      color: var(--text-primary);
      border-color: var(--text-tertiary);
      transform: translateY(-2px);
      box-shadow: 0 4px 12px rgba(0,0,0,0.2);
    }
    .tab:active {
      transform: translateY(0);
    }
    
    /* ============================================
       Panels - Glassmorphism cards
       ============================================ */
    .sections { 
      margin-top: 32px; 
      display: grid; 
      gap: 32px; 
    }
    
    .panel { 
      background: var(--glass-bg);
      backdrop-filter: blur(16px);
      border-radius: 20px;
      padding: 30px;
      box-shadow: var(--shadow-card);
      border: 1px solid var(--border-light);
      position: relative;
      overflow: hidden;
    }
    
    /* Subtle inner glow for panels */
    .panel::before {
      content: '';
      position: absolute;
      top: 0; left: 0; right: 0;
      height: 1px;
      background: linear-gradient(90deg, transparent, rgba(255,255,255,0.1), transparent);
    }
    
    .panel h2 { 
      margin-bottom: 24px;
      font-size: 22px;
      color: var(--text-primary);
      display: flex;
      align-items: center;
      gap: 12px;
      font-family: "Outfit", sans-serif;
    }
    
    .panel h2 span { 
      color: var(--accent-primary); 
      font-weight: 600; 
      font-size: 14px;
      background: var(--ai-bg);
      padding: 6px 14px;
      border-radius: 20px;
      border: 1px solid var(--ai-border);
    }
    
    .stack { 
      display: grid; 
      gap: 20px; 
    }
    
    .subpanel { 
      background: var(--bg-secondary);
      border-radius: 16px;
      padding: 20px;
      border: 1px solid var(--border-light);
      transition: all 0.3s ease;
    }
    
    .subpanel:hover {
      border-color: var(--border-medium);
      box-shadow: 0 8px 24px rgba(0,0,0,0.3);
      transform: translateY(-2px);
    }
    
    .subpanel h3 { 
      margin-bottom: 16px;
      font-size: 16px;
      color: var(--text-primary);
      display: flex;
      align-items: center;
      gap: 10px;
    }
    
    .subpanel h3 span { 
      color: var(--text-secondary); 
      font-weight: 500; 
      font-size: 13px;
    }
    
    /* ============================================
       Tables - Sleek & Modern
       ============================================ */
    table { 
      width: 100%; 
      border-collapse: separate;
      border-spacing: 0;
      font-size: 14px;
    }
    
    thead {
      position: sticky;
      top: 70px;
      z-index: 50;
      backdrop-filter: blur(10px);
    }
    
    th { 
      color: var(--text-secondary); 
      font-weight: 600; 
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 1px;
      padding: 16px 14px;
      text-align: left;
      border-bottom: 1px solid var(--border-medium);
      background: rgba(18, 18, 20, 0.9);
    }
    
    td { 
      padding: 18px 14px;
      text-align: left;
      vertical-align: top;
      border-bottom: 1px solid var(--border-light);
      transition: background-color 0.2s ease;
      line-height: 1.6;
    }
    
    tbody tr {
      transition: all 0.2s ease;
    }
    
    tbody tr:hover td {
      background-color: rgba(255, 255, 255, 0.03);
    }
    
    td.title { 
      min-width: 260px;
      max-width: 500px;
    }
    
    /* ============================================
       Links & Buttons - Neon Accents
       ============================================ */
    a { 
      color: var(--accent-primary); 
      text-decoration: none;
      font-weight: 500;
      transition: all 0.2s;
    }
    
    a:hover { 
      color: #7dd3fc;
      text-shadow: var(--shadow-glow);
    }
    
    a[target="_blank"]::after {
      content: "↗";
      font-family: inherit;
      font-size: 0.85em;
      margin-left: 4px;
      opacity: 0.7;
    }
    
    .empty { 
      color: var(--text-tertiary); 
      font-size: 14px;
      text-align: center;
      padding: 60px 20px;
      font-weight: 500;
      background: var(--bg-secondary);
      border-radius: 16px;
      border: 1px dashed var(--border-medium);
    }
    
    /* ============================================
       AI Summary Card - Cyber/Neon Style
       ============================================ */
    .ai-summary-card {
      background: linear-gradient(135deg, rgba(59, 130, 246, 0.08) 0%, rgba(139, 92, 246, 0.05) 100%);
      border: 1px solid rgba(59, 130, 246, 0.2);
      border-radius: 16px;
      padding: 24px;
      margin: 20px 0;
      position: relative;
    }
    
    .ai-summary-card::after {
      content: '';
      position: absolute;
      top: 0; left: 0; right: 0; bottom: 0;
      border-radius: 16px;
      box-shadow: inset 0 0 20px rgba(59, 130, 246, 0.05);
      pointer-events: none;
    }
    
    .ai-summary-header {
      display: flex;
      align-items: center;
      gap: 12px;
      margin-bottom: 16px;
    }
    
    .ai-icon {
      font-size: 24px;
      filter: drop-shadow(0 0 8px rgba(59, 130, 246, 0.4));
    }
    
    .ai-title {
      font-weight: 700;
      color: var(--text-primary);
      font-size: 16px;
      font-family: "Outfit", sans-serif;
      letter-spacing: 0.5px;
      text-shadow: 0 0 10px rgba(59, 130, 246, 0.3);
    }
    
    .ai-summary-content {
      color: var(--text-secondary);
      font-size: 14.5px;
      line-height: 1.8;
    }
    
    /* ============================================
       Forecast Section - Dynamic Cards
       ============================================ */
    .forecast-company {
      background: var(--bg-tertiary);
      border: 1px solid var(--border-light);
      border-radius: 16px;
      padding: 22px;
    }
    
    .forecast-company h3 {
      font-size: 18px;
      color: var(--text-primary);
    }
    
    .forecast-company h3 span {
      background: rgba(255, 255, 255, 0.05);
      padding: 4px 10px;
      border-radius: 6px;
      font-family: monospace;
      font-size: 13px;
    }
    
    .forecast-metrics {
      width: 100%;
      margin: 16px 0;
      background: rgba(0,0,0,0.2);
      border-radius: 12px;
      overflow: hidden;
    }
    
    .forecast-metrics th {
      background: rgba(255,255,255,0.02);
      border-bottom: 1px solid var(--border-light);
      color: var(--text-secondary);
    }
    
    .forecast-metrics td {
      border-bottom: 1px solid var(--border-light);
    }
    
    .forecast-metrics tr:last-child td { border-bottom: none; }
    
    .forecast-reason {
      color: var(--text-secondary);
      font-size: 13.5px;
      padding: 16px;
      background: rgba(255, 255, 255, 0.02);
      border-radius: 12px;
      border-left: 3px solid var(--accent-primary);
    }
    
    /* ============================================
       Buttons - Glowing interactions
       ============================================ */
    .ai-analyze-btn, .expand-btn {
      padding: 10px 20px;
      border-radius: 20px;
      background: var(--bg-secondary);
      color: var(--text-primary);
      border: 1px solid var(--accent-primary);
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
      display: inline-flex;
      align-items: center;
      justify-content: center;
    }
    
    .ai-analyze-btn:hover, .expand-btn:hover {
      background: var(--accent-primary);
      color: #fff;
      box-shadow: 0 0 15px var(--accent-glow);
      transform: translateY(-1px);
    }
    
    .expand-controls {
      margin: 20px 0;
      text-align: right;
    }
    
    .expand-btn {
      background: var(--accent-gradient);
      border: none;
      color: #fff;
    }
    
    .expand-btn:hover {
      box-shadow: 0 4px 20px rgba(139, 92, 246, 0.4);
    }
    
    /* ============================================
       Regulatory Warning & Capital
       ============================================ */
    .regulatory-warning {
      background: linear-gradient(135deg, rgba(251, 191, 36, 0.05) 0%, rgba(251, 191, 36, 0.01) 100%);
      border: 1px solid rgba(251, 191, 36, 0.2);
    }
    
    .regulatory-warning h3 {
      color: var(--color-warning);
    }
    
    .regulatory-row td {
      background: rgba(251, 191, 36, 0.03);
    }
    
    .regulatory-row td:first-child {
      border-left: 3px solid var(--color-warning);
    }
    
    .capital-companies { display: grid; gap: 16px; }
    
    .capital-company-card {
      background: var(--bg-tertiary);
      border: 1px solid var(--border-light);
      border-radius: 16px;
      padding: 20px;
      transition: all 0.3s;
    }
    
    .capital-company-card:hover {
      border-color: rgba(255, 255, 255, 0.2);
      transform: translateY(-2px);
      box-shadow: 0 10px 30px rgba(0,0,0,0.2);
    }
    
    .capital-company-header {
      display: flex; align-items: center; gap: 12px; margin-bottom: 12px;
    }
    
    .capital-company-name { font-weight: 700; font-size: 16px; color: var(--text-primary); }
    
    .capital-company-symbol {
      background: rgba(255,255,255,0.05);
      padding: 4px 8px; border-radius: 8px; font-family: monospace; font-size: 13px; color: var(--text-secondary);
    }
    
    .capital-count { color: var(--accent-primary); font-weight: 700; font-size: 13px; }
    
    .capital-titles { color: var(--text-secondary); font-size: 14px; line-height: 1.8; }
    
    /* ============================================
       Mobile Optimizations
       ============================================ */
    @media (max-width: 1024px) {
      .wrap { padding: 24px 16px; }
      td.title { min-width: 200px; max-width: 350px; }
    }
    
    @media (max-width: 768px) {
      html { font-size: 16px; }
      h1 { font-size: 26px; }
      .tabs { padding: 12px 0; gap: 8px; }
      .tab { padding: 8px 18px; font-size: 13px; }
      
      .panel { padding: 20px; border-radius: 16px; }
      .panel h2 { font-size: 18px; }
      
      table { display: block; overflow-x: auto; white-space: nowrap; }
      th, td { padding: 14px 12px; }
      td.title { white-space: normal; min-width: 220px; }
      
      .ai-analyze-btn, .expand-btn { min-height: 44px; }
    }
"""

# Replace the fonts and style
new_head = f'''  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Outfit:wght@500;600;700&display=swap" rel="stylesheet">
  <style>{new_style}</style>'''

old_pattern = re.compile(r'  <link rel="preconnect" href="https://fonts.googleapis.com">.*?  </style>', re.DOTALL)
new_content = old_pattern.sub(new_head, content)

if new_content == content:
    print("No changes made. Pattern matching might have failed.")
else:
    file_path.write_text(new_content, encoding="utf-8")
    print("CSS Updated Successfully!")
