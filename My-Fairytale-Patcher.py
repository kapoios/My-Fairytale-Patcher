import struct
import os
import re
import shutil
import tkinter as tk
import subprocess
from tkinter import filedialog, messagebox, ttk, scrolledtext

# CONFIGURATION
# ---------------------------------------------------------
RESOLUTIONS = {
    "1080p (1920x1080)": (1920, 1080),
    "1440p (2560x1440)": (2560, 1440),
    "4K (3840x2160)": (3840, 2160)
}

# PATCH PATTERNS
PATTERNS = [
    # Main Executable Resolution
    {"name": "main engine Width (Stack)", "regex": b'\xC7\x45.\x00\x05\x00\x00', "offset": 3, "type": "width"},
    {"name": "main engine Height (Stack)", "regex": b'\xC7\x45.\xD0\x02\x00\x00', "offset": 3, "type": "height"},
    {"name": "main engine Width (EAX)", "regex": b'\xB8\x00\x05\x00\x00', "offset": 1, "type": "width"},
    {"name": "main engine Height (EAX)", "regex": b'\xB8\xD0\x02\x00\x00', "offset": 1, "type": "height"},
    # Internal Render Scale (Fixes Water PIP effect)
    {"name": "internal render scale (W, H)", "regex": b'\x00\x00\xA0\x44\x00\x00\x34\x44', "type": "raw_float_pair"},
    # UI Canvas (Fixes UI Coordinate System)
    {"name": "UI canvas", "regex": b'\x00\x05\x00\x00\xD0\x02\x00\x00', "type": "ui_canvas"},
    # UI Double Height (The 64-bit 720.0 found in scan)
    {"name": "UI scaling double", "regex": b'\x00\x00\x00\x00\x00\x80\x86\x40', "type": "double_height"}
]


class ResolutionPatcher:
    def __init__(self, root):
        self.root = root
        self.root.title("My Fairytale Patcher")
        self.root.geometry("540x550")
        self.root.resizable(False, False)

        # UI Styling
        style = ttk.Style()
        style.configure("Header.TLabel", font=("Segoe UI", 12, "bold"))
        ttk.Label(root, text="My Fairytale Resolution Patcher", style="Header.TLabel").pack(pady=15)

        # Paths
        sl_frame = ttk.LabelFrame(root, text="1. Steamless Location", padding=10)
        sl_frame.pack(fill="x", padx=15, pady=5)
        self.sl_path_var = tk.StringVar()
        ttk.Entry(sl_frame, textvariable=self.sl_path_var).pack(side="left", fill="x", expand=True, padx=(0, 5))
        ttk.Button(sl_frame, text="Browse", command=self.browse_steamless).pack(side="right")

        game_frame = ttk.LabelFrame(root, text="2. Game Executable", padding=10)
        game_frame.pack(fill="x", padx=15, pady=5)
        self.game_path_var = tk.StringVar()
        ttk.Entry(game_frame, textvariable=self.game_path_var).pack(side="left", fill="x", expand=True, padx=(0, 5))
        ttk.Button(game_frame, text="Browse", command=self.browse_game).pack(side="right")

        res_frame = ttk.LabelFrame(root, text="3. Target Resolution", padding=10)
        res_frame.pack(fill="x", padx=15, pady=5)
        self.res_var = tk.StringVar(value="4K (3840x2160)")
        ttk.Combobox(res_frame, textvariable=self.res_var, values=list(RESOLUTIONS.keys()), state="readonly").pack(
            fill="x")

        # Options
        opts_frame = ttk.LabelFrame(root, text="4. Options", padding=10)
        opts_frame.pack(fill="x", padx=15, pady=5)
        self.replace_var = tk.BooleanVar(value=True)
        self.backup_var = tk.BooleanVar(value=True)
        self.cleanup_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(opts_frame, text="Replace original file", variable=self.replace_var,
                        command=self.toggle_backup_state).pack(anchor="w")
        self.chk_backup = ttk.Checkbutton(opts_frame, text="Backup original (.bak)", variable=self.backup_var,
                                          state="normal")
        self.chk_backup.pack(anchor="w", padx=20)
        ttk.Checkbutton(opts_frame, text="Delete unpacked temp file", variable=self.cleanup_var).pack(anchor="w")

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(root, textvariable=self.status_var, foreground="blue").pack(pady=(10, 0))
        ttk.Button(root, text="PATCH GAME", command=self.start_process).pack(pady=15, fill="x", padx=40, ipady=5)
        self.auto_detect()

    def toggle_backup_state(self):
        if self.replace_var.get():
            self.chk_backup.configure(state="normal")
            self.backup_var.set(True)
        else:
            self.chk_backup.configure(state="disabled")
            self.backup_var.set(False)

    def auto_detect(self):
        for path in ["Steamless.CLI.exe", os.path.join("Steamless", "Steamless.CLI.exe")]:
            if os.path.exists(path):
                self.sl_path_var.set(os.path.abspath(path))
                break

    def browse_steamless(self):
        f = filedialog.askopenfilename(filetypes=[("Steamless CLI", "Steamless.CLI.exe")])
        if f: self.sl_path_var.set(f)

    def browse_game(self):
        f = filedialog.askopenfilename(filetypes=[("Executable", "*.exe")])
        if f: self.game_path_var.set(f)

    def start_process(self):
        game_path = self.game_path_var.get()
        sl_path = self.sl_path_var.get()
        if not game_path or not os.path.exists(game_path): return

        target_file = game_path
        unpacked_created = False

        if sl_path and os.path.exists(sl_path) and ".unpacked" not in game_path:
            self.status_var.set("Unpacking...")
            self.root.update()
            try:
                subprocess.run([sl_path, game_path], cwd=os.path.dirname(sl_path), check=True,
                               creationflags=subprocess.CREATE_NO_WINDOW)
                if os.path.exists(game_path + ".unpacked.exe"):
                    target_file = game_path + ".unpacked.exe"
                    unpacked_created = True
            except:
                pass

        success, log = self.patch_file(target_file, game_path)
        if success:
            if unpacked_created and self.cleanup_var.get(): os.remove(target_file)
            self.status_var.set("Success!")
            self.show_log_window(log)

    def patch_file(self, input_file, original_game_path):
        w, h = RESOLUTIONS[self.res_var.get()]
        try:
            with open(input_file, "rb") as f:
                data = f.read()
            patched_data = bytearray(data)
            count = 0
            patch_log = []

            for p in PATTERNS:
                for m in re.finditer(p["regex"], data, re.DOTALL):
                    start = m.start()

                    if p["type"] == "raw_float_pair":
                        patched_data[start:start + 4] = struct.pack('<f', float(w))
                        patched_data[start + 4:start + 8] = struct.pack('<f', float(h))
                        patch_log.append(f"[{p['name']}] 0x{start:08X}")

                    elif p["type"] == "ui_canvas":
                        patched_data[start:start + 4] = struct.pack('<I', w)
                        patched_data[start + 4:start + 8] = struct.pack('<I', h)
                        patch_log.append(f"[{p['name']}] 0x{start:08X}")

                    elif p["type"] == "float_bias":
                        # We change -1.0 to -3.0 (Sharper) or 0.0 to -3.0
                        # Try setting it to a very sharp negative value
                        new_bias = -3.0
                        if len(m.group(0)) == 8:  # Double
                            val = struct.pack('<d', new_bias)
                        else:  # Float
                            val = struct.pack('<f', new_bias)

                        patched_data[start:start + len(val)] = val
                        patch_log.append(f"[{p['name']}] 0x{start:08X} | Set to {new_bias}")

                    elif p["type"] == "double_height":
                        patched_data[start:start + 8] = struct.pack('<d', float(h))
                        patch_log.append(f"[{p['name']}] 0x{start:08X}")

                    else:
                        off = start + p.get("offset", 0)
                        val = struct.pack('<I', w) if p["type"] == "width" else struct.pack('<I', h)
                        patched_data[off:off + 4] = val
                        patch_log.append(f"[{p['name']}] 0x{off:08X}")

                    count += 1

            if count == 0: return False, ""

            output_filename = original_game_path if self.replace_var.get() else original_game_path.replace(".exe",
                                                                                                           f"_{w}x{h}.exe")
            if self.backup_var.get() and not os.path.exists(original_game_path + ".bak"):
                shutil.copy2(original_game_path, original_game_path + ".bak")

            with open(output_filename, "wb") as out:
                out.write(patched_data)
            return True, "\n".join(patch_log)
        except Exception as e:
            messagebox.showerror("Error", str(e))
            return False, ""

    def show_log_window(self, log_text):
        top = tk.Toplevel(self.root)
        top.title("Patch Log")
        txt = scrolledtext.ScrolledText(top, width=50, height=15)
        txt.pack(padx=10, pady=10)
        txt.insert(tk.END, log_text)
        txt.configure(state='disabled')


if __name__ == "__main__":
    root = tk.Tk()
    ResolutionPatcher(root)
    root.mainloop()