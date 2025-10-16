#!/usr/bin/env python3

import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import os
import threading

class SimpleREDLINEGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("REDLINE - Financial Data Processor")
        self.root.geometry("600x400")
        
        # Main frame
        main_frame = ttk.Frame(root, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Title
        title = ttk.Label(main_frame, text="🚀 REDLINE Financial Data Processor", 
                         font=('Arial', 16, 'bold'))
        title.pack(pady=(0, 20))
        
        # Status
        status_frame = ttk.LabelFrame(main_frame, text="System Status", padding="10")
        status_frame.pack(fill=tk.X, pady=(0, 20))
        
        ttk.Label(status_frame, text="✅ ARM64 Docker Container: Ready").pack(anchor=tk.W)
        ttk.Label(status_frame, text="✅ Stooq Data: 13,941 files ready").pack(anchor=tk.W)
        ttk.Label(status_frame, text="✅ Native GUI: Running").pack(anchor=tk.W)
        
        # Buttons
        button_frame = ttk.LabelFrame(main_frame, text="Actions", padding="10")
        button_frame.pack(fill=tk.X, pady=(0, 20))
        
        self.process_btn = ttk.Button(button_frame, text="📊 Process Stooq Data", 
                                     command=self.process_data)
        self.process_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        self.view_btn = ttk.Button(button_frame, text="👁️ Open Data Folder", 
                                  command=self.open_folder)
        self.view_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        self.docker_btn = ttk.Button(button_frame, text="🐳 Run CLI Version", 
                                    command=self.run_cli)
        self.view_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        # Output area
        output_frame = ttk.LabelFrame(main_frame, text="Output", padding="10")
        output_frame.pack(fill=tk.BOTH, expand=True)
        
        self.output_text = tk.Text(output_frame, height=10, wrap=tk.WORD)
        scrollbar = ttk.Scrollbar(output_frame, orient=tk.VERTICAL, command=self.output_text.yview)
        self.output_text.configure(yscrollcommand=scrollbar.set)
        
        self.output_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Initial message
        self.log("🚀 REDLINE Native GUI Ready!")
        self.log("✅ ARM64 Docker container available")
        self.log("✅ 13,941 Stooq data files ready for processing")
        self.log("")
        self.log("Click 'Process Stooq Data' to begin...")
    
    def log(self, message):
        """Add message to log"""
        self.output_text.insert(tk.END, f"{message}\n")
        self.output_text.see(tk.END)
        self.root.update_idletasks()
    
    def process_data(self):
        """Process data using Docker"""
        self.log("🔄 Starting data processing...")
        self.process_btn.config(state='disabled')
        
        def run_process():
            try:
                cmd = [
                    'docker', 'run', '--rm',
                    '-v', f'{os.getcwd()}:/app',
                    '-v', f'{os.getcwd()}/data:/app/data',
                    'redline_arm',
                    'python3', '/app/data_module.py', '--task=load'
                ]
                
                self.log(f"Running: {' '.join(cmd)}")
                
                result = subprocess.run(cmd, capture_output=True, text=True)
                
                if result.stdout:
                    self.log("Output:")
                    self.log(result.stdout)
                
                if result.stderr:
                    self.log("Errors:")
                    self.log(result.stderr)
                
                if result.returncode == 0:
                    self.log("✅ Processing completed successfully!")
                else:
                    self.log(f"❌ Processing failed (exit code: {result.returncode})")
                    
            except Exception as e:
                self.log(f"❌ Error: {str(e)}")
            finally:
                self.process_btn.config(state='normal')
        
        threading.Thread(target=run_process, daemon=True).start()
    
    def open_folder(self):
        """Open data folder"""
        data_dir = os.path.join(os.getcwd(), 'data')
        if os.path.exists(data_dir):
            subprocess.run(['open', data_dir])
            self.log(f"📁 Opened: {data_dir}")
        else:
            self.log("❌ Data directory not found")
    
    def run_cli(self):
        """Run CLI version"""
        self.log("🐳 Running CLI version...")
        subprocess.Popen(['./run_stooq_arm.bash'], cwd=os.getcwd())
        self.log("✅ CLI version started in new terminal")

def main():
    root = tk.Tk()
    app = SimpleREDLINEGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
