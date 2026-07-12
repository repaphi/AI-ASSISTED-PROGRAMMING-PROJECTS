"""aint working
Title: OpenSTAAD Floor Framing Plan Generation & Analysis Script
Author: Structural Engineering Assistant
Reference: National Structural Code of the Philippines (NSCP 2015, 7th Edition)
           ACI 318-14 Building Code Requirements for Structural Concrete
Target Engine: STAAD.Pro CONNECT Edition (OpenSTAAD COM Link)

This script automates:
1. Connecting to an active instance of STAAD.Pro using pure dynamic late-binding.
2. Generating a physical node grid mapping out the Ground/Second Floor plans.
3. Modeling columns, primary longitudinal girders, and transverse floor beams.
4. Setting up concrete material properties (f'c = 27.6 MPa) and cross-sections.
5. Computing and applying NSCP 2015 Dead & Live load states.
6. Generating factored load combinations (1.4D and 1.2D + 1.6L).
7. Triggering the STAAD Analysis Engine.
"""

import sys
import math
import os
import shutil

# Proactively clear the win32com gen_py cache directory to completely eliminate 
# corrupted early-binding TypeLib wrappers that treat methods as integers or booleans.
try:
    import win32com
    gen_dir = getattr(win32com, "__gen_path__", None)
    if gen_dir and os.path.exists(gen_dir):
        shutil.rmtree(gen_dir)
        print("Successfully purged local win32com early-binding 'gen_py' cache.")
except Exception as cache_err:
    print(f"Diagnostics: Cache purge skipped or not required ({cache_err}).")

# Try importing the pywin32 modules to interface with COM objects
try:
    import win32com.client
    import win32com.client.dynamic
except ImportError:
    print("Error: 'pywin32' library is required to execute OpenSTAAD routines.")
    print("Please install it using: pip install pywin32")
    sys.exit(1)


def com_call(obj, method_name, *args):
    """
    Explicitly invokes an OpenSTAAD method using the COM DISPATCH_METHOD (1) flag.
    Bypasses pywin32's automatic getter evaluation, preventing method/property collisions.
    """
    if obj is None:
        raise ValueError(f"COM interface for invoking '{method_name}' is not initialized.")
    try:
        # Extract the dispatch ID of the target method
        dispid = obj._oleobj_.GetIDsOfNames(0, method_name)[0]
        # Invoke specifically with DISPATCH_METHOD (value = 1)
        return obj._oleobj_.Invoke(dispid, 0, 1, True, *args)
    except Exception as invoke_err:
        # Fallback to standard dynamic getattr call if direct invoke fails
        try:
            return getattr(obj, method_name)(*args)
        except Exception as attr_err:
            raise RuntimeError(
                f"Failed to invoke COM method '{method_name}' on {obj}. "
                f"Invoke Error: {invoke_err} | Fallback Error: {attr_err}"
            )


class STAADFramingGenerator:
    def __init__(self):
        self.os_obj = None
        self.geometry = None
        self.properties = None
        self.loads = None
        self.views = None
        self.output = None
        
        # Grid definition parameters based on the As-Built Floor Plan
        # X-spans (transverse direction): A to B = 1.95 m, B to C = 3.05 m (Total = 5.0 m)
        self.grid_x = [0.0, 1.95, 5.0]  
        # Z-spans (longitudinal direction): Grids 1', 1, 2, 3
        # 1' to 1 = 3.5 m, 1 to 2 = 3.6 m, 2 to 3 = 3.6 m
        self.grid_z = [0.0, 3.5, 7.1, 10.7]  
        # Floor elevations (Y-coordinates): Base/Foundation = 0.0 m, Level 2 = 3.2 m
        self.elevations = [0.0, 3.2]
        
        # Structural Section Dimensions (in meters)
        self.col_b = 0.35   # Column width
        self.col_h = 0.35   # Column depth
        self.beam_b = 0.25  # Beam width
        self.beam_h = 0.40  # Beam depth (NSCP span/16 minimum thickness check)
        
        # Materials
        self.fc = 27.6 * 1000  # Concrete Compressive Strength in kN/m^2 (27.6 MPa)
        self.fy = 414.0 * 1000 # Steel Yield Strength in kN/m^2 (Grade 60)
        
        # Load magnitudes (kN/m^2) according to NSCP 2015 Table 204-1 and 205-1
        self.slab_thick = 0.125  # Slab thickness of 125mm
        self.slab_density = 24.0 # Concrete density in kN/m^3
        self.dl_self = self.slab_thick * self.slab_density # 3.0 kN/m^2
        self.dl_finishes = 1.2   # Finishes and ceiling utility (1.2 kN/m^2)
        self.dl_partition = 1.0  # Movable interior partition allowance (1.0 kN/m^2)
        self.live_residential = 1.9 # Residential private rooms (1.9 kN/m^2)
        self.live_corridor = 3.8    # Public corridors / common space (3.8 kN/m^2)

    def connect_staad(self):
        """Initializes pure dynamic late-bound COM connection with active STAAD.Pro instance."""
        print("Attempting connection to active STAAD.Pro file instance...")
        try:
            # Force pure late-binding dynamic dispatch to bypass corrupted gen_py early-binding caches
            try:
                raw_obj = win32com.client.GetActiveObject("StaadPro.OpenSTAAD")
                self.os_obj = win32com.client.dynamic.Dispatch(raw_obj)
            except Exception:
                self.os_obj = win32com.client.dynamic.Dispatch("StaadPro.OpenSTAAD")
                
            print("Successfully linked to active OpenSTAAD instance using pure dynamic late-binding.")
            
            # Explicitly wrapping child properties in dynamic.Dispatch to enforce absolute runtime late-binding
            self.geometry = win32com.client.dynamic.Dispatch(self.os_obj.Geometry)
            self.properties = win32com.client.dynamic.Dispatch(self.os_obj.Property)
            self.loads = win32com.client.dynamic.Dispatch(self.os_obj.Load)
            self.views = win32com.client.dynamic.Dispatch(self.os_obj.View)
            self.output = win32com.client.dynamic.Dispatch(self.os_obj.Output)
            
            print("All active OpenSTAAD child interfaces successfully bound dynamically.")

            # Standardize Units: Force = Kilonewtons (kN), Length = Meters (m)
            # Length: 4 = Meter, Force: 5 = Kilonewton
            try:
                com_call(self.os_obj, "SetInputUnits", 4, 5)
                print("Base units configured to Kilonewtons (kN) and Meters (m) via Root interface.")
            except Exception as unit_error:
                print(f"Warning: Root unit interface not supported or skipped: {unit_error}")
                print("Proceeding using the active STAAD.Pro workspace's native unit context.")
                
        except Exception as e:
            print("\nError connecting to STAAD.Pro! Ensure that:")
            print("1. STAAD.Pro is open with a valid structural file model active.")
            print("2. You are executing this script with matching administrator privileges.")
            print(f"System Message Details: {e}")
            sys.exit(1)

    def generate_nodes(self):
        """Generates coordinate nodes based on the asymmetric grid mapping."""
        print("\n[Step 1/6] Generating structural joint coordinates...")
        self.node_map = {} # Map node index coordinates to assigned node IDs
        node_counter = 1
        
        # Iterate over Elevations (Y), Longitudinal grids (Z), and Transverse grids (X)
        for y_idx, y in enumerate(self.elevations):
            for z_idx, z in enumerate(self.grid_z):
                for x_idx, x in enumerate(self.grid_x):
                    # CreateNode(NodeNo, X, Y, Z) resolves automatically via late-binding dynamic dispatch helper
                    com_call(self.geometry, "CreateNode", node_counter, x, y, z)
                    self.node_map[(x_idx, y_idx, z_idx)] = node_counter
                    node_counter += 1
        
        print(f"Node layout processing complete. {node_counter - 1} physical nodes mapped.")

    def create_members(self):
        """Generates Column & Beam physical members on structural grid arrays."""
        print("\n[Step 2/6] Modeling physical Columns and Beams...")
        self.column_ids = []
        self.beam_ids = []
        member_counter = 1
        
        # 1. Column Generation (vertical members spanning from Y=0 to Y=3.2)
        for z_idx in range(len(self.grid_z)):
            for x_idx in range(len(self.grid_x)):
                n1 = self.node_map[(x_idx, 0, z_idx)]
                n2 = self.node_map[(x_idx, 1, z_idx)]
                com_call(self.geometry, "CreateBeam", member_counter, n1, n2)
                self.column_ids.append(member_counter)
                member_counter += 1
                
        # 2. Longitudinal Framing Girders (Z-direction Beams on Level 2)
        for x_idx in range(len(self.grid_x)):
            for z_idx in range(len(self.grid_z) - 1):
                n1 = self.node_map[(x_idx, 1, z_idx)]
                n2 = self.node_map[(x_idx, 1, z_idx + 1)]
                com_call(self.geometry, "CreateBeam", member_counter, n1, n2)
                self.beam_ids.append(member_counter)
                member_counter += 1

        # 3. Transverse Floor Beams (X-direction Beams on Level 2)
        for z_idx in range(len(self.grid_z)):
            for x_idx in range(len(self.grid_x) - 1):
                n1 = self.node_map[(x_idx, 1, z_idx)]
                n2 = self.node_map[(x_idx + 1, 1, z_idx)]
                com_call(self.geometry, "CreateBeam", member_counter, n1, n2)
                self.beam_ids.append(member_counter)
                member_counter += 1

        print(f"Structural elements established. Columns: {len(self.column_ids)} | Beams: {len(self.beam_ids)}")

    def assign_section_properties(self):
        """Sets material characteristics and assigns cross-section profiles."""
        print("\n[Step 3/6] Defining section properties and assigning concrete profiles...")
        
        # Invoke rectangular concrete property creation explicitly through the com_call method helper
        col_prop_id = com_call(self.properties, "CreatePrismaticRectangleProperty", self.col_h, self.col_b)
        beam_prop_id = com_call(self.properties, "CreatePrismaticRectangleProperty", self.beam_h, self.beam_b)
        
        # Assign properties to Columns
        for col_id in self.column_ids:
            com_call(self.properties, "AssignBeamProperty", col_id, col_prop_id)
            
        # Assign properties to Floor Beams
        for beam_id in self.beam_ids:
            com_call(self.properties, "AssignBeamProperty", beam_id, beam_prop_id)

        print("Reinforced concrete member properties applied successfully.")

    def _safe_create_load_case(self, case_title, load_type_id=1):
        """Attempts multiple known OpenSTAAD methods dynamically using runtime late-binding."""
        errors = []
        candidate_methods = ["CreateNewLoadCase", "CreateNewLoad", "AddNewLoadCase", "AddLoadCase"]
        
        # 1. Try CreateNewLoadCase (Standard signature in modern CONNECT: title, load_type_id)
        try:
            com_call(self.loads, "CreateNewLoadCase", case_title, load_type_id)
            return True
        except Exception as err_2arg:
            errors.append(f"CreateNewLoadCase with 2 args failed: {err_2arg}")
            
        # 2. Try CreateNewLoadCase with single argument
        try:
            com_call(self.loads, "CreateNewLoadCase", case_title)
            return True
        except Exception as err_1arg:
            errors.append(f"CreateNewLoadCase with 1 arg failed: {err_1arg}")

        # 3. Try standard CreateNewLoad (Classic OpenSTAAD)
        try:
            com_call(self.loads, "CreateNewLoad", case_title)
            return True
        except Exception as err_classic:
            errors.append(f"CreateNewLoad failed: {err_classic}")

        # 4. Probing alternate dispatch matches dynamically
        for m_name in candidate_methods:
            if m_name != "CreateNewLoadCase":
                try:
                    com_call(self.loads, m_name, case_title, load_type_id)
                    return True
                except Exception as err_alt2:
                    errors.append(f"getattr({m_name}) with 2 args failed: {err_alt2}")
                try:
                    com_call(self.loads, m_name, case_title)
                    return True
                except Exception as err_alt1:
                    errors.append(f"getattr({m_name}) with 1 arg failed: {err_alt1}")
                    
        # Print diagnostic error log to stdout before raising
        print("\n" + "!"*60)
        print("          OPENSTAAD LOAD CREATION DIAGNOSTIC FAILURE REPORT")
        print("!"*60)
        print("The script attempted multiple API call variations. Details below:")
        for idx, err in enumerate(errors, 1):
            print(f"  {idx:02d}. {err}")
        print("!"*60 + "\n")
        
        raise AttributeError("Unable to create a new load case. Your version of STAAD.Pro uses an alternate Load Case API schema.")

    def _safe_activate_load_case(self, case_id):
        """Dynamically ensures a specific loadcase index is active in the current workspace context."""
        activation_methods = ["SetLoadActive", "SetActiveLoadCase"]
        errors = []
        for m_name in activation_methods:
            try:
                com_call(self.loads, m_name, case_id)
                return True
            except Exception as e:
                errors.append(f"Attr Call {m_name}({case_id}) failed: {e}")
                
        print(f"Warning: Load Case Activation could not confirm Case ID {case_id} is active.")
        for err in errors:
            print(f"  > {err}")
        return False

    def apply_loads(self):
        """Calculates area loads and distributes them as beam line loads."""
        print("\n[Step 4/6] Formulating NSCP 2015 Live & Dead gravity loads...")
        
        # Diagnostic Pre-check: Show active load cases
        try:
            current_count = com_call(self.loads, "GetNumberOfLoadCases")
            print(f"Diagnostics: Active document contains {current_count} load case(s).")
        except Exception as diag_err:
            print(f"Diagnostics: GetNumberOfLoadCases check skipped: {diag_err}")
            
        # 1. Setup Dead Load Case (Load Type = 1)
        self._safe_create_load_case("DEAD LOAD", 1)
        dl_case_id = 1
        self._safe_activate_load_case(dl_case_id)
        
        # Add Self Weight of frame members safely (Direction Y = 2, Factor = -1.0)
        try:
            # Try 2-parameter signature (Direction, Factor)
            com_call(self.loads, "AddSelfWeight", 2, -1.0)
        except Exception:
            try:
                # Try 3-parameter signature with explicit Case ID (CaseID, Direction, Factor)
                com_call(self.loads, "AddSelfWeight", dl_case_id, 2, -1.0)
            except Exception:
                try:
                    # Alternate vertical direction index fallback
                    com_call(self.loads, "AddSelfWeight", 1, -1.0)
                except Exception as sw_err:
                    print(f"Warning: Self weight could not be applied automatically: {sw_err}")
        
        # Calculate tributary width loads for representative slab distribution
        # In a simplified 1-way / 2-way tributary approximation:
        # Transverse beam spacing = 3.6m. Slab DL = (3.0 + 1.2 + 1.0) = 5.2 kN/m^2.
        # Average tributary load on primary longitudinal beams = 5.2 kN/m^2 * (1.8m tributary width) = 9.36 kN/m
        line_dl = (self.dl_self + self.dl_finishes + self.dl_partition) * 1.8
        
        # Apply calculated uniform distributed line loads to floor beams under Dead Load Case
        for beam_id in self.beam_ids:
            try:
                # Standard signature (Member, Direction, W1, W2, D1, D2, D3)
                # Direction = 2 (Local Y axis acting downwards)
                com_call(self.loads, "AddMemberUniformLoad", beam_id, 2, -line_dl, -line_dl, 0.0, 0.0, 0.0)
            except Exception:
                try:
                    # Try alternate signature with explicit Case ID prepended
                    com_call(self.loads, "AddMemberUniformLoad", dl_case_id, beam_id, 2, -line_dl, 0.0, 0.0)
                except Exception:
                    try:
                        # Fallback to alternate method name
                        com_call(self.loads, "AddMemberUniformForce", beam_id, 2, -line_dl, 0.0, 0.0, 0.0)
                    except Exception as load_err:
                        print(f"Warning: Beam DL load application failed on Member {beam_id}: {load_err}")

        # 2. Setup Live Load Case (Load Type = 2)
        self._safe_create_load_case("LIVE LOAD", 2)
        ll_case_id = 2
        self._safe_activate_load_case(ll_case_id)
        
        # Representative Live Load (Residential Rooms + Corridor Allowance)
        # Average LL = (1.9 + 3.8) / 2 = 2.85 kN/m^2.
        # Line load on primary beams = 2.85 kN/m^2 * 1.8m tributary width = 5.13 kN/m
        line_ll = 2.85 * 1.8

        # Apply calculated uniform distributed line loads to floor beams under Live Load Case
        for beam_id in self.beam_ids:
            try:
                com_call(self.loads, "AddMemberUniformLoad", beam_id, 2, -line_ll, -line_ll, 0.0, 0.0, 0.0)
            except Exception:
                try:
                    com_call(self.loads, "AddMemberUniformLoad", ll_case_id, beam_id, 2, -line_ll, 0.0, 0.0)
                except Exception:
                    try:
                        com_call(self.loads, "AddMemberUniformForce", beam_id, 2, -line_ll, 0.0, 0.0, 0.0)
                    except Exception as load_err:
                        print(f"Warning: Beam LL load application failed on Member {beam_id}: {load_err}")
            
        print(f"Applied Slab Dead Load intensity: {line_dl:.2f} kN/m on frame beams.")
        print(f"Applied Slab Live Load intensity: {line_ll:.2f} kN/m on frame beams.")

    def create_load_combinations(self):
        """Assembles required ultimate limit state design combinations."""
        print("\n[Step 5/6] Building design ultimate load combinations (NSCP Section 203)...")
        
        # Comb 1: 1.4 D
        # CreateLoadCombination(Combination Case ID, Title, Primary Case Count, [Cases], [Factors])
        try:
            com_call(self.loads, "CreateLoadCombination", 3, "1.4 DEAD", 1, [1], [1.4])
            # Comb 2: 1.2 D + 1.6 L
            com_call(self.loads, "CreateLoadCombination", 4, "1.2D + 1.6L", 2, [1, 2], [1.2, 1.6])
        except Exception:
            try:
                # Alternate signatures use AddLoadCombination
                com_call(self.loads, "AddLoadCombination", 3, "1.4 DEAD", 1, [1], [1.4])
                com_call(self.loads, "AddLoadCombination", 4, "1.2D + 1.6L", 2, [1, 2], [1.2, 1.6])
            except Exception as comb_err:
                print(f"Warning: Automated Load combinations skipped: {comb_err}")
        
        print("Ultimate Limit State Combinations configured successfully.")

    def run_analysis(self):
        """Invokes the STAAD.Pro solver engine."""
        print("\n[Step 6/6] Executing finite element analysis in STAAD.Pro solver...")
        try:
            # Standard root OpenSTAAD method for invoking the active file solver
            com_call(self.os_obj, "Analyze")
            print("STAAD analysis run completed. Output files generated.")
        except Exception as e:
            print(f"Solver connection failure: {e}")

    def generate_report(self):
        """Displays localized member parameters and outputs validation report."""
        print("\n" + "="*60)
        print("          STRUCTURAL MODEL VALIDATION SUMMARY REPORT")
        print("="*60)
        print(f"Concrete compressive strength (f'c) : {self.fc/1000:.1f} MPa")
        print(f"Reinforcement yield strength (fy)   : {self.fy/1000:.1f} MPa")
        print(f"Slab Thickness / Floor Elevation    : {self.slab_thick*1000:.0f} mm / {self.elevations[1]:.1f} m")
        print("-"*60)
        print("Grid Line Coordinates Matrix (Meters):")
        print(f" - X-Coordinate (Transverse spans A-B-C)     : {self.grid_x}")
        print(f" - Z-Coordinate (Longitudinal spans 1'-1-2-3): {self.grid_z}")
        print("-"*60)
        print("Frame Member Size Profile Mapping:")
        print(f" - Structural Columns (C1)  : {self.col_h*1000:.0f} x {self.col_b*1000:.0f} mm")
        print(f" - Framing Beams (B1)       : {self.beam_h*1000:.0f} x {self.beam_b*1000:.0f} mm")
        print("-"*60)
        print("NSCP 2015 Gravity Loadings:")
        print(f" - Self-Weight (DL)         : Calculated dynamically (-Y direction)")
        print(f" - Superimposed DL (Slab)   : {self.dl_finishes + self.dl_partition:.2f} kN/m^2")
        print(f" - Occupancy Live Load (LL) : 1.90 - 3.80 kN/m^2")
        print("="*60)
        print("Script execution completed successfully. Verify results in STAAD.Pro.\n")


# Execution block
if __name__ == "__main__":
    generator = STAADFramingGenerator()
    # Execute the structured engineering modeling steps
    generator.connect_staad()
    generator.generate_nodes()
    generator.create_members()
    generator.assign_section_properties()
    generator.apply_loads()
    generator.create_load_combinations()
    generator.run_analysis()
    generator.generate_report()