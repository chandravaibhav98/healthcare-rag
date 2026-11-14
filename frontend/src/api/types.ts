/** Friendly aliases for the generated OpenAPI types (contract 1.3, ADR-0006). */
import type { components } from './generated/schema';

type Schemas = components['schemas'];

export type QAResponse = Schemas['QAResponse'];
export type QARequest = Schemas['QARequest'];
export type Citation = Schemas['Citation'];
export type Signals = Schemas['Signals'];
export type ResponseMeta = Schemas['ResponseMeta'];
export type AbstentionReason = Schemas['AbstentionReason'];
export type User = Schemas['UserOut'];
export type TokenResponse = Schemas['TokenResponse'];
export type Role = User['role'];
export type Stats = Schemas['StatsOut'];
export type QuerySummary = Schemas['QuerySummary'];
export type QueryDetail = Schemas['QueryDetail'];
export type ReviewIn = Schemas['ReviewIn'];
export type ReviewOut = Schemas['ReviewOut'];
export type ReviewQueueItem = Schemas['ReviewQueueItem'];
export type EvalRun = Schemas['EvalRunOut'];
export type EvalRunDetail = Schemas['EvalRunDetail'];
export type IndexVersion = Schemas['IndexVersionOut'];
export type RebuildStatus = Schemas['RebuildStatus'];
export type DocumentInfo = Schemas['DocumentOut'];
export type ConfigOut = Schemas['ConfigOut'];
export type ConfigValues = Schemas['ConfigValues'];
export type ConfigUpdate = Schemas['ConfigUpdate'];
export type AuditEntry = Schemas['AuditOut'];
export type VersionInfo = Schemas['VersionInfo'];
export type ProblemDetails = Schemas['ProblemDetails'];

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}
