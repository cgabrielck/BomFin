"""Research entry point: registered snapshots, guarded tools and durable audit."""
from pathlib import Path
from uuid import UUID

from gabfin.research.nodes import ResearchRuntime, build_research_graph
from gabfin.research.tools import SnapshotTools


class ResearchService:
    def __init__(self, store, *, model, roles_dir: Path, schema_dir: Path):
        self.store = store
        self.model = model
        self.roles_dir = roles_dir
        self.schema_dir = schema_dir

    async def run(self, snapshot_id: UUID, *, role: str | None = None):
        payload = self.store.get_snapshot(snapshot_id)
        payload['snapshot_id'] = str(payload['snapshot_id'])
        payload['as_of'] = payload['as_of'].isoformat()
        runtime = ResearchRuntime(self.roles_dir, self.schema_dir, model=self.model,
            tools=SnapshotTools(payload['context']).mapping(),
            snapshot_evidence={snapshot_id: self.store.evidence_ids(snapshot_id)},
            audit_sink=self.store.append_check)
        if role is not None:
            return await runtime.run(role, payload)
        return await build_research_graph(runtime).ainvoke({'payload': payload})


def configured_service(store, *, roles_dir: Path, schema_dir: Path):
    """Explicit provider selection; an absent configuration never yields a fake report."""
    from gabfin.research.model import OpenAICompatibleModel, load_model_config
    return ResearchService(store, model=OpenAICompatibleModel(load_model_config()),
                           roles_dir=roles_dir, schema_dir=schema_dir)
