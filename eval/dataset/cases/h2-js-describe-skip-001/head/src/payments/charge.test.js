import { charge } from "./charge";

describe.skip("charge", () => {
  it("rejects negative amounts", () => {
    expect(() => charge(-1)).toThrow();
  });
});
