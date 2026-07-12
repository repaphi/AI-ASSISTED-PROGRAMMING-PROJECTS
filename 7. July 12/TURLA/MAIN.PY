"""
Isolated Square Pad Footing Design per ACI 318-19
===================================================
Strength Design (LRFD) methodology, translated from the calculation
package "Design Procedure: Isolated Square Pad Footing (ACI 318-19)".

Units: US Customary (kips, psi, ft, in) unless noted.

DISCLAIMER: For preliminary / educational use. Must be verified and
sealed by a licensed structural engineer using project-specific
loads, geotechnical data, and the governing code edition/printing.
"""

import math
from dataclasses import dataclass, field

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from mpl_toolkits.mplot3d.art3d import Poly3DCollection


# ---------------------------------------------------------------------
# 1. DESIGN INPUTS
# ---------------------------------------------------------------------

@dataclass
class DesignInputs:
    # Loads
    D: float = 200.0          # Dead load, service (kips)
    L: float = 150.0          # Live load, service (kips)
    load_factor_D: float = 1.2
    load_factor_L: float = 1.6
    M: float = 0.0            # Applied moment, service (kip-ft) -- 0 = concentric

    # Geotechnical
    qa: float = 4.0           # Allowable soil bearing pressure, service (ksf)
    Df: float = 4.0           # Footing base depth below grade (ft)
    gamma_soil: float = 0.120 # Soil unit weight (kcf)

    # Column
    c1: float = 20.0          # Column dimension 1 (in)
    c2: float = 20.0          # Column dimension 2 (in), = c1 for square column
    col_bars: int = 8         # Number of column vertical bars (for dowel matching)
    col_bar_size: int = 8     # Column bar size (e.g., 8 = #8)

    # Materials
    fc: float = 4000.0        # f'c (psi)
    fy: float = 60000.0       # fy (psi)
    gamma_conc: float = 0.150 # Concrete unit weight (kcf)
    lam: float = 1.0          # lambda, normal-weight concrete (ACI 19.2.4.2)

    # Cover / trial geometry
    cover: float = 3.0        # Clear cover, cast against earth (in) (ACI Table 20.6.1.3.1)
    trial_h: float = 24.0     # Trial footing thickness (in)
    trial_bar_size: int = 8   # Trial flexural bar size (e.g., 8 = #8)

    # Strength reduction factors (ACI 21.2.1)
    phi_shear: float = 0.75
    phi_flexure: float = 0.90

    # Spacing / detailing limits
    max_spacing_limit: float = 18.0  # in (lesser of 3h or 18 in, ACI 8.7.2.2)


# Bar area lookup (in^2) for standard US bar sizes
BAR_AREA = {3: 0.11, 4: 0.20, 5: 0.31, 6: 0.44, 7: 0.60, 8: 0.79,
            9: 1.00, 10: 1.27, 11: 1.56}
BAR_DIAM = {3: 0.375, 4: 0.500, 5: 0.625, 6: 0.750, 7: 0.875, 8: 1.000,
            9: 1.128, 10: 1.270, 11: 1.410}


@dataclass
class DesignResults:
    Ps: float = 0.0
    Pu: float = 0.0
    qa_net: float = 0.0
    A_req: float = 0.0
    B: float = 0.0
    L: float = 0.0
    q_service: float = 0.0
    qu: float = 0.0
    d: float = 0.0
    punching: dict = field(default_factory=dict)
    one_way: dict = field(default_factory=dict)
    flexure: dict = field(default_factory=dict)
    dowels: dict = field(default_factory=dict)
    checks: list = field(default_factory=list)


# ---------------------------------------------------------------------
# 2. STEP FUNCTIONS
# ---------------------------------------------------------------------

def step1_footing_area(inp: DesignInputs, res: DesignResults):
    """Determine required footing plan area from service loads and
    net allowable soil bearing pressure (ACI 13.2.6.1)."""
    res.Ps = inp.D + inp.L
    res.Pu = inp.load_factor_D * inp.D + inp.load_factor_L * inp.L

    footing_wt = (inp.trial_h / 12.0) * inp.gamma_conc          # ksf
    surcharge = (inp.Df - inp.trial_h / 12.0) * inp.gamma_soil  # ksf
    res.qa_net = inp.qa - footing_wt - surcharge

    res.A_req = res.Ps / res.qa_net
    side = math.sqrt(res.A_req)

    # Round up to nearest 0.25 ft (typical practice), with a margin
    def round_up(x, inc=0.25):
        return math.ceil(x / inc) * inc

    B = round_up(side)
    res.B, res.L = B, B  # square footing
    res.q_service = res.Ps / (res.B * res.L)

    res.checks.append((
        "Service bearing pressure",
        res.q_service, res.qa_net,
        res.q_service <= res.qa_net
    ))
    return res


def step3_factored_pressure(inp: DesignInputs, res: DesignResults):
    """Factored net soil pressure for structural design."""
    res.qu = res.Pu / (res.B * res.L)
    return res


def step4_punching_shear(inp: DesignInputs, res: DesignResults):
    """Two-way (punching) shear check at d/2 from column face
    (ACI 22.6.4.1, 22.6.5.2)."""
    db = BAR_DIAM[inp.trial_bar_size]
    d = inp.trial_h - inp.cover - db
    res.d = d

    b0 = 4 * (inp.c1 + d)                       # in, square column
    side_ft = (inp.c1 + d) / 12.0
    Vu = res.Pu - res.qu * side_ft ** 2

    sqrt_fc = math.sqrt(inp.fc)
    beta = inp.c1 / inp.c2
    alpha_s = 40  # interior column (ACI 22.6.5.3)

    Vc_a = 4 * inp.lam * sqrt_fc * b0 * d
    Vc_b = (2 + 4 / beta) * inp.lam * sqrt_fc * b0 * d
    Vc_c = (alpha_s * d / b0 + 2) * inp.lam * sqrt_fc * b0 * d
    Vc = min(Vc_a, Vc_b, Vc_c) / 1000.0  # kips

    phiVc = inp.phi_shear * Vc

    res.punching = dict(b0=b0, Vu=Vu, Vc_a=Vc_a / 1000, Vc_b=Vc_b / 1000,
                         Vc_c=Vc_c / 1000, Vc=Vc, phiVc=phiVc)
    res.checks.append(("Two-way (punching) shear", Vu, phiVc, Vu <= phiVc))
    return res


def step5_one_way_shear(inp: DesignInputs, res: DesignResults):
    """One-way (beam) shear check at distance d from column face
    (ACI 22.5.1.2, 22.5.5.1)."""
    d = res.d
    x = (res.L - inp.c1 / 12.0) / 2.0 - d / 12.0  # ft, critical section to edge
    Vu = res.qu * res.B * x

    sqrt_fc = math.sqrt(inp.fc)
    phiVc = inp.phi_shear * 2 * inp.lam * sqrt_fc * (res.B * 12) * d / 1000.0

    res.one_way = dict(x=x, Vu=Vu, phiVc=phiVc)
    res.checks.append(("One-way shear", Vu, phiVc, Vu <= phiVc))
    return res


def step6_7_flexure(inp: DesignInputs, res: DesignResults):
    """Flexural design at column face + minimum reinforcement check
    (ACI 13.2.7.1, 13.3.3.3, 7.6.1.1)."""
    d = res.d
    b = res.B * 12.0  # in
    l = (res.L - inp.c1 / 12.0) / 2.0  # ft, cantilever length

    Mu = res.qu * res.B * l ** 2 / 2.0        # kip-ft
    Mu_lbin = Mu * 12000.0                    # lb-in

    Ru = Mu_lbin / (inp.phi_flexure * b * d ** 2)  # psi

    term = 1 - (2 * Ru) / (0.85 * inp.fc)
    if term < 0:
        raise ValueError("Section too small for flexure -- increase thickness.")
    rho = (0.85 * inp.fc / inp.fy) * (1 - math.sqrt(term))

    As_req = rho * b * d
    As_min = 0.0018 * b * inp.trial_h  # ACI 7.6.1.1 (S&T minimum, governs footings)

    As_design = max(As_req, As_min)
    governs = "Minimum (S&T)" if As_min > As_req else "Flexural strength"

    # Bar selection
    Ab = BAR_AREA[inp.trial_bar_size]
    n_bars = math.ceil(As_design / Ab)

    # iterate bar count upward until spacing requirement satisfied
    db = BAR_DIAM[inp.trial_bar_size]
    while True:
        avail_width = b - 2 * inp.cover - db
        spacing = avail_width / (n_bars - 1)
        max_sp = min(3 * inp.trial_h, inp.max_spacing_limit)
        if spacing <= max_sp:
            break
        n_bars += 1

    As_provided = n_bars * Ab

    res.flexure = dict(Mu=Mu, Ru=Ru, rho=rho, As_req=As_req, As_min=As_min,
                        As_design=As_design, governs=governs,
                        bar_size=inp.trial_bar_size, n_bars=n_bars,
                        As_provided=As_provided, spacing=spacing,
                        max_spacing=max_sp)
    res.checks.append(("Flexural reinforcement (As)",
                        As_design, As_provided, As_provided >= As_design))
    res.checks.append(("Bar spacing", spacing, max_sp, spacing <= max_sp))
    return res


def step8_development_length(inp: DesignInputs, res: DesignResults):
    """Straight-bar tension development length check (ACI 25.4.2).
    Simplified equation for uncoated bottom bars, #7 and larger,
    with cover/spacing >= db (ACI Table 25.4.2.2, Case 1)."""
    db = BAR_DIAM[res.flexure['bar_size']]
    psi_t, psi_e, psi_s = 1.0, 1.0, 1.0
    sqrt_fc = math.sqrt(inp.fc)

    ld = (inp.fy * psi_t * psi_e * psi_s) / (20.0 * inp.lam * sqrt_fc) * db
    ld = max(ld, 12.0)  # ACI 25.4.2.1(b) minimum 12 in

    l = (res.L - inp.c1 / 12.0) / 2.0 * 12.0  # cantilever length, in
    avail = l - inp.cover

    res.flexure['ld_required'] = ld
    res.flexure['ld_available'] = avail
    res.checks.append(("Development length", ld, avail, ld <= avail))
    return res


def step9_dowels(inp: DesignInputs, res: DesignResults):
    """Compression development length for column dowels (ACI 25.4.9)."""
    db = BAR_DIAM[inp.col_bar_size]
    sqrt_fc = math.sqrt(inp.fc)
    ldc = max(0.02 * inp.fy * db / (inp.lam * sqrt_fc),
              0.0003 * inp.fy * db,
              8.0)  # 8 in minimum, ACI 25.4.9.1
    res.dowels = dict(n_bars=inp.col_bars, bar_size=inp.col_bar_size, ldc=ldc)
    return res


# ---------------------------------------------------------------------
# 3. DRIVER
# ---------------------------------------------------------------------

def design_footing(inp: DesignInputs) -> DesignResults:
    res = DesignResults()
    step1_footing_area(inp, res)
    step3_factored_pressure(inp, res)
    step4_punching_shear(inp, res)
    step5_one_way_shear(inp, res)
    step6_7_flexure(inp, res)
    step8_development_length(inp, res)
    step9_dowels(inp, res)
    return res


def print_report(inp: DesignInputs, res: DesignResults):
    print("=" * 70)
    print("ISOLATED PAD FOOTING DESIGN -- ACI 318-19")
    print("=" * 70)

    print(f"\nService load Ps = D + L           = {res.Ps:.1f} kips")
    print(f"Factored load Pu = 1.2D + 1.6L     = {res.Pu:.1f} kips")
    print(f"Net allowable soil pressure        = {res.qa_net:.3f} ksf")
    print(f"Required area A_req                = {res.A_req:.1f} ft^2")
    print(f"Selected footing                   = {res.B:.2f} ft x {res.L:.2f} ft "
          f"({res.B*res.L:.1f} ft^2)")
    print(f"Service bearing pressure check      = {res.q_service:.3f} ksf "
          f"<= {res.qa_net:.3f} ksf")
    print(f"Factored soil pressure qu           = {res.qu:.3f} ksf")
    print(f"Effective depth d                   = {res.d:.2f} in "
          f"(h = {inp.trial_h:.1f} in, cover = {inp.cover:.1f} in)")

    p = res.punching
    print(f"\n--- Two-way (punching) shear ---")
    print(f"b0 = {p['b0']:.1f} in")
    print(f"Vu = {p['Vu']:.1f} kips")
    print(f"Vc candidates: (a) {p['Vc_a']:.1f}  (b) {p['Vc_b']:.1f}  "
          f"(c) {p['Vc_c']:.1f} kips -> governs {p['Vc']:.1f} kips")
    print(f"phi*Vc = {p['phiVc']:.1f} kips")

    o = res.one_way
    print(f"\n--- One-way shear ---")
    print(f"Critical section x = {o['x']:.2f} ft from edge")
    print(f"Vu = {o['Vu']:.1f} kips   phi*Vc = {o['phiVc']:.1f} kips")

    f = res.flexure
    print(f"\n--- Flexure ---")
    print(f"Mu = {f['Mu']:.1f} kip-ft   Ru = {f['Ru']:.1f} psi   rho = {f['rho']:.5f}")
    print(f"As required (strength) = {f['As_req']:.2f} in^2")
    print(f"As minimum (ACI 7.6.1.1) = {f['As_min']:.2f} in^2")
    print(f"Governing: {f['governs']}  ->  As,design = {f['As_design']:.2f} in^2")
    print(f"Provide: {f['n_bars']}-#{f['bar_size']} bars each way "
          f"(As,provided = {f['As_provided']:.2f} in^2)")
    print(f"Spacing = {f['spacing']:.1f} in c/c  (limit = {f['max_spacing']:.1f} in)")
    print(f"Development length required = {f['ld_required']:.1f} in, "
          f"available = {f['ld_available']:.1f} in")

    d_ = res.dowels
    print(f"\n--- Dowels ---")
    print(f"Provide {d_['n_bars']}-#{d_['bar_size']} dowels, "
          f"embedment >= {d_['ldc']:.1f} in into footing")

    print(f"\n{'='*70}\nSUMMARY OF CODE CHECKS\n{'='*70}")
    print(f"{'Check':38s}{'Demand':>12s}{'Capacity':>12s}{'Status':>8s}")
    for name, demand, capacity, ok in res.checks:
        status = "OK" if ok else "NG"
        print(f"{name:38s}{demand:12.2f}{capacity:12.2f}{status:>8s}")

    all_ok = all(c[3] for c in res.checks)
    print(f"\nOVERALL: {'ALL CHECKS SATISFIED' if all_ok else 'ONE OR MORE CHECKS FAILED -- REVISE DESIGN'}")
    print(f"\nFINAL FOOTING: {res.B:.2f} ft x {res.L:.2f} ft x {inp.trial_h:.0f} in thick")
    print(f"REINFORCEMENT: {f['n_bars']}-#{f['bar_size']} bars each way, bottom, "
          f"{f['spacing']:.1f} in c/c")


# ---------------------------------------------------------------------
# 4. 3D VISUALIZATION (matplotlib mplot3d — pure Python, no browser)
# ---------------------------------------------------------------------

def _box_faces(origin, size):
    """Return the 6 quad faces of a box for Poly3DCollection.
    origin = (x, y, z) of the box's min corner; size = (dx, dy, dz)."""
    x0, y0, z0 = origin
    dx, dy, dz = size
    x1, y1, z1 = x0 + dx, y0 + dy, z0 + dz

    v = np.array([
        [x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],  # bottom
        [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1],  # top
    ])
    faces = [
        [v[0], v[1], v[2], v[3]],  # bottom
        [v[4], v[5], v[6], v[7]],  # top
        [v[0], v[1], v[5], v[4]],  # front
        [v[2], v[3], v[7], v[6]],  # back
        [v[1], v[2], v[6], v[5]],  # right
        [v[0], v[3], v[7], v[4]],  # left
    ]
    return faces


def _add_box(ax, origin, size, color, alpha=1.0, edgecolor='#40444c', lw=0.5):
    faces = _box_faces(origin, size)
    box = Poly3DCollection(faces, facecolor=color, edgecolor=edgecolor,
                            linewidths=lw, alpha=alpha)
    ax.add_collection3d(box)


def _add_bar(ax, p0, p1, color, lw=2.5):
    """Draw a straight reinforcing bar as a thick line segment."""
    xs, ys, zs = zip(p0, p1)
    ax.plot(xs, ys, zs, color=color, linewidth=lw, solid_capstyle='round')


def build_3d_geometry(inp: DesignInputs, res: DesignResults):
    """Compute all geometry (footing, column, rebar, dowels) in feet,
    centered in plan at the origin, footing base at z=0 (up-axis = Z)."""
    B, L, h = res.B, res.L, inp.trial_h / 12.0
    colW, colL, colStub = inp.c1 / 12.0, inp.c2 / 12.0, 3.0
    cover = inp.cover / 12.0
    barDia = BAR_DIAM[res.flexure['bar_size']] / 12.0
    n = res.flexure['n_bars']
    spacing = res.flexure['spacing'] / 12.0

    geo = {}
    geo['footing_origin'] = (-B/2, -L/2, 0.0)
    geo['footing_size'] = (B, L, h)
    geo['column_origin'] = (-colW/2, -colL/2, h)
    geo['column_size'] = (colW, colL, colStub)

    # rebar mat: two orthogonal layers near the bottom
    y_lower = cover + barDia/2
    y_upper = y_lower + barDia
    start = -B/2 + cover + barDia/2

    bars_x = []  # bars running along Y (spaced along X) -- lower layer
    for i in range(n):
        x = start + i * spacing
        bars_x.append(((x, -L/2 + cover, y_lower), (x, L/2 - cover, y_lower)))

    bars_z = []  # bars running along X (spaced along Y) -- upper layer
    for i in range(n):
        yv = start + i * spacing
        bars_z.append(((-B/2 + cover, yv, y_upper), (B/2 - cover, yv, y_upper)))

    geo['bars_x'] = bars_x
    geo['bars_z'] = bars_z

    # dowels around column perimeter
    inset = 2.5/12
    hw, hl = colW/2 - inset, colL/2 - inset
    pts = [(-hw,-hl), (0,-hl), (hw,-hl), (hw,0), (hw,hl), (0,hl), (-hw,hl), (-hw,0)]
    y_bot = cover
    y_top = h + res.dowels['ldc'] / 12.0
    dowels = [((px, py, y_bot), (px, py, y_top)) for px, py in pts]
    geo['dowels'] = dowels

    return geo


def _draw_scene(ax, inp, res, geo, show_rebar=True, show_dowels=True,
                 show_column=True, footing_alpha=0.35):
    _add_box(ax, geo['footing_origin'], geo['footing_size'],
             color='#b7b3aa', alpha=footing_alpha)
    if show_column:
        _add_box(ax, geo['column_origin'], geo['column_size'],
                 color='#8f8b82', alpha=0.9)
    if show_rebar:
        for p0, p1 in geo['bars_x']:
            _add_bar(ax, p0, p1, color='#d9822b', lw=2.2)
        for p0, p1 in geo['bars_z']:
            _add_bar(ax, p0, p1, color='#b8621b', lw=2.2)
    if show_dowels:
        for p0, p1 in geo['dowels']:
            _add_bar(ax, p0, p1, color='#e0a355', lw=2.5)

    B, L, _ = geo['footing_size']
    _, _, h = geo['footing_size']
    _, _, colStub = geo['column_size']
    top = h + colStub

    ax.set_xlim(-B*0.65, B*0.65)
    ax.set_ylim(-L*0.65, L*0.65)
    ax.set_zlim(0, top*1.15)
    ax.set_box_aspect((B, L, top*1.15*2))
    ax.set_xlabel('X (ft)')
    ax.set_ylabel('Y (ft)')
    ax.set_zlabel('Z (ft)')
    ax.set_facecolor('#14161a')


def plot_3d_footing(inp: DesignInputs, res: DesignResults,
                     out_path="pad_footing_3d.png"):
    """Static multi-view 3D rendering: isometric, plan, and elevation."""
    geo = build_3d_geometry(inp, res)

    fig = plt.figure(figsize=(15, 6), facecolor='#14161a')

    ax1 = fig.add_subplot(1, 3, 1, projection='3d')
    _draw_scene(ax1, inp, res, geo)
    ax1.view_init(elev=22, azim=-55)
    ax1.set_title('Isometric', color='#e8e6df', fontsize=11)

    ax2 = fig.add_subplot(1, 3, 2, projection='3d')
    _draw_scene(ax2, inp, res, geo, show_column=False)
    ax2.view_init(elev=89, azim=-90)
    ax2.set_title('Plan (rebar mat)', color='#e8e6df', fontsize=11)

    ax3 = fig.add_subplot(1, 3, 3, projection='3d')
    _draw_scene(ax3, inp, res, geo)
    ax3.view_init(elev=4, azim=-90)
    ax3.set_title('Elevation', color='#e8e6df', fontsize=11)

    for ax in (ax1, ax2, ax3):
        ax.tick_params(colors='#9a9890', labelsize=7)
        ax.xaxis.pane.set_facecolor('#1b1e24')
        ax.yaxis.pane.set_facecolor('#1b1e24')
        ax.zaxis.pane.set_facecolor('#1b1e24')

    fig.suptitle(
        f"Pad Footing — {geo['footing_size'][0]:.2f} x {geo['footing_size'][1]:.2f} ft "
        f"x {inp.trial_h:.0f} in  |  {res.flexure['n_bars']}-#{res.flexure['bar_size']} "
        f"bars each way @ {res.flexure['spacing']:.1f} in c/c  |  ACI 318-19",
        color='#e8e6df', fontsize=12
    )
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    fig.savefig(out_path, dpi=160, facecolor=fig.get_facecolor())
    plt.close(fig)
    return out_path


def animate_3d_footing(inp: DesignInputs, res: DesignResults,
                        out_path="pad_footing_3d_rotation.gif",
                        n_frames=72, elev=20):
    """Rotating 360-degree GIF of the footing model, pure matplotlib."""
    geo = build_3d_geometry(inp, res)

    fig = plt.figure(figsize=(7, 7), facecolor='#14161a')
    ax = fig.add_subplot(111, projection='3d')
    _draw_scene(ax, inp, res, geo)
    ax.tick_params(colors='#9a9890', labelsize=7)
    ax.xaxis.pane.set_facecolor('#1b1e24')
    ax.yaxis.pane.set_facecolor('#1b1e24')
    ax.zaxis.pane.set_facecolor('#1b1e24')
    ax.set_title(
        f"{geo['footing_size'][0]:.2f} x {geo['footing_size'][1]:.2f} ft x "
        f"{inp.trial_h:.0f} in | {res.flexure['n_bars']}-#{res.flexure['bar_size']} EW",
        color='#e8e6df', fontsize=10
    )

    def update(frame):
        ax.view_init(elev=elev, azim=frame * 360 / n_frames)
        return []

    anim = animation.FuncAnimation(fig, update, frames=n_frames, interval=60, blit=False)
    anim.save(out_path, writer='pillow', fps=16, dpi=110,
              savefig_kwargs={'facecolor': fig.get_facecolor()})
    plt.close(fig)
    return out_path


# ---------------------------------------------------------------------
# 5. DESIGN DASHBOARD (single-page summary, pure matplotlib)
# ---------------------------------------------------------------------

_DASH_BG = '#14161a'
_DASH_PANEL = '#1b1e24'
_DASH_BORDER = '#2c3038'
_DASH_INK = '#e8e6df'
_DASH_DIM = '#9a9890'
_DASH_ACCENT = '#d9822b'
_DASH_BLUE = '#5b8fb0'
_DASH_GOOD = '#5fa87e'
_DASH_BAD = '#c25b52'


def _style_panel(ax, title=None):
    ax.set_facecolor(_DASH_PANEL)
    for spine in ax.spines.values():
        spine.set_color(_DASH_BORDER)
    ax.tick_params(colors=_DASH_DIM, labelsize=8)
    if title:
        ax.set_title(title, color=_DASH_INK, fontsize=11, loc='left',
                     fontweight='bold', pad=10)


def _draw_plan_view(ax, inp, res, geo):
    """Top-down plan: footing outline, column, rebar grid, dimensions."""
    _style_panel(ax, "PLAN VIEW")
    B, L, _ = geo['footing_size']

    ax.add_patch(plt.Rectangle((-B/2, -L/2), B, L, facecolor='#3a3d43',
                                edgecolor=_DASH_DIM, linewidth=1.2, zorder=1))
    colW, colL, _ = geo['column_size']
    ax.add_patch(plt.Rectangle((-colW/2, -colL/2), colW, colL,
                                facecolor='#55585f', edgecolor=_DASH_INK,
                                linewidth=1.0, zorder=3))

    for p0, p1 in geo['bars_x']:
        ax.plot([p0[0], p1[0]], [p0[1], p1[1]], color=_DASH_ACCENT,
                linewidth=1.3, zorder=2, alpha=0.85)
    for p0, p1 in geo['bars_z']:
        ax.plot([p0[0], p1[0]], [p0[1], p1[1]], color='#b8621b',
                linewidth=1.3, zorder=2, alpha=0.85)

    off = 0.9
    ax.annotate('', xy=(B/2, L/2+off), xytext=(-B/2, L/2+off),
                arrowprops=dict(arrowstyle='<->', color=_DASH_BLUE, lw=1))
    ax.text(0, L/2+off+0.35, f"{B:.2f} ft", color=_DASH_BLUE, ha='center', fontsize=8)
    ax.annotate('', xy=(-B/2-off, L/2), xytext=(-B/2-off, -L/2),
                arrowprops=dict(arrowstyle='<->', color=_DASH_BLUE, lw=1))
    ax.text(-B/2-off-0.4, 0, f"{L:.2f} ft", color=_DASH_BLUE, ha='center',
            va='center', rotation=90, fontsize=8)

    n, sp = res.flexure['n_bars'], res.flexure['spacing']
    ax.text(0, -L/2-off-0.15,
            f"{n}-#{res.flexure['bar_size']} bars each way @ {sp:.1f} in c/c",
            color=_DASH_DIM, ha='center', fontsize=8)

    lim = max(B, L)/2 + off + 1.0
    ax.set_xlim(-lim, lim); ax.set_ylim(-lim, lim)
    ax.set_aspect('equal')
    ax.set_xticks([]); ax.set_yticks([])


def _draw_section_view(ax, inp, res, geo):
    """Elevation/section: footing thickness, column stub, cover, dowels."""
    _style_panel(ax, "SECTION")
    B, _, h = geo['footing_size']
    colW, _, colStub = geo['column_size']

    ax.add_patch(plt.Rectangle((-B/2, 0), B, h, facecolor='#3a3d43',
                                edgecolor=_DASH_DIM, linewidth=1.2, zorder=1))
    ax.add_patch(plt.Rectangle((-colW/2, h), colW, colStub,
                                facecolor='#55585f', edgecolor=_DASH_INK,
                                linewidth=1.0, zorder=2))

    barDia = BAR_DIAM[res.flexure['bar_size']] / 12.0
    cover = inp.cover / 12.0
    y_bar = cover + barDia/2
    ax.plot([-B/2+cover, B/2-cover], [y_bar, y_bar], color=_DASH_ACCENT,
            linewidth=3, zorder=3)

    for p0, p1 in geo['dowels'][:3]:
        pass  # dowels shown in plan/3D view; section keeps it clean

    off = 0.7
    ax.annotate('', xy=(B/2+off, 0), xytext=(B/2+off, h),
                arrowprops=dict(arrowstyle='<->', color=_DASH_BLUE, lw=1))
    ax.text(B/2+off+0.3, h/2, f"{inp.trial_h:.0f} in", color=_DASH_BLUE,
            rotation=90, va='center', fontsize=8)
    ax.text(0, -0.55, f"cover = {inp.cover:.0f} in", color=_DASH_DIM,
            ha='center', fontsize=7.5)

    lim = B/2 + off + 1.0
    top = h + colStub
    ax.set_xlim(-lim, lim); ax.set_ylim(-0.8, top*1.15)
    ax.set_aspect('equal')
    ax.set_xticks([]); ax.set_yticks([])


def _draw_utilization(ax, res):
    """Horizontal utilization-ratio bars for every code check."""
    _style_panel(ax, "CODE CHECK UTILIZATION")
    names = [c[0] for c in res.checks]
    ratios = [c[1]/c[2]*100 for c in res.checks]
    colors = [_DASH_GOOD if r <= 100 else _DASH_BAD for r in ratios]

    y = np.arange(len(names))
    ax.barh(y, ratios, color=colors, height=0.55, zorder=2)
    ax.axvline(100, color=_DASH_INK, linewidth=1, linestyle='--', zorder=1)
    ax.set_yticks(y)
    ax.set_yticklabels(names, color=_DASH_INK, fontsize=8.5)
    ax.set_xlabel('Demand / Capacity  (%)', color=_DASH_DIM, fontsize=8)
    ax.invert_yaxis()
    for yi, r in zip(y, ratios):
        ax.text(r + 2, yi, f"{r:.0f}%", va='center', color=_DASH_INK, fontsize=8)
    ax.set_xlim(0, max(115, max(ratios)*1.15))
    ax.grid(axis='x', color=_DASH_BORDER, linewidth=0.6)


def _draw_stats(ax, inp, res):
    """Key numeric results as a clean text block."""
    _style_panel(ax, "KEY RESULTS")
    ax.set_xticks([]); ax.set_yticks([])

    f = res.flexure
    lines = [
        ("Service load Ps",     f"{res.Ps:.1f} kips"),
        ("Factored load Pu",    f"{res.Pu:.1f} kips"),
        ("Footing plan",        f"{res.B:.2f} x {res.L:.2f} ft"),
        ("Thickness",           f"{inp.trial_h:.0f} in  (d = {res.d:.1f} in)"),
        ("Factored soil qu",    f"{res.qu:.2f} ksf"),
        ("Moment Mu",           f"{f['Mu']:.1f} kip-ft"),
        ("As required",         f"{f['As_design']:.2f} in\u00b2  ({f['governs']})"),
        ("As provided",         f"{f['n_bars']}-#{f['bar_size']}  "
                                 f"({f['As_provided']:.2f} in\u00b2)"),
        ("Bar spacing",         f"{f['spacing']:.1f} in c/c"),
        ("Dowels",              f"{res.dowels['n_bars']}-#{res.dowels['bar_size']}, "
                                 f"ldc \u2265 {res.dowels['ldc']:.1f} in"),
    ]
    n = len(lines)
    for i, (label, value) in enumerate(lines):
        y = 1 - (i + 0.5) / n
        ax.text(0.02, y, label, color=_DASH_DIM, fontsize=8.5, va='center',
                transform=ax.transAxes)
        ax.text(0.98, y, value, color=_DASH_INK, fontsize=8.5, va='center',
                ha='right', transform=ax.transAxes, fontfamily='monospace')
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)


def _draw_status_banner(ax, inp, res):
    """Top banner: title + overall PASS/FAIL status."""
    ax.set_xticks([]); ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_facecolor(_DASH_BG)

    ax.text(0.0, 0.62, "PAD FOOTING DESIGN DASHBOARD", color=_DASH_INK,
            fontsize=17, fontweight='bold', transform=ax.transAxes)
    ax.text(0.0, 0.18, "ACI 318-19  \u00b7  strength design (LRFD)",
            color=_DASH_DIM, fontsize=10, transform=ax.transAxes)

    all_ok = all(c[3] for c in res.checks)
    status = "ALL CHECKS PASS" if all_ok else "CHECK(S) FAILED"
    color = _DASH_GOOD if all_ok else _DASH_BAD
    ax.text(1.0, 0.4, status, color=color, fontsize=15, fontweight='bold',
            ha='right', transform=ax.transAxes,
            bbox=dict(boxstyle='round,pad=0.4', facecolor=_DASH_PANEL,
                       edgecolor=color, linewidth=1.3))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)


def create_dashboard(inp: DesignInputs, res: DesignResults,
                      out_path="pad_footing_dashboard.png"):
    """Assemble a single-page engineering dashboard: plan view, section
    view, code-check utilization bars, and key results -- all in one PNG."""
    geo = build_3d_geometry(inp, res)

    fig = plt.figure(figsize=(16, 10), facecolor=_DASH_BG)
    gs = fig.add_gridspec(3, 3, height_ratios=[0.45, 2.1, 1.3],
                           width_ratios=[1.05, 1.0, 1.15],
                           hspace=0.35, wspace=0.28)

    ax_banner = fig.add_subplot(gs[0, :])
    ax_plan = fig.add_subplot(gs[1:, 0])
    ax_section = fig.add_subplot(gs[1, 1])
    ax_util = fig.add_subplot(gs[1, 2])
    ax_stats = fig.add_subplot(gs[2, 1])
    ax_table = fig.add_subplot(gs[2, 2])

    _draw_status_banner(ax_banner, inp, res)
    _draw_plan_view(ax_plan, inp, res, geo)
    _draw_section_view(ax_section, inp, res, geo)
    _draw_utilization(ax_util, res)
    _draw_stats(ax_stats, inp, res)

    _style_panel(ax_table, "CHECK SUMMARY")
    ax_table.set_xticks([]); ax_table.set_yticks([])
    col_labels = ["Check", "Demand", "Capacity", "Status"]
    cell_text, cell_colors = [], []
    for name, demand, capacity, ok in res.checks:
        cell_text.append([name, f"{demand:.1f}", f"{capacity:.1f}",
                           "OK" if ok else "NG"])
        cell_colors.append([_DASH_PANEL]*3 + [_DASH_GOOD if ok else _DASH_BAD])
    tbl = ax_table.table(cellText=cell_text, colLabels=col_labels,
                          cellColours=cell_colors, loc='center',
                          cellLoc='left', colLoc='left')
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(7.5)
    tbl.scale(1, 1.5)
    for (r, c), cell in tbl.get_celld().items():
        cell.set_edgecolor(_DASH_BORDER)
        cell.set_text_props(color=_DASH_INK)
        if r == 0:
            cell.set_text_props(color=_DASH_DIM, fontweight='bold')
            cell.set_facecolor(_DASH_PANEL)

    fig.savefig(out_path, dpi=150, facecolor=fig.get_facecolor())
    plt.close(fig)
    return out_path


# ---------------------------------------------------------------------
# 6. RUN
# ---------------------------------------------------------------------

if __name__ == "__main__":
    inputs = DesignInputs()          # edit values here for a new project
    results = design_footing(inputs)
    print_report(inputs, results)

    png_path = plot_3d_footing(inputs, results, "pad_footing_3d.png")
    gif_path = animate_3d_footing(inputs, results, "pad_footing_3d_rotation.gif")
    dash_path = create_dashboard(inputs, results, "pad_footing_dashboard.png")
    print(f"\n3D visualization saved: {png_path}")
    print(f"3D rotation GIF saved:  {gif_path}")
    print(f"Dashboard saved:        {dash_path}")