import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getPromptLibraryClient } from '@core/features/library/api/browser/client';
import { type PromptLibraryPrompt } from '@core/primitives/prompt-library/api';

const promptLibraryQueryKey = ['promptLibrary'] as const;

export function usePromptLibrary() {
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: promptLibraryQueryKey,
    queryFn: async () => (await getPromptLibraryClient()).get(),
    staleTime: 5 * 60_000,
  });

  const updateMutation = useMutation<
    void,
    Error,
    PromptLibraryPrompt[],
    { previousPrompts: PromptLibraryPrompt[] | undefined }
  >({
    mutationFn: async (prompts) => (await getPromptLibraryClient()).update({ prompts }),
    onMutate: async (prompts) => {
      await queryClient.cancelQueries({ queryKey: promptLibraryQueryKey });
      const previousPrompts =
        queryClient.getQueryData<PromptLibraryPrompt[]>(promptLibraryQueryKey);
      queryClient.setQueryData(promptLibraryQueryKey, prompts);
      return { previousPrompts };
    },
    onError: (_error, _prompts, context) => {
      queryClient.setQueryData(promptLibraryQueryKey, context?.previousPrompts);
      void queryClient.invalidateQueries({ queryKey: promptLibraryQueryKey });
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: promptLibraryQueryKey });
    },
  });

  return {
    value: data ?? [],
    update: updateMutation.mutate,
    isLoading,
    isSaving: updateMutation.isPending,
  };
}
