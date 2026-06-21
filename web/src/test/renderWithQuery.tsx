/**
 * Helper para tests que renderean componentes que usan useQuery /
 * useMutation. Cada test recibe un QueryClient nuevo (sin staleTime y
 * sin retries) para que las queries se comporten predeciblemente.
 *
 * Uso:
 *   import { renderWithQuery } from "@/test/renderWithQuery";
 *   renderWithQuery(<NotesPanel />);
 *
 * Si necesitás inspeccionar/manipular el cliente desde el test:
 *   const { client } = renderWithQuery(<X />);
 *   client.setQueryData(["notes"], [...]);
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderOptions, type RenderResult } from "@testing-library/react";
import type { ReactElement } from "react";

export function renderWithQuery(
  ui: ReactElement,
  options: RenderOptions = {},
): RenderResult & { client: QueryClient } {
  const client = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        staleTime: 0,
        gcTime: 0,
        refetchOnWindowFocus: false,
      },
      mutations: { retry: false },
    },
  });
  const result = render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>, options);
  return { ...result, client };
}
