import { useQuery } from "@tanstack/react-query";
import { getJob, getJobs, ApiError } from "./client";
import { config } from "../config";

const retry = (count: number, error: Error) =>
  !(error instanceof ApiError && error.status < 500) && count < 2;
export const isRunning = (status?: string) =>
  Boolean(status && !["done", "failed"].includes(status));
export function useJob(id?: string) {
  return useQuery({
    queryKey: ["job", id],
    queryFn: ({ signal }) => getJob(id!, signal),
    enabled: Boolean(id),
    refetchInterval: (query) =>
      isRunning(query.state.data?.status)
        ? config.pollingMs
        : query.state.data?.status === "done"
          ? config.heatmapRefreshMs
          : false,
    refetchOnWindowFocus: true,
    retry,
  });
}
export function useJobs() {
  return useQuery({
    queryKey: ["jobs"],
    queryFn: ({ signal }) => getJobs(signal),
    refetchInterval: (query) =>
      query.state.data?.jobs.some((job) => isRunning(job.status))
        ? config.pollingMs
        : false,
    retry,
  });
}
