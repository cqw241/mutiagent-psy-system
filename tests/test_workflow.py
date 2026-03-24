from app.graph.workflow import build_graph


def test_graph_compiles_successfully():
    graph = build_graph()
    assert graph is not None
