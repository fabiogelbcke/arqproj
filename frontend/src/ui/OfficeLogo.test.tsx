import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { OfficeLogo } from "./OfficeLogo";

describe("the office's logo", () => {
  it("is sized by its shape once loaded", () => {
    render(<OfficeLogo light="/logo.png" alt="Alinea" />);
    const logo = screen.getByRole("img", { name: "Alinea" });
    expect(logo.style.getPropertyValue("--logo-r")).toBe(""); // the usual 4:1 until then
    Object.defineProperties(logo, { naturalWidth: { value: 400 }, naturalHeight: { value: 100 } });
    fireEvent.load(logo);
    expect(logo.style.getPropertyValue("--logo-r")).toBe("4");
  });

  it("brings the dark mode logo along when there is one, for the theme to choose", () => {
    const { container, rerender } = render(<OfficeLogo light="/logo.png" alt="Alinea" />);
    expect(container.querySelectorAll("img")).toHaveLength(1);
    rerender(<OfficeLogo light="/logo.png" dark="/logo?dark=true" alt="Alinea" />);
    const [light, dark] = container.querySelectorAll("img");
    expect(dark).toHaveAttribute("src", "/logo?dark=true");
    expect(light!.parentElement).toHaveAttribute("data-dark");
  });
});
