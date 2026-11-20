// k6 load test for POST /qa (plan §4 Phase 7).
//
//   k6 run e2e/load/qa.js                         # 50 VUs for 5 minutes against :8000
//   BASE_URL=http://host:8000 VUS=10 DURATION=30s k6 run e2e/load/qa.js
//
// Run it through scripts/load-test.sh|ps1, which also starts a disposable API with load-
// friendly rate limits when no target is given. The production default of 60 requests per
// minute per client would otherwise turn most of this test into 429s.
//
// Gates (thresholds fail the run, so k6 exits non-zero):
//   * p95 latency of /qa below 300 ms
//   * no 5xx responses (`server_errors` rate is exactly 0)
//   * every response is a schema-shaped answer (checks ≥ 99.9 %: answer, citations,
//     confidence, status ∈ {validated, needs_review})
// Questions are the held-out test split, answerable and unanswerable alike, so both the
// validated and the abstention paths are exercised.
import http from 'k6/http';
import { check, sleep } from 'k6';
import { SharedArray } from 'k6/data';
import { Rate } from 'k6/metrics';

const BASE_URL = (__ENV.BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');
const QA_PATH = __ENV.QA_PATH || '/api/v1/qa';
const VUS = Number(__ENV.VUS || 50);
const DURATION = __ENV.DURATION || '5m';
const P95_MS = Number(__ENV.P95_MS || 300);
const THINK_S = Number(__ENV.THINK_S || 1);

const questions = new SharedArray('questions', () =>
  open(__ENV.QUESTIONS || '../../backend/evaluation/datasets/gold_test.jsonl')
    .split('\n')
    .filter((line) => line.trim())
    .map((line) => JSON.parse(line).question),
);

const serverErrors = new Rate('server_errors');

export const options = {
  scenarios: {
    qa: {
      executor: 'constant-vus',
      vus: VUS,
      duration: DURATION,
      gracefulStop: '10s',
    },
  },
  thresholds: {
    'http_req_duration{endpoint:qa}': [`p(95)<${P95_MS}`],
    server_errors: ['rate==0'],
    checks: ['rate>0.999'],
  },
  summaryTrendStats: ['avg', 'min', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
};

export function setup() {
  const ready = http.get(`${BASE_URL}/readyz`);
  if (ready.status !== 200) {
    throw new Error(`${BASE_URL}/readyz returned ${ready.status}; is the API up?`);
  }
  return {};
}

export default function () {
  const question = questions[Math.floor(Math.random() * questions.length)];
  const res = http.post(`${BASE_URL}${QA_PATH}`, JSON.stringify({ question, top_k: 5 }), {
    headers: { 'Content-Type': 'application/json' },
    tags: { endpoint: 'qa' },
  });
  serverErrors.add(res.status >= 500);
  check(res, {
    'status is 200': (r) => r.status === 200,
    'answer contract': (r) => {
      if (r.status !== 200) return false;
      const body = r.json();
      return (
        typeof body.answer === 'string' &&
        Array.isArray(body.citations) &&
        typeof body.confidence === 'number' &&
        (body.status === 'validated' || body.status === 'needs_review')
      );
    },
  });
  sleep(THINK_S * (0.5 + Math.random()));
}
