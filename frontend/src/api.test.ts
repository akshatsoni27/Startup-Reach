import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, auth } from "./api";

afterEach(() => vi.restoreAllMocks());

describe("typed API client", () => {
  it("adds the session bearer token and parses responses", async () => {
    auth.set("session-token");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [], page: 1, page_size: 20, total: 0 }), { status: 200 })));
    await expect(api.companies()).resolves.toMatchObject({ total: 0 });
    expect(fetch).toHaveBeenCalledWith("http://localhost:8000/api/v1/companies?page=1&page_size=20", expect.objectContaining({ headers: expect.any(Headers) }));
    const request = vi.mocked(fetch).mock.calls[0][1] as RequestInit;
    expect((request.headers as Headers).get("Authorization")).toBe("Bearer session-token");
  });

  it("normalizes safe backend errors and clears invalid auth", async () => {
    auth.set("expired");
    vi.stubGlobal("fetch", vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify({ code: "authentication_required", message: "Authentication required." }), { status: 401 }))));
    const result = api.profile();
    await expect(result).rejects.toBeInstanceOf(ApiError);
    await expect(result).rejects.toMatchObject({ status: 401, code: "authentication_required" });
    expect(auth.get()).toBe("");
  });

  it("normalizes network failures to safe ApiError without exposing browser crash", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const result = api.dashboard();
    await expect(result).rejects.toBeInstanceOf(ApiError);
    await expect(result).rejects.toMatchObject({ status: 0, code: "network_error" });
  });

  it("handles database service unavailable error safely", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ code: "service_unavailable", message: "The database operation could not be completed." }), { status: 503 })));
    const result = api.dashboard();
    await expect(result).rejects.toBeInstanceOf(ApiError);
    await expect(result).rejects.toMatchObject({ status: 503, code: "service_unavailable", message: "The database operation could not be completed." });
  });
});
