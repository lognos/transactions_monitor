"""Graph entry points for the local LangSmith Studio server."""

from . import llm
from .graphs.evaluate import build_evaluate_graph
from .graphs.review import build_review_graph
from .local_demo import LocalDemo

store = LocalDemo()
evaluate_graph = build_evaluate_graph(
    store=store, write_with_audit=store.write_with_audit, recommend=llm.recommend,
)
review_graph = build_review_graph(
    store=store, check_gate=store.check_gate, write_with_audit=store.write_with_audit, learn=llm.learn,
)
