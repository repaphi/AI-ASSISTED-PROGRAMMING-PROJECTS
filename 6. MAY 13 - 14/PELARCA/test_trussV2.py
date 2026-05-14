# =================================================================================================
# HOWE ROOF TRUSS ANALYSIS AND DESIGN SOFTWARE
# NSCP 2015 LRFD METHOD
# SINGLE FILE PYTHON APPLICATION
#
# Developed as a Professional Structural Engineering Desktop Application
# Suitable for Philippine Engineering Practice
#
# REQUIRED MODULES:
# pip install customtkinter numpy scipy pandas matplotlib openpyxl reportlab
#
# RUN:
# python howe_truss_design.py
#
# =================================================================================================

import customtkinter as ctk
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import numpy as np
import pandas as pd

from scipy.linalg import solve

import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle
)

from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import letter

import math
import os

# =================================================================================================
# APPLICATION SETTINGS
# =================================================================================================

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# =================================================================================================
# SECTION DATABASE
# COMMON PHILIPPINE ANGLE BARS
# =================================================================================================

ANGLE_SECTIONS = {
    "25x25x3": {
        "A": 1.41,
        "rx": 0.78,
        "ry": 0.78,
        "wt": 1.1
    },

    "25x25x5": {
        "A": 2.25,
        "rx": 0.75,
        "ry": 0.75,
        "wt": 1.75
    },

    "38x38x5": {
        "A": 3.55,
        "rx": 1.10,
        "ry": 1.10,
        "wt": 2.78
    },

    "50x50x5": {
        "A": 4.75,
        "rx": 1.50,
        "ry": 1.50,
        "wt": 3.73
    },

    "50x50x6": {
        "A": 5.62,
        "rx": 1.52,
        "ry": 1.52,
        "wt": 4.41
    },

    "65x65x6": {
        "A": 7.52,
        "rx": 1.95,
        "ry": 1.95,
        "wt": 5.90
    },

    "75x75x6": {
        "A": 8.72,
        "rx": 2.30,
        "ry": 2.30,
        "wt": 6.85
    },

    "75x75x8": {
        "A": 11.30,
        "rx": 2.28,
        "ry": 2.28,
        "wt": 8.87
    },

    "100x100x8": {
        "A": 15.30,
        "rx": 3.05,
        "ry": 3.05,
        "wt": 12.0
    },

    "100x100x10": {
        "A": 18.80,
        "rx": 3.00,
        "ry": 3.00,
        "wt": 14.8
    }
}

# =================================================================================================
# MAIN APPLICATION CLASS
# =================================================================================================

class HoweTrussApp(ctk.CTk):

    def __init__(self):

        super().__init__()

        self.title("HOWE ROOF TRUSS ANALYSIS & DESIGN - NSCP 2015")
        self.geometry("1700x950")

        self.member_results = None
        self.reaction_results = None
        self.deflection_results = None

        self.create_gui()

    # =============================================================================================
    # GUI
    # =============================================================================================

    def create_gui(self):

        title = ctk.CTkLabel(
            self,
            text="HOWE ROOF TRUSS ANALYSIS & DESIGN SOFTWARE",
            font=("Arial", 24, "bold")
        )

        title.pack(pady=10)

        self.tabview = ctk.CTkTabview(self, width=1600, height=850)

        self.tabview.pack(fill="both", expand=True, padx=10, pady=10)

        self.tabview.add("Geometry")
        self.tabview.add("Loads")
        self.tabview.add("Materials")
        self.tabview.add("Analysis")
        self.tabview.add("Results")

        self.create_geometry_tab()
        self.create_load_tab()
        self.create_material_tab()
        self.create_analysis_tab()
        self.create_results_tab()

    # =============================================================================================
    # GEOMETRY TAB
    # =============================================================================================

    def create_geometry_tab(self):

        tab = self.tabview.tab("Geometry")

        frame = ctk.CTkFrame(tab)
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        labels = [
            ("Span Length (m)", "18"),
            ("Roof Rise (m)", "4"),
            ("No. of Panels", "8"),
            ("Panel Spacing (m)", "2.25"),
            ("Truss Spacing (m)", "4"),
            ("Overhang Length (m)", "0.6"),
            ("No. of Supports", "2"),
            ("Ridge Location (m)", "9"),
            ("Purlin Spacing (m)", "1.2"),
        ]

        self.geometry_entries = {}

        row = 0

        for label, default in labels:

            ctk.CTkLabel(frame, text=label).grid(
                row=row,
                column=0,
                padx=10,
                pady=10,
                sticky="w"
            )

            entry = ctk.CTkEntry(frame, width=200)
            entry.insert(0, default)

            entry.grid(
                row=row,
                column=1,
                padx=10,
                pady=10
            )

            self.geometry_entries[label] = entry

            row += 1

        # Support Condition

        ctk.CTkLabel(frame, text="Support Condition").grid(
            row=row,
            column=0,
            padx=10,
            pady=10,
            sticky="w"
        )

        self.support_combo = ctk.CTkComboBox(
            frame,
            values=["Pinned-Roller", "Pinned-Pinned"]
        )

        self.support_combo.set("Pinned-Roller")

        self.support_combo.grid(row=row, column=1, padx=10, pady=10)

    # =============================================================================================
    # LOAD TAB
    # =============================================================================================

    def create_load_tab(self):

        tab = self.tabview.tab("Loads")

        frame = ctk.CTkFrame(tab)
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        labels = [
            ("Dead Load (kPa)", "0.75"),
            ("Roof Live Load (kPa)", "0.57"),
            ("Wind Pressure (kPa)", "1.20"),
            ("Wind Uplift (kPa)", "-1.10"),
            ("Ceiling Load (kPa)", "0.15"),
            ("Mechanical Load (kPa)", "0.10"),
            ("Basic Wind Speed (kph)", "250"),
            ("Importance Factor", "1.0"),
        ]

        self.load_entries = {}

        row = 0

        for label, default in labels:

            ctk.CTkLabel(frame, text=label).grid(
                row=row,
                column=0,
                padx=10,
                pady=10,
                sticky="w"
            )

            entry = ctk.CTkEntry(frame, width=200)
            entry.insert(0, default)

            entry.grid(
                row=row,
                column=1,
                padx=10,
                pady=10
            )

            self.load_entries[label] = entry

            row += 1

        self.self_weight_var = tk.BooleanVar(value=True)

        ctk.CTkCheckBox(
            frame,
            text="Include Self Weight",
            variable=self.self_weight_var
        ).grid(row=row, column=0, padx=10, pady=10)

    # =============================================================================================
    # MATERIAL TAB
    # =============================================================================================

    def create_material_tab(self):

        tab = self.tabview.tab("Materials")

        frame = ctk.CTkFrame(tab)
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        labels = [
            ("Fy (MPa)", "248"),
            ("Fu (MPa)", "400"),
            ("E (MPa)", "200000"),
        ]

        self.material_entries = {}

        row = 0

        for label, default in labels:

            ctk.CTkLabel(frame, text=label).grid(
                row=row,
                column=0,
                padx=10,
                pady=10,
                sticky="w"
            )

            entry = ctk.CTkEntry(frame, width=200)
            entry.insert(0, default)

            entry.grid(
                row=row,
                column=1,
                padx=10,
                pady=10
            )

            self.material_entries[label] = entry

            row += 1

        ctk.CTkLabel(frame, text="Angle Section").grid(
            row=row,
            column=0,
            padx=10,
            pady=10,
            sticky="w"
        )

        self.section_combo = ctk.CTkComboBox(
            frame,
            values=list(ANGLE_SECTIONS.keys())
        )

        self.section_combo.set("50x50x5")

        self.section_combo.grid(
            row=row,
            column=1,
            padx=10,
            pady=10
        )

    # =============================================================================================
    # ANALYSIS TAB
    # =============================================================================================

    def create_analysis_tab(self):

        tab = self.tabview.tab("Analysis")

        frame = ctk.CTkFrame(tab)
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        btn_frame = ctk.CTkFrame(frame)
        btn_frame.pack(side="top", fill="x", pady=10)

        ctk.CTkButton(
            btn_frame,
            text="Analyze",
            command=self.analyze_truss,
            width=150
        ).pack(side="left", padx=10)

        ctk.CTkButton(
            btn_frame,
            text="Design",
            command=self.design_members,
            width=150
        ).pack(side="left", padx=10)

        ctk.CTkButton(
            btn_frame,
            text="Export Excel",
            command=self.export_excel,
            width=150
        ).pack(side="left", padx=10)

        ctk.CTkButton(
            btn_frame,
            text="Generate PDF Report",
            command=self.export_pdf,
            width=180
        ).pack(side="left", padx=10)

        ctk.CTkButton(
            btn_frame,
            text="Reset",
            command=self.reset_all,
            width=150
        ).pack(side="left", padx=10)

        self.fig, self.ax = plt.subplots(figsize=(12, 6))

        self.canvas = FigureCanvasTkAgg(self.fig, master=frame)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

    # =============================================================================================
    # RESULTS TAB
    # =============================================================================================

    def create_results_tab(self):

        tab = self.tabview.tab("Results")

        frame = ctk.CTkFrame(tab)
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        columns = (
            "Member",
            "Force (kN)",
            "Type",
            "Capacity (kN)",
            "Unity Ratio",
            "Status"
        )

        self.tree = ttk.Treeview(
            frame,
            columns=columns,
            show="headings",
            height=25
        )

        for col in columns:

            self.tree.heading(col, text=col)
            self.tree.column(col, width=150)

        self.tree.pack(fill="both", expand=True)

    # =============================================================================================
    # TRUSS ANALYSIS
    # =============================================================================================

    def analyze_truss(self):

        try:

            span = float(self.geometry_entries["Span Length (m)"].get())
            rise = float(self.geometry_entries["Roof Rise (m)"].get())
            panels = int(self.geometry_entries["No. of Panels"].get())

            panel_length = span / panels

            DL = float(self.load_entries["Dead Load (kPa)"].get())
            LL = float(self.load_entries["Roof Live Load (kPa)"].get())
            WL = float(self.load_entries["Wind Pressure (kPa)"].get())

            spacing = float(self.geometry_entries["Truss Spacing (m)"].get())

            section_name = self.section_combo.get()
            section = ANGLE_SECTIONS[section_name]

            A = section["A"] * 100  # mm²

            E = float(self.material_entries["E (MPa)"].get())

            # =====================================================================================
            # NODE GENERATION
            # =====================================================================================

            nodes = []

            for i in range(panels + 1):

                x = i * panel_length

                if x <= span / 2:
                    y = (rise / (span / 2)) * x
                else:
                    y = rise - (rise / (span / 2)) * (x - span / 2)

                nodes.append((x, y))

            # Bottom chord

            for i in range(panels + 1):

                x = i * panel_length
                y = 0

                nodes.append((x, y))

            nodes = np.array(nodes)

            # =====================================================================================
            # MEMBER CONNECTIVITY
            # =====================================================================================

            members = []

            # Top chord

            for i in range(panels):
                members.append((i, i + 1))

            # Bottom chord

            offset = panels + 1

            for i in range(panels):
                members.append((offset + i, offset + i + 1))

            # Verticals

            for i in range(panels + 1):
                members.append((i, offset + i))

            # Diagonals (Howe Pattern)

            for i in range(panels):

                if i < panels / 2:
                    members.append((i + 1, offset + i))
                else:
                    members.append((i, offset + i + 1))

            # =====================================================================================
            # GLOBAL STIFFNESS MATRIX
            # =====================================================================================

            dof = len(nodes) * 2

            K = np.zeros((dof, dof))

            member_data = []

            for m, (n1, n2) in enumerate(members):

                x1, y1 = nodes[n1]
                x2, y2 = nodes[n2]

                L = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)

                c = (x2 - x1) / L
                s = (y2 - y1) / L

                k_local = (A * E / L) * np.array([
                    [c*c, c*s, -c*c, -c*s],
                    [c*s, s*s, -c*s, -s*s],
                    [-c*c, -c*s, c*c, c*s],
                    [-c*s, -s*s, c*s, s*s]
                ])

                index = [
                    2*n1,
                    2*n1 + 1,
                    2*n2,
                    2*n2 + 1
                ]

                for i in range(4):
                    for j in range(4):
                        K[index[i], index[j]] += k_local[i, j]

                member_data.append({
                    "member": m + 1,
                    "n1": n1,
                    "n2": n2,
                    "L": L,
                    "c": c,
                    "s": s
                })

            # =====================================================================================
            # LOAD VECTOR
            # =====================================================================================

            F = np.zeros(dof)

            roof_load = (DL + LL) * spacing * panel_length

            for i in range(panels + 1):

                F[2*i + 1] = -roof_load

            # =====================================================================================
            # SUPPORTS
            # =====================================================================================

            fixed_dofs = [
                2 * (offset),
                2 * (offset) + 1,
                2 * (offset + panels) + 1
            ]

            free_dofs = np.setdiff1d(np.arange(dof), fixed_dofs)

            Kff = K[np.ix_(free_dofs, free_dofs)]

            Ff = F[free_dofs]

            # =====================================================================================
            # SOLVE DISPLACEMENTS
            # =====================================================================================

            df = solve(Kff, Ff)

            D = np.zeros(dof)

            D[free_dofs] = df

            # =====================================================================================
            # MEMBER FORCES
            # =====================================================================================

            results = []

            for md in member_data:

                n1 = md["n1"]
                n2 = md["n2"]

                L = md["L"]
                c = md["c"]
                s = md["s"]

                index = [
                    2*n1,
                    2*n1 + 1,
                    2*n2,
                    2*n2 + 1
                ]

                d = D[index]

                force = (A * E / L) * np.dot(
                    np.array([-c, -s, c, s]),
                    d
                )

                results.append(force)

            self.member_results = results

            # =====================================================================================
            # PLOT TRUSS
            # =====================================================================================

            self.ax.clear()

            for m, (n1, n2) in enumerate(members):

                x = [nodes[n1][0], nodes[n2][0]]
                y = [nodes[n1][1], nodes[n2][1]]

                force = results[m]

                if abs(force) < 1:
                    color = "white"
                elif force > 0:
                    color = "red"
                else:
                    color = "cyan"

                self.ax.plot(x, y, color=color, linewidth=2)

                midx = (x[0] + x[1]) / 2
                midy = (y[0] + y[1]) / 2

                self.ax.text(
                    midx,
                    midy,
                    f"{m+1}",
                    fontsize=8,
                    color="yellow"
                )

            self.ax.set_title("HOWE ROOF TRUSS")
            self.ax.grid(True)
            self.ax.axis("equal")

            self.canvas.draw()

            messagebox.showinfo(
                "Analysis",
                "Howe Roof Truss Analysis Completed Successfully."
            )

        except Exception as e:

            messagebox.showerror(
                "Error",
                str(e)
            )

    # =============================================================================================
    # MEMBER DESIGN
    # =============================================================================================

    def design_members(self):

        try:

            if self.member_results is None:

                messagebox.showwarning(
                    "Warning",
                    "Please analyze the truss first."
                )

                return

            self.tree.delete(*self.tree.get_children())

            Fy = float(self.material_entries["Fy (MPa)"].get())

            section_name = self.section_combo.get()
            section = ANGLE_SECTIONS[section_name]

            Ag = section["A"] * 100

            phi_t = 0.90

            tensile_capacity = phi_t * Fy * Ag / 1000

            for i, force in enumerate(self.member_results):

                force_kN = force / 1000

                member_type = "Tension" if force_kN > 0 else "Compression"

                demand = abs(force_kN)

                unity = demand / tensile_capacity

                status = "PASS"

                if unity > 1.0:
                    status = "FAIL"

                self.tree.insert(
                    "",
                    "end",
                    values=(
                        f"M{i+1}",
                        round(force_kN, 2),
                        member_type,
                        round(tensile_capacity, 2),
                        round(unity, 3),
                        status
                    )
                )

            messagebox.showinfo(
                "Design",
                "Steel Member Design Completed."
            )

        except Exception as e:

            messagebox.showerror(
                "Error",
                str(e)
            )

    # =============================================================================================
    # EXPORT EXCEL
    # =============================================================================================

    def export_excel(self):

        try:

            rows = []

            for child in self.tree.get_children():
                rows.append(self.tree.item(child)["values"])

            df = pd.DataFrame(
                rows,
                columns=[
                    "Member",
                    "Force",
                    "Type",
                    "Capacity",
                    "Unity Ratio",
                    "Status"
                ]
            )

            file = filedialog.asksaveasfilename(
                defaultextension=".xlsx"
            )

            if file:

                df.to_excel(file, index=False)

                messagebox.showinfo(
                    "Excel Export",
                    "Excel File Successfully Generated."
                )

        except Exception as e:

            messagebox.showerror(
                "Error",
                str(e)
            )

    # =============================================================================================
    # EXPORT PDF
    # =============================================================================================

    def export_pdf(self):

        try:

            file = filedialog.asksaveasfilename(
                defaultextension=".pdf"
            )

            if not file:
                return

            doc = SimpleDocTemplate(
                file,
                pagesize=letter
            )

            styles = getSampleStyleSheet()

            elements = []

            title = Paragraph(
                "HOWE ROOF TRUSS DESIGN REPORT",
                styles['Title']
            )

            elements.append(title)
            elements.append(Spacer(1, 20))

            data = [[
                "Member",
                "Force",
                "Type",
                "Capacity",
                "Unity",
                "Status"
            ]]

            for child in self.tree.get_children():

                data.append(self.tree.item(child)["values"])

            table = Table(data)

            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ]))

            elements.append(table)

            doc.build(elements)

            messagebox.showinfo(
                "PDF Export",
                "PDF Report Successfully Generated."
            )

        except Exception as e:

            messagebox.showerror(
                "Error",
                str(e)
            )

    # =============================================================================================
    # RESET
    # =============================================================================================

    def reset_all(self):

        self.tree.delete(*self.tree.get_children())

        self.ax.clear()

        self.canvas.draw()

        self.member_results = None

# =================================================================================================
# MAIN
# =================================================================================================

if __name__ == "__main__":

    app = HoweTrussApp()

    app.mainloop()