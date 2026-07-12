"""
================================================================================
 ISOLATED FOOTING DESIGN TUTOR - DESKTOP APP (Tkinter GUI)
 Based on NSCP 2015 (National Structural Code of the Philippines), which for
 reinforced-concrete design mirrors ACI 318-14 provisions.
================================================================================

WHAT CHANGED FROM THE COMMAND-LINE VERSION
-------------------------------------------
Same design engine (same formulas, same NSCP logic) as before, but now wrapped
in an actual app-style interface with TABS you click through instead of
typing answers to input() prompts one at a time:

    [ 1. Inputs ]  ->  [ 2. Theory ]  ->  [ 3. Results ]  ->  [ 4. Visualization ]  ->  [ 5. STAAD ]

You fill in the form on Tab 1, click "Run Design", and every other tab
populates automatically -- the theory explanation, the calculation log
(with every formula shown), the pass/fail summary, and the 2D/3D plots
rendered right inside the window (no separate pop-up plot window).

HOW TO RUN
----------
    python isolated_footing_design_gui.py

DEPENDENCIES
------------
    pip install matplotlib numpy
    (tkinter ships with standard Python on Windows/Mac; on some Linux distros
     you may need `sudo apt install python3-tk`)
    pip install pywin32          # ONLY for the STAAD.Pro tab, Windows only

DISCLAIMER
----------
This tool is written for LEARNING PURPOSES. It follows the general logic of
NSCP/ACI 318 footing design but is intentionally simplified (concentric,
mostly axial column loads on square/rectangular pad footings). Always have a
licensed structural engineer check real designs.
================================================================================
"""

import io
import math
import contextlib
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

import numpy as np
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401 (needed for 3D projection)


# ==============================================================================
# DESIGN ENGINE  (same calculation logic as the CLI version -- unchanged math,
# still prints its work with `print()`; the GUI just captures that printed
# output and shows it inside a text box instead of the console)
# ==============================================================================
def terzaghi_qult(c, phi_deg, gamma, Df, B, shape="square"):
    """
    Simplified Terzaghi general bearing capacity equation for a square/strip
    footing under vertical, centric load (no water table, no eccentricity):

        qult = c*Nc*Sc + gamma*Df*Nq + 0.5*gamma*B*Ngamma*Sgamma

    Used only if the user asks the app to ESTIMATE qa instead of typing in a
    geotechnical report value directly.
    """
    phi = math.radians(phi_deg)
    if phi_deg == 0:
        Nq, Nc, Ngamma = 1.0, 5.7, 0.0
    else:
        Nq = (math.e ** (2 * math.pi * (0.75 - phi_deg / 360) * math.tan(phi))) / \
             (2 * (math.cos(math.radians(45 + phi_deg / 2))) ** 2)
        Nc = (Nq - 1) / math.tan(phi)
        Ngamma = (Nq - 1) * math.tan(1.4 * phi)

    Sc, Sgamma = (1.3, 0.8) if shape == "square" else (1.0, 1.0)
    qult = c * Nc * Sc + gamma * Df * Nq + 0.5 * gamma * B * Ngamma * Sgamma
    return qult, (Nc, Nq, Ngamma)


def explain_design_basis(data):
    """Prints the 'lecture' -- the theory behind each design step, in plain
    student-friendly language, BEFORE the numbers are crunched."""
    print("""
An ISOLATED (or "pad") FOOTING supports a single column and spreads its load
over a large enough soil area that the soil doesn't fail or settle too much.

NSCP footing design generally happens in this order:

  (a) SOIL CLASSIFICATION (context, not a direct formula)
      Atterberg limits tell us how "clayey" or "plastic" the soil is:
          Plasticity Index, PI = LL - PL
      A high PI (e.g. > 20) suggests a clay that may be compressible and
      more sensitive to moisture -> settlement becomes as important as
      bearing capacity. This is why geotechnical engineers report both an
      allowable bearing pressure AND a settlement-based capacity; the
      smaller of the two governs qa. Moisture content and Atterberg limits
      do NOT plug directly into the bearing-capacity formula -- they're used
      to classify the soil and sanity-check the qa value.

  (b) SIZE THE FOOTING FOR SERVICE (UNFACTORED) LOADS
      We use the actual (not factored) loads because soil pressure is a
      SERVICEABILITY check, not a strength check:
          Total service load, P = PD + PL
          Required area,     A_req = P / q_net_allow
      where q_net_allow already has the FS baked in (qa = q_ultimate / FS),
      minus the weight of soil/footing displaced:
          q_net_allow = qa - gamma_conc * Df

  (c) CHECK STRENGTH (FACTORED LOADS) FOR THE CONCRETE ITSELF
      Once the footing plan size is fixed, we factor the loads
      (Pu = 1.2 PD + 1.6 PL per NSCP 203 load combos) to find the soil
      pressure used for concrete design:
          qu = Pu / A_footing
      This qu pushes UP against the footing and is what bends/shears it.

  (d) TWO-WAY (PUNCHING) SHEAR CHECK
      The column tries to "punch" through the footing like a stamp through
      paper. NSCP checks shear on a critical perimeter located d/2 from the
      column face (d = effective depth):
          bo = perimeter of that critical section
          Vc = 0.33 * lambda * sqrt(f'c) * bo * d   (NSCP 422.6.5, simplified)
      This is usually the GOVERNING (most critical) check for footings.

  (e) ONE-WAY (BEAM) SHEAR CHECK
      The footing also acts like a wide cantilevered beam off each column
      face. Critical section is at distance d from the column face:
          Vc = 0.17 * lambda * sqrt(f'c) * b * d     (NSCP 422.5.5)

  (f) FLEXURE (BENDING) DESIGN
      Bending moment is taken at the face of the column (cantilever action):
          Mu = qu * b * (L_cant)^2 / 2
      Then solved like a normal RC beam section for required steel As.

  (g) MINIMUM STEEL & BAR SPACING
      Footings need at least the shrinkage/temperature steel ratio
      (0.0018 for grade 415 steel, NSCP 407.6.1) even if flexure needs less.

We'll now walk through (b) - (g) with YOUR numbers, showing every formula.
""")


def _first_trial_thickness(B):
    """Rule-of-thumb starting thickness: h ~ B/6, not less than 300mm,
    rounded up to the nearest 25mm."""
    h = max(B / 6, 0.30)
    return math.ceil(h * 40) / 40


def _rho_from_Rn(Rn, fc, fy):
    """
    rho = (0.85*f'c/fy) * [1 - sqrt(1 - 2*Rn/(0.85*f'c))]
    Standard Whitney stress-block flexural design equation (NSCP/ACI 318).
    """
    term = 1 - (2 * Rn) / (0.85 * fc)
    if term < 0:
        return 0.0
    return (0.85 * fc / fy) * (1 - math.sqrt(term))


def design_footing(data):
    """
    Full isolated footing design: required area, factored soil pressure,
    two-way (punching) shear, one-way (beam) shear, and flexural steel.
    Prints every formula + substituted numbers, and returns a `results` dict
    used by the visualization and STAAD-export steps.
    """
    results = dict(data)

    # ---- (b) SIZE FOR SERVICE LOADS -----------------------------------------
    P_service = data["P_dead"] + data["P_live"]
    print(f"(b) Service load:  P = PD + PL = {data['P_dead']} + {data['P_live']}"
          f" = {P_service:.2f} kN")

    if data["qa_given"] > 0:
        qa = data["qa_given"]
        print(f"    Using geotech-report allowable bearing capacity: "
              f"qa = {qa:.2f} kPa (FS = {data['FS']} already applied by geotech engineer)")
    else:
        B_trial = math.sqrt(P_service / 150.0)
        qa_trial, qult, factors = None, None, None
        for _ in range(20):
            qult, factors = terzaghi_qult(
                data["cohesion"], data["friction_ang"], data["gamma_soil"],
                data["Df"], B_trial, shape="square")
            qa_trial = qult / data["FS"]
            A_trial = P_service / (qa_trial - data["gamma_conc"] * data["Df"])
            B_new = math.sqrt(A_trial)
            if abs(B_new - B_trial) < 0.001:
                B_trial = B_new
                break
            B_trial = B_new
        qa = qa_trial
        Nc, Nq, Ngamma = factors
        print(f"    Terzaghi factors for phi = {data['friction_ang']} deg: "
              f"Nc={Nc:.2f}, Nq={Nq:.2f}, Ngamma={Ngamma:.2f}")
        print(f"    qult = c*Nc*Sc + gamma*Df*Nq + 0.5*gamma*B*Ngamma*Sgamma "
              f"= {qult:.2f} kPa")
        print(f"    qa = qult / FS = {qult:.2f} / {data['FS']} = {qa:.2f} kPa")

    q_net_allow = qa - data["gamma_conc"] * data["Df"]
    print(f"    Net allowable pressure: q_net = qa - gamma_conc*Df "
          f"= {qa:.2f} - {data['gamma_conc']:.2f}*{data['Df']:.2f} "
          f"= {q_net_allow:.2f} kPa")

    A_req = P_service / q_net_allow
    print(f"    Required footing area: A_req = P / q_net = {P_service:.2f} / "
          f"{q_net_allow:.2f} = {A_req:.3f} m^2")

    B = math.ceil(math.sqrt(A_req) * 20) / 20  # round UP to nearest 0.05 m
    L = B
    A_provided = B * L
    print(f"    -> Provide a SQUARE footing: B = L = {B:.2f} m "
          f"(A_provided = {A_provided:.3f} m^2 >= A_req)")

    lot_check = "OK, fits within lot" if A_provided < data["lot_area"] else \
        "WARNING: footing area exceeds lot area, revisit layout!"
    print(f"    Sanity check vs. lot area ({data['lot_area']} m^2): {lot_check}")

    # ---- (c) FACTORED SOIL PRESSURE ------------------------------------------
    Pu = 1.2 * data["P_dead"] + 1.6 * data["P_live"]
    qu = Pu / A_provided
    print(f"\n(c) Factored load: Pu = 1.2*PD + 1.6*PL = 1.2*{data['P_dead']} + "
          f"1.6*{data['P_live']} = {Pu:.2f} kN")
    print(f"    Factored (upward) soil pressure: qu = Pu / A_provided = "
          f"{Pu:.2f} / {A_provided:.3f} = {qu:.2f} kPa")

    # ---- trial thickness (auto rule-of-thumb, or user override) --------------
    h_override = data.get("h_override")
    h = h_override if (h_override and h_override > 0) else _first_trial_thickness(B)
    cover = 0.075
    bar_dia_est = 0.016
    d = h - cover - bar_dia_est / 2
    src = "user override" if (h_override and h_override > 0) else "auto rule-of-thumb (h ~ B/6, min 300mm)"
    print(f"\n    Trial total footing thickness, h = {h*1000:.0f} mm [{src}]")
    print(f"    Effective depth d = h - cover - db/2 = {d*1000:.0f} mm")

    # ---- (d) TWO-WAY (PUNCHING) SHEAR ----------------------------------------
    c1, c2 = data["col_width"], data["col_length"]
    bo = 2 * (c1 + d) + 2 * (c2 + d)
    Vu_punch = qu * (A_provided - (c1 + d) * (c2 + d))
    Vc_punch = 0.33 * math.sqrt(data["fc"]) * bo * d * 1000
    phi_shear = 0.75
    Vc_punch_capacity = phi_shear * Vc_punch
    print(f"\n(d) TWO-WAY (PUNCHING) SHEAR CHECK")
    print(f"    Critical perimeter, bo = 2(c1+d) + 2(c2+d) = {bo:.3f} m")
    print(f"    Vu = qu*(A - (c1+d)(c2+d)) = {Vu_punch:.2f} kN")
    print(f"    Vc = 0.33*sqrt(f'c)*bo*d = {Vc_punch:.2f} kN")
    print(f"    phi*Vc = {phi_shear}*{Vc_punch:.2f} = {Vc_punch_capacity:.2f} kN")
    punch_ok = Vc_punch_capacity >= Vu_punch
    print(f"    Check: phi*Vc {'>=' if punch_ok else '<'} Vu  ->  "
          f"{'OK' if punch_ok else 'NOT OK -> increase thickness h'}")

    # ---- (e) ONE-WAY (BEAM) SHEAR --------------------------------------------
    cant = (B - c1) / 2
    x_crit = cant - d
    Vu_beam = qu * L * max(x_crit, 0)
    Vc_beam_kN = 0.17 * math.sqrt(data["fc"]) * (L * 1000) * (d * 1000) / 1000
    Vc_beam_capacity = phi_shear * Vc_beam_kN
    print(f"\n(e) ONE-WAY (BEAM) SHEAR CHECK")
    print(f"    Cantilever beyond column face = (B - c1)/2 = {cant:.3f} m")
    print(f"    Critical section at distance d from face -> x_crit = {x_crit:.3f} m")
    print(f"    Vu = qu * L * x_crit = {Vu_beam:.2f} kN")
    print(f"    Vc = 0.17*sqrt(f'c)*b*d = {Vc_beam_kN:.2f} kN")
    print(f"    phi*Vc = {Vc_beam_capacity:.2f} kN")
    beam_shear_ok = Vc_beam_capacity >= Vu_beam
    print(f"    Check: phi*Vc {'>=' if beam_shear_ok else '<'} Vu  ->  "
          f"{'OK' if beam_shear_ok else 'NOT OK -> increase thickness h'}")

    # ---- (f) FLEXURE DESIGN ---------------------------------------------------
    Mu = qu * L * cant ** 2 / 2
    phi_flex = 0.90
    Rn = (Mu * 1e6) / (phi_flex * (L * 1000) * (d * 1000) ** 2)
    rho = _rho_from_Rn(Rn, data["fc"], data["fy"])
    rho_min = 0.0018
    rho_use = max(rho, rho_min)
    As = rho_use * (L * 1000) * (d * 1000)
    print(f"\n(f) FLEXURAL (BENDING) DESIGN")
    print(f"    Mu = qu * L * (cantilever)^2 / 2 = {qu:.2f}*{L:.2f}*{cant:.3f}^2/2 "
          f"= {Mu:.2f} kN.m")
    print(f"    Rn = Mu / (phi*b*d^2) = {Rn:.4f} MPa")
    print(f"    rho required (from Rn) = {rho:.5f}   |   rho_min = {rho_min}")
    print(f"    rho used = max(rho, rho_min) = {rho_use:.5f}")
    print(f"    As required = rho*b*d = {As:.1f} mm^2 (total, across full width L)")

    bar_dia = 16
    bar_area = math.pi / 4 * bar_dia ** 2
    n_bars = math.ceil(As / bar_area)
    spacing = (L * 1000 - 2 * cover * 1000) / (n_bars - 1) if n_bars > 1 else 0
    print(f"    Using {bar_dia}mm bars (area = {bar_area:.1f} mm^2 each): "
          f"need {n_bars} bars, spaced at ~{spacing:.0f} mm o.c. each way")

    results.update(dict(
        P_service=P_service, qa=qa, q_net_allow=q_net_allow, A_req=A_req,
        B=B, L=L, A_provided=A_provided, Pu=Pu, qu=qu, h=h, d=d,
        punch_ok=punch_ok, beam_shear_ok=beam_shear_ok,
        Mu=Mu, As=As, bar_dia=bar_dia, n_bars=n_bars, spacing=spacing,
        Vu_punch=Vu_punch, Vc_punch_capacity=Vc_punch_capacity,
        Vu_beam=Vu_beam, Vc_beam_capacity=Vc_beam_capacity,
    ))

    print("\n" + "-" * 70)
    print("DESIGN SUMMARY")
    print("-" * 70)
    print(f"Footing size            : {B:.2f} m x {L:.2f} m x {h*1000:.0f} mm thick")
    print(f"Provided area           : {A_provided:.3f} m^2  (required {A_req:.3f} m^2)")
    print(f"Net allowable pressure  : {q_net_allow:.2f} kPa")
    print(f"Factored bearing pressure qu : {qu:.2f} kPa")
    print(f"Punching shear          : {'PASS' if punch_ok else 'FAIL'}")
    print(f"One-way (beam) shear    : {'PASS' if beam_shear_ok else 'FAIL'}")
    print(f"Main reinforcement      : {n_bars}-{bar_dia}mm bars @ {spacing:.0f} mm o.c., each way")
    print("-" * 70)
    if not (punch_ok and beam_shear_ok):
        print("NOTE: a shear check FAILED. Go back to Tab 1, enter a larger\n"
              "'Override footing thickness h' value, and click Run Design again.")

    return results


def build_figure(results):
    """
    Builds (but does not show) a matplotlib Figure with:
      - a 2D plan view (footing outline, column footprint, rebar hints)
      - a pseudo-3D block view (footing slab + column stub)
    Returns the Figure so the GUI can embed it in a Tkinter canvas.
    """
    B, L, h = results["B"], results["L"], results["h"]
    c1, c2 = results["col_width"], results["col_length"]

    fig = plt.figure(figsize=(9.5, 4.6))

    # ---- 2D PLAN VIEW ----------------------------------------------------------
    ax1 = fig.add_subplot(1, 2, 1)
    ax1.add_patch(plt.Rectangle((-B / 2, -L / 2), B, L, fill=True,
                                 facecolor="#d9d9d9", edgecolor="black", linewidth=2))
    ax1.add_patch(plt.Rectangle((-c1 / 2, -c2 / 2), c1, c2, fill=True,
                                 facecolor="#8c8c8c", edgecolor="black", linewidth=1.5))

    n_hint = 8
    for i in range(1, n_hint):
        y = -L / 2 + i * L / n_hint
        ax1.plot([-B / 2 + 0.05, B / 2 - 0.05], [y, y], color="crimson", linewidth=0.6)
    for i in range(1, n_hint):
        x = -B / 2 + i * B / n_hint
        ax1.plot([x, x], [-L / 2 + 0.05, L / 2 - 0.05], color="steelblue", linewidth=0.6)

    ax1.set_xlim(-B / 2 - 0.2, B / 2 + 0.2)
    ax1.set_ylim(-L / 2 - 0.2, L / 2 + 0.2)
    ax1.set_aspect("equal")
    ax1.set_title(f"Plan: {B:.2f}m x {L:.2f}m\n"
                   f"{results['n_bars']}-{results['bar_dia']}mm @ {results['spacing']:.0f}mm o.c. EW",
                   fontsize=9)
    ax1.set_xlabel("m", fontsize=8)
    ax1.set_ylabel("m", fontsize=8)
    ax1.tick_params(labelsize=7)

    # ---- 3D BLOCK VIEW ----------------------------------------------------------
    ax2 = fig.add_subplot(1, 2, 2, projection="3d")
    _draw_box(ax2, -B / 2, -L / 2, 0, B, L, h, color="#bfbfbf")
    col_h = 0.6
    _draw_box(ax2, -c1 / 2, -c2 / 2, h, c1, c2, col_h, color="#7f7f7f")

    ax2.set_title("3D Footing + Column Stub", fontsize=9)
    ax2.set_xlabel("B (m)", fontsize=8)
    ax2.set_ylabel("L (m)", fontsize=8)
    ax2.set_zlabel("H (m)", fontsize=8)
    max_range = max(B, L) / 2 + 0.3
    ax2.set_xlim(-max_range, max_range)
    ax2.set_ylim(-max_range, max_range)
    ax2.set_zlim(0, h + col_h + 0.2)
    ax2.tick_params(labelsize=7)

    fig.tight_layout()
    return fig


def _draw_box(ax, x0, y0, z0, dx, dy, dz, color):
    """Draws a simple rectangular box (used for footing + column stub)."""
    x = [x0, x0 + dx]
    y = [y0, y0 + dy]
    z = [z0, z0 + dz]
    xx, yy = np.meshgrid(x, y)
    ax.plot_surface(xx, yy, np.full_like(xx, z0), color=color, alpha=0.85)
    ax.plot_surface(xx, yy, np.full_like(xx, z0 + dz), color=color, alpha=0.85)
    for xi in x:
        yy2, zz2 = np.meshgrid(y, z)
        ax.plot_surface(np.full_like(yy2, xi), yy2, zz2, color=color, alpha=0.6)
    for yi in y:
        xx2, zz2 = np.meshgrid(x, z)
        ax.plot_surface(xx2, np.full_like(xx2, yi), zz2, color=color, alpha=0.6)


def send_to_staad(results):
    """
    Sends the footing geometry into a RUNNING STAAD.Pro 2025 session via the
    OpenSTAAD COM API (Windows only, STAAD.Pro must already be open with a
    model loaded, `pip install pywin32`). Falls back to printing the exact
    pseudocode if that environment isn't available.
    """
    B, L, h = results["B"], results["L"], results["h"]
    try:
        import win32com.client as win32

        staad = win32.Dispatch("StaadPro.OpenSTAAD")
        geometry = staad.Geometry
        support = staad.Support
        staad.SetSilentMode(1)
        print("Connected to STAAD.Pro via OpenSTAAD COM interface.")

        x0, y0 = -B / 2, -L / 2
        node_coords = [
            (x0, 0.0, y0), (x0 + B, 0.0, y0),
            (x0 + B, 0.0, y0 + L), (x0, 0.0, y0 + L),
        ]
        node_ids = [geometry.CreateNode(x, y, z) for (x, y, z) in node_coords]
        print(f"Created footing corner nodes: {node_ids}")

        plate_id = geometry.CreatePlate(4, node_ids)
        print(f"Created footing plate element, ID = {plate_id}")

        for nid in node_ids:
            support.CreateSupportFixed(nid)
        print("Assigned FIXED supports at footing nodes "
              "(approximation for stiff soil; refine with springs if you "
              "have a coefficient of subgrade reaction, ks).")
        print(f"\nFooting thickness (h = {h*1000:.0f} mm) should be set as the "
              "plate thickness in STAAD's Property page.")
        print("\nSTAAD integration complete. Switch to STAAD.Pro to see it.")

    except ImportError:
        print("'pywin32' is not installed, or you are not on Windows.")
        print("This step only works on Windows with STAAD.Pro 2025 open and")
        print("pywin32 installed (`pip install pywin32`). Here is what WOULD")
        print("have run:\n")
        _print_staad_pseudocode(results)
    except Exception as e:
        print(f"Could not connect to STAAD.Pro: {e}")
        print("Make sure STAAD.Pro 2025 is OPEN with a model loaded.\n")
        print("Here is what WOULD have run:\n")
        _print_staad_pseudocode(results)


def _print_staad_pseudocode(results):
    B, L = results["B"], results["L"]
    print(f"""    staad = win32.Dispatch("StaadPro.OpenSTAAD")
    n1 = staad.Geometry.CreateNode(-{B/2:.2f}, 0, -{L/2:.2f})
    n2 = staad.Geometry.CreateNode( {B/2:.2f}, 0, -{L/2:.2f})
    n3 = staad.Geometry.CreateNode( {B/2:.2f}, 0,  {L/2:.2f})
    n4 = staad.Geometry.CreateNode(-{B/2:.2f}, 0,  {L/2:.2f})
    plate_id = staad.Geometry.CreatePlate(4, [n1, n2, n3, n4])
    for n in [n1, n2, n3, n4]:
        staad.Support.CreateSupportFixed(n)""")


# ==============================================================================
# GUI APP
# ==============================================================================
FIELD_DEFS = [
    # (section, key, label, default)
    ("Site / Lot", "lot_area", "Lot area (m²)", "150.0"),
    ("Column / Loads", "col_width", "Column width, c1 (m)", "0.40"),
    ("Column / Loads", "col_length", "Column length, c2 (m)", "0.40"),
    ("Column / Loads", "P_dead", "Service Dead Load, PD (kN)", "600.0"),
    ("Column / Loads", "P_live", "Service Live Load, PL (kN)", "300.0"),
    ("Soil", "moisture_content", "Moisture content, w (%)", "22.0"),
    ("Soil", "LL", "Liquid Limit, LL (%)", "45.0"),
    ("Soil", "PL", "Plastic Limit, PL (%)", "22.0"),
    ("Soil", "qa_given", "Allowable bearing capacity, qa (kPa)", "190.0"),
    ("Soil", "cohesion", "  (if estimating) Soil cohesion, c (kPa)", "10.0"),
    ("Soil", "friction_ang", "  (if estimating) Friction angle, phi (deg)", "28.0"),
    ("Soil", "gamma_soil", "  (if estimating) Soil unit weight (kN/m³)", "18.0"),
    ("Soil", "Df", "Depth of footing base, Df (m)", "1.20"),
    ("Materials / FS", "FS", "Factor of Safety (bearing)", "3.0"),
    ("Materials / FS", "fc", "Concrete strength, f'c (MPa)", "21.0"),
    ("Materials / FS", "fy", "Steel yield strength, fy (MPa)", "415.0"),
    ("Materials / FS", "gamma_conc", "Unit weight of concrete (kN/m³)", "23.5"),
    ("Materials / FS", "h_override", "Override thickness h (m) — blank = auto", ""),
]


class FootingApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Isolated Footing Design Tutor — NSCP")
        self.geometry("980x680")
        self.minsize(860, 600)

        self.results = None
        self.canvas_widget = None
        self.toolbar_widget = None

        self._build_style()
        self._build_layout()

    # ---------------------------------------------------------------- style
    def _build_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Header.TLabel", font=("Segoe UI", 13, "bold"))
        style.configure("Status.TLabel", font=("Segoe UI", 11, "bold"))
        style.configure("TButton", font=("Segoe UI", 10))
        style.configure("TLabelframe.Label", font=("Segoe UI", 10, "bold"))

    # --------------------------------------------------------------- layout
    def _build_layout(self):
        header = ttk.Frame(self, padding=(12, 10))
        header.pack(fill="x")
        ttk.Label(header, text="Isolated Footing Design Tutor",
                  style="Header.TLabel").pack(side="left")
        self.status_lbl = ttk.Label(header, text="Fill in inputs and click Run Design",
                                     style="Status.TLabel")
        self.status_lbl.pack(side="right")

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.tab_inputs = ttk.Frame(self.notebook)
        self.tab_theory = ttk.Frame(self.notebook)
        self.tab_results = ttk.Frame(self.notebook)
        self.tab_viz = ttk.Frame(self.notebook)
        self.tab_staad = ttk.Frame(self.notebook)

        self.notebook.add(self.tab_inputs, text="1. Inputs")
        self.notebook.add(self.tab_theory, text="2. Theory")
        self.notebook.add(self.tab_results, text="3. Results")
        self.notebook.add(self.tab_viz, text="4. Visualization")
        self.notebook.add(self.tab_staad, text="5. STAAD.Pro")

        self._build_inputs_tab()
        self._build_theory_tab()
        self._build_results_tab()
        self._build_viz_tab()
        self._build_staad_tab()

    # --------------------------------------------------------- Tab 1: Inputs
    def _build_inputs_tab(self):
        outer = ttk.Frame(self.tab_inputs, padding=10)
        outer.pack(fill="both", expand=True)

        canvas = tk.Canvas(outer, highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        scroll_frame = ttk.Frame(canvas)
        scroll_frame.bind("<Configure>",
                           lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.vars = {}
        sections = {}
        for section, key, label, default in FIELD_DEFS:
            if section not in sections:
                frame = ttk.LabelFrame(scroll_frame, text=section, padding=10)
                frame.pack(fill="x", padx=4, pady=6)
                sections[section] = frame
            frame = sections[section]
            row = frame.grid_size()[1]
            ttk.Label(frame, text=label, width=42, anchor="w").grid(
                row=row, column=0, sticky="w", padx=4, pady=3)
            var = tk.StringVar(value=default)
            ttk.Entry(frame, textvariable=var, width=14).grid(
                row=row, column=1, sticky="w", padx=4, pady=3)
            self.vars[key] = var

        hint = ttk.Label(
            scroll_frame,
            text=("Tip: set 'Allowable bearing capacity qa' to 0 to have the app "
                  "ESTIMATE it from cohesion/friction angle/unit weight using "
                  "Terzaghi's equation instead of a geotech-report value."),
            wraplength=820, foreground="#555555")
        hint.pack(fill="x", padx=8, pady=(0, 6))

        btn_frame = ttk.Frame(scroll_frame, padding=(4, 8))
        btn_frame.pack(fill="x")
        ttk.Button(btn_frame, text="▶ Run Design", command=self.run_design
                   ).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Reset to Defaults", command=self.reset_defaults
                   ).pack(side="left", padx=4)

    def reset_defaults(self):
        for section, key, label, default in FIELD_DEFS:
            self.vars[key].set(default)
        self.status_lbl.config(text="Reset to defaults", foreground="black")

    # --------------------------------------------------------- Tab 2: Theory
    def _build_theory_tab(self):
        frame = ttk.Frame(self.tab_theory, padding=10)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Design theory walkthrough (updates each time you run the design)",
                  style="Header.TLabel").pack(anchor="w", pady=(0, 6))
        self.theory_text = scrolledtext.ScrolledText(
            frame, wrap="word", font=("Consolas", 10), state="normal")
        self.theory_text.pack(fill="both", expand=True)
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            explain_design_basis({})
        self.theory_text.insert("1.0", buf.getvalue())
        self.theory_text.config(state="disabled")

    # -------------------------------------------------------- Tab 3: Results
    def _build_results_tab(self):
        frame = ttk.Frame(self.tab_results, padding=10)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Step-by-step calculation log",
                  style="Header.TLabel").pack(anchor="w", pady=(0, 6))
        self.results_text = scrolledtext.ScrolledText(
            frame, wrap="word", font=("Consolas", 10), state="normal")
        self.results_text.pack(fill="both", expand=True)
        self.results_text.insert("1.0", "Run the design from Tab 1 to see results here.")
        self.results_text.config(state="disabled")

    # ---------------------------------------------------- Tab 4: Visualization
    def _build_viz_tab(self):
        self.viz_frame = ttk.Frame(self.tab_viz, padding=10)
        self.viz_frame.pack(fill="both", expand=True)
        self.viz_placeholder = ttk.Label(
            self.viz_frame,
            text="Run the design from Tab 1 to see the 2D plan and 3D footing model here.")
        self.viz_placeholder.pack(expand=True)

    # -------------------------------------------------------- Tab 5: STAAD
    def _build_staad_tab(self):
        frame = ttk.Frame(self.tab_staad, padding=10)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="STAAD.Pro 2025 / OpenSTAAD integration",
                  style="Header.TLabel").pack(anchor="w", pady=(0, 4))
        ttk.Label(
            frame,
            text=("Requires Windows + STAAD.Pro 2025 already OPEN with a model "
                  "loaded, plus `pip install pywin32`. Run the design first."),
            wraplength=850, foreground="#555555").pack(anchor="w", pady=(0, 8))
        ttk.Button(frame, text="⇪ Send Footing Geometry to STAAD.Pro",
                   command=self.run_staad).pack(anchor="w", pady=(0, 8))
        self.staad_text = scrolledtext.ScrolledText(
            frame, wrap="word", font=("Consolas", 10), state="normal")
        self.staad_text.pack(fill="both", expand=True)
        self.staad_text.insert("1.0", "Nothing sent yet.")
        self.staad_text.config(state="disabled")

    # ------------------------------------------------------------- actions
    def _parse_inputs(self):
        """Reads every Entry field, converts to float, returns the `data`
        dict expected by design_footing(). Raises ValueError with a helpful
        message if something isn't a valid number."""
        data = {}
        for section, key, label, default in FIELD_DEFS:
            raw = self.vars[key].get().strip()
            if key == "h_override":
                data["h_override"] = float(raw) if raw else None
                continue
            if raw == "":
                raise ValueError(f"'{label.strip()}' is empty — please enter a number.")
            try:
                data[key] = float(raw)
            except ValueError:
                raise ValueError(f"'{label.strip()}' must be a number, got '{raw}'.")
        return data

    def run_design(self):
        try:
            data = self._parse_inputs()
        except ValueError as e:
            messagebox.showerror("Input error", str(e))
            return

        # ---- capture the theory + calculation print() output as text -------
        with contextlib.redirect_stdout(io.StringIO()) as theory_buf:
            explain_design_basis(data)
        with contextlib.redirect_stdout(io.StringIO()) as calc_buf:
            try:
                results = design_footing(data)
            except Exception as e:
                messagebox.showerror("Calculation error", str(e))
                return

        self.results = results

        # ---- update Theory tab ---------------------------------------------
        self.theory_text.config(state="normal")
        self.theory_text.delete("1.0", "end")
        self.theory_text.insert("1.0", theory_buf.getvalue())
        self.theory_text.config(state="disabled")

        # ---- update Results tab ---------------------------------------------
        self.results_text.config(state="normal")
        self.results_text.delete("1.0", "end")
        self.results_text.insert("1.0", calc_buf.getvalue())
        self.results_text.config(state="disabled")

        # ---- update status bar ------------------------------------------------
        overall_ok = results["punch_ok"] and results["beam_shear_ok"]
        self.status_lbl.config(
            text=(f"{results['B']:.2f}m x {results['L']:.2f}m x "
                  f"{results['h']*1000:.0f}mm  —  "
                  f"{'ALL CHECKS PASS' if overall_ok else 'SHEAR CHECK FAILED'}"),
            foreground=("#1a7a1a" if overall_ok else "#b30000"))

        # ---- update Visualization tab ------------------------------------------
        for child in self.viz_frame.winfo_children():
            child.destroy()
        fig = build_figure(results)
        canvas = FigureCanvasTkAgg(fig, master=self.viz_frame)
        canvas.draw()
        toolbar = NavigationToolbar2Tk(canvas, self.viz_frame)
        toolbar.update()
        canvas.get_tk_widget().pack(fill="both", expand=True)

        self.notebook.select(self.tab_results)

    def run_staad(self):
        if self.results is None:
            messagebox.showwarning("No design yet",
                                    "Run the design on Tab 1 first.")
            return
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            send_to_staad(self.results)
        self.staad_text.config(state="normal")
        self.staad_text.delete("1.0", "end")
        self.staad_text.insert("1.0", buf.getvalue())
        self.staad_text.config(state="disabled")


def main():
    app = FootingApp()
    app.mainloop()


if __name__ == "__main__":
    main()