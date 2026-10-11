import { copyFile, mkdir } from "node:fs/promises";
await mkdir(new URL("../public/demo/", import.meta.url), { recursive: true });
for (const [source, target] of [
  ["rgb.png", "rooftop.png"],
  ["shade_C.png", "shade.png"],
]) {
  await copyFile(
    new URL(`../../contracts/fixtures/${source}`, import.meta.url),
    new URL(`../public/demo/${target}`, import.meta.url),
  );
}
