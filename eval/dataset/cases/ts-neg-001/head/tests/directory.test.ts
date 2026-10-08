import { emailsOf } from "../src/services/directory";

test("collects emails", () => {
  expect(emailsOf([{ id: "1", email: "a@example.invalid" }])).toEqual(["a@example.invalid"]);
});
