export interface BackendVersion {
  build_sha: string;
}

export async function getBackendVersion(): Promise<BackendVersion> {
  const response = await fetch("/api/version", { cache: "no-store", credentials: "omit" });
  if (!response.ok) throw new Error("Backend version unavailable");
  const body: unknown = await response.json();
  if (typeof body !== "object" || body === null || !("build_sha" in body) || typeof body.build_sha !== "string") {
    throw new Error("Backend version unavailable");
  }
  return { build_sha: body.build_sha };
}
