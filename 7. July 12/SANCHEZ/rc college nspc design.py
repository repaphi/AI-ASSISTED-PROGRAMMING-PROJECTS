"""first run at the script making, i think the summary is wrong though since it's not reflecting the answers in the book LMAO


Preliminary reinforced-concrete beam design, SI units.

Basis: NSCP 2015 (7th ed.), Vol. 1, Ch. 4 structural-concrete provisions
(ACI 318-14 based) and Sec. 203 strength-load combinations.  This program
implements the gravity combination 1.2D + 1.6L only.  It is for a normalweight,
non-prestressed, singly reinforced, simply supported rectangular beam; it is
not a substitute for a signed design or for seismic/special-moment-frame
detailing, development length, deflection, torsion, openings, or other loads.

Inputs: metres for span; mm for section/cover; MPa (N/mm2) for strengths;
kN/m for the *superimposed* dead and live line loads.  Beam self-weight is
added automatically using 24 kN/m3.
"""
from dataclasses import dataclass
from math import cos, radians, sin, sqrt
import tkinter as tk
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText

ES = 200_000.0                 # MPa, modulus of reinforcing steel
GAMMA_CONCRETE = 24.0          # kN/m3, normalweight concrete
PHI_FLEXURE = 0.90             # tension-controlled flexure
PHI_SHEAR = 0.75               # shear
BAR_AREAS = {10: 78.5, 12: 113.1, 16: 201.1, 20: 314.2, 25: 490.9, 28: 615.8, 32: 804.2}


@dataclass
class BeamInput:
    span_m: float
    width_mm: float
    depth_mm: float
    fc_mpa: float
    fy_mpa: float
    live_load_kn_m: float
    dead_load_kn_m: float       # superimposed dead load; self-weight added below
    cover_mm: float             # clear cover to outside of closed stirrup


def beta1(fc: float) -> float:
    """NSCP Ch. 4 / ACI rectangular stress-block factor beta_1."""
    return max(0.65, 0.85 - 0.05 * max(fc - 28.0, 0.0) / 7.0)


def factored_loads(x: BeamInput) -> dict:
    """NSCP concrete strength combination 1.2D + 1.6L (gravity only)."""
    self_weight = GAMMA_CONCRETE * (x.width_mm / 1000) * (x.depth_mm / 1000)
    dead_total = x.dead_load_kn_m + self_weight
    wu = 1.2 * dead_total + 1.6 * x.live_load_kn_m
    return {"self_weight": self_weight, "dead_total": dead_total, "wu": wu}


def demand_actions(wu_kn_m: float, span_m: float) -> dict:
    """Elastic actions for a uniformly loaded, simply supported beam."""
    return {"mu_kn_m": wu_kn_m * span_m**2 / 8.0,
            "vu_kn": wu_kn_m * span_m / 2.0}


def reinforcement_limits(b: float, d: float, fc: float, fy: float) -> dict:
    """NSCP/ACI minimum As and 0.75*rho_balanced maximum As."""
    as_min = max(0.25 * sqrt(fc) / fy * b * d, 1.4 / fy * b * d)
    rho_bal = 0.85 * beta1(fc) * fc / fy * (0.003 / (0.003 + fy / ES))
    as_max = 0.75 * rho_bal * b * d
    return {"as_min": as_min, "as_max": as_max, "rho_bal": rho_bal}


def required_steel_area(mu_kn_m: float, b: float, d: float, fc: float, fy: float) -> float:
    """Solve phi*Mn >= Mu, with Mn=As*fy*(d-a/2), a=As*fy/(0.85fc*b)."""
    mn_required = mu_kn_m * 1e6 / PHI_FLEXURE  # N-mm
    radical = d**2 - 2.0 * mn_required / (0.85 * fc * b)
    if radical <= 0:
        raise ValueError("Section is too small for a singly reinforced rectangular design.")
    a = d - sqrt(radical)
    return 0.85 * fc * b * a / fy


def nominal_moment(as_mm2: float, b: float, d: float, fc: float, fy: float) -> dict:
    """Return a, Mn and phi*Mn for a yielded tension-steel rectangular section."""
    a = as_mm2 * fy / (0.85 * fc * b)
    mn_kn_m = as_mm2 * fy * (d - a / 2.0) / 1e6
    return {"a": a, "mn": mn_kn_m, "phi_mn": PHI_FLEXURE * mn_kn_m}


def choose_longitudinal_bars(x: BeamInput, mu_kn_m: float, stirrup_db: int = 10) -> dict:
    """Try customary bar sizes and select the least over-provided one-layer arrangement."""
    options = []
    core_width = x.width_mm - 2 * (x.cover_mm + stirrup_db)
    for db, area_one in BAR_AREAS.items():
        d = x.depth_mm - x.cover_mm - stirrup_db - db / 2.0
        if d <= 0:
            continue
        limits = reinforcement_limits(x.width_mm, d, x.fc_mpa, x.fy_mpa)
        as_calc = required_steel_area(mu_kn_m, x.width_mm, d, x.fc_mpa, x.fy_mpa)
        as_required = max(as_calc, limits["as_min"])
        # Conservative clear horizontal spacing: max(25 mm, db), aggregate-size check remains user responsibility.
        clear = max(25.0, float(db))
        for n in range(2, 9):
            as_provided = n * area_one
            fits = n * db + (n - 1) * clear <= core_width + 1e-9
            if fits and as_provided >= as_required and as_provided <= limits["as_max"]:
                cap = nominal_moment(as_provided, x.width_mm, d, x.fc_mpa, x.fy_mpa)
                if cap["phi_mn"] >= mu_kn_m:
                    options.append({"n": n, "db": db, "as_provided": as_provided,
                                    "as_required": as_required, "as_calc": as_calc, "d": d,
                                    "limits": limits, "capacity": cap, "clear": clear})
    if not options:
        raise ValueError("No one-layer bar arrangement satisfies flexure, spacing, and As limits; revise the beam section.")
    return min(options, key=lambda o: (o["as_provided"] - o["as_required"], o["n"], -o["db"]))


def stirrup_design(x: BeamInput, vu_kn: float, d: float, stirrup_db: int = 10) -> dict:
    """NSCP/ACI concrete shear, minimum ties, and vertical two-leg closed-stirrup spacing."""
    b, fc, fy = x.width_mm, x.fc_mpa, x.fy_mpa
    vc_kn = 0.17 * sqrt(fc) * b * d / 1000.0  # lambda=1.0 normalweight concrete
    vs_required_kn = max(0.0, vu_kn / PHI_SHEAR - vc_kn)
    vn_limit_kn = 0.66 * sqrt(fc) * b * d / 1000.0
    if vu_kn > PHI_SHEAR * vn_limit_kn:
        raise ValueError("Vu exceeds the code maximum shear strength for this section; enlarge beam or redesign.")

    av = 2.0 * BAR_AREAS[stirrup_db]  # two-leg closed tie
    av_over_s_min = max(0.062 * sqrt(fc) * b / fy, 0.35 * b / fy)
    s_by_min = av / av_over_s_min
    s_by_strength = float("inf") if vs_required_kn == 0 else av * fy * d / (vs_required_kn * 1000.0)
    s_max = min(d / 2.0, 600.0)       # vertical stirrups, ordinary beam
    s = min(s_by_strength, s_by_min, s_max)
    s = max(25.0, 5.0 * int(s // 5.0))  # round down to a practical 5-mm increment
    if s < 25:
        raise ValueError("Required stirrup spacing is impractically small; enlarge beam/use larger stirrups.")
    min_required = vu_kn > 0.5 * PHI_SHEAR * vc_kn
    vs_provided_kn = av * fy * d / (s * 1000.0)
    return {"db": stirrup_db, "av": av, "vc": vc_kn, "vs_required": vs_required_kn,
            "vs_provided": vs_provided_kn, "s": s, "s_max": s_max, "s_by_min": s_by_min,
            "min_required": min_required, "phi_vn": PHI_SHEAR * (vc_kn + vs_provided_kn)}


def design_beam(x: BeamInput) -> dict:
    """Run load, actions, flexure, longitudinal-bar selection, and shear design."""
    if min(x.span_m, x.width_mm, x.depth_mm, x.fc_mpa, x.fy_mpa, x.live_load_kn_m,
           x.dead_load_kn_m, x.cover_mm) <= 0:
        raise ValueError("All input values must be positive.")
    loads = factored_loads(x)
    actions = demand_actions(loads["wu"], x.span_m)
    bars = choose_longitudinal_bars(x, actions["mu_kn_m"])
    shear = stirrup_design(x, actions["vu_kn"], bars["d"])
    return {"input": x, "loads": loads, "actions": actions, "bars": bars, "shear": shear}


def report(r: dict) -> str:
    """Create a clear, print-ready calculation report."""
    x, l, a, b, s = r["input"], r["loads"], r["actions"], r["bars"], r["shear"]
    flex_ok = b["capacity"]["phi_mn"] >= a["mu_kn_m"] and b["as_provided"] <= b["limits"]["as_max"]
    shear_ok = s["phi_vn"] >= a["vu_kn"]
    return f"""
NSCP 2015 GRAVITY RC BEAM DESIGN — PRELIMINARY REPORT
Assumptions: simply supported rectangular beam; normalweight concrete; uniformly distributed gravity load;
1.2D + 1.6L only; no seismic, wind, torsion, deflection, development, or detailing design.

1. INPUTS (SI)
   Span L = {x.span_m:.3f} m; width b = {x.width_mm:.0f} mm; overall depth h = {x.depth_mm:.0f} mm
   f'c = {x.fc_mpa:.1f} MPa; fy = {x.fy_mpa:.1f} MPa; clear cover = {x.cover_mm:.0f} mm
   Superimposed DL = {x.dead_load_kn_m:.3f} kN/m; LL = {x.live_load_kn_m:.3f} kN/m

2. FACTORED LOADS (NSCP Sec. 203 / Ch. 4): Wu = 1.2D + 1.6L
   Beam self-weight = 24(b)(h) = {l['self_weight']:.3f} kN/m
   Total D = {l['dead_total']:.3f} kN/m; Wu = {l['wu']:.3f} kN/m

3. DEMAND (uniform load, simple span)
   Mu = WuL^2/8 = {a['mu_kn_m']:.3f} kN-m
   Vu = WuL/2 = {a['vu_kn']:.3f} kN

4. FLEXURE (NSCP Ch. 4 rectangular stress block; phi = {PHI_FLEXURE:.2f})
   Effective depth d = {b['d']:.1f} mm
   As(calc) = {b['as_calc']:.1f} mm²; As,min = {b['limits']['as_min']:.1f} mm²
   As,required = max[As(calc), As,min] = {b['as_required']:.1f} mm²
   As,max = 0.75 rho_bal bd = {b['limits']['as_max']:.1f} mm²
   Provide {b['n']} - {b['db']} mm bottom bars: As,provided = {b['as_provided']:.1f} mm²
   Clear bar spacing provided/check basis = {b['clear']:.0f} mm minimum
   a = {b['capacity']['a']:.1f} mm; phiMn = {b['capacity']['phi_mn']:.3f} kN-m

5. SHEAR (NSCP Ch. 4; Vc = 0.17*sqrt(f'c)*bwd; phi = {PHI_SHEAR:.2f})
   Vc = {s['vc']:.3f} kN; Vs,required = {s['vs_required']:.3f} kN
   Provide 2-legged {s['db']} mm closed stirrups (Av = {s['av']:.1f} mm²) @ {s['s']:.0f} mm c/c
   Vs,provided = {s['vs_provided']:.3f} kN; s,max = {s['s_max']:.1f} mm; phi(Vc+Vs) = {s['phi_vn']:.3f} kN
   Minimum shear reinforcement required by Vu > 0.5phiVc: {'YES' if s['min_required'] else 'NO (ties still recommended for cage integrity)'}

SUMMARY REPORT
   Beam span: {x.span_m:.3f} m | Section: {x.width_mm:.0f} mm wide x {x.depth_mm:.0f} mm deep
   Materials: f'c = {x.fc_mpa:.1f} MPa | fy = {x.fy_mpa:.1f} MPa
   Longitudinal reinforcement: {b['n']} - {b['db']} mm bottom bars (As = {b['as_provided']:.1f} mm²)
   Stirrups: 2-legged {s['db']} mm closed stirrups @ {s['s']:.0f} mm c/c
   NSCP gravity flexure check: {'PASS' if flex_ok else 'FAIL'} | shear check: {'PASS' if shear_ok else 'FAIL'}
   Final design must be reviewed by the Engineer of Record and checked against the licensed NSCP text.
""".strip()


class BeamDesignerApp(tk.Tk):
    """Desktop interface plus a mouse-rotatable, schematic 3D reinforcement view."""
    FIELDS = (("Beam span length", "span_m", "m"), ("Beam width", "width_mm", "mm"),
              ("Beam overall depth", "depth_mm", "mm"), ("Concrete strength f'c", "fc_mpa", "MPa"),
              ("Steel yield strength fy", "fy_mpa", "MPa"), ("Live load", "live_load_kn_m", "kN/m"),
              ("Superimposed dead load", "dead_load_kn_m", "kN/m"), ("Clear cover", "cover_mm", "mm"))

    def __init__(self):
        super().__init__()
        self.title("NSCP RC Beam Designer - Preliminary")
        self.geometry("1180x760"); self.minsize(980, 640)
        self.entries, self.result, self.drag = {}, None, None
        self.yaw, self.pitch = -28, 18
        self.build(); self.placeholder()

    def build(self):
        base = ttk.Frame(self, padding=12); base.pack(fill="both", expand=True)
        base.columnconfigure(1, weight=1); base.rowconfigure(0, weight=1)
        form = ttk.LabelFrame(base, text="Beam Inputs (all required)", padding=10)
        form.grid(row=0, column=0, sticky="nsw", padx=(0, 10))
        for row, (label, key, unit) in enumerate(self.FIELDS):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", pady=3)
            self.entries[key] = ttk.Entry(form, width=14)
            self.entries[key].grid(row=row, column=1, padx=4, pady=3)
            ttk.Label(form, text=unit).grid(row=row, column=2, sticky="w")
        ttk.Label(form, text="Dead load excludes beam self-weight.", wraplength=230).grid(row=8, column=0, columnspan=3, sticky="w", pady=(8, 3))
        ttk.Button(form, text="Calculate and Visualize", command=self.calculate).grid(row=9, column=0, columnspan=3, sticky="ew", pady=3)
        ttk.Button(form, text="Clear", command=self.clear).grid(row=10, column=0, columnspan=3, sticky="ew")
        right = ttk.Frame(base); right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1); right.rowconfigure(0, weight=3); right.rowconfigure(1, weight=2)
        view = ttk.LabelFrame(right, text="3D Reinforcement View - drag to rotate", padding=6)
        view.grid(row=0, column=0, sticky="nsew"); view.columnconfigure(0, weight=1); view.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(view, background="#f4f4f4", highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.canvas.bind("<Configure>", lambda event: self.draw())
        self.canvas.bind("<ButtonPress-1>", lambda event: setattr(self, "drag", (event.x, event.y)))
        self.canvas.bind("<B1-Motion>", self.rotate)
        out = ttk.LabelFrame(right, text="Calculation Results", padding=6)
        out.grid(row=1, column=0, sticky="nsew", pady=(10, 0)); out.columnconfigure(0, weight=1); out.rowconfigure(0, weight=1)
        self.output = ScrolledText(out, wrap="word", font=("Consolas", 9), height=18)
        self.output.grid(row=0, column=0, sticky="nsew"); self.output.configure(state="disabled")

    def read_inputs(self):
        try:
            values = {key: float(self.entries[key].get()) for _, key, _ in self.FIELDS}
        except ValueError:
            raise ValueError("Enter a valid number in every field.")
        return BeamInput(**values)

    def calculate(self):
        try:
            self.result = design_beam(self.read_inputs())
        except ValueError as error:
            messagebox.showerror("Input or design error", str(error)); return
        self.output.configure(state="normal"); self.output.delete("1.0", "end")
        self.output.insert("1.0", report(self.result)); self.output.configure(state="disabled")
        self.draw()

    def clear(self):
        for entry in self.entries.values(): entry.delete(0, "end")
        self.result = None; self.output.configure(state="normal"); self.output.delete("1.0", "end"); self.output.configure(state="disabled"); self.placeholder()

    def rotate(self, event):
        if self.drag:
            self.yaw += (event.x - self.drag[0]) * .45
            self.pitch = max(-65, min(65, self.pitch + (event.y - self.drag[1]) * .35))
            self.drag = (event.x, event.y); self.draw()

    def placeholder(self):
        self.canvas.delete("all")
        self.canvas.create_text(max(1, self.canvas.winfo_width()) / 2, max(1, self.canvas.winfo_height()) / 2,
                                text="Enter beam parameters, then select Calculate and Visualize", fill="#555555")

    def project(self, x, y, z, scale, cx, cy):
        yaw, pitch = radians(self.yaw), radians(self.pitch)
        xr, yr = x * cos(yaw) - y * sin(yaw), x * sin(yaw) + y * cos(yaw)
        return cx + scale * xr, cy - scale * (z * cos(pitch) + yr * sin(pitch))

    def draw(self):
        if not self.result:
            self.placeholder(); return
        self.canvas.delete("all")
        width, height = max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height())
        x, bars, shear = self.result["input"], self.result["bars"], self.result["shear"]
        length, beam_width, beam_depth = x.span_m * 1000, x.width_mm, x.depth_mm
        scale = min(width / (length * 1.35 + beam_width * 1.6), height / (beam_depth * 2.0 + beam_width * 1.8))
        cx, cy = width * .50, height * .56
        p = lambda xx, yy, zz: self.project(xx - length / 2, yy - beam_width / 2, zz - beam_depth / 2, scale, cx, cy)
        c = {(xx, yy, zz): p(xx, yy, zz) for xx in (0, length) for yy in (0, beam_width) for zz in (0, beam_depth)}
        def polygon(points, **args): self.canvas.create_polygon([item for point in points for item in point], **args)
        def line(points, **args): self.canvas.create_line([item for point in points for item in point], **args)
        polygon([c[(0,0,0)],c[(length,0,0)],c[(length,0,beam_depth)],c[(0,0,beam_depth)]], fill="#d6d6d6", outline="#666666")
        polygon([c[(length,0,0)],c[(length,beam_width,0)],c[(length,beam_width,beam_depth)],c[(length,0,beam_depth)]], fill="#bdbdbd", outline="#666666")
        polygon([c[(0,0,beam_depth)],c[(length,0,beam_depth)],c[(length,beam_width,beam_depth)],c[(0,beam_width,beam_depth)]], fill="#e6e6e6", outline="#666666")
        cover, stirrup_db = x.cover_mm, shear["db"]
        n_stirrups = min(24, max(4, int(length / shear["s"]) + 1))
        for i in range(n_stirrups):
            xx = 60 + i * (length - 120) / (n_stirrups - 1)
            line([p(xx,cover,cover),p(xx,beam_width-cover,cover),p(xx,beam_width-cover,beam_depth-cover),p(xx,cover,beam_depth-cover),p(xx,cover,cover)], fill="#2468b0", width=2)
        count, db, z = bars["n"], bars["db"], cover + stirrup_db + bars["db"] / 2
        ys = [beam_width / 2] if count == 1 else [cover + stirrup_db + db / 2 + i * (beam_width - 2 * (cover + stirrup_db + db / 2)) / (count - 1) for i in range(count)]
        for yy in ys:
            line([p(0,yy,z),p(length,yy,z)], fill="#b22c2c", width=max(2, int(db * scale)))
            ex, ey = p(length,yy,z); radius = max(3, db * scale / 2)
            self.canvas.create_oval(ex-radius, ey-radius, ex+radius, ey+radius, fill="#b22c2c", outline="#702020")
        self.canvas.create_text(10, 10, anchor="nw", text=f"Red: {count}-{db} mm bottom bars | Blue: 2-leg {stirrup_db} mm stirrups @ {shear['s']:.0f} mm", fill="#222222")


if __name__ == "__main__":
    BeamDesignerApp().mainloop()
