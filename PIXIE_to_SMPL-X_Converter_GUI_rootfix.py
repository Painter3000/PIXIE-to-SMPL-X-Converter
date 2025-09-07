# PIXIE_to_SMPL-X_Converter_GUI_rootfix.py
# ---------------------------------------
# Für Blender-SMPL-X-Add-on:
#  - KEIN per-Bone-Koordinatenflip mehr
#  - Optional NUR Root (global_orient) um 180° um X (und optional Z) drehen
#    -> behebt "Kopfstand", ohne lokale Posen zu verfälschen.

from tkinter import ttk, filedialog, scrolledtext, messagebox
import tkinter as tk
import pickle, os, numpy as np
from scipy.spatial.transform import Rotation

try:
    from mathutils import Matrix
    HAS_MATHUTILS = True
except Exception:
    HAS_MATHUTILS = False


class PixieToSMPLXConverter:
    def __init__(self, root):
        self.root = root
        self.root.title("PIXIE → SMPL-X (Root-Fix)")
        self.root.geometry("900x700")

        # --- State
        self.root_fix_x_var = tk.BooleanVar(value=True)   # 180° um X auf Root
        self.root_fix_z_var = tk.BooleanVar(value=False)  # optional 180° um Z
        self.input_file_var = tk.StringVar()
        self.output_file_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Bereit – wähle eine PIXIE PKL-Datei")
        self.loaded_data = None

        # --- Layout
        main = ttk.Frame(root, padding=10); main.grid(sticky="nsew")
        root.columnconfigure(0, weight=1); root.rowconfigure(0, weight=1)
        main.columnconfigure(1, weight=1); main.rowconfigure(4, weight=1)

        ttk.Label(main, text="PIXIE PKL-Datei:").grid(row=0, column=0, sticky="w")
        f_in = ttk.Frame(main); f_in.grid(row=0, column=1, sticky="ew"); f_in.columnconfigure(0, weight=1)
        ttk.Entry(f_in, textvariable=self.input_file_var, state="readonly").grid(row=0, column=0, sticky="ew", padx=(0,5))
        ttk.Button(f_in, text="Durchsuchen", command=self.browse_input).grid(row=0, column=1)

        ttk.Label(main, text="SMPL-X Output:").grid(row=1, column=0, sticky="w", pady=5)
        f_out = ttk.Frame(main); f_out.grid(row=1, column=1, sticky="ew", pady=5); f_out.columnconfigure(0, weight=1)
        ttk.Entry(f_out, textvariable=self.output_file_var).grid(row=0, column=0, sticky="ew", padx=(0,5))
        ttk.Button(f_out, text="Speichern unter", command=self.browse_output).grid(row=0, column=1)

        box = ttk.LabelFrame(main, text="Optionen", padding=8); box.grid(row=2, column=0, columnspan=2, sticky="ew", pady=5)
        ttk.Checkbutton(box, text="Nur Root (global_orient) um 180° um X drehen", variable=self.root_fix_x_var)\
            .grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(box, text="Zusätzlich 180° um Z (optional)", variable=self.root_fix_z_var)\
            .grid(row=1, column=0, sticky="w")
        ttk.Label(box, text="Hinweis: Keine per-Bone-Konvertierung – das Add-on erledigt den Raumwechsel.", font=("TkDefaultFont",8))\
            .grid(row=2, column=0, sticky="w", pady=(4,0))

        btns = ttk.Frame(main); btns.grid(row=3, column=0, columnspan=2, pady=8)
        ttk.Button(btns, text="Inspizieren", command=self.inspect).grid(row=0, column=0, padx=4)
        ttk.Button(btns, text="Konvertieren", command=self.convert).grid(row=0, column=1, padx=4)
        ttk.Button(btns, text="Beide", command=self.inspect_and_convert).grid(row=0, column=2, padx=4)

        ttk.Label(main, text="Ausgabe:").grid(row=4, column=0, sticky=("w","n"))
        self.out = scrolledtext.ScrolledText(main, width=90, height=30, font=("Consolas",9))
        self.out.grid(row=4, column=1, sticky="nsew", pady=(0,5))

        ttk.Label(main, textvariable=self.status_var, relief=tk.SUNKEN, anchor="w")\
            .grid(row=5, column=0, columnspan=2, sticky="ew")

    # --- UI helpers
    def log(self, s): self.out.insert(tk.END, s+"\n"); self.out.see(tk.END); self.root.update()
    def clear(self): self.out.delete("1.0", tk.END)

    def browse_input(self):
        fn = filedialog.askopenfilename(title="PIXIE PKL-Datei", filetypes=[("Pickle","*.pkl"), ("Alle Dateien","*.*")])
        if fn:
            self.input_file_var.set(fn)
            base,_ = os.path.splitext(fn)
            self.output_file_var.set(base+"_smplx.pkl")
            self.status_var.set(f"Input: {os.path.basename(fn)}")

    def browse_output(self):
        fn = filedialog.asksaveasfilename(title="SMPL-X speichern unter", defaultextension=".pkl",
                                          filetypes=[("Pickle","*.pkl"), ("Alle Dateien","*.*")])
        if fn: self.output_file_var.set(fn)

    # --- IO
    @staticmethod
    def _robust_load(path):
        with open(path,"rb") as f:
            try: return pickle.load(f)
            except Exception:
                f.seek(0); return pickle.load(f, encoding="latin1")

    # --- Inspect
    def inspect(self):
        inp = self.input_file_var.get()
        if not inp:
            messagebox.showwarning("Warnung","Bitte zuerst eine Input-Datei auswählen."); return
        self.clear()
        try:
            d = self._robust_load(inp); self.loaded_data = d
        except Exception as e:
            self.log(f"[FEHLER] Laden: {e}"); return

        self.log("=== PIXIE PKL Inspektion ===")
        self.log(f"Datei: {os.path.basename(inp)}")
        try: self.log(f"Größe: {os.path.getsize(inp)} Bytes")
        except: pass
        self.log(f"Keys: {sorted(list(d.keys()))}")

        def shp(k): 
            try: return np.asarray(d[k]).shape
            except: return None

        self.log("\n=== Kernfelder ===")
        for k in ["global_pose","global_orient","body_pose","left_hand_pose","right_hand_pose",
                  "jaw_pose","betas","expression","shape","exp","transl","body_cam"]:
            if k in d: self.log(f"{k:16s} -> {shp(k)}")
            else:      self.log(f"{k:16s} -> [NICHT GEFUNDEN]")

        if "global_pose" in d:
            gp = np.asarray(d["global_pose"]).squeeze()
            if gp.shape[-2:] == (3,3):
                self.log("[OK] global_pose ist 3x3")
                if HAS_MATHUTILS:
                    try:
                        q = Matrix(gp.reshape(3,3).tolist()).to_quaternion()
                        self.log(f"[Sanity] |angle|={np.degrees(q.angle):.1f}°, axis=({q.axis.x:.3f},{q.axis.y:.3f},{q.axis.z:.3f})")
                    except Exception as e:
                        self.log(f"[WARN] Quaternion: {e}")
        elif "global_orient" in d:
            go = np.asarray(d["global_orient"]).reshape(-1)
            self.log(f"[OK] global_orient len={go.size}")

    # --- Convert core
    @staticmethod
    def _to_rotvec_block(x):
        """Akzeptiert 3x3 oder rotvec; liefert rotvec (3,)"""
        arr = np.asarray(x)
        if arr.shape[-2:] == (3,3):
            return Rotation.from_matrix(arr.reshape(3,3)).as_rotvec()
        return arr.reshape(3)

    def _compose_root_fix(self, rotvec):
        """Links-multipliziere Fix-Rotation(en) auf den Root."""
        R = Rotation.from_rotvec(rotvec.reshape(3))
        if self.root_fix_x_var.get():
            R = Rotation.from_rotvec([np.pi,0,0]) * R
        if self.root_fix_z_var.get():
            R = Rotation.from_rotvec([0,0,np.pi]) * R
        return R.as_rotvec()

    def convert(self):
        inp = self.input_file_var.get()
        outp = self.output_file_var.get()
        if not inp:
            messagebox.showwarning("Warnung","Bitte Input-Datei wählen."); return
        if not outp:
            messagebox.showwarning("Warnung","Bitte Output-Pfad angeben."); return

        if self.loaded_data is None:
            try: self.loaded_data = self._robust_load(inp)
            except Exception as e:
                messagebox.showerror("Fehler", f"Laden fehlgeschlagen: {e}"); return

        d = self.loaded_data
        self.log("\n=== Konvertierung PIXIE → SMPL-X (Add-on) ===")
        self.log("[INFO] Per-Bone-Flip: AUS  |  Root X180: %s  |  Root Z180: %s" %
                 (self.root_fix_x_var.get(), self.root_fix_z_var.get()))

        smplx = {}

        # --- global_orient
        if "global_pose" in d:
            go = self._to_rotvec_block(d["global_pose"])
            self.log("[✓] global_pose → rotvec")
        elif "global_orient" in d:
            go = self._to_rotvec_block(d["global_orient"])
            self.log("[✓] global_orient übernommen")
        else:
            go = np.zeros(3); self.log("[+] global_orient Default (0,0,0)")

        go_fixed = self._compose_root_fix(go)
        smplx["global_orient"] = go_fixed.reshape(1,3)

        # --- body_pose
        if "body_pose" in d:
            bp = np.asarray(d["body_pose"])
            if bp.shape == (21,3,3):
                rv = Rotation.from_matrix(bp).as_rotvec().reshape(1,-1)
                self.log(f"[✓] body_pose 21x3x3 → (1,{rv.shape[1]})")
            else:
                rv = bp.reshape(1,-1)
                self.log(f"[✓] body_pose Axis-Angle → (1,{rv.shape[1]})")
            smplx["body_pose"] = rv
        else:
            smplx["body_pose"] = np.zeros((1,63)); self.log("[+] body_pose Default (1,63)")

        # --- hands
        for side in ["left","right"]:
            key = f"{side}_hand_pose"
            if key in d:
                hp = np.asarray(d[key])
                if hp.shape == (15,3,3): rv = Rotation.from_matrix(hp).as_rotvec().reshape(1,-1)
                else:                    rv = hp.reshape(1,-1)
                self.log(f"[✓] {key} → (1,{rv.shape[1]})")
                smplx[key] = rv
            else:
                smplx[key] = np.zeros((1,45)); self.log(f"[+] {key} Default (1,45)")

        # --- jaw
        if "jaw_pose" in d:
            smplx["jaw_pose"] = self._to_rotvec_block(d["jaw_pose"]).reshape(1,3); self.log("[✓] jaw_pose")
        else:
            smplx["jaw_pose"] = np.zeros((1,3)); self.log("[+] jaw_pose Default")

        # --- shape / expression
        if "shape" in d:
            smplx["betas"] = np.asarray(d["shape"]).reshape(1,-1); self.log(f"[✓] shape→betas (1,{smplx['betas'].shape[1]})")
        elif "betas" in d:
            smplx["betas"] = np.asarray(d["betas"]).reshape(1,-1); self.log(f"[✓] betas (1,{smplx['betas'].shape[1]})")
        else:
            smplx["betas"] = np.zeros((1,10)); self.log("[+] betas Default (1,10)")

        if "exp" in d:
            smplx["expression"] = np.asarray(d["exp"]).reshape(1,-1); self.log(f"[✓] exp→expression (1,{smplx['expression'].shape[1]})")
        elif "expression" in d:
            smplx["expression"] = np.asarray(d["expression"]).reshape(1,-1); self.log(f"[✓] expression (1,{smplx['expression'].shape[1]})")
        else:
            smplx["expression"] = np.zeros((1,50)); self.log("[+] expression Default (1,50)")

        # --- transl (so lassen – Add-on setzt Szene-Pos separat)
        if "transl" in d:
            smplx["transl"] = np.asarray(d["transl"]).reshape(1,3); self.log("[✓] transl übernommen")
        else:
            smplx["transl"] = np.zeros((1,3)); self.log("[+] transl Default (0,0,0)")

        # --- schreiben
        try:
            out_final = self.output_file_var.get()
            base, ext = os.path.splitext(out_final)
            tag = "_rootX180" if self.root_fix_x_var.get() else "_nofix"
            if self.root_fix_z_var.get(): tag += "_Z180"
            out_final = base + tag + ext

            with open(out_final,"wb") as f:
                pickle.dump(smplx, f)
            self.log("\n[SUCCESS] SMPL-X gespeichert: " + out_final)
            self.status_var.set("Konvertierung erfolgreich")
        except Exception as e:
            self.log(f"[FEHLER] Speichern: {e}")
            messagebox.showerror("Fehler", str(e))

    def inspect_and_convert(self):
        self.clear(); self.inspect()
        if self.loaded_data is not None:
            self.convert()


def main():
    root = tk.Tk()
    app = PixieToSMPLXConverter(root)
    root.mainloop()

if __name__ == "__main__":
    main()

