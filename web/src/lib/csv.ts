import Papa from "papaparse";
import type { JobSummary, LocationInput } from "../api/types";
import { config } from "../config";
import { inServiceArea } from "./geo";

export function parseAddresses(csv: string): Array<string | LocationInput> {
  const result = Papa.parse<string[]>(csv.trim(), {
    skipEmptyLines: "greedy",
    delimiter: ",",
  });
  if (result.errors.length)
    throw new Error(`Could not read CSV: ${result.errors[0].message}`);
  const rows = result.data;
  if (!rows.length) throw new Error("Add at least one address.");
  const header = rows[0].map((cell) => cell.trim().toLowerCase());
  const addressIndex = header.indexOf("address");
  const latIndex = header.indexOf("lat");
  const lngIndex = header.indexOf("lng");
  const hasHeader = addressIndex >= 0 || latIndex >= 0 || lngIndex >= 0;
  const data = hasHeader ? rows.slice(1) : rows;
  if (!data.length || data.length > config.maxBatch)
    throw new Error(
      `Add between 1 and ${config.maxBatch} addresses per batch.`,
    );
  return data.map((row, index) => {
    const rowNumber = index + (hasHeader ? 2 : 1);
    if (
      latIndex >= 0 &&
      lngIndex >= 0 &&
      row[latIndex]?.trim() &&
      row[lngIndex]?.trim()
    ) {
      const lat = Number(row[latIndex]);
      const lng = Number(row[lngIndex]);
      if (!inServiceArea(lat, lng))
        throw new Error(
          `Row ${rowNumber}: coordinates must be inside the Delhi/NCR service area.`,
        );
      return {
        lat,
        lng,
        ...(addressIndex >= 0 && row[addressIndex]?.trim()
          ? { address: row[addressIndex].trim() }
          : {}),
      };
    }
    const address = row[hasHeader ? addressIndex : 0]?.trim();
    if (!address)
      throw new Error(`Row ${rowNumber}: add an address or both lat and lng.`);
    if (!hasHeader && row.length > 1)
      throw new Error(
        `Row ${rowNumber}: put addresses containing commas in double quotes, or use an address header.`,
      );
    return address;
  });
}

const safeCell = (value: unknown) => {
  const text = value == null ? "" : String(value);
  return /^[\s]*[=+@-]/.test(text) ? `'${text}` : text;
};
export function jobsCsv(jobs: JobSummary[]): string {
  return Papa.unparse({
    fields: [
      "job_id",
      "address",
      "status",
      "system_kw",
      "annual_kwh",
      "payback_years",
      "created_at",
    ],
    data: jobs.map((job) =>
      [
        job.job_id,
        job.address,
        job.status,
        job.kw_dc,
        job.annual_kwh,
        job.payback_years,
        job.created_at,
      ].map(safeCell),
    ),
  });
}
export function downloadText(
  text: string,
  name: string,
  type = "text/csv;charset=utf-8",
) {
  const url = URL.createObjectURL(new Blob(["\uFEFF", text], { type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
