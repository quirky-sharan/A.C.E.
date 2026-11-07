import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { requestClient } from "../test/tasks";
import { Skills } from "./skills";

const listed = {
  available: true,
  apps: [
    { name: "Spotify", kind: "aumid", target: "S!a", launch_count: 3 },
    { name: "Visual Studio Code", kind: "exe", target: "VSC", launch_count: 0 },
  ],
};

describe("Skills page: app index", () => {
  it("lists the indexed apps with their kind and launch count", async () => {
    const { client, requests } = requestClient({ "apps.list": listed });
    render(<Skills client={client} />);
    await vi.waitFor(() => expect(screen.getByRole("list", { name: "Apps" })).toBeTruthy());
    const list = screen.getByRole("list", { name: "Apps" }).textContent ?? "";
    for (const text of [
      "Spotify",
      "Store app",
      "opened 3×",
      "Visual Studio Code",
      "never opened",
    ]) {
      expect(list).toContain(text);
    }
    expect(requests[0]).toEqual(["apps.list", { query: null, limit: 500 }]);
  });

  it("searches and refreshes through the core", async () => {
    const { client, requests } = requestClient({
      "apps.list": listed,
      "apps.refresh": { count: 2 },
    });
    render(<Skills client={client} />);
    await vi.waitFor(() => expect(requests).toHaveLength(1));
    fireEvent.change(screen.getByRole("searchbox", { name: "Search apps" }), {
      target: { value: " spot " },
    });
    await vi.waitFor(() =>
      expect(requests.at(-1)).toEqual(["apps.list", { query: "spot", limit: 500 }]),
    );
    fireEvent.click(screen.getByRole("button", { name: "Refresh from Start" }));
    await vi.waitFor(() =>
      expect(requests.map(([method]) => method)).toEqual([
        "apps.list",
        "apps.list",
        "apps.refresh",
        "apps.list",
      ]),
    );
  });

  it("says when app control is not available", async () => {
    const { client } = requestClient({ "apps.list": { available: false, apps: [] } });
    render(<Skills client={client} />);
    await vi.waitFor(() =>
      expect(screen.getByText("App control is not available on this system.")).toBeTruthy(),
    );
  });
});
