import struct
import os
import re
import shutil
import tkinter as tk
import subprocess
from tkinter import filedialog, messagebox, ttk

# CONFIGURATION
# ---------------------------------------------------------
RESOLUTIONS = {
    "1080p (1920x1080)": (1920, 1080),
    "1440p (2560x1440)": (2560, 1440),
    "4K (3840x2160)": (3840, 2160)
}

# PATCH PATTERNS
PATTERNS = [
    {"name": "Init Width", "regex": b'\xC7\x45.\x00\x05\x00\x00', "offset": 3, "type": "width"},
    {"name": "Init Height", "regex": b'\xC7\x45.\xD0\x02\x00\x00', "offset": 3, "type": "height"},
    {"name": "Getter Width", "regex": b'\xB8\x00\x05\x00\x00', "offset": 1, "type": "width"},
    {"name": "Getter Height", "regex": b'\xB8\xD0\x02\x00\x00', "offset": 1, "type": "height"}
]


class ResolutionPatcher:
    def __init__(self, root):
        self.root = root
        self.root.title("My Fairytale Patcher")
        self.root.geometry("540x550")
        self.root.resizable(False, False)

        # Style
        style = ttk.Style()
        style.configure("Header.TLabel", font=("Segoe UI", 12, "bold"))
        style.configure("Bold.TCheckbutton", font=("Segoe UI", 9, "bold"))

        # Header
        ttk.Label(root, text="My Fairytale Resolution Patcher", style="Header.TLabel").pack(pady=15)

        # --- SECTION 1: Steamless (Unpacker) ---
        sl_frame = ttk.LabelFrame(root, text="1. Steamless Location", padding=10)
        sl_frame.pack(fill="x", padx=15, pady=5)

        self.sl_path_var = tk.StringVar()
        entry_sl = ttk.Entry(sl_frame, textvariable=self.sl_path_var)
        entry_sl.pack(side="left", fill="x", expand=True, padx=(0, 5))
        ttk.Button(sl_frame, text="Browse", command=self.browse_steamless).pack(side="right")

        # --- SECTION 2: Game File ---
        game_frame = ttk.LabelFrame(root, text="2. Game Executable", padding=10)
        game_frame.pack(fill="x", padx=15, pady=5)

        self.game_path_var = tk.StringVar()
        entry_game = ttk.Entry(game_frame, textvariable=self.game_path_var)
        entry_game.pack(side="left", fill="x", expand=True, padx=(0, 5))
        ttk.Button(game_frame, text="Browse", command=self.browse_game).pack(side="right")

        # --- SECTION 3: Resolution ---
        res_frame = ttk.LabelFrame(root, text="3. Target Resolution", padding=10)
        res_frame.pack(fill="x", padx=15, pady=5)

        self.res_var = tk.StringVar(value="1440p (2560x1440)")
        ttk.Combobox(res_frame, textvariable=self.res_var, values=list(RESOLUTIONS.keys()), state="readonly").pack(
            fill="x")

        # --- SECTION 4: Options ---
        opts_frame = ttk.LabelFrame(root, text="4. Options", padding=10)
        opts_frame.pack(fill="x", padx=15, pady=5)

        self.replace_var = tk.BooleanVar(value=False)
        self.backup_var = tk.BooleanVar(value=False)
        self.cleanup_var = tk.BooleanVar(value=True)

        # 1. Replace Checkbox (Triggers toggle logic)
        self.chk_replace = ttk.Checkbutton(
            opts_frame,
            text="Replace original file (Overwrite)",
            variable=self.replace_var,
            style="Bold.TCheckbutton",
            command=self.toggle_backup_state
        )
        self.chk_replace.pack(anchor="w", pady=(0, 5))

        # 2. Backup Checkbox (Disabled by default)
        self.chk_backup = ttk.Checkbutton(
            opts_frame,
            text="Backup original file (.bak)",
            variable=self.backup_var,
            state="disabled"
        )
        self.chk_backup.pack(anchor="w", padx=20)

        # 3. Cleanup Checkbox
        ttk.Checkbutton(
            opts_frame,
            text="Delete unpacked temp file (Cleanup)",
            variable=self.cleanup_var
        ).pack(anchor="w", pady=(5, 0))

        # --- ACTION BUTTON ---
        self.status_var = tk.StringVar(value="Ready")
        self.status_label = ttk.Label(root, textvariable=self.status_var, foreground="blue")
        self.status_label.pack(pady=(10, 0))

        btn_process = ttk.Button(root, text="PATCH GAME", command=self.start_process)
        btn_process.pack(pady=15, fill="x", padx=40, ipady=5)

        self.auto_detect()

    def toggle_backup_state(self):
        """Enable/Disable backup option based on Replace selection"""
        if self.replace_var.get():
            self.chk_backup.configure(state="normal")
            self.backup_var.set(True)  # Auto-check backup when replacing
        else:
            self.chk_backup.configure(state="disabled")
            self.backup_var.set(False)  # Uncheck backup when not replacing

    def auto_detect(self):
        if os.path.exists("Steamless.CLI.exe"):
            self.sl_path_var.set(os.path.abspath("Steamless.CLI.exe"))
            self.status_var.set("Steamless detected (Root).")
            return

        subfolder_path = os.path.join("Steamless", "Steamless.CLI.exe")
        if os.path.exists(subfolder_path):
            self.sl_path_var.set(os.path.abspath(subfolder_path))
            self.status_var.set("Steamless detected (Subfolder).")
            return

    def browse_steamless(self):
        f = filedialog.askopenfilename(filetypes=[("Steamless CLI", "Steamless.CLI.exe"), ("Exe", "*.exe")])
        if f: self.sl_path_var.set(f)

    def browse_game(self):
        f = filedialog.askopenfilename(filetypes=[("Executable", "*.exe")])
        if f: self.game_path_var.set(f)

    def start_process(self):
        game_path = self.game_path_var.get()
        sl_path = self.sl_path_var.get()

        if not game_path or not os.path.exists(game_path):
            messagebox.showerror("Error", "Please select the game executable.")
            return

        # ---------------------------
        # STEP 1: UNPACKING LOGIC
        # ---------------------------
        target_file = game_path
        unpacked_created = False

        if sl_path and os.path.exists(sl_path) and ".unpacked" not in game_path:
            self.status_var.set("Unpacking with Steamless...")
            self.root.update()

            try:
                sl_dir = os.path.dirname(sl_path)
                subprocess.run([sl_path, game_path], cwd=sl_dir, check=True, creationflags=subprocess.CREATE_NO_WINDOW)

                expected_output = game_path + ".unpacked.exe"
                if os.path.exists(expected_output):
                    target_file = expected_output
                    unpacked_created = True
                else:
                    messagebox.showwarning("Warning",
                                           "Steamless finished but output not found.\nPatching original file (might fail).")

            except Exception as e:
                messagebox.showerror("Steamless Error", f"Failed to run Steamless.\n{str(e)}")
                return

        # ---------------------------
        # STEP 2: PATCHING LOGIC
        # ---------------------------
        success, msg = self.patch_file(target_file, game_path)

        # ---------------------------
        # STEP 3: CLEANUP
        # ---------------------------
        if success:
            if unpacked_created and self.cleanup_var.get():
                try:
                    os.remove(target_file)
                except:
                    pass
            self.status_var.set("Success!")
            messagebox.showinfo("Success", msg)
        else:
            self.status_var.set("Failed.")

    def patch_file(self, input_file, original_game_path):
        res_name = self.res_var.get()
        w, h = RESOLUTIONS[res_name]

        self.status_var.set(f"Patching to {res_name}...")
        self.root.update()

        try:
            with open(input_file, "rb") as f:
                data = f.read()

            patched_data = bytearray(data)
            count = 0

            for p in PATTERNS:
                for m in re.finditer(p["regex"], data, re.DOTALL):
                    off = m.start() + p["offset"]
                    val = struct.pack('<I', w if p["type"] == "width" else h)
                    patched_data[off:off + 4] = val
                    count += 1

            if count == 0:
                messagebox.showerror("Failure", "No resolution patterns found.")
                return False, ""

            # ---------------------------
            # SAVE & BACKUP LOGIC
            # ---------------------------

            # If replacing original
            if self.replace_var.get():
                output_filename = original_game_path

                # Perform Backup ONLY if Replace is ON and Backup is ON
                if self.backup_var.get():
                    backup_path = original_game_path + ".bak"
                    if not os.path.exists(backup_path):
                        shutil.copy2(original_game_path, backup_path)

            # If NOT replacing original
            else:
                folder = os.path.dirname(original_game_path)
                base = os.path.basename(original_game_path).replace(".unpacked", "").replace(".exe", "")
                output_filename = os.path.join(folder, f"{base}_{w}x{h}.exe")

            with open(output_filename, "wb") as out:
                out.write(patched_data)

            return True, f"Patched {count} locations!\n\nFile saved as:\n{os.path.basename(output_filename)}"

        except Exception as e:
            messagebox.showerror("Error", f"Patch error: {str(e)}")
            return False, ""


if __name__ == "__main__":
    root = tk.Tk()
    ResolutionPatcher(root)
    root.mainloop()