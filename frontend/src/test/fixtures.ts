/** Contract-shaped fixtures (typed against the generated OpenAPI types). */
import type {
  AuditEntry,
  ConfigOut,
  DocumentInfo,
  EvalRunDetail,
  IndexVersion,
  Page,
  QAResponse,
  QueryDetail,
  QuerySummary,
  RebuildStatus,
  ReviewQueueItem,
  Stats,
  TokenResponse,
  User,
  VersionInfo,
} from '@/api/types';

export const NOW = '2026-11-14T08:00:00Z';

export function user(role: User['role']): User {
  return {
    id: `00000000-0000-0000-0000-00000000000${String(['user', 'reviewer', 'admin'].indexOf(role))}`,
    email: `${role}@example.org`,
    display_name: { user: 'User', reviewer: 'Reviewer', admin: 'Admin' }[role],
    role,
    is_active: true,
    created_at: NOW,
    last_login_at: NOW,
  };
}

export function tokens(role: User['role']): TokenResponse {
  return {
    access_token: `token-${role}`,
    token_type: 'bearer',
    expires_in: 900,
    refresh_token: `refresh-${role}`,
    refresh_expires_at: NOW,
    user: user(role),
  };
}

export const SNIPPET =
  'Perform hand hygiene with alcohol-based handrub for 20–30 seconds, covering all surfaces of the hands until dry.';

export const qaValidated: QAResponse = {
  answer: 'Hand hygiene with alcohol-based handrub should take 20–30 seconds [1].',
  citations: [
    {
      id: 1,
      doc_id: 'who-hh-001',
      title: 'Hand Hygiene in Health Care',
      source_org: 'WHO',
      section_path: 'Technique › Handrub',
      chunk_id: 'who-hh-001::technique::0001',
      snippet: SNIPPET,
      score: 0.82,
      superseded: false,
    },
    {
      id: 2,
      doc_id: 'cdc-hh-002',
      title: 'Handrub Guidance (2019)',
      source_org: 'CDC',
      section_path: 'Duration',
      chunk_id: 'cdc-hh-002::duration::0001',
      snippet: 'Rub hands for at least 15 seconds.',
      score: 0.61,
      superseded: true,
    },
  ],
  confidence: 0.81,
  status: 'validated',
  meta: {
    request_id: 'req-validated-0001',
    index_version: '6ce73ffaf982', // pragma: allowlist secret (fake hash)
    latency_ms: 9.4,
    abstained: false,
    reason: null,
    signals: { coverage: 1, query_support: 0.78, retrieval_score: 0.64, numeric_ok: true },
  },
};

export const qaAbstained: QAResponse = {
  answer:
    'The indexed guidelines do not contain sufficient evidence to answer this confidently. Please consult the cited sources or escalate for review.',
  citations: qaValidated.citations.slice(0, 1),
  confidence: 0.32,
  status: 'needs_review',
  meta: {
    request_id: 'req-abstained-0002',
    index_version: '6ce73ffaf982', // pragma: allowlist secret (fake hash)
    latency_ms: 7.1,
    abstained: true,
    reason: 'low_confidence',
    signals: { coverage: 1, query_support: 0.2, retrieval_score: 0.3, numeric_ok: true },
  },
};

export const stats: Stats = {
  since: '2026-11-07T08:00:00Z',
  until: NOW,
  total: 62,
  validated: 45,
  needs_review: 17,
  pass_rate: 45 / 62,
  abstention_rate: 17 / 62,
  mean_confidence: 0.71,
  latency_p50_ms: 6.2,
  latency_p95_ms: 10.1,
  reasons: { low_confidence: 12, below_retrieval_floor: 5 },
  top_topics: [
    { topic: 'hand-hygiene', count: 9 },
    { topic: 'ppe', count: 7 },
  ],
  series: [
    { day: '2026-11-12', total: 30, validated: 22, needs_review: 8, mean_confidence: 0.7 },
    { day: '2026-11-13', total: 32, validated: 23, needs_review: 9, mean_confidence: 0.72 },
  ],
  confidence_histogram: Array.from({ length: 10 }, (_, i) => ({
    lower: i / 10,
    upper: (i + 1) / 10,
    count: i >= 6 ? 9 : 2,
  })).map((b, i) => (i === 0 ? { ...b, count: 2 } : b)),
};

export const querySummary: QuerySummary = {
  id: '11111111-1111-1111-1111-111111111111',
  request_id: 'req-abstained-0002',
  created_at: NOW,
  user_id: null,
  question: 'Patient [ID] had a needlestick, what is the first step?',
  redactions: 1,
  status: 'needs_review',
  reason: 'low_confidence',
  confidence: 0.32,
  top_k: 5,
  latency_ms: 7.1,
  index_version: '6ce73ffaf982', // pragma: allowlist secret (fake hash)
  topics: ['sharps-safety'],
  reviewed: false,
  escalated_at: null,
};

export const queryDetail: QueryDetail = {
  ...querySummary,
  signals: { coverage: 1, query_support: 0.2, retrieval_score: 0.3, numeric_ok: true },
  citations: qaValidated.citations.map((c) => ({ ...c })),
  answer: qaAbstained.answer,
  candidate_answer: 'Wash the wound with soap and water [1].',
  escalation_note: null,
  review: null,
};

export const reviewPage: Page<ReviewQueueItem> = {
  items: [{ query: querySummary, review: null }],
  total: 1,
  limit: 20,
  offset: 0,
};

export const queryPage: Page<QuerySummary> = {
  items: [
    querySummary,
    {
      ...querySummary,
      id: '22222222-2222-2222-2222-222222222222',
      question: 'How long should handrub take?',
      status: 'validated',
      reason: null,
      confidence: 0.81,
    },
  ],
  total: 2,
  limit: 25,
  offset: 0,
};

const curve = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9].map((t) => ({
  threshold: t,
  pass_rate: Math.max(0, 1.1 - t),
  false_validation_rate: Math.max(0, 0.6 - t),
}));

export const evalRun: EvalRunDetail = {
  id: '33333333-3333-3333-3333-333333333333',
  split: 'dev',
  status: 'succeeded',
  triggered_by: null,
  index_version: '6ce73ffaf982', // pragma: allowlist secret (fake hash)
  created_at: NOW,
  started_at: NOW,
  finished_at: NOW,
  scorecard: { 'p@5': 0.6016, 'hit@5': 0.9918, pass_rate: 0.9262, false_validation_rate: 0 },
  error: null,
  summary: {
    threshold_curve: curve,
    config: { weights: [0.2, 0.6, 0.2] },
    low_confidence: [
      {
        id: 'q-0007',
        why: 'validated within 0.05 of the threshold',
        confidence: 0.62,
        kind: 'direct',
        topic: 'ppe',
        question: 'When should gloves be changed?',
      },
    ],
  },
};

export const indexVersions: Page<IndexVersion> = {
  items: [
    {
      version: '6ce73ffaf982', // pragma: allowlist secret (fake hash)
      path: '/index',
      document_count: 72,
      chunk_count: 346,
      source: 'boot',
      is_active: true,
      created_at: NOW,
      activated_at: NOW,
      corpus_hash: 'a1b2c3d4e5f6a7b8c9d0', // pragma: allowlist secret (fake hash)
      config_hash: 'ffeeddccbbaa99887766', // pragma: allowlist secret (fake hash)
    },
    {
      version: '0123456789ab', // pragma: allowlist secret (fake hash)
      path: '/indexes/0123456789ab', // pragma: allowlist secret (fake hash)
      document_count: 72,
      chunk_count: 351,
      source: 'rebuild',
      is_active: false,
      created_at: NOW,
      activated_at: null,
      corpus_hash: 'a1b2c3d4e5f6a7b8c9d0', // pragma: allowlist secret (fake hash)
      config_hash: '00112233445566778899', // pragma: allowlist secret (fake hash)
    },
  ],
  total: 2,
  limit: 200,
  offset: 0,
};

export const rebuildStatus: RebuildStatus = {
  allowed: true,
  running: false,
  started_at: null,
  finished_at: null,
  last_version: null,
  last_error: null,
};

export const documents: Page<DocumentInfo> = {
  items: [
    {
      doc_id: 'who-hh-001',
      title: 'Hand Hygiene in Health Care',
      source_org: 'WHO',
      version: '2.0',
      effective_date: '2024-01-01',
      status: 'current',
      supersedes: null,
      topics: ['hand-hygiene'],
      path: 'who/who-hh-001.md',
      chunk_count: 6,
      token_count: 820,
    },
  ],
  total: 1,
  limit: 25,
  offset: 0,
};

export const config: ConfigOut = {
  version: 0,
  values: {
    threshold: 0.6,
    retrieval_floor: 0.15,
    weights: { coverage: 0.2, query_support: 0.6, retrieval: 0.2 },
  },
  updated_at: null,
  updated_by: null,
  comment: null,
};

export const audit: Page<AuditEntry> = {
  items: [
    {
      id: 1,
      created_at: NOW,
      actor_id: null,
      actor_email: 'admin@example.org',
      action: 'config.update',
      target_type: 'app_config',
      target_id: '1',
      details: { comment: 'tighten' },
      request_id: 'r1',
      ip: '127.0.0.1',
    },
  ],
  total: 1,
  limit: 50,
  offset: 0,
};

export const version: VersionInfo = {
  build_version: '0.6.0',
  contract_version: '1.3.1',
  index_version: '6ce73ffaf982', // pragma: allowlist secret (fake hash)
  analysis_version: 2,
};
