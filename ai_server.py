#!/usr/bin/env python3
"""
AI解读服务 - 为机构调研PDF提供AI分析
启动: python ai_server.py
"""

import json
import http.server
import socketserver
import urllib.request
import urllib.parse
import io
import os
import sys
from pathlib import Path

# 尝试导入PDF处理库
try:
    import PyPDF2
    HAS_PDF2 = True
except ImportError:
    HAS_PDF2 = False

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

PORT = 8888


def extract_pdf_text(url, max_pages=5):
    """从PDF URL提取文本内容"""
    try:
        # 下载PDF
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        req = urllib.request.Request(url, headers=headers)
        
        with urllib.request.urlopen(req, timeout=30) as response:
            pdf_bytes = response.read()
        
        text = ""
        
        # 使用pdfplumber（效果更好）
        if HAS_PDFPLUMBER:
            try:
                with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                    for i, page in enumerate(pdf.pages[:max_pages]):
                        page_text = page.extract_text()
                        if page_text:
                            text += page_text + "\n"
                    return text[:8000]  # 限制文本长度
            except Exception as e:
                print(f"pdfplumber error: {e}")
        
        # 备用：使用PyPDF2
        if HAS_PDF2:
            try:
                with io.BytesIO(pdf_bytes) as pdf_file:
                    reader = PyPDF2.PdfReader(pdf_file)
                    for i, page in enumerate(reader.pages[:max_pages]):
                        text += page.extract_text() or ""
                        text += "\n"
                return text[:8000]
            except Exception as e:
                print(f"PyPDF2 error: {e}")
        
        # 如果都没有，返回错误
        if not HAS_PDF2 and not HAS_PDFPLUMBER:
            return "[ERROR] 请安装PDF处理库: pip install pdfplumber PyPDF2"
        
        return text[:8000] if text else "[ERROR] 无法提取PDF文本"
        
    except Exception as e:
        return f"[ERROR] PDF下载或处理失败: {str(e)}"


def analyze_with_doubao(text, company_name=""):
    """使用豆包AI分析调研内容"""
    try:
        import openai
        
        api_key = "7c45a349-5a95-4885-a7b6-df6ed599ed5e"
        base_url = "https://ark.cn-beijing.volces.com/api/v3"
        model_id = "ep-20260103112951-vxd7j"
        
        # 截断文本以适应token限制
        truncated_text = text[:6000] if len(text) > 6000 else text
        
        prompt = f"""请对以下机构投资者调研记录进行专业分析总结，要求：
1. 提炼核心投资亮点和业务进展
2. 总结机构关注的主要问题
3. 分析公司的竞争优势和风险点
4. 控制在200字以内
5. 使用专业金融语言

调研记录内容：
{truncated_text}

请直接输出分析总结："""
        
        messages = [
            {"role": "system", "content": "你是专业的金融分析师，擅长分析机构投资者调研记录，提炼关键投资信息。"},
            {"role": "user", "content": prompt},
        ]
        
        client = openai.OpenAI(api_key=api_key, base_url=base_url)
        completion = client.chat.completions.create(
            model=model_id,
            messages=messages,
            temperature=0,
            top_p=0.8,
            max_tokens=300,
        )
        
        if hasattr(completion, "choices") and completion.choices:
            result = completion.choices[0].message.content.strip()
            return result
        return "AI分析未返回有效内容"
        
    except Exception as e:
        return f"AI分析失败: {str(e)}"


class AIHandler(http.server.BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        """处理CORS预检请求"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def do_POST(self):
        """处理POST请求"""
        if self.path == '/analyze':
            try:
                # 读取请求体
                content_length = int(self.headers.get('Content-Length', 0))
                post_data = self.rfile.read(content_length)
                data = json.loads(post_data.decode('utf-8'))
                
                pdf_url = data.get('url', '')
                if not pdf_url:
                    self._send_error(400, "Missing URL")
                    return
                
                print(f"[*] 正在分析: {pdf_url}")
                
                # 提取PDF文本
                pdf_text = extract_pdf_text(pdf_url)
                
                if pdf_text.startswith('[ERROR]'):
                    self._send_json({"summary": pdf_text, "error": True})
                    return
                
                # AI分析
                summary = analyze_with_doubao(pdf_text)
                
                self._send_json({"summary": summary, "error": False})
                print(f"[+] 分析完成")
                
            except Exception as e:
                self._send_error(500, str(e))
        else:
            self._send_error(404, "Not Found")
    
    def _send_json(self, data):
        """发送JSON响应"""
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))
    
    def _send_error(self, code, message):
        """发送错误响应"""
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps({"error": message}).encode('utf-8'))
    
    def log_message(self, format, *args):
        """自定义日志"""
        print(f"[{self.date_time_string()}] {format % args}")


def main():
    # 检查依赖
    if not HAS_PDF2 and not HAS_PDFPLUMBER:
        print("[!] 警告: 未安装PDF处理库，请先运行: pip install pdfplumber PyPDF2")
        print("[*] 尝试使用纯文本模式（可能无法处理PDF）")
    
    with socketserver.TCPServer(("", PORT), AIHandler) as httpd:
        print(f"[*] AI解读服务已启动: http://localhost:{PORT}")
        print(f"[*] 按 Ctrl+C 停止服务")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n[*] 服务已停止")


if __name__ == "__main__":
    main()
