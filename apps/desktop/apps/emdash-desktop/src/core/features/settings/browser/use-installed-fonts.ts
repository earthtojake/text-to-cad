import { useQuery } from '@tanstack/react-query';
import { getHostClient } from '@core/primitives/desktop-host/browser/host-client';

const dedupeAndSort = (fonts: string[]): string[] =>
  Array.from(new Set(fonts.map((font) => font.trim()).filter(Boolean))).sort((a, b) =>
    a.localeCompare(b)
  );

export function useInstalledFonts() {
  const { data = [], isLoading } = useQuery<string[]>({
    queryKey: ['app', 'installedFonts', 'all'],
    queryFn: async () => {
      try {
        const result = await (await getHostClient()).listInstalledFonts({ refresh: true });
        if (result?.success && Array.isArray(result.fonts)) {
          return dedupeAndSort(result.fonts);
        }
      } catch {
        // Swallow — UI shows just the default option.
      }
      return [];
    },
    staleTime: 0,
    refetchOnMount: 'always',
  });

  return { fonts: data, isLoading };
}
