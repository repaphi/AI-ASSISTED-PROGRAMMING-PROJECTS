"""
Footing Studio — preliminary isolated-footing study and OpenSTAAD exporter.

This is an educational, preliminary-design tool.  It is not a substitute for
review by a licensed structural/geotechnical engineer or for the full NSCP
requirements applicable to a project.

Install optional dependencies before running:
    py -m pip install pywin32 matplotlib

For OpenSTAAD export:
  1. Start STAAD.Pro and open the target .std model.
  2. Set that model's working units to metres before exporting.
  3. Enter unused node/plate IDs in this program.

The OpenSTAAD calls use _FlagAsMethod because some STAAD COM methods are
reported as properties by pywin32.  Without it Python can raise:
    TypeError: 'int' object is not callable
"""

from __future__ import annotations

import math
import textwrap
import tkinter as tk
from dataclasses import dataclass
from tkinter import filedialog, messagebox, scrolledtext, ttk


# ---------------------------------------------------------------------------
# Engineering calculation model
# ---------------------------------------------------------------------------

@dataclass
class FootingInput:
    lot_area: float                 # m² — retained as a planning input
    column_load: float              # kN, service axial load used for sizing
    moisture_content: float         # percent
    liquid_limit: float             # percent
    plastic_limit: float            # percent
    allowable_bearing: float        # kPa = kN/m², already includes geotechnical FS
    geotechnical_fs: float          # reported only; do not divide q_allow again
    column_x: float                 # m
    column_z: float                 # m
    footing_depth: float            # m
    concrete_strength: float        # MPa
    steel_yield: float              # MPa
    cover: float                    # m
    bar_diameter: float             # mm


@dataclass
class FootingResult:
    design_load: float
    required_area: float
    footing_x: float
    footing_z: float
    area_provided: float
    bearing_pressure: float
    effective_depth_mm: float
    one_way_demand: float
    one_way_capacity: float
    punching_demand: float
    punching_capacity: float
    required_steel_mm2_per_m: float
    suggested_spacing_mm: float
    plasticity_index: float
    warnings: list[str]


def calculate_footing(data: FootingInput) -> FootingResult:
    """Perform transparent, conservative preliminary calculations.

    Design basis: q_allow is an allowable/service bearing pressure.  A 10%
    allowance is added to column load for preliminary footing self-weight and
    soil cover.  Shear expressions are simplified one-way and punching checks
    based on common NSCP/ACI-style concrete strength format; verify the exact
    NSCP edition, load combinations, factors, and detailing with the engineer.
    """
    if data.allowable_bearing <= 0 or data.column_load <= 0:
        raise ValueError("Column load and allowable bearing capacity must be greater than zero.")
    if min(data.column_x, data.column_z, data.footing_depth, data.concrete_strength,
           data.steel_yield, data.bar_diameter) <= 0:
        raise ValueError("Column dimensions, depth, material strengths, and bar size must be greater than zero.")
    if data.cover < 0:
        raise ValueError("Concrete cover cannot be negative.")

    warnings: list[str] = []
    # q_allow usually already has the geotechnical factor of safety embedded.
    # Applying it again is a frequent and unnecessarily conservative error.
    design_load = 1.10 * data.column_load
    required_area = design_load / data.allowable_bearing
    side = math.ceil(math.sqrt(required_area) / 0.05) * 0.05  # practical 50 mm rounding
    footing_x = footing_z = side
    area_provided = footing_x * footing_z
    q = design_load / area_provided

    d_mm = data.footing_depth * 1000 - data.cover * 1000 - data.bar_diameter / 2
    if d_mm <= 0:
        raise ValueError("Effective depth is zero or negative. Increase footing depth or reduce cover/bar size.")
    d_m = d_mm / 1000

    # Preliminary one-way shear at a distance d from the column face.
    # For a square footing, assess the more severe direction.
    cantilever_x = (footing_x - data.column_x) / 2
    cantilever_z = (footing_z - data.column_z) / 2
    if min(cantilever_x, cantilever_z) <= 0:
        raise ValueError("The footing must be wider than the column in both plan directions.")
    one_way_demand_x = q * footing_z * max(cantilever_x - d_m, 0.0)
    one_way_demand_z = q * footing_x * max(cantilever_z - d_m, 0.0)
    one_way_demand = max(one_way_demand_x, one_way_demand_z)
    critical_width_mm = footing_z * 1000 if one_way_demand_x >= one_way_demand_z else footing_x * 1000
    phi = 0.75
    one_way_capacity = phi * 0.17 * math.sqrt(data.concrete_strength) * critical_width_mm * d_mm / 1000

    # Preliminary interior punching perimeter at d/2 from column faces.
    b0_mm = 2 * ((data.column_x * 1000 + d_mm) + (data.column_z * 1000 + d_mm))
    area_inside_m2 = (data.column_x + d_m) * (data.column_z + d_m)
    punching_demand = q * max(area_provided - area_inside_m2, 0.0)
    punching_capacity = phi * 0.33 * math.sqrt(data.concrete_strength) * b0_mm * d_mm / 1000

    # Flexure at column face for a 1 m strip. Moment is q*l²/2, kN·m per m.
    projection = max(cantilever_x, cantilever_z)
    mu_knm_per_m = q * projection ** 2 / 2
    fy = data.steel_yield
    # A simple lever-arm approximation z ≈ 0.9d.
    as_flexure = mu_knm_per_m * 1_000_000 / (0.90 * fy * d_mm)
    # Minimum shrinkage/temperature reinforcement reference value: 0.0018bh.
    as_min = 0.0018 * 1000 * (data.footing_depth * 1000)
    required_steel = max(as_flexure, as_min)
    bar_area = math.pi * data.bar_diameter ** 2 / 4
    spacing = math.floor((bar_area * 1000 / required_steel) / 10) * 10
    spacing = min(spacing, 300)  # common practical cap; project detailing rules govern
    spacing = max(spacing, 50)

    if one_way_demand > one_way_capacity:
        warnings.append("One-way shear does not pass in this preliminary check; increase depth or revise the footing.")
    if punching_demand > punching_capacity:
        warnings.append("Punching shear does not pass in this preliminary check; increase depth, add a pedestal, or redesign.")
    if data.liquid_limit <= data.plastic_limit:
        warnings.append("Liquid limit must be greater than plastic limit to interpret the plasticity index.")
    if area_provided > data.lot_area:
        warnings.append("The preliminary footing area is larger than the entered lot area.")
    if data.geotechnical_fs <= 0:
        warnings.append("Enter a positive geotechnical factor of safety for reporting.")

    return FootingResult(
        design_load=design_load, required_area=required_area,
        footing_x=footing_x, footing_z=footing_z, area_provided=area_provided,
        bearing_pressure=q, effective_depth_mm=d_mm,
        one_way_demand=one_way_demand, one_way_capacity=one_way_capacity,
        punching_demand=punching_demand, punching_capacity=punching_capacity,
        required_steel_mm2_per_m=required_steel, suggested_spacing_mm=spacing,
        plasticity_index=data.liquid_limit - data.plastic_limit,
        warnings=warnings,
    )


def make_explanation(data: FootingInput, r: FootingResult) -> str:
    """Return an offline, student-friendly explanation of the calculation."""
    one_way_status = "PASS" if r.one_way_demand <= r.one_way_capacity else "REVIEW REQUIRED"
    punch_status = "PASS" if r.punching_demand <= r.punching_capacity else "REVIEW REQUIRED"
    warning_text = "\n".join(f"• {w}" for w in r.warnings) or "• No automatic warnings were generated."
    return textwrap.dedent(f"""
        DESIGN BASIS — preliminary learning calculation
        ------------------------------------------------
        Input column service load: P = {data.column_load:,.2f} kN
        A 10% preliminary allowance represents the footing's self-weight and soil cover:
            P_design = 1.10 × P = {r.design_load:,.2f} kN

        1. GEOTECHNICAL SCREENING
        The supplied allowable bearing capacity is q_allow = {data.allowable_bearing:,.2f} kPa
        (1 kPa = 1 kN/m²). It should come from the geotechnical report and normally
        already includes the stated geotechnical factor of safety ({data.geotechnical_fs:g}).
        Do not divide q_allow by the factor of safety a second time unless the report
        expressly calls the number an ultimate capacity.

        Plasticity index: PI = LL − PL = {data.liquid_limit:.1f} − {data.plastic_limit:.1f}
                            = {r.plasticity_index:.1f}%
        Moisture content entered: {data.moisture_content:.1f}%
        These values help a geotechnical engineer judge soil behavior; they do not by
        themselves establish a safe bearing pressure.

        2. FOOTING PLAN SIZE
        Required area = P_design / q_allow
                      = {r.design_load:,.2f} / {data.allowable_bearing:,.2f}
                      = {r.required_area:.3f} m²
        A square plan is rounded up to the next 50 mm:
            footing = {r.footing_x:.2f} m × {r.footing_z:.2f} m
            area provided = {r.area_provided:.3f} m²
            service bearing pressure = P_design / A_provided = {r.bearing_pressure:.2f} kPa

        3. SHEAR SCREENING
        Effective depth d = overall depth − cover − bar diameter/2
                          = {r.effective_depth_mm:.0f} mm
        One-way shear is checked at distance d from the column face.
            Vu = {r.one_way_demand:.2f} kN;  φVc = {r.one_way_capacity:.2f} kN  → {one_way_status}
        Punching shear is checked around a perimeter at d/2 from the column face.
            Vu = {r.punching_demand:.2f} kN;  φVc = {r.punching_capacity:.2f} kN  → {punch_status}

        4. REINFORCEMENT STARTING POINT
        The program uses a simple 1 m strip cantilever model at the column face,
        then compares it with a minimum reinforcement estimate.
            Required steel ≥ {r.required_steel_mm2_per_m:.0f} mm²/m
            Starting layout: Ø{data.bar_diameter:.0f} bars @ {r.suggested_spacing_mm:.0f} mm each way
        This must still be checked for NSCP strength combinations, development length,
        cover, spacing, column load transfer, and all site-specific detailing.

        IMPORTANT LIMITS
        {warning_text}
        This program is for preliminary educational use. Obtain a geotechnical report
        and have the final NSCP footing design reviewed and signed by the responsible engineer.
    """).strip()


# ---------------------------------------------------------------------------
# OpenSTAAD export
# ---------------------------------------------------------------------------

def export_to_staad(r: FootingResult, node_start: int, plate_id: int) -> str:
    """Send a footing-outline plate to the open STAAD.Pro model.

    The key compatibility fix is _FlagAsMethod.  Some OpenSTAAD type-library
    entries appear as integer properties to pywin32, even though they are methods.
    """
    try:
        import win32com.client as win32
    except ImportError as exc:
        raise RuntimeError("pywin32 is not installed. Run: py -m pip install pywin32") from exc

    try:
        # GetActiveObject attaches to STAAD already open by the user.  Dispatch can
        # create a separate automation instance and is less suitable for this workflow.
        staad = win32.GetActiveObject("StaadPro.OpenSTAAD")
        geometry = staad.Geometry

        # Essential fix for 'int object is not callable' / 'bool object is not callable'.
        for method in ("SetSilentMode", "SaveModel"):
            staad._FlagAsMethod(method)
        for method in ("CreateNode", "CreatePlate"):
            geometry._FlagAsMethod(method)

        staad.SetSilentMode(1)

        n1, n2, n3, n4 = node_start, node_start + 1, node_start + 2, node_start + 3
        hx, hz = r.footing_x / 2, r.footing_z / 2

        # CreateNode(node_number, X, Y, Z). Existing model must use metre units.
        geometry.CreateNode(n1, -hx, 0.0, -hz)
        geometry.CreateNode(n2,  hx, 0.0, -hz)
        geometry.CreateNode(n3,  hx, 0.0,  hz)
        geometry.CreateNode(n4, -hx, 0.0,  hz)

        # CreatePlate(plate_number, NodeA, NodeB, NodeC, NodeD)
        # Passing a list here is incorrect for the OpenSTAAD COM method.
        geometry.CreatePlate(plate_id, n1, n2, n3, n4)
        staad.SaveModel(1)
        return (f"Export complete. Created plate {plate_id} with nodes "
                f"{n1}, {n2}, {n3}, {n4}. The active STAAD model was saved.")
    except Exception as exc:
        hint = (
            "Open STAAD.Pro with the target model active, confirm that the model uses metres, "
            "and use unused IDs. Python and STAAD.Pro must use the same 64-bit architecture."
        )
        raise RuntimeError(f"STAAD export failed: {exc}\n\n{hint}") from exc


# ---------------------------------------------------------------------------
# Dark-academia Tkinter interface
# ---------------------------------------------------------------------------

PALETTE = {
    "ink": "#17130F", "paper": "#EAD9B7", "paper_dim": "#CDB98D",
    "brown": "#34251C", "brown_2": "#4E3627", "gold": "#C69952",
    "gold_light": "#E3C277", "wine": "#7C3942", "sage": "#8D9A74",
    "cream": "#F6EAD0", "muted": "#B9A889",
}


class FootingStudio(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Footing Studio  |  Preliminary NSCP Study")
        self.geometry("1210x780")
        self.minsize(1050, 690)
        self.configure(bg=PALETTE["ink"])
        self.result: FootingResult | None = None
        self._make_style()
        self._make_layout()

    def _make_style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background=PALETTE["ink"])
        style.configure("Panel.TFrame", background=PALETTE["brown"])
        style.configure("TLabel", background=PALETTE["brown"], foreground=PALETTE["paper"])
        style.configure("Title.TLabel", background=PALETTE["ink"], foreground=PALETTE["gold_light"],
                        font=("Georgia", 24, "bold"))
        style.configure("Subtitle.TLabel", background=PALETTE["ink"], foreground=PALETTE["muted"],
                        font=("Georgia", 10, "italic"))
        style.configure("Section.TLabel", background=PALETTE["brown"], foreground=PALETTE["gold_light"],
                        font=("Georgia", 12, "bold"))
        style.configure("TEntry", fieldbackground=PALETTE["cream"], foreground=PALETTE["ink"],
                        insertcolor=PALETTE["ink"], padding=5)
        style.configure("Gold.TButton", background=PALETTE["gold"], foreground=PALETTE["ink"],
                        font=("Georgia", 10, "bold"), padding=(10, 7))
        style.map("Gold.TButton", background=[("active", PALETTE["gold_light"])])
        style.configure("Wine.TButton", background=PALETTE["wine"], foreground=PALETTE["cream"],
                        font=("Georgia", 10, "bold"), padding=(10, 7))
        style.map("Wine.TButton", background=[("active", "#98505B")])

    def _make_layout(self) -> None:
        header = ttk.Frame(self)
        header.pack(fill="x", padx=28, pady=(20, 12))
        ttk.Label(header, text="Footing Studio", style="Title.TLabel").pack(anchor="w")
        ttk.Label(header, text="A warm little desk for preliminary isolated-footing studies · NSCP review required",
                  style="Subtitle.TLabel").pack(anchor="w", pady=(2, 0))

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, padx=28, pady=(0, 24))
        body.columnconfigure(0, weight=0, minsize=340)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        left = ttk.Frame(body, style="Panel.TFrame", padding=18)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        right = ttk.Frame(body, style="Panel.TFrame", padding=18)
        right.grid(row=0, column=1, sticky="nsew")
        self._make_inputs(left)
        self._make_results(right)

    def _make_inputs(self, parent: ttk.Frame) -> None:
        self.vars: dict[str, tk.StringVar] = {}
        fields = [
            ("Site & soil", None, None),
            ("lot_area", "Lot area (m²)", "150"),
            ("column_load", "Column service load (kN)", "900"),
            ("moisture", "Moisture content (%)", "22"),
            ("liquid_limit", "Liquid limit, LL (%)", "45"),
            ("plastic_limit", "Plastic limit, PL (%)", "25"),
            ("bearing", "Allowable bearing (kPa)", "200"),
            ("fs", "Geotechnical factor of safety", "3"),
            ("Geometry & materials", None, None),
            ("column_x", "Column X size (m)", "0.40"),
            ("column_z", "Column Z size (m)", "0.40"),
            ("depth", "Footing thickness (m)", "0.50"),
            ("fc", "Concrete strength f'c (MPa)", "28"),
            ("fy", "Steel yield strength fy (MPa)", "415"),
            ("cover", "Bottom cover (m)", "0.075"),
            ("bar", "Bar diameter (mm)", "16"),
        ]
        row = 0
        for key, label, default in fields:
            if label is None:
                ttk.Label(parent, text=key, style="Section.TLabel").grid(
                    row=row, column=0, columnspan=2, sticky="w", pady=(8 if row else 0, 6))
                row += 1
                continue
            ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=3)
            var = tk.StringVar(value=default)
            self.vars[key] = var
            ttk.Entry(parent, textvariable=var, width=13).grid(row=row, column=1, sticky="e", pady=3)
            row += 1

        button_row = ttk.Frame(parent, style="Panel.TFrame")
        button_row.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(14, 4))
        ttk.Button(button_row, text="Calculate & explain", style="Gold.TButton", command=self.calculate).pack(
            side="left", expand=True, fill="x", padx=(0, 4))
        ttk.Button(button_row, text="3D preview", style="Wine.TButton", command=self.show_plot).pack(
            side="left", expand=True, fill="x", padx=(4, 0))

        ttk.Label(parent, text="STAAD.Pro export", style="Section.TLabel").grid(
            row=row + 1, column=0, columnspan=2, sticky="w", pady=(18, 6))
        self.node_id = tk.StringVar(value="9001")
        self.plate_id = tk.StringVar(value="9001")
        ttk.Label(parent, text="First unused node ID").grid(row=row + 2, column=0, sticky="w", pady=3)
        ttk.Entry(parent, textvariable=self.node_id, width=13).grid(row=row + 2, column=1, sticky="e", pady=3)
        ttk.Label(parent, text="Unused plate ID").grid(row=row + 3, column=0, sticky="w", pady=3)
        ttk.Entry(parent, textvariable=self.plate_id, width=13).grid(row=row + 3, column=1, sticky="e", pady=3)
        ttk.Button(parent, text="Export outline to STAAD", style="Wine.TButton", command=self.export).grid(
            row=row + 4, column=0, columnspan=2, sticky="ew", pady=(9, 0))

    def _make_results(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Notebook", style="Section.TLabel").pack(anchor="w", pady=(0, 8))
        self.output = scrolledtext.ScrolledText(
            parent, wrap="word", bg=PALETTE["paper"], fg=PALETTE["ink"],
            insertbackground=PALETTE["ink"], relief="flat", borderwidth=0,
            font=("Georgia", 10), padx=16, pady=14,
        )
        self.output.pack(fill="both", expand=True)
        self.output.insert("1.0", "Enter the site, column, and material values, then choose “Calculate & explain.”\n\n"
                          "The STAAD button sends a single plate footprint to the currently active STAAD.Pro model. "
                          "It is a rendering/export aid—not a full soil-supported analysis model.")
        self.output.configure(state="disabled")
        actions = ttk.Frame(parent, style="Panel.TFrame")
        actions.pack(fill="x", pady=(10, 0))
        ttk.Button(actions, text="Save notebook", style="Gold.TButton", command=self.save_notebook).pack(side="right")

    def _read_input(self) -> FootingInput:
        v = {key: float(item.get().strip()) for key, item in self.vars.items()}
        return FootingInput(
            lot_area=v["lot_area"], column_load=v["column_load"], moisture_content=v["moisture"],
            liquid_limit=v["liquid_limit"], plastic_limit=v["plastic_limit"],
            allowable_bearing=v["bearing"], geotechnical_fs=v["fs"], column_x=v["column_x"],
            column_z=v["column_z"], footing_depth=v["depth"], concrete_strength=v["fc"],
            steel_yield=v["fy"], cover=v["cover"], bar_diameter=v["bar"],
        )

    def _write_output(self, value: str) -> None:
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.insert("1.0", value)
        self.output.configure(state="disabled")

    def calculate(self) -> None:
        try:
            data = self._read_input()
            self.result = calculate_footing(data)
            self._write_output(make_explanation(data, self.result))
        except ValueError as exc:
            messagebox.showerror("Please review the inputs", str(exc), parent=self)

    def show_plot(self) -> None:
        if self.result is None:
            self.calculate()
            if self.result is None:
                return
        try:
            import matplotlib.pyplot as plt
            from mpl_toolkits.mplot3d.art3d import Poly3DCollection
        except ImportError:
            messagebox.showerror("Preview unavailable", "Install matplotlib first:\npy -m pip install matplotlib", parent=self)
            return
        data = self._read_input()
        r = self.result
        hx, hz = r.footing_x / 2, r.footing_z / 2
        y0, y1 = 0, data.footing_depth
        verts = [(-hx, -hz, y0), (hx, -hz, y0), (hx, hz, y0), (-hx, hz, y0)]
        top = [(x, z, y1) for x, z, _ in verts]
        faces = [verts, top,
                 [verts[0], verts[1], top[1], top[0]], [verts[1], verts[2], top[2], top[1]],
                 [verts[2], verts[3], top[3], top[2]], [verts[3], verts[0], top[0], top[3]]]
        fig = plt.figure("Footing Studio — 3D Preview", facecolor=PALETTE["ink"])
        ax = fig.add_subplot(111, projection="3d")
        ax.set_facecolor(PALETTE["brown"])
        ax.add_collection3d(Poly3DCollection(faces, facecolors=PALETTE["gold"], edgecolors=PALETTE["ink"], alpha=.72))
        cx, cz = data.column_x / 2, data.column_z / 2
        ax.bar3d(-cx, -cz, y1, data.column_x, data.column_z, data.footing_depth * .8,
                 color=PALETTE["wine"], alpha=.85, shade=True)
        ax.set_xlabel("X (m)", color=PALETTE["paper"]); ax.set_ylabel("Z (m)", color=PALETTE["paper"])
        ax.set_zlabel("Y (m)", color=PALETTE["paper"])
        ax.tick_params(colors=PALETTE["paper"])
        ax.set_title(f"{r.footing_x:.2f} m × {r.footing_z:.2f} m footing", color=PALETTE["gold_light"], pad=18)
        ax.set_box_aspect((r.footing_x, r.footing_z, max(data.footing_depth * 2, .5)))
        plt.show()

    def export(self) -> None:
        if self.result is None:
            self.calculate()
            if self.result is None:
                return
        try:
            node = int(self.node_id.get())
            plate = int(self.plate_id.get())
            if node <= 0 or plate <= 0:
                raise ValueError("Node and plate IDs must be positive whole numbers.")
            text = export_to_staad(self.result, node, plate)
            messagebox.showinfo("STAAD.Pro export", text, parent=self)
        except (ValueError, RuntimeError) as exc:
            messagebox.showerror("STAAD.Pro export", str(exc), parent=self)

    def save_notebook(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self, title="Save footing notebook", defaultextension=".txt",
            filetypes=[("Text file", "*.txt")], initialfile="footing_study.txt")
        if not path:
            return
        with open(path, "w", encoding="utf-8") as file:
            file.write(self.output.get("1.0", "end-1c"))
        messagebox.showinfo("Saved", f"Notebook saved to:\n{path}", parent=self)


if __name__ == "__main__":
    FootingStudio().mainloop()
