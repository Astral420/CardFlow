import axios, { type AxiosError, type InternalAxiosRequestConfig } from "axios";
import type {
  Batch,
  BatchDetail,
  BatchDuplicatePair,
  CardCrop,
  CardCropDetail,
  CreateUserPayload,
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
  baseURL: import.meta.env.VITE_API_BASE_URL ?? "/api",
  withCredentials: true,
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

// ---- Session recovery / forced logout ----
//
// A 401 here always means "this session is no longer valid" -- every
// endpoint that can 401 requires auth, and the UI only ever calls those
// when canEdit/isAdmin is true, so there's no legitimate "you're an
// unauthenticated Guest" 401 to distinguish from a real one.
//
// On a 401, try exactly one silent refresh (via the httpOnly cookie) and
// retry the original request with the new access token. If the refresh
// itself fails -- expired refresh token, or an Admin revoked this
// account's sessions -- fall through to a hard client-side logout and
// redirect, which is what actually fixes the "deleted user stays logged
// in until manual refresh" bug: the very next request this tab makes
// (the sidebar/dashboard polling queries fire every 15s) now forces the
// user out on its own.

let refreshInFlight: Promise<string | null> | null = null;

function refreshOnce(): Promise<string | null> {
  if (!refreshInFlight) {
    refreshInFlight = refreshAccessToken()
      .then(({ access_token }) => {
        setToken(access_token);
        return access_token;
      })
      .catch(() => {
        setToken(null);
        return null;
      })
      .finally(() => {
        refreshInFlight = null;
      });
  }
  return refreshInFlight;
}

// Module-level slot for the auth context to register a handler that
// clears user state the instant a session revocation is detected.
// This lets the UI degrade to Guest mode (canEdit/isAdmin = false)
// synchronously, before the /login redirect fires -- so deleted users
// can't see or interact with editor controls during the redirect.
let _onSessionRevoked: (() => void) | null = null;

export function setSessionRevokedHandler(cb: () => void) {
  _onSessionRevoked = cb;
}

function forceLogoutRedirect() {
  setToken(null);
  _onSessionRevoked?.();
  if (window.location.pathname !== "/login") {
    window.location.assign("/login");
  }
}

type RetriableConfig = InternalAxiosRequestConfig & { _retried?: boolean };

client.interceptors.response.use(
  (response) => response,
  async (error: unknown) => {
    if (!axios.isAxiosError(error) || error.response?.status !== 401 || !error.config) {
      return Promise.reject(error);
    }

    const original = error.config as RetriableConfig;
    const url = original.url ?? "";
    const isAuthEndpoint =
      url.includes("/auth/login") || url.includes("/auth/refresh") || url.includes("/auth/logout");

    if (isAuthEndpoint || original._retried) {
      // A failed login attempt (wrong password) is a normal form error,
      // not a session ending -- don't bounce someone off the login page
      // for typing the wrong password. Everything else (a failed
      // refresh, or a retried request that still 401s) means the
      // session is genuinely gone.
      //
      // Guard on getToken(): a Guest probing /auth/me has no access
      // token and no refresh cookie. Their /auth/refresh call 401s here
      // too, but they were never "logged in" -- only redirect when there
      // was actually a token to lose.
      if (!url.includes("/auth/login") && getToken()) {
        forceLogoutRedirect();
      }
      return Promise.reject(error);
    }

    original._retried = true;
    const newToken = await refreshOnce();
    if (!newToken) {
      // refreshOnce().catch already called setToken(null) before we
      // reach here, so this guard is belt-and-suspenders -- but
      // consistent with the intent above.
      if (getToken()) {
        forceLogoutRedirect();
      }
      return Promise.reject(error);
    }

    original.headers.Authorization = `Bearer ${newToken}`;
    return client(original);
  }
);

// ---- Auth ----

export async function login(name: string, password: string) {
  const { data } = await client.post<{ access_token: string; token_type: string }>(
    "/auth/login",
    { name, password }
  );
  return data;
}

export async function getMe() {
  const { data } = await client.get<User>("/auth/me");
  return data;
}

export async function refreshAccessToken() {
  const { data } = await client.post<{ access_token: string; token_type: string }>(
    "/auth/refresh"
  );
  return data;
}

export async function logout() {
  try {
    await client.post("/auth/logout");
  } catch {
    // Best-effort -- even if this fails (offline, etc.) the local
    // session below still gets cleared, which is what actually matters
    // for this tab.
  } finally {
    setToken(null);
  }
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

export async function deleteBatch(batchId: number): Promise<void> {
  await client.delete(`/batches/${batchId}`);
}

export async function getBatchDuplicates(batchId: number) {
  const { data } = await client.get<BatchDuplicatePair[]>(`/batches/${batchId}/duplicates`);
  return data;
}

export async function exportBatchZip(batchId: number, filename: string) {
  const response = await client.get(`/batches/${batchId}/export`, {
    responseType: "blob",
  });
  const blob = response.data as Blob;
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

export async function getNextRotation(batchId?: number, afterId?: number) {
  const params: Record<string, number> = {};
  if (batchId) params.batch_id = batchId;
  if (afterId) params.after_id = afterId;
  const { data } = await client.get<RotationNext | null>("/review/rotation/next", {
    params: Object.keys(params).length ? params : undefined,
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

// ---- User management (Admin only) ----

export async function listUsers() {
  const { data } = await client.get<User[]>("/users");
  return data;
}

export async function createUser(payload: CreateUserPayload) {
  const { data } = await client.post<User>("/users", payload);
  return data;
}

export async function deleteUser(userId: number) {
  await client.delete(`/users/${userId}`);
}

// ---- Health check ----

export async function checkHealth() {
  const { data } = await client.get<{ status: string }>("/health");
  return data;
}