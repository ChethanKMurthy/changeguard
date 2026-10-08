import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { renderInlineCode } from "./inline-code";

describe("renderInlineCode", () => {
  it("renders backticked fragments as code", () => {
    const { container } = render(<p>{renderInlineCode("Undefined name `REGIONAL_RATES` on line 27")}</p>);
    expect(container.querySelector("code")?.textContent).toBe("REGIONAL_RATES");
    expect(container.textContent).toBe("Undefined name REGIONAL_RATES on line 27");
  });

  it("never interprets untrusted text as HTML", () => {
    const { container } = render(<p>{renderInlineCode('`<img src=x onerror="alert(1)">` and <b>bold</b>')}</p>);
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("b")).toBeNull();
    expect(container.textContent).toContain("<b>bold</b>");
  });

  it("leaves unmatched backticks alone", () => {
    const { container } = render(<p>{renderInlineCode("a ` lone tick")}</p>);
    expect(container.querySelector("code")).toBeNull();
    expect(container.textContent).toBe("a ` lone tick");
  });
});
