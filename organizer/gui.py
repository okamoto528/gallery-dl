import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from tkinterdnd2 import DND_FILES, TkinterDnD
import os
import threading
import subprocess
import shutil
from send2trash import send2trash
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
        
        # Search Bar (Everything)
        search_frame = ttk.Frame(self, padding=10)
        search_frame.pack(fill=tk.X)
        
        ttk.Label(search_frame, text="Search (Everything):").pack(side=tk.LEFT)
        self.search_entry = ttk.Entry(search_frame, width=40)
        self.search_entry.pack(side=tk.LEFT, padx=5)
        self.search_entry.bind("<Return>", lambda e: self.search_files())
        
        ttk.Button(search_frame, text="Search & Add", command=self.search_files).pack(side=tk.LEFT)

        # 2. Main List Area (Treeview)
        list_frame = ttk.LabelFrame(self, text="Files", padding=10)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Columns: #0=Read(Tree), File, Author, Category, Status
        self.tree = ttk.Treeview(list_frame, columns=("File", "Author", "Category", "Status"), selectmode="extended")
        
        # Configure headers with sort command
        self.tree.heading("#0", text="Read", command=lambda: self.sort_column("#0", False))
        self.tree.heading("File", text="File", command=lambda: self.sort_column("File", False))
        self.tree.heading("Author", text="Author", command=lambda: self.sort_column("Author", False))
        self.tree.heading("Category", text="Category (Double-click to edit)", command=lambda: self.sort_column("Category", False))
        self.tree.heading("Status", text="Status", command=lambda: self.sort_column("Status", False))
        
        self.tree.column("#0", width=50, anchor="center")
        self.tree.column("File", width=300)
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
        # Single click to edit. Note: This might conflict with row selection.
        # However, user requested "Single click".
        # We need to make sure we don't block selection of other columns.
        self.tree.bind("<ButtonRelease-1>", self.on_click_release)
        # Double click to open file
        self.tree.bind("<Double-1>", self.on_double_click)
        # Keyboard shortcuts
        self.tree.bind("<Control-a>", self._select_all)
        self.tree.bind("<Delete>", self._delete_selected)
        
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
            
    def search_files(self):
        keyword = self.search_entry.get().strip()
        if not keyword:
            messagebox.showwarning("Warning", "Please enter a keyword.")
            return
            
        self.log(f"Searching for '{keyword}' with Everything...")
        # Run in thread to avoid freeze
        threading.Thread(target=self._execute_search, args=(keyword,), daemon=True).start()

    def _execute_search(self, keyword):
        try:
            # es command: keyword .cbz !_trash
            # We filter for .cbz and exclude _trash
            cmd = ["es", keyword, ".cbz", "!_trash"]
            
            # Note: explicit encoding might be needed depending on system. 
            # Trying default (None) which uses system locale (e.g. cp932).
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                self.queue_log(f"Search failed: {result.stderr}")
                return

            lines = result.stdout.strip().splitlines()
            count = 0
            for line in lines:
                path = line.strip()
                
                # Filter out _trash directory generally
                if "_trash" in path.lower():
                    # More strict check: if _trash is part of the directory path
                    # (Simple string check might falsely trigger on "my_trash_manga.cbz")
                    # But user asked for E:\_trash exclusion.
                    # Let's check if separator+_trash+separator is in it, or if it starts/ends with it in the dir component.
                    # Safest generic way for "in _trash folder":
                    if os.sep + "_trash" + os.sep in path.lower() or path.lower().startswith("_trash" + os.sep) or path.lower().endswith(os.sep + "_trash"):
                        continue
                    # Also handle E:\_trash\file.cbz -> E:\_trash matches start
                    # Let's simple normalize and check regex or just simple substring if acceptable.
                    # Given the request, "exclude files in _trash".
                    if r"\_trash\\" in path or "/_trash/" in path or path.startswith("_trash\\") or r"\_trash" in os.path.dirname(path):
                         # If the directory name itself is _trash
                         # Let's use a simpler path component check
                         parts = path.split(os.sep)
                         if "_trash" in [p.lower() for p in parts[:-1]]: # Check directories only
                             continue

                if os.path.isfile(path) and path.lower().endswith('.cbz'):
                    # Add to tree (must be on main thread)
                    self.after(0, self.add_file_to_tree, path)
                    count += 1
            
            self.queue_log(f"Found and added {count} files.")
            
        except FileNotFoundError:
             self.queue_log("Error: 'es' command not found. Please ensure Everything is installed and 'es.exe' is in your PATH.")
        except Exception as e:
             self.queue_log(f"Search error: {e}")

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
        
        # Use Unicode Checkboxes: ☐ (u2610) / ☑ (u2611)
        # Note: Some fonts might not show these well. [ ] / [x] is safer if unicode fail.
        # Let's try Unicode first as requested "checkbox" look.
        # Format: "☐" for #0, Filename for #1
        checked_char = "☑" # or \u2611
        unchecked_char = "☐" # or \u2610
        
        # Check if already in Read folder
        # Simple check: parent folder is named "Read"
        is_read = False
        parent_dir = os.path.basename(os.path.dirname(path))
        if parent_dir.lower() == "read":
            is_read = True
            
        initial_check = checked_char if is_read else unchecked_char
        
        # text=#0(Read), values=(File, Author, Category, Status)
        item_id = self.tree.insert("", tk.END, text=initial_check, values=(os.path.basename(path), author, prediction, "Pending"))
        self.files_map[path] = item_id

    def on_click_release(self, event):
        """Handle single click release to edit category specific column or toggle checkbox"""
        region = self.tree.identify("region", event.x, event.y)
        if region != "tree" and region != "cell":
            return
            
        column = self.tree.identify_column(event.x)
        item_id = self.tree.identify_row(event.y)
        if not item_id:
            return

        # Check for checkbox click in tree column (#0)
        # Treeview #0 is the "tree" label
        if column == "#0":
            current_text = self.tree.item(item_id, "text")
            unchecked_char = "☐"
            checked_char = "☑"
            new_text = ""
            new_is_read = False
            
            if current_text == unchecked_char:
                new_text = checked_char
                new_is_read = True
            elif current_text == checked_char:
                new_text = unchecked_char
                new_is_read = False
            else:
                return # Unknown state

            # Toggle UI first
            self.tree.item(item_id, text=new_text)
            
            # Execute Immediate Move
            self._execute_immediate_move(item_id, new_is_read)
            return

        # Columns: #0=Read, #1=File, #2=Author, #3=Category, #4=Status
        if column == "#3": # Category
            self.edit_category(item_id, column)

    def sort_column(self, col, reverse):
        """Sort tree contents when a column header is clicked."""
        l = []
        for k in self.tree.get_children(''):
            if col == "#0":
                val = self.tree.item(k, 'text')
            else:
                val = self.tree.set(k, col)
            l.append((val, k))

        l.sort(key=lambda t: t[0].lower() if isinstance(t[0], str) else t[0], reverse=reverse)

        for index, (val, k) in enumerate(l):
            self.tree.move(k, '', index)

        # Update heading command to reverse sort on next click
        self.tree.heading(col, command=lambda: self.sort_column(col, not reverse))

    def on_double_click(self, event):
        """Handle double click to open file"""
        region = self.tree.identify("region", event.x, event.y)
        if region != "tree" and region != "cell":
             return

        column = self.tree.identify_column(event.x)
        # Columns: #0=Read, #1=File, ...
        # Allow opening via File column (#1) or even Read column if double clicked (toggle + open? ignore.)
        # Let's restrict to File (#1)
        if column == "#1":
            item_id = self.tree.identify_row(event.y)
            if not item_id:
                return
            
            # Retrieve file path
            file_path = None
            for p, iid in self.files_map.items():
                if iid == item_id:
                    file_path = p
                    break
            
            if file_path and os.path.exists(file_path):
                try:
                    os.startfile(file_path)
                    self.log(f"Opened file: {os.path.basename(file_path)}")
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to open file: {e}")
            else:
                 messagebox.showwarning("Warning", "File not found.")

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
        combo.bind("<<ComboboxSelected>>", save_edit)
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
            # Preserve File, Author and Status, update Category
            # values = (File, Author, Category, Status)
            current_values = self.tree.item(item, "values")
            # Update index 2 (Category)
            self.tree.item(item, values=(current_values[0], current_values[1], new_cat, current_values[3]))

    def clear_list(self):
        self.files_map.clear()
        for item in self.tree.get_children():
            self.tree.delete(item)

    def _select_all(self, event=None):
        """Ctrl+A: Files リストの全アイテムを選択"""
        all_items = self.tree.get_children()
        if all_items:
            self.tree.selection_set(all_items)
        return "break"

    def _delete_selected(self, event=None):
        """Del: 選択されたファイルをゴミ箱に移動し、リストから削除"""
        selected_items = self.tree.selection()
        if not selected_items:
            return

        count = len(selected_items)
        if not messagebox.askyesno("確認", f"{count} 件のファイルをゴミ箱に移動しますか？"):
            return

        moved = 0
        errors = 0
        for item in selected_items:
            path_to_remove = None
            for path, iid in self.files_map.items():
                if iid == item:
                    path_to_remove = path
                    break

            if path_to_remove and os.path.exists(path_to_remove):
                try:
                    send2trash(path_to_remove)
                    self.log(f"Trashed: {os.path.basename(path_to_remove)}")
                    moved += 1
                except Exception as e:
                    self.log(f"Error trashing {os.path.basename(path_to_remove)}: {e}")
                    errors += 1
                    continue

            if path_to_remove:
                del self.files_map[path_to_remove]
            self.tree.delete(item)

        self.log(f"Delete completed: {moved} moved to _trash, {errors} errors.")

    def open_alias_manager(self):
        # Alias manager needs update? It uses DB, independent of list.
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
                # values = (File, Author, Category, Status) -> Author is index 1
                author = values[1]
                if author and author != "Unknown":
                    authors_to_process.add(author)
        else:
            # Get all unique Authors from the file list
            for item in self.tree.get_children():
                values = self.tree.item(item, "values")
                author = values[1]
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
                    encoding='cp932',
                    errors='replace'
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

    def _execute_immediate_move(self, item_id, is_read):
        """Execute move for a single item triggered by user action."""
        # Retrieve current info
        values = self.tree.item(item_id, "values")
        author = values[1]
        target_cat = values[2]
        
        # Find current path
        file_path = None
        for p, iid in self.files_map.items():
            if iid == item_id:
                file_path = p
                break
        
        if not file_path:
            self.log(f"Error: Could not find path for item {item_id}")
            return

        base_path = self.dir_entry.get()
        self.tree.set(item_id, "Status", "Moving...")
        
        # Run in thread or sync? 
        # Sync is safer for map update consistency unless we lock. 
        # Since it's one file, let's try sync for responsiveness check, or short thread.
        # User wants "Timing of check".
        
        def run_move():
            success, msg, new_path = self.organizer.organize_file(file_path, target_cat, base_path, is_read=is_read)
            
            # Post-move updates (schedule on main thread)
            self.after(0, lambda: self._post_move_update(item_id, success, msg, new_path, file_path))
            
        threading.Thread(target=run_move, daemon=True).start()

    def _post_move_update(self, item_id, success, msg, new_path, old_path):
        if success:
            status = "Done"
            if "already in target" in msg:
                 status = "Done (In Place)"
            
            self.tree.set(item_id, "Status", status)
            self.log(f"[Auto-Move] {msg}")
            
            # Update map if path changed
            if new_path and new_path != old_path:
                if old_path in self.files_map:
                    del self.files_map[old_path]
                self.files_map[new_path] = item_id
                
        else:
            self.tree.set(item_id, "Status", "Error")
            self.log(f"[Auto-Move Error] {msg}")
            # Revert checkbox?
            # Doing so might cause confusion if user spams click. Leave as is, user sees Error.

    def process_files(self, base_path):
        self.queue_log("--- Starting Processing ---")
        
        # We iterate over the TREE items to maintain order
        items = self.tree.get_children()
        
        success_count = 0
        skip_count = 0
        fail_count = 0
        
        for item_id in items:
            # values = (File, Author, Category, Status)
            values = self.tree.item(item_id, "values")
            # Index 2 is Category
            target_cat = values[2]
            author = values[1]
            
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
            self.queue_update_item(item_id, values[0], author, target_cat, "Processing...")
            
            # Check read status
            item_text = self.tree.item(item_id, "text")
            is_read = item_text.startswith("☑")
            
            success, msg, new_path = self.organizer.organize_file(file_path, target_cat, base_path, is_read=is_read)
            
            status_msg = ""
            if success:
                if "already in target" in msg:
                     status_msg = "Done (In Place)"
                     success_count += 1
                else:    
                     status_msg = "Done"
                     success_count += 1
                self.queue_log(f"  [OK] {msg}")
                
                # Update map
                if new_path and new_path != file_path:
                    if file_path in self.files_map:
                        del self.files_map[file_path]
                    self.files_map[new_path] = item_id
                    
            else:
                if "already exists" in msg:
                    status_msg = "Skipped"
                    skip_count += 1
                    self.queue_log(f"  [Skip] {msg}")
                else:
                    status_msg = "Error"
                    fail_count += 1
                    self.queue_log(f"  [Error] {msg}")
            
            self.queue_update_item(item_id, values[0], author, target_cat, status_msg)
        
        self.queue_log(f"--- Completed: {success_count} OK, {skip_count} Skip, {fail_count} Fail ---")
        self.after(0, self.cleanup_ui)

    def queue_log(self, msg):
        self.after(0, lambda: self.log(msg))
        
    def queue_update_item(self, item_id, filename, author, cat, status):
        # values = (File, Author, Category, Status)
        self.after(0, lambda: self.tree.item(item_id, values=(filename, author, cat, status)))

    def cleanup_ui(self):
        self.process_btn.config(state='normal')
        messagebox.showinfo("Done", "Processing Complete")

if __name__ == "__main__":
    app = OrganizerApp()
    app.mainloop()
