/* Generated from schemas/gabfin-1.0.json. Run npm run contracts; do not edit. */

export type GabFinContracts =
  | ContractModel
  | Money
  | VersionedContract
  | BarMarketEvent
  | QuoteMarketEvent
  | TradeMarketEvent
  | CalendarSnapshot
  | FeedCleanup
  | FeedHealth
  | FreshnessDecision
  | FreshnessPolicy
  | MarketCursor
  | MarketSnapshot
  | MarketUpdate
  | RecoveryBatch
  | RecoveryCoverage
  | RecoveryGap
  | SessionWindow
  | Capability
  | Principal
  | Resource
  | ResourceKind
  | Role
  | IndicatorPoint
  | IndicatorSeries
  | IndicatorStatus
  | PositionEffect
  | PositionSide
  | StrategyIntent
  | TradePlan
  | ErrorFrame
  | ResumeFrame
  | SnapshotFrame
  | StreamHello
  | UpdateFrame
  | JobLease
  | Reservation
  | ReservationStatus
  | AssetClass
  | Bar
  | BarStatus
  | EntitlementStatus
  | Instrument2
  | MarketSession
  | OptionRight
  | OptionTerms
  | QuoteEntitlements
  | QuotePoint
  | QuoteQuality
  | QuoteSnapshot
  | TimeUnit
  | Timeframe
  | TradeTick
  | OrderCommand
  | OrderEvent
  | PolicyVersion2
  | RiskBounds
  | RiskCheck
  | RiskDecision
  | Citation
  | DurationHorizon
  | EventHorizon
  | EvidenceItem
  | Fact
  | Inference
  | MissingData
  | ResearchReport
  | ResearchRequest
  | ResearchSummary
  | ResearchUsage
  | UnspecifiedHorizon
  | Demand
  | FeedCapabilities
  | HistoryLimit
  | SequenceRule
  | SubscriptionKey
  | SubscriptionPlan
  | SubscriptionRejection
  | AccountSnapshot
  | BrokerSnapshot
  | CandidateObservation
  | ExperimentResult
  | ExperimentSpec
  | HarnessProposal
  | HealthReport
  | ModelMessage
  | ModelRequest
  | ModelResult
  | OrderSnapshot
  | Position
  | ReconciliationResult
  | RiskContext
  | StrategyContext
  | SubmitResult
  | TapeManifest
  | TapePartition
  | TapeReadResult
  | TapeSeries
  | TapeWriteResult
  | MarketRequest
  | MarketStreamRequest;
export type Amount = string;
export type Currency = string;
export type SchemaVersion = '1.0';
export type AvailableAt = string;
export type DedupKey = string;
export type EventAt = string;
export type EventId = string;
export type InstrumentId = string;
export type Kind = 'bar';
export type AvailableAt1 = string;
export type Close = string;
export type CorporateActionPolicy = string;
export type End = string;
export type EventAt1 = string;
export type High = string;
export type InstrumentId1 = string;
export type Low = string;
export type Open = string;
export type ReceivedAt = string;
export type Revision = number;
export type SchemaVersion1 = '1.0';
export type MarketSession = 'pre_market' | 'regular' | 'post_market' | 'overnight' | 'closed' | 'unknown';
export type Source = string;
export type Start = string;
export type BarStatus = 'forming' | 'final' | 'corrected';
export type Count = number;
export type TimeUnit = 'second' | 'minute' | 'hour' | 'trading_day' | 'week' | 'month' | 'year';
export type Volume = string | null;
export type ReceivedAt1 = string;
export type SchemaVersion2 = '1.0';
export type Source1 = string;
export type SourceSeq = string | null;
export type AvailableAt2 = string;
export type DedupKey1 = string;
export type EventAt2 = string;
export type EventId1 = string;
export type InstrumentId2 = string;
export type Kind1 = 'quote';
export type AsOf = string;
export type AgeMs = number | null;
export type AvailableAt3 = string;
export type EventAt3 = string | null;
export type Price = string;
export type ReceivedAt2 = string;
export type CapabilitySnapshotId = string | null;
export type CheckedAt = string | null;
export type EntitlementStatus = 'unknown' | 'realtime' | 'delayed' | 'indicative' | 'denied';
export type Feed = string;
export type InstrumentId3 = string;
export type QuoteQuality =
  | 'unknown'
  | 'delayed'
  | 'indicative'
  | 'stale'
  | 'incomplete'
  | 'clock_skew'
  | 'crossed'
  | 'permission_denied'
  | 'unavailable';
export type Quality = QuoteQuality[];
export type SchemaVersion3 = '1.0';
export type ReceivedAt3 = string;
export type SchemaVersion4 = '1.0';
export type Source2 = string;
export type SourceSeq1 = string | null;
export type AvailableAt4 = string;
export type DedupKey2 = string;
export type EventAt4 = string;
export type EventId2 = string;
export type InstrumentId4 = string;
export type Kind2 = 'trade';
export type InstrumentId5 = string;
export type Price1 = string;
export type Quantity = string;
export type SchemaVersion5 = '1.0';
export type TradeId = string | null;
export type ReceivedAt4 = string;
export type SchemaVersion6 = '1.0';
export type Source3 = string;
export type SourceSeq2 = string | null;
export type CalendarId = string;
export type CoverageEnd = string;
export type CoverageStart = string;
export type SchemaVersion7 = '1.0';
export type Version = string;
export type End1 = string;
export type SchemaVersion8 = '1.0';
export type Session = 'pre_market' | 'regular' | 'post_market';
export type Start1 = string;
/**
 * @maxItems 10000
 */
export type Windows = SessionWindow[];
export type ContextClosed = boolean;
export type ReasonCodes = string[];
export type ReleaseConfirmed = boolean;
export type Channel = 'quote' | 'trade' | 'bar';
export type InstrumentId6 = string;
export type RequestedKeys = SubscriptionKey[];
export type SchemaVersion9 = '1.0';
export type Source4 = string;
export type Connected = boolean;
export type ConnectionStartedAt = string | null;
export type GapPending = boolean;
export type HeartbeatAt = string | null;
export type SchemaVersion10 = '1.0';
export type Source5 = string;
export type Eligible = boolean;
export type EvaluatedAt = string;
export type PolicyVersion = string;
/**
 * @minItems 1
 */
export type Reasons = [string, ...string[]];
export type SchemaVersion11 = '1.0';
/**
 * @minItems 1
 */
export type AllowedSessions = [
  'pre_market' | 'regular' | 'post_market',
  ...('pre_market' | 'regular' | 'post_market')[]
];
export type Approved = boolean;
export type MaxEntitlementAgeMs = number;
export type MaxHeartbeatAgeMs = number;
export type MaxQuoteAgeMs = number;
export type SchemaVersion12 = '1.0';
export type Version1 = string;
export type Epoch = string;
export type Sequence = number;
export type AsOf1 = string;
export type Bars = BarMarketEvent[];
export type Cursor = number;
export type Epoch1 = string;
export type End2 = string | null;
export type GapId = string;
export type Reason = string;
export type SchemaVersion13 = '1.0';
export type Source6 = string;
export type Start2 = string;
export type Quotes = QuoteMarketEvent[];
export type SchemaVersion14 = '1.0';
export type Epoch2 = string;
export type Event = (QuoteMarketEvent | TradeMarketEvent | BarMarketEvent) | null;
export type ProcessedAt = string;
export type SchemaVersion15 = '1.0';
export type Sequence1 = number;
export type Complete = boolean;
export type Complete1 = boolean;
export type EmptyReason = ('provider_verified_empty' | 'market_closed') | null;
export type End3 = string;
export type HasMore = boolean;
export type RecordCount = number;
export type Start3 = string;
/**
 * @maxItems 3000
 */
export type Coverage = RecoveryCoverage[];
export type End4 = string;
/**
 * @maxItems 10000
 */
export type Events = (QuoteMarketEvent | TradeMarketEvent | BarMarketEvent)[];
export type Evidence = string;
export type GapId1 = string;
export type Mode = 'history' | 'quote_snapshot';
export type SchemaVersion16 = '1.0';
export type Source7 = string;
export type Start4 = string;
export type Capability =
  | 'read_account'
  | 'resolve_symbols'
  | 'start_research'
  | 'read_report'
  | 'draft_trade_plan'
  | 'read_market'
  | 'manage_watchlist'
  | 'propose_strategy'
  | 'strategy:emit'
  | 'submit_order'
  | 'cancel_order'
  | 'start_worker'
  | 'pause_worker'
  | 'resume_worker'
  | 'write_policy'
  | 'approve_proposal';
export type ActorId = string;
export type Role = 'owner' | 'chat' | 'research' | 'strategy' | 'executor';
export type SchemaVersion17 = '1.0';
export type Scope = Capability[];
export type Id = string;
export type ResourceKind =
  | 'account'
  | 'instrument'
  | 'research_job'
  | 'research_report'
  | 'watchlist'
  | 'order'
  | 'strategy'
  | 'policy'
  | 'proposal'
  | 'artifact';
export type Owner = string;
export type SchemaVersion18 = '1.0';
export type ComputedAt = string;
export type ComputedBy = 'local' | 'futu_api';
export type EventAt5 = string;
export type Indicator =
  | 'sma'
  | 'ema'
  | 'wma'
  | 'macd'
  | 'macd_signal'
  | 'macd_histogram'
  | 'rsi'
  | 'stochastic_k'
  | 'stochastic_d'
  | 'stochastic_j'
  | 'roc'
  | 'momentum'
  | 'atr'
  | 'bollinger_upper'
  | 'bollinger_middle'
  | 'bollinger_lower'
  | 'bollinger_percent_b'
  | 'bollinger_bandwidth'
  | 'donchian_upper'
  | 'donchian_lower'
  | 'historical_volatility'
  | 'obv'
  | 'volume_sma'
  | 'mfi'
  | 'vwap';
export type InstrumentId7 = string;
export type Realtime = boolean;
export type SchemaVersion19 = '1.0';
export type SourceCoverage = 'iex' | 'sip' | 'futu_nasdaq_totalview' | 'futu_arca' | 'unknown';
export type Value = string | null;
export type Indicator1 =
  | 'sma'
  | 'ema'
  | 'wma'
  | 'macd'
  | 'macd_signal'
  | 'macd_histogram'
  | 'rsi'
  | 'stochastic_k'
  | 'stochastic_d'
  | 'stochastic_j'
  | 'roc'
  | 'momentum'
  | 'atr'
  | 'bollinger_upper'
  | 'bollinger_middle'
  | 'bollinger_lower'
  | 'bollinger_percent_b'
  | 'bollinger_bandwidth'
  | 'donchian_upper'
  | 'donchian_lower'
  | 'historical_volatility'
  | 'obv'
  | 'volume_sma'
  | 'mfi'
  | 'vwap';
export type InstrumentId8 = string;
/**
 * @maxItems 100000
 */
export type Points = IndicatorPoint[];
export type SourceCoverage1 = 'iex' | 'sip' | 'futu_nasdaq_totalview' | 'futu_arca' | 'unknown';
export type Indicator2 =
  | 'sma'
  | 'ema'
  | 'wma'
  | 'macd'
  | 'macd_signal'
  | 'macd_histogram'
  | 'rsi'
  | 'stochastic_k'
  | 'stochastic_d'
  | 'stochastic_j'
  | 'roc'
  | 'momentum'
  | 'atr'
  | 'bollinger_upper'
  | 'bollinger_middle'
  | 'bollinger_lower'
  | 'bollinger_percent_b'
  | 'bollinger_bandwidth'
  | 'donchian_upper'
  | 'donchian_lower'
  | 'historical_volatility'
  | 'obv'
  | 'volume_sma'
  | 'mfi'
  | 'vwap';
export type ObservedBars = number | null;
export type Ready = boolean;
export type Reason1 = string | null;
export type RequiredBars = number | null;
export type PositionEffect = 'open' | 'reduce' | 'close';
/**
 * Position direction, independent of the broker's buy/sell order side.
 */
export type PositionSide = 'long' | 'short';
export type ExpiresAt = string;
export type Instrument = string;
export type IntentId = string;
export type Invalidation = string;
export type Kind3 = 'strategy_intent';
export type PolicyVersion1 = string;
export type ProducerScope = 'strategy:emit';
export type SchemaVersion20 = '1.0';
export type Setup = string;
export type SnapshotId = string;
export type StrategyVersion = string;
export type Advisory = true;
export type AsOf2 = string;
export type EntryScenarios = string[];
export type Evidence1 = string[];
export type ExitScenarios = string[];
export type Instrument1 = string;
export type Kind4 = 'trade_plan';
export type SchemaVersion21 = '1.0';
export type Code = 'unauthorized' | 'invalid_request' | 'snapshot_required' | 'slow_consumer';
export type Kind5 = 'error';
export type Version2 = 1;
export type Cursor1 = number;
export type Epoch3 = string;
export type Kind6 = 'resumed';
export type Version3 = 1;
export type Kind7 = 'snapshot';
export type Version4 = 1;
export type Cursor2 = number | null;
export type Epoch4 = string | null;
/**
 * @minItems 1
 * @maxItems 1000
 */
export type InstrumentIds = [string, ...string[]];
export type Token = string;
export type Version5 = number;
export type Kind8 = 'update';
export type Version6 = 1;
export type AcquiredAt = string;
export type Attempt = number;
export type ExpiresAt1 = string;
export type JobId = string;
export type LeaseToken = string;
export type SchemaVersion22 = '1.0';
export type WorkerId = string;
export type ActualAmount = string | null;
export type Amount1 = string;
export type BudgetId = string;
export type CreatedAt = string;
export type Currency1 = string;
export type JobId1 = string;
export type ReservationId = string;
export type SchemaVersion23 = '1.0';
export type ReservationStatus = 'reserved' | 'settled' | 'released' | 'unknown';
export type UpdatedAt = string;
export type AssetClass = 'equity' | 'option';
export type Currency2 = string;
export type InstrumentId9 = string;
export type LotSize = string;
export type Expiry = string;
export type Multiplier = string;
export type OptionRight = 'call' | 'put';
export type Strike = string;
export type UnderlyingId = string;
export type SchemaVersion24 = '1.0';
export type TickSize = string;
export type ClientOrderId = string;
export type Instrument3 = string;
export type IntentId1 = string;
export type LimitPrice = string | null;
export type Qty = string;
export type RiskDecisionId = string;
export type SchemaVersion25 = '1.0';
export type Session1 = 'pre_market' | 'regular' | 'post_market';
export type Side = 'buy' | 'sell';
export type Tif = 'day' | 'gtc' | 'ioc' | 'fok';
export type Type = 'market' | 'limit';
export type AvailableAt5 = string;
export type BrokerId = string | null;
export type ClientOrderId1 = string;
export type CumFillQty = string;
export type DedupKey3 = string;
export type EventAt6 = string;
export type EventId3 = string;
export type EvidenceId = string | null;
export type FillEvidence = 'unavailable' | 'broker_reported';
export type FillPrice = string | null;
export type ReceivedAt5 = string;
export type SchemaVersion26 = '1.0';
export type Status =
  | 'proposed'
  | 'approved'
  | 'send_pending'
  | 'acknowledged'
  | 'partial'
  | 'filled'
  | 'canceled'
  | 'rejected'
  | 'unknown';
export type AllowedAssets = 'equity'[];
export type AllowedSessions1 = ('pre_market' | 'regular' | 'post_market')[];
export type AllowedStrategies = string[];
export type ApprovalHash = string | null;
export type ApprovedAt = string | null;
export type DailyLoss = string | null;
export type GrossExposureLeverage = string | null;
export type MissingDataPolicy = 'halt_entries' | null;
export type PerTradeRisk = string | null;
export type RuntimeDrawdown = string | null;
export type SchemaVersion27 = '1.0';
export type Status1 = 'draft' | 'approved' | 'retired';
export type Version7 = string;
export type Code1 = string;
export type Passed = boolean;
export type Approved1 = boolean;
/**
 * @minItems 1
 */
export type Checks = [RiskCheck, ...RiskCheck[]];
export type DecisionId = string;
export type ExpiresAt2 = string;
export type IntentId2 = string;
export type PolicyVersion3 = string;
export type Quantity1 = string | null;
/**
 * @minItems 1
 */
export type ReasonCodes1 = [string, ...string[]];
export type SchemaVersion28 = '1.0';
export type CitationId = string;
export type EvidenceId1 = string;
export type Locator = string;
export type Count1 = number;
export type Kind9 = 'duration';
export type Unit = 'minute' | 'hour' | 'calendar_day' | 'trading_day' | 'week' | 'month' | 'year';
export type ExpectedAt = string | null;
export type Kind10 = 'event';
export type Name = string;
export type ArtifactId = string | null;
export type AvailableAt6 = string;
export type ContentHash = string;
export type EvidenceId2 = string;
export type FirstSeenAt = string;
export type LicenseTag = string;
export type OriginalFirm = string | null;
export type PublishedAt = string | null;
export type Publisher = string;
export type SchemaVersion29 = '1.0';
export type Url = string | null;
/**
 * @minItems 1
 */
export type CitationIds = [string, ...string[]];
export type FactId = string;
export type Text = string;
export type Assumptions = string[];
export type CitationIds1 = string[];
export type Counterevidence = string[];
export type FactIds = string[];
export type InferenceId = string;
export type Text1 = string;
export type AffectedConclusions = string[];
export type Code2 = string;
export type Description = string;
export type AsOf3 = string;
export type Citations = Citation[];
export type Completeness = 'complete' | 'partial';
export type Evidence2 = EvidenceItem[];
export type Facts = Fact[];
export type GeneratedAt = string;
export type Horizon = DurationHorizon | EventHorizon | UnspecifiedHorizon;
export type Kind11 = 'unspecified';
export type Reason2 = string;
export type Inferences = Inference[];
export type MissingData1 = MissingData[];
export type ModelVersion = string;
export type PromptVersion = string;
export type ReportId = string;
export type RequestId = string;
export type SchemaVersion30 = '1.0';
export type SnapshotId1 = string;
export type Conditions = string[];
export type Disposition = 'watch' | 'avoid' | 'no_edge' | 'insufficient_evidence';
export type Invalidation1 = string[];
export type WhyNow = string;
export type CostState = 'known' | 'unknown';
export type InputTokens = number | null;
export type OutputTokens = number | null;
export type ActorId1 = string;
export type AsOf4 = string;
export type BudgetId1 = string;
/**
 * @minItems 1
 */
export type CapabilityScope = [string, ...string[]];
export type Deadline = string;
export type Horizon1 = DurationHorizon | EventHorizon | UnspecifiedHorizon;
/**
 * @minItems 1
 */
export type Instruments = [string, ...string[]];
export type Question = string;
export type RequestId1 = string;
export type SchemaVersion31 = '1.0';
export type SnapshotId2 = string;
export type DemandId = string;
export type ExpiresAt3 = string;
export type Owner1 = string;
export type Priority = 'holding' | 'chart' | 'strategy' | 'watchlist' | 'candidate';
export type SchemaVersion32 = '1.0';
export type AssetClasses = AssetClass[];
export type CheckedAt1 = string;
export type Channel1 = 'quote' | 'trade' | 'bar';
export type MaxRecords = number | null;
export type HistoryLimits = HistoryLimit[];
export type LatencyLabel = 'unknown' | 'realtime' | 'delayed' | 'indicative';
export type MaxSubscriptions = number | null;
export type PermissionErrors = string[];
export type SchemaVersion33 = '1.0';
export type Channel2 = 'quote' | 'trade' | 'bar';
export type Semantics = 'opaque' | 'contiguous';
export type SequenceRules = SequenceRule[];
export type Sessions = MarketSession[];
export type Source8 = string;
export type Accepted = SubscriptionKey[];
export type AsOf5 = string;
/**
 * @minItems 1
 */
export type ReasonCodes2 = [string, ...string[]];
export type Rejected = SubscriptionRejection[];
export type SchemaVersion34 = '1.0';
export type Source9 = string;
export type AsOf6 = string;
export type SchemaVersion35 = '1.0';
export type SnapshotId3 = string;
export type AsOf7 = string;
export type Complete2 = boolean;
export type OpenOrders = OrderCommand[];
export type InstrumentId10 = string;
export type Quantity2 = string;
export type Positions = Position[];
export type RecentFills = OrderEvent[];
export type SchemaVersion36 = '1.0';
export type SnapshotId4 = string;
export type Action = 'include' | 'exclude';
/**
 * @minItems 1
 */
export type Evidence3 = [string, ...string[]];
export type ExpiresAt4 = string;
export type Horizon2 = DurationHorizon | EventHorizon | UnspecifiedHorizon;
export type Instrument4 = string;
export type ObservationId = string;
export type ObservedAt = string;
export type Reason3 = string;
export type SchemaVersion37 = '1.0';
export type Equity = Money[];
export type Events1 = string[];
export type ExperimentId = string;
export type Fills = OrderEvent[];
export type SchemaVersion38 = '1.0';
export type Warnings = string[];
export type DatasetManifest = string;
export type End5 = string;
export type ExecutionAssumptions = string[];
export type ExperimentId1 = string;
export type SchemaVersion39 = '1.0';
export type SessionPolicy = string[];
export type Start5 = string;
export type StrategyVersion1 = string;
export type Approval = string | null;
export type ArtifactHash = string;
export type BaseVersion = string;
export type DeployVersion = string;
export type Diff = string;
/**
 * @minItems 1
 */
export type ExperimentIds = [string, ...string[]];
export type ProposalId = string;
export type RollbackVersion = string;
export type SchemaVersion40 = '1.0';
export type Component = string;
export type HeartbeatAt1 = string;
export type LagMs = number | null;
export type LastErrorCode = string | null;
export type SchemaVersion41 = '1.0';
export type State = 'healthy' | 'degraded' | 'unavailable' | 'unknown';
export type Content = string;
export type Role1 = 'system' | 'user' | 'assistant';
export type Deadline1 = string;
export type EvidenceRefs = string[];
/**
 * @minItems 1
 */
export type Messages = [ModelMessage, ...ModelMessage[]];
export type Model = string;
export type JsonValue = unknown;
export type RequestId2 = string;
export type SchemaVersion42 = '1.0';
export type Error = string | null;
export type Model1 = string;
export type Output = {
  [k: string]: JsonValue;
} | null;
export type RequestId3 = string;
export type SchemaVersion43 = '1.0';
export type AsOf8 = string;
export type SchemaVersion44 = '1.0';
export type EntryAllowed = boolean;
export type Matched = boolean;
export type Mismatches = string[];
export type SchemaVersion45 = '1.0';
export type BorrowAvailable = boolean | null;
export type PendingOrders = OrderCommand[];
export type PolicyVersion4 = string;
export type Quotes1 = QuoteSnapshot[];
export type SchemaVersion46 = '1.0';
export type Session2 = 'pre_market' | 'regular' | 'post_market';
export type SnapshotId5 = string;
export type AccountSnapshotId = string;
export type AsOf9 = string;
export type FinalizedBars = Bar[];
export type PolicyVersion5 = string;
export type SchemaVersion47 = '1.0';
export type StrategyVersion2 = string;
export type BrokerId1 = string | null;
export type ClientOrderId2 = string;
export type Reason4 = string | null;
export type SchemaVersion48 = '1.0';
export type Status2 = 'ACKNOWLEDGED' | 'REJECTED' | 'UNKNOWN';
export type Complete3 = boolean;
export type MaxEventAt = string | null;
export type MinEventAt = string | null;
export type Path = string;
export type Rows = number;
export type Sha256 = string;
export type Partitions = TapePartition[];
export type PrecisionPolicy = string;
export type SchemaVersion49 = '1.0';
export type Adjustment = string;
export type Complete4 = boolean;
export type CoverageEnd1 = string | null;
export type CoverageStart1 = string | null;
export type Retention = 'full_history' | 'rolling_2y';
export type RowCount = number;
export type SchemaVersion50 = '1.0';
export type SeriesId = string;
export type Source10 = string;
export type Symbol = string;
export type VenueCoverage = string;
export type WrittenAt = string;
export type MaxEventAt1 = string | null;
export type MinEventAt1 = string | null;
export type Rows1 = number;
export type RowsOutsideRetention = number;
export type DroppedOutsideRetention = number;
export type Partitions1 = TapePartition[];
/**
 * @minItems 1
 * @maxItems 64
 */
export type Keys = [SubscriptionKey, ...SubscriptionKey[]];
export type Version8 = number;
export type Cursor3 = number | null;
export type Epoch5 = string | null;
/**
 * @minItems 1
 * @maxItems 64
 */
export type Keys1 = [SubscriptionKey, ...SubscriptionKey[]];
export type Version9 = number;

/**
 * Reject unknown fields and accidental reassignment, not an auth boundary.
 */
export interface ContractModel {}
/**
 * A signed amount and code shape; no rounding, currency lookup or FX.
 */
export interface Money {
  amount: Amount;
  currency: Currency;
}
export interface VersionedContract {
  schema_version: SchemaVersion;
}
export interface BarMarketEvent {
  available_at: AvailableAt;
  dedup_key: DedupKey;
  event_at: EventAt;
  event_id: EventId;
  instrument_id: InstrumentId;
  kind: Kind;
  payload: Bar;
  received_at: ReceivedAt1;
  schema_version: SchemaVersion2;
  source: Source1;
  source_seq: SourceSeq;
}
export interface Bar {
  available_at: AvailableAt1;
  close: Close;
  corporate_action_policy: CorporateActionPolicy;
  end: End;
  event_at: EventAt1;
  high: High;
  instrument_id: InstrumentId1;
  low: Low;
  open: Open;
  received_at: ReceivedAt;
  revision: Revision;
  schema_version: SchemaVersion1;
  session: MarketSession;
  source: Source;
  start: Start;
  status: BarStatus;
  timeframe: Timeframe;
  volume: Volume;
}
export interface Timeframe {
  count: Count;
  unit: TimeUnit;
}
export interface QuoteMarketEvent {
  available_at: AvailableAt2;
  dedup_key: DedupKey1;
  event_at: EventAt2;
  event_id: EventId1;
  instrument_id: InstrumentId2;
  kind: Kind1;
  payload: QuoteSnapshot;
  received_at: ReceivedAt3;
  schema_version: SchemaVersion4;
  source: Source2;
  source_seq: SourceSeq1;
}
/**
 * Per-price ages are relative to as_of, never a live wall clock.
 */
export interface QuoteSnapshot {
  as_of: AsOf;
  ask: QuotePoint | null;
  bid: QuotePoint | null;
  entitlements: QuoteEntitlements;
  feed: Feed;
  instrument_id: InstrumentId3;
  last: QuotePoint | null;
  quality: Quality;
  schema_version: SchemaVersion3;
  session: MarketSession;
}
export interface QuotePoint {
  age_ms: AgeMs;
  available_at: AvailableAt3;
  event_at: EventAt3;
  price: Price;
  received_at: ReceivedAt2;
}
/**
 * Reported metadata; actual capability verification is a service duty.
 */
export interface QuoteEntitlements {
  capability_snapshot_id?: CapabilitySnapshotId;
  checked_at: CheckedAt;
  status: EntitlementStatus;
}
export interface TradeMarketEvent {
  available_at: AvailableAt4;
  dedup_key: DedupKey2;
  event_at: EventAt4;
  event_id: EventId2;
  instrument_id: InstrumentId4;
  kind: Kind2;
  payload: TradeTick;
  received_at: ReceivedAt4;
  schema_version: SchemaVersion6;
  source: Source3;
  source_seq: SourceSeq2;
}
/**
 * A market print, not an account fill or an instruction to trade.
 */
export interface TradeTick {
  instrument_id: InstrumentId5;
  price: Price1;
  quantity: Quantity;
  schema_version: SchemaVersion5;
  trade_id: TradeId;
}
/**
 * Exchange-sourced, finite coverage; absence inside coverage means closed.
 *
 * Ingestion supplies verified calendar identity/version. No weekday fallback.
 */
export interface CalendarSnapshot {
  calendar_id: CalendarId;
  coverage_end: CoverageEnd;
  coverage_start: CoverageStart;
  schema_version: SchemaVersion7;
  version: Version;
  windows: Windows;
}
export interface SessionWindow {
  end: End1;
  schema_version: SchemaVersion8;
  session: Session;
  start: Start1;
}
export interface FeedCleanup {
  context_closed: ContextClosed;
  reason_codes: ReasonCodes;
  release_confirmed: ReleaseConfirmed;
  requested_keys: RequestedKeys;
  schema_version: SchemaVersion9;
  source: Source4;
}
export interface SubscriptionKey {
  channel: Channel;
  instrument_id: InstrumentId6;
  timeframe: Timeframe | null;
}
export interface FeedHealth {
  connected: Connected;
  connection_started_at?: ConnectionStartedAt;
  gap_pending: GapPending;
  heartbeat_at: HeartbeatAt;
  schema_version: SchemaVersion10;
  source: Source5;
}
/**
 * Data prerequisites only. Risk, account, strategy and execution remain separate.
 */
export interface FreshnessDecision {
  ages_ms: AgesMs;
  eligible: Eligible;
  evaluated_at: EvaluatedAt;
  policy_version: PolicyVersion;
  reasons: Reasons;
  schema_version: SchemaVersion11;
}
export interface AgesMs {
  [k: string]: number | null;
}
/**
 * Caller must supply a registry-verified policy; there are no defaults.
 */
export interface FreshnessPolicy {
  allowed_sessions: AllowedSessions;
  approved: Approved;
  max_entitlement_age_ms: MaxEntitlementAgeMs;
  max_heartbeat_age_ms: MaxHeartbeatAgeMs;
  max_quote_age_ms: MaxQuoteAgeMs;
  schema_version: SchemaVersion12;
  version: Version1;
}
export interface MarketCursor {
  epoch: Epoch;
  sequence: Sequence;
}
export interface MarketSnapshot {
  as_of: AsOf1;
  bars: Bars;
  cursor: Cursor;
  epoch: Epoch1;
  gap: RecoveryGap | null;
  health: FeedHealth;
  quotes: Quotes;
  schema_version: SchemaVersion14;
}
export interface RecoveryGap {
  end?: End2;
  gap_id: GapId;
  reason: Reason;
  schema_version: SchemaVersion13;
  source: Source6;
  start: Start2;
}
export interface MarketUpdate {
  epoch: Epoch2;
  event: Event;
  gap: RecoveryGap | null;
  health: FeedHealth;
  processed_at: ProcessedAt;
  schema_version: SchemaVersion15;
  sequence: Sequence1;
}
export interface RecoveryBatch {
  complete: Complete;
  coverage?: Coverage;
  end: End4;
  events: Events;
  evidence: Evidence;
  gap_id: GapId1;
  mode?: Mode;
  schema_version: SchemaVersion16;
  source: Source7;
  start: Start4;
}
/**
 * Trusted history adapter's pagination/coverage receipt, per subscription.
 *
 * This is evidence supplied by a verified adapter, not a claim accepted from
 * consumers. Empty history needs an explicit provider/calendar explanation.
 */
export interface RecoveryCoverage {
  complete: Complete1;
  empty_reason?: EmptyReason;
  end: End3;
  has_more: HasMore;
  key: SubscriptionKey;
  record_count: RecordCount;
  start: Start3;
}
export interface Principal {
  actor_id: ActorId;
  role: Role;
  schema_version: SchemaVersion17;
  scope: Scope;
}
export interface Resource {
  id: Id;
  kind: ResourceKind;
  owner: Owner;
  schema_version: SchemaVersion18;
}
/**
 * One computed indicator value at one instant.
 */
export interface IndicatorPoint {
  computed_at: ComputedAt;
  computed_by: ComputedBy;
  event_at: EventAt5;
  indicator: Indicator;
  instrument_id: InstrumentId7;
  params: Params;
  realtime?: Realtime;
  schema_version: SchemaVersion19;
  source_coverage: SourceCoverage;
  timeframe: Timeframe;
  value: Value;
}
export interface Params {
  [k: string]: string;
}
/**
 * A run of indicator points for one indicator and one parameter set.
 */
export interface IndicatorSeries {
  indicator: Indicator1;
  instrument_id: InstrumentId8;
  params: Params1;
  points: Points;
  source_coverage: SourceCoverage1;
  timeframe: Timeframe;
}
export interface Params1 {
  [k: string]: string;
}
/**
 * Why an indicator has no value, or that it has one.
 */
export interface IndicatorStatus {
  indicator: Indicator2;
  observed_bars?: ObservedBars;
  params: Params2;
  ready: Ready;
  reason?: Reason1;
  required_bars?: RequiredBars;
}
export interface Params2 {
  [k: string]: string;
}
/**
 * Strategy output to risk evaluation; not a broker order or approval.
 */
export interface StrategyIntent {
  expires_at: ExpiresAt;
  instrument: Instrument;
  intent_id: IntentId;
  invalidation: Invalidation;
  kind: Kind3;
  policy_version: PolicyVersion1;
  position_effect: PositionEffect;
  producer_scope: ProducerScope;
  schema_version: SchemaVersion20;
  setup: Setup;
  side: PositionSide;
  snapshot_id: SnapshotId;
  strategy_version: StrategyVersion;
}
/**
 * Research/chat output for display; never a strategy/executor input.
 */
export interface TradePlan {
  advisory: Advisory;
  as_of: AsOf2;
  entry_scenarios: EntryScenarios;
  evidence: Evidence1;
  exit_scenarios: ExitScenarios;
  instrument: Instrument1;
  kind: Kind4;
  schema_version: SchemaVersion21;
  side: PositionSide;
}
export interface ErrorFrame {
  code: Code;
  kind: Kind5;
  version: Version2;
}
export interface ResumeFrame {
  cursor: Cursor1;
  epoch: Epoch3;
  kind: Kind6;
  version: Version3;
}
export interface SnapshotFrame {
  kind: Kind7;
  payload: MarketSnapshot;
  version: Version4;
}
export interface StreamHello {
  cursor?: Cursor2;
  epoch?: Epoch4;
  instrument_ids: InstrumentIds;
  token: Token;
  version: Version5;
}
export interface UpdateFrame {
  kind: Kind8;
  payload: MarketUpdate;
  version: Version6;
}
export interface JobLease {
  acquired_at: AcquiredAt;
  attempt: Attempt;
  expires_at: ExpiresAt1;
  job_id: JobId;
  lease_token: LeaseToken;
  schema_version: SchemaVersion22;
  worker_id: WorkerId;
}
export interface Reservation {
  actual_amount: ActualAmount;
  amount: Amount1;
  budget_id: BudgetId;
  created_at: CreatedAt;
  currency: Currency1;
  job_id: JobId1;
  reservation_id: ReservationId;
  schema_version: SchemaVersion23;
  status: ReservationStatus;
  updated_at: UpdatedAt;
}
export interface Instrument2 {
  asset_class: AssetClass;
  currency: Currency2;
  instrument_id: InstrumentId9;
  lot_size: LotSize;
  option?: OptionTerms | null;
  schema_version: SchemaVersion24;
  tick_size: TickSize;
  vendor_symbols: VendorSymbols;
}
export interface OptionTerms {
  expiry: Expiry;
  multiplier: Multiplier;
  right: OptionRight;
  strike: Strike;
  underlying_id: UnderlyingId;
}
export interface VendorSymbols {
  [k: string]: string;
}
export interface OrderCommand {
  client_order_id: ClientOrderId;
  instrument: Instrument3;
  intent_id: IntentId1;
  limit_price: LimitPrice;
  qty: Qty;
  risk_decision_id: RiskDecisionId;
  schema_version: SchemaVersion25;
  session: Session1;
  side: Side;
  tif: Tif;
  type: Type;
}
export interface OrderEvent {
  available_at: AvailableAt5;
  broker_id: BrokerId;
  client_order_id: ClientOrderId1;
  cum_fill_qty: CumFillQty;
  dedup_key: DedupKey3;
  event_at: EventAt6;
  event_id: EventId3;
  evidence_id: EvidenceId;
  fill_evidence: FillEvidence;
  fill_price: FillPrice;
  received_at: ReceivedAt5;
  schema_version: SchemaVersion26;
  status: Status;
}
export interface PolicyVersion2 {
  allowed_assets: AllowedAssets;
  allowed_sessions: AllowedSessions1;
  allowed_strategies: AllowedStrategies;
  approval_hash: ApprovalHash;
  approved_at: ApprovedAt;
  risk_bounds: RiskBounds;
  schema_version: SchemaVersion27;
  status: Status1;
  version: Version7;
}
export interface RiskBounds {
  daily_loss: DailyLoss;
  gross_exposure_leverage: GrossExposureLeverage;
  missing_data_policy: MissingDataPolicy;
  per_trade_risk: PerTradeRisk;
  runtime_drawdown: RuntimeDrawdown;
}
export interface RiskCheck {
  code: Code1;
  passed: Passed;
}
export interface RiskDecision {
  approved: Approved1;
  checks: Checks;
  decision_id: DecisionId;
  expires_at: ExpiresAt2;
  intent_id: IntentId2;
  policy_version: PolicyVersion3;
  quantity: Quantity1;
  reason_codes: ReasonCodes1;
  risk_amount: Money | null;
  schema_version: SchemaVersion28;
}
export interface Citation {
  citation_id: CitationId;
  evidence_id: EvidenceId1;
  locator: Locator;
}
export interface DurationHorizon {
  count: Count1;
  kind: Kind9;
  unit: Unit;
}
export interface EventHorizon {
  expected_at: ExpectedAt;
  kind: Kind10;
  name: Name;
  window?: DurationHorizon | null;
}
export interface EvidenceItem {
  artifact_id: ArtifactId;
  available_at: AvailableAt6;
  content_hash: ContentHash;
  evidence_id: EvidenceId2;
  first_seen_at: FirstSeenAt;
  license_tag: LicenseTag;
  original_firm: OriginalFirm;
  published_at: PublishedAt;
  publisher: Publisher;
  schema_version: SchemaVersion29;
  url: Url;
}
export interface Fact {
  citation_ids: CitationIds;
  fact_id: FactId;
  text: Text;
}
export interface Inference {
  assumptions: Assumptions;
  citation_ids: CitationIds1;
  counterevidence: Counterevidence;
  fact_ids: FactIds;
  inference_id: InferenceId;
  text: Text1;
}
export interface MissingData {
  affected_conclusions: AffectedConclusions;
  code: Code2;
  description: Description;
}
export interface ResearchReport {
  as_of: AsOf3;
  citations: Citations;
  completeness: Completeness;
  evidence: Evidence2;
  facts: Facts;
  generated_at: GeneratedAt;
  horizon: Horizon;
  inferences: Inferences;
  missing_data: MissingData1;
  model_version: ModelVersion;
  prompt_version: PromptVersion;
  report_id: ReportId;
  request_id: RequestId;
  schema_version: SchemaVersion30;
  snapshot_id: SnapshotId1;
  summary: ResearchSummary;
  usage: ResearchUsage;
}
export interface UnspecifiedHorizon {
  kind: Kind11;
  reason: Reason2;
}
export interface ResearchSummary {
  conditions: Conditions;
  disposition: Disposition;
  invalidation: Invalidation1;
  why_now: WhyNow;
}
export interface ResearchUsage {
  cost: Money | null;
  cost_state: CostState;
  input_tokens: InputTokens;
  output_tokens: OutputTokens;
}
export interface ResearchRequest {
  actor_id: ActorId1;
  as_of: AsOf4;
  budget_id: BudgetId1;
  capability_scope: CapabilityScope;
  deadline: Deadline;
  horizon: Horizon1;
  instruments: Instruments;
  question: Question;
  request_id: RequestId1;
  schema_version: SchemaVersion31;
  snapshot_id: SnapshotId2;
}
export interface Demand {
  demand_id: DemandId;
  expires_at: ExpiresAt3;
  key: SubscriptionKey;
  owner: Owner1;
  priority: Priority;
  schema_version: SchemaVersion32;
}
export interface FeedCapabilities {
  asset_classes: AssetClasses;
  checked_at: CheckedAt1;
  history_limits: HistoryLimits;
  latency_label: LatencyLabel;
  max_subscriptions: MaxSubscriptions;
  permission_errors: PermissionErrors;
  schema_version: SchemaVersion33;
  sequence_rules?: SequenceRules;
  sessions: Sessions;
  source: Source8;
}
export interface HistoryLimit {
  channel: Channel1;
  max_records: MaxRecords;
  timeframe: Timeframe | null;
}
/**
 * Omitted channels are opaque. Contiguous numbers must not reset mid-epoch.
 */
export interface SequenceRule {
  channel: Channel2;
  semantics: Semantics;
  timeframe: Timeframe | null;
}
export interface SubscriptionPlan {
  accepted: Accepted;
  as_of: AsOf5;
  rejected: Rejected;
  schema_version: SchemaVersion34;
  source: Source9;
}
export interface SubscriptionRejection {
  key: SubscriptionKey;
  reason_codes: ReasonCodes2;
}
export interface AccountSnapshot {
  as_of: AsOf6;
  buying_power: Money;
  equity: Money;
  schema_version: SchemaVersion35;
  snapshot_id: SnapshotId3;
}
export interface BrokerSnapshot {
  account: AccountSnapshot;
  as_of: AsOf7;
  complete: Complete2;
  open_orders: OpenOrders;
  positions: Positions;
  recent_fills: RecentFills;
  schema_version: SchemaVersion36;
  snapshot_id: SnapshotId4;
}
export interface Position {
  instrument_id: InstrumentId10;
  quantity: Quantity2;
}
export interface CandidateObservation {
  action: Action;
  evidence: Evidence3;
  expires_at: ExpiresAt4;
  horizon: Horizon2;
  instrument: Instrument4;
  observation_id: ObservationId;
  observed_at: ObservedAt;
  reason: Reason3;
  schema_version: SchemaVersion37;
}
export interface ExperimentResult {
  equity: Equity;
  events: Events1;
  experiment_id: ExperimentId;
  fees: Money;
  fills: Fills;
  schema_version: SchemaVersion38;
  warnings: Warnings;
}
export interface ExperimentSpec {
  dataset_manifest: DatasetManifest;
  end: End5;
  execution_assumptions: ExecutionAssumptions;
  experiment_id: ExperimentId1;
  schema_version: SchemaVersion39;
  session_policy: SessionPolicy;
  start: Start5;
  strategy_version: StrategyVersion1;
}
export interface HarnessProposal {
  approval: Approval;
  artifact_hash: ArtifactHash;
  base_version: BaseVersion;
  deploy_version: DeployVersion;
  diff: Diff;
  experiment_ids: ExperimentIds;
  metrics: Metrics;
  proposal_id: ProposalId;
  rollback_version: RollbackVersion;
  schema_version: SchemaVersion40;
}
export interface Metrics {
  [k: string]: string;
}
export interface HealthReport {
  component: Component;
  dependency_health: DependencyHealth;
  heartbeat_at: HeartbeatAt1;
  lag_ms: LagMs;
  last_error_code: LastErrorCode;
  schema_version: SchemaVersion41;
  state: State;
}
export interface DependencyHealth {
  [k: string]: 'healthy' | 'degraded' | 'unavailable' | 'unknown';
}
export interface ModelMessage {
  content: Content;
  role: Role1;
}
export interface ModelRequest {
  deadline: Deadline1;
  evidence_refs: EvidenceRefs;
  messages: Messages;
  model: Model;
  output_schema: OutputSchema;
  request_id: RequestId2;
  schema_version: SchemaVersion42;
}
export interface OutputSchema {
  [k: string]: JsonValue;
}
export interface ModelResult {
  error: Error;
  model: Model1;
  output: Output;
  request_id: RequestId3;
  schema_version: SchemaVersion43;
  usage: ResearchUsage;
}
export interface OrderSnapshot {
  as_of: AsOf8;
  command: OrderCommand;
  latest_event: OrderEvent;
  schema_version: SchemaVersion44;
}
export interface ReconciliationResult {
  entry_allowed: EntryAllowed;
  matched: Matched;
  mismatches: Mismatches;
  schema_version: SchemaVersion45;
}
export interface RiskContext {
  account: AccountSnapshot;
  borrow_available: BorrowAvailable;
  pending_orders: PendingOrders;
  policy_version: PolicyVersion4;
  quotes: Quotes1;
  reserved_risk: Money;
  schema_version: SchemaVersion46;
  session: Session2;
  snapshot_id: SnapshotId5;
}
export interface StrategyContext {
  account_snapshot_id: AccountSnapshotId;
  as_of: AsOf9;
  features: Features;
  finalized_bars: FinalizedBars;
  policy_version: PolicyVersion5;
  schema_version: SchemaVersion47;
  strategy_version: StrategyVersion2;
}
export interface Features {
  [k: string]: string;
}
export interface SubmitResult {
  broker_id: BrokerId1;
  client_order_id: ClientOrderId2;
  reason: Reason4;
  schema_version: SchemaVersion48;
  status: Status2;
}
/**
 * Index of a tape series. `complete=false` means the series is not readable.
 */
export interface TapeManifest {
  complete: Complete3;
  partitions: Partitions;
  precision_policy?: PrecisionPolicy;
  schema_version: SchemaVersion49;
  series: TapeSeries;
  written_at: WrittenAt;
}
/**
 * One stored file; the checksum binds a dataset to exact stored bytes.
 */
export interface TapePartition {
  max_event_at: MaxEventAt;
  min_event_at: MinEventAt;
  path: Path;
  rows: Rows;
  sha256: Sha256;
}
/**
 * Identity and retention of one stored series; not a data payload.
 */
export interface TapeSeries {
  adjustment: Adjustment;
  asset_class: AssetClass;
  complete: Complete4;
  coverage_end: CoverageEnd1;
  coverage_start: CoverageStart1;
  retention: Retention;
  row_count: RowCount;
  schema_version: SchemaVersion50;
  series_id: SeriesId;
  source: Source10;
  symbol: Symbol;
  timeframe: Timeframe;
  venue_coverage: VenueCoverage;
}
/**
 * Rows read back, plus what the reader must be told about their limits.
 *
 * `rows_outside_retention` counts stored rows that fall outside the
 * retention window. It is reported rather than silently dropped, so a
 * caller never mistakes a clipped read for complete history.
 */
export interface TapeReadResult {
  max_event_at: MaxEventAt1;
  min_event_at: MinEventAt1;
  rows: Rows1;
  rows_outside_retention?: RowsOutsideRetention;
  series: TapeSeries;
}
/**
 * What a write produced; the manifest is the durable record.
 */
export interface TapeWriteResult {
  dropped_outside_retention: DroppedOutsideRetention;
  partitions: Partitions1;
  series: TapeSeries;
}
export interface MarketRequest {
  keys: Keys;
  version: Version8;
}
export interface MarketStreamRequest {
  cursor?: Cursor3;
  epoch?: Epoch5;
  keys: Keys1;
  version: Version9;
}
