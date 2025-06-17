"""
Web Interface for Daily Notes Processor
Run this script to start a web server with buttons for common functions
"""

import os
import sys
import io
import time
import json
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import webbrowser
import urllib.parse
from contextlib import redirect_stdout

# Add src directory to path for imports
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir / 'src'))

# Global processor instance and output buffer
processor = None
output_buffer = []
output_lock = threading.Lock()
current_process = None

def capture_output(func):
    """Decorator to capture console output"""
    def wrapper(*args, **kwargs):
        global output_buffer, current_process
        
        # Clear previous output
        with output_lock:
            output_buffer = []
            current_process = func.__name__
        
        # Capture stdout and run function
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            result = func(*args, **kwargs)
        
        # Store output
        with output_lock:
            output_buffer.append(buffer.getvalue())
            current_process = None
        
        return result
    return wrapper

class WebProcessor:
    """Web-friendly versions of processor functions"""
    def __init__(self, android_processor):
        self.processor = android_processor
    
    @capture_output
    def process_all_audio(self):
        """Process all audio files"""
        audio_files = self.processor.find_audio_files()
        if not audio_files:
            print("📭 No audio files found.")
            return []
        
        results = []
        for audio_path in audio_files:
            success = self.processor.process_audio_file(audio_path)
            results.append({
                'file': audio_path.name,
                'success': success
            })
        
        return results
    
    @capture_output
    def process_specific_audio(self, filename):
        """Process a specific audio file"""
        audio_path = self.processor.config.audio_input_path / filename
        success = self.processor.process_audio_file(audio_path)
        return success
    
    @capture_output
    def generate_timeline_all(self):
        """Generate timeline for all projects"""
        results = self.processor.timeline_generator.process_all_projects()
        return results
    
    @capture_output
    def generate_timeline_project(self, project_name):
        """Generate timeline for a specific project"""
        count = self.processor.timeline_generator.generate_missing_weeks(project_name)
        return count
    
    def get_available_projects(self):
        """Get list of available projects"""
        return self.processor.config.get_available_projects()
    
    def find_audio_files(self):
        """Find audio files in inbox"""
        return [f.name for f in self.processor.find_audio_files()]
    
    @capture_output
    def show_settings(self):
        """Show current settings"""
        self.processor._show_settings()

class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress log messages to keep console clean
        return
    
    def do_GET(self):
        global processor, web_processor, output_buffer
        
        # Parse URL and parameters
        parsed_path = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed_path.query)
        
        # Main page
        if parsed_path.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            
            # Get available audio files and projects
            audio_files = web_processor.find_audio_files()
            projects = web_processor.get_available_projects()
            
            # HTML content with larger buttons and status area
            html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <title>Daily Notes</title>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5; }}
                    h1 {{ color: #333; font-size: 24px; margin-bottom: 20px; }}
                    h2 {{ color: #555; font-size: 20px; margin: 20px 0 10px 0; }}
                    .button-container {{ display: flex; flex-direction: column; gap: 15px; margin-bottom: 20px; }}
                    .button {{ 
                        background-color: #4CAF50; 
                        color: white; 
                        border: none; 
                        padding: 15px 20px; 
                        text-align: center; 
                        text-decoration: none; 
                        font-size: 18px; 
                        border-radius: 8px; 
                        cursor: pointer;
                        display: block;
                    }}
                    .button.blue {{ background-color: #2196F3; }}
                    .button.orange {{ background-color: #FF9800; }}
                    .button.disabled {{ background-color: #cccccc; color: #666666; }}
                    .section {{ margin-bottom: 30px; }}
                    .card {{ 
                        background-color: white; 
                        border: 1px solid #ddd; 
                        padding: 15px; 
                        border-radius: 8px;
                        margin-bottom: 15px;
                    }}
                    .file-list {{ 
                        max-height: 200px; 
                        overflow-y: auto; 
                        border: 1px solid #ddd;
                        border-radius: 5px;
                        padding: 0;
                        margin-top: 10px;
                    }}
                    .file-item {{ 
                        padding: 10px 15px;
                        border-bottom: 1px solid #eee;
                        display: flex;
                        align-items: center;
                    }}
                    .file-item:last-child {{ border-bottom: none; }}
                    select, button[type="submit"] {{
                        padding: 12px;
                        border: 1px solid #ddd;
                        border-radius: 5px;
                        font-size: 16px;
                        margin: 5px 0;
                    }}
                    button[type="submit"] {{
                        background-color: #4CAF50;
                        color: white;
                        border: none;
                        cursor: pointer;
                    }}
                    .project-form {{ margin-top: 15px; }}
                    .footer {{ margin-top: 30px; text-align: center; color: #666; font-size: 14px; }}
                    #status-area {{ 
                        background-color: white; 
                        border: 1px solid #ddd; 
                        padding: 15px; 
                        border-radius: 8px;
                        min-height: 100px;
                        max-height: 300px;
                        overflow-y: auto;
                        font-family: monospace;
                        white-space: pre-wrap;
                    }}
                    .output-line {{ margin: 0; }}
                    .badge {{
                        display: inline-block;
                        min-width: 10px;
                        padding: 3px 7px;
                        font-size: 12px;
                        font-weight: 700;
                        line-height: 1;
                        color: #fff;
                        text-align: center;
                        white-space: nowrap;
                        vertical-align: middle;
                        background-color: #777;
                        border-radius: 10px;
                        margin-left: 5px;
                    }}
                </style>
            </head>
            <body>
                <h1>📱 Daily Notes Processor</h1>
                
                <div class="section">
                    <div class="card">
                        <h2>🎤 Process Audio Files</h2>
                        <p>Found {len(audio_files)} audio files in inbox</p>
                        
                        {('<div class="file-list">' + 
                        ''.join([f'<div class="file-item"><a href="/process_file?filename={f}">{f}</a></div>' 
                                for f in audio_files]) + 
                        '</div>') if audio_files else '<p>No audio files available</p>'}
                        
                        <div style="margin-top: 15px;">
                            <a href="/process_audio" class="button {'disabled' if not audio_files else ''}">
                                Process All Audio Files
                            </a>
                        </div>
                    </div>
                </div>
                
                <div class="section">
                    <div class="card">
                        <h2>📅 Generate Timeline</h2>
                        <p>Found {len(projects)} projects</p>
                        
                        <form action="/generate_timeline_project" method="get" class="project-form">
                            <select name="project" required>
                                {' '.join([f'<option value="{p}">{p}</option>' for p in projects])}
                            </select>
                            <button type="submit">Generate for Project</button>
                        </form>
                        
                        <div style="margin-top: 15px;">
                            <a href="/generate_timeline_all" class="button blue {'disabled' if not projects else ''}">
                                Generate All Timelines
                            </a>
                        </div>
                    </div>
                </div>
                
                <div class="section">
                    <a href="/settings" class="button orange">⚙️ Show Settings</a>
                </div>
                
                <div class="section">
                    <h2>Console Output</h2>
                    <div id="status-area">
                        <p class="output-line">Ready. Select an action above.</p>
                    </div>
                </div>
                
                <div class="footer">
                    <p>Add to home screen: tap share/menu → Add to Home Screen</p>
                </div>
                
                <script>
                    // Poll for output updates
                    function updateOutput() {{
                        fetch('/output')
                            .then(response => response.json())
                            .then(data => {{
                                if (data.output && data.output.length > 0) {{
                                    const statusArea = document.getElementById('status-area');
                                    statusArea.innerHTML = '';
                                    
                                    data.output.forEach(line => {{
                                        const p = document.createElement('p');
                                        p.className = 'output-line';
                                        p.textContent = line;
                                        statusArea.appendChild(p);
                                    }});
                                    
                                    // Scroll to bottom
                                    statusArea.scrollTop = statusArea.scrollHeight;
                                }}
                                
                                // Continue polling if a process is running
                                if (data.running) {{
                                    setTimeout(updateOutput, 1000);
                                }}
                            }});
                    }}
                    
                    // Start polling when page loads
                    updateOutput();
                </script>
            </body>
            </html>
            """
            self.wfile.write(html.encode())
            
        # Get console output
        elif parsed_path.path == '/output':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            with output_lock:
                response = {
                    'output': output_buffer,
                    'running': current_process is not None
                }
                
            self.wfile.write(json.dumps(response).encode())
            
        # Process all audio files
        elif parsed_path.path == '/process_audio':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            
            # Run processing in a separate thread
            def process_audio():
                try:
                    web_processor.process_all_audio()
                except Exception as e:
                    print(f"Error processing audio: {e}")
            
            threading.Thread(target=process_audio).start()
            
            html = """
            <!DOCTYPE html>
            <html>
            <head>
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <meta http-equiv="refresh" content="1;url=/">
                <title>Processing Audio</title>
                <style>
                    body { font-family: Arial, sans-serif; margin: 0; padding: 20px; }
                    .loader {
                        border: 8px solid #f3f3f3;
                        border-top: 8px solid #3498db;
                        border-radius: 50%;
                        width: 50px;
                        height: 50px;
                        animation: spin 2s linear infinite;
                        margin: 20px auto;
                    }
                    @keyframes spin {
                        0% { transform: rotate(0deg); }
                        100% { transform: rotate(360deg); }
                    }
                </style>
            </head>
            <body>
                <h2>Processing Audio Files...</h2>
                <div class="loader"></div>
                <p>Processing has started. You'll be redirected to the main page.</p>
                <p><a href="/">Return to main page</a></p>
            </body>
            </html>
            """
            self.wfile.write(html.encode())
            
        # Process specific file
        elif parsed_path.path == '/process_file':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            
            filename = params.get('filename', [''])[0]
            
            # Run processing in a separate thread
            def process_file():
                try:
                    web_processor.process_specific_audio(filename)
                except Exception as e:
                    print(f"Error processing file: {e}")
            
            threading.Thread(target=process_file).start()
            
            html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <meta http-equiv="refresh" content="1;url=/">
                <title>Processing File</title>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; }}
                    .loader {{
                        border: 8px solid #f3f3f3;
                        border-top: 8px solid #3498db;
                        border-radius: 50%;
                        width: 50px;
                        height: 50px;
                        animation: spin 2s linear infinite;
                        margin: 20px auto;
                    }}
                    @keyframes spin {{
                        0% {{ transform: rotate(0deg); }}
                        100% {{ transform: rotate(360deg); }}
                    }}
                </style>
            </head>
            <body>
                <h2>Processing File: {filename}</h2>
                <div class="loader"></div>
                <p>Processing has started. You'll be redirected to the main page.</p>
                <p><a href="/">Return to main page</a></p>
            </body>
            </html>
            """
            self.wfile.write(html.encode())
            
        # Generate timeline for all projects
        elif parsed_path.path == '/generate_timeline_all':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            
            # Run timeline generation in a separate thread
            def generate_all_timelines():
                try:
                    web_processor.generate_timeline_all()
                except Exception as e:
                    print(f"Error generating timelines: {e}")
            
            threading.Thread(target=generate_all_timelines).start()
            
            html = """
            <!DOCTYPE html>
            <html>
            <head>
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <meta http-equiv="refresh" content="1;url=/">
                <title>Generating All Timelines</title>
                <style>
                    body { font-family: Arial, sans-serif; margin: 0; padding: 20px; }
                    .loader {
                        border: 8px solid #f3f3f3;
                        border-top: 8px solid #3498db;
                        border-radius: 50%;
                        width: 50px;
                        height: 50px;
                        animation: spin 2s linear infinite;
                        margin: 20px auto;
                    }
                    @keyframes spin {
                        0% { transform: rotate(0deg); }
                        100% { transform: rotate(360deg); }
                    }
                </style>
            </head>
            <body>
                <h2>Generating All Timelines...</h2>
                <div class="loader"></div>
                <p>Timeline generation has started. You'll be redirected to the main page.</p>
                <p><a href="/">Return to main page</a></p>
            </body>
            </html>
            """
            self.wfile.write(html.encode())
            
        # Generate timeline for specific project
        elif parsed_path.path == '/generate_timeline_project':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            
            project = params.get('project', [''])[0]
            
            # Run timeline generation in a separate thread
            def generate_project_timeline():
                try:
                    web_processor.generate_timeline_project(project)
                except Exception as e:
                    print(f"Error generating timeline for {project}: {e}")
            
            threading.Thread(target=generate_project_timeline).start()
            
            html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <meta http-equiv="refresh" content="1;url=/">
                <title>Generating Timeline</title>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; }}
                    .loader {{
                        border: 8px solid #f3f3f3;
                        border-top: 8px solid #3498db;
                        border-radius: 50%;
                        width: 50px;
                        height: 50px;
                        animation: spin 2s linear infinite;
                        margin: 20px auto;
                    }}
                    @keyframes spin {{
                        0% {{ transform: rotate(0deg); }}
                        100% {{ transform: rotate(360deg); }}
                    }}
                </style>
            </head>
            <body>
                <h2>Generating Timeline for {project}...</h2>
                <div class="loader"></div>
                <p>Timeline generation has started. You'll be redirected to the main page.</p>
                <p><a href="/">Return to main page</a></p>
            </body>
            </html>
            """
            self.wfile.write(html.encode())
            
        # Show settings
        elif parsed_path.path == '/settings':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            
            # Get settings in a separate thread
            def show_settings():
                web_processor.show_settings()
            
            threading.Thread(target=show_settings).start()
            
            html = """
            <!DOCTYPE html>
            <html>
            <head>
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <meta http-equiv="refresh" content="2;url=/">
                <title>Settings</title>
                <style>
                    body { font-family: Arial, sans-serif; margin: 0; padding: 20px; }
                    .loader {
                        border: 8px solid #f3f3f3;
                        border-top: 8px solid #3498db;
                        border-radius: 50%;
                        width: 50px;
                        height: 50px;
                        animation: spin 2s linear infinite;
                        margin: 20px auto;
                    }
                    @keyframes spin {
                        0% { transform: rotate(0deg); }
                        100% { transform: rotate(360deg); }
                    }
                </style>
            </head>
            <body>
                <h2>Loading Settings...</h2>
                <div class="loader"></div>
                <p>Retrieving settings. You'll be redirected to the main page.</p>
                <p><a href="/">Return to main page</a></p>
            </body>
            </html>
            """
            self.wfile.write(html.encode())
            
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'404 Not Found')

def run_server(port=8080):
    global processor, web_processor
    
    # Import here to avoid circular imports
    from android_main import AndroidNotesProcessor
    
    # Initialize processor
    print("Initializing Daily Notes Processor...")
    processor = AndroidNotesProcessor()
    web_processor = WebProcessor(processor)
    
    # Create server
    server_address = ('', port)
    httpd = HTTPServer(server_address, SimpleHTTPRequestHandler)
    
    # Try to determine local IP address
    try:
        import socket
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        print(f"Local IP address: http://{local_ip}:{port}")
    except:
        print("Could not determine local IP address")
    
    # Open browser automatically on non-Android platforms
    if "ANDROID_STORAGE" not in os.environ:
        webbrowser.open(f'http://localhost:{port}/')
    
    print(f"Server started at http://localhost:{port}")
    print("To add to home screen:")
    print("1. Open this URL in your phone's browser")
    print("2. Use the 'Add to Home Screen' option in your browser's menu")
    print("Press Ctrl+C to stop the server")
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")

if __name__ == "__main__":
    run_server()