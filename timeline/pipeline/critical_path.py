"""
CriticalPathEngine — Component 04 Pipeline Step 4.

Implements the Critical Path Method (CPM) using a NetworkX DiGraph.

Definitions used here:
  ES  — Early Start  (earliest day a phase can begin)
  EF  — Early Finish (ES + duration)
  LF  — Late Finish  (latest day a phase can finish without delaying the project)
  LS  — Late Start   (LF - duration)
  TF  — Total Float  (LS - ES); zero means on the critical path)
"""

import networkx as nx

from timeline.pipeline.phases import ALL_PHASES, PHASE_DEPENDENCIES


class CriticalPathEngine:
    """
    Builds the project network and runs a forward/backward CPM pass.

    The graph uses phase names as node labels.  Each node carries a
    ``duration`` attribute (working days) set by build_network().
    """

    def build_network(self, phase_durations: dict[str, int]) -> nx.DiGraph:
        """
        Construct the directed acyclic graph from PHASE_DEPENDENCIES.

        Args:
            phase_durations: Mapping of phase name → working-day duration.

        Returns:
            nx.DiGraph with nodes labelled by phase name and a ``duration``
            attribute on every node.

        Raises:
            ValueError: If a phase present in PHASE_DEPENDENCIES is missing
                        from phase_durations.
        """
        missing = [ph for ph in ALL_PHASES if ph not in phase_durations]
        if missing:
            raise ValueError(
                f"CriticalPathEngine.build_network: missing durations for phases: {missing}"
            )

        G = nx.DiGraph()

        for phase in ALL_PHASES:
            G.add_node(phase, duration=phase_durations[phase])

        for phase, predecessors in PHASE_DEPENDENCIES.items():
            for pred in predecessors:
                G.add_edge(pred, phase)

        if not nx.is_directed_acyclic_graph(G):
            raise ValueError(
                "Phase dependency graph contains a cycle — check PHASE_DEPENDENCIES."
            )

        return G

    def calculate(self, graph: nx.DiGraph) -> dict:
        """
        Run the forward (ES/EF) and backward (LS/LF) CPM passes.

        Total project duration equals the maximum EF across all phases,
        which is identical to the sum of durations along the critical path.

        Args:
            graph: DiGraph produced by build_network().

        Returns:
            dict with keys:
              - ``critical_path``        list[str] in topological order
              - ``total_duration_days``  int
              - ``total_duration_weeks`` float  (5-day week)
              - ``float_per_phase``      dict[str, int]
              - ``early_start_per_phase``  dict[str, int]
              - ``early_finish_per_phase`` dict[str, int]

        Raises:
            ValueError: If the graph contains a cycle or is empty.
        """
        if len(graph) == 0:
            raise ValueError("CriticalPathEngine.calculate received an empty graph.")

        topo_order: list[str] = list(nx.topological_sort(graph))

        # ── Forward pass ──────────────────────────────────────────────────────
        es: dict[str, int] = {}
        ef: dict[str, int] = {}
        for node in topo_order:
            preds = list(graph.predecessors(node))
            es[node] = max((ef[p] for p in preds), default=0)
            ef[node] = es[node] + graph.nodes[node]["duration"]

        project_duration: int = max(ef.values())

        # ── Backward pass ─────────────────────────────────────────────────────
        ls: dict[str, int] = {}
        lf: dict[str, int] = {}
        for node in reversed(topo_order):
            succs = list(graph.successors(node))
            lf[node] = min((ls[s] for s in succs), default=project_duration)
            ls[node] = lf[node] - graph.nodes[node]["duration"]

        # ── Total float and critical path ─────────────────────────────────────
        total_float: dict[str, int] = {node: ls[node] - es[node] for node in graph.nodes()}

        # Preserve topological order so the caller gets a walk-able sequence.
        critical_path: list[str] = [n for n in topo_order if total_float[n] == 0]

        return {
            "critical_path":           critical_path,
            "total_duration_days":     project_duration,
            "total_duration_weeks":    round(project_duration / 5.0, 2),
            "float_per_phase":         total_float,
            "early_start_per_phase":   es,
            "early_finish_per_phase":  ef,
        }
