"""Interactive preliminary isolated-pad-footing design per ACI 318-19 (US customary units).

Run:
    py -m pip install -r requirements.txt
    py pad_footing_dashboard.py

The final command starts Streamlit automatically.  It also works when launched
explicitly with ``py -m streamlit run pad_footing_dashboard.py``.

IMPORTANT: This is a transparent preliminary-design aid, not a sealed design.
It assumes a concentrically supported, nonprestressed, normalweight concrete footing,
uniform soil reaction for strength checks, no uplift, and no load combination generation.
The engineer of record must verify geotechnical bearing/load basis, development, detailing,
settlement, stability, seismic requirements, and all project-specific ACI provisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, sqrt
from typing import Dict, List, Tuple
import subprocess
import sys
from pathlib import Path
from shutil import copyfile

import pandas as pd
import plotly.graph_objects as go
import streamlit as st


# Common US bar data: nominal diameter (in.) and area (in2).
BAR_DATA: Dict[str, Tuple[float, float]] = {
    "#5": (0.625, 0.31), "#6": (0.750, 0.44), "#7": (0.875, 0.60),
    "#8": (1.000, 0.79), "#9": (1.128, 1.00), "#10": (1.270, 1.27),
}

PHI_FLEXURE = 0.90  # ACI 318-19 Table 21.2.2, tension-controlled sections.
PHI_SHEAR = 0.75   # ACI 318-19 Table 21.2.1, shear.
LAMBDA = 1.0       # Normalweight concrete, ACI 318-19 §19.2.4.


@dataclass(frozen=True)
class FootingInputs:
    pu: float       # Factored axial load, kips (compression positive)
    mx: float       # Factored moment about x, kip-ft
    my: float       # Factored moment about y, kip-ft
    qa: float       # User-supplied bearing limit, ksf; same force basis as Pu/M
    cx: float       # Column dimension parallel to footing x, inches
    cy: float       # Column dimension parallel to footing y, inches
    fc: float       # Concrete compressive strength, psi
    fy: float       # Reinforcement yield strength, psi
    cover: float    # Bottom/side cover against soil, inches
    aspect: float = 1.0  # Footing length / width


def soil_pressures(inp: FootingInputs, length_ft: float, width_ft: float) -> Tuple[float, float]:
    """Return maximum/minimum corner contact stress (ksf) for biaxial P-M.

    Linear elastic bearing distribution; q = P/A ± 6Mx/(B L²) ± 6My/(L B²).
    Soil bearing itself is governed by the geotechnical report, not ACI 318.
    """
    q0 = inp.pu / (length_ft * width_ft)
    q_mx = 6.0 * inp.mx / (width_ft * length_ft**2)
    q_my = 6.0 * inp.my / (length_ft * width_ft**2)
    return q0 + abs(q_mx) + abs(q_my), q0 - abs(q_mx) - abs(q_my)


def select_plan_dimensions(inp: FootingInputs, increment_ft: float = 0.25) -> Tuple[float, float, float, float]:
    """Find the smallest rectangular plan satisfying qmax ≤ qa and qmin ≥ 0."""
    if inp.pu <= 0 or inp.qa <= 0:
        raise ValueError("Axial compression and bearing limit must both be positive.")
    area_guess = max(inp.pu / inp.qa, 1.0)
    width = max(3.0, sqrt(area_guess / inp.aspect))
    while width <= 40.0:
        length = ceil((inp.aspect * width) / increment_ft) * increment_ft
        qmax, qmin = soil_pressures(inp, length, width)
        if qmax <= inp.qa and qmin >= 0:
            return length, width, qmax, qmin
        width += increment_ft
    raise ValueError("No practical plan found within the 40-ft search limit.")


def required_steel(mu_kipft: float, strip_width_in: float, d_in: float,
                   fc_psi: float, fy_psi: float) -> float:
    """Solve phi*Mn >= Mu by bisection for a singly reinforced rectangular strip.

    ACI 318-19 §22.3 flexural strength: a=As*fy/(0.85*fc*b), Mn=As*fy*(d-a/2).
    """
    mu = max(mu_kipft, 0.0) * 12_000.0
    if mu == 0:
        return 0.0
    lo, hi = 0.0, 0.85 * fc_psi * strip_width_in * 0.75 * d_in / fy_psi
    for _ in range(80):
        steel = (lo + hi) / 2
        a = steel * fy_psi / (0.85 * fc_psi * strip_width_in)
        phi_mn = PHI_FLEXURE * steel * fy_psi * (d_in - a / 2)
        if phi_mn < mu:
            lo = steel
        else:
            hi = steel
    return hi


def choose_bars(as_required: float, strip_width_in: float, h_in: float,
                cover_in: float) -> Dict[str, float | str | bool]:
    """Choose practical bottom bars; checks clear spacing and a conservative 18-in maximum.

    The minimum ratio used is the Grade-60 slab/shrinkage value 0.0018. Confirm
    applicability and any footing-specific distribution/detailing provisions for the project.
    """
    as_min = 0.0018 * strip_width_in * h_in
    demand = max(as_required, as_min)
    for name, (dia, area) in BAR_DATA.items():
        usable = strip_width_in - 2 * (cover_in + dia / 2)
        max_spacing = min(18.0, 3.0 * h_in)
        count = max(2, ceil(usable / max_spacing) + 1, ceil(demand / area))
        spacing = usable / (count - 1)
        clear = spacing - dia
        if clear >= max(dia, 1.0):  # ACI Ch. 25 clear-spacing concept; verify aggregate rule.
            return {"bar": name, "diameter": dia, "count": count, "spacing": spacing,
                    "as_provided": count * area, "as_required": demand,
                    "as_min": as_min, "spacing_ok": spacing <= max_spacing}
    raise ValueError("Required reinforcement exceeds the available bar-selection range.")


def one_way_shear(inp: FootingInputs, length_ft: float, width_ft: float, d_in: float,
                  q_design: float) -> List[Dict[str, float | str | bool]]:
    """One-way shear at d from column face; ACI 318-19 §22.5 and §13.3."""
    results = []
    # Moment about x makes pressure vary along length; use qmax conservatively for both strips.
    for direction, footing_dim, column_dim, strip_width in (
        ("x direction", length_ft * 12, inp.cx, width_ft * 12),
        ("y direction", width_ft * 12, inp.cy, length_ft * 12),
    ):
        projection = (footing_dim - column_dim) / 2
        vu = q_design / 144.0 * strip_width * max(projection - d_in, 0.0) / 1000.0
        vc = 2.0 * LAMBDA * sqrt(inp.fc) * strip_width * d_in / 1000.0
        phi_vc = PHI_SHEAR * vc
        results.append({"check": f"One-way shear, {direction}", "Vu (kip)": vu,
                        "phi Vc (kip)": phi_vc, "D/C": vu / phi_vc if phi_vc else 9e9,
                        "Pass": vu <= phi_vc})
    return results


def punching_shear(inp: FootingInputs, length_ft: float, width_ft: float, d_in: float,
                   q_design: float) -> Dict[str, float | str | bool]:
    """Interior-column two-way shear at perimeter d/2 from column face.

    ACI 318-19 §22.6.5.2: Vc is the least of the beta, alpha_s, and 4sqrt(fc) expressions.
    alpha_s=40 for an interior column. This tool does not address edge/corner columns.
    """
    bo = 2.0 * (inp.cx + inp.cy + 2.0 * d_in)
    beta = max(inp.cx, inp.cy) / min(inp.cx, inp.cy)
    vc_psi = min(4.0, 2.0 + 4.0 / beta, 2.0 + 40.0 * d_in / bo) * LAMBDA * sqrt(inp.fc)
    phi_vc = PHI_SHEAR * vc_psi * bo * d_in / 1000.0
    footing_area = length_ft * width_ft * 144.0
    area_inside = (inp.cx + d_in) * (inp.cy + d_in)
    vu = q_design / 144.0 * max(footing_area - area_inside, 0.0) / 1000.0
    return {"check": "Two-way (punching) shear", "Vu (kip)": vu, "phi Vc (kip)": phi_vc,
            "D/C": vu / phi_vc if phi_vc else 9e9, "Pass": vu <= phi_vc,
            "bo (in)": bo}


def design_footing(inp: FootingInputs) -> Dict:
    """Size plan and depth, design bottom steel in both directions, return transparent checks."""
    length, width, qmax, qmin = select_plan_dimensions(inp)
    # Iterate 2-in depth increments.  Use a #8 trial bar for a conservative effective-depth search.
    for h in range(12, 73, 2):
        d = h - inp.cover - BAR_DATA["#8"][0] / 2
        if d <= 0:
            continue
        shear = one_way_shear(inp, length, width, d, qmax)
        punch = punching_shear(inp, length, width, d, qmax)
        if all(row["Pass"] for row in shear) and punch["Pass"]:
            break
    else:
        raise ValueError("Shear design did not converge by 72 in thickness.")

    # Cantilever moments at column faces. qmax is intentionally conservative for biaxial loading.
    ax = (length * 12 - inp.cx) / 2
    ay = (width * 12 - inp.cy) / 2
    mux = qmax / 144.0 * (width * 12) * ax**2 / 2 / 12.0
    muy = qmax / 144.0 * (length * 12) * ay**2 / 2 / 12.0
    # Bars running x resist the x-direction cantilever; bars running y resist y-direction cantilever.
    as_x = required_steel(mux, width * 12, d, inp.fc, inp.fy)
    as_y = required_steel(muy, length * 12, d, inp.fc, inp.fy)
    bars_x = choose_bars(as_x, width * 12, h, inp.cover)
    bars_y = choose_bars(as_y, length * 12, h, inp.cover)

    # Recheck d using the selected bottom bar; report selected-bar demand checks.
    return {"length_ft": length, "width_ft": width, "thickness_in": h, "d_in": d,
            "qmax": qmax, "qmin": qmin, "mu_x": mux, "mu_y": muy,
            "bars_x": bars_x, "bars_y": bars_y,
            "checks": shear + [punch],
            "bearing_pass": qmax <= inp.qa and qmin >= 0}


def footing_figure(inp: FootingInputs, dsgn: Dict) -> go.Figure:
    """Plotly 3-D geometry: footing, column, and two bottom bar mats."""
    L, W, H = dsgn["length_ft"] * 12, dsgn["width_ft"] * 12, dsgn["thickness_in"]
    cx, cy = inp.cx, inp.cy
    fig = go.Figure()

    def block(x0, x1, y0, y1, z0, z1, color, name, opacity):
        x = [x0,x1,x1,x0,x0,x1,x1,x0]; y = [y0,y0,y1,y1,y0,y0,y1,y1]; z = [z0,z0,z0,z0,z1,z1,z1,z1]
        faces = [[0,1,2],[0,2,3],[4,5,6],[4,6,7],[0,1,5],[0,5,4],[1,2,6],[1,6,5],[2,3,7],[2,7,6],[3,0,4],[3,4,7]]
        fig.add_trace(go.Mesh3d(x=x, y=y, z=z, i=[f[0] for f in faces], j=[f[1] for f in faces],
                                k=[f[2] for f in faces], color=color, opacity=opacity, name=name))

    block(-L/2, L/2, -W/2, W/2, -H, 0, "#9ecae1", "Footing", 0.55)
    block(-cx/2, cx/2, -cy/2, cy/2, 0, min(1.5 * max(cx, cy), 72), "#6b7280", "Column", 0.75)
    z = -H + inp.cover
    for label, bars, along_x in (("X reinforcement", dsgn["bars_x"], True),
                                 ("Y reinforcement", dsgn["bars_y"], False)):
        n, s = int(bars["count"]), float(bars["spacing"])
        transverse = W if along_x else L
        positions = [-(n-1)*s/2 + i*s for i in range(n)]
        for i, pos in enumerate(positions):
            if along_x:
                xx, yy = [-L/2 + inp.cover, L/2 - inp.cover], [pos, pos]
            else:
                xx, yy = [pos, pos], [-W/2 + inp.cover, W/2 - inp.cover]
            fig.add_trace(go.Scatter3d(x=xx, y=yy, z=[z, z], mode="lines",
                          line=dict(color="#b45309" if along_x else "#047857", width=5),
                          name=label, legendgroup=label, showlegend=i == 0, hoverinfo="skip"))
    fig.update_layout(height=610, margin=dict(l=0, r=0, b=0, t=25),
        scene=dict(xaxis_title="x (in)", yaxis_title="y (in)", zaxis_title="z (in)",
                   aspectmode="data", camera=dict(eye=dict(x=1.5, y=-1.5, z=0.9))))
    return fig


def main() -> None:
    st.set_page_config(page_title="ACI 318-19 Pad Footing", layout="wide")
    st.title("ACI 318-19 Preliminary Pad Footing Designer")
    st.caption("US customary units. Enter factored P-M actions and a bearing cap on the same force basis.")
    with st.sidebar:
        st.header("Design inputs")
        pu = st.number_input("Factored axial load Pu (kip)", min_value=1.0, value=500.0, step=10.0)
        mx = st.number_input("Factored Mx (kip-ft)", value=0.0, step=10.0)
        my = st.number_input("Factored My (kip-ft)", value=0.0, step=10.0)
        qa = st.number_input("Bearing limit qa (ksf)", min_value=0.1, value=4.0, step=0.1)
        st.divider(); st.subheader("Column and material")
        cx = st.number_input("Column x dimension (in)", min_value=6.0, value=18.0)
        cy = st.number_input("Column y dimension (in)", min_value=6.0, value=18.0)
        fc = st.number_input("Concrete f'c (psi)", min_value=2500.0, value=4000.0, step=500.0)
        fy = st.number_input("Steel fy (psi)", min_value=40000.0, value=60000.0, step=5000.0)
        cover = st.number_input("Concrete cover (in)", min_value=2.0, value=3.0, step=0.25)
        aspect = st.number_input("Plan aspect ratio L / B", min_value=0.5, value=1.0, step=0.05)
    inp = FootingInputs(pu, mx, my, qa, cx, cy, fc, fy, cover, aspect)
    try:
        dsgn = design_footing(inp)
    except (ValueError, ZeroDivisionError) as err:
        st.error(f"Design cannot be completed: {err}")
        return
    st.subheader("Selected footing")
    a, b, c, e = st.columns(4)
    a.metric("Length", f"{dsgn['length_ft']:.2f} ft")
    b.metric("Width", f"{dsgn['width_ft']:.2f} ft")
    c.metric("Thickness", f"{dsgn['thickness_in']:.0f} in")
    e.metric("Effective depth (trial)", f"{dsgn['d_in']:.1f} in")
    st.write(f"**Bottom bars running x:** {dsgn['bars_x']['count']} {dsgn['bars_x']['bar']} @ "
             f"{dsgn['bars_x']['spacing']:.1f} in c/c  |  "
             f"**Bottom bars running y:** {dsgn['bars_y']['count']} {dsgn['bars_y']['bar']} @ "
             f"{dsgn['bars_y']['spacing']:.1f} in c/c")
    checks = [{"Check": "Soil bearing / no uplift", "Demand": dsgn["qmax"], "Capacity": qa,
               "D/C": dsgn["qmax"] / qa, "Pass": dsgn["bearing_pass"]}] + [
        {"Check": r["check"], "Demand": r["Vu (kip)"], "Capacity": r["phi Vc (kip)"],
         "D/C": r["D/C"], "Pass": r["Pass"]} for r in dsgn["checks"]]
    st.subheader("Code and design checks")
    st.dataframe(pd.DataFrame(checks).style.format({"Demand": "{:.1f}", "Capacity": "{:.1f}", "D/C": "{:.2f}"}), use_container_width=True)
    st.info("Flexural demands: Mux = {:.1f} kip-ft; Muy = {:.1f} kip-ft.  Steel shown includes a 0.0018 minimum ratio assumption.".format(dsgn["mu_x"], dsgn["mu_y"]))
    st.plotly_chart(footing_figure(inp, dsgn), use_container_width=True)
    st.caption("ACI references embedded in functions: Ch. 13 foundations; §22.3 flexure; §22.5 one-way shear; §22.6.5.2 punching shear; Ch. 25 detailing. Verify against your adopted ACI 318-19 edition and project amendments.")


if __name__ == "__main__":
    # A Streamlit script normally needs ``streamlit run``.  This small launcher
    # lets a user double-click/run the .py file as well, without recursively
    # launching a second server once Streamlit evaluates the script.
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        inside_streamlit = get_script_run_ctx() is not None
    except (ImportError, AttributeError):
        inside_streamlit = False
    if inside_streamlit:
        main()
    else:
        # Streamlit's extension check is case-sensitive: it accepts ``.py`` but
        # rejects ``.PY``.  If Windows supplied an uppercase suffix, run a
        # lower-case copy placed beside the original source file.
        source = Path(__file__).resolve()
        streamlit_source = source
        if source.suffix != ".py":
            streamlit_source = source.with_name(f"{source.stem}_streamlit.py")
            copyfile(source, streamlit_source)
        subprocess.run([sys.executable, "-m", "streamlit", "run", str(streamlit_source)], check=False)

