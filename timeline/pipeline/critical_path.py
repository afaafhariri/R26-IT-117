import networkx as nx
from typing import Dict
from timeline.pipeline import phases

class CriticalPathEngine:
    """
    Constructs the project schedule network and identifies the critical path.
    """

    def build_network(self, phase_durations: Dict[str, int]) -> nx.DiGraph:
        """
        Creates a NetworkX Directed Graph representing the phases and their dependencies.
        
        Args:
            phase_durations: Mapping of phase name to duration in working days.
            
        Returns:
            nx.DiGraph: The populated network graph.
        """
        try:
            G = nx.DiGraph()

            # Add nodes with duration attribute
            for phase, duration in phase_durations.items():
                G.add_node(phase, duration=duration)

            # Define edges based on dependencies
            edges = [
                (phases.SITE_PREPARATION, phases.FOUNDATION),
                (phases.FOUNDATION, phases.SUPERSTRUCTURE),
                (phases.SUPERSTRUCTURE, phases.BRICKWORK_AND_BLOCKWORK),
                (phases.SUPERSTRUCTURE, phases.ROOF_STRUCTURE),
                (phases.ROOF_STRUCTURE, phases.ROOF_COVERING),
                (phases.BRICKWORK_AND_BLOCKWORK, phases.EXTERNAL_PLASTERING),
                (phases.BRICKWORK_AND_BLOCKWORK, phases.INTERNAL_PLASTERING),
                (phases.EXTERNAL_PLASTERING, phases.PAINTING),
                (phases.INTERNAL_PLASTERING, phases.FLOOR_FINISHING),
                (phases.INTERNAL_PLASTERING, phases.CEILING),
                (phases.FLOOR_FINISHING, phases.DOOR_AND_WINDOW_FIXING),
                (phases.ELECTRICAL_FIRST_FIX, phases.CEILING),
                (phases.PLUMBING_FIRST_FIX, phases.CEILING),
                (phases.CEILING, phases.ELECTRICAL_SECOND_FIX),
                (phases.CEILING, phases.PLUMBING_SECOND_FIX),
                (phases.DOOR_AND_WINDOW_FIXING, phases.FINAL_INSPECTION),
                (phases.ELECTRICAL_SECOND_FIX, phases.FINAL_INSPECTION),
                (phases.PLUMBING_SECOND_FIX, phases.FINAL_INSPECTION),
                (phases.EXTERNAL_WORKS, phases.FINAL_INSPECTION),
            ]

            G.add_edges_from(edges)

            # Handle nodes without predecessors (start nodes) and successors (end nodes)
            # Typically, add dummy start/end nodes for cleaner calculation, but we stick to basics here.

            return G

        except Exception as e:
            raise ValueError(f"Error building critical path network: {str(e)}")

    def calculate(self, graph: nx.DiGraph) -> dict:
        """
        Calculates Early Start/Finish, Late Start/Finish, Float, and Critical Path.
        
        Args:
            graph: The NetworkX Digraph from build_network.
            
        Returns:
            dict containing calculated critical path metrics.
        """
        try:
            # Add a single start and end node conceptually, but we can do a topological sort
            es = {}
            ef = {}
            for node in nx.topological_sort(graph):
                preds = list(graph.predecessors(node))
                if not preds:
                    es[node] = 0
                else:
                    es[node] = max(ef[p] for p in preds)
                ef[node] = es[node] + graph.nodes[node]['duration']

            project_duration = max(ef.values())

            ls = {}
            lf = {}
            for node in reversed(list(nx.topological_sort(graph))):
                succs = list(graph.successors(node))
                if not succs:
                    lf[node] = project_duration
                else:
                    lf[node] = min(ls[s] for s in succs)
                ls[node] = lf[node] - graph.nodes[node]['duration']

            float_time = {node: ls[node] - es[node] for node in graph.nodes()}
            critical_path = [node for node in graph.nodes() if float_time[node] == 0]

            return {
                "critical_path": critical_path,
                "total_duration_days": int(project_duration),
                "total_duration_weeks": round(project_duration / 5.0, 2),  # Assuming 5 working days a week
                "float_per_phase": float_time,
                "early_start_per_phase": es,
                "early_finish_per_phase": ef
            }

        except Exception as e:
            raise ValueError(f"Error calculating critical path: {str(e)}")
