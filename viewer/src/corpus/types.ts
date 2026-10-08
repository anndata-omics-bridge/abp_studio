/** Browser contracts for the persisted corpus records and APB representation v4. */
export type StorageFormat = 'hdf5' | 'duckdb' | 'parquet'
export type Status = 'pending' | 'running' | 'succeeded' | 'failed' | 'skipped' | 'interrupted'
export type InputKind = 'file' | 'folder'
export interface CsvRow { [field: string]: string }
export type CsvRows = CsvRow[] & { columns?: string[] }
export interface CorpusRow extends CsvRow {
  input_file: string
  vendor_parameter_file: string
  module: string
  software_name: string
}
export interface Artifact {
  role: string
  path: string
  format?: StorageFormat | null
  size_bytes?: number | null
}
export interface StepReport {
  name: string
  command?: string[]
  inputs?: Artifact[]
  outputs?: Artifact[]
  status: Status
  runtime_seconds?: number | null
  peak_memory_bytes?: number | null
}
export interface DatasetReport {
  schema_version?: 2
  run_id?: string
  workflow?: string
  format?: StorageFormat
  status: Status
  runtime_seconds?: number | null
  steps: StepReport[]
}
export interface ReportLink {
  input_file: string
  dataset: string
  path: string
  progress: string
  output_dir: string
}
export interface RunManifest {
  schema_version: 2
  run_id: string
  created_at: string
  corpus_name: string
  workflow: string
  format: StorageFormat
  data_root: string
  tools?: Record<string, string>
  tool_versions?: Record<string, string>
  cores: number
  corpus: string
  source_corpus: string
  input_metadata?: string | null
  workflow_table?: string | null
  workflow_source: string
  execution_settings: string
  reports: ReportLink[]
}
export interface Catalog { schema_version: 2; store_root?: string; runs?: string[]; output_extensions?: Record<string, string[]> }
export interface Operation { updated_at?: string; status?: string }
export interface CatalogRun { path: string; manifest: RunManifest; outputExtensions?: string[] }
export interface RunChoice extends CatalogRun { label: string }
export interface DatasetRow extends ReportLink {
  [field: string]: unknown
  module: string
  software_name: string
  vendor_parameter_file?: string
  input_file_name: string
  input_file_parent: string
  input_file_size_bytes?: string | number
  input_file_kind: InputKind | null
  output_file: string
  output_file_name: string
  output_file_parent: string
  output_file_size_bytes: number | null
  output_file_format: StorageFormat | null
  ion_variables: number | null
  status: Status
  runtime_seconds: number | null
  peak_memory_bytes: number | null
  record?: DatasetReport | null
  oddities?: DatasetOddities | null
  oddity_count?: number | null
  oddity_state?: string
}
export type MetricStatus = 'ok' | 'attention' | 'not_checked'
/** One producer summary entry, as recorded in the displayed sidecar. */
export interface OddityMetric {
  scope: string
  record: string
  name: string
  label: string
  value: string | number | boolean | null
  unit: string
  status: MetricStatus
  layer: string
}
export interface DatasetOddities {
  input_file: string
  software_name: string
  module: string
  status: string
  source_step: string
  source_path: string
  source_status: string
  available: boolean
  metrics: OddityMetric[]
  notes: string[]
}
export interface AffectedDatasets { record: string; name: string; label: string; datasets: number }
export interface RunOddities {
  format: 'apb-studio-oddities'
  format_version: 2
  run_id: string
  datasets: DatasetOddities[]
  software: {
    software_name: string
    dataset_count: number
    summarized_count: number
    attention_count: number
    affected: AffectedDatasets[]
  }[]
}
export interface DirectedArtifact extends Artifact { direction: 'Input' | 'Output'; step: string }
export interface StepArtifact extends Artifact { step: string }
export interface ToolTimings {
  format: 'apb-tool-timings'
  format_version: 1
  tool: string
  operation: string
  phases: { name: string; seconds: number }[]
}
export type ToolTimingDocument = ToolTimings
export interface DatasetPoint {
  input_file: string
  module: string
  software_name: string
  input_size_mib: number | null
  ion_variables: number | null
}
export interface ChartPoint extends DatasetPoint {
  step: string
  tool: string
  status: Status
  runtime_seconds?: number | null
  peak_memory_mib?: number | null
  output_role?: string
  output_path?: string
  output_size_mib?: number
}
export interface TimingPoint extends ChartPoint {
  timing_key: string
  timing_label: string
  timing_path: string
  phase: string
  duration_seconds: number
}
export interface TimingView { key: string; label: string; points: TimingPoint[] }
export interface ChartView {
  key: string
  label: string
  steps: ChartPoint[]
  outputs: ChartPoint[]
  timingViews?: TimingView[]
}
export type XAxis = 'input_size_mib' | 'ion_variables'
export interface Dimensions { observations: number; variables: number }
export interface TableColumn { name: string; dtype: string; null_count?: number }
export interface TableDescription { row_count: number; key_columns: string[]; columns: TableColumn[] }
export interface NamedTable extends TableDescription { name: string; metadata?: Record<string, unknown> }
export interface Statistics {
  [field: string]: number | string | null | undefined
  total_count?: number
  finite_count?: number
  null_count?: number
  nan_count?: number
  positive_infinity_count?: number
  negative_infinity_count?: number
  zero_count?: number
  mean?: number | null
  median?: number | null
  first_quartile?: number | null
  third_quartile?: number | null
  minimum?: number | null
  maximum?: number | null
}
export interface Layer {
  name: string
  role: string
  primary?: boolean
  storage_slot?: 'X' | 'layers'
  shape: Dimensions
  value_kind: string
  type?: string
  dtype?: string
  unit?: string | number | boolean | null
  scale?: string | number | boolean | null
  statistics?: Statistics
  category_count?: number
  counts?: Record<string, number>
  observation_summaries?: {
    total_count: number
    emitted_count: number
    truncated: boolean
    items: { observation_index: number; statistics: Statistics }[]
  }
}
export type AlignedSlot = 'obsm' | 'varm' | 'obsp' | 'varp'
export type AlignedTables = Partial<Record<AlignedSlot, NamedTable[]>>
export interface FastaSource { path?: string; checksum?: string }
export interface PeptideVerification {
  feature_count?: number
  matched_feature_count?: number
  unmatched_feature_count?: number
  il_only_matched_feature_count?: number
}
export interface FastaVerificationProvenance {
  sources?: Record<string, FastaSource>
}
export interface FastaCheck extends PeptideVerification, FastaVerificationProvenance {
  level: string
}
export interface ApbMetadata extends Record<string, unknown> {
  hierarchy?: { identities?: [string, string][] }
  fasta?: {
    provenance?: { peptide_verification?: FastaVerificationProvenance }
    result?: { peptide_verification?: PeptideVerification }
  }
}
export interface Level {
  name: string
  dimensions: Dimensions
  primary_layer?: string
  obs: TableDescription
  var: TableDescription
  layers: Layer[]
  aligned?: AlignedTables
  apb?: ApbMetadata
  observations?: {
    total_count: number
    emitted_count: number
    truncated: boolean
    items: { index: number; label: string; key?: Record<string, unknown> }[]
  }
}
export interface FeatureRelation {
  name: string
  annotation_table: string
  target_level: string
  coordinates: TableDescription
  metadata?: Record<string, unknown>
}
export interface Representation {
  format: 'apb2-result-representation'
  format_version: '5'
  artifact: { name: string; physical_format: string; size_bytes?: number } | null
  root?: { apb?: ApbMetadata } | null
  levels: Level[]
  annotation_tables?: NamedTable[]
  feature_relations?: FeatureRelation[]
}
export interface LoadedRepresentation { artifact: StepArtifact; representation: Representation | null }
export type RepresentationView =
  | { key: string; kind: 'apb-metadata' | 'representation-json' | 'anndata-structure'; label: string; representation: Representation }
  | { key: string; kind: 'level'; label: string; representation: Representation; level: Level }
  | { key: string; kind: 'annotation'; label: string; representation: Representation; annotationTable: NamedTable; referenceLevel?: Level }
export interface AnnDataDiagram {
  name: string
  dimensions: Dimensions
  x: Layer | null
  layers: Layer[]
  obs: TableDescription
  var: TableDescription
  aligned: Record<AlignedSlot, NamedTable[]>
  uns: ApbMetadata
}
export interface AnnDataStructure {
  kind: 'anndata'
  label: string
  objectPath: string
  /** Where this AnnData keeps its level part: ``uns["apb"]``, or ``uns["ion"]["apb"]`` in H5AD. */
  unsKey: string
  /** A standalone H5AD's root part, kept apart in ``uns["apb"]``. */
  rootUns?: ApbMetadata
  diagram: AnnDataDiagram
  hasStorage: boolean
  annotation: boolean
}
export interface MuDataStructure {
  kind: 'mudata'
  label: string
  objectPath: string
  uns: ApbMetadata
  hasStorage: boolean
  modalities: { name: string; objectPath: string; dimensions: Dimensions }[]
  relations: FeatureRelation[]
}
export type StructureView = AnnDataStructure | MuDataStructure
