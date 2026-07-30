import { useQuery } from "@tanstack/react-query";
import { checkHealth } from "./api";

export function useHealthCheck() {
  const query = useQuery({
    queryKey: ["health"],
    queryFn: checkHealth,
    refetchInterval: 15_000,
    retry: 1,
    refetchOnWindowFocus: true,
  });

  const isOperational = query.isSuccess && query.data?.status === "ok";

  let statusText = "Operational";
  let badgeVariant: "mint" | "rose" | "neutral" = "mint";
  let accent: "mint" | "rose" | "lavender" = "mint";

  if (query.isLoading) {
    statusText = "Checking...";
    badgeVariant = "neutral";
    accent = "lavender";
  } else if (query.isError || !isOperational) {
    statusText = "Offline";
    badgeVariant = "rose";
    accent = "rose";
  }

  return {
    ...query,
    isOperational,
    statusText,
    badgeVariant,
    accent,
  };
}
