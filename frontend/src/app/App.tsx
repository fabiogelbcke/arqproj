import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createBrowserRouter, RouterProvider } from "react-router";

import { routes } from "./routes";

export function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
  });
}

const router = createBrowserRouter(routes, { basename: "/painel" });
const queryClient = makeQueryClient();

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  );
}
