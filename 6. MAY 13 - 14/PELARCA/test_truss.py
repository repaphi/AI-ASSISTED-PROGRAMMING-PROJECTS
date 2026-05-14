import tkinter as tk
import customtkinter as ctk
from tkinter import ttk, messagebox
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg


# ===========================
# Howe Truss Analyzer & Designer
# NSCP 2015 LRFD Method (Simplified Framework)
# ===========================


class HoweTrussApp(ctk.CTk):

    def __init__(self):
        super().__init__()

        self.title("Steel Howe Roof Truss Analyzer - NSCP 2015 (LRFD)")
        self.geometry("1200x700")

        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")

        # Tabs
        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(fill="both", expand=True)

        self.geometry_tab = self.tabview.add("Geometry")
        self.loading_tab = self.tabview.add("Loading")
        self.material_tab = self.tabview.add("Materials")
        self.section_tab = self.tabview.add("Sections")
        self.results_tab = self.tabview.add("Results")

        self.create_geometry_inputs()
        self.create_loading_inputs()
        self.create_material_inputs()
        self.create_section_inputs()
        self.create_results_panel()

        # Default values
        self.set_default_values()

    # -------------------------
    # Input Panels
    # -------------------------

    def create_geometry_inputs(self):

        frame = ctk.CTkFrame(self.geometry_tab)
        frame.pack(padx=20, pady=20, fill="both", expand=True)

        self.span_var = tk.DoubleVar()
        self.rise_var = tk.DoubleVar()
        self.panels_var = tk.IntVar()
        self.spacing_var = tk.DoubleVar()

        ctk.CTkLabel(frame, text="Truss Span Length (m)").grid(row=0, column=0, sticky="w")
        ctk.CTkEntry(frame, textvariable=self.span_var).grid(row=0, column=1)

        ctk.CTkLabel(frame, text="Roof Rise Height (m)").grid(row=1, column=0, sticky="w")
        ctk.CTkEntry(frame, textvariable=self.rise_var).grid(row=1, column=1)

        ctk.CTkLabel(frame, text="Number of Panels").grid(row=2, column=0, sticky="w")
        ctk.CTkEntry(frame, textvariable=self.panels_var).grid(row=2, column=1)

        ctk.CTkLabel(frame, text="Truss Spacing (m)").grid(row=3, column=0, sticky="w")
        ctk.CTkEntry(frame, textvariable=self.spacing_var).grid(row=3, column=1)

    def create_loading_inputs(self):

        frame = ctk.CTkFrame(self.loading_tab)
        frame.pack(padx=20, pady=20, fill="both", expand=True)

        self.dead_var = tk.DoubleVar()
        self.live_var = tk.DoubleVar()
        self.wind_var = tk.DoubleVar()

        ctk.CTkLabel(frame, text="Dead Load (kPa)").grid(row=0, column=0, sticky="w")
        ctk.CTkEntry(frame, textvariable=self.dead_var).grid(row=0, column=1)

        ctk.CTkLabel(frame, text="Roof Live Load (kPa)").grid(row=1, column=0, sticky="w")
        ctk.CTkEntry(frame, textvariable=self.live_var).grid(row=1, column=1)

        ctk.CTkLabel(frame, text="Wind Pressure (kPa)").grid(row=2, column=0, sticky="w")
        ctk.CTkEntry(frame, textvariable=self.wind_var).grid(row=2, column=1)

    def create_material_inputs(self):

        frame = ctk.CTkFrame(self.material_tab)
        frame.pack(padx=20, pady=20, fill="both", expand=True)

        self.fy_var = tk.DoubleVar()
        self.fu_var = tk.DoubleVar()
        self.e_var = tk.DoubleVar()

        ctk.CTkLabel(frame, text="Yield Strength Fy (MPa)").grid(row=0, column=0, sticky="w")
        ctk.CTkEntry(frame, textvariable=self.fy_var).grid(row=0, column=1)

        ctk.CTkLabel(frame, text="Ultimate Strength Fu (MPa)").grid(row=1, column=0, sticky="w")
        ctk.CTkEntry(frame, textvariable=self.fu_var).grid(row=1, column=1)

        ctk.CTkLabel(frame, text="Modulus of Elasticity E (MPa)").grid(row=2, column=0, sticky="w")
        ctk.CTkEntry(frame, textvariable=self.e_var).grid(row=2, column=1)

    def create_section_inputs(self):

        frame = ctk.CTkFrame(self.section_tab)
        frame.pack(padx=20, pady=20, fill="both", expand=True)

        self.section_var = tk.StringVar()

        sections = [
            "25x25x3",
            "25x25x5",
            "38x38x5",
            "50x50x5",
            "50x50x6",
            "65x65x6",
            "75x75x6",
            "75x75x8",
            "100x100x8",
            "100x100x10"
        ]

        ctk.CTkLabel(frame, text="Select Angle Section").grid(row=0, column=0, sticky="w")

        ctk.CTkOptionMenu(
            frame,
            variable=self.section_var,
            values=sections
        ).grid(row=0, column=1)

    def create_results_panel(self):

        frame = ctk.CTkFrame(self.results_tab)
        frame.pack(padx=20, pady=20, fill="both", expand=True)

        self.analyze_btn = ctk.CTkButton(
            frame,
            text="Analyze & Design",
            command=self.run_analysis
        )

        self.analyze_btn.pack(pady=10)

        self.text_output = tk.Text(frame, height=20)
        self.text_output.pack(fill="both", expand=True)

    def set_default_values(self):

        self.span_var.set(18.0)
        self.rise_var.set(4.0)
        self.panels_var.set(8)
        self.spacing_var.set(4.0)

        self.dead_var.set(0.50)
        self.live_var.set(0.75)
        self.wind_var.set(1.20)

        self.fy_var.set(248)
        self.fu_var.set(400)
        self.e_var.set(200000)

        self.section_var.set("50x50x5")

    def run_analysis(self):

        self.text_output.delete(1.0, tk.END)

        self.text_output.insert(
            tk.END,
            "Howe Truss Analysis Started...\n\n"
        )

        self.text_output.insert(
            tk.END,
            f"Span = {self.span_var.get()} m\n"
        )

        self.text_output.insert(
            tk.END,
            f"Rise = {self.rise_var.get()} m\n"
        )

        self.text_output.insert(
            tk.END,
            f"Panels = {self.panels_var.get()}\n"
        )

        self.text_output.insert(
            tk.END,
            f"Selected Section = {self.section_var.get()}\n"
        )

        self.text_output.insert(
            tk.END,
            "\nAnalysis routine not yet implemented.\n"
        )


# ===========================
# Main Program
# ===========================

if __name__ == "__main__":
    app = HoweTrussApp()
    app.mainloop()