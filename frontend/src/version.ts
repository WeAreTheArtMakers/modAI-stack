export const FRONTEND_BUILD_SHA = import.meta.env.VITE_BUILD_SHA ?? "development";

const RELEASE_SHA_PATTERN = /^[0-9a-f]{40}$/i;

export function isReleaseSha(value: unknown): value is string {
  return typeof value === "string" && RELEASE_SHA_PATTERN.test(value);
}

export function shortSha(value: string): string {
  return isReleaseSha(value) ? value.slice(0, 12).toLowerCase() : "Development build";
}

export function versionsMismatch(frontendSha: unknown, backendSha: unknown): boolean {
  return isReleaseSha(frontendSha)
    && isReleaseSha(backendSha)
    && frontendSha.toLowerCase() !== backendSha.toLowerCase();
}
