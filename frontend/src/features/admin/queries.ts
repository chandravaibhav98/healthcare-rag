/** TanStack Query hooks for the admin API. Query keys start with 'admin' so a sign-out
 * can drop them all at once. */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api, unwrap } from '@/api/client';
import type { paths } from '@/api/generated/schema';
import type { ConfigUpdate, ReviewIn } from '@/api/types';

type QueryParams<P extends keyof paths> = paths[P] extends {
  get: { parameters: { query?: infer Q } };
}
  ? NonNullable<Q>
  : never;

export type QueriesParams = QueryParams<'/api/v1/admin/queries'>;
export type ReviewsParams = QueryParams<'/api/v1/admin/reviews'>;
export type DocumentsParams = QueryParams<'/api/v1/admin/documents'>;
export type AuditParams = QueryParams<'/api/v1/admin/audit-log'>;

export function useStats(from: string, to: string) {
  return useQuery({
    queryKey: ['admin', 'stats', from, to],
    queryFn: () => unwrap(api.GET('/api/v1/admin/stats', { params: { query: { from, to } } })),
  });
}

export function useQueryList(query: QueriesParams) {
  return useQuery({
    queryKey: ['admin', 'queries', query],
    queryFn: () => unwrap(api.GET('/api/v1/admin/queries', { params: { query } })),
    placeholderData: keepPreviousData,
  });
}

export function useQueryDetail(id: string | null) {
  return useQuery({
    queryKey: ['admin', 'query', id],
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/admin/queries/{query_id}', { params: { path: { query_id: id ?? '' } } }),
      ),
    enabled: id !== null,
  });
}

export function useReviewQueue(query: ReviewsParams) {
  return useQuery({
    queryKey: ['admin', 'reviews', query],
    queryFn: () => unwrap(api.GET('/api/v1/admin/reviews', { params: { query } })),
    placeholderData: keepPreviousData,
  });
}

export function useSubmitReview() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ queryId, body }: { queryId: string; body: ReviewIn }) =>
      unwrap(
        api.POST('/api/v1/admin/reviews/{query_id}', {
          params: { path: { query_id: queryId } },
          body,
        }),
      ),
    onSuccess: () => client.invalidateQueries({ queryKey: ['admin'] }),
  });
}

export function useEvalRuns() {
  return useQuery({
    queryKey: ['admin', 'eval-runs'],
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/admin/eval-runs', { params: { query: { limit: 50, order: 'desc' } } }),
      ),
    // Poll while a run is in flight so the table updates by itself.
    refetchInterval: (query) =>
      query.state.data?.items.some((r) => r.status === 'queued' || r.status === 'running')
        ? 2000
        : false,
  });
}

export function useEvalRun(id: string | null) {
  return useQuery({
    queryKey: ['admin', 'eval-run', id],
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/admin/eval-runs/{run_id}', { params: { path: { run_id: id ?? '' } } }),
      ),
    enabled: id !== null,
  });
}

export function useStartEval() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.POST('/api/v1/admin/eval-runs')),
    onSuccess: () => client.invalidateQueries({ queryKey: ['admin', 'eval-runs'] }),
  });
}

export function useIndexVersions() {
  return useQuery({
    queryKey: ['admin', 'index-versions'],
    queryFn: () =>
      unwrap(api.GET('/api/v1/admin/index/versions', { params: { query: { limit: 200 } } })),
  });
}

export function useActivateVersion() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (version: string) =>
      unwrap(
        api.POST('/api/v1/admin/index/versions/{version}/activate', {
          params: { path: { version } },
        }),
      ),
    onSuccess: () => client.invalidateQueries(),
  });
}

export function useRebuildStatus(enabled: boolean) {
  return useQuery({
    queryKey: ['admin', 'rebuild'],
    queryFn: () => unwrap(api.GET('/api/v1/admin/index/rebuild')),
    enabled,
    refetchInterval: (query) => (query.state.data?.running ? 1500 : false),
  });
}

export function useStartRebuild() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.POST('/api/v1/admin/index/rebuild')),
    onSuccess: () => client.invalidateQueries({ queryKey: ['admin'] }),
  });
}

export function useDocuments(query: DocumentsParams) {
  return useQuery({
    queryKey: ['admin', 'documents', query],
    queryFn: () => unwrap(api.GET('/api/v1/admin/documents', { params: { query } })),
    placeholderData: keepPreviousData,
  });
}

export function useConfig() {
  return useQuery({
    queryKey: ['admin', 'config'],
    queryFn: () => unwrap(api.GET('/api/v1/admin/config')),
  });
}

export function useUpdateConfig() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: ConfigUpdate) => unwrap(api.PUT('/api/v1/admin/config', { body })),
    onSuccess: () => client.invalidateQueries({ queryKey: ['admin'] }),
  });
}

export function useAuditLog(query: AuditParams) {
  return useQuery({
    queryKey: ['admin', 'audit', query],
    queryFn: () => unwrap(api.GET('/api/v1/admin/audit-log', { params: { query } })),
    placeholderData: keepPreviousData,
  });
}
