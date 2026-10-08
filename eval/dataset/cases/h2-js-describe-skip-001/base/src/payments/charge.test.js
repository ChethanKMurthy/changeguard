import { charge } from "./charge";

describe("charge", () => {
  it("rejects negative amounts", () => {
    expect(() => charge(-1)).toThrow();
  });
});
