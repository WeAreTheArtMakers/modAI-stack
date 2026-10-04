import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { RetrievalProfileCatalog } from "../types";
import { SystemPage } from "./SystemPage";

vi.mock("../api/health", () => ({ getReadiness: vi.fn() }));
vi.mock("../api/models", () => ({ getModelStatus: vi.fn() }));
vi.mock("../api/retrieval", () => ({ getRetrievalProfiles: vi.fn() }));

const profiles: RetrievalProfileCatalog = {
  active_profile_id: "english-optimized",
  profile_switching_enabled: false,
  profiles: [
    {
      profile_id: "compact-multilingual",
      display_name: "Compact Multilingual",
      description: "Düşük kaynaklı çok dilli hedef; model doğrulaması bekliyor.",
      language_capabilities: ["Türkçe + English + multilingual hedefi; ölçüm bekliyor"],
      hardware_class: "Düşük kaynak / hızlı",
      availability: "experimental",
      active: false,
      selectable: false,
    },
    {
      profile_id: "balanced-multilingual",
      display_name: "Balanced Multilingual",
      description: "Dengeli kaynak hedefi; model sağlama bekliyor.",
      language_capabilities: ["Çok dilli hedef; ölçüm bekliyor"],
      hardware_class: "Orta kaynak",
      availability: "available_after_provisioning",
      active: false,
      selectable: false,
    },
    {
      profile_id: "advanced-long-document",
      display_name: "Advanced Long-Document",
      description: "Uzun belge hedefi; yapılandırılmadı.",
      language_capabilities: ["Çok dilli hedef; ölçüm bekliyor"],
      hardware_class: "Yüksek kaynak",
      availability: "not_configured",
      active: false,
      selectable: false,
    },
    {
      profile_id: "english-optimized",
      display_name: "English Optimized",
      description: "Mevcut hafif İngilizce odaklı baseline; Türkçe ölçülmedi.",
      language_capabilities: ["English-focused", "Türkçe performansı benchmark edilmedi"],
      hardware_class: "Düşük kaynak",
      availability: "active",
      active: true,
      selectable: false,
    },
  ],
};

describe("SystemPage retrieval profile catalog", () => {
  it("shows human-readable statuses and keeps profile switching disabled", async () => {
    const healthApi = await import("../api/health");
    const modelsApi = await import("../api/models");
    const retrievalApi = await import("../api/retrieval");
    vi.mocked(healthApi.getReadiness).mockResolvedValue({ status: "ready", ready: true, dependencies: { postgres: true, redis: true, qdrant: true }, ollama: { ready: true }, embedding: { ready: true } });
    vi.mocked(modelsApi.getModelStatus).mockResolvedValue({
      providers: [{ provider: "ollama", endpoint: "http://localhost:11434", ready: true }],
      generation: { provider: "ollama", configured_model: "modAIJet:latest", ready: true, running: true },
      embedding: {
        configured_model: "sentence-transformers/all-MiniLM-L6-v2",
        source: "huggingface_cache",
        download_allowed: false,
        cache_available: true,
        ready: true,
        status: "ready",
      },
    });
    vi.mocked(retrievalApi.getRetrievalProfiles).mockResolvedValue(profiles);

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={queryClient}><SystemPage /></QueryClientProvider>);

    expect(await screen.findByRole("heading", { name: "Etkin arama profili" })).toBeInTheDocument();
    expect(screen.getAllByText("English Optimized").length).toBeGreaterThan(0);
    expect(screen.getByText("Compact Multilingual")).toBeInTheDocument();
    expect(screen.getByText("Deneysel")).toBeInTheDocument();
    expect(screen.getAllByText("Türkçe performansı benchmark edilmedi").length).toBeGreaterThan(0);
    expect(screen.getByText("Profil değiştirme kapalı")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /uygula|apply/i })).not.toBeInTheDocument();
    expect(healthApi.getReadiness).toHaveBeenCalled();
    for (const name of ["PostgreSQL", "Redis", "Qdrant"]) {
      expect(screen.getByText(name).closest(".panel")?.textContent).toContain("Hazır");
    }
    expect(screen.queryByText("API sinyali yok")).not.toBeInTheDocument();
    expect(document.body.textContent).not.toContain("all-MiniLM-L6-v2");
  });

  it("shows a failed dependency from /ready as unavailable, not unknown", async () => {
    const healthApi = await import("../api/health");
    const modelsApi = await import("../api/models");
    const retrievalApi = await import("../api/retrieval");
    vi.mocked(healthApi.getReadiness).mockResolvedValue({ status: "not_ready", ready: false, dependencies: { postgres: true, redis: false, qdrant: true }, ollama: { ready: true }, embedding: { ready: true } });
    vi.mocked(modelsApi.getModelStatus).mockRejectedValue(new Error("unavailable"));
    vi.mocked(retrievalApi.getRetrievalProfiles).mockResolvedValue(profiles);
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={queryClient}><SystemPage /></QueryClientProvider>);
    expect(await screen.findByText("Redis")).toBeInTheDocument();
    expect(screen.getByText("Redis").closest(".panel")?.textContent).toContain("Ulaşılamıyor");
    expect(screen.getByText("PostgreSQL").closest(".panel")?.textContent).toContain("Hazır");
  });
});
