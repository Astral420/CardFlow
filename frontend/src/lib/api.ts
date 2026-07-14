import axios, { type AxiosError } from "axios";
import type {
  Batch,
  BatchDetail,
  BatchDuplicatePair,
  CardCrop,
  CardCropDetail,
  CropQueueItem,
  DuplicateCandidate,
  QueueCount,
  RawScan,
  RotationNext,
  User,
} from "./types";

const TOKEN_KEY = "card-tool.token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

export const client = axios.create({
  baseURL: "/api",
});

client.interceptors.request.use((config) => {
  const token = getToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export function isUnauthorized(error: unknown): boolean {
  return axios.isAxiosError(error) && error.response?.status === 401;
}

export function apiErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const err = error as AxiosError<{ detail?: string }>;
    return err.response?.data?.detail ?? err.message;
  }
  return "Something went wrong";
}

// ---- Auth ----

export async function login(name: string, passcode: string) {
  const { data } = await client.post<{ access_token: string; token_type: string }>(
    "/auth/login",
    { name, passcode }
  );
  return data;
}

export async function getMe() {
  const { data } = await client.get<User>("/auth/me");
  return data;
}

// ---- Batches ----

export async function listBatches(limit = 50) {
  const { data } = await client.get<Batch[]>("/batches", { params: { limit } });
  return data;
}

export async function getBatch(batchId: number) {
  const { data } = await client.get<BatchDetail>(`/batches/${batchId}`);
  return data;
}

export async function getBatchScans(batchId: number) {
  const { data } = await client.get<RawScan[]>(`/batches/${batchId}/scans`);
  return data;
}

export async function uploadBatch(file: File, sourceLabel?: string) {
  const form = new FormData();
  form.append("file", file);
  if (sourceLabel) form.append("source_label", sourceLabel);
  const { data } = await client.post<{ batch_id: number }>("/batches", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function forceAdvanceBatch(batchId: number) {
  const { data } = await client.post<BatchDetail>(
    `/batches/${batchId}/force-advance`
  );
  return data;
}

export async function getBatchDuplicates(batchId: number) {
  const { data } = await client.get<BatchDuplicatePair[]>(`/batches/${batchId}/duplicates`);
  return data;
}

export async function exportBatchZip(batchId: number, filename: string) {
  const token = getToken();
  const response = await fetch(`/api/batches/${batchId}/export`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!response.ok) {
    throw new Error(`Export failed: ${response.statusText}`);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// ---- Rotation review ----

export async function getNextRotation(batchId?: number) {
  const { data } = await client.get<RotationNext | null>("/review/rotation/next", {
    params: batchId ? { batch_id: batchId } : undefined,
  });
  return data;
}

export async function getRotationQueueCount() {
  const { data } = await client.get<QueueCount>("/review/rotation/queue-count");
  return data;
}

export async function rotateCrop(cropId: number, degrees: number) {
  const { data } = await client.post<CropQueueItem>(
    `/review/rotation/${cropId}/rotate`,
    { degrees }
  );
  return data;
}

export async function confirmCrop(cropId: number) {
  const { data } = await client.post<RotationNext | null>(
    `/review/rotation/${cropId}/confirm`
  );
  return data;
}

// ---- Duplicate review ----

export async function getNextDuplicate() {
  const { data } = await client.get<DuplicateCandidate | null>("/review/duplicates/next");
  return data;
}

export async function getDuplicateQueueCount() {
  const { data } = await client.get<QueueCount>("/review/duplicates/queue-count");
  return data;
}

export async function decideDuplicate(
  candidateId: number,
  status: "confirmed_duplicate" | "rejected"
) {
  const { data } = await client.post<DuplicateCandidate | null>(
    `/review/duplicates/${candidateId}/decision`,
    { status }
  );
  return data;
}

// ---- Card log ----

export interface ListCardsParams {
  batch_id?: number;
  status?: string;
  search?: string;
  limit?: number;
  offset?: number;
}

export async function listCards(params: ListCardsParams) {
  const { data } = await client.get<CardCrop[]>("/cards", { params });
  return data;
}

export async function getCard(cropId: number) {
  const { data } = await client.get<CardCropDetail>(`/cards/${cropId}`);
  return data;
}
