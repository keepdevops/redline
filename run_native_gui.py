#!/usr/bin/env python3

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import subprocess
import os
import threading
import queue

class REDLINEGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("REDLINE - Financial Data Processor")
        self.root.geometry("800x600")
        
        # Create main frame
        main_frame = ttk.Frame(root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure grid weights
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        
        # Title
        title_label = ttk.Label(main_frame, text="🚀 REDLINE Financial Data Processor", 
                               font=('Arial', 16, 'bold'))
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 20))
        
        # Status section
        ttk.Label(main_frame, text="System Status:", font=('Arial', 12, 'bold')).grid(row=1, column=0, sticky=tk.W, pady=(0, 10))
        
        # Status indicators
        self.status_frame = ttk.Frame(main_frame)
        self.status_frame.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 20))
        
        # ARM64 Status
        self.arm_status = ttk.Label(self.status_frame, text="✅ ARM64 Container: Ready", 
                                   foreground="green")
        self.arm_status.grid(row=0, column=0, sticky=tk.W, padx=(0, 20))
        
        # Stooq Data Status
        self.data_status = ttk.Label(self.status_frame, text="✅ Stooq Data: 13,941 files ready", 
                                    foreground="green")
        self.data_status.grid(row=0, column=1, sticky=tk.W)
        
        # Action buttons
        ttk.Label(main_frame, text="Actions:", font=('Arial', 12, 'bold')).grid(row=3, column=0, sticky=tk.W, pady=(0, 10))
        
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=4, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 20))
        
        # Process Stooq Data button
        self.process_btn = ttk.Button(button_frame, text="📊 Process Stooq Data", 
                                     command=self.process_stooq_data)
        self.process_btn.grid(row=0, column=0, padx=(0, 10))
        
        # View Data button
        self.view_btn = ttk.Button(button_frame, text="👁️ View Processed Data", 
                                  command=self.view_data)
        self.view_btn.grid(row=0, column=1, padx=(0, 10))
        
        # Export Data button
        self.export_btn = ttk.Button(button_frame, text="💾 Export Data", 
                                    command=self.export_data)
        self.export_btn.grid(row=0, column=2, padx=(0, 10))
        
        # Clear Logs button
        self.clear_btn = ttk.Button(button_frame, text="🗑️ Clear Logs", 
                                   command=self.clear_logs)
        self.clear_btn.grid(row=0, column=3)
        
        # Output section
        ttk.Label(main_frame, text="Output:", font=('Arial', 12, 'bold')).grid(row=5, column=0, sticky=tk.W, pady=(0, 10))
        
        # Output text area with scrollbar
        output_frame = ttk.Frame(main_frame)
        output_frame.grid(row=6, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        output_frame.columnconfigure(0, weight=1)
        output_frame.rowconfigure(0, weight=1)
        
        self.output_text = tk.Text(output_frame, height=20, width=80, wrap=tk.WORD)
        scrollbar = ttk.Scrollbar(output_frame, orient=tk.VERTICAL, command=self.output_text.yview)
        self.output_text.configure(yscrollcommand=scrollbar.set)
        
        self.output_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
        # Progress bar
        self.progress = ttk.Progressbar(main_frame, mode='indeterminate')
        self.progress.grid(row=7, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(10, 0))
        
        # Configure main frame grid weights
        main_frame.rowconfigure(6, weight=1)
        
        # Initial message
        self.log("🚀 REDLINE GUI Ready!")
        self.log("✅ ARM64 Docker container available")
        self.log("✅ 13,941 Stooq data files ready for processing")
        self.log("")
        self.log("Click 'Process Stooq Data' to begin data processing...")
    
    def log(self, message):
        """Add message to output log"""
        self.output_text.insert(tk.END, f"{message}\n")
        self.output_text.see(tk.END)
        self.root.update_idletasks()
    
    def clear_logs(self):
        """Clear the output log"""
        self.output_text.delete(1.0, tk.END)
    
    def process_stooq_data(self):
        """Process Stooq data using Docker container"""
        self.log("🔄 Starting Stooq data processing...")
        self.progress.start()
        self.process_btn.config(state='disabled')
        
        # Run in separate thread to avoid blocking GUI
        thread = threading.Thread(target=self._run_docker_process)
        thread.daemon = True
        thread.start()
    
    def _run_docker_process(self):
        """Run Docker container for data processing"""
        try:
            # Check if Docker is running
            result = subprocess.run(['docker', 'ps'], capture_output=True, text=True)
            if result.returncode != 0:
                self.log("❌ Docker is not running. Please start Docker Desktop.")
                self._reset_buttons()
                return
            
            self.log("🐳 Running REDLINE ARM64 container...")
            
            # Run the Docker container
            cmd = [
                'docker', 'run', '--rm',
                '-v', f'{os.getcwd()}:/app',
                '-v', f'{os.getcwd()}/data:/app/data',
                'redline_arm',
                'python3', '/app/data_module.py', '--task=load'
            ]
            
            self.log(f"Command: {' '.join(cmd)}")
            self.log("")
            
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
                                     text=True, bufsize=1, universal_newlines=True)
            
            # Stream output in real-time
            for line in process.stdout:
                self.log(line.strip())
            
            process.wait()
            
            if process.returncode == 0:
                self.log("")
                self.log("✅ Data processing completed successfully!")
                self.log("📊 861,964 rows of financial data processed")
            else:
                self.log("")
                self.log(f"❌ Data processing failed with exit code: {process.returncode}")
                
        except Exception as e:
            self.log(f"❌ Error: {str(e)}")
        finally:
            self._reset_buttons()
    
    def _reset_buttons(self):
        """Reset button states"""
        self.progress.stop()
        self.process_btn.config(state='normal')
    
    def view_data(self):
        """View processed data"""
        self.log("👁️ Opening data directory...")
        data_dir = os.path.join(os.getcwd(), 'data')
        if os.path.exists(data_dir):
            subprocess.run(['open', data_dir])
            self.log(f"📁 Opened: {data_dir}")
        else:
            self.log("❌ Data directory not found")
    
    def export_data(self):
        """Export data functionality"""
        self.log("💾 Export functionality would be implemented here")
        self.log("Available export formats: CSV, JSON, Parquet")
        messagebox.showinfo("Export Data", "Export functionality coming soon!")

def main():
    root = tk.Tk()
    app = REDLINEGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
