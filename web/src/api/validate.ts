import Ajv2020 from "ajv/dist/2020";
import schema from "../../../contracts/schemas/C.schema.json";
import type { Report } from "./types";
const ajv = new Ajv2020({ strict: false, allErrors: true });
const validate = ajv.compile<Report>(schema);
export function validateReport(value: unknown): Report {
  if (!validate(value))
    throw new Error(
      "The solar report does not match the shared data contract. Please refresh or contact the project team.",
    );
  return value;
}
