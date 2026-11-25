"""Research data shape and local integrity; no authorization or semantic verdict."""
from typing import Annotated, Literal, Self
from uuid import UUID
from pydantic import Field, HttpUrl, StrictInt, StringConstraints, model_validator
from gabfin.contracts.common import ContractModel, VersionedContract, NonEmptyText, OpaqueKey, UtcTimestamp, Money

Counter = Annotated[StrictInt, Field(ge=0, le=9007199254740991)]
PositiveCount = Annotated[StrictInt, Field(ge=1, le=9007199254740991)]
Digest = Annotated[str, StringConstraints(strict=True, pattern=r'^[a-f0-9]{64}$')]


def unique(values):
    result = set(values)
    if len(result) != len(values):
        raise ValueError('Duplicate identity or reference')
    return result


class DurationHorizon(ContractModel):
    kind: Literal['duration']
    count: PositiveCount
    unit: Literal['minute','hour','calendar_day','trading_day','week','month','year']


class EventHorizon(ContractModel):
    kind: Literal['event']
    name: NonEmptyText
    expected_at: UtcTimestamp | None
    window: DurationHorizon | None = None


class UnspecifiedHorizon(ContractModel):
    kind: Literal['unspecified']
    reason: NonEmptyText


ResearchHorizon = Annotated[DurationHorizon | EventHorizon | UnspecifiedHorizon, Field(discriminator='kind')]


class EvidenceItem(VersionedContract):
    evidence_id: UUID
    url: HttpUrl | None
    artifact_id: UUID | None
    publisher: NonEmptyText
    original_firm: NonEmptyText | None
    published_at: UtcTimestamp | None
    first_seen_at: UtcTimestamp
    available_at: UtcTimestamp
    content_hash: Digest
    license_tag: OpaqueKey

    @model_validator(mode='after')
    def provenance(self) -> Self:
        if self.url is None and self.artifact_id is None:
            raise ValueError('Evidence requires a source URL or artifact')
        if self.first_seen_at > self.available_at:
            raise ValueError('Availability cannot precede first observation')
        if self.url is not None and (self.url.username is not None or self.url.password is not None):
            raise ValueError('Source URL cannot contain credentials')
        return self


class ResearchRequest(VersionedContract):
    request_id: UUID
    instruments: Annotated[tuple[UUID,...], Field(min_length=1)]
    question: NonEmptyText
    horizon: ResearchHorizon
    actor_id: UUID
    capability_scope: Annotated[tuple[OpaqueKey,...], Field(min_length=1)]
    snapshot_id: UUID
    budget_id: UUID
    as_of: UtcTimestamp
    deadline: UtcTimestamp

    @model_validator(mode='after')
    def request_shape(self) -> Self:
        unique(self.instruments)
        unique(self.capability_scope)
        if self.deadline <= self.as_of:
            raise ValueError('Deadline must follow data cutoff')
        return self


class Citation(ContractModel):
    citation_id: UUID
    evidence_id: UUID
    locator: NonEmptyText


class Fact(ContractModel):
    fact_id: UUID
    text: NonEmptyText
    citation_ids: Annotated[tuple[UUID,...], Field(min_length=1)]


class Inference(ContractModel):
    inference_id: UUID
    text: NonEmptyText
    fact_ids: tuple[UUID,...]
    citation_ids: tuple[UUID,...]
    assumptions: tuple[NonEmptyText,...]
    counterevidence: tuple[UUID,...]

    @model_validator(mode='after')
    def premises(self) -> Self:
        if not self.fact_ids and not self.citation_ids:
            raise ValueError('Inference requires supporting premises')
        return self


class MissingData(ContractModel):
    code: OpaqueKey
    description: NonEmptyText
    affected_conclusions: tuple[NonEmptyText,...]


class ResearchSummary(ContractModel):
    why_now: NonEmptyText
    disposition: Literal['watch','avoid','no_edge','insufficient_evidence']
    conditions: tuple[NonEmptyText,...]
    invalidation: tuple[NonEmptyText,...]


class ResearchUsage(ContractModel):
    input_tokens: Counter | None
    output_tokens: Counter | None
    cost: Money | None
    cost_state: Literal['known','unknown']

    @model_validator(mode='after')
    def honest_cost(self) -> Self:
        if (self.cost_state == 'known') != (self.cost is not None):
            raise ValueError('Known cost requires an amount; unknown cost stays null')
        if self.cost is not None and self.cost.amount < 0:
            raise ValueError('Usage cost cannot be negative')
        return self


class ResearchReport(VersionedContract):
    report_id: UUID
    request_id: UUID
    snapshot_id: UUID
    horizon: ResearchHorizon
    evidence: tuple[EvidenceItem,...]
    facts: tuple[Fact,...]
    inferences: tuple[Inference,...]
    citations: tuple[Citation,...]
    missing_data: tuple[MissingData,...]
    summary: ResearchSummary
    completeness: Literal['complete','partial']
    as_of: UtcTimestamp
    generated_at: UtcTimestamp
    model_version: NonEmptyText
    prompt_version: NonEmptyText
    usage: ResearchUsage

    @model_validator(mode='after')
    def document_integrity(self) -> Self:
        evidence_ids = unique(tuple(x.evidence_id for x in self.evidence))
        citation_ids = unique(tuple(x.citation_id for x in self.citations))
        fact_ids = unique(tuple(x.fact_id for x in self.facts))
        unique(tuple(x.inference_id for x in self.inferences))
        for citation in self.citations:
            if citation.evidence_id not in evidence_ids:
                raise ValueError('Citation references missing evidence')
        for fact in self.facts:
            if not unique(fact.citation_ids) <= citation_ids:
                raise ValueError('Fact references missing citation')
        for inference in self.inferences:
            if not unique(inference.fact_ids) <= fact_ids:
                raise ValueError('Inference references missing fact')
            if not unique(inference.citation_ids) <= citation_ids or not unique(inference.counterevidence) <= citation_ids:
                raise ValueError('Inference references missing citation')
        if self.generated_at < self.as_of or any(x.available_at > self.as_of for x in self.evidence):
            raise ValueError('Report violates information cutoff or generation chronology')
        if (self.completeness == 'partial') != bool(self.missing_data):
            raise ValueError('Partial reports require disclosed missing data')
        if self.summary.disposition == 'insufficient_evidence' and self.completeness != 'partial':
            raise ValueError('Insufficient evidence must be disclosed as partial')
        if not self.facts and not self.inferences and not (self.completeness == 'partial' and self.summary.disposition == 'insufficient_evidence'):
            raise ValueError('Empty findings cannot be a successful complete analysis')
        return self
