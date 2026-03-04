import re
from pathlib import Path

file_path = Path("c:/Users/chenh/Documents/Stocks/touyan-alpha/render_static_report.py")
content = file_path.read_text(encoding="utf-8")

new_style = """
    /* ============================================
       Modern Bright UI - "Moomoo Style"
       ============================================ */
    :root {
      /* Background */
      --bg-primary: #ffffff;
      --bg-secondary: #f4f5f9;
      --bg-tertiary: #ffffff;
      --bg-hover: #f0f2f5;
      
      /* Text */
      --text-primary: #12161b;
      --text-secondary: #586171;
      --text-tertiary: #8b92a5;
      --text-inverse: #ffffff;
      
      /* Borders & Shadows */
      --border-light: #eaecf1;
      --border-medium: #dfe2ea;
      --border-dark: #c4c8d4;
      --shadow-card: 0 4px 16px rgba(0, 0, 0, 0.04);
      --shadow-hover: 0 6px 24px rgba(0, 0, 0, 0.08);
      
      /* Financial Colors (A-shares: Red Up, Green Down) */
      --color-up: #f24957;           /* Moomoo Red */
      --color-up-bg: rgba(242, 73, 87, 0.08);
      --color-down: #13b77f;         /* Moomoo Green */
      --color-down-bg: rgba(19, 183, 127, 0.08);
      --color-warning: #ff8f00;      /* Orange */
      --color-info: #0066ff;         /* Bright Blue */
      
      /* Accents */
      --accent-primary: #ff6600;     /* Moomoo Brand Orange */
      --accent-hover: #ff8533;
      --accent-gradient: linear-gradient(135deg, #ff6600, #ff8f00);
      
      /* AI */
      --ai-bg: #f5f9ff;
      --ai-border: #d6e8ff;
      --ai-text: #0055ff;
    }
    
    * { box-sizing: border-box; }
    
    html {
      scroll-behavior: smooth;
      scroll-padding-top: 80px;
    }
    
    body {
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      color: var(--text-primary);
      background: var(--bg-secondary);
      line-height: 1.6;
      -webkit-font-smoothing: antialiased;
      -moz-osx-font-smoothing: grayscale;
    }
    
    .wrap { 
      max-width: 1400px; 
      margin: 0 auto; 
      padding: 24px 24px 60px; 
    }
    
    h1, h2, h3 { 
      margin: 0; 
      font-weight: 700;
    }
    
    h1 {
      font-size: 28px;
      color: var(--text-primary);
      padding-bottom: 16px;
      display: flex;
      align-items: center;
      gap: 12px;
    }
    
    h1::before {
      content: '';
      display: inline-block;
      width: 6px;
      height: 28px;
      background: var(--accent-gradient);
      border-radius: 4px;
    }
    
    /* ============================================
       Tabs - Modern Pill shapes
       ============================================ */
    .tabs { 
      display: flex; 
      gap: 12px; 
      margin-top: 20px; 
      padding: 12px 0; 
      position: sticky; 
      top: 0; 
      background: rgba(244, 245, 249, 0.9); 
      backdrop-filter: blur(12px); 
      -webkit-backdrop-filter: blur(12px);
      z-index: 100;
      overflow-x: auto;
      scrollbar-width: none;
    }
    .tabs::-webkit-scrollbar { display: none; }
    
    .tab { 
      padding: 10px 24px; 
      border-radius: 20px; 
      background: var(--bg-primary); 
      border: 1px solid var(--border-light); 
      color: var(--text-secondary); 
      text-decoration: none; 
      font-size: 15px; 
      font-weight: 600; 
      transition: all 0.2s ease;
      white-space: nowrap;
      box-shadow: 0 2px 4px rgba(0,0,0,0.02);
    }
    .tab:hover { 
      color: var(--accent-primary);
      border-color: var(--accent-primary);
      background: #fff8f5;
    }
    
    /* ============================================
       Panels - Clean White Cards
       ============================================ */
    .sections { 
      margin-top: 24px; 
      display: grid; 
      gap: 24px; 
    }
    
    .panel { 
      background: var(--bg-primary);
      border-radius: 16px;
      padding: 28px;
      box-shadow: var(--shadow-card);
      border: 1px solid var(--border-light);
    }
    
    .panel h2 { 
      margin-bottom: 20px;
      font-size: 20px;
      color: var(--text-primary);
      display: flex;
      align-items: center;
      gap: 10px;
    }
    
    .panel h2 span { 
      color: var(--accent-primary); 
      font-weight: 600; 
      font-size: 14px;
      background: #fff0e5;
      padding: 4px 12px;
      border-radius: 20px;
    }
    
    .stack { 
      display: grid; 
      gap: 16px; 
    }
    
    .subpanel { 
      background: #fafafc;
      border-radius: 12px;
      padding: 20px;
      border: 1px solid var(--border-light);
      transition: all 0.2s ease;
    }
    
    .subpanel:hover {
      background: #ffffff;
      box-shadow: var(--shadow-hover);
      border-color: var(--border-medium);
    }
    
    .subpanel h3 { 
      margin-bottom: 16px;
      font-size: 16px;
      color: var(--text-primary);
      display: flex;
      align-items: center;
      gap: 8px;
    }
    
    .subpanel h3 span { 
      color: var(--text-tertiary); 
      font-weight: 500; 
      font-size: 13px;
    }
    
    /* ============================================
       Tables - Crisp and Readable
       ============================================ */
    table { 
      width: 100%; 
      border-collapse: separate;
      border-spacing: 0;
      font-size: 14px;
    }
    
    thead {
      position: sticky;
      top: 60px;
      z-index: 50;
      background: var(--bg-primary);
    }
    
    th { 
      color: var(--text-secondary); 
      font-weight: 500; 
      font-size: 13px;
      padding: 14px 12px;
      text-align: left;
      border-bottom: 1px solid var(--border-medium);
      background: #fafafc;
    }
    
    th:first-child { border-top-left-radius: 8px; border-bottom-left-radius: 8px; }
    th:last-child { border-top-right-radius: 8px; border-bottom-right-radius: 8px; }
    
    td { 
      padding: 16px 12px;
      text-align: left;
      vertical-align: top;
      border-bottom: 1px solid var(--border-light);
      transition: background-color 0.2s ease;
      line-height: 1.6;
    }
    
    tbody tr:hover td {
      background-color: var(--bg-hover);
    }
    
    td.title { 
      min-width: 260px;
      max-width: 500px;
      color: var(--text-primary);
    }
    
    /* ============================================
       Links & Buttons - Brand Accent
       ============================================ */
    a { 
      color: var(--color-info); 
      text-decoration: none;
      font-weight: 500;
      transition: all 0.2s;
    }
    
    a:hover { 
      color: #0044cc;
      text-decoration: underline;
    }
    
    .empty { 
      color: var(--text-tertiary); 
      font-size: 14px;
      text-align: center;
      padding: 40px 20px;
      background: #fafafc;
      border-radius: 12px;
      border: 1px dashed var(--border-medium);
    }
    
    /* ============================================
       AI Summary Card - Crisp Tech Vibe
       ============================================ */
    .ai-summary-card {
      background: var(--ai-bg);
      border: 1px solid var(--ai-border);
      border-radius: 12px;
      padding: 20px;
      margin: 16px 0;
    }
    
    .ai-summary-header {
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 12px;
    }
    
    .ai-icon {
      font-size: 20px;
    }
    
    .ai-title {
      font-weight: 700;
      color: var(--ai-text);
      font-size: 15px;
    }
    
    .ai-summary-content {
      color: var(--text-primary);
      font-size: 14px;
      line-height: 1.7;
    }
    
    /* ============================================
       Forecast Section - Dynamic Cards
       ============================================ */
    .forecast-company {
      background: var(--bg-primary);
      border: 1px solid var(--border-light);
      border-radius: 12px;
      padding: 20px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.02);
    }
    
    .forecast-company h3 {
      font-size: 17px;
      color: var(--text-primary);
    }
    
    .forecast-company h3 span {
      background: #f0f2f5;
      padding: 3px 8px;
      border-radius: 6px;
      font-size: 12px;
      color: var(--text-secondary);
    }
    
    .forecast-metrics {
      width: 100%;
      margin: 16px 0;
      border: 1px solid var(--border-light);
      border-radius: 8px;
      overflow: hidden;
    }
    
    .forecast-metrics th {
      background: #fafafc;
      border-bottom: 1px solid var(--border-light);
      border-radius: 0;
    }
    
    .forecast-metrics td {
      border-bottom: 1px solid var(--border-light);
    }
    
    .forecast-metrics tr:last-child td { border-bottom: none; }
    
    .forecast-reason {
      color: var(--text-secondary);
      font-size: 13.5px;
      padding: 14px 16px;
      background: #fafafc;
      border-radius: 8px;
      border-left: 3px solid var(--accent-primary);
    }
    
    /* ============================================
       Buttons
       ============================================ */
    .ai-analyze-btn, .expand-btn {
      padding: 8px 16px;
      border-radius: 6px;
      background: var(--ai-bg);
      color: var(--ai-text);
      border: 1px solid var(--ai-border);
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.2s;
    }
    
    .ai-analyze-btn:hover, .expand-btn:hover {
      background: #e0edff;
    }
    
    .expand-controls {
      margin: 16px 0;
      text-align: right;
    }
    
    .expand-btn {
      background: var(--accent-primary);
      border: none;
      color: #fff;
    }
    
    .expand-btn:hover {
      background: var(--accent-hover);
    }
    
    /* ============================================
       Regulatory Warning & Capital
       ============================================ */
    .regulatory-warning {
      background: #fffcf5;
      border: 1px solid #ffd599;
    }
    
    .regulatory-warning h3 {
      color: var(--color-warning);
    }
    
    .regulatory-row td {
      background: #fffcf5;
    }
    
    .regulatory-row td:first-child {
      border-left: 3px solid var(--color-warning);
    }
    
    .capital-companies { display: grid; gap: 16px; }
    
    .capital-company-card {
      background: #ffffff;
      border: 1px solid var(--border-light);
      border-radius: 12px;
      padding: 16px;
      transition: all 0.2s;
    }
    
    .capital-company-card:hover {
      border-color: var(--border-medium);
      box-shadow: var(--shadow-hover);
    }
    
    .capital-company-header {
      display: flex; align-items: center; gap: 10px; margin-bottom: 10px;
    }
    
    .capital-company-name { font-weight: 600; font-size: 15px; color: var(--text-primary); }
    
    .capital-company-symbol {
      background: #f0f2f5;
      padding: 2px 8px; border-radius: 6px; font-size: 13px; color: var(--text-secondary);
    }
    
    .capital-count { color: var(--accent-primary); font-weight: 600; font-size: 13px; }
    
    .capital-titles { color: var(--text-secondary); font-size: 14px; line-height: 1.7; }
    
    /* ============================================
       Mobile Optimizations
       ============================================ */
    @media (max-width: 1024px) {
      .wrap { padding: 24px 16px; }
      td.title { min-width: 200px; max-width: 350px; }
    }
    
    @media (max-width: 768px) {
      h1 { font-size: 24px; }
      .tabs { padding: 12px 0; gap: 8px; }
      .tab { padding: 8px 16px; font-size: 13px; }
      
      .panel { padding: 20px; border-radius: 12px; }
      
      table { display: block; overflow-x: auto; white-space: nowrap; }
      th, td { padding: 12px; }
      td.title { white-space: normal; min-width: 220px; }
    }
"""

new_head = f'''  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <style>{new_style}'''

old_pattern = re.compile(r'  <link rel="preconnect" href="https://fonts.googleapis.com">.*?  <style>.*?(</style>)', re.DOTALL)

def replacer(match):
    style_content = new_style
    # Doubling brackets for f-string formatting
    style_content = style_content.replace('{', '{{').replace('}', '}}')
    head = f'''  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <style>{style_content}'''
    return head + match.group(1)

new_content = old_pattern.sub(replacer, content)

if new_content == content:
    print("No changes made. Pattern matching might have failed.")
else:
    file_path.write_text(new_content, encoding="utf-8")
    print("Light Theme CSS Updated Successfully!")
