import { compile } from "json-schema-to-typescript";
import { readFile, writeFile, mkdir } from "node:fs/promises";

await mkdir(new URL("../src/api/generated/", import.meta.url), {
  recursive: true,
});
// The generator understands tuple-style items; normalize draft-2020-12 prefixItems
// only in memory. Runtime validation always uses the original shared schemas.
function normalize(value) {
  if (Array.isArray(value)) return value.map(normalize);
  if (value && typeof value === "object") {
    const result = Object.fromEntries(
      Object.entries(value).map(([key, child]) => [key, normalize(child)]),
    );
    if (result.prefixItems) {
      result.items = result.prefixItems;
      result.additionalItems = false;
      delete result.prefixItems;
    }
    return result;
  }
  return value;
}
for (const [contract, title] of [
  ["A", "RoofJob"],
  ["B", "Segmentation"],
  ["C", "Report"],
]) {
  const source = new URL(
    `../../contracts/schemas/${contract}.schema.json`,
    import.meta.url,
  );
  const schema = normalize(JSON.parse(await readFile(source, "utf8")));
  schema.title = title;
  const result = await compile(schema, title, {
    bannerComment:
      "/* Generated from contracts/schemas. Run npm run generate:types. */",
  });
  await writeFile(
    new URL(`../src/api/generated/${contract}.ts`, import.meta.url),
    result,
    "utf8",
  );
}
