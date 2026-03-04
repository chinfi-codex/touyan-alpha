import re
from pathlib import Path

file_path = Path("c:/Users/chenh/Documents/Stocks/touyan-alpha/render_static_report.py")
content = file_path.read_text(encoding="utf-8")

# Extract the style block
pattern = re.compile(r'(<style>)(.*?)(</style>)', re.DOTALL)

def replacer(match):
    style_content = match.group(2)
    # Ensure all '{' and '}' are doubled
    # First un-double them in case
    style_content = style_content.replace('{{', '{').replace('}}', '}')
    # Then double them all
    style_content = style_content.replace('{', '{{').replace('}', '}}')
    return match.group(1) + style_content + match.group(3)

new_content = pattern.sub(replacer, content)
file_path.write_text(new_content, encoding="utf-8")
print("Fixed f-string escaping in style block.")
