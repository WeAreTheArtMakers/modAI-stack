import { describe, expect, it } from "vitest";
import { isReleaseSha, shortSha, versionsMismatch } from "./version";

const shaA = "a".repeat(40);
const shaB = "b".repeat(40);

describe("release SHA helpers", () => {
  it("accepts exactly 40 hexadecimal characters and normalizes comparisons", () => {
    expect(isReleaseSha(shaA)).toBe(true);
    expect(isReleaseSha("A".repeat(40))).toBe(true);
    expect(isReleaseSha("a".repeat(39))).toBe(false);
    expect(isReleaseSha("g".repeat(40))).toBe(false);
    expect(shortSha(shaA)).toBe("a".repeat(12));
    expect(versionsMismatch(shaA, "A".repeat(40))).toBe(false);
    expect(versionsMismatch(shaA, shaB)).toBe(true);
  });

  it("does not compare development, empty, or malformed values as releases", () => {
    expect(shortSha("development")).toBe("Development build");
    expect(versionsMismatch(shaA, "development")).toBe(false);
    expect(versionsMismatch("development", shaB)).toBe(false);
    expect(versionsMismatch("", shaB)).toBe(false);
    expect(versionsMismatch(shaA, "not-a-sha")).toBe(false);
  });
});
