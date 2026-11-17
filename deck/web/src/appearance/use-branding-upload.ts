import { useState } from "react";
import type { Branding } from "@deck/contract";

/** Controller owns browser decoding resources; controls only render data/actions. */
export function useBrandingUpload(onChange: (patch: Partial<Branding>) => void) {
  const [error, setError] = useState("");
  async function upload(file: File | undefined, key: "logoLight" | "logoDark") {
    if (!file) return;
    if (!["image/png", "image/jpeg", "image/webp"].includes(file.type) || file.size > 250_000) { setError("Elige PNG, JPG o WebP de hasta 250 KB."); return; }
    try {
      const image = await createImageBitmap(file);
      if (image.width > 4096 || image.height > 4096) { image.close(); setError("El logo debe medir como máximo 4096 × 4096 píxeles."); return; }
      image.close();
      const data = await new Promise<string>((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result)); reader.onerror = reject; reader.readAsDataURL(file); });
      onChange({ [key]: data }); setError("");
    } catch { setError("No se pudo leer la imagen."); }
  }
  return { error, upload };
}
