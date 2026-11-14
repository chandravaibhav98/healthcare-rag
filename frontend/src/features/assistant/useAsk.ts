import { useMutation } from '@tanstack/react-query';

import { api, ApiError } from '@/api/client';
import type { QAResponse } from '@/api/types';
import { parseQAResponse } from '@/api/validation';

export interface AskInput {
  question: string;
  topK: number;
}

/** POST /api/v1/qa with runtime validation of the response body. */
export function useAsk() {
  return useMutation<QAResponse, Error, AskInput>({
    mutationFn: async ({ question, topK }) => {
      const { data, error, response } = await api.POST('/api/v1/qa', {
        body: { question, top_k: topK },
      });
      if (!response.ok || data === undefined) {
        throw new ApiError(response.status, (error as ApiError['problem']) ?? null);
      }
      return parseQAResponse(data);
    },
  });
}
