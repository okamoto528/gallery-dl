import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from tkinterdnd2 import DND_FILES, TkinterDnD
import os
import threading
import subprocess
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
        self.geometry("900x600")
        
        # Initialize Backend
        self.db = DBManager()
        self.organizer = FileOrganizer(self.db)
        
        self.files_map = {} # path -> item_id
        self.base_dir = DEFAULT_CONFIG["output_dir"]
        
        # Load Categories
        self.categories = self.db.get_all_categories()
        
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
        
        # Category Selection (Batch)
        ttk.Label(top_frame, text="  Category Selection:").pack(side=tk.LEFT)
        self.category_var = tk.StringVar()
        self.category_combo = ttk.Combobox(top_frame, textvariable=self.category_var, width=15)
        self.category_combo['values'] = self.categories
        self.category_combo.pack(side=tk.LEFT, padx=5)
        if self.categories:
            self.category_combo.current(0)
        
        ttk.Button(top_frame, text="Apply to Selected", command=self.apply_category).pack(side=tk.LEFT)
        
        # 2. Main List Area (Treeview)
        list_frame = ttk.LabelFrame(self, text="Files", padding=10)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Columns: #0=File(Tree), Author, Category, Status
        self.tree = ttk.Treeview(list_frame, columns=("Author", "Category", "Status"), selectmode="extended")
        self.tree.heading("#0", text="File")
        self.tree.heading("Author", text="Author")
        self.tree.heading("Category", text="Category (Double-click to edit)")
        self.tree.heading("Status", text="Status")
        
        self.tree.column("#0", width=300)
        self.tree.column("Author", width=150)
        self.tree.column("Category", width=100)
        self.tree.column("Status", width=150)
        
        self.tree.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.config(yscrollcommand=scrollbar.set)
        
        # DnD Binding
        self.tree.drop_target_register(DND_FILES)
        self.tree.dnd_bind('<<Drop>>', self.drop_files)
        
        # Editing Binding
        self.tree.bind("<Double-1>", self.on_double_click)
        
        # 3. Bottom Bar: Actions & Log
        action_frame = ttk.Frame(self, padding=10)
        action_frame.pack(fill=tk.X)
        
        self.process_btn = ttk.Button(action_frame, text="Start Organize", command=self.start_processing_thread)
        self.process_btn.pack(side=tk.LEFT)
        
        ttk.Button(action_frame, text="Clear List", command=self.clear_list).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(action_frame, text="Clean Duplicates", command=self.run_clean_duplicates).pack(side=tk.LEFT, padx=5)
        
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
            # Update config implementation if we had persistance...

    def drop_files(self, event):
        files = self.tk.splitlist(event.data)
        for f in files:
            if os.path.isdir(f):
                for root, _, filenames in os.walk(f):
                    for filename in filenames:
                        if filename.lower().endswith('.cbz'):
                            full_path = os.path.join(root, filename)
                            self.add_file_to_tree(full_path)
            elif f.lower().endswith('.cbz'):
                self.add_file_to_tree(f)

    def add_file_to_tree(self, path):
        if path in self.files_map:
            return # Already in list
            
        # Predict Category
        # Returns (Category, AuthorName)
        prediction, author = self.organizer.get_default_category_for_file(path)
        
        if not prediction:
            # Fallback to current combo value or Unknown
            prediction = self.category_var.get()
            if not prediction and self.categories:
                prediction = self.categories[0]
        
        if not author:
            author = "Unknown"
            
        item_id = self.tree.insert("", tk.END, text=os.path.basename(path), values=(author, prediction, "Pending"))
        self.files_map[path] = item_id

    def on_double_click(self, event):
        """Handle double click to edit category"""
        region = self.tree.identify("region", event.x, event.y)
        if region != "cell":
            return
            
        column = self.tree.identify_column(event.x)
        # Columns: #0=File(tree), #1=Author, #2=Category, #3=Status
        if column == "#2": # Category
            item_id = self.tree.identify_row(event.y)
            if not item_id:
                return
                
            self.edit_category(item_id, column)

    def edit_category(self, item_id, column):
        x, y, w, h = self.tree.bbox(item_id, column)
        
        # Create a combobox for editing
        current_val = self.tree.set(item_id, "Category")
        
        combo = ttk.Combobox(self.tree, values=self.categories)
        combo.set(current_val)
        combo.place(x=x, y=y, width=w, height=h)
        combo.focus()
        
        def save_edit(event=None):
            new_val = combo.get().strip()
            if new_val:
                self.check_and_add_category(new_val)
                self.tree.set(item_id, "Category", new_val)
            combo.destroy()
            
        def cancel_edit(event=None):
            combo.destroy()
            
        combo.bind("<Return>", save_edit)
        combo.bind("<FocusOut>", save_edit)
        combo.bind("<Escape>", cancel_edit)

    def check_and_add_category(self, name):
        """Check if category is new, and if so add to DB and update lists."""
        if name not in self.categories:
            self.db.add_category(name)
            self.categories = self.db.get_all_categories() # Refresh to get sorted logic if any, or just append
            self.update_combos()
            self.log(f"New category added: {name}")

    def update_combos(self):
        self.category_combo['values'] = self.categories

    def apply_category(self):
        """Applies current dropdown category to selected rows"""
        selected_items = self.tree.selection()
        if not selected_items:
            messagebox.showinfo("Info", "No files selected.")
            return
            
        new_cat = self.category_var.get().strip()
        if new_cat:
            self.check_and_add_category(new_cat)
            
        for item in selected_items:
            # Preserve Author and Status, update Category
            # values = (Author, Category, Status)
            current_values = self.tree.item(item, "values")
            self.tree.item(item, values=(current_values[0], new_cat, current_values[2]))

    def clear_list(self):
        self.files_map.clear()
        for item in self.tree.get_children():
            self.tree.delete(item)

    def open_alias_manager(self):
        AliasManager(self, self.db)

    def run_clean_duplicates(self):
        """Run clean_duplicates.py with the Author from selected files or all files."""
        selected_items = self.tree.selection()
        
        # Collect Authors to process
        authors_to_process = set()
        
        if selected_items:
            # Get Authors from selected items
            for item in selected_items:
                values = self.tree.item(item, "values")
                author = values[0]  # values = (Author, Category, Status)
                if author and author != "Unknown":
                    authors_to_process.add(author)
        else:
            # Get all unique Authors from the file list
            for item in self.tree.get_children():
                values = self.tree.item(item, "values")
                author = values[0]
                if author and author != "Unknown":
                    authors_to_process.add(author)
        
        if not authors_to_process:
            messagebox.showwarning("Warning", "No valid Authors found.")
            return
        
        # Determine script path
        script_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "clean_duplicates.py")
        
        if not os.path.exists(script_path):
            messagebox.showerror("Error", f"Script not found: {script_path}")
            return
        
        self.log(f"Running Clean Duplicates for {len(authors_to_process)} author(s)...")
        
        # Run in a separate thread
        threading.Thread(target=self._execute_clean_duplicates_batch, args=(script_path, list(authors_to_process)), daemon=True).start()

    def _execute_clean_duplicates_batch(self, script_path, authors):
        """Execute clean_duplicates for each unique author."""
        for author in authors:
            keyword = f"[{author}]"
            self.queue_log(f"  Processing: {keyword}")
            try:
                result = subprocess.run(
                    ["python", script_path, "--keyword", keyword],
                    capture_output=True,
                    text=True,
                    encoding='utf-8'
                )
                
                if result.stdout:
                    for line in result.stdout.strip().split('\n'):
                        self.queue_log(f"    {line}")
                if result.stderr:
                    for line in result.stderr.strip().split('\n'):
                        self.queue_log(f"    [ERR] {line}")
                        
            except Exception as e:
                self.queue_log(f"  Error: {e}")
        
        self.queue_log("Clean Duplicates completed.")

    def start_processing_thread(self):
        if not self.files_map:
            messagebox.showwarning("Warning", "No files to process.")
            return
        
        base_path = self.dir_entry.get()
        
        # Disable UI
        self.process_btn.config(state='disabled')
        
        threading.Thread(target=self.process_files, args=(base_path,), daemon=True).start()

    def process_files(self, base_path):
        self.queue_log("--- Starting Processing ---")
        
        # We iterate over the TREE items to maintain order and get the user-set category
        items = self.tree.get_children()
        
        success_count = 0
        skip_count = 0
        fail_count = 0
        
        for item_id in items:
            # info = [Author, Category, Status]
            values = self.tree.item(item_id, "values")
            target_cat = values[1]
            
            # Find path from map
            file_path = None
            for p, iid in self.files_map.items():
                if iid == item_id:
                    file_path = p
                    break
            
            if not file_path:
                continue

            self.queue_log(f"Processing: {os.path.basename(file_path)}")
            # Update status to processing
            self.queue_update_item(item_id, values[0], target_cat, "Processing...")
            
            success, msg = self.organizer.organize_file(file_path, target_cat, base_path)
            
            status_msg = ""
            if success:
                # organize_file returns True on move or "File already in target".
                # If msg indicates skip... wait. file_organizer returns False on existence collision?
                # User said "Status: Skipped".
                # My logic in file_organizer: return False, "Target file already exists: ..."
                if "already in target" in msg:
                     status_msg = "Done (In Place)"
                     success_count += 1
                else:    
                     status_msg = "Done"
                     success_count += 1
                self.queue_log(f"  [OK] {msg}")
            else:
                if "already exists" in msg:
                    status_msg = "Skipped"
                    skip_count += 1
                    self.queue_log(f"  [Skip] {msg}")
                else:
                    status_msg = "Error"
                    fail_count += 1
                    self.queue_log(f"  [Error] {msg}")
            
            self.queue_update_item(item_id, values[0], target_cat, status_msg)
        
        self.queue_log(f"--- Completed: {success_count} OK, {skip_count} Skip, {fail_count} Fail ---")
        self.after(0, self.cleanup_ui)

    def queue_log(self, msg):
        self.after(0, lambda: self.log(msg))
        
    def queue_update_item(self, item_id, author, cat, status):
        self.after(0, lambda: self.tree.item(item_id, values=(author, cat, status)))

    def cleanup_ui(self):
        self.process_btn.config(state='normal')
        messagebox.showinfo("Done", "Processing Complete")

if __name__ == "__main__":
    app = OrganizerApp()
    app.mainloop()
