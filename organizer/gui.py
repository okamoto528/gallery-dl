import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from tkinterdnd2 import DND_FILES, TkinterDnD
import os
import threading
from .db_manager import DBManager
from .file_organizer import FileOrganizer

# Configuration Defaults
DEFAULT_CONFIG = {
    "output_dir": r"T:\organized_h_manga"
}

class AliasManager(tk.Toplevel):
    def __init__(self, parent, db_manager):
        super().__init__(parent)
        self.title("Manage Author Aliases")
        self.geometry("500x400")
        self.db = db_manager
        
        self.create_widgets()
        
    def create_widgets(self):
        # Frame for Adder
        add_frame = ttk.LabelFrame(self, text="Add New Alias")
        add_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(add_frame, text="Alias Name:").grid(row=0, column=0, padx=5, pady=5)
        self.alias_entry = ttk.Entry(add_frame, width=30)
        self.alias_entry.grid(row=0, column=1, padx=5, pady=5)
        
        ttk.Label(add_frame, text="Primary Author:").grid(row=1, column=0, padx=5, pady=5)
        self.primary_entry = ttk.Entry(add_frame, width=30)
        self.primary_entry.grid(row=1, column=1, padx=5, pady=5)
        
        ttk.Button(add_frame, text="Add", command=self.add_alias).grid(row=2, column=1, sticky="e", padx=5, pady=5)
        
        # Frame for List (Simple view for now, maybe just search)
        # For MVP, just the adder is critical.
        info_label = ttk.Label(self, text="* Aliases map a variation to a primary name.\n* Changes take effect on next organization.")
        info_label.pack(padx=10, pady=10)

    def add_alias(self):
        alias = self.alias_entry.get().strip()
        primary = self.primary_entry.get().strip()
        
        if not alias or not primary:
            messagebox.showerror("Error", "Both fields are required.")
            return

        try:
            self.db.add_alias(alias, primary)
            messagebox.showinfo("Success", f"Mapped '{alias}' -> '{primary}'")
            self.alias_entry.delete(0, tk.END)
            self.primary_entry.delete(0, tk.END)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to add alias: {e}")

class OrganizerApp(TkinterDnD.Tk):
    def __init__(self):
        super().__init__()
        self.title("Hitomi Organizer")
        self.geometry("800x600")
        
        # Initialize Backend
        self.db = DBManager()
        self.organizer = FileOrganizer(self.db)
        
        self.files_to_process = []
        self.base_dir = os.path.abspath("downloads") # Default
        
        self.create_menu()
        self.create_widgets()

    def create_menu(self):
        menubar = tk.Menu(self)
        self.config(menu=menubar)
        
        tools_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Tools", menu=tools_menu)
        tools_menu.add_command(label="Manage Author Aliases", command=self.open_alias_manager)

    def create_widgets(self):
        # 1. Top Bar: Directory & Category
        top_frame = ttk.Frame(self, padding=10)
        top_frame.pack(fill=tk.X)
        
        # Output Dir
        ttk.Label(top_frame, text="Output Directory:").pack(side=tk.LEFT)
        self.dir_entry = ttk.Entry(top_frame, width=40)
        self.dir_entry.insert(0, self.base_dir)
        self.dir_entry.pack(side=tk.LEFT, padx=5)
        ttk.Button(top_frame, text="Browse", command=self.browse_dir).pack(side=tk.LEFT)
        
        # Category Selection
        ttk.Label(top_frame, text="  Category (Type):").pack(side=tk.LEFT)
        self.category_var = tk.StringVar()
        self.category_combo = ttk.Combobox(top_frame, textvariable=self.category_var, width=15)
        self.category_combo['values'] = ('Doujinshi', 'Manga', 'Game CG', 'Artist CG', 'Anime', 'Unknown')
        self.category_combo.pack(side=tk.LEFT, padx=5)
        self.category_combo.current(0)
        
        # 2. Main Drop Area
        drop_frame = ttk.LabelFrame(self, text="Drop Files Here", padding=10)
        drop_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.file_listbox = tk.Listbox(drop_frame, selectmode=tk.EXTENDED)
        self.file_listbox.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        
        scrollbar = ttk.Scrollbar(drop_frame, orient="vertical", command=self.file_listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.file_listbox.config(yscrollcommand=scrollbar.set)
        
        # DnD Binding
        self.file_listbox.drop_target_register(DND_FILES)
        self.file_listbox.dnd_bind('<<Drop>>', self.drop_files)
        
        # 3. Bottom Bar: Actions & Log
        action_frame = ttk.Frame(self, padding=10)
        action_frame.pack(fill=tk.X)
        
        self.process_btn = ttk.Button(action_frame, text="Start Organize", command=self.start_processing_thread)
        self.process_btn.pack(side=tk.LEFT)
        
        ttk.Button(action_frame, text="Clear List", command=self.clear_list).pack(side=tk.LEFT, padx=5)
        
        # Log Area
        log_frame = ttk.LabelFrame(self, text="Log", padding=5)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.log_text = tk.Text(log_frame, height=8, state='disabled')
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def log(self, message):
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state='disabled')

    def browse_dir(self):
        path = filedialog.askdirectory(initialdir=self.base_dir)
        if path:
            self.base_dir = path
            self.dir_entry.delete(0, tk.END)
            self.dir_entry.insert(0, path)

    def drop_files(self, event):
        files = self.tk.splitlist(event.data)
        for f in files:
            if os.path.isdir(f):
                # Scan directory
                for root, _, filenames in os.walk(f):
                    for filename in filenames:
                        if filename.lower().endswith('.cbz'):
                            full_path = os.path.join(root, filename)
                            self.add_file_to_list(full_path)
            elif f.lower().endswith('.cbz'):
                self.add_file_to_list(f)
        
        self.predict_category()

    def add_file_to_list(self, path):
        if path not in self.files_to_process:
            self.files_to_process.append(path)
            self.file_listbox.insert(tk.END, path)

    def clear_list(self):
        self.files_to_process = []
        self.file_listbox.delete(0, tk.END)

    def predict_category(self):
        """Attempts to predict category from the FIRST file in the list."""
        if not self.files_to_process:
            return
            
        first_file = self.files_to_process[0]
        prediction = self.organizer.get_default_category_for_file(first_file)
        
        if prediction:
            self.category_var.set(prediction)
            self.log(f"Auto-selected category '{prediction}' based on author history.")

    def open_alias_manager(self):
        AliasManager(self, self.db)

    def start_processing_thread(self):
        if not self.files_to_process:
            messagebox.showwarning("Warning", "No files to process.")
            return

        target_cat = self.category_var.get()
        base_path = self.dir_entry.get()
        
        if not target_cat:
            messagebox.showwarning("Warning", "Please select a category.")
            return

        # Disable UI
        self.process_btn.config(state='disabled')
        
        threading.Thread(target=self.process_files, args=(target_cat, base_path), daemon=True).start()

    def process_files(self, category, base_path):
        self.queue_log("--- Starting Processing ---")
        success_count = 0
        fail_count = 0
        
        # Snapshot list
        files = list(self.files_to_process)
        
        for f in files:
            self.queue_log(f"Processing: {os.path.basename(f)}")
            success, msg = self.organizer.organize_file(f, category, base_path)
            if success:
                self.queue_log(f"  [OK] {msg}")
                success_count += 1
            else:
                self.queue_log(f"  [Error] {msg}")
                fail_count += 1
        
        self.queue_log(f"--- Completed: {success_count} Success, {fail_count} Failed ---")
        
        # Schedule UI cleanup
        self.after(0, self.cleanup_ui)

    def queue_log(self, msg):
        self.after(0, lambda: self.log(msg))

    def cleanup_ui(self):
        self.files_to_process = []
        self.file_listbox.delete(0, tk.END)
        self.process_btn.config(state='normal')
        messagebox.showinfo("Done", "Processing Complete")


if __name__ == "__main__":
    app = OrganizerApp()
    app.mainloop()
