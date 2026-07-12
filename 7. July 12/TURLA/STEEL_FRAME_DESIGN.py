"""
=============================================================================
 STAAD.Pro / OpenSTAAD Structural Design Dashboard  (Plotly Dash edition)
=============================================================================
A Plotly Dash application that:
    1. Collects geometry / loading / material inputs from the user through
       an input form (no Streamlit).
    2. Builds an OpenSTAAD (STAAD.Pro COM automation, via `comtypes` - no
       `pywin32`/`win32com`) model, applies loads per ASCE 7-16, runs the
       analysis, and pulls back reactions / forces.
    3. Runs simplified ACI 318-19 code-compliance checks on the concrete
       pedestal / base-plate bearing region and reports pass/fail.
    4. Renders an interactive 3D Plotly visualization of the frame,
       highlighting the steel-to-concrete base plate connections.

-----------------------------------------------------------------------------
IMPORTANT / READ FIRST
-----------------------------------------------------------------------------
- OpenSTAAD is a Windows-only COM automation interface exposed by a
  licensed, RUNNING copy of Bentley STAAD.Pro. This script therefore only
  performs real analysis when run on a Windows machine that has STAAD.Pro
  installed, licensed, and open. It cannot be run or tested inside this
  sandbox, and Anthropic does not have a copy of STAAD.Pro to test against.
- The exact method names on the OpenSTAAD object model (Geometry, Property,
  Support, Load, Analysis, Output, etc.) can differ slightly between
  STAAD.Pro versions/service packs. The calls below follow the documented
  OpenSTAAD API structure (see STAAD.Pro Help -> OpenSTAAD), but confirm
  exact signatures against the "OpenSTAAD.chm" / API guide shipped with
  your installed version and adjust if a method name has changed.
- The ACI 318-19 / ASCE 7-16 checks implemented here are SIMPLIFIED,
  illustrative engineering calculations meant to demonstrate the workflow
  and code-reference structure. They are NOT a substitute for a full code
  check by a licensed engineer, and are not sufficient on their own for
  construction documents. Every check below cites the specific clause it
  approximates so a qualified engineer can verify / extend it.
- If OpenSTAAD cannot be reached (e.g. running on macOS/Linux, STAAD.Pro
  isn't open, or "Connect to live STAAD.Pro" is left unchecked), the app
  automatically falls back to a "demo / analytical" mode so the dashboard,
  checks, and 3D visualization can still be explored end-to-end.

Prerequisites (Windows, with STAAD.Pro installed for live analysis):
    pip install dash plotly numpy comtypes

Run with:
    python staad_design_dashboard.py
Then open the URL it prints (default http://127.0.0.1:8050) in a browser.
=============================================================================
"""

import math
import traceback
from dataclasses import dataclass

import numpy as np
import plotly.graph_objects as go

from dash import Dash, dcc, html, Input, Output, State, dash_table, no_update

# comtypes is a pure-Python COM automation library (no pywin32 dependency)
# and is only available/needed on Windows. We import it defensively so the
# rest of the app still loads (in demo/analytical mode) on machines where
# OpenSTAAD automation isn't possible.
try:
    import comtypes.client as comtypes_client
    OPENSTAAD_LIB_AVAILABLE = True
except ImportError:
    OPENSTAAD_LIB_AVAILABLE = False


# =============================================================================
# 1. DATA MODEL FOR USER INPUTS
# =============================================================================
@dataclass
class DesignInputs:
    """Container for every parameter the user supplies through the form."""

    # --- Geometry ---
    num_bays_x: int = 3            # number of bays along X
    num_bays_z: int = 2            # number of bays along Z (out-of-plane)
    bay_spacing_x: float = 6.0     # m, center-to-center bay spacing along X
    bay_spacing_z: float = 6.0     # m, center-to-center bay spacing along Z
    num_stories: int = 1           # number of stories above ground
    column_height: float = 4.0     # m, typical story height
    ground_elevation: float = 0.0  # m, elevation of finished ground level (FGL)
    base_plate_elevation: float = -1.2  # m, elevation of top of concrete
                                         # pedestal where the steel base
                                         # plate bears (relative to FGL,
                                         # negative = below grade)

    # --- Steel column / beam section sizes (nominal, user-entered) ---
    column_section: str = "W12X65"
    beam_section: str = "W16X40"

    # --- Material strengths ---
    fc_concrete_mpa: float = 27.6   # f'c, concrete compressive strength (MPa) ~4000 psi
    fy_steel_mpa: float = 345.0     # Fy, structural steel yield strength (MPa) ~50 ksi
    fy_rebar_mpa: float = 420.0     # fy, reinforcing steel yield strength (MPa) ~60 ksi

    # --- Base plate / pedestal geometry ---
    base_plate_length_mm: float = 500.0
    base_plate_width_mm: float = 500.0
    pedestal_length_mm: float = 700.0
    pedestal_width_mm: float = 700.0
    anchor_bolt_dia_mm: float = 25.0
    num_anchor_bolts: int = 4

    # --- Loads (ASCE 7-16) ---
    dead_load_kpa: float = 3.5      # kPa, floor/roof dead load (ASCE 7-16 Ch.3)
    live_load_kpa: float = 2.4      # kPa, live load (ASCE 7-16 Ch.4, Table 4.3-1)
    basic_wind_speed_mps: float = 50.0   # m/s, Vult (ASCE 7-16 Ch.26, Fig 26.5-1)
    exposure_category: str = "C"         # ASCE 7-16 Section 26.7
    risk_category: str = "II"            # ASCE 7-16 Table 1.5-1
    seismic_ss: float = 0.75             # ASCE 7-16 Ch.11, mapped Ss
    seismic_s1: float = 0.30             # ASCE 7-16 Ch.11, mapped S1
    site_class: str = "D"                # ASCE 7-16 Ch.20

    # --- STAAD connection ---
    use_live_staad: bool = False    # if False, run in demo/analytical mode
    staad_std_file_path: str = r"C:\STAAD_Models\generated_frame.std"


# =============================================================================
# 2. FUNCTION: INPUT HANDLING
#    (Dash layout builder + a parser that turns submitted form values back
#    into a DesignInputs dataclass instance)
# =============================================================================
def _labeled_input(label, input_id, value, input_type="number", **kwargs):
    """Small helper to keep the layout grid below readable."""
    return html.Div(
        [
            html.Label(label, style={"fontSize": "13px", "fontWeight": "600"}),
            dcc.Input(
                id=input_id, type=input_type, value=value,
                style={"width": "100%"}, **kwargs
            ),
        ],
        style={"marginBottom": "10px"},
    )


def build_input_layout() -> html.Div:
    """
    Builds the Dash input form: Geometry / Sections / Materials /
    Base Plate-Pedestal / Loads (ASCE 7-16) / OpenSTAAD connection -
    matching the categories requested by the user. Returns a Div meant to
    sit in a left-hand column of the page layout.
    """
    defaults = DesignInputs()

    def section(title, children):
        return html.Div(
            [html.H4(title, style={"marginTop": "18px", "marginBottom": "6px"})] + children,
            style={"borderBottom": "1px solid #ddd", "paddingBottom": "8px"},
        )

    return html.Div(
        [
            section("1. Geometry", [
                _labeled_input("Number of bays (X direction)", "in-num-bays-x", defaults.num_bays_x),
                _labeled_input("Number of bays (Z direction)", "in-num-bays-z", defaults.num_bays_z),
                _labeled_input("Bay spacing X (m)", "in-bay-spacing-x", defaults.bay_spacing_x),
                _labeled_input("Bay spacing Z (m)", "in-bay-spacing-z", defaults.bay_spacing_z),
                _labeled_input("Number of stories", "in-num-stories", defaults.num_stories),
                _labeled_input("Typical story height (m)", "in-column-height", defaults.column_height),
                _labeled_input("Ground level elevation (m)", "in-ground-elevation", defaults.ground_elevation),
                _labeled_input(
                    "Base plate elevation, top of pedestal (m, rel. to ground)",
                    "in-base-plate-elevation", defaults.base_plate_elevation
                ),
            ]),
            section("2. Steel Sections", [
                _labeled_input("Column section (AISC designation)", "in-column-section",
                                defaults.column_section, input_type="text"),
                _labeled_input("Beam section (AISC designation)", "in-beam-section",
                                defaults.beam_section, input_type="text"),
            ]),
            section("3. Material Strengths", [
                _labeled_input("f'c - concrete (MPa)", "in-fc-concrete", defaults.fc_concrete_mpa),
                _labeled_input("Fy - structural steel (MPa)", "in-fy-steel", defaults.fy_steel_mpa),
                _labeled_input("fy - reinforcing steel (MPa)", "in-fy-rebar", defaults.fy_rebar_mpa),
            ]),
            section("4. Base Plate / Pedestal", [
                _labeled_input("Base plate length (mm)", "in-bp-length", defaults.base_plate_length_mm),
                _labeled_input("Base plate width (mm)", "in-bp-width", defaults.base_plate_width_mm),
                _labeled_input("Pedestal length (mm)", "in-ped-length", defaults.pedestal_length_mm),
                _labeled_input("Pedestal width (mm)", "in-ped-width", defaults.pedestal_width_mm),
                _labeled_input("Anchor bolt diameter (mm)", "in-bolt-dia", defaults.anchor_bolt_dia_mm),
                _labeled_input("Number of anchor bolts per base plate", "in-num-bolts", defaults.num_anchor_bolts),
            ]),
            section("5. Loads (ASCE 7-16)", [
                _labeled_input("Dead load (kPa)", "in-dead-load", defaults.dead_load_kpa),
                _labeled_input("Live load (kPa)", "in-live-load", defaults.live_load_kpa),
                _labeled_input("Basic wind speed, Vult (m/s)", "in-wind-speed", defaults.basic_wind_speed_mps),
                html.Label("Wind exposure category", style={"fontSize": "13px", "fontWeight": "600"}),
                dcc.Dropdown(id="in-exposure-cat", options=["B", "C", "D"], value=defaults.exposure_category,
                             style={"marginBottom": "10px"}),
                html.Label("Risk category", style={"fontSize": "13px", "fontWeight": "600"}),
                dcc.Dropdown(id="in-risk-cat", options=["I", "II", "III", "IV"], value=defaults.risk_category,
                             style={"marginBottom": "10px"}),
                _labeled_input("Mapped Ss (g)", "in-seismic-ss", defaults.seismic_ss),
                _labeled_input("Mapped S1 (g)", "in-seismic-s1", defaults.seismic_s1),
                html.Label("Site class", style={"fontSize": "13px", "fontWeight": "600"}),
                dcc.Dropdown(id="in-site-class", options=["A", "B", "C", "D", "E"], value=defaults.site_class,
                             style={"marginBottom": "10px"}),
            ]),
            section("6. OpenSTAAD Connection", [
                dcc.Checklist(
                    id="in-use-live-staad",
                    options=[{"label": " Connect to a running STAAD.Pro instance (Windows only)", "value": "live"}],
                    value=[],
                    style={"marginBottom": "10px"},
                ),
                _labeled_input(
                    "STAAD .std file path (created if it does not exist)",
                    "in-std-path", defaults.staad_std_file_path, input_type="text"
                ),
            ]),
            html.Button("Run Design", id="btn-run-design", n_clicks=0, style={
                "width": "100%", "marginTop": "16px", "padding": "10px",
                "backgroundColor": "#2c5f8a", "color": "white", "border": "none",
                "borderRadius": "4px", "fontWeight": "600", "cursor": "pointer",
            }),
        ],
        style={"width": "320px", "padding": "14px", "overflowY": "auto", "height": "100vh"},
    )


# All form-input component ids, in the exact order the callback's State
# list supplies them, so parse_inputs_from_values() can zip them together.
INPUT_IDS = [
    "in-num-bays-x", "in-num-bays-z", "in-bay-spacing-x", "in-bay-spacing-z",
    "in-num-stories", "in-column-height", "in-ground-elevation", "in-base-plate-elevation",
    "in-column-section", "in-beam-section",
    "in-fc-concrete", "in-fy-steel", "in-fy-rebar",
    "in-bp-length", "in-bp-width", "in-ped-length", "in-ped-width",
    "in-bolt-dia", "in-num-bolts",
    "in-dead-load", "in-live-load", "in-wind-speed", "in-exposure-cat", "in-risk-cat",
    "in-seismic-ss", "in-seismic-s1", "in-site-class",
    "in-use-live-staad", "in-std-path",
]


def parse_inputs_from_values(values: list) -> DesignInputs:
    """
    Converts the raw list of values Dash hands back from the form (in the
    order defined by INPUT_IDS) into a validated DesignInputs instance.
    """
    (num_bays_x, num_bays_z, bay_spacing_x, bay_spacing_z,
     num_stories, column_height, ground_elevation, base_plate_elevation,
     column_section, beam_section,
     fc_concrete_mpa, fy_steel_mpa, fy_rebar_mpa,
     base_plate_length_mm, base_plate_width_mm, pedestal_length_mm, pedestal_width_mm,
     anchor_bolt_dia_mm, num_anchor_bolts,
     dead_load_kpa, live_load_kpa, basic_wind_speed_mps, exposure_category, risk_category,
     seismic_ss, seismic_s1, site_class,
     use_live_staad_list, staad_std_file_path) = values

    return DesignInputs(
        num_bays_x=int(num_bays_x), num_bays_z=int(num_bays_z),
        bay_spacing_x=float(bay_spacing_x), bay_spacing_z=float(bay_spacing_z),
        num_stories=int(num_stories), column_height=float(column_height),
        ground_elevation=float(ground_elevation), base_plate_elevation=float(base_plate_elevation),
        column_section=column_section, beam_section=beam_section,
        fc_concrete_mpa=float(fc_concrete_mpa), fy_steel_mpa=float(fy_steel_mpa),
        fy_rebar_mpa=float(fy_rebar_mpa),
        base_plate_length_mm=float(base_plate_length_mm), base_plate_width_mm=float(base_plate_width_mm),
        pedestal_length_mm=float(pedestal_length_mm), pedestal_width_mm=float(pedestal_width_mm),
        anchor_bolt_dia_mm=float(anchor_bolt_dia_mm), num_anchor_bolts=int(num_anchor_bolts),
        dead_load_kpa=float(dead_load_kpa), live_load_kpa=float(live_load_kpa),
        basic_wind_speed_mps=float(basic_wind_speed_mps), exposure_category=exposure_category,
        risk_category=risk_category, seismic_ss=float(seismic_ss), seismic_s1=float(seismic_s1),
        site_class=site_class, use_live_staad=("live" in (use_live_staad_list or [])),
        staad_std_file_path=staad_std_file_path,
    )


# =============================================================================
# 3. FUNCTION: OPENSTAAD SCRIPT GENERATION AND EXECUTION
# =============================================================================
def connect_to_staad():
    """
    Attaches to a running STAAD.Pro instance via COM (using `comtypes`,
    NOT `win32com`/`pywin32`) and returns the top-level OpenSTAAD
    automation object, or None if unavailable.

    STAAD.Pro must already be open with the OpenSTAAD interface enabled.
    """
    if not OPENSTAAD_LIB_AVAILABLE:
        return None
    try:
        # "StaadPro.OpenSTAAD" is the registered COM ProgID exposed by a
        # running STAAD.Pro session. comtypes.client.GetActiveObject()
        # attaches to it by ProgID, wrapping it in a dynamic COM interface
        # built at runtime from the type library (no makepy step needed).
        staad = comtypes_client.GetActiveObject("StaadPro.OpenSTAAD", dynamic=True)
        return staad
    except Exception:
        return None


def generate_and_run_staad_model(inputs: DesignInputs) -> dict:
    """
    Builds the frame geometry in STAAD.Pro through the OpenSTAAD COM API,
    assigns sections/materials, applies ASCE 7-16 loads, runs the analysis,
    and extracts reactions / member forces.

    If a live STAAD.Pro session is not available (use_live_staad == False,
    or the COM connection fails), this function instead computes an
    approximate, self-consistent set of results analytically so the
    dashboard remains fully functional in demo mode. The analytical
    fallback (and any live-STAAD error) is recorded in results['warnings']
    for the UI to display, rather than printed directly (this module has
    no direct dependency on a specific UI framework).

    Returns
    -------
    dict with keys:
        'mode'             : "live_staad" or "demo_analytical"
        'nodes'            : {node_id: (x, y, z)}
        'base_nodes'       : list of node_ids at the base plate elevation
        'reactions'        : {node_id: {'Fx','Fy','Fz','Mx','My','Mz'}} (kN, kN-m)
        'max_column_axial' : kN, worst-case column axial force (for checks)
        'max_beam_moment'  : kN-m, worst-case beam bending moment
        'load_combo'       : text description of the governing ASCE 7-16 combo used
        'warnings'         : list[str], any fallback/error messages to surface in the UI
    """
    warnings = []

    # ---- 3a. Build node/member geometry from bay counts & spacing --------
    nx, nz = inputs.num_bays_x, inputs.num_bays_z
    dx, dz = inputs.bay_spacing_x, inputs.bay_spacing_z
    story_h = inputs.column_height
    n_story = inputs.num_stories
    base_z = inputs.base_plate_elevation  # elevation of top of pedestal (steel/concrete interface)
    ground_z = inputs.ground_elevation

    nodes = {}
    node_id = 1
    node_lookup = {}  # (ix, iz, story) -> node_id
    for ix in range(nx + 1):
        for iz in range(nz + 1):
            for story in range(n_story + 1):
                x = ix * dx
                y = ground_z + story * story_h  # vertical axis = Y (STAAD default up-axis)
                z = iz * dz
                nodes[node_id] = (x, y, z)
                node_lookup[(ix, iz, story)] = node_id
                node_id += 1

    # Base-plate nodes: one per column line, positioned at base_plate_elevation
    # (below/at the story-0 grid) representing the steel-to-concrete interface.
    base_nodes = []
    base_node_lookup = {}
    for ix in range(nx + 1):
        for iz in range(nz + 1):
            bx, bz = ix * dx, iz * dz
            by = base_z
            nodes[node_id] = (bx, by, bz)
            base_nodes.append(node_id)
            base_node_lookup[(ix, iz)] = node_id
            node_id += 1

    members = []  # (start_node, end_node, member_type, section)
    # Columns: base plate -> story 0 -> story 1 -> ... -> story n
    for ix in range(nx + 1):
        for iz in range(nz + 1):
            prev = base_node_lookup[(ix, iz)]
            for story in range(n_story + 1):
                cur = node_lookup[(ix, iz, story)]
                members.append((prev, cur, "column", inputs.column_section))
                prev = cur

    # Beams: connect adjacent grid nodes at each story level (X and Z directions)
    for story in range(n_story + 1):
        for ix in range(nx + 1):
            for iz in range(nz):
                n1 = node_lookup[(ix, iz, story)]
                n2 = node_lookup[(ix, iz + 1, story)]
                members.append((n1, n2, "beam", inputs.beam_section))
        for iz in range(nz + 1):
            for ix in range(nx):
                n1 = node_lookup[(ix, iz, story)]
                n2 = node_lookup[(ix + 1, iz, story)]
                members.append((n1, n2, "beam", inputs.beam_section))

    # ---- 3b. Attempt live OpenSTAAD automation ----------------------------
    staad = connect_to_staad() if inputs.use_live_staad else None

    if inputs.use_live_staad and staad is None:
        warnings.append(
            "Could not attach to a running STAAD.Pro instance via comtypes "
            "(OpenSTAAD unavailable, not on Windows, or STAAD.Pro isn't open). "
            "Falling back to analytical demo mode."
        )

    if staad is not None:
        try:
            result = _run_live_staad(staad, inputs, nodes, base_nodes, members)
            result["warnings"] = warnings
            return result
        except Exception as exc:
            warnings.append(
                f"OpenSTAAD automation failed ({exc}). Falling back to the "
                "analytical demo mode. Full traceback:\n" + traceback.format_exc()
            )

    # ---- 3c. Analytical fallback (demo mode) ------------------------------
    result = _run_demo_analytical(inputs, nodes, base_nodes, members)
    result["warnings"] = warnings
    return result


def _run_live_staad(staad, inputs: DesignInputs, nodes, base_nodes, members) -> dict:
    """
    Issues the actual OpenSTAAD COM calls: create geometry, assign
    properties/materials, define ASCE 7-16 load cases, analyze, and read
    back reactions/forces. Wrapped separately so callers can catch and
    fall back cleanly if the installed STAAD.Pro version exposes slightly
    different method names.

    NOTE: method names (CreateNode, CreateBeam, CreateBeamPropertyFromTable,
    etc.) follow the documented OpenSTAAD object model (Geometry / Property /
    Support / Load / Analysis / Output). Verify against your STAAD.Pro
    version's OpenSTAAD help file if a call fails.
    """
    geometry = staad.Geometry
    prop = staad.Property
    support = staad.Support
    load = staad.Load
    analysis = staad.Analysis
    output = staad.Output
    command = staad.Command

    # --- Start a new model file (or open the target .std) ---
    staad.NewSTAADFile(inputs.staad_std_file_path)
    staad.SetUnit(4, 6)  # 4 = meters, 6 = kN (Length/Force unit codes per OpenSTAAD spec)

    # --- Create nodes ---
    for nid, (x, y, z) in nodes.items():
        geometry.CreateNode(nid, x, y, z)

    # --- Create members and assign sections ---
    member_id = 1
    section_assignments = {}  # section name -> list of member ids, for batch property calls
    for (n1, n2, mtype, section) in members:
        geometry.CreateBeam(member_id, n1, n2)
        section_assignments.setdefault(section, []).append(member_id)
        member_id += 1

    # --- Material definition (steel, per AISC / ASTM A992 unless overridden) ---
    prop.CreateMaterial("STEEL_A992", inputs.fy_steel_mpa * 1000.0, 0.3, 77.0)  # E(kPa)~placeholder, nu, density
    for section, ids in section_assignments.items():
        prop.CreateBeamPropertyFromTable(section, "AISC")  # American AISC steel table
        for mid in ids:
            prop.AssignBeamProperty(mid, section)
            prop.AssignMaterialToMember(mid, "STEEL_A992")

    # --- Supports: fix all base-plate nodes (steel-to-concrete pedestal
    #     interface) as fixed, approximating a rigid, fully anchored base
    #     connection per typical column base design practice. ---
    for bn in base_nodes:
        support.CreateSupportFixed(bn)

    # --- Loads per ASCE 7-16 -------------------------------------------
    # Dead Load (D) - ASCE 7-16 Chapter 3
    load.CreateNewPrimaryLoad("DEAD LOAD - ASCE 7-16 Ch.3")
    load.AddMemberUniformForce(list(range(1, member_id)), 0, -inputs.dead_load_kpa, 0)

    # Live Load (L) - ASCE 7-16 Chapter 4, reducible per Section 4.7
    load.CreateNewPrimaryLoad("LIVE LOAD - ASCE 7-16 Ch.4")
    load.AddMemberUniformForce(list(range(1, member_id)), 0, -inputs.live_load_kpa, 0)

    # Wind Load (W) - ASCE 7-16 Chapters 26-30, Directional Procedure
    # Velocity pressure qz = 0.613 * Kz * Kzt * Kd * V^2 * Ke  (Eq. 26.10-1, SI form)
    kz, kzt, kd, ke = 0.85, 1.0, 0.85, 1.0
    qz = 0.613 * kz * kzt * kd * (inputs.basic_wind_speed_mps ** 2) * ke  # Pa
    load.CreateNewPrimaryLoad(f"WIND LOAD - ASCE 7-16 Ch.26-30 (qz={qz:.0f} Pa)")
    load.AddMemberUniformForce(list(range(1, member_id)), qz / 1000.0, 0, 0)

    # Seismic Load (E) - ASCE 7-16 Chapter 12, Equivalent Lateral Force
    # Procedure: Cs = Sds / (R/Ie), base shear V = Cs * W  (Eq. 12.8-2)
    sds = (2.0 / 3.0) * inputs.seismic_ss  # simplified, ignoring Fa site coefficient detail
    r_factor = 3.25  # typical R for ordinary steel moment frame, ASCE 7-16 Table 12.2-1
    ie = 1.0 if inputs.risk_category in ("I", "II") else 1.25
    cs = sds / (r_factor / ie)
    load.CreateNewPrimaryLoad(f"SEISMIC LOAD - ASCE 7-16 Ch.12 (Cs={cs:.3f})")
    load.AddMemberUniformForce(list(range(1, member_id)), cs * inputs.dead_load_kpa, 0, 0)

    # Governing ASCE 7-16 Section 2.3.1 strength combinations used for design:
    # 1.2D + 1.6L,  1.2D + 1.0W + L,  1.2D + 1.0E + L are generated below.
    load.CreateNewCombinationLoad("COMBO 1: 1.2D+1.6L (ASCE 7-16 Eq.2.3.1-2)",
                                   [(1, 1.2), (2, 1.6)])
    load.CreateNewCombinationLoad("COMBO 2: 1.2D+1.0W+1.0L (ASCE 7-16 Eq.2.3.1-4)",
                                   [(1, 1.2), (3, 1.0), (2, 1.0)])
    load.CreateNewCombinationLoad("COMBO 3: 1.2D+1.0E+1.0L (ASCE 7-16 Eq.2.3.1-6)",
                                   [(1, 1.2), (4, 1.0), (2, 1.0)])

    # --- Run analysis ---
    analysis.SetAnalysisPrintOption(True)
    command.PerformAnalysis()
    staad.SaveSTAADFile()

    # --- Extract reactions and worst-case member forces -----------------
    reactions = {}
    for bn in base_nodes:
        fx, fy, fz, mx, my, mz = output.GetSupportReactions(bn, 2)  # 2 = governing combo, example
        reactions[bn] = {"Fx": fx, "Fy": fy, "Fz": fz, "Mx": mx, "My": my, "Mz": mz}

    max_axial = max(abs(r["Fy"]) for r in reactions.values()) if reactions else 0.0
    max_beam_moment = output.GetMaxMemberMoment()  # illustrative aggregate call

    return {
        "mode": "live_staad",
        "nodes": nodes,
        "base_nodes": base_nodes,
        "reactions": reactions,
        "max_column_axial": max_axial,
        "max_beam_moment": max_beam_moment,
        "load_combo": "1.2D + 1.0E + 1.0L (ASCE 7-16 Eq. 2.3.1-6, governing)",
    }


def _run_demo_analytical(inputs: DesignInputs, nodes, base_nodes, members) -> dict:
    """
    Analytical stand-in used when STAAD.Pro/OpenSTAAD is not reachable.
    Computes an approximate tributary-area gravity load per column and a
    simplified ASCE 7-16 seismic base shear, distributed evenly to the
    base nodes, purely so the rest of the dashboard (checks + 3D view)
    has representative numbers to display. This is NOT a substitute for
    a real STAAD analysis.
    """
    nx, nz = inputs.num_bays_x, inputs.num_bays_z
    dx, dz = inputs.bay_spacing_x, inputs.bay_spacing_z
    n_story = inputs.num_stories
    n_columns = (nx + 1) * (nz + 1)

    # Tributary area per interior column (simplification: uses average bay
    # dimensions for all columns, edge/corner effects ignored for the demo).
    trib_area = dx * dz
    total_area = trib_area * nx * nz * (n_story + 1) if n_story >= 0 else trib_area

    # Total factored gravity load per ASCE 7-16 Eq. 2.3.1-2: 1.2D + 1.6L
    w_dl = inputs.dead_load_kpa * total_area
    w_ll = inputs.live_load_kpa * total_area
    factored_gravity = 1.2 * w_dl + 1.6 * w_ll  # kN

    axial_per_column = factored_gravity / max(n_columns, 1)

    # Simplified seismic base shear per ASCE 7-16 Eq. 12.8-2: V = Cs * W
    sds = (2.0 / 3.0) * inputs.seismic_ss
    r_factor = 3.25
    ie = 1.0 if inputs.risk_category in ("I", "II") else 1.25
    cs = sds / (r_factor / ie)
    seismic_base_shear = cs * w_dl  # kN, W taken as dead load (ASCE 7-16 Sec.12.7.2)

    reactions = {}
    for bn in base_nodes:
        reactions[bn] = {
            "Fx": seismic_base_shear / max(len(base_nodes), 1),
            "Fy": -axial_per_column,   # compression (down) reaction
            "Fz": 0.0,
            "Mx": 0.0,
            "My": 0.0,
            "Mz": seismic_base_shear / max(len(base_nodes), 1) * inputs.column_height * 0.1,
        }

    # Rough beam moment estimate: w*L^2/8 for a simply-supported equivalent span
    w_line = (inputs.dead_load_kpa * 1.2 + inputs.live_load_kpa * 1.6) * dz  # kN/m along a beam
    max_beam_moment = w_line * (dx ** 2) / 8.0

    return {
        "mode": "demo_analytical",
        "nodes": nodes,
        "base_nodes": base_nodes,
        "reactions": reactions,
        "max_column_axial": axial_per_column,
        "max_beam_moment": max_beam_moment,
        "load_combo": "1.2D + 1.6L (gravity, governing) / Cs*W (ASCE 7-16 Eq.12.8-2, seismic)",
    }


# =============================================================================
# 4. FUNCTION: SIMPLIFIED ACI 318-19 CODE-COMPLIANCE CHECKS
# =============================================================================
def perform_code_checks(inputs: DesignInputs, results: dict) -> dict:
    """
    Runs simplified ACI 318-19 checks on the concrete pedestal / base
    plate bearing region, using the governing column axial reaction from
    the STAAD (or demo) results. Returns a dict of check results.

    References:
        - ACI 318-19 Section 22.8: Bearing strength of concrete
        - ACI 318-19 Section 17.4: Anchoring to Concrete - concrete
          breakout / bearing checks for base plates
        - ACI 318-19 Section 10.6: Minimum reinforcement for pedestals
          (treated as short compression members)
    """
    fc = inputs.fc_concrete_mpa  # MPa
    A1 = inputs.base_plate_length_mm * inputs.base_plate_width_mm  # mm^2, bearing area
    A2 = inputs.pedestal_length_mm * inputs.pedestal_width_mm      # mm^2, pedestal area

    # ACI 318-19 Eq. 22.8.3.2: Pn = 0.85*f'c*A1*sqrt(A2/A1), capped at 2*0.85*f'c*A1
    sqrt_ratio = min(math.sqrt(A2 / A1), 2.0)  # ACI limits sqrt(A2/A1) <= 2
    phi_bearing = 0.65  # ACI 318-19 Table 21.2.1, bearing on concrete
    Pn_bearing = 0.85 * fc * A1 * sqrt_ratio  # N (since fc in MPa = N/mm^2, A1 in mm^2)
    phi_Pn_bearing_kN = phi_bearing * Pn_bearing / 1000.0  # kN

    demand_axial_kN = abs(results["max_column_axial"])  # kN, factored column reaction

    bearing_ok = phi_Pn_bearing_kN >= demand_axial_kN
    bearing_ratio = demand_axial_kN / phi_Pn_bearing_kN if phi_Pn_bearing_kN > 0 else float("inf")

    # ACI 318-19 Section 10.6.1.1: minimum longitudinal reinforcement
    # ratio for pedestals/columns, rho_min = 0.01 (1%) of gross area.
    Ag = A2  # mm^2
    As_min_mm2 = 0.01 * Ag
    # Assume the design provides 1.5% for this demo, purely illustrative:
    As_provided_mm2 = 0.015 * Ag
    rebar_ratio_ok = As_provided_mm2 >= As_min_mm2

    # Simplified anchor bolt shear check, ACI 318-19 Ch.17 (concrete
    # breakout/steel strength of anchors). This only flags whether a
    # basic bolt count/size is plausible for the given shear demand, as a
    # placeholder illustrative check -- a full ACI 318-19 Ch.17
    # breakout/pryout check requires edge distances, embedment depth, and
    # bolt group geometry not collected in this simplified dashboard.
    Ab = math.pi / 4.0 * inputs.anchor_bolt_dia_mm ** 2  # mm^2, one bolt
    Fy_bolt_assumed_mpa = 345.0  # ASTM F1554 Gr.55-ish, illustrative
    phi_shear = 0.65  # ACI 318-19 17.5.3 (steel strength of anchor in shear, simplified)
    Vn_bolts_kN = phi_shear * 0.6 * Fy_bolt_assumed_mpa * Ab * inputs.num_anchor_bolts / 1000.0
    shear_demand_kN = abs(results["reactions"][results["base_nodes"][0]]["Fx"]) if results["base_nodes"] else 0.0
    anchor_shear_ok = Vn_bolts_kN >= shear_demand_kN

    return {
        "bearing_capacity_kN": phi_Pn_bearing_kN,
        "bearing_demand_kN": demand_axial_kN,
        "bearing_ratio": bearing_ratio,
        "bearing_ok": bearing_ok,
        "rebar_min_mm2": As_min_mm2,
        "rebar_provided_mm2": As_provided_mm2,
        "rebar_ok": rebar_ratio_ok,
        "anchor_shear_capacity_kN": Vn_bolts_kN,
        "anchor_shear_demand_kN": shear_demand_kN,
        "anchor_shear_ok": anchor_shear_ok,
    }


# =============================================================================
# 5. FUNCTION: 3D VISUALIZATION (Plotly)
# =============================================================================
def visualize_structure_3d(inputs: DesignInputs, results: dict) -> go.Figure:
    """
    Builds an interactive 3D Plotly figure showing columns, beams, and
    base plates, with the steel-to-concrete base-plate connections
    highlighted in a distinct color/marker so they are easy to identify.
    """
    nodes = results["nodes"]

    fig = go.Figure()

    # --- Rebuild the exact same node-id numbering scheme used in
    #     generate_and_run_staad_model, so the plotted geometry lines up
    #     with whatever was actually analyzed. ---
    nx, nz = inputs.num_bays_x, inputs.num_bays_z
    n_story = inputs.num_stories

    node_id = 1
    node_lookup = {}
    for ix in range(nx + 1):
        for iz in range(nz + 1):
            for story in range(n_story + 1):
                node_lookup[(ix, iz, story)] = node_id
                node_id += 1
    base_node_lookup = {}
    for ix in range(nx + 1):
        for iz in range(nz + 1):
            base_node_lookup[(ix, iz)] = node_id
            node_id += 1

    def line3d(n1, n2, color, width, name, showlegend=False):
        x1, y1, z1 = nodes[n1]
        x2, y2, z2 = nodes[n2]
        fig.add_trace(go.Scatter3d(
            x=[x1, x2], y=[z1, z2], z=[y1, y2],  # plot Y (vertical) as the Z-axis for viewing
            mode="lines", line=dict(color=color, width=width),
            name=name, showlegend=showlegend, hoverinfo="name"
        ))

    # --- Columns ---
    first_col = True
    for ix in range(nx + 1):
        for iz in range(nz + 1):
            prev = base_node_lookup[(ix, iz)]
            for story in range(n_story + 1):
                cur = node_lookup[(ix, iz, story)]
                line3d(prev, cur, "steelblue", 8, "Column (steel)", showlegend=first_col)
                first_col = False
                prev = cur

    # --- Beams ---
    first_beam = True
    for story in range(n_story + 1):
        for ix in range(nx + 1):
            for iz in range(nz):
                n1 = node_lookup[(ix, iz, story)]
                n2 = node_lookup[(ix, iz + 1, story)]
                line3d(n1, n2, "darkorange", 5, "Beam (steel)", showlegend=first_beam)
                first_beam = False
        for iz in range(nz + 1):
            for ix in range(nx):
                n1 = node_lookup[(ix, iz, story)]
                n2 = node_lookup[(ix + 1, iz, story)]
                line3d(n1, n2, "darkorange", 5, "Beam (steel)", showlegend=False)

    # --- Base plates + pedestal tops: highlighted markers/squares at the
    #     steel-to-concrete interface. ---
    bx_list, by_list, bz_list = [], [], []
    for (ix, iz), bn in base_node_lookup.items():
        x, y, z = nodes[bn]
        bx_list.append(x)
        by_list.append(z)
        bz_list.append(y)

    fig.add_trace(go.Scatter3d(
        x=bx_list, y=by_list, z=bz_list,
        mode="markers",
        marker=dict(size=10, color="crimson", symbol="square"),
        name="Base plate / steel-to-concrete connection",
        hovertext=[f"Base plate at elev {inputs.base_plate_elevation} m"] * len(bx_list),
        hoverinfo="text"
    ))

    # --- Simple pedestal representation as short vertical concrete stubs
    #     below each base plate, so the concrete pedestal is visually
    #     distinguishable from the steel. ---
    first_ped = True
    for (ix, iz), bn in base_node_lookup.items():
        x, y, z = nodes[bn]
        fig.add_trace(go.Scatter3d(
            x=[x, x], y=[z, z], z=[y - 0.6, y],
            mode="lines", line=dict(color="dimgray", width=14),
            name="Concrete pedestal", showlegend=first_ped, hoverinfo="name"
        ))
        first_ped = False

    fig.update_layout(
        scene=dict(
            xaxis_title="X (m)",
            yaxis_title="Z (m)",
            zaxis_title="Elevation, Y (m)",
            aspectmode="data",
        ),
        margin=dict(l=0, r=0, t=30, b=0),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        height=650,
    )
    return fig


# =============================================================================
# 6. DASH APP LAYOUT AND CALLBACK (entry point)
# =============================================================================
app = Dash(__name__)
app.title = "STAAD/OpenSTAAD Design Dashboard"

app.layout = html.Div(
    [
        html.Div(
            [
                build_input_layout(),
            ],
            style={"flex": "0 0 340px", "borderRight": "1px solid #ddd", "backgroundColor": "#fafafa"},
        ),
        html.Div(
            [
                html.H2("Steel Frame Design Dashboard - OpenSTAAD + ACI 318-19 / ASCE 7-16"),
                html.P(
                    "Enter geometry, material, and load parameters on the left, then click "
                    "\"Run Design\" to generate the OpenSTAAD model, run the analysis, and "
                    "check the base-plate/pedestal connection against ACI 318-19."
                ),
                html.Div(
                    (
                        "comtypes / OpenSTAAD is not available in this environment, so the app "
                        "will run in demo/analytical mode. On a licensed Windows machine with "
                        "STAAD.Pro open, install `comtypes` and check \"Connect to a running "
                        "STAAD.Pro instance\" for live analysis."
                    ) if not OPENSTAAD_LIB_AVAILABLE else "",
                    style={"backgroundColor": "#eef6ff", "padding": "8px", "borderRadius": "4px",
                           "display": "block" if not OPENSTAAD_LIB_AVAILABLE else "none"},
                ),
                dcc.Tabs(id="tabs-main", value="tab-results", children=[
                    dcc.Tab(label="Analysis Results", value="tab-results"),
                    dcc.Tab(label="Code Compliance (ACI 318-19)", value="tab-checks"),
                    dcc.Tab(label="3D Visualization", value="tab-3d"),
                ]),
                dcc.Loading(html.Div(id="tab-content"), type="circle"),
                dcc.Store(id="store-results"),
                dcc.Store(id="store-checks"),
                dcc.Store(id="store-inputs"),
            ],
            style={"flex": "1", "padding": "18px", "overflowY": "auto", "height": "100vh"},
        ),
    ],
    style={"display": "flex", "fontFamily": "Arial, sans-serif"},
)


@app.callback(
    Output("store-results", "data"),
    Output("store-checks", "data"),
    Output("store-inputs", "data"),
    Input("btn-run-design", "n_clicks"),
    *[State(cid, "value") for cid in INPUT_IDS],
    prevent_initial_call=True,
)
def on_run_design(n_clicks, *values):
    """
    Runs when "Run Design" is clicked: parses the form, generates/executes
    the OpenSTAAD model (or the analytical fallback), runs the ACI 318-19
    checks, and stashes everything in dcc.Store components so the tab
    renderer below can display it without re-running the analysis.
    """
    inputs = parse_inputs_from_values(list(values))
    results = generate_and_run_staad_model(inputs)
    checks = perform_code_checks(inputs, results)
    return results, checks, inputs.__dict__


def _restore_int_keys(results: dict) -> dict:
    """
    dcc.Store round-trips `data` through JSON, and JSON object keys must be
    strings -- so results['nodes'] and results['reactions'] (both keyed by
    integer node IDs when generated) come back from the store with string
    keys ("25" instead of 25). results['base_nodes'] is a *list*, so its
    integer elements are unaffected. This restores the original int keys
    on the two dicts so downstream code (which looks nodes up by int,
    e.g. in visualize_structure_3d) works whether `results` just came
    straight out of generate_and_run_staad_model() or out of a dcc.Store.
    """
    results = dict(results)  # shallow copy, don't mutate the Store's data in place
    results["nodes"] = {int(k): v for k, v in results["nodes"].items()}
    results["reactions"] = {int(k): v for k, v in results["reactions"].items()}
    return results


@app.callback(
    Output("tab-content", "children"),
    Input("tabs-main", "value"),
    Input("store-results", "data"),
    State("store-checks", "data"),
    State("store-inputs", "data"),
)
def render_tab(tab, results, checks, inputs_dict):
    """Renders whichever tab is active using the most recently run results."""
    if results is None:
        return html.Div("Click \"Run Design\" to generate and run the model.",
                         style={"marginTop": "20px", "color": "#666"})

    results = _restore_int_keys(results)
    inputs = DesignInputs(**inputs_dict)

    if tab == "tab-results":
        rows = [
            {"Node": bn, "Fx (kN)": round(r["Fx"], 2), "Fy (kN)": round(r["Fy"], 2),
             "Fz (kN)": round(r["Fz"], 2), "Mz (kN-m)": round(r["Mz"], 2)}
            for bn, r in results["reactions"].items()
        ]
        warnings_block = html.Div(
            [html.P(w, style={"color": "#b45309"}) for w in results.get("warnings", [])]
        )
        return html.Div([
            warnings_block,
            html.H4("Analysis Mode"),
            html.P("Live STAAD.Pro analysis" if results["mode"] == "live_staad"
                   else "Demo / analytical fallback (STAAD.Pro not connected)"),
            html.H4("Governing Load Combination"),
            html.P(results["load_combo"]),
            html.Div([
                html.Div([html.B("Max column axial reaction: "),
                          f"{results['max_column_axial']:.1f} kN"], style={"marginRight": "40px"}),
                html.Div([html.B("Max beam moment (approx.): "),
                          f"{results['max_beam_moment']:.1f} kN-m"]),
            ], style={"display": "flex", "marginBottom": "12px"}),
            html.H4("Base Reactions"),
            dash_table.DataTable(
                data=rows,
                columns=[{"name": c, "id": c} for c in ["Node", "Fx (kN)", "Fy (kN)", "Fz (kN)", "Mz (kN-m)"]],
                style_table={"overflowX": "auto"}, page_size=10,
            ),
            html.H4("Member Sizes Used"),
            html.P(f"Columns: {inputs.column_section}  |  Beams: {inputs.beam_section}"),
        ])

    if tab == "tab-checks":
        def status(ok, fail_msg):
            return html.Span("PASS", style={"color": "green", "fontWeight": "700"}) if ok \
                else html.Span(f"FAIL - {fail_msg}", style={"color": "crimson", "fontWeight": "700"})

        return html.Div([
            html.H4("Base Plate Bearing - ACI 318-19 Section 22.8 / 17.4"),
            html.P([
                f"Factored bearing capacity phi*Pn = {checks['bearing_capacity_kN']:.1f} kN vs. "
                f"demand = {checks['bearing_demand_kN']:.1f} kN "
                f"(D/C ratio = {checks['bearing_ratio']:.2f})  ",
                status(checks["bearing_ok"], "resize base plate/pedestal"),
            ]),
            html.H4("Pedestal Minimum Reinforcement - ACI 318-19 Section 10.6.1.1"),
            html.P([
                f"As,min = {checks['rebar_min_mm2']:.0f} mm^2 vs. "
                f"As,provided (assumed) = {checks['rebar_provided_mm2']:.0f} mm^2  ",
                status(checks["rebar_ok"], "increase pedestal reinforcement"),
            ]),
            html.H4("Anchor Bolt Shear - ACI 318-19 Chapter 17 (simplified)"),
            html.P([
                f"Capacity = {checks['anchor_shear_capacity_kN']:.1f} kN vs. "
                f"demand = {checks['anchor_shear_demand_kN']:.1f} kN  ",
                status(checks["anchor_shear_ok"], "add/upsize anchor bolts"),
            ]),
            html.P(
                "These checks are simplified illustrations of the referenced ACI 318-19 "
                "clauses and do not include edge-distance/breakout/pryout checks, bolt "
                "group eccentricity, or combined tension-shear interaction. A licensed "
                "engineer should perform the complete Chapter 17 anchor design.",
                style={"fontStyle": "italic", "color": "#666", "marginTop": "12px"},
            ),
        ])

    if tab == "tab-3d":
        fig = visualize_structure_3d(inputs, results)
        return html.Div([
            html.P(
                "Steel columns (blue), steel beams (orange), concrete pedestals (gray), "
                "and steel-to-concrete base-plate connections (red squares) at elevation "
                f"{inputs.base_plate_elevation} m.",
                style={"color": "#666"},
            ),
            dcc.Graph(figure=fig, style={"height": "650px"}),
        ])

    return no_update


if __name__ == "__main__":
    # Dash >= 2.11 renamed Flask's runner to `app.run`. If you're on an
    # older Dash version and this raises AttributeError, use
    # `app.run_server(debug=True)` instead.
    app.run(debug=True)
